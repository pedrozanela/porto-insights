"""Linker determinístico (links_to, same_time_window) e allowlist read-only. Sem rede."""
from __future__ import annotations

from backend.graph.extractors.calendar import extract_calendar
from backend.graph.extractors.drive import extract_drive
from backend.graph.extractors.gmail import extract_gmail
from backend.graph.linker import build_candidates, deterministic_links, semantic_links
from backend.graph.schema import GraphEdge, GraphNode, GraphState
from backend.mcp.allowlist import allowed, is_write_tool


# --- fake client OpenAI-compatible (sem rede) para exercitar o linker semântico ---
class _FakeCompletions:
    def __init__(self, content):
        self.content = content

    async def create(self, **kwargs):
        msg = type("Msg", (), {"content": self.content})()
        choice = type("Choice", (), {"message": msg})()
        return type("Resp", (), {"choices": [choice]})()


class _FakeClient:
    def __init__(self, content):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(content)})()


def test_links_to_drive_from_email_body():
    fid = "1AbCdef_GHIjklmno-PQRstuvwx12"  # id realista (20+ chars)
    url = f"https://docs.google.com/document/d/{fid}/edit"
    state = GraphState()
    extract_drive(state, "google_drive_search",
                  {"items": [{"id": fid, "name": "Pauta", "webViewLink": url}]}, 1)
    extract_gmail(state, "gmail_read_message", {
        "id": "m1", "threadId": "t1", "subject": "Comitê", "from": "Ana <ana@porto.com>",
        "body": f"segue a pauta: {url}", "date": "Thu, 10 Sep 2026 10:00:00 -0300",
    }, 1)
    # o extrator do Gmail já cria a aresta links_to a partir do link no corpo
    deterministic_links(state, turn=1, time_window_days=3)
    assert any(e.type == "links_to" for e in state.edges.values())


def test_same_time_window_event_and_email_with_common_person():
    state = GraphState()
    extract_calendar(state, "calendar_event_get", {
        "id": "e1", "summary": "Comitê", "start": {"dateTime": "2026-09-11T14:00:00-03:00"},
        "attendees": [{"email": "ana@porto.com", "displayName": "Ana"}],
    }, 1)
    extract_gmail(state, "gmail_search", {"items": [{
        "id": "m1", "threadId": "t1", "subject": "Comitê", "from": "Ana <ana@porto.com>",
        "date": "Wed, 10 Sep 2026 10:00:00 -0300",
    }]}, 1)
    edges = deterministic_links(state, turn=1, time_window_days=3)
    assert any(e.type == "same_time_window" for e in edges)


def test_no_same_time_window_when_far_apart():
    state = GraphState()
    extract_calendar(state, "calendar_event_get", {
        "id": "e1", "summary": "Comitê", "start": {"dateTime": "2026-09-11T14:00:00-03:00"},
        "attendees": [{"email": "ana@porto.com", "displayName": "Ana"}],
    }, 1)
    extract_gmail(state, "gmail_search", {"items": [{
        "id": "m1", "threadId": "t1", "subject": "outro", "from": "Ana <ana@porto.com>",
        "date": "Mon, 01 Jun 2026 10:00:00 -0300",
    }]}, 1)
    edges = deterministic_links(state, turn=1, time_window_days=3)
    assert not any(e.type == "same_time_window" for e in edges)


def test_allowlist_blocks_writes_allows_reads():
    assert is_write_tool("gmail_send_message", None)
    assert is_write_tool("calendar_event_delete", None)
    assert not is_write_tool("gmail_search", None)
    assert not allowed("gmail_create_draft", "cria rascunho", extra_allow=set(), extra_deny=set())
    assert allowed("gmail_search", "busca", extra_allow=set(), extra_deny=set())
    # override por denylist
    assert not allowed("gmail_search", "busca", extra_allow=set(), extra_deny={"gmail_search"})


def test_build_candidates_cap_e_prioridade():
    # Fixture de 300 nós: corta em 80, e os nós do turno atual entram com prioridade.
    st = GraphState()
    for i in range(300):
        st.add_node(GraphNode(f"n{i}", "person", f"P{i}", "gmail",
                              first_seen_turn=(2 if i < 5 else 1), props={}))
    cands, total = build_candidates(st, turn=2, cap=80)
    assert total == 300 and len(cands) == 80
    ids = {c["id"] for c in cands}
    assert all(f"n{i}" in ids for i in range(5))            # os 5 do turno atual entram
    assert set(cands[0].keys()) == {"id", "tipo", "rotulo", "data"}   # lista compacta


async def test_linker_json_invalido_registra_health_e_nao_promove():
    # (a) JSON inválido não zera relevant_ids em silêncio: health.failed + turno só determinístico.
    st = GraphState()
    st.add_node(GraphNode("calendar:e", "calendar_event", "Comitê", "calendar", 1, props={}))
    st.add_node(GraphNode("genie:x", "genie_answer", "Carteira", "genie", 1, props={}))
    client = _FakeClient("isto não é json { quebrado")
    nodes, edges, relevant = await semantic_links(client, "m", st, 1, 0.6, answer_text="algo")
    assert nodes == [] and edges == [] and relevant == set()
    h = st.linker_health
    assert h["failed"] is True and h["parsed"] is False and h["error"]


async def test_linker_json_valido_promove_relevantes():
    st = GraphState()
    st.add_node(GraphNode("calendar:e", "calendar_event", "Comitê", "calendar", 1, props={}))
    st.add_node(GraphNode("genie:x", "genie_answer", "Carteira", "genie", 1, props={}))
    payload = ('{"edges": [{"source": "genie:x", "target": "calendar:e", "confidence": 0.9, '
               '"rationale": "mesmo tema"}], "mentions": [], "relevant_node_ids": ["calendar:e"]}')
    client = _FakeClient(payload)
    nodes, edges, relevant = await semantic_links(client, "m", st, 1, 0.6, answer_text="algo")
    assert relevant == {"calendar:e"}
    assert any(e.type == "related_to" for e in edges)
    assert st.linker_health["failed"] is False and st.linker_health["relevant"] == 1


def test_precedencia_deterministica_pair_linked():
    from backend.graph.linker import pair_linked
    st = GraphState()
    st.add_node(GraphNode(id="genie:x", type="genie_answer", label="a", source="genie", first_seen_turn=1))
    st.add_node(GraphNode(id="asset:table:cat.sch.mv", type="data_asset", label="mv", source="genie", first_seen_turn=1))
    st.add_edge(GraphEdge(id="c", source="genie:x", target="asset:table:cat.sch.mv", type="cites", first_seen_turn=1))
    # já ligados por 'cites' (determinístico) → o semântico não deve propor related_to
    assert pair_linked(st, "genie:x", "asset:table:cat.sch.mv")
    assert pair_linked(st, "asset:table:cat.sch.mv", "genie:x")
    assert not pair_linked(st, "genie:x", "inexistente")
