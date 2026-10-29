"""Agent write tools: create_file, edit_file, delete_file.

These tools NEVER modify the repository directly; they produce Proposals for review,
or apply them via the review policy when in auto mode.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import select

from app.ai.review import apply_proposal, decide
from app.ai.tools.base import Tool, ToolContext, ToolResult
from app.files.errors import FileNotFound, InvalidPath
from app.files.service import compute_content_hash, normalize_path
from app.models.proposals import Proposal
from app.parser.blast import blast_radius as blast_algo

MAX_PENDING_PROPOSALS = 50


class CreateFileTool(Tool):
    """Propose creating a new file with specified initial content."""

    name = "create_file"
    description = (
        "Create a proposal to add a new file. Fails if the file already exists. "
        "In Review mode, creates a pending proposal; in Auto mode, applies immediately."
    )
    permission = "write"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Normalized target path to create."},
            "content": {"type": "string", "description": "Initial text content of the new file."},
            "rationale": {
                "type": "string",
                "description": "Short explanation of why this file is being created.",
            },
        },
        "required": ["path", "content", "rationale"],
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        raw_path = args.get("path", "")
        content = args.get("content", "")
        rationale = args.get("rationale", "")

        try:
            path = normalize_path(raw_path)
        except InvalidPath as exc:
            return ToolResult(
                ok=False,
                data={"error": f"Invalid path: {exc}"},
                error=f"Invalid path: {exc}",
                summary=f"create_file {raw_path} (invalid path)",
            )

        decision = decide(ctx.review_mode, "create")
        ro_err = "Read-only mode is active. Cannot create files. Describe the plan instead."
        if decision == "block":
            return ToolResult(
                ok=False,
                data={"error": ro_err},
                error=ro_err,
                summary=f"create_file {path} (blocked: read-only)",
            )

        # Check if file already exists in effective repository
        if ctx.files is not None:
            try:
                ctx.files.read_effective(path)
                return ToolResult(
                    ok=False,
                    data={"error": f"File '{path}' already exists."},
                    error=f"File '{path}' already exists.",
                    summary=f"create_file {path} (already exists)",
                )
            except FileNotFound:
                pass

        if ctx.session is None or ctx.user is None or ctx.repo is None:
            return ToolResult(
                ok=False,
                data={"error": "Database session, user, or repository context missing."},
                error="Database session, user, or repository context missing.",
                summary=f"create_file {path} (context error)",
            )

        # Enforce maximum pending proposals limit
        pending_count = len(
            ctx.session.exec(
                select(Proposal).where(
                    Proposal.repo_id == ctx.repo.id,
                    Proposal.status == "pending",
                )
            ).all()
        )
        if pending_count >= MAX_PENDING_PROPOSALS:
            return ToolResult(
                ok=False,
                data={
                    "error": f"Maximum pending proposals limit ({MAX_PENDING_PROPOSALS}) reached."
                },
                error=f"Maximum pending proposals limit ({MAX_PENDING_PROPOSALS}) reached.",
                summary=f"create_file {path} (too many proposals)",
            )

        proposal = Proposal(
            user_id=ctx.user.id,
            repo_id=ctx.repo.id,
            session_id=ctx.session_id,
            kind="create",
            path=path,
            old_content=None,
            new_content=content,
            base_hash=None,
            rationale=rationale,
            blast_radius_count=0,
            status="pending",
        )
        ctx.session.add(proposal)
        ctx.session.commit()
        ctx.session.refresh(proposal)

        if decision == "apply":
            apply_proposal(proposal, ctx.user, ctx.repo, ctx.session)

        return ToolResult(
            ok=True,
            data={
                "proposal_id": proposal.id,
                "kind": "create",
                "path": path,
                "status": proposal.status,
                "rationale": rationale,
                "blast_radius_count": 0,
            },
            proposal_id=proposal.id,
            summary=f"create_file {path} -> proposal #{proposal.id} ({proposal.status})",
        )


class EditFileTool(Tool):
    """Propose modifying an existing file via unique substring replacement."""

    name = "edit_file"
    description = (
        "Propose editing a file by replacing a unique substring. 'old' must match exactly once "
        "in the effective file content. Produces a proposal for review."
    )
    permission = "write"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Normalized target path to edit."},
            "old": {
                "type": "string",
                "description": "Exact text substring to replace (must appear exactly once).",
            },
            "new": {"type": "string", "description": "New replacement text substring."},
            "rationale": {
                "type": "string",
                "description": "Short explanation of the edit and why it was made.",
            },
        },
        "required": ["path", "old", "new", "rationale"],
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        raw_path = args.get("path", "")
        old_sub = args.get("old", "")
        new_sub = args.get("new", "")
        rationale = args.get("rationale", "")

        try:
            path = normalize_path(raw_path)
        except InvalidPath as exc:
            return ToolResult(
                ok=False,
                data={"error": f"Invalid path: {exc}"},
                error=f"Invalid path: {exc}",
                summary=f"edit_file {raw_path} (invalid path)",
            )

        decision = decide(ctx.review_mode, "edit")
        ro_err = "Read-only mode is active. Cannot edit files. Describe the plan instead."
        if decision == "block":
            return ToolResult(
                ok=False,
                data={"error": ro_err},
                error=ro_err,
                summary=f"edit_file {path} (blocked: read-only)",
            )

        if ctx.files is None:
            return ToolResult(
                ok=False,
                data={"error": "File service unavailable."},
                error="File service unavailable.",
                summary=f"edit_file {path} (error)",
            )

        try:
            eff = ctx.files.read_effective(path)
            current_content = eff["content"]
        except FileNotFound:
            return ToolResult(
                ok=False,
                data={"error": f"File '{path}' not found."},
                error=f"File '{path}' not found.",
                summary=f"edit_file {path} (not found)",
            )

        match_count = current_content.count(old_sub)
        if match_count == 0:
            return ToolResult(
                ok=False,
                data={
                    "error": f"Substring 'old' not found in '{path}'. Zero matches.",
                    "match_count": 0,
                },
                error=f"Substring 'old' not found in '{path}'. Zero matches.",
                summary=f"edit_file {path} (0 matches)",
            )
        if match_count > 1:
            return ToolResult(
                ok=False,
                data={
                    "error": (
                        f"Substring 'old' matches {match_count} times in '{path}'. "
                        "Must match exactly once. Include more surrounding lines for uniqueness."
                    ),
                    "match_count": match_count,
                },
                error=(
                    f"Substring 'old' matches {match_count} times in '{path}'. "
                    "Must match exactly once. Include more surrounding lines for uniqueness."
                ),
                summary=f"edit_file {path} ({match_count} matches)",
            )

        new_full_content = current_content.replace(old_sub, new_sub, 1)

        if ctx.session is None or ctx.user is None or ctx.repo is None:
            return ToolResult(
                ok=False,
                data={"error": "Database session, user, or repository context missing."},
                error="Database session, user, or repository context missing.",
                summary=f"edit_file {path} (context error)",
            )

        pending_count = len(
            ctx.session.exec(
                select(Proposal).where(
                    Proposal.repo_id == ctx.repo.id,
                    Proposal.status == "pending",
                )
            ).all()
        )
        if pending_count >= MAX_PENDING_PROPOSALS:
            return ToolResult(
                ok=False,
                data={
                    "error": f"Maximum pending proposals limit ({MAX_PENDING_PROPOSALS}) reached."
                },
                error=f"Maximum pending proposals limit ({MAX_PENDING_PROPOSALS}) reached.",
                summary=f"edit_file {path} (too many proposals)",
            )

        base_hash = compute_content_hash(current_content)
        blast_count = None
        if ctx.graph is not None and path in ctx.graph:
            try:
                impacts = blast_algo(ctx.graph, path, max_depth=3)
                blast_count = len(impacts)
            except Exception:
                blast_count = None

        proposal = Proposal(
            user_id=ctx.user.id,
            repo_id=ctx.repo.id,
            session_id=ctx.session_id,
            kind="edit",
            path=path,
            old_content=current_content,
            new_content=new_full_content,
            base_hash=base_hash,
            rationale=rationale,
            blast_radius_count=blast_count,
            status="pending",
        )
        ctx.session.add(proposal)
        ctx.session.commit()
        ctx.session.refresh(proposal)

        if decision == "apply":
            apply_proposal(proposal, ctx.user, ctx.repo, ctx.session)

        return ToolResult(
            ok=True,
            data={
                "proposal_id": proposal.id,
                "kind": "edit",
                "path": path,
                "status": proposal.status,
                "blast_radius_count": blast_count,
                "rationale": rationale,
            },
            proposal_id=proposal.id,
            summary=f"edit_file {path} -> proposal #{proposal.id} ({proposal.status})",
        )


class DeleteFileTool(Tool):
    """Propose deleting a file from the repository."""

    name = "delete_file"
    description = (
        "Propose deleting an existing file. Deletion always requires human review "
        "and is never automatically applied even in Auto mode."
    )
    permission = "write"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Normalized target path to delete."},
            "rationale": {
                "type": "string",
                "description": "Short explanation of why this file is being deleted.",
            },
        },
        "required": ["path", "rationale"],
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        raw_path = args.get("path", "")
        rationale = args.get("rationale", "")

        try:
            path = normalize_path(raw_path)
        except InvalidPath as exc:
            return ToolResult(
                ok=False,
                data={"error": f"Invalid path: {exc}"},
                error=f"Invalid path: {exc}",
                summary=f"delete_file {raw_path} (invalid path)",
            )

        decision = decide(ctx.review_mode, "delete")
        if decision == "block":
            return ToolResult(
                ok=False,
                data={"error": "Read-only mode is active. Cannot delete files."},
                error="Read-only mode is active. Cannot delete files.",
                summary=f"delete_file {path} (blocked: read-only)",
            )

        if ctx.files is None:
            return ToolResult(
                ok=False,
                data={"error": "File service unavailable."},
                error="File service unavailable.",
                summary=f"delete_file {path} (error)",
            )

        try:
            eff = ctx.files.read_effective(path)
            current_content = eff["content"]
        except FileNotFound:
            return ToolResult(
                ok=False,
                data={"error": f"File '{path}' not found to delete."},
                error=f"File '{path}' not found to delete.",
                summary=f"delete_file {path} (not found)",
            )

        if ctx.session is None or ctx.user is None or ctx.repo is None:
            return ToolResult(
                ok=False,
                data={"error": "Database session, user, or repository context missing."},
                error="Database session, user, or repository context missing.",
                summary=f"delete_file {path} (context error)",
            )

        pending_count = len(
            ctx.session.exec(
                select(Proposal).where(
                    Proposal.repo_id == ctx.repo.id,
                    Proposal.status == "pending",
                )
            ).all()
        )
        if pending_count >= MAX_PENDING_PROPOSALS:
            return ToolResult(
                ok=False,
                data={
                    "error": f"Maximum pending proposals limit ({MAX_PENDING_PROPOSALS}) reached."
                },
                error=f"Maximum pending proposals limit ({MAX_PENDING_PROPOSALS}) reached.",
                summary=f"delete_file {path} (too many proposals)",
            )

        base_hash = compute_content_hash(current_content)
        blast_count = None
        if ctx.graph is not None and path in ctx.graph:
            try:
                impacts = blast_algo(ctx.graph, path, max_depth=3)
                blast_count = len(impacts)
            except Exception:
                blast_count = None

        # Even in auto mode, decide("auto", "delete") is "queue", so delete always queues!
        proposal = Proposal(
            user_id=ctx.user.id,
            repo_id=ctx.repo.id,
            session_id=ctx.session_id,
            kind="delete",
            path=path,
            old_content=current_content,
            new_content=None,
            base_hash=base_hash,
            rationale=rationale,
            blast_radius_count=blast_count,
            status="pending",
        )
        ctx.session.add(proposal)
        ctx.session.commit()
        ctx.session.refresh(proposal)

        return ToolResult(
            ok=True,
            data={
                "proposal_id": proposal.id,
                "kind": "delete",
                "path": path,
                "status": "pending",
                "blast_radius_count": blast_count,
                "rationale": rationale,
            },
            proposal_id=proposal.id,
            summary=f"delete_file {path} -> proposal #{proposal.id} (pending)",
        )
