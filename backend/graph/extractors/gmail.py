"""Extrai nós/arestas de resultados das tools do Gmail (search, read_message, get_thread)."""
from __future__ import annotations

from typing import Any

from ..schema import GraphEdge, GraphNode, GraphState
from .common import email_id, parse_address, parse_address_list, person_id, thread_id

GMAIL_MSG_URL = "https://mail.google.com/mail/u/0/#all/"


def _add_person(state: GraphState, added_n, name: str, email: str, turn: int) -> str | None:
    if not email:
        return None
    pid = person_id(email)
    n = state.add_node(GraphNode(id=pid, type="person", label=name or email, source="gmail",
                                 url=f"mailto:{email}", first_seen_turn=turn, props={"email": email}))
    if n:
        added_n.append(n)
    return pid


def _add_email(state: GraphState, added_n, added_e, msg: dict[str, Any], turn: int) -> None:
    mid = msg.get("id") or msg.get("messageId")
    if not mid:
        return
    eid = email_id(mid)
    tid = msg.get("threadId")
    subject = msg.get("subject") or "(sem assunto)"
    # texto para o linker (corpo/snippet) detectar links de Drive
    body_text = " ".join(str(msg.get(k, "")) for k in ("body", "snippet"))
    en = state.add_node(GraphNode(
        id=eid, type="email", label=subject[:60], source="gmail",
        url=GMAIL_MSG_URL + str(mid), first_seen_turn=turn,
        props={"subject": subject, "from": msg.get("from"), "to": msg.get("to"),
               "date": msg.get("date"), "thread_id": tid, "snippet": msg.get("snippet"),
               "_text": body_text},
    ))
    if en:
        added_n.append(en)

    # thread + in_thread
    if tid:
        tnode = state.add_node(GraphNode(id=thread_id(tid), type="email_thread",
                                         label=f"Thread: {subject[:40]}", source="gmail",
                                         first_seen_turn=turn, props={"thread_id": tid}))
        if tnode:
            added_n.append(tnode)
        e = state.add_edge(GraphEdge(id=GraphState.edge_id(eid, "in_thread", thread_id(tid)),
                                     source=eid, target=thread_id(tid), type="in_thread", first_seen_turn=turn))
        if e:
            added_e.append(e)

    # sender / recipients
    if msg.get("from"):
        name, email = parse_address(str(msg["from"]))
        pid = _add_person(state, added_n, name, email, turn)
        if pid:
            e = state.add_edge(GraphEdge(id=GraphState.edge_id(eid, "sender", pid),
                                         source=eid, target=pid, type="sender", first_seen_turn=turn))
            if e:
                added_e.append(e)
    for field in ("to", "cc"):
        for name, email in parse_address_list(str(msg.get(field, "") or "")):
            pid = _add_person(state, added_n, name, email, turn)
            if pid:
                e = state.add_edge(GraphEdge(id=GraphState.edge_id(eid, "recipient", pid),
                                             source=eid, target=pid, type="recipient", first_seen_turn=turn))
                if e:
                    added_e.append(e)


def extract_gmail(state: GraphState, tool_name: str, result: dict[str, Any], turn: int):
    added_n: list[GraphNode] = []
    added_e: list[GraphEdge] = []

    if tool_name in ("gmail_search", "gmail_search_threads", "gmail_list_drafts"):
        for msg in result.get("items", []) or []:
            _add_email(state, added_n, added_e, msg, turn)
    elif tool_name == "gmail_read_message":
        _add_email(state, added_n, added_e, result, turn)
    elif tool_name == "gmail_get_thread":
        tid = result.get("id") or result.get("threadId")
        for msg in result.get("messages", []) or []:
            if tid and "threadId" not in msg:
                msg = {**msg, "threadId": tid}
            _add_email(state, added_n, added_e, msg, turn)
    return added_n, added_e
