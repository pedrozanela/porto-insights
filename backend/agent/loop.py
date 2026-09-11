"""Loop de um turno — assíncrono, com tool calling.

Fluxo: chama o modelo com a tool composta genie__ask; se o modelo a invoca, executa o ciclo
do Genie One (streamando tool_progress), monta o card (tool_call_result) e os nós do grafo
(graph_delta), devolve um resultado compacto ao modelo e continua; quando o modelo responde sem
tool call, o texto final é o streaming de tokens. Limitado por AGENT_MAX_TOOL_ITERATIONS.

Persistência (histórico): só a mensagem do usuário e a resposta final do assistente vão para o
store — o andaime de tool calls é transitório. As chamadas do store (síncronas) rodam em thread.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import anyio

from ..auth import UserContext
from ..config import Settings
from ..genie.client import run_genie_ask
from ..genie.composite import GENIE_TOOL, card_payload, compact_result_for_llm
from ..graph.extractors.genie import extract_genie
from ..graph.schema import delta_payload
from ..graph.store import GraphStore
from ..llm import build_async_client, stream_turn
from ..sse import sse
from ..store.base import ConversationStore
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger("porto_insights.agent")


def _resolve_model(settings: Settings, requested: str) -> tuple[str, str | None]:
    allowed = {e.name for e in settings.endpoints}
    if requested and requested in allowed:
        return requested, None
    default = settings.default_endpoint
    if requested:
        return default, f"Modelo '{requested}' não está disponível; usando {default}."
    return default, None


async def _run_genie_tool(
    user: UserContext, settings: Settings, store: ConversationStore, graph: GraphStore,
    conversation_id: str, turn: int, question: str, follow_up: bool,
) -> AsyncIterator[dict]:
    """Executa genie__ask. Emite eventos ('progress'|'card'|'graph'|'compact')."""
    genie_cid = None
    if follow_up:
        genie_cid = await anyio.to_thread.run_sync(
            store.get_genie_conversation_id, user.email, conversation_id)

    result = None
    async for kind, payload in run_genie_ask(
        host_url=settings.host_url, token=user.token, warehouse_id=settings.sql_warehouse_id,
        question=question, conversation_id=genie_cid,
        poll_initial_ms=settings.genie_poll_initial_ms, poll_max_ms=settings.genie_poll_max_ms,
        max_wait_s=settings.genie_max_wait_s, max_rows_to_llm=settings.genie_max_rows_to_llm,
    ):
        if kind == "progress":
            yield {"kind": "progress", "step": payload}
        else:
            result = payload

    if result is None:
        yield {"kind": "compact", "text": "O Genie One não retornou resultado."}
        return

    # persiste o fio do Genie para follow-ups
    if result.conversation_id:
        await anyio.to_thread.run_sync(
            store.set_genie_conversation_id, user.email, conversation_id, result.conversation_id)

    yield {"kind": "card", "card": card_payload(result)}

    # grafo: genie_answer + data_asset + cites/follows_up
    state = graph.get(user.email, conversation_id)
    nodes, edges = extract_genie(
        state, turn=turn, genie_conversation_id=result.conversation_id,
        response_id=result.response_id, answer=result.answer, deep_link=result.deep_link,
        sql=result.sql, links=result.links,
    )
    if nodes or edges:
        yield {"kind": "graph", "delta": delta_payload(nodes, edges, turn)}

    yield {"kind": "compact", "text": compact_result_for_llm(result)}


async def run_turn(
    user: UserContext, settings: Settings, store: ConversationStore, graph: GraphStore,
    conversation_id: str, user_message: str, requested_model: str,
) -> AsyncIterator[str]:
    user_message = (user_message or "").strip()
    if not user_message:
        yield sse("error", message="Mensagem vazia.")
        return

    model, warning = _resolve_model(settings, requested_model)
    history = await anyio.to_thread.run_sync(store.get_messages, user.email, conversation_id)
    await anyio.to_thread.run_sync(store.add_message, user.email, conversation_id, "user", user_message)
    turn = len([m for m in history if m.role == "user"]) + 1

    yield sse("turn_start", conversation_id=conversation_id, model=model, turn=turn)
    if warning:
        yield sse("warning", message=warning)

    working: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    working += [{"role": m.role, "content": m.content} for m in history]
    working.append({"role": "user", "content": user_message})

    client = build_async_client(settings.host_url, user.token)
    full_answer_parts: list[str] = []

    try:
        for _iteration in range(settings.agent_max_tool_iterations):
            content = ""
            tool_calls: list[dict] = []
            async for ev in stream_turn(client, model, working, tools=[GENIE_TOOL]):
                if ev["type"] == "token":
                    full_answer_parts.append(ev["text"])
                    yield sse("token", text=ev["text"])
                elif ev["type"] == "complete":
                    content = ev["content"]
                    tool_calls = ev["tool_calls"]

            if not tool_calls:
                break  # resposta final já streamada

            # registra a decisão do modelo e executa cada tool
            working.append({"role": "assistant", "content": content or None, "tool_calls": tool_calls})
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                if name == "genie__ask":
                    question = args.get("question", user_message)
                    follow_up = bool(args.get("follow_up", False))
                    yield sse("tool_call_start", tool="genie__ask", label="Perguntando ao Genie One…",
                              args={"question": question})
                    compact = "O Genie One não retornou resultado."
                    async for out in _run_genie_tool(
                        user, settings, store, graph, conversation_id, turn, question, follow_up):
                        if out["kind"] == "progress":
                            yield sse("tool_progress", tool="genie__ask", step=out["step"])
                        elif out["kind"] == "card":
                            yield sse("tool_call_result", tool="genie__ask", card=out["card"])
                        elif out["kind"] == "graph":
                            yield sse("graph_delta", **out["delta"])
                        elif out["kind"] == "compact":
                            compact = out["text"]
                    working.append({"role": "tool", "tool_call_id": tc["id"], "content": compact})
                else:
                    working.append({"role": "tool", "tool_call_id": tc["id"],
                                    "content": f"Ferramenta desconhecida: {name}."})
    except Exception as e:  # noqa: BLE001
        logger.exception("erro no turno (modelo=%s)", model)
        yield sse("error", message=f"Não consegui concluir a resposta com o modelo {model}. "
                  "Tente novamente ou troque de modelo.", detail=str(e)[:200])
        return

    answer = "".join(full_answer_parts).strip()
    if answer:
        await anyio.to_thread.run_sync(store.add_message, user.email, conversation_id, "assistant", answer)
    yield sse("done", conversation_id=conversation_id, model=model)
