"""Cliente do Genie One via MCP: máquina de estados ask → poll → get_query_result.

O ciclo assíncrono do Genie NÃO é exposto ao LLM. Ele é encapsulado aqui e, acima, na tool
composta `genie__ask`. Nomes de tools confirmados na Fase 0: genie_ask, genie_poll_response,
genie_get_query_result (sem view_ask neste servidor).

Autenticação: token OBO do usuário (as permissões de UC e os deep links valem para ele).
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from mcp import ClientSession

from ..mcp.client import mcp_session, structured, text_content

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


@dataclass
class GenieResult:
    status: str
    conversation_id: str
    response_id: str
    answer: str = ""
    deep_link: str | None = None
    sql: str | None = None
    item_id: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False
    # links citados no corpo (label, url) — fontes e "Explore in Databricks"
    links: list[tuple[str, str]] = field(default_factory=list)


def _best_query_item(query_items: list[dict]) -> dict | None:
    """Escolhe a query de agregação relevante, ignorando SHOW CREATE / DESCRIBE de inspeção."""
    agg = [
        qi for qi in query_items
        if (qi.get("sql") or "").strip().upper().startswith("SELECT")
        and "SHOW CREATE" not in (qi.get("sql") or "").upper()
    ]
    chosen = agg[-1] if agg else (query_items[-1] if query_items else None)
    return chosen


async def _get_query_result(s: ClientSession, cid: str, rid: str, item_id: str) -> dict:
    res = await s.call_tool(
        "genie_get_query_result",
        {"conversation_id": cid, "response_id": rid, "item_id": item_id},
    )
    return structured(res)


async def run_genie_ask(
    *,
    host_url: str,
    token: str,
    warehouse_id: str,
    question: str,
    conversation_id: str | None,
    poll_initial_ms: int,
    poll_max_ms: int,
    max_wait_s: int,
    max_rows_to_llm: int,
) -> AsyncIterator[tuple[str, Any]]:
    """Gera eventos do ciclo do Genie:
      ("progress", "texto do passo")  — cada progress_step novo
      ("result",   GenieResult)       — resultado final (uma vez, no fim)
    """
    url = f"{host_url}/api/2.0/mcp/genie"
    async with mcp_session(url, token, timeout=max_wait_s + 30) as s:
        args: dict[str, Any] = {"question": question}
        if conversation_id:
            args["conversation_id"] = conversation_id
        # warehouse_id vai no _meta da requisição MCP (não como argumento da tool).
        ask = structured(await s.call_tool("genie_ask", args, meta={"warehouse_id": warehouse_id}))
        cid = ask.get("conversation_id") or conversation_id or ""
        rid = ask.get("response_id") or ""

        yield ("progress", "Perguntando ao Genie One…")

        seen = 0
        started = time.time()
        delay = poll_initial_ms / 1000.0
        while time.time() - started < max_wait_s:
            await asyncio.sleep(delay)
            delay = min(delay * 1.4, poll_max_ms / 1000.0)
            poll_res = await s.call_tool(
                "genie_poll_response", {"conversation_id": cid, "response_id": rid}
            )
            poll = structured(poll_res)
            for step in (poll.get("progress_steps") or [])[seen:]:
                yield ("progress", step)
            seen = max(seen, len(poll.get("progress_steps") or []))

            status = poll.get("status")
            if status and status != "in_progress":
                body = text_content(poll_res)
                result = GenieResult(
                    status=status, conversation_id=cid, response_id=rid,
                    answer=poll.get("final_answer") or "",
                    deep_link=poll.get("deep_link"),
                    links=LINK_RE.findall(body),
                )
                qi = _best_query_item(poll.get("query_items") or [])
                if qi:
                    result.sql = qi.get("sql")
                    result.item_id = qi.get("item_id")
                    if status == "completed" and result.item_id:
                        try:
                            qr = await _get_query_result(s, cid, rid, result.item_id)
                            result.columns = [c.get("name", "") for c in (qr.get("columns") or [])]
                            result.rows = (qr.get("rows") or [])[:max_rows_to_llm]
                            result.truncated = bool(qr.get("truncated"))
                        except Exception:  # noqa: BLE001
                            pass  # sem dados tabulares; o texto/answer basta
                yield ("result", result)
                return

        yield ("result", GenieResult(status="timeout", conversation_id=cid, response_id=rid,
                                     answer="O Genie One demorou além do tempo limite."))
