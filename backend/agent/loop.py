"""Loop de um turno — assíncrono, com tool calling (Genie One + Google Workspace).

Tools expostas ao modelo: a composta genie__ask + as tools read-only do Google (descobertas
via tools/list). Ao executar uma tool do Google, o resultado alimenta os extratores do grafo;
ao fim do turno rodam os linkers (determinístico + semântico) e o grafo cresce por deltas.

Toda chamada (modelo, Genie, Google) usa o token OBO do usuário.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import anyio

from ..auth import UserContext
from ..config import Settings
from ..genie.client import run_genie_ask
from ..genie.composite import GENIE_TOOL, card_payload, compact_result_for_llm
from ..graph.extractors.genie import extract_genie
from ..graph.linker import (
    NODE_CREATING_TOOLS, deterministic_links, extract_from_tool, reconcile_provisionals,
    reconcile_recurring, semantic_links,
)
from ..graph.promotion import bare_visible_events, enforce_no_orphans, promote, visible_delta
from ..graph.schema import GraphNode, delta_payload, is_visible
from ..graph.suggestions import build_suggestions
from ..graph.store import GraphStore
from ..llm import build_async_client, stream_turn
from ..mcp.client import mcp_session, structured, text_content
from ..mcp.registry import get_registry
from ..sse import sse
from ..store.base import ConversationStore
from .. import tracing
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger("porto_insights.agent")

AUTH_HINTS = ("login", "authoriz", "authentic", "oauth", "consent", "unauthenticated", "not connected")

# Backstop de latência: o modelo às vezes "pagina" uma listagem (ex.: chama calendar_event_list
# 10x avançando o time_min) mesmo instruído a não fazer. Capamos chamadas repetidas da MESMA
# tool de listagem/busca por turno; além do teto, devolvemos um aviso em vez de executar.
LISTING_TOOLS = frozenset({
    "calendar_event_list", "google_drive_search", "google_drive_list_recent",
    "gmail_search", "gmail_search_threads",
})
LISTING_CAP_PER_TURN = 3

# Brasil não tem horário de verão desde 2019 → offset fixo UTC-3 (sem dependência de tzdata).
_BR_TZ = timezone(timedelta(hours=-3))
_WEEKDAYS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
             "sábado", "domingo")
_MONTHS = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
           "setembro", "outubro", "novembro", "dezembro")


def _today_preamble() -> str:
    """Âncora temporal injetada no system prompt a cada turno. Sem isto, o modelo não sabe
    que dia é hoje e calcula 'esta semana'/'amanhã' errado (ex.: cai em outro mês/ano)."""
    now = datetime.now(timezone.utc).astimezone(_BR_TZ)
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    d = lambda x: f"{x.day:02d}/{x.month:02d}/{x.year}"  # noqa: E731
    return (
        "Contexto temporal (use como referência para QUALQUER filtro de data — agenda, emails e "
        f"documentos): hoje é {_WEEKDAYS[now.weekday()]}, {now.day} de {_MONTHS[now.month - 1]} de "
        f"{now.year}, {now:%H:%M} (horário de Brasília). A semana atual (segunda a domingo) vai de "
        f"{d(monday)} a {d(sunday)}. \"Esta semana\" = esse intervalo; \"hoje\" = {d(now)}. "
        "Calcule TODAS as datas a partir de HOJE; NUNCA use outro ano ou mês por conta própria e "
        "nunca deduza a data a partir de eventos antigos que aparecerem nas buscas."
    )


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


def _primary_ids(tool_name: str, data: dict) -> list[str]:
    """IDs do(s) nó(s) primário(s) buscado(s) por uma tool `get` (para marcar via_get pelo id)."""
    from ..graph.extractors.common import drive_id, email_id, event_id, thread_id
    ids: list[str] = []
    if tool_name == "calendar_event_get" and data.get("id"):
        ids.append(event_id(data["id"]))
    elif tool_name == "gmail_read_message" and data.get("id"):
        ids.append(email_id(data["id"]))
    elif tool_name == "gmail_get_thread":
        tid = data.get("id") or data.get("threadId")
        if tid:
            ids.append(thread_id(tid))
        for m in data.get("messages", []) or []:
            if m.get("id"):
                ids.append(email_id(m["id"]))
    elif tool_name in ("google_file_read", "google_file_metadata", "google_file_download"):
        md = data.get("metadata") if isinstance(data.get("metadata"), dict) else data
        fid = md.get("id") or md.get("file_id") or md.get("document_id")
        if fid:
            ids.append(drive_id(fid))
    return ids


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


async def _enrich_data_assets(user, state) -> None:
    """B4: para cada data_asset novo, busca no Unity Catalog (OBO) o comentário → rótulo de
    exibição e o tipo (metric view vs tabela). Nome técnico fica em props.title (tooltip/painel)."""
    for n in [x for x in state.nodes.values() if x.type == "data_asset" and not x.props.get("uc_resolved")]:
        fq = n.props.get("qualified_name")
        if not fq or fq.count(".") != 2:
            n.props["uc_resolved"] = True
            continue
        try:
            info = await anyio.to_thread.run_sync(lambda: user.wsc.tables.get(fq))
            comment = (getattr(info, "comment", None) or "").strip()
            ttype = str(getattr(info, "table_type", "") or "")
            if comment:  # rótulo = 1ª oração do comentário do UC
                n.label = comment.split(".")[0].split(",")[0][:40]
            if "METRIC" in ttype.upper():
                n.props["asset_type"] = "metric_view"
        except Exception as e:  # noqa: BLE001
            # Fallback benigno: sem o scope catalog.tables:read no token OBO (ex.: consentimento
            # do usuário anterior ao scope), mantém o nome técnico. Glyph/tipo já vêm da heurística.
            logger.info("enrich_data_assets: tables.get(%s) indisponível (%s) — mantendo nome técnico",
                        fq, type(e).__name__)
        n.props["uc_resolved"] = True


def _drive_arg_name(registry, tool: str) -> str:
    """Nome do parâmetro de id do arquivo no schema da tool (fileId/document_id/id/…)."""
    schema = next((t["function"]["parameters"] for t in (registry.openai_tools if registry else [])
                   if t["function"]["name"] == tool), {}) or {}
    props = schema.get("properties", {}) or {}
    for k in props:
        kl = k.lower()
        if "fileid" in kl.replace("_", "") or "documentid" in kl.replace("_", "") or kl in ("id", "file_id"):
            return k
    return "file_id"


async def _enrich_drive_stubs(user, state, turn, registry) -> None:
    """Item 4: anexos do Calendar que chegaram só com fileUrl/fileId (stub) ganham título e
    mimeType via Drive (files.get / metadata, OBO). Cache por id, no máx. 5 por turno.
    Fallback de rótulo: 'Documento sem título' — nunca '(documento)'."""
    if not registry:
        return
    tool = next((n for n, s in registry.service_name.items()
                 if s == "drive" and n in ("google_file_metadata", "google_file_read", "google_file_download")), None)
    if not tool:
        return
    url = registry.service_url.get(tool)
    arg = _drive_arg_name(registry, tool)
    stubs = [n for n in state.nodes.values()
             if n.type == "drive_file" and n.props.get("stub") and not n.props.get("stub_resolved")]
    for n in stubs[:5]:
        fid = n.props.get("file_id")
        if fid:
            try:
                async with mcp_session(url, user.token, timeout=45) as s:
                    data = structured(await s.call_tool(tool, {arg: fid}))
                new_nodes, _ = extract_from_tool(state, "drive", tool, data, turn)
                for nn in new_nodes:  # metadados adicionais (ex.: dono) entram em staging
                    nn.props["staged"] = True
            except Exception as e:  # noqa: BLE001
                logger.info("enrich_drive_stubs: %s falhou (%s)", fid, type(e).__name__)
        if not n.label or n.label == "(documento)":
            n.label = "Documento sem título"
        n.props["stub_resolved"] = True


async def _enrich_bare_events(user, state, turn, registry) -> int:
    """Item 1: evento promovido por casamento de título que não tem participantes carregados
    recebe um `calendar_event_get` feito pelo BACKEND (não depende do prompt). Limite 5/turno,
    cache por event id (props.bare_enriched). Retorna quantos eventos foram enriquecidos."""
    if not registry:
        return 0
    get_tool = next((n for n, s in registry.service_name.items()
                     if s == "calendar" and n == "calendar_event_get"), None)
    if not get_tool:
        return 0
    url = registry.service_url.get(get_tool)
    done = 0
    for ev in bare_visible_events(state)[:5]:
        ev.props["bare_enriched"] = True  # marca antes p/ não repetir mesmo em erro
        raw = ev.id.split("calendar:", 1)[-1]
        try:
            async with mcp_session(url, user.token, timeout=45) as s:
                data = structured(await s.call_tool("calendar_event_get", {"event_id": raw}))
            nodes, _ = extract_from_tool(state, "calendar", "calendar_event_get", data, turn)
            for n in nodes:
                if n.id != ev.id:  # participantes/anexos entram em staging; o evento continua visível
                    n.props["staged"] = True
            done += 1
        except Exception as e:  # noqa: BLE001
            logger.info("enrich_bare_events: get(%s) falhou (%s)", raw, type(e).__name__)
    return done


async def _enrich_provisional_events(user, settings, graph, conversation_id, turn, registry) -> None:
    """Fallback determinístico: para cada evento provisório, busca o dia no Calendar e abre o
    evento correspondente (traz participantes, em staging). A reconciliação funde provisório→real."""
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
                nodes, _ = extract_from_tool(state, "calendar", "calendar_event_get", ev, turn)
                for n in nodes:
                    n.props["staged"] = True
                for pid in _primary_ids("calendar_event_get", ev):  # evento real → via_get pelo id
                    if pid in state.nodes:
                        state.nodes[pid].props["via_get"] = True
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


def _mcp_service_full(service_url: str) -> str:
    """Extrai o nome completo do MCP Service da URL do gateway
    (…/ai-gateway/mcp-services/system.ai.google_calendar → system.ai.google_calendar)."""
    return service_url.rstrip("/").split("/")[-1]


def _mcp_consent_url(host_url: str, service_full: str) -> str:
    """Página de consentimento/login do MCP Service no Catalog Explorer.
    NÃO é /explore/connections (isso é UC HTTP connection, outra coisa)."""
    return f"{host_url}/explore/data/mcp-services/{service_full.replace('.', '/')}"


async def _run_google_tool(user, settings, graph, conversation_id, turn, service, tool_name, service_url, args):
    """Executa uma tool do Google. Emite ('auth'|'graph'|'compact')."""
    service_full = _mcp_service_full(service_url)
    try:
        async with mcp_session(service_url, user.token, timeout=60) as s:
            res = await s.call_tool(tool_name, args)
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if _looks_like_auth_error(msg):
            yield {"kind": "auth", "service": service, "service_full": service_full}
            yield {"kind": "compact", "text": f"O usuário ainda não conectou a conta Google ({service}). "
                   "Peça para conectar e siga com o que for possível."}
        else:
            yield {"kind": "compact", "text": f"Erro ao consultar {tool_name}: {msg[:150]}"}
        return

    if getattr(res, "is_error", False):
        body = text_content(res)
        if _looks_like_auth_error(body):
            yield {"kind": "auth", "service": service, "service_full": service_full}
        yield {"kind": "compact", "text": f"{tool_name}: {body[:300]}"}
        return

    data = structured(res)
    if not data:
        data = {"_raw": text_content(res)[:2000]}

    # Extrai para STAGING (props.staged=True): nada vai ao frontend agora. A promoção por
    # evidência, no fim do turno, decide o que fica visível. Leituras focadas (get) marcam
    # via_get=True (critério de promoção c).
    state = graph.get(user.email, conversation_id)
    nodes, _ = extract_from_tool(state, service, tool_name, data, turn)
    for n in nodes:
        n.props["staged"] = True
    # via_get no(s) nó(s) PRIMÁRIO(s) buscado(s) — pelo id, existam eles ou não (o item pode já
    # ter sido criado, em staging, por uma listagem anterior). Participantes de evento NÃO
    # ganham via_get: passam pelo colapso.
    for pid in _primary_ids(tool_name, data):
        if pid in state.nodes:
            state.nodes[pid].props["via_get"] = True

    # resultado enxuto para o LLM (só o necessário; evita corpos completos)
    compact = text_content(res) or json.dumps(data, ensure_ascii=False)
    yield {"kind": "compact", "text": compact[:4000]}


async def run_turn(user, settings, store, graph, conversation_id, user_message, requested_model) -> AsyncIterator[str]:
    """Wrapper fino: abre o span raiz do turno (MLflow, best-effort) e delega. O span fica ativo
    durante toda a geração, então os spans de LLM (autolog) e de tools aninham por contexto."""
    model, _ = _resolve_model(settings, requested_model)
    with tracing.turn_span(question=(user_message or "").strip(), model=model,
                           conversation_id=conversation_id, user_email=user.email):
        async for ev in _run_turn_impl(user, settings, store, graph, conversation_id,
                                       user_message, requested_model):
            yield ev


async def _run_turn_impl(user, settings, store, graph, conversation_id, user_message, requested_model) -> AsyncIterator[str]:
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
            settings.host_url, user.token, settings.mcp_services,
            extra_allow={s.strip() for s in settings.mcp_tool_allowlist_extra.split(",") if s.strip()},
            extra_deny={s.strip() for s in settings.mcp_tool_denylist_extra.split(",") if s.strip()},
        )
    except Exception:  # noqa: BLE001
        logger.exception("falha ao montar registry de tools do Google")
        registry = None

    tools = [GENIE_TOOL] + (registry.openai_tools if registry else [])
    for svc, err in (registry.failed_services if registry else {}).items():
        if _looks_like_auth_error(err):
            yield sse("auth_required", service=svc.split(".")[-1],
                      login_url=_mcp_consent_url(settings.host_url, svc))

    working = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + _today_preamble()}]
    working += [{"role": m.role, "content": m.content} for m in history]
    working.append({"role": "user", "content": user_message})

    client = build_async_client(settings.host_url, user.token)
    final_answer = ""  # só a resposta do turno (não a narração pré-tool) é persistida
    used_tools = False
    tool_call_count = 0
    turn_t0 = time.monotonic()  # latência (item 3): total, Genie, linker
    genie_ms = 0.0
    linker_ms = 0.0
    listing_calls: dict[str, int] = {}  # backstop anti-paginação (por tool, por turno)

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
            # Rede de segurança: se o teto de iterações for atingido com tools ainda pendentes,
            # não perca o texto — sem final_answer o casamento por título não promove nada.
            if content:
                final_answer = content

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
                    _g0 = time.monotonic()
                    with tracing.tool_span("genie__ask", inputs={"question": question}):
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
                    genie_ms += (time.monotonic() - _g0) * 1000
                    working.append({"role": "tool", "tool_call_id": tc["id"], "content": compact})

                elif registry and name in registry.service_url:
                    service = registry.service_of(name)
                    # Backstop anti-paginação: além do teto, não executa — devolve aviso ao modelo.
                    if name in LISTING_TOOLS:
                        listing_calls[name] = listing_calls.get(name, 0) + 1
                        if listing_calls[name] > LISTING_CAP_PER_TURN:
                            working.append({"role": "tool", "tool_call_id": tc["id"], "content": (
                                f"Você já chamou `{name}` {LISTING_CAP_PER_TURN} vezes neste turno. "
                                "NÃO liste de novo: uma listagem do período já traz todos os itens. "
                                "Use os resultados anteriores para responder agora.")})
                            continue
                    label = {"gmail": "Buscando emails…", "calendar": "Consultando sua agenda…",
                             "drive": "Procurando documentos…",
                             "web": "Pesquisando na web…"}.get(service, "Consultando…")
                    yield sse("tool_call_start", tool=name, label=label, args=args)
                    compact = "Sem resultado."
                    with tracing.tool_span(name, inputs=args):
                        async for out in _run_google_tool(user, settings, graph, conversation_id, turn,
                                                           service, name, registry.service_url[name], args):
                            if out["kind"] == "auth":
                                yield sse("auth_required", service=out["service"],
                                          login_url=_mcp_consent_url(
                                              settings.host_url,
                                              out.get("service_full") or f"system.ai.{out['service']}"))
                            elif out["kind"] == "graph":
                                yield sse("graph_delta", **out["delta"])
                            elif out["kind"] == "compact":
                                compact = out["text"]
                    yield sse("tool_call_result", tool=name)
                    working.append({"role": "tool", "tool_call_id": tc["id"], "content": compact})
                else:
                    working.append({"role": "tool", "tool_call_id": tc["id"],
                                    "content": f"Ferramenta desconhecida: {name}."})

        # Fim do turno: promoção por evidência (o grafo mostra evidência, não exploração).
        # Roda também em turnos SEM tool quando já há grafo — assim uma pergunta de raciocínio
        # (ex.: "isso tem relação com alguma reunião?") pode criar arestas related_to entre nós
        # já existentes (cruza agenda ↔ dados).
        state = graph.get(user.email, conversation_id)
        if used_tools or len([n for n in state.nodes.values() if is_visible(n)]) >= 2:
            before_visible = {n.id for n in state.nodes.values() if is_visible(n)}

            # Enriquecimento (staging): traz o evento real do dia p/ um provisório, se Calendar ok.
            calendar_ok = registry and any(v == "calendar" for v in registry.service_name.values())
            if calendar_ok and any(n.props.get("provisional") and n.type == "calendar_event"
                                   for n in state.nodes.values()):
                await _enrich_provisional_events(user, settings, graph, conversation_id, turn, registry)

            # Item 4: resolve título/mimeType de anexos que vieram só como stub (fileUrl/fileId).
            await _enrich_drive_stubs(user, state, turn, registry)

            # Reconciliação ANTES da promoção: funde provisório→real (reaponta notes_of) e
            # instâncias recorrentes num único nó canônico (evento semanal = 1 nó, não N).
            _, removed = reconcile_provisionals(state, turn)
            _, removed_rec = reconcile_recurring(state, final_answer)
            removed += removed_rec
            # Linker semântico (vê todos os nós, inclusive staging) → related_to, mentions e
            # relevant_node_ids. Determinístico ANTES da promoção: cria links_to/same_time_window
            # para o fechamento estrutural e o invariante sem-órfãos verem todas as arestas.
            _l0 = time.monotonic()
            sem_nodes, sem_edges, relevant_ids = await semantic_links(
                client, model, state, turn, settings.semantic_linker_min_confidence,
                answer_text=final_answer)
            linker_ms += (time.monotonic() - _l0) * 1000
            deterministic_links(state, turn, settings.time_window_days)
            # Promoção por evidência (semente + fechamento estrutural + colapso + anexos).
            promoted_ids = promote(state, answer_text=final_answer, relevant_ids=relevant_ids,
                                   asked_text=user_message)
            # Item 1: eventos promovidos por título sem participantes → get determinístico do
            # backend e reaplica a promoção (colapso traz os participantes) ANTES do sem-órfãos.
            if calendar_ok and await _enrich_bare_events(user, state, turn, registry):
                deterministic_links(state, turn, settings.time_window_days)
                promoted_ids |= promote(state, answer_text=final_answer, relevant_ids=relevant_ids,
                                        asked_text=user_message)

            # A2: se o modelo abriu vários eventos candidatos e só 1 é a evidência, registra no trace.
            opened_ev = [n for n in state.nodes.values()
                         if n.type == "calendar_event" and n.props.get("via_get")]
            promoted_ev = [state.nodes[i] for i in promoted_ids
                           if i in state.nodes and state.nodes[i].type == "calendar_event"]
            if len(opened_ev) >= 2 and len(promoted_ev) == 1:
                day = str(promoted_ev[0].props.get("start", ""))[:10]
                day_br = f"{day[8:10]}/{day[5:7]}" if len(day) == 10 else ""
                yield sse("tool_progress", tool="agenda",
                          step=f"Verifiquei {len(opened_ev)} reuniões"
                          + (f" do dia {day_br}" if day_br else "")
                          + f"; a correspondente é “{promoted_ev[0].label}”.")

            # B4: rótulo do data_asset a partir do comentário do Unity Catalog (OBO), best-effort.
            await _enrich_data_assets(user, state)

            _mark_self(state, user.email)  # Bloco 2
            # Invariante sem-órfãos sobre o grafo FINAL do turno (todas as arestas já existem).
            enforce_no_orphans(state, asked_text=user_message)

            vis_nodes, vis_edges = visible_delta(state)
            newly = [nid for nid in {n.id for n in vis_nodes} - before_visible]
            yield sse("graph_delta", **delta_payload(vis_nodes, vis_edges, turn,
                                                      removed_node_ids=removed, promoted_node_ids=newly))

            sugg = build_suggestions(state, asked=asked_questions)  # Bloco 5: só nós visíveis
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
                       if is_visible(n) and not n.props.get("is_self")])
    # Latência (item 3): total, nº de tool calls, tempo do Genie e do linker deste turno.
    total_ms = round((time.monotonic() - turn_t0) * 1000)
    timing = {"total_ms": total_ms, "tool_calls": tool_call_count,
              "genie_ms": round(genie_ms), "linker_ms": round(linker_ms)}
    tracing.set_turn_metrics(graph_nodes=graph_nodes, timing=timing)  # anota no span raiz (MLflow)
    logger.info("turn timing model=%s %s", model, timing)
    yield sse("done", conversation_id=conversation_id, model=model, timing=timing)
