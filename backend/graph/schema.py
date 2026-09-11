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


def delta_payload(added_nodes: list[GraphNode], added_edges: list[GraphEdge], turn: int) -> dict:
    return {
        "added_nodes": [asdict(n) for n in added_nodes],
        "added_edges": [asdict(e) for e in added_edges],
        "turn": turn,
    }
