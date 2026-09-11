"""Bloco 5: regras de sugestão a partir das lacunas do grafo. Sem rede."""
from __future__ import annotations

from backend.graph.schema import GraphEdge, GraphNode, GraphState
from backend.graph.suggestions import build_suggestions


def _ev(state, nid="calendar:e1", label="Comitê de Crédito PJ"):
    state.add_node(GraphNode(id=nid, type="calendar_event", label=label, source="calendar",
                             first_seen_turn=1, props={"start": "2026-09-11T14:00:00-03:00", "summary": label}))


def test_evento_sem_email_sugere_emails():
    state = GraphState()
    _ev(state)
    sugg = build_suggestions(state)
    assert any("emails" in s["label"].lower() and s["node_id"] == "calendar:e1" for s in sugg)


def test_nao_repete_pergunta_ja_feita():
    state = GraphState()
    _ev(state)
    first = build_suggestions(state)[0]
    again = build_suggestions(state, asked={first["prompt"]})
    assert all(s["prompt"] != first["prompt"] for s in again)


def test_limite_de_tres():
    state = GraphState()
    for i in range(6):
        _ev(state, nid=f"calendar:e{i}", label=f"Reunião {i}")
    assert len(build_suggestions(state)) <= 3


def _edge(state, a, t, b):
    state.add_edge(GraphEdge(id=GraphState.edge_id(a, t, b), source=a, target=b, type=t, first_seen_turn=1))


def test_pessoa_com_dois_objetos():
    # Evento sem lacunas de maior prioridade (tem email e doc), para a regra 5 (pessoa) surgir.
    state = GraphState()
    _ev(state, nid="calendar:e1", label="Reunião A")
    state.add_node(GraphNode(id="gmail:m1", type="email", label="assunto", source="gmail", first_seen_turn=1, props={}))
    state.add_node(GraphNode(id="drive:d1", type="drive_file", label="doc", source="drive", first_seen_turn=1, props={}))
    state.add_node(GraphNode(id="person:lucca@porto.com", type="person", label="Lucca Cruz",
                             source="calendar", first_seen_turn=1, props={"email": "lucca@porto.com"}))
    _edge(state, "calendar:e1", "same_time_window", "gmail:m1")
    _edge(state, "calendar:e1", "links_to", "drive:d1")
    _edge(state, "gmail:m1", "links_to", "drive:d1")
    _edge(state, "calendar:e1", "attendee", "person:lucca@porto.com")
    _edge(state, "gmail:m1", "recipient", "person:lucca@porto.com")
    assert any("Lucca" in s["label"] for s in build_suggestions(state))


def test_self_nao_gera_sugestao_de_pessoa():
    state = GraphState()
    _ev(state, nid="calendar:e1")
    _ev(state, nid="calendar:e2", label="Outra")
    state.add_node(GraphNode(id="person:me", type="person", label="Você", source="calendar",
                             first_seen_turn=1, props={"email": "me@x.com", "is_self": True}))
    for e in ("calendar:e1", "calendar:e2"):
        state.add_edge(GraphEdge(id=GraphState.edge_id(e, "attendee", "person:me"),
                                 source=e, target="person:me", type="attendee", first_seen_turn=1))
    assert not any("Você" in s["label"] for s in build_suggestions(state))
