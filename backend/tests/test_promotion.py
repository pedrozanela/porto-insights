"""Promoção por evidência + colapso de participantes. Sem rede."""
from __future__ import annotations

from backend.graph.promotion import promote, promote_ids, visible_delta
from backend.graph.schema import GraphEdge, GraphNode, GraphState, is_visible


def staged(nid, typ, label, **props):
    return GraphNode(id=nid, type=typ, label=label, source="gmail", first_seen_turn=1,
                     props={"staged": True, **props})


def test_promocao_por_referencia_na_resposta():
    st = GraphState()
    st.add_node(staged("gmail:m1", "email", "Comitê de Crédito PJ"))
    st.add_node(staged("gmail:m2", "email", "Almoço de sexta"))
    promote(st, answer_text="Encontrei o email do Comitê de Crédito PJ.", relevant_ids=set(), asked_text="")
    assert is_visible(st.nodes["gmail:m1"]) and not is_visible(st.nodes["gmail:m2"])


def test_promocao_por_relevant_ids():
    st = GraphState()
    st.add_node(staged("drive:d1", "drive_file", "Doc X"))
    promote(st, answer_text="", relevant_ids={"drive:d1"}, asked_text="")
    assert is_visible(st.nodes["drive:d1"])


def test_via_get_sozinho_nao_promove():
    # (c) removido: abrir "para conferir" (via_get) não é evidência — nem doc nem evento.
    st = GraphState()
    st.add_node(staged("drive:d1", "drive_file", "Doc aberto", via_get=True, file_id="doc1"))
    st.add_node(staged("calendar:e1", "calendar_event", "Contas Salesforce", via_get=True))
    promote(st, answer_text="resposta sem referência a nada disso", relevant_ids=set(), asked_text="")
    assert not is_visible(st.nodes["drive:d1"])
    assert not is_visible(st.nodes["calendar:e1"])


def test_promocao_por_id_canonico_de_url():
    # Referência por id canônico do Drive extraído de uma URL na resposta final.
    fid = "1AbCdef_GHIjklmno-PQRstuvwx12"
    st = GraphState()
    st.add_node(staged("drive:" + fid, "drive_file", "Pauta", file_id=fid))
    ans = f"Encontrei o doc: https://docs.google.com/document/d/{fid}/edit"
    promote(st, answer_text=ans, relevant_ids=set(), asked_text="")
    assert is_visible(st.nodes["drive:" + fid])


def test_tres_eventos_um_promovido():
    # Três eventos abertos (via_get); só o citado na resposta é promovido.
    st = GraphState()
    for i, name in enumerate(["Contas Salesforce", "M. Sales: BR SA Tech Meeting", "Databricks & Porto - App"]):
        st.add_node(staged(f"calendar:e{i}", "calendar_event", name, via_get=True, summary=name))
    promote(st, relevant_ids={"calendar:e2"},  # o linker marcou só o do Lucca
            answer_text="A reunião correspondente é a Databricks & Porto - App.", asked_text="Lucca")
    assert is_visible(st.nodes["calendar:e2"])
    assert not is_visible(st.nodes["calendar:e0"]) and not is_visible(st.nodes["calendar:e1"])


def test_promocao_tardia():
    st = GraphState()
    st.add_node(staged("calendar:e1", "calendar_event", "Contas Salesforce"))
    promote(st, answer_text="resposta sobre outra coisa", relevant_ids=set(), asked_text="")
    assert not is_visible(st.nodes["calendar:e1"])  # fica em staging
    # turno posterior: o semântico marca como relevante → promove
    promote(st, answer_text="Sobre a reunião Contas Salesforce...", relevant_ids={"calendar:e1"}, asked_text="")
    assert is_visible(st.nodes["calendar:e1"])


def test_evento_de_documento_de_notas_promove():
    # Doc de notas visível (via_get) → seu evento (notes_of) é promovido, mesmo sem relevant_ids.
    st = GraphState()
    st.add_node(staged("drive:d1", "drive_file", "Reunião X (notas)", via_get=True))
    st.add_node(staged("calendar:provisional:x", "calendar_event", "Reunião X"))
    st.add_edge(GraphEdge(id="nx", source="drive:d1", target="calendar:provisional:x",
                          type="notes_of", first_seen_turn=1))
    # doc promovido por relevant_ids → seu evento (notes_of) também promove
    promote(st, answer_text="", relevant_ids={"drive:d1"}, asked_text="")
    assert is_visible(st.nodes["drive:d1"]) and is_visible(st.nodes["calendar:provisional:x"])


def test_colapso_de_participantes():
    st = GraphState()
    st.add_node(staged("calendar:e1", "calendar_event", "Databricks & Porto - App", via_get=True))
    for pid, name in [("person:lucca", "Lucca Cruz"), ("person:org", "Organizador X"),
                      ("person:a", "Fulano A"), ("person:b", "Ciclano B")]:
        st.add_node(staged(pid, "person", name, email=pid))
    st.add_edge(GraphEdge(id="e|org", source="calendar:e1", target="person:org", type="organizer", first_seen_turn=1))
    for pid in ("person:lucca", "person:a", "person:b"):
        st.add_edge(GraphEdge(id=f"a|{pid}", source="calendar:e1", target=pid, type="attendee", first_seen_turn=1))

    # evento promovido por relevant_ids (b); participantes passam pelo colapso
    promote(st, answer_text="reunião com Lucca", relevant_ids={"calendar:e1"}, asked_text="Lucca")
    ev = st.nodes["calendar:e1"]
    assert is_visible(ev)
    assert is_visible(st.nodes["person:lucca"])   # perguntado
    assert is_visible(st.nodes["person:org"])     # organizador
    assert not is_visible(st.nodes["person:a"]) and not is_visible(st.nodes["person:b"])  # colapsados
    assert ev.props["staged_participants"] == 2
    assert {p["id"] for p in ev.props["staged_people"]} == {"person:a", "person:b"}

    # promoção manual de um participante colapsado
    promote_ids(st, ["person:a"])
    assert is_visible(st.nodes["person:a"])
    assert ev.props["staged_participants"] == 1


def test_visible_delta_exclui_staging():
    st = GraphState()
    st.add_node(staged("gmail:m1", "email", "visível", staged=False))
    st.add_node(staged("gmail:m2", "email", "escondido"))
    nodes, _ = visible_delta(st)
    assert [n.id for n in nodes] == ["gmail:m1"]


def test_anexo_promovido_com_evento():
    # B1: ao promover um evento, seu anexo (aresta attached) é promovido junto.
    st = GraphState()
    st.add_node(staged("calendar:e1", "calendar_event", "Comitê", summary="Comitê"))
    st.add_node(staged("drive:pauta", "drive_file", "Pauta", file_id="pauta"))
    st.add_edge(GraphEdge(id="att", source="calendar:e1", target="drive:pauta", type="attached", first_seen_turn=1))
    promote(st, relevant_ids={"calendar:e1"}, answer_text="", asked_text="")
    assert is_visible(st.nodes["calendar:e1"]) and is_visible(st.nodes["drive:pauta"])
