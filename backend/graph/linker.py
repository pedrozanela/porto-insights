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

from .extractors.calendar import extract_calendar
from .extractors.common import drive_id, extract_drive_ids
from .extractors.drive import extract_drive
from .extractors.gmail import extract_gmail
from .schema import GraphEdge, GraphState

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


SEMANTIC_PROMPT = """\
Você conecta um grafo de conhecimento. Recebe uma lista de NÓS existentes (id, tipo, rótulo).
Proponha arestas do tipo "related_to" entre nós que tratam do MESMO assunto/tema e que ainda
não estariam obviamente ligados (ex.: uma reunião e uma resposta de dados sobre o tema dela).

Regras:
- Use SOMENTE os ids fornecidos. NÃO invente nós.
- Cada aresta: {"source": id, "target": id, "confidence": 0..1, "rationale": "motivo curto em pt-BR"}.
- Só proponha o que tiver relação real e clara. Prefira poucas arestas de alta confiança.
- Responda APENAS um JSON: {"edges": [...]}.

NÓS:
"""


async def semantic_links(client, model: str, state: GraphState, turn: int, min_confidence: float) -> list[GraphEdge]:
    """Chamada enxuta ao LLM propondo arestas related_to entre nós existentes."""
    nodes = list(state.nodes.values())
    if len(nodes) < 2:
        return []
    listing = "\n".join(f'- {{"id": "{n.id}", "tipo": "{n.type}", "rotulo": "{n.label[:50]}"}}' for n in nodes)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": SEMANTIC_PROMPT + listing}],
            max_tokens=600,
        )
        content = resp.choices[0].message.content or "{}"
        content = content[content.find("{"): content.rfind("}") + 1] or "{}"
        proposed = json.loads(content).get("edges", [])
    except Exception as e:  # noqa: BLE001
        logger.info("semantic linker falhou/sem saída: %s", str(e)[:100])
        return []

    added: list[GraphEdge] = []
    for p in proposed:
        src, tgt = p.get("source"), p.get("target")
        conf = float(p.get("confidence", 0) or 0)
        if src not in state.nodes or tgt not in state.nodes or src == tgt or conf < min_confidence:
            continue
        e = state.add_edge(GraphEdge(
            id=GraphState.edge_id(src, "related_to", tgt), source=src, target=tgt, type="related_to",
            first_seen_turn=turn, weight=conf, confidence=conf, rationale=(p.get("rationale") or "")[:200],
        ))
        if e:
            added.append(e)
    return added
