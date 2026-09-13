"""Extratores gmail/calendar/drive: resultado de tool → nós/arestas. Sem rede."""
from __future__ import annotations

from backend.graph.extractors.calendar import extract_calendar
from backend.graph.extractors.common import extract_drive_ids, parse_address, parse_address_list
from backend.graph.extractors.drive import extract_drive
from backend.graph.extractors.gmail import extract_gmail
from backend.graph.schema import GraphState


def test_parse_address():
    assert parse_address("David Meyer <david@x.com>") == ("David Meyer", "david@x.com")
    assert parse_address("a@x.com") == ("a@x.com", "a@x.com")
    assert parse_address_list("A <a@x.com>, B <b@x.com>") == [("A", "a@x.com"), ("B", "b@x.com")]


def test_extract_drive_ids():
    txt = "veja https://docs.google.com/document/d/1AbC_def-GHITjklmnop123456/edit e mais"
    assert extract_drive_ids(txt) == ["1AbC_def-GHITjklmnop123456"]


def test_gmail_search_cria_email_e_pessoas_sem_thread():
    # Busca NÃO cria nó de thread (A4); cria email + pessoas.
    state = GraphState()
    result = {"items": [{
        "id": "m1", "threadId": "t1", "subject": "Comitê de Crédito PJ",
        "from": "Ana <ana@porto.com>", "to": "Bruno <bruno@porto.com>", "date": "Thu, 10 Sep 2026 10:00:00 -0300",
        "snippet": "pauta do comitê",
    }]}
    nodes, edges = extract_gmail(state, "gmail_search", result, turn=1)
    types = {n.type for n in nodes}
    assert "email" in types and "person" in types
    assert "email_thread" not in types
    assert {"sender", "recipient"} <= {e.type for e in edges}


def test_gmail_thread_duas_mensagens_cria_thread():
    state = GraphState()
    result = {"id": "t1", "messages": [
        {"id": "m1", "subject": "Comitê", "from": "Ana <ana@porto.com>"},
        {"id": "m2", "subject": "Re: Comitê", "from": "Bruno <bruno@porto.com>"},
    ]}
    nodes, edges = extract_gmail(state, "gmail_get_thread", result, turn=1)
    assert any(n.type == "email_thread" for n in nodes)
    assert sum(1 for e in edges if e.type == "in_thread") == 2


def test_gmail_thread_uma_mensagem_sem_thread():
    state = GraphState()
    result = {"id": "t1", "messages": [{"id": "m1", "subject": "Só uma", "from": "Ana <ana@porto.com>"}]}
    nodes, _ = extract_gmail(state, "gmail_get_thread", result, turn=1)
    assert not any(n.type == "email_thread" for n in nodes)  # thread única não vira nó


def test_gmail_remetente_automatico():
    state = GraphState()
    result = {"items": [{"id": "m1", "threadId": "t1", "subject": "Notas da reunião",
                         "from": "Gemini <notifications@google.com>", "date": "Thu, 10 Sep 2026 10:00:00 -0300"}]}
    nodes, edges = extract_gmail(state, "gmail_search", result, turn=1)
    email = next(n for n in nodes if n.type == "email")
    assert email.props["automated_sender"] is True
    assert email.label.endswith("(automático)")
    assert not any(n.type == "person" for n in nodes)  # remetente automático não vira pessoa
    assert not any(e.type == "sender" for e in edges)


def test_gmail_link_de_drive_no_corpo_cria_drive_file():
    fid = "1AbCdef_GHIjklmno-PQRstuvwx12"
    state = GraphState()
    extract_gmail(state, "gmail_read_message", {
        "id": "m1", "threadId": "t1", "subject": "Comitê", "from": "Ana <ana@porto.com>",
        "body": f"segue a pauta: https://docs.google.com/document/d/{fid}/edit",
    }, turn=1)
    assert any(n.type == "drive_file" and n.props["file_id"] == fid for n in state.nodes.values())
    assert any(e.type == "links_to" for e in state.edges.values())


def test_pessoa_rotulo_nunca_email():
    state = GraphState()
    nodes, _ = extract_gmail(state, "gmail_search", {"items": [{
        "id": "m1", "threadId": "t1", "subject": "x", "from": "fernando.custodio@databricks.com",
    }]}, turn=1)
    p = next(n for n in nodes if n.type == "person")
    assert p.label == "Fernando Custodio" and "@" not in p.label
    assert p.props["email"] == "fernando.custodio@databricks.com"


def test_calendar_event_get_organizer_and_attendees():
    state = GraphState()
    ev = {
        "id": "e1", "summary": "Comitê de Crédito PJ", "start": {"dateTime": "2026-09-11T14:00:00-03:00"},
        "organizer": {"email": "ana@porto.com", "displayName": "Ana"},
        "attendees": [{"email": "bruno@porto.com", "displayName": "Bruno"},
                      {"email": "ana@porto.com", "displayName": "Ana"}],
        "description": "pauta",
    }
    nodes, edges = extract_calendar(state, "calendar_event_get", ev, turn=1)
    assert any(n.type == "calendar_event" for n in nodes)
    assert any(e.type == "organizer" for e in edges)
    assert sum(1 for e in edges if e.type == "attendee") == 2


def test_drive_search_creates_file():
    state = GraphState()
    result = {"items": [{"id": "f1", "name": "Pauta Comitê", "mimeType": "application/vnd.google-apps.document",
                         "webViewLink": "https://docs.google.com/document/d/f1/edit"}]}
    nodes, _ = extract_drive(state, "google_drive_search", result, turn=1)
    assert any(n.type == "drive_file" and n.props["file_id"] == "f1" for n in nodes)


def test_drive_file_read_nested_metadata():
    # google_file_read aninha id/name em "metadata"; o extractor deve desembrulhar e criar o nó.
    state = GraphState()
    # formato REAL do file_read: metadata.{document_id, title, web_view_link}
    result = {"metadata": {"document_id": "f9", "title": "Pauta Comitê",
                           "web_view_link": "https://docs.google.com/document/d/f9/edit"},
              "content": "texto...", "truncated": False}
    nodes, _ = extract_drive(state, "google_file_read", result, turn=1)
    n = next((x for x in nodes if x.type == "drive_file"), None)
    assert n and n.props["file_id"] == "f9" and n.label == "Pauta Comitê" and n.url
