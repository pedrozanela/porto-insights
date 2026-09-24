"""Descoberta de tools dos MCP Services do Google (system.ai.*).

Nunca inventar nomes de tools: descobre via tools/list em cada serviço no início da sessão
(cache curto por usuário), aplica a allowlist read-only e converte os schemas para o formato
`tools` do OpenAI. Mantém o mapa nome_da_tool → URL do serviço para rotear a execução.

Os nomes reais já trazem a origem (gmail_search, calendar_event_list, google_drive_search,
google_file_read), então não re-prefixamos; o `service_of` cobre a atribuição de origem.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .allowlist import allowed
from .client import mcp_session

logger = logging.getLogger("porto_insights.mcp.registry")

_CACHE_TTL_S = 300
_cache: dict[str, tuple[float, "ToolRegistry"]] = {}


@dataclass
class ToolRegistry:
    # tools no formato OpenAI (para passar ao modelo)
    openai_tools: list[dict[str, Any]] = field(default_factory=list)
    # nome da tool → URL do serviço MCP
    service_url: dict[str, str] = field(default_factory=dict)
    # nome da tool → "gmail" | "google_calendar" | "google_drive"
    service_name: dict[str, str] = field(default_factory=dict)
    # serviços que falharam no tools/list (ex.: sem login OAuth) → mensagem
    failed_services: dict[str, str] = field(default_factory=dict)

    def service_of(self, tool_name: str) -> str | None:
        return self.service_name.get(tool_name)


def _short(svc: str) -> str:
    # system.ai.gmail → gmail ; system.ai.google_calendar → calendar ; google_drive → drive
    base = svc.split(".")[-1]
    return {"google_calendar": "calendar", "google_drive": "drive",
            "web_search": "web"}.get(base, base)


async def build_registry(
    host_url: str, token: str, services: list[str], *,
    extra_allow: set[str] | None = None, extra_deny: set[str] | None = None,
) -> ToolRegistry:
    extra_allow = extra_allow or set()
    extra_deny = extra_deny or set()
    reg = ToolRegistry()

    async def _fetch(svc: str):
        url = f"{host_url}/ai-gateway/mcp-services/{svc}"
        try:
            async with mcp_session(url, token, timeout=12) as s:
                return svc, url, (await s.list_tools()).tools, None
        except Exception as e:  # noqa: BLE001 — serviço sem login OAuth ou indisponível
            return svc, url, None, str(e)[:200]

    # Descoberta CONCORRENTE: a latência do 1º turno vira a do serviço mais lento, não a soma
    # dos serviços (crítico quando o Google ainda não foi conectado → cada um ia até o timeout).
    results = await asyncio.gather(*(_fetch(svc) for svc in services))
    by_svc = {svc: (url, tools, err) for (svc, url, tools, err) in results}

    for svc in services:  # monta em ordem determinística
        url, tools, err = by_svc[svc]
        if err is not None:
            logger.warning("tools/list falhou em %s: %s", svc, err[:120])
            reg.failed_services[svc] = err
            continue
        for t in tools:
            if not allowed(t.name, t.description, extra_allow=extra_allow, extra_deny=extra_deny):
                logger.info("tool bloqueada (allowlist read-only): %s", t.name)
                continue
            reg.service_url[t.name] = url
            reg.service_name[t.name] = _short(svc)
            reg.openai_tools.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": (t.description or "")[:1024],
                    "parameters": t.input_schema or {"type": "object", "properties": {}},
                },
            })
    return reg


async def get_registry(host_url: str, token: str, services: list[str], **kwargs) -> ToolRegistry:
    """Cache curto por token para não refazer tools/list a cada turno."""
    key = hashlib.sha256(token.encode()).hexdigest()[:16]
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL_S:
        return hit[1]
    reg = await build_registry(host_url, token, services, **kwargs)
    _cache[key] = (now, reg)
    return reg
