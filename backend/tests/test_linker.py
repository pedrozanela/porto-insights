"""Linker determinístico (links_to, same_time_window) e allowlist read-only. Sem rede."""
from __future__ import annotations

from backend.graph.extractors.calendar import extract_calendar
from backend.graph.extractors.drive import extract_drive
from backend.graph.extractors.gmail import extract_gmail
from backend.graph.linker import deterministic_links
from backend.graph.schema import GraphState
from backend.mcp.allowlist import allowed, is_write_tool


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
    edges = deterministic_links(state, turn=1, time_window_days=3)
    assert any(e.type == "links_to" for e in edges)


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
