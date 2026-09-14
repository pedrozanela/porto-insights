"""Extrai nós/arestas de resultados das tools do Calendar (event_list, event_get)."""
from __future__ import annotations

from typing import Any

from ..schema import GraphEdge, GraphNode, GraphState
from .common import display_name, drive_id, event_id, extract_drive_ids, person_id
from .drive import drive_file_from_url


def _person(state: GraphState, added_n, name: str, email: str, turn: int) -> str | None:
    if not email:
        return None
    pid = person_id(email)
    n = state.add_node(GraphNode(id=pid, type="person", label=display_name(name, email), source="calendar",
                                 url=f"mailto:{email}", first_seen_turn=turn, props={"email": email}))
    if n:
        added_n.append(n)
    return pid


def _start(ev: dict[str, Any]) -> str | None:
    s = ev.get("start") or {}
    if isinstance(s, dict):
        return s.get("dateTime") or s.get("date")
    return str(s) if s else None


def _attach(state: GraphState, added_n, added_e, cid: str, fid: str, url: str, turn: int) -> None:
    did = drive_file_from_url(state, added_n, fid, url, turn)
    if did:
        e = state.add_edge(GraphEdge(id=GraphState.edge_id(cid, "attached", did),
                                     source=cid, target=did, type="attached", first_seen_turn=turn,
                                     weight=0.9, evidence=["anexo/link do convite"]))
        if e:
            added_e.append(e)


def _add_event(state: GraphState, added_n, added_e, ev: dict[str, Any], turn: int, full: bool) -> None:
    eid_raw = ev.get("id")
    if not eid_raw:
        return
    cid = event_id(eid_raw)
    summary = ev.get("summary") or "(evento sem título)"
    desc = ev.get("description") or ""
    node = state.add_node(GraphNode(
        id=cid, type="calendar_event", label=summary[:60], source="calendar",
        url=ev.get("htmlLink"), first_seen_turn=turn,
        props={"summary": summary, "start": _start(ev), "location": ev.get("location"),
               "description": desc, "_text": f"{summary} {desc}",
               "recurring_id": ev.get("recurringEventId")}))
    if node:
        added_n.append(node)

    if not full:
        return  # event_list não traz attendees/organizer/anexos

    org = ev.get("organizer") or {}
    if isinstance(org, dict) and org.get("email"):
        pid = _person(state, added_n, org.get("displayName", ""), org["email"], turn)
        if pid:
            e = state.add_edge(GraphEdge(id=GraphState.edge_id(cid, "organizer", pid),
                                         source=cid, target=pid, type="organizer", first_seen_turn=turn))
            if e:
                added_e.append(e)
    for att in ev.get("attendees", []) or []:
        if not isinstance(att, dict) or not att.get("email"):
            continue
        pid = _person(state, added_n, att.get("displayName", ""), att["email"], turn)
        if pid:
            e = state.add_edge(GraphEdge(id=GraphState.edge_id(cid, "attendee", pid),
                                         source=cid, target=pid, type="attendee", first_seen_turn=turn))
            if e:
                added_e.append(e)

    # B1: anexos formais do convite → drive_file + attached
    for a in ev.get("attachments", []) or []:
        if not isinstance(a, dict):
            continue
        fid = a.get("fileId") or "".join(extract_drive_ids(a.get("fileUrl", "")))
        if fid:
            _attach(state, added_n, added_e, cid, fid, a.get("fileUrl") or "", turn)
    # links de Drive na descrição do convite → também tratados como anexo do evento
    for fid in extract_drive_ids(desc):
        _attach(state, added_n, added_e, cid, fid, f"https://docs.google.com/document/d/{fid}/edit", turn)


def extract_calendar(state: GraphState, tool_name: str, result: dict[str, Any], turn: int):
    added_n: list[GraphNode] = []
    added_e: list[GraphEdge] = []
    if tool_name == "calendar_event_list":
        for ev in result.get("items", []) or []:
            _add_event(state, added_n, added_e, ev, turn, full=False)
    elif tool_name == "calendar_event_get":
        _add_event(state, added_n, added_e, result, turn, full=True)
    return added_n, added_e
