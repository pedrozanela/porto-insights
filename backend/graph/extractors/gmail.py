"""Extrai nós/arestas de resultados das tools do Gmail (search, read_message, get_thread)."""
from __future__ import annotations

from typing import Any

from ..schema import GraphEdge, GraphNode, GraphState
from .common import (
    display_name, email_id, extract_drive_ids, is_automated_sender, parse_address,
    parse_address_list, person_id, thread_id,
)
from .drive import drive_file_from_url

GMAIL_MSG_URL = "https://mail.google.com/mail/u/0/#all/"


def _add_person(state: GraphState, added_n, name: str, email: str, turn: int) -> str | None:
    if not email:
        return None
    pid = person_id(email)
    n = state.add_node(GraphNode(id=pid, type="person", label=display_name(name, email), source="gmail",
                                 url=f"mailto:{email}", first_seen_turn=turn, props={"email": email}))
    if n:
        added_n.append(n)
    return pid


def _add_email(state: GraphState, added_n, added_e, msg: dict[str, Any], turn: int) -> str | None:
    mid = msg.get("id") or msg.get("messageId")
    if not mid:
        return None
    eid = email_id(mid)
    tid = msg.get("threadId")
    subject = msg.get("subject") or "(sem assunto)"
    body_text = " ".join(str(msg.get(k, "")) for k in ("body", "snippet"))

    # remetente automático? (Gemini, noreply, notifications…) → não vira person
    from_name, from_email = parse_address(str(msg.get("from", "") or ""))
    automated = bool(from_email) and is_automated_sender(from_name, from_email)
    label = subject[:60] + (" (automático)" if automated else "")

    en = state.add_node(GraphNode(
        id=eid, type="email", label=label, source="gmail", url=GMAIL_MSG_URL + str(mid),
        first_seen_turn=turn,
        props={"subject": subject, "from": msg.get("from"), "to": msg.get("to"),
               "date": msg.get("date"), "thread_id": tid, "snippet": msg.get("snippet"),
               "_text": body_text, "automated_sender": automated}))
    if en:
        added_n.append(en)

    if from_email and not automated:
        pid = _add_person(state, added_n, from_name, from_email, turn)
        if pid:
            e = state.add_edge(GraphEdge(id=GraphState.edge_id(eid, "sender", pid),
                                         source=eid, target=pid, type="sender", first_seen_turn=turn))
            if e:
                added_e.append(e)
    for field in ("to", "cc"):
        for name, email in parse_address_list(str(msg.get(field, "") or "")):
            if is_automated_sender(name, email):
                continue
            pid = _add_person(state, added_n, name, email, turn)
            if pid:
                e = state.add_edge(GraphEdge(id=GraphState.edge_id(eid, "recipient", pid),
                                             source=eid, target=pid, type="recipient", first_seen_turn=turn))
                if e:
                    added_e.append(e)

    # links de Drive no corpo → drive_file + links_to (A3)
    for fid in extract_drive_ids(body_text):
        url = f"https://docs.google.com/document/d/{fid}/edit"
        did = drive_file_from_url(state, added_n, fid, url, turn)
        if did:
            e = state.add_edge(GraphEdge(id=GraphState.edge_id(eid, "links_to", did),
                                         source=eid, target=did, type="links_to", first_seen_turn=turn,
                                         evidence=["link de Drive no corpo do email"]))
            if e:
                added_e.append(e)
    return eid


def extract_gmail(state: GraphState, tool_name: str, result: dict[str, Any], turn: int):
    added_n: list[GraphNode] = []
    added_e: list[GraphEdge] = []

    if tool_name in ("gmail_search", "gmail_search_threads", "gmail_list_drafts"):
        for msg in result.get("items", []) or []:
            _add_email(state, added_n, added_e, msg, turn)  # buscas não criam nó de thread
    elif tool_name == "gmail_read_message":
        _add_email(state, added_n, added_e, result, turn)
    elif tool_name == "gmail_get_thread":
        tid = result.get("id") or result.get("threadId")
        messages = result.get("messages", []) or []
        eids = []
        for msg in messages:
            if tid and "threadId" not in msg:
                msg = {**msg, "threadId": tid}
            eid = _add_email(state, added_n, added_e, msg, turn)
            if eid:
                eids.append(eid)
        # nó de thread só quando há 2+ mensagens (A4)
        if tid and len(eids) >= 2:
            subject = (messages[0].get("subject") if messages else "") or "thread"
            tn = state.add_node(GraphNode(id=thread_id(tid), type="email_thread",
                                          label=f"Thread: {subject[:40]}", source="gmail",
                                          first_seen_turn=turn, props={"thread_id": tid}))
            if tn:
                added_n.append(tn)
            for eid in eids:
                e = state.add_edge(GraphEdge(id=GraphState.edge_id(eid, "in_thread", thread_id(tid)),
                                             source=eid, target=thread_id(tid), type="in_thread",
                                             first_seen_turn=turn))
                if e:
                    added_e.append(e)
    return added_n, added_e
