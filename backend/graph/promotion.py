"""Promoção por evidência: o grafo mostra evidência, não exploração.

Extratores põem nós em staging (props.staged=True). Um nó vira visível quando:
  (a) a resposta final o referencia (id, url ou título normalizado),
  (b) o linker semântico o marca em relevant_node_ids,
  (c) foi obtido via `get` explícito (props.via_get=True).
Nada é apagado; nós em staging ficam no store e podem ser promovidos num turno posterior.

Colapso de participantes: ao promover um calendar_event, promove como person apenas quem foi
perguntado, o organizador, e quem já está ligado a outro objeto visível. Os demais ficam em
staging; o evento ganha props.staged_participants (contagem) e props.staged_people (lista).
"""
from __future__ import annotations

from .extractors.common import normalize_title
from .schema import GraphState, is_visible


def _references(node, answer_text: str, answer_norm: str) -> bool:
    if node.id and node.id in answer_text:
        return True
    url = node.url or node.props.get("url") or node.props.get("web_view_link")
    if url and str(url) in answer_text:
        return True
    lab = normalize_title(node.props.get("title") or node.label)
    return len(lab) > 4 and lab in answer_norm


def _person_neighbors(state: GraphState, ev_id: str):
    out = []
    for e in state.edges.values():
        if e.type in ("attendee", "organizer"):
            other = e.target if e.source == ev_id else (e.source if e.target == ev_id else None)
            if other and other in state.nodes and state.nodes[other].type == "person":
                out.append((state.nodes[other], e.type))
    return out


def _person_linked_to_other_visible(state: GraphState, person_id: str, exclude_ev: str) -> bool:
    for e in state.edges.values():
        other = None
        if e.source == person_id:
            other = e.target
        elif e.target == person_id:
            other = e.source
        if other and other != exclude_ev and other in state.nodes:
            n = state.nodes[other]
            if n.type != "person" and is_visible(n):
                return True
    return False


def _collapse_participants(state: GraphState, ev, asked_norm: str, promoted: set[str]) -> None:
    staged_people = []
    for p, etype in _person_neighbors(state, ev.id):
        if is_visible(p):
            continue
        name_tokens = [t for t in normalize_title(p.label).split() if len(t) > 2]
        asked = any(t in asked_norm for t in name_tokens)
        is_org = etype == "organizer"
        linked = _person_linked_to_other_visible(state, p.id, ev.id)
        if asked or is_org or linked:
            p.props["staged"] = False
            promoted.add(p.id)
        else:
            staged_people.append({"id": p.id, "name": p.label})
    ev.props["staged_participants"] = len(staged_people)
    ev.props["staged_people"] = staged_people


def promote(state: GraphState, *, answer_text: str, relevant_ids: set[str], asked_text: str) -> set[str]:
    """Aplica as regras de promoção. Retorna os ids que passaram a ser visíveis neste passo."""
    answer_text = answer_text or ""
    answer_norm = normalize_title(answer_text)
    asked_norm = normalize_title(f"{asked_text} {answer_text}")
    promoted: set[str] = set()

    def eligible(n) -> bool:
        return _references(n, answer_text, answer_norm) or n.id in relevant_ids or bool(n.props.get("via_get"))

    # 1) nós não-evento: (a) referência, (b) relevant_ids ou (c) via_get.
    for n in list(state.nodes.values()):
        if n.type == "calendar_event" or is_visible(n):
            continue
        if eligible(n):
            n.props["staged"] = False
            promoted.add(n.id)

    # 2) eventos. Promove quando: (b) o linker semântico marca como relevante (decide qual é A
    # reunião da resposta), OU é o evento de um documento de notas já visível (aresta notes_of —
    # evidência forte). NÃO promove por via_get ("abrir para conferir") nem por menção textual
    # (o modelo pode LISTAR vários candidatos): isso é exploração, não evidência.
    notes_event_of_visible_doc = {
        e.target for e in state.edges.values()
        if e.type == "notes_of" and e.source in state.nodes and is_visible(state.nodes[e.source])
    }
    for ev in [n for n in state.nodes.values() if n.type == "calendar_event"]:
        if not is_visible(ev) and (ev.id in relevant_ids or ev.id in notes_event_of_visible_doc):
            ev.props["staged"] = False
            promoted.add(ev.id)
        if is_visible(ev):
            _collapse_participants(state, ev, asked_norm, promoted)

    return promoted


def promote_ids(state: GraphState, ids: list[str], *, asked_text: str = "") -> set[str]:
    """Promoção manual (ex.: usuário clica em um participante no painel de detalhe)."""
    asked_norm = normalize_title(asked_text)
    promoted: set[str] = set()
    for nid in ids:
        n = state.nodes.get(nid)
        if n and not is_visible(n):
            n.props["staged"] = False
            promoted.add(nid)
    for ev in [n for n in state.nodes.values() if n.type == "calendar_event" and is_visible(n)]:
        _collapse_participants(state, ev, asked_norm, promoted)
    return promoted


def visible_delta(state: GraphState):
    """Todos os nós/arestas visíveis (o frontend deduplica por id)."""
    nodes = [n for n in state.nodes.values() if is_visible(n)]
    vis = {n.id for n in nodes}
    edges = [e for e in state.edges.values() if e.source in vis and e.target in vis]
    return nodes, edges
