"""Linkers do grafo (abordagem híbrida).

Determinístico (confiável, barato, explicável): links de Drive citados em corpos de email /
descrições de evento (links_to); proximidade temporal entre evento e email com pessoas em
comum (same_time_window).

Semântico (inferido pelo LLM): arestas related_to entre nós existentes, com confidence e
rationale em pt-BR; só aceitas com confidence >= limite. O LLM não cria nós.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime

from pydantic import BaseModel, ValidationError

from .extractors.calendar import extract_calendar
from .extractors.common import drive_id, extract_drive_ids, normalize_title, provisional_person_id
from .extractors.drive import extract_drive
from .extractors.gmail import extract_gmail
from .schema import GraphEdge, GraphNode, GraphState, is_visible

logger = logging.getLogger("porto_insights.graph.linker")


# Só estas tools criam nós no grafo: leituras "focadas" de um item específico. Buscas/listagens
# (gmail_search, google_drive_search, calendar_event_list, ...) NÃO criam nós — servem só de
# candidatos para o modelo. Assim o grafo reflete o que a conversa de fato abriu, sem poluir com
# dezenas de hits de busca irrelevantes. (Nós de dados vêm à parte, das citações do Genie.)
NODE_CREATING_TOOLS = {
    "gmail_read_message", "gmail_get_thread",
    "calendar_event_get",
    "google_file_read", "google_file_metadata", "google_file_download",
}


def creates_nodes(tool_name: str) -> bool:
    return tool_name in NODE_CREATING_TOOLS


def extract_from_tool(state: GraphState, service: str, tool_name: str, result: dict, turn: int):
    """Roteia o resultado de uma tool do Google para o extractor certo."""
    if service == "gmail":
        return extract_gmail(state, tool_name, result, turn)
    if service == "calendar":
        return extract_calendar(state, tool_name, result, turn)
    if service == "drive":
        return extract_drive(state, tool_name, result, turn)
    return [], []


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if "," in value:  # RFC 2822 (data de email)
            return parsedate_to_datetime(value)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def deterministic_links(state: GraphState, turn: int, time_window_days: int) -> list[GraphEdge]:
    """Arestas cross-source. Roda sobre o estado acumulado; devolve só as novas."""
    added: list[GraphEdge] = []

    # Adjacência pessoa → nós (por tipo), a partir das arestas existentes.
    persons_of: dict[str, set[str]] = {}  # node_id -> set(person_id)
    for e in state.edges.values():
        if e.type in ("sender", "recipient", "attendee", "organizer"):
            persons_of.setdefault(e.source, set()).add(e.target)

    emails = [n for n in state.nodes.values() if n.type == "email"]
    events = [n for n in state.nodes.values() if n.type == "calendar_event"]
    files_by_id = {n.props.get("file_id"): n for n in state.nodes.values() if n.type == "drive_file"}

    # links_to: Drive citado no corpo de email / descrição de evento
    for n in emails + events:
        text = str(n.props.get("_text", ""))
        for fid in extract_drive_ids(text):
            target = files_by_id.get(fid) or state.nodes.get(drive_id(fid))
            if target:
                e = state.add_edge(GraphEdge(
                    id=GraphState.edge_id(n.id, "links_to", target.id),
                    source=n.id, target=target.id, type="links_to", first_seen_turn=turn,
                    evidence=["link de Drive no corpo"],
                ))
                if e:
                    added.append(e)

    # same_time_window: evento × email com pessoa em comum e proximidade temporal
    for ev in events:
        ev_people = persons_of.get(ev.id, set())
        ev_dt = _parse_dt(ev.props.get("start"))
        if not ev_people or not ev_dt:
            continue
        for em in emails:
            if not (persons_of.get(em.id, set()) & ev_people):
                continue
            em_dt = _parse_dt(em.props.get("date"))
            if em_dt and abs((em_dt - ev_dt).days) <= time_window_days:
                e = state.add_edge(GraphEdge(
                    id=GraphState.edge_id(ev.id, "same_time_window", em.id),
                    source=ev.id, target=em.id, type="same_time_window", first_seen_turn=turn,
                    weight=0.8, evidence=["pessoas em comum + proximidade temporal"],
                ))
                if e:
                    added.append(e)
    return added


def pair_linked(state: GraphState, a: str, b: str) -> bool:
    """True se já existe qualquer aresta entre a e b (precedência determinística sobre related_to)."""
    return any((e.source == a and e.target == b) or (e.source == b and e.target == a)
               for e in state.edges.values())


def reconcile_provisionals(state: GraphState, turn: int) -> tuple[list[GraphEdge], list[str]]:
    """Funde nós provisórios nos reais equivalentes. Retorna (arestas novas, ids removidos).
    - evento provisório → evento real: mesmo título normalizado e start em ±15 min.
    - pessoa provisória → pessoa real: mesmo nome normalizado."""
    added: list[GraphEdge] = []
    removed: list[str] = []

    events = [n for n in state.nodes.values() if n.type == "calendar_event"]
    provis_ev = [n for n in events if n.props.get("provisional")]
    real_ev = [n for n in events if not n.props.get("provisional")]
    for p in provis_ev:
        p_norm = normalize_title(p.props.get("summary") or p.label)
        p_dt = _parse_dt(p.props.get("start"))
        for r in real_ev:
            if normalize_title(r.props.get("summary") or r.label) != p_norm:
                continue
            r_dt = _parse_dt(r.props.get("start"))
            close = True
            if p_dt and r_dt:
                close = abs((p_dt - r_dt).total_seconds()) <= 15 * 60
            if close:
                edges, rem = state.merge_node(p.id, r.id)
                added += edges
                if rem:
                    removed.append(rem)
                break

    persons = [n for n in state.nodes.values() if n.type == "person"]
    provis_p = [n for n in persons if n.props.get("provisional")]
    real_p = [n for n in persons if not n.props.get("provisional")]
    for p in provis_p:
        p_norm = normalize_title(p.label)
        for r in real_p:
            if normalize_title(r.label) == p_norm:
                edges, rem = state.merge_node(p.id, r.id)
                added += edges
                if rem:
                    removed.append(rem)
                break
    return added, removed


SEMANTIC_PROMPT = """\
Você conecta um grafo de conhecimento. Recebe CANDIDATOS (id, tipo, rótulo curto, data) e o TEXTO
da resposta dada ao usuário neste turno. Faça três coisas:

1) edges (related_to): pares de nós existentes que tratam do MESMO assunto e ainda não estariam
   obviamente ligados (ex.: uma reunião e uma resposta de dados sobre o tema dela).
   Cada um: {"source": id, "target": id, "confidence": 0..1, "rationale": "motivo curto pt-BR"}.

2) mentions: NOMES DE PESSOAS citados no texto que NÃO estão entre os candidatos (ex.: alguém
   citado no resumo de um documento). Cada um: {"name": "Nome Sobrenome", "in_node": id_do_conteudo,
   "confidence": 0..1}. APENAS pessoas reais (não empresas, produtos, times ou lugares).

3) relevant_node_ids: ids dos candidatos DIRETAMENTE relevantes para a resposta deste turno.
   Ignore o que apareceu só como ruído de busca.

Use SOMENTE ids fornecidos; não invente ids. Prefira poucas propostas de alta confiança.
Responda APENAS um objeto JSON: {"edges": [...], "mentions": [...], "relevant_node_ids": [...]}.

CANDIDATOS (JSON):
"""


class _LinkerEdge(BaseModel):
    source: str
    target: str
    confidence: float = 0.0
    rationale: str = ""


class _LinkerMention(BaseModel):
    name: str
    in_node: str
    confidence: float = 0.0


class _LinkerOut(BaseModel):
    edges: list[_LinkerEdge] = []
    mentions: list[_LinkerMention] = []
    relevant_node_ids: list[str] = []


def _find_person_by_name(state: GraphState, name: str) -> GraphNode | None:
    norm = normalize_title(name)
    for n in state.nodes.values():
        if n.type == "person" and normalize_title(n.label) == norm:
            return n
    return None


def _node_date(n: GraphNode) -> str:
    if n.type == "calendar_event":
        return str(n.props.get("start") or "")[:10]
    if n.type == "email":
        return str(n.props.get("date") or "")[:16]
    return ""


def build_candidates(state: GraphState, turn: int, cap: int = 80) -> tuple[list[dict], int]:
    """Lista COMPACTA de candidatos p/ o linker (nunca os nós completos). Prioridade: nós do
    turno atual, depois os de maior grau (o "episódio" é a conversa toda). Devolve (lista, total)."""
    nodes = list(state.nodes.values())
    deg: dict[str, int] = {}
    for e in state.edges.values():
        deg[e.source] = deg.get(e.source, 0) + 1
        deg[e.target] = deg.get(e.target, 0) + 1
    nodes.sort(key=lambda n: (1 if n.first_seen_turn == turn else 0, deg.get(n.id, 0)), reverse=True)
    cands = [{"id": n.id, "tipo": n.type, "rotulo": n.label[:50], "data": _node_date(n)}
             for n in nodes[:cap]]
    return cands, len(nodes)


async def _call_linker(client, model: str, prompt: str) -> tuple[dict | None, str, str | None]:
    """Chama o modelo pedindo JSON. Tenta modo JSON estruturado; se o endpoint recusar, refaz sem.
    Retorna (data|None, mode, error)."""
    for mode, kwargs in (("json_object", {"response_format": {"type": "json_object"}}), ("plain", {})):
        try:
            resp = await client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], max_tokens=1500, **kwargs)
            content = resp.choices[0].message.content or ""
            frag = content[content.find("{"): content.rfind("}") + 1]
            return json.loads(frag), mode, None
        except TypeError:
            continue  # endpoint não aceita response_format → tenta plain
        except Exception as e:  # noqa: BLE001 — JSON inválido/truncado ou erro de rede
            if mode == "plain":
                return None, mode, f"{type(e).__name__}: {str(e)[:120]}"
            continue
    return None, "plain", "sem saída"


async def semantic_links(
    client, model: str, state: GraphState, turn: int, min_confidence: float,
    *, answer_text: str = "", mention_min_conf: float = 0.7,
) -> tuple[list[GraphNode], list[GraphEdge], set[str]]:
    """LLM propõe related_to (entre nós), mentions (pessoas citadas) e relevant_node_ids.
    Falha de JSON NÃO zera silenciosamente: registra state.linker_health e o turno segue só com
    as regras determinísticas (título, id canônico, fechamento). Retorna (nós, arestas, relevant)."""
    nodes = list(state.nodes.values())
    if len(nodes) < 2 and not answer_text:
        return [], [], set()
    cands, total = build_candidates(state, turn)
    prompt = SEMANTIC_PROMPT + json.dumps(cands, ensure_ascii=False) + f"\n\nTEXTO DA RESPOSTA:\n{answer_text[:2000]}"
    raw, mode, error = await _call_linker(client, model, prompt)

    health = {"input_size": total, "listed": len(cands), "mode": mode,
              "parsed": raw is not None, "error": error, "relevant": 0, "failed": raw is None}
    if raw is None:
        logger.warning("linker_failed (%s): input=%d listed=%d — turno só determinístico",
                       error, total, len(cands))
        state.linker_health = health  # type: ignore[attr-defined]
        return [], [], set()
    try:
        data = _LinkerOut.model_validate(raw)
    except ValidationError as ve:
        health.update(parsed=False, failed=True, error=f"schema: {str(ve)[:120]}")
        logger.warning("linker_failed (schema): %s", str(ve)[:120])
        state.linker_health = health  # type: ignore[attr-defined]
        return [], [], set()

    added_nodes: list[GraphNode] = []
    added_edges: list[GraphEdge] = []
    relevant_ids: set[str] = {i for i in data.relevant_node_ids if i in state.nodes}
    health["relevant"] = len(relevant_ids)
    state.linker_health = health  # type: ignore[attr-defined]

    for p in data.edges:
        src, tgt = p.source, p.target
        conf = float(p.confidence or 0)
        if src not in state.nodes or tgt not in state.nodes or src == tgt or conf < min_confidence:
            continue
        if pair_linked(state, src, tgt):  # B2: já conectados deterministicamente → não propor related_to
            continue
        e = state.add_edge(GraphEdge(
            id=GraphState.edge_id(src, "related_to", tgt), source=src, target=tgt, type="related_to",
            first_seen_turn=turn, weight=conf, confidence=conf, rationale=(p.rationale or "")[:200]))
        if e:
            added_edges.append(e)

    for m in data.mentions:
        name = (m.name or "").strip()
        in_node = m.in_node
        conf = float(m.confidence or 0)
        if not name or conf < mention_min_conf or in_node not in state.nodes:
            continue
        existing = _find_person_by_name(state, name)  # se já há pessoa (real/provisória), reusa
        pid = existing.id if existing else provisional_person_id(name)
        if not existing:
            n = state.add_node(GraphNode(id=pid, type="person", label=name, source="genie",
                                         first_seen_turn=turn, props={"provisional": True, "mentioned": True}))
            if n:
                added_nodes.append(n)
        e = state.add_edge(GraphEdge(
            id=GraphState.edge_id(in_node, "mentions", pid), source=in_node, target=pid, type="mentions",
            first_seen_turn=turn, weight=0.3, confidence=conf, evidence=["citado no conteúdo"]))
        if e:
            added_edges.append(e)
    return added_nodes, added_edges, relevant_ids
