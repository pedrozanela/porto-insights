"""Sessão MCP assíncrona sobre Streamable HTTP, autenticada com o token do usuário (OBO).

Confirmado na Fase 0 (pacote mcp 2.x): o cliente é
    streamable_http_client(url, http_client=httpx2.AsyncClient(headers=Bearer ...))
mais ClientSession(read, write); os campos são snake_case (structured_content, input_schema).
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@asynccontextmanager
async def mcp_session(url: str, token: str, *, timeout: float = 120) -> AsyncIterator[ClientSession]:
    """Abre e inicializa uma sessão MCP no servidor `url` com o token OBO."""
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx2.AsyncClient(headers=headers, timeout=timeout) as hc:
        async with streamable_http_client(url, http_client=hc) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                yield session


def structured(result: Any) -> dict[str, Any]:
    """Extrai o structured_content de um CallToolResult (snake_case no mcp 2.x),
    caindo para o parse do texto JSON quando necessário."""
    sc = getattr(result, "structured_content", None)
    if sc:
        return sc
    txt = text_content(result)
    if txt.strip().startswith("{"):
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            pass
    return {}


def text_content(result: Any) -> str:
    return "\n".join(c.text for c in (result.content or []) if getattr(c, "text", None))


async def list_tool_names(url: str, token: str) -> list[str]:
    async with mcp_session(url, token) as s:
        return [t.name for t in (await s.list_tools()).tools]
