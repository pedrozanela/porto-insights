"""Bloco 1: parser de notas do Gemini, evento provisório, notes_of e reconciliação. Sem rede."""
from __future__ import annotations

from backend.graph.extractors.calendar import extract_calendar
from backend.graph.extractors.common import parse_gemini_title, provisional_event_id
from backend.graph.extractors.drive import extract_drive
from backend.graph.linker import reconcile_provisionals
from backend.graph.schema import GraphState


def test_parse_variantes_e_timezone():
    en = parse_gemini_title("Databricks & Porto - App - 2026/09/10 10:02 GMT-03:00 - Notes by Gemini")
    assert en == ("Databricks & Porto - App", "2026-09-10T10:02:00-03:00")
    ptbr = parse_gemini_title("Quartile - sessão 1 Lakebase - 2026/08/21 16:01 GMT-03:00 - Anotações do Gemini")
    assert ptbr and ptbr[0] == "Quartile - sessão 1 Lakebase"
    abbr = parse_gemini_title("Calgary Energy Forum Discussion  - 2026/09/10 12:29 EDT - Notes by Gemini")
    assert abbr and abbr[1].endswith("-04:00")  # EDT
    # hífen no meio do título preservado
    hyph = parse_gemini_title("[Novo] :: Sync Databricks & Agi - Eng - 2026/09/08 16:09 GMT-03:00 - Notes by Gemini")
    assert hyph and hyph[0] == "[Novo] :: Sync Databricks & Agi - Eng"


def test_nao_reconhece_doc_comum():
    assert parse_gemini_title("B3 & Databricks - Kick Off 2026 | Notas Organizadas") is None
    assert parse_gemini_title("Databricks - AI Features Security") is None


def test_file_read_gemini_cria_evento_provisorio_e_notes_of():
    state = GraphState()
    result = {"metadata": {"document_id": "docABCDEFGHIJKLMNOPQRST",
                           "title": "Databricks & Porto - App - 2026/09/10 10:02 GMT-03:00 - Notes by Gemini",
                           "web_view_link": "https://docs.google.com/document/d/docABCDEFGHIJKLMNOPQRST/edit"},
              "content": "notas..."}
    nodes, edges = extract_drive(state, "google_file_read", result, turn=1)
    doc = next(n for n in nodes if n.type == "drive_file")
    assert doc.label.endswith("(notas)") and "Notes by Gemini" not in doc.label
    assert doc.props["title"].endswith("Notes by Gemini")  # título completo preservado
    ev = next(n for n in nodes if n.type == "calendar_event")
    assert ev.props["provisional"] is True and ev.props["start"] == "2026-09-10T10:02:00-03:00"
    assert any(e.type == "notes_of" and e.source == doc.id and e.target == ev.id for e in edges)


def test_reconciliacao_funde_provisorio_no_real():
    state = GraphState()
    # provisório (de nota) + sua aresta notes_of a partir do doc
    extract_drive(state, "google_file_read", {"metadata": {
        "document_id": "docABCDEFGHIJKLMNOPQRST",
        "title": "Databricks & Porto - App - 2026/09/10 10:02 GMT-03:00 - Notes by Gemini",
        "web_view_link": "https://x/d/docABCDEFGHIJKLMNOPQRST/edit"}}, turn=1)
    prov_id = provisional_event_id("Databricks & Porto - App", "2026-09-10T10:02:00-03:00")
    assert prov_id in state.nodes
    # evento REAL equivalente entra (mesmo título, start em ±15 min) com participante
    extract_calendar(state, "calendar_event_get", {
        "id": "realEVT", "summary": "Databricks & Porto - App",
        "start": {"dateTime": "2026-09-10T10:05:00-03:00"},
        "attendees": [{"email": "lucca@porto.com", "displayName": "Lucca Cruz"}],
    }, turn=2)
    edges, removed = reconcile_provisionals(state, turn=2)
    assert prov_id in removed and prov_id not in state.nodes           # provisório removido
    assert "calendar:realEVT" in state.nodes                           # real permanece
    # a aresta notes_of foi reapontada para o evento real
    assert any(e.type == "notes_of" and e.target == "calendar:realEVT" for e in state.edges.values())
