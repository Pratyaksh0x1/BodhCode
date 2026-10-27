"""Unit and integration tests for grounded file explanation."""


import networkx as nx
import pytest
from sqlmodel import Session

from app.ai.explain import explain_file
from app.ai.llm import LLMClient, LLMResult, LLMUsage
from app.models.repo import Repo


class FakeExplainLLM(LLMClient):
    """Fake LLM client that records prompts and returns deterministic responses."""

    def __init__(self, response_text: str = "This file manages user authentication.") -> None:
        self.response_text = response_text
        self.call_count = 0
        self.captured_messages: list[dict] = []

    async def chat(self, messages, **kwargs) -> LLMResult:
        self.call_count += 1
        self.captured_messages = messages
        return LLMResult(
            text=self.response_text,
            latency_ms=10.0,
            model="fake-groq",
            usage=LLMUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )


@pytest.fixture
def explain_graph() -> nx.DiGraph:
    """Fixture providing a test dependency graph."""
    g = nx.DiGraph()
    g.add_node(
        "src/auth.ts",
        name="auth.ts",
        size=1500,
        exports=["login", "logout"],
        has_default_export=False,
        external_deps=["jsonwebtoken"],
    )
    g.add_node(
        "src/utils.ts",
        name="utils.ts",
        size=500,
        exports=["formatDate"],
        has_default_export=False,
        external_deps=[],
    )
    # utils.ts imports auth.ts (auth.ts has 1 dependent)
    g.add_edge("src/utils.ts", "src/auth.ts", kinds={"import"}, type_only=False, count=1)
    return g


@pytest.mark.asyncio
async def test_explain_facts_grounded_in_prompt(
    explain_graph: nx.DiGraph,
    db_session: Session,
) -> None:
    """Assert captured prompt contains strictly facts from the graph and wraps source."""
    repo = Repo(id=1, owner="test", name="repo", branch="main", commit_sha="abc1234", user_id=1)
    fake_llm = FakeExplainLLM("Explanation referencing `src/utils.ts`.")

    res = await explain_file(
        repo=repo,
        file_path="src/auth.ts",
        language="en",
        graph=explain_graph,
        source_dir=None,
        session=db_session,
        llm_client=fake_llm,
    )

    assert fake_llm.call_count == 1
    captured_user = fake_llm.captured_messages[-1]["content"]

    # Verify captured prompt facts match graph facts
    assert "File Path: src/auth.ts" in captured_user
    assert "Size: 1500 bytes" in captured_user
    assert "Named Exports: login, logout" in captured_user
    assert "Direct Dependents (importers): src/utils.ts" in captured_user
    assert "External Packages: jsonwebtoken" in captured_user

    # Verify result verified files and no flagged files
    assert "src/utils.ts" in res.verified_files
    assert len(res.flagged) == 0
    assert not res.cached


@pytest.mark.asyncio
async def test_explain_flags_invented_files(
    explain_graph: nx.DiGraph,
    db_session: Session,
) -> None:
    """Assert invented filenames in the LLM output are flagged and annotated with warning."""
    repo = Repo(id=1, owner="test", name="repo", branch="main", commit_sha="abc1234", user_id=1)
    fake_llm = FakeExplainLLM("`src/auth.ts` calls `src/fake/secret.ts`.")

    res = await explain_file(
        repo=repo,
        file_path="src/auth.ts",
        language="en",
        graph=explain_graph,
        source_dir=None,
        session=db_session,
        llm_client=fake_llm,
    )

    assert "src/auth.ts" in res.verified_files
    assert "src/fake/secret.ts" in res.flagged
    assert "`src/fake/secret.ts` ⚠unverified" in res.explanation


@pytest.mark.asyncio
async def test_explain_cache_hit_makes_zero_llm_calls(
    explain_graph: nx.DiGraph,
    db_session: Session,
) -> None:
    """Second identical call must be a cache hit and make zero LLM calls."""
    repo = Repo(id=1, owner="test", name="repo", branch="main", commit_sha="c12345", user_id=1)
    fake_llm = FakeExplainLLM("A good file explanation.")

    # First call: cache miss
    res1 = await explain_file(
        repo=repo,
        file_path="src/auth.ts",
        language="en",
        graph=explain_graph,
        source_dir=None,
        session=db_session,
        llm_client=fake_llm,
    )
    assert fake_llm.call_count == 1
    assert not res1.cached

    # Second call: cache hit
    res2 = await explain_file(
        repo=repo,
        file_path="src/auth.ts",
        language="en",
        graph=explain_graph,
        source_dir=None,
        session=db_session,
        llm_client=fake_llm,
    )
    # Call count remains 1!
    assert fake_llm.call_count == 1
    assert res2.cached
    assert res2.explanation == res1.explanation
