"""Helpers compartilhados dos extratores: parsing de 'Nome <email>', IDs de nó, links de Drive."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone

_ADDR_RE = re.compile(r"^\s*(?:\"?(?P<name>[^\"<]*?)\"?\s*)?<(?P<email>[^>]+)>\s*$")
_DRIVE_ID_RE = re.compile(r"(?:/d/|[?&]id=)([a-zA-Z0-9_-]{20,})")

# Notas de reunião do Gemini: "<título> - YYYY/MM/DD HH:MM <TZ> - <sufixo Gemini>".
# Verificado nos títulos reais do Drive: sufixos "Notes by Gemini" e "Anotações do Gemini";
# TZ tanto "GMT-03:00" quanto abreviações ("EDT"); títulos podem ter hífen no meio.
_GEMINI_RE = re.compile(
    r"^(?P<title>.+?)\s*(?:-|às)\s*"
    r"(?P<date>\d{4}/\d{2}/\d{2})\s+(?P<time>\d{1,2}:\d{2})\s+"
    r"(?P<tz>GMT[+-]\d{1,2}(?::\d{2})?|[A-Za-z]{2,5})\s*-\s*"
    r"(?P<suffix>Notes by Gemini|Anota[çc][õo]es do Gemini|Notas do Gemini)\s*$"
)

_TZ_ABBR = {  # offsets em horas para abreviações comuns
    "UTC": 0, "GMT": 0, "BRT": -3, "BRST": -2, "EDT": -4, "EST": -5,
    "CDT": -5, "CST": -6, "MDT": -6, "MST": -7, "PDT": -7, "PST": -8,
}


def normalize_title(text: str) -> str:
    """Normaliza para comparação: minúsculas, sem acento, sem pontuação, espaços colapsados."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    no_accent = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-z0-9]+", " ", no_accent.lower())
    return " ".join(cleaned.split())


def _tz(tz: str) -> timezone | None:
    m = re.match(r"GMT([+-])(\d{1,2})(?::(\d{2}))?$", tz)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0)))
    if tz.upper() in _TZ_ABBR:
        return timezone(timedelta(hours=_TZ_ABBR[tz.upper()]))
    return None


def parse_gemini_title(name: str) -> tuple[str, str] | None:
    """Reconhece nota de reunião do Gemini. Retorna (título_da_reunião, datetime_iso) ou None."""
    if not name:
        return None
    m = _GEMINI_RE.match(name.strip())
    if not m:
        return None
    title = m.group("title").strip()
    try:
        y, mo, d = (int(x) for x in m.group("date").split("/"))
        hh, mm = (int(x) for x in m.group("time").split(":"))
        dt = datetime(y, mo, d, hh, mm, tzinfo=_tz(m.group("tz")))
    except ValueError:
        return None
    return title, dt.isoformat()


def provisional_event_id(title: str, dt_iso: str) -> str:
    key = f"{normalize_title(title)}|{dt_iso}"
    return f"calendar:provisional:{hashlib.sha1(key.encode()).hexdigest()}"


def provisional_person_id(name: str) -> str:
    return f"person:provisional:{hashlib.sha1(normalize_title(name).encode()).hexdigest()}"


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


_AUTOMATED = ("noreply", "no-reply", "donotreply", "do-not-reply", "notifications",
              "notification", "calendar-notification", "mailer-daemon", "automated")


def is_automated_sender(name: str, email: str) -> bool:
    """Remetentes automáticos (Gemini, noreply, notifications@, calendar-notification…)."""
    n, e = (name or "").lower(), (email or "").lower()
    if n in ("gemini", "google calendar", "google agenda"):
        return True
    return any(tok in e for tok in _AUTOMATED)


def display_name(name: str, email: str) -> str:
    """Rótulo de pessoa — NUNCA um email. Usa displayName; senão deriva do local part."""
    name = (name or "").strip()
    if name and "@" not in name and normalize_title(name) != normalize_title(email):
        return name
    local = (email or "").split("@")[0]
    parts = re.split(r"[._\-]+", local)
    return " ".join(p.capitalize() for p in parts if p) or email


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
