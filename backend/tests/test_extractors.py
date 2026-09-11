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


def test_gmail_search_creates_email_thread_and_persons():
    state = GraphState()
    result = {"items": [{
        "id": "m1", "threadId": "t1", "subject": "Comitê de Crédito PJ",
        "from": "Ana <ana@porto.com>", "to": "Bruno <bruno@porto.com>", "date": "Thu, 10 Sep 2026 10:00:00 -0300",
        "snippet": "pauta do comitê",
    }]}
    nodes, edges = extract_gmail(state, "gmail_search", result, turn=1)
    types = sorted({n.type for n in nodes})
    assert types == ["email", "email_thread", "person"]
    etypes = {e.type for e in edges}
    assert {"sender", "recipient", "in_thread"} <= etypes


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
