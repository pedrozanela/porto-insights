"""Extrai nós/arestas de resultados das tools do Drive (search, list_recent, file_metadata, file_read)."""
from __future__ import annotations

from typing import Any

from ..schema import GraphEdge, GraphNode, GraphState
from .common import display_name, drive_id, parse_gemini_title, person_id, provisional_event_id


def _owner(state: GraphState, added_n, added_e, fid_node: str, owners: list, turn: int) -> None:
    for o in owners or []:
        if not isinstance(o, dict) or not o.get("emailAddress"):
            continue
        email = o["emailAddress"]
        pid = person_id(email)
        n = state.add_node(GraphNode(id=pid, type="person", label=display_name(o.get("displayName"), email),
                                     source="drive", url=f"mailto:{email}", first_seen_turn=turn,
                                     props={"email": email}))
        if n:
            added_n.append(n)
        e = state.add_edge(GraphEdge(id=GraphState.edge_id(fid_node, "organizer", pid),
                                     source=fid_node, target=pid, type="organizer", first_seen_turn=turn))
        if e:
            added_e.append(e)


def _upsert_file_node(state: GraphState, added_n, fid: str, label: str, url: str | None,
                      name: str, mime: str | None, turn: int) -> GraphNode:
    """Cria o drive_file ou faz upgrade de um stub existente (ex.: criado a partir de um link)."""
    node_id = drive_id(fid)
    existing = state.nodes.get(node_id)
    if existing:
        if name and name not in ("(documento)", "(arquivo)", "Documento sem título"):  # upgrade do stub
            existing.label = label
            existing.props.update({"name": name, "title": name, "mimeType": mime, "stub": False})
            if url:
                existing.url = url
        return existing
    node = GraphNode(id=node_id, type="drive_file", label=label, source="drive", url=url,
                     first_seen_turn=turn, props={"name": name, "title": name, "mimeType": mime, "file_id": fid})
    state.add_node(node)
    added_n.append(node)
    return node


def drive_file_from_url(state: GraphState, added_n, fid: str, url: str, turn: int) -> str | None:
    """Cria um drive_file 'stub' a partir de um id de arquivo do Drive (link em email/evento)."""
    node_id = drive_id(fid)
    if node_id in state.nodes:
        return node_id
    node = GraphNode(id=node_id, type="drive_file", label="Documento sem título", source="drive", url=url,
                     first_seen_turn=turn, props={"file_id": fid, "stub": True, "staged": True})
    state.add_node(node)
    added_n.append(node)
    return node_id


def _add_file(state: GraphState, added_n, added_e, f: dict[str, Any], turn: int) -> None:
    if isinstance(f.get("metadata"), dict) and (
        f["metadata"].get("id") or f["metadata"].get("file_id") or f["metadata"].get("document_id")
    ):
        f = f["metadata"]
    fid = f.get("id") or f.get("file_id") or f.get("document_id")
    if not fid:
        return
    name = f.get("name") or f.get("title") or "(arquivo)"
    url = f.get("webViewLink") or f.get("web_view_link") or f.get("link")
    mime = f.get("mimeType")

    gemini = parse_gemini_title(name)
    label = f"{gemini[0][:44]} (notas)" if gemini else name[:60]

    node = _upsert_file_node(state, added_n, fid, label, url, name, mime, turn)
    node_id = node.id
    _owner(state, added_n, added_e, node_id, f.get("owners", []), turn)

    if gemini:
        meeting_title, dt_iso = gemini
        ev_id = provisional_event_id(meeting_title, dt_iso)
        ev = state.add_node(GraphNode(
            id=ev_id, type="calendar_event", label=meeting_title[:60], source="calendar",
            first_seen_turn=turn,
            props={"provisional": True, "start": dt_iso, "summary": meeting_title,
                   "inferred_from": "documento de notas do Gemini"}))
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
