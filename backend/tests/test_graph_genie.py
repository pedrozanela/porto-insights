"""Extractor do grafo a partir do resultado do Genie: nós, cites e follows_up. Sem rede."""
from __future__ import annotations

from backend.graph.extractors.genie import _tables_from_sql, extract_genie
from backend.graph.schema import GraphState


def test_tables_from_sql():
    sql = "SELECT a FROM cat.sch.mv_carteira_credito WHERE x=1"
    assert _tables_from_sql(sql) == ["cat.sch.mv_carteira_credito"]


def test_tables_from_sql_invalid_returns_empty():
    assert _tables_from_sql("isto não é sql válido {{{") == []
    assert _tables_from_sql(None) == []


def test_extract_creates_answer_and_asset_with_cites():
    state = GraphState()
    nodes, edges = extract_genie(
        state, turn=1, genie_conversation_id="conv-1", response_id="r1",
        answer="Capital de Giro PJ 118% da meta", deep_link="https://ws/one/chat/threads/conv-1",
        sql="SELECT * FROM cat.sch.mv_carteira_credito", links=[],
    )
    types = sorted(n.type for n in nodes)
    assert types == ["data_asset", "genie_answer"]
    assert any(e.type == "cites" and e.confidence == 1.0 for e in edges)
    # dedupe: repetir o mesmo asset não recria nós
    nodes2, _ = extract_genie(
        state, turn=1, genie_conversation_id="conv-1", response_id="r1",
        answer="x", deep_link=None, sql="SELECT * FROM cat.sch.mv_carteira_credito", links=[],
    )
    assert nodes2 == []


def test_follows_up_between_consecutive_answers():
    state = GraphState()
    extract_genie(state, turn=1, genie_conversation_id="conv-1", response_id="r1",
                  answer="a1", deep_link=None, sql=None, links=[])
    _, edges = extract_genie(state, turn=2, genie_conversation_id="conv-1", response_id="r2",
                             answer="a2", deep_link=None, sql=None, links=[])
    assert any(e.type == "follows_up" for e in edges)


def test_data_asset_from_explore_link_without_sql():
    state = GraphState()
    nodes, _ = extract_genie(
        state, turn=1, genie_conversation_id="c", response_id="r",
        answer="x", deep_link=None, sql=None,
        links=[("cat.sch.tabela", "https://ws/explore/data/cat/sch/tabela")],
    )
    assert any(n.type == "data_asset" and n.props["qualified_name"] == "cat.sch.tabela" for n in nodes)
