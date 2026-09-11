"""Extrai nós/arestas de resultados das tools do Drive (search, list_recent, file_metadata, file_read)."""
from __future__ import annotations

from typing import Any

from ..schema import GraphEdge, GraphNode, GraphState
from .common import drive_id, parse_gemini_title, person_id, provisional_event_id


def _owner(state: GraphState, added_n, added_e, fid_node: str, owners: list, turn: int) -> None:
    for o in owners or []:
        if not isinstance(o, dict) or not o.get("emailAddress"):
            continue
        pid = person_id(o["emailAddress"])
        n = state.add_node(GraphNode(id=pid, type="person", label=o.get("displayName") or o["emailAddress"],
                                     source="drive", url=f"mailto:{o['emailAddress']}", first_seen_turn=turn,
                                     props={"email": o["emailAddress"]}))
        if n:
            added_n.append(n)
        e = state.add_edge(GraphEdge(id=GraphState.edge_id(fid_node, "organizer", pid),
                                     source=fid_node, target=pid, type="organizer", first_seen_turn=turn))
        if e:
            added_e.append(e)


def _add_file(state: GraphState, added_n, added_e, f: dict[str, Any], turn: int) -> None:
    # As tools do Drive são inconsistentes: search/list/metadata trazem id/name/webViewLink no
    # topo; google_file_read aninha em "metadata" com document_id/title/web_view_link.
    if isinstance(f.get("metadata"), dict) and (
        f["metadata"].get("id") or f["metadata"].get("file_id") or f["metadata"].get("document_id")
    ):
        f = f["metadata"]
    fid = f.get("id") or f.get("file_id") or f.get("document_id")
    if not fid:
        return
    node_id = drive_id(fid)
    name = f.get("name") or f.get("title") or "(arquivo)"
    url = f.get("webViewLink") or f.get("web_view_link") or f.get("link")

    # Nota de reunião do Gemini? Então o rótulo perde o boilerplate e criamos o evento provisório.
    gemini = parse_gemini_title(name)
    if gemini:
        meeting_title, dt_iso = gemini
        label = f"{meeting_title[:44]} (notas)"
    else:
        label = name[:60]

    node = state.add_node(GraphNode(
        id=node_id, type="drive_file", label=label, source="drive",
        url=url, first_seen_turn=turn,
        props={"name": name, "title": name, "mimeType": f.get("mimeType"), "file_id": fid},
    ))
    if node:
        added_n.append(node)
    _owner(state, added_n, added_e, node_id, f.get("owners", []), turn)

    if gemini:
        meeting_title, dt_iso = gemini
        ev_id = provisional_event_id(meeting_title, dt_iso)
        ev = state.add_node(GraphNode(
            id=ev_id, type="calendar_event", label=meeting_title[:60], source="calendar",
            first_seen_turn=turn,
            props={"provisional": True, "start": dt_iso, "summary": meeting_title,
                   "inferred_from": "documento de notas do Gemini"},
        ))
        if ev:
            added_n.append(ev)
        e = state.add_edge(GraphEdge(
            id=GraphState.edge_id(node_id, "notes_of", ev_id), source=node_id, target=ev_id,
            type="notes_of", first_seen_turn=turn, weight=0.9, confidence=1.0,
            evidence=["título de nota do Gemini"]))
        if e:
            added_e.append(e)


def extract_drive(state: GraphState, tool_name: str, result: dict[str, Any], turn: int):
    added_n: list[GraphNode] = []
    added_e: list[GraphEdge] = []
    if tool_name in ("google_drive_search", "google_drive_list_recent"):
        for f in result.get("items", []) or []:
            _add_file(state, added_n, added_e, f, turn)
    elif tool_name in ("google_file_metadata", "google_file_read", "google_file_download"):
        _add_file(state, added_n, added_e, result, turn)
    return added_n, added_e
