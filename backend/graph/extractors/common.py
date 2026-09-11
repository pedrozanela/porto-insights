"""Helpers compartilhados dos extratores: parsing de 'Nome <email>', IDs de nó, links de Drive."""
from __future__ import annotations

import re

_ADDR_RE = re.compile(r"^\s*(?:\"?(?P<name>[^\"<]*?)\"?\s*)?<(?P<email>[^>]+)>\s*$")
_DRIVE_ID_RE = re.compile(r"(?:/d/|[?&]id=)([a-zA-Z0-9_-]{20,})")


def parse_address(raw: str) -> tuple[str, str]:
    """'David Meyer <david@x.com>' → ('David Meyer', 'david@x.com'). Sem '<>' vira (email, email)."""
    if not raw:
        return "", ""
    m = _ADDR_RE.match(raw)
    if m:
        email = m.group("email").strip().lower()
        name = (m.group("name") or "").strip() or email
        return name, email
    email = raw.strip().lower()
    return email, email


def parse_address_list(raw: str) -> list[tuple[str, str]]:
    """Divide 'a <a@x>, b <b@x>' respeitando vírgulas."""
    if not raw:
        return []
    return [parse_address(part) for part in raw.split(",") if part.strip()]


def person_id(email: str) -> str:
    return f"person:{email.lower()}"


def email_id(message_id: str) -> str:
    return f"gmail:{message_id}"


def thread_id(tid: str) -> str:
    return f"gmail:thread:{tid}"


def event_id(eid: str) -> str:
    return f"calendar:{eid}"


def drive_id(file_id: str) -> str:
    return f"drive:{file_id}"


def extract_drive_ids(text: str) -> list[str]:
    """IDs de arquivos do Drive citados em um texto (links docs.google.com/.../d/<id>)."""
    if not text:
        return []
    seen: list[str] = []
    for m in _DRIVE_ID_RE.finditer(text):
        fid = m.group(1)
        if fid not in seen:
            seen.append(fid)
    return seen
