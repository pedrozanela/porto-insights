"""Modelo do grafo de relacionamentos — contrato backend ↔ frontend.

Espelha os tipos TypeScript da spec. O grafo é acumulativo por conversa: cada turno adiciona
nós/arestas e o frontend recebe deltas. IDs são determinísticos para deduplicar entre turnos.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# NodeType: person | calendar_event | email | email_thread | drive_file | genie_answer | data_asset
# EdgeType: attendee | organizer | sender | recipient | attached | links_to | in_thread |
#           mentions | same_time_window | related_to | cites | follows_up


@dataclass
class GraphNode:
    id: str
    type: str
    label: str
    source: str  # gmail | calendar | drive | genie
    first_seen_turn: int
    url: str | None = None
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    id: str
    source: str
    target: str
    type: str
    first_seen_turn: int
    weight: float = 1.0
    confidence: float = 1.0
    rationale: str | None = None
    evidence: list[str] = field(default_factory=list)


class GraphState:
    """Estado acumulativo do grafo de uma conversa. add_* deduplica e devolve só o que é novo."""

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}
        # último nó genie_answer por conversa do Genie (para arestas follows_up)
        self.last_genie_answer: dict[str, str] = {}

    def add_node(self, node: GraphNode) -> GraphNode | None:
        if node.id in self.nodes:
            return None
        self.nodes[node.id] = node
        return node

    def add_edge(self, edge: GraphEdge) -> GraphEdge | None:
        if edge.id in self.edges:
            return None
        # não cria aresta com pontas inexistentes
        if edge.source not in self.nodes or edge.target not in self.nodes:
            return None
        self.edges[edge.id] = edge
        return edge

    @staticmethod
    def edge_id(source: str, etype: str, target: str) -> str:
        return f"{source}|{etype}|{target}"

    def remove_node(self, node_id: str) -> None:
        """Remove um nó e todas as arestas que o tocam."""
        self.nodes.pop(node_id, None)
        for eid in [e.id for e in self.edges.values() if e.source == node_id or e.target == node_id]:
            self.edges.pop(eid, None)
        for k, v in list(self.last_genie_answer.items()):
            if v == node_id:
                del self.last_genie_answer[k]

    def merge_node(self, from_id: str, to_id: str) -> tuple[list["GraphEdge"], str | None]:
        """Funde `from_id` em `to_id`: reaponta as arestas e remove o `from_id`.
        Retorna (arestas novas reapontadas, from_id removido) para o delta."""
        if from_id not in self.nodes or to_id not in self.nodes or from_id == to_id:
            return [], None
        rerouted: list[GraphEdge] = []
        for e in [e for e in self.edges.values() if e.source == from_id or e.target == from_id]:
            ns = to_id if e.source == from_id else e.source
            nt = to_id if e.target == from_id else e.target
            if ns == nt:
                continue
            new = GraphEdge(id=self.edge_id(ns, e.type, nt), source=ns, target=nt, type=e.type,
                            first_seen_turn=e.first_seen_turn, weight=e.weight, confidence=e.confidence,
                            rationale=e.rationale, evidence=e.evidence)
            if self.add_edge(new):
                rerouted.append(new)
        self.remove_node(from_id)
        return rerouted, from_id


def delta_payload(added_nodes: list[GraphNode], added_edges: list[GraphEdge], turn: int,
                  removed_node_ids: list[str] | None = None) -> dict:
    return {
        "added_nodes": [asdict(n) for n in added_nodes],
        "added_edges": [asdict(e) for e in added_edges],
        "removed_node_ids": removed_node_ids or [],
        "turn": turn,
    }
