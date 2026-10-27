"""Translation engine with masking, caching, paragraph chunking, and batching."""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from app.ai.llm import LLMClient, LLMRateLimited
from app.ai.prompts.translate import (
    VERSION,
    build_batch_translate_messages,
    build_translate_messages,
)
from app.ai.tracing import update_current_llm_run
from app.i18n.mask import _PLACEHOLDER_RE, mask_protected, placeholders_intact, unmask
from app.models.translation import TranslationCache
from app.models.user import utc_now

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 2500
MAX_BATCH_ITEMS = 25
MAX_BATCH_CHARS = 3000


@dataclass
class TranslationResult:
    """Outcome of a translation request."""

    text: str
    source_lang: str | None
    target_lang: str
    from_cache: bool
    ok: bool
    reason: str | None = None


def compute_cache_key(
    source_lang: str | None,
    target_lang: str,
    kind: str,
    text: str,
) -> str:
    """Compute deterministic SHA-256 cache key including prompt version."""
    src = source_lang or ""
    key_str = f"{VERSION}|{src}|{target_lang}|{kind}|{text}"
    return hashlib.sha256(key_str.encode("utf-8")).hexdigest()


def chunk_by_paragraphs(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text along paragraph boundaries to keep each chunk under max_chars."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        # If a single paragraph exceeds max_chars, split along single newlines
        if para_len > max_chars:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            lines = para.split("\n")
            line_chunk: list[str] = []
            line_len = 0
            for line in lines:
                if line_chunk and (line_len + len(line) + 1 > max_chars):
                    chunks.append("\n".join(line_chunk))
                    line_chunk = [line]
                    line_len = len(line)
                else:
                    line_chunk.append(line)
                    line_len += len(line) + (1 if line_len > 0 else 0)
            if line_chunk:
                chunks.append("\n".join(line_chunk))
            continue

        if current_chunk and (current_len + para_len + 2 > max_chars):
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_len = para_len
        else:
            current_chunk.append(para)
            current_len += para_len + (2 if current_len > 0 else 0)

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


async def translate_text(
    text: str,
    *,
    source: str | None,
    target: str,
    kind: str,
    session: Session,
    llm_client: LLMClient | None = None,
    refresh: bool = False,
) -> TranslationResult:
    """Translate markdown or plain text with caching, masking, and placeholder verification.

    If source is None or source == target, returns original text without LLM invocation.
    """
    if not text.strip() or source is None or source == target:
        return TranslationResult(
            text=text,
            source_lang=source or target,
            target_lang=target,
            from_cache=False,
            ok=True,
        )

    cache_key = compute_cache_key(source, target, kind, text)

    # 1. Cache lookup unless refresh is explicitly requested
    if not refresh:
        cached = session.get(TranslationCache, cache_key)
        if cached:
            return TranslationResult(
                text=cached.text,
                source_lang=cached.source_lang,
                target_lang=cached.target_lang,
                from_cache=True,
                ok=True,
            )

    client = llm_client or LLMClient()

    # 2. Mask protected elements (code, links, traces, etc.)
    masked_text, mapping = mask_protected(text)

    # 3. Chunk into paragraph-bounded slices
    chunks = chunk_by_paragraphs(masked_text, MAX_CHUNK_CHARS)
    translated_chunks: list[str] = []

    for chunk in chunks:
        # Identify placeholders local to this chunk
        chunk_tokens = set(_PLACEHOLDER_RE.findall(chunk))
        chunk_mapping = {t: mapping[t] for t in chunk_tokens if t in mapping}

        messages = build_translate_messages(chunk, source, target, kind=kind)

        try:
            res = await client.chat(
                messages=messages,
                feature=f"translate.{kind}",
                fast=True,
                temperature=0.0,
            )
            update_current_llm_run(
                feature=f"translate.{kind}",
                model=res.model,
                prompt_name="translate",
                prompt_version=VERSION,
                usage=res.usage,
            )
            translated_chunk = res.text.strip()
        except LLMRateLimited:
            logger.warning("Translation rate limited by Groq API")
            return TranslationResult(
                text=text,
                source_lang=source,
                target_lang=target,
                from_cache=False,
                ok=False,
                reason="busy",
            )
        except Exception as err:
            logger.warning(f"Translation LLM call failed: {type(err).__name__}")
            return TranslationResult(
                text=text,
                source_lang=source,
                target_lang=target,
                from_cache=False,
                ok=False,
                reason="unavailable",
            )

        # 4. Verify placeholders in this chunk; retry once if damaged
        if not placeholders_intact(translated_chunk, chunk_mapping):
            try:
                retry_res = await client.chat(
                    messages=messages,
                    feature=f"translate.{kind}",
                    fast=True,
                    temperature=0.0,
                )
                translated_chunk = retry_res.text.strip()
            except Exception:
                return TranslationResult(
                    text=text,
                    source_lang=source,
                    target_lang=target,
                    from_cache=False,
                    ok=False,
                    reason="placeholder_mismatch",
                )

            if not placeholders_intact(translated_chunk, chunk_mapping):
                return TranslationResult(
                    text=text,
                    source_lang=source,
                    target_lang=target,
                    from_cache=False,
                    ok=False,
                    reason="placeholder_mismatch",
                )

        translated_chunks.append(translated_chunk)

    # 5. Join chunks and unmask
    full_translated_masked = "\n\n".join(translated_chunks)
    if not placeholders_intact(full_translated_masked, mapping):
        return TranslationResult(
            text=text,
            source_lang=source,
            target_lang=target,
            from_cache=False,
            ok=False,
            reason="placeholder_mismatch",
        )

    final_text = unmask(full_translated_masked, mapping)

    # 6. Store in persistent cache
    try:
        cache_entry = TranslationCache(
            key=cache_key,
            source_lang=source,
            target_lang=target,
            kind=kind,
            prompt_version=VERSION,
            text=final_text,
            created_at=utc_now(),
        )
        session.merge(cache_entry)
        session.commit()
    except Exception as exc:
        logger.warning(f"Failed to persist translation cache: {exc}")
        session.rollback()

    return TranslationResult(
        text=final_text,
        source_lang=source,
        target_lang=target,
        from_cache=False,
        ok=True,
    )


async def translate_many(
    items: list[str],
    *,
    source: str | None,
    target: str,
    kind: str,
    session: Session,
    llm_client: LLMClient | None = None,
    refresh: bool = False,
) -> list[TranslationResult]:
    """Translate a list of short strings (e.g., titles) with JSON batching.

    Batches items up to MAX_BATCH_ITEMS and MAX_BATCH_CHARS. Falls back to per-item
    translation on any JSON malformation or placeholder loss.
    """
    if not items:
        return []

    if source is None or source == target:
        return [
            TranslationResult(
                text=it,
                source_lang=source or target,
                target_lang=target,
                from_cache=False,
                ok=True,
            )
            for it in items
        ]

    client = llm_client or LLMClient()
    results: list[TranslationResult | None] = [None] * len(items)
    misses: list[tuple[int, str]] = []

    # Check cache for each item first
    for idx, item in enumerate(items):
        if not item.strip():
            results[idx] = TranslationResult(
                text=item,
                source_lang=source,
                target_lang=target,
                from_cache=False,
                ok=True,
            )
            continue

        if not refresh:
            cache_key = compute_cache_key(source, target, kind, item)
            cached = session.get(TranslationCache, cache_key)
            if cached:
                results[idx] = TranslationResult(
                    text=cached.text,
                    source_lang=cached.source_lang,
                    target_lang=cached.target_lang,
                    from_cache=True,
                    ok=True,
                )
                continue

        misses.append((idx, item))

    if not misses:
        return [r for r in results if r is not None]

    # Batch misses
    batches: list[list[tuple[int, str]]] = []
    current_batch: list[tuple[int, str]] = []
    current_chars = 0

    for idx, item in misses:
        item_len = len(item)
        if current_batch and (
            len(current_batch) >= MAX_BATCH_ITEMS or current_chars + item_len > MAX_BATCH_CHARS
        ):
            batches.append(current_batch)
            current_batch = [(idx, item)]
            current_chars = item_len
        else:
            current_batch.append((idx, item))
            current_chars += item_len

    if current_batch:
        batches.append(current_batch)

    # Process each batch
    for batch in batches:
        # Mask each item in the batch
        batch_masked_info: list[tuple[int, str, dict[str, str]]] = []
        payload_items: list[dict[str, Any]] = []

        for b_idx, (orig_idx, orig_text) in enumerate(batch):
            masked_text, mapping = mask_protected(orig_text)
            batch_masked_info.append((orig_idx, orig_text, mapping))
            payload_items.append({"i": b_idx, "t": masked_text})

        json_str = json.dumps(payload_items, ensure_ascii=False)
        messages = build_batch_translate_messages(json_str, source, target, kind=kind)

        batch_success = False
        try:
            res = await client.chat(
                messages=messages,
                feature=f"translate.{kind}",
                fast=True,
                temperature=0.0,
            )
            update_current_llm_run(
                feature=f"translate.{kind}",
                model=res.model,
                prompt_name="translate_batch",
                prompt_version=VERSION,
                usage=res.usage,
            )
            raw_text = res.text.strip()

            # Strip markdown json block fences if LLM wrapped output
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()

            parsed = json.loads(raw_text)
            if isinstance(parsed, list) and len(parsed) == len(batch):
                batch_results: list[tuple[int, str]] = []
                for b_idx, (orig_idx, _, mapping) in enumerate(batch_masked_info):
                    item_dict = parsed[b_idx]
                    if not isinstance(item_dict, dict) or item_dict.get("i") != b_idx:
                        break
                    t_val = str(item_dict.get("t", ""))
                    if not placeholders_intact(t_val, mapping):
                        break
                    unmasked_val = unmask(t_val, mapping)
                    batch_results.append((orig_idx, unmasked_val))

                if len(batch_results) == len(batch):
                    for orig_idx, unmasked_val in batch_results:
                        # Cache successful item
                        orig_text = items[orig_idx]
                        ckey = compute_cache_key(source, target, kind, orig_text)
                        try:
                            centry = TranslationCache(
                                key=ckey,
                                source_lang=source,
                                target_lang=target,
                                kind=kind,
                                prompt_version=VERSION,
                                text=unmasked_val,
                                created_at=utc_now(),
                            )
                            session.merge(centry)
                            session.commit()
                        except Exception:
                            session.rollback()

                        results[orig_idx] = TranslationResult(
                            text=unmasked_val,
                            source_lang=source,
                            target_lang=target,
                            from_cache=False,
                            ok=True,
                        )
                    batch_success = True
        except Exception as exc:
            logger.info(f"Batch translation failed, falling back to itemized: {exc}")

        # If batch failed, fallback to itemized translate_text
        if not batch_success:
            for orig_idx, orig_text, _ in batch_masked_info:
                item_res = await translate_text(
                    orig_text,
                    source=source,
                    target=target,
                    kind=kind,
                    session=session,
                    llm_client=client,
                    refresh=refresh,
                )
                results[orig_idx] = item_res

    return [r for r in results if r is not None]
