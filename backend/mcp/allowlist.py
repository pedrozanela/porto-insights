"""Allowlist read-only (defesa em profundidade).

Os serviços built-in system.ai.* já bloqueiam escrita por service policy (só expõem o
subconjunto de leitura). Ainda assim, bloqueamos no backend qualquer tool cujo nome ou
descrição sugira escrita, para que uma tool de escrita nunca chegue ao modelo.
"""
from __future__ import annotations

import re

# Verbos/indícios de escrita. Casados como palavras nos tokens do nome e na descrição.
WRITE_HINTS = {
    "send", "create", "update", "delete", "move", "trash", "share", "modify",
    "insert", "reply", "draft", "label", "unlabel", "remove", "patch", "write",
    "add", "set", "compose", "forward", "archive", "star", "import", "upload",
}

_TOKEN_RE = re.compile(r"[a-z]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def is_write_tool(name: str, description: str | None) -> bool:
    """True se o nome sugere escrita (checa tokens do nome; a descrição só reforça)."""
    name_tokens = _tokens(name)
    if name_tokens & WRITE_HINTS:
        return True
    return False


def allowed(name: str, description: str | None, *, extra_allow: set[str], extra_deny: set[str]) -> bool:
    if name in extra_deny:
        return False
    if name in extra_allow:
        return True
    return not is_write_tool(name, description)
