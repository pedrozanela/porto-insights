"""Máquina de estados do Genie One (ask → poll → get_query_result) com fixtures, sem rede.

Faz monkeypatch de mcp_session para devolver uma sessão fake roteirizada, e verifica que
run_genie_ask emite os progress_steps na ordem e monta o GenieResult final (texto, SQL,
colunas/linhas via genie_get_query_result, deep link e fontes citadas).
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass

import pytest

from backend.genie import client as genie_client


@dataclass
class _Text:
    text: str


class _Result:
    def __init__(self, structured: dict | None = None, text: str = "") -> None:
        self.structured_content = structured or {}
        self.content = [_Text(text)] if text else []


class FakeSession:
    """Sessão MCP fake: responde call_tool conforme um roteiro fixo."""

    def __init__(self) -> None:
        self.poll_calls = 0
        self.calls: list[str] = []

    async def call_tool(self, name, arguments=None, meta=None):  # noqa: ANN001
        self.calls.append(name)
        if name == "genie_ask":
            return _Result({"conversation_id": "conv-1", "response_id": "resp-1", "status": "in_progress"})
        if name == "genie_poll_response":
            self.poll_calls += 1
            if self.poll_calls == 1:
                return _Result({
                    "status": "in_progress",
                    "progress_steps": ["Thinking: procurando fontes", "Running SQL: SELECT ..."],
                })
            return _Result(
                {
                    "status": "completed",
                    "conversation_id": "conv-1",
                    "response_id": "resp-1",
                    "final_answer": "Capital de Giro PJ atingiu 118% da meta.",
                    "deep_link": "https://ws/one/chat/threads/conv-1",
                    "progress_steps": None,
                    "query_items": [{"item_id": "pub_x_output", "sql": "SELECT `Produto` FROM cat.sch.mv_carteira_credito"}],
                },
                text="[mv_carteira_credito](https://ws/explore/data/cat/sch/mv_carteira_credito) "
                     "[Explore in Databricks](https://ws/one/chat/threads/conv-1)",
            )
        if name == "genie_get_query_result":
            return _Result({
                "columns": [{"name": "Produto"}, {"name": "Originação"}],
                "rows": [["Capital de Giro PJ", "43190900.00"]],
                "total_row_count": 1,
                "truncated": False,
            })
        raise AssertionError(f"tool inesperada: {name}")


@pytest.fixture
def patch_session(monkeypatch):
    session = FakeSession()

    @contextlib.asynccontextmanager
    async def fake_mcp_session(url, token, timeout=120):  # noqa: ANN001
        yield session

    monkeypatch.setattr(genie_client, "mcp_session", fake_mcp_session)
    return session


async def _collect(**kwargs):
    progress, result = [], None
    async for kind, payload in genie_client.run_genie_ask(**kwargs):
        if kind == "progress":
            progress.append(payload)
        else:
            result = payload
    return progress, result


BASE = dict(
    host_url="https://ws", token="t", warehouse_id="wh", question="q",
    conversation_id=None, poll_initial_ms=1, poll_max_ms=2, max_wait_s=10, max_rows_to_llm=50,
)


async def test_progress_then_completed(patch_session):
    progress, result = await _collect(**BASE)
    assert progress[0] == "Perguntando ao Genie One…"
    assert "Thinking: procurando fontes" in progress
    assert "Running SQL: SELECT ..." in progress
    assert result.status == "completed"
    assert "118%" in result.answer
    assert result.deep_link == "https://ws/one/chat/threads/conv-1"


async def test_query_result_and_sources(patch_session):
    _, result = await _collect(**BASE)
    assert result.columns == ["Produto", "Originação"]
    assert result.rows == [["Capital de Giro PJ", "43190900.00"]]
    assert result.truncated is False
    # link citado de /explore/data/ foi capturado
    labels = [l[0] for l in result.links]
    assert "mv_carteira_credito" in labels


async def test_follow_up_passes_conversation_id(patch_session, monkeypatch):
    captured = {}
    original = patch_session.call_tool

    async def spy(name, arguments=None, meta=None):  # noqa: ANN001
        if name == "genie_ask":
            captured["args"] = arguments
        return await original(name, arguments, meta)

    monkeypatch.setattr(patch_session, "call_tool", spy)
    await _collect(**{**BASE, "conversation_id": "conv-prev"})
    assert captured["args"].get("conversation_id") == "conv-prev"
