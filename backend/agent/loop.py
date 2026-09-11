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
from ..graph.linker import (
    creates_nodes, deterministic_links, extract_from_tool, reconcile_provisionals, semantic_links,
)
from ..graph.schema import GraphNode, delta_payload
from ..graph.suggestions import build_suggestions
from ..graph.store import GraphStore
from ..llm import build_async_client, stream_turn
from ..mcp.client import mcp_session, structured, text_content
from ..mcp.registry import get_registry
from ..sse import sse
from ..store.base import ConversationStore
from ..tracing import trace_turn
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


def _mark_self(state, user_email: str) -> GraphNode | None:
    """Marca o nó person do usuário atual como 'Você' (Bloco 2). Retorna o nó p/ re-emitir."""
    email = (user_email or "").lower()
    for n in state.nodes.values():
        if n.type == "person" and str(n.props.get("email", "")).lower() == email and email:
            if not n.props.get("is_self"):
                n.props["is_self"] = True
                n.label = "Você"
                return n
            return None
    return None


async def _enrich_provisional_events(user, settings, graph, conversation_id, turn, registry):
    """Fallback determinístico: para cada evento provisório, busca o dia no Calendar e abre o
    evento correspondente (traz participantes). A reconciliação depois funde provisório→real."""
    state = graph.get(user.email, conversation_id)
    cal_list = next((n for n, s in registry.service_name.items() if s == "calendar" and n == "calendar_event_list"), None)
    cal_get = next((n for n, s in registry.service_name.items() if s == "calendar" and n == "calendar_event_get"), None)
    if not (cal_list and cal_get):
        return
    from ..graph.extractors.common import normalize_title
    url = registry.service_url.get(cal_list)
    get_url = registry.service_url.get(cal_get)
    provisionals = [n for n in state.nodes.values()
                    if n.type == "calendar_event" and n.props.get("provisional") and n.props.get("start")]
    # mapa dia -> títulos normalizados que queremos casar (só abrimos eventos que casam)
    want: dict[str, set[str]] = {}
    for p in provisionals[:3]:
        want.setdefault(str(p.props["start"])[:10], set()).add(normalize_title(p.props.get("summary") or p.label))
    for day, titles in list(want.items())[:2]:  # no máximo 2 dias
        try:
            async with mcp_session(url, user.token, timeout=45) as s:
                res = await s.call_tool("calendar_event_list",
                                        {"time_min": f"{day}T00:00:00-03:00", "time_max": f"{day}T23:59:59-03:00",
                                         "query": "", "max_results": 30})
            items = structured(res).get("items") or []
            # abre APENAS os eventos cujo título casa com um provisório (cirúrgico, sem ruído)
            matches = [it for it in items if it.get("id") and normalize_title(it.get("summary", "")) in titles]
            for it in matches[:3]:
                async with mcp_session(get_url, user.token, timeout=45) as s2:
                    ev = structured(await s2.call_tool("calendar_event_get", {"event_id": it["id"]}))
                nodes, edges = extract_from_tool(state, "calendar", "calendar_event_get", ev, turn)
                if nodes or edges:
                    yield {"kind": "graph", "delta": delta_payload(nodes, edges, turn)}
        except Exception as e:  # noqa: BLE001
            logger.info("enriquecimento de calendar falhou: %s", str(e)[:120])
            return


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

    # Só leituras focadas (get/read) criam nós — buscas/listagens são apenas candidatos.
    if creates_nodes(tool_name):
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
    asked_questions = {m.content for m in history if m.role == "user"} | {user_message}

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
    final_answer = ""  # só a resposta do turno (não a narração pré-tool) é persistida
    used_tools = False
    tool_call_count = 0

    try:
        for _iteration in range(settings.agent_max_tool_iterations):
            content = ""
            tool_calls = []
            async for ev in stream_turn(client, model, working, tools=tools):
                if ev["type"] == "token":
                    # Tokens são streamados ao vivo. Se este trecho preceder uma tool_call, é
                    # NARRAÇÃO: o frontend o move para o trace quando o tool_call_start chega.
                    yield sse("token", text=ev["text"])
                elif ev["type"] == "complete":
                    content, tool_calls = ev["content"], ev["tool_calls"]

            if not tool_calls:
                final_answer = content  # só a última iteração (sem tool) é a resposta
                break

            used_tools = True
            tool_call_count += len(tool_calls)
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

        # Fim do turno (se houve uso de tools): enriquecimento, linkers, reconciliação.
        if used_tools:
            state = graph.get(user.email, conversation_id)

            # Enriquecimento determinístico: se há evento provisório (deduzido de nota do Gemini)
            # e o Calendar está autorizado, busca o dia real p/ trazer o evento e participantes.
            calendar_ok = registry and any(v == "calendar" for v in registry.service_name.values())
            if calendar_ok and any(n.props.get("provisional") and n.type == "calendar_event"
                                   for n in state.nodes.values()):
                async for out in _enrich_provisional_events(user, settings, graph, conversation_id, turn, registry):
                    if out["kind"] == "graph":
                        yield sse("graph_delta", **out["delta"])

            det = deterministic_links(state, turn, settings.time_window_days)
            sem_nodes, sem_edges = await semantic_links(
                client, model, state, turn, settings.semantic_linker_min_confidence,
                answer_text=final_answer)
            rec_edges, removed = reconcile_provisionals(state, turn)
            self_node = _mark_self(state, user.email)  # Bloco 2: marca o nó "Você"
            if self_node:
                sem_nodes.append(self_node)
            if det or sem_nodes or sem_edges or rec_edges or removed:
                yield sse("graph_delta", **delta_payload(sem_nodes, det + sem_edges + rec_edges, turn, removed))

            # Bloco 5: sugestões a partir das lacunas do grafo.
            sugg = build_suggestions(state, asked=asked_questions)
            if sugg:
                yield sse("suggestions", suggestions=sugg)
    except Exception as e:  # noqa: BLE001
        logger.exception("erro no turno (modelo=%s)", model)
        yield sse("error", message=f"Não consegui concluir a resposta com o modelo {model}. "
                  "Tente novamente ou troque de modelo.", detail=str(e)[:200])
        return

    answer = final_answer.strip()
    if answer:
        await anyio.to_thread.run_sync(store.add_message, user.email, conversation_id, "assistant", answer)

    graph_nodes = len([n for n in graph.get(user.email, conversation_id).nodes.values()
                       if not n.props.get("is_self")])
    trace_turn(model=model, question=user_message, tool_calls=tool_call_count, graph_nodes=graph_nodes)
    yield sse("done", conversation_id=conversation_id, model=model)
