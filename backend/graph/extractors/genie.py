"""Extrai nós/arestas do grafo a partir de um resultado do Genie One.

- 1 nó `genie_answer` (a resposta), com url = deep link "Explore in Databricks".
- N nós `data_asset` das fontes citadas: tabelas/metric views do SQL (via sqlglot) e dos
  links de /explore/data/ do corpo.
- arestas `cites`: genie_answer → data_asset.
- aresta `follows_up`: genie_answer anterior → atual (mesma conversa do Genie).

Arestas determinísticas (confidence = 1.0).
"""
from __future__ import annotations

import logging

import sqlglot
from sqlglot import exp

from ..schema import GraphEdge, GraphNode, GraphState

logger = logging.getLogger("porto_insights.graph.genie")


def _tables_from_sql(sql: str | None) -> list[str]:
    if not sql:
        return []
    try:
        parsed = sqlglot.parse_one(sql, read="databricks")
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for t in parsed.find_all(exp.Table):
        parts = [p for p in (t.catalog, t.db, t.name) if p]
        if parts:
            fq = ".".join(parts)
            if fq not in out:
                out.append(fq)
    return out


def _tables_from_links(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Links de /explore/data/ do corpo → (nome qualificado, url)."""
    out = []
    for label, url in links:
        if "/explore/data/" in url:
            out.append((label, url))
    return out


def extract_genie(
    state: GraphState,
    *,
    turn: int,
    genie_conversation_id: str,
    response_id: str,
    answer: str,
    deep_link: str | None,
    sql: str | None,
    links: list[tuple[str, str]],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    added_nodes: list[GraphNode] = []
    added_edges: list[GraphEdge] = []

    # Nó da resposta do Genie
    answer_id = f"genie:{genie_conversation_id}:{response_id}"
    label = (answer.strip().lstrip("#").strip().splitlines()[0][:60] if answer else "Resposta do Genie")
    n = state.add_node(GraphNode(
        id=answer_id, type="genie_answer", label=label or "Resposta do Genie",
        source="genie", url=deep_link, first_seen_turn=turn,
        props={"deep_link": deep_link},
    ))
    if n:
        added_nodes.append(n)

    # follows_up: liga à resposta anterior da mesma conversa do Genie
    prev = state.last_genie_answer.get(genie_conversation_id)
    if prev and prev != answer_id:
        e = state.add_edge(GraphEdge(
            id=GraphState.edge_id(prev, "follows_up", answer_id),
            source=prev, target=answer_id, type="follows_up", first_seen_turn=turn,
        ))
        if e:
            added_edges.append(e)
    state.last_genie_answer[genie_conversation_id] = answer_id

    # data_asset das tabelas do SQL + links de explore/data
    url_by_table = {}
    for lbl, url in _tables_from_links(links):
        url_by_table[lbl] = url

    tables = list(_tables_from_sql(sql))
    for lbl in url_by_table:
        if lbl not in tables:
            tables.append(lbl)

    for fq in tables:
        asset_id = f"asset:table:{fq}"
        short = fq.split(".")[-1]
        an = state.add_node(GraphNode(
            id=asset_id, type="data_asset", label=short,
            source="genie", url=url_by_table.get(fq), first_seen_turn=turn,
            # asset_type por heurística (mv_ = metric view); título técnico p/ tooltip/painel.
            props={"asset_type": "metric_view" if short.startswith("mv_") else "table",
                   "qualified_name": fq, "title": fq},
        ))
        if an:
            added_nodes.append(an)
        ce = state.add_edge(GraphEdge(
            id=GraphState.edge_id(answer_id, "cites", asset_id),
            source=answer_id, target=asset_id, type="cites", first_seen_turn=turn,
        ))
        if ce:
            added_edges.append(ce)

    return added_nodes, added_edges
