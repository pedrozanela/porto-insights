"""Loop de um turno — assíncrono, com tool calling (Genie One + Google Workspace).

Tools expostas ao modelo: a composta genie__ask + as tools read-only do Google (descobertas
via tools/list). Ao executar uma tool do Google, o resultado alimenta os extratores do grafo;
ao fim do turno rodam os linkers (determinístico + semântico) e o grafo cresce por deltas.

Toda chamada (modelo, Genie, Google) usa o token OBO do usuário.
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
from ..graph.linker import deterministic_links, extract_from_tool, semantic_links
from ..graph.schema import delta_payload
from ..graph.store import GraphStore
from ..llm import build_async_client, stream_turn
from ..mcp.client import mcp_session, structured, text_content
from ..mcp.registry import get_registry
from ..sse import sse
from ..store.base import ConversationStore
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger("porto_insights.agent")

AUTH_HINTS = ("login", "authoriz", "authentic", "oauth", "consent", "unauthenticated", "not connected")


def _resolve_model(settings: Settings, requested: str) -> tuple[str, str | None]:
    allowed = {e.name for e in settings.endpoints}
    if requested and requested in allowed:
        return requested, None
    default = settings.default_endpoint
    if requested:
        return default, f"Modelo '{requested}' não está disponível; usando {default}."
    return default, None


def _looks_like_auth_error(msg: str) -> bool:
    m = msg.lower()
    return any(h in m for h in AUTH_HINTS)


async def _run_genie_tool(user, settings, store, graph, conversation_id, turn, question, follow_up):
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
    if result.conversation_id:
        await anyio.to_thread.run_sync(
            store.set_genie_conversation_id, user.email, conversation_id, result.conversation_id)
    yield {"kind": "card", "card": card_payload(result)}
    state = graph.get(user.email, conversation_id)
    nodes, edges = extract_genie(
        state, turn=turn, genie_conversation_id=result.conversation_id, response_id=result.response_id,
        answer=result.answer, deep_link=result.deep_link, sql=result.sql, links=result.links)
    if nodes or edges:
        yield {"kind": "graph", "delta": delta_payload(nodes, edges, turn)}
    yield {"kind": "compact", "text": compact_result_for_llm(result)}


async def _run_google_tool(user, settings, graph, conversation_id, turn, service, tool_name, service_url, args):
    """Executa uma tool do Google. Emite ('auth'|'graph'|'compact')."""
    try:
        async with mcp_session(service_url, user.token, timeout=60) as s:
            res = await s.call_tool(tool_name, args)
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if _looks_like_auth_error(msg):
            yield {"kind": "auth", "service": service}
            yield {"kind": "compact", "text": f"O usuário ainda não conectou a conta Google ({service}). "
                   "Peça para conectar e siga com o que for possível."}
        else:
            yield {"kind": "compact", "text": f"Erro ao consultar {tool_name}: {msg[:150]}"}
        return

    if getattr(res, "is_error", False):
        body = text_content(res)
        if _looks_like_auth_error(body):
            yield {"kind": "auth", "service": service}
        yield {"kind": "compact", "text": f"{tool_name}: {body[:300]}"}
        return

    data = structured(res)
    if not data:
        data = {"_raw": text_content(res)[:2000]}

    state = graph.get(user.email, conversation_id)
    nodes, edges = extract_from_tool(state, service, tool_name, data, turn)
    if nodes or edges:
        yield {"kind": "graph", "delta": delta_payload(nodes, edges, turn)}

    # resultado enxuto para o LLM (só o necessário; evita corpos completos)
    compact = text_content(res) or json.dumps(data, ensure_ascii=False)
    yield {"kind": "compact", "text": compact[:4000]}


async def run_turn(user, settings, store, graph, conversation_id, user_message, requested_model) -> AsyncIterator[str]:
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

    # Descobre as tools do Google (cache curto por usuário) + a tool composta do Genie.
    try:
        registry = await get_registry(
            settings.host_url, user.token, settings.google_services,
            extra_allow={s.strip() for s in settings.mcp_tool_allowlist_extra.split(",") if s.strip()},
            extra_deny={s.strip() for s in settings.mcp_tool_denylist_extra.split(",") if s.strip()},
        )
    except Exception:  # noqa: BLE001
        logger.exception("falha ao montar registry de tools do Google")
        registry = None

    tools = [GENIE_TOOL] + (registry.openai_tools if registry else [])
    for svc, err in (registry.failed_services if registry else {}).items():
        if _looks_like_auth_error(err):
            yield sse("auth_required", service=svc.split(".")[-1], login_url=f"{settings.host_url}/explore/connections")

    working = [{"role": "system", "content": SYSTEM_PROMPT}]
    working += [{"role": m.role, "content": m.content} for m in history]
    working.append({"role": "user", "content": user_message})

    client = build_async_client(settings.host_url, user.token)
    full_answer_parts: list[str] = []
    used_tools = False

    try:
        for _iteration in range(settings.agent_max_tool_iterations):
            content = ""
            tool_calls = []
            async for ev in stream_turn(client, model, working, tools=tools):
                if ev["type"] == "token":
                    full_answer_parts.append(ev["text"])
                    yield sse("token", text=ev["text"])
                elif ev["type"] == "complete":
                    content, tool_calls = ev["content"], ev["tool_calls"]

            if not tool_calls:
                break

            used_tools = True
            working.append({"role": "assistant", "content": content or None, "tool_calls": tool_calls})
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                if name == "genie__ask":
                    question = args.get("question", user_message)
                    yield sse("tool_call_start", tool="genie__ask", label="Perguntando ao Genie One…",
                              args={"question": question})
                    compact = "Sem resultado."
                    async for out in _run_genie_tool(user, settings, store, graph, conversation_id,
                                                      turn, question, bool(args.get("follow_up"))):
                        if out["kind"] == "progress":
                            yield sse("tool_progress", tool="genie__ask", step=out["step"])
                        elif out["kind"] == "card":
                            yield sse("tool_call_result", tool="genie__ask", card=out["card"])
                        elif out["kind"] == "graph":
                            yield sse("graph_delta", **out["delta"])
                        elif out["kind"] == "compact":
                            compact = out["text"]
                    working.append({"role": "tool", "tool_call_id": tc["id"], "content": compact})

                elif registry and name in registry.service_url:
                    service = registry.service_of(name)
                    label = {"gmail": "Buscando emails…", "calendar": "Consultando sua agenda…",
                             "drive": "Procurando documentos…"}.get(service, "Consultando…")
                    yield sse("tool_call_start", tool=name, label=label, args=args)
                    compact = "Sem resultado."
                    async for out in _run_google_tool(user, settings, graph, conversation_id, turn,
                                                       service, name, registry.service_url[name], args):
                        if out["kind"] == "auth":
                            yield sse("auth_required", service=out["service"],
                                      login_url=f"{settings.host_url}/explore/connections")
                        elif out["kind"] == "graph":
                            yield sse("graph_delta", **out["delta"])
                        elif out["kind"] == "compact":
                            compact = out["text"]
                    yield sse("tool_call_result", tool=name)
                    working.append({"role": "tool", "tool_call_id": tc["id"], "content": compact})
                else:
                    working.append({"role": "tool", "tool_call_id": tc["id"],
                                    "content": f"Ferramenta desconhecida: {name}."})

        # Linkers ao fim do turno (se houve uso de tools): determinístico + semântico.
        if used_tools:
            state = graph.get(user.email, conversation_id)
            det = deterministic_links(state, turn, settings.time_window_days)
            sem = await semantic_links(client, model, state, turn, settings.semantic_linker_min_confidence)
            if det or sem:
                yield sse("graph_delta", **delta_payload([], det + sem, turn))
    except Exception as e:  # noqa: BLE001
        logger.exception("erro no turno (modelo=%s)", model)
        yield sse("error", message=f"Não consegui concluir a resposta com o modelo {model}. "
                  "Tente novamente ou troque de modelo.", detail=str(e)[:200])
        return

    answer = "".join(full_answer_parts).strip()
    if answer:
        await anyio.to_thread.run_sync(store.add_message, user.email, conversation_id, "assistant", answer)
    yield sse("done", conversation_id=conversation_id, model=model)
