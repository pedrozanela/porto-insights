"""Fase 0 — descoberta reproduzível do ambiente para o Porto Insights.

Roda um diagnóstico read-only do workspace e imprime o que o app precisa saber:
  1. profile / identidade
  2. Genie One MCP: tools/list (confirma o preview Managed MCP Servers)
  3. serving endpoints de chat + teste real de tool calling
  4. SQL warehouses (destaca serverless)
  5. MCP Services system.ai.{gmail,google_calendar,google_drive}: tools/list

Não cria nada. Autentica pelo profile fevm-pzanela-classic-aws (token OBO em prod é o do usuário).

Uso: python discover.py
"""
from __future__ import annotations

import asyncio
import json

import httpx2
from databricks.sdk import WorkspaceClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

PROFILE = "fevm-pzanela-classic-aws"
GOOGLE_SERVICES = ("gmail", "google_calendar", "google_drive")

TOOL_CALLING_CANDIDATES = [
    "databricks-claude-sonnet-5", "databricks-claude-opus-5", "databricks-claude-haiku-4-5",
    "databricks-gpt-5-5", "databricks-gpt-5-4", "databricks-gemini-3-8-flash",
    "databricks-llama-4-maverick", "databricks-grok-4-6",
]

PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "genie__ask",
        "description": "Pergunta analítica sobre dados",
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string"}, "follow_up": {"type": "boolean"}},
            "required": ["question"],
        },
    },
}


def w() -> WorkspaceClient:
    return WorkspaceClient(profile=PROFILE)


def token(client: WorkspaceClient) -> str:
    return client.config.oauth_token().access_token


async def mcp_tools(url: str, tok: str) -> list[str]:
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {tok}"}, timeout=60) as hc:
        async with streamable_http_client(url, http_client=hc) as st:
            async with ClientSession(st[0], st[1]) as s:
                await s.initialize()
                return [t.name for t in (await s.list_tools()).tools]


def test_tool_calling(client: WorkspaceClient, endpoint: str) -> str:
    oai = client.serving_endpoints.get_open_ai_client()
    try:
        resp = oai.chat.completions.create(
            model=endpoint,
            messages=[{"role": "user", "content": "Qual a carteira PJ neste mês? Use a ferramenta."}],
            tools=[PROBE_TOOL], tool_choice="auto", max_tokens=300,
        )
        tc = resp.choices[0].message.tool_calls
        return "OK (tool_calls)" if tc else "sem tool_calls"
    except Exception as e:  # noqa: BLE001
        return f"ERRO {str(e)[:70]}"


def main() -> None:
    client = w()
    host = client.config.host.rstrip("/")
    tok = token(client)

    print("== 1. Identidade ==")
    me = client.current_user.me()
    print(f"  profile={PROFILE}  host={host}")
    print(f"  usuário={me.user_name}")

    print("\n== 2. Genie One MCP ==")
    try:
        tools = asyncio.run(mcp_tools(f"{host}/api/2.0/mcp/genie", tok))
        print(f"  tools/list: {', '.join(tools)}")
    except Exception as e:  # noqa: BLE001
        print(f"  FALHOU (preview Managed MCP Servers habilitado?): {str(e)[:120]}")

    print("\n== 3. Serving endpoints (chat + tool calling) ==")
    all_eps = {e.name for e in client.serving_endpoints.list()}
    for ep in TOOL_CALLING_CANDIDATES:
        if ep in all_eps:
            print(f"  {ep:34} {test_tool_calling(client, ep)}")
        else:
            print(f"  {ep:34} (ausente neste workspace)")

    print("\n== 4. SQL warehouses ==")
    for wh in client.warehouses.list():
        serverless = getattr(wh, "enable_serverless_compute", None)
        print(f"  {wh.id}  serverless={serverless}  {wh.name}")

    print("\n== 5. MCP Services system.ai ==")
    for svc in GOOGLE_SERVICES:
        url = f"{host}/ai-gateway/mcp-services/system.ai.{svc}"
        try:
            tools = asyncio.run(mcp_tools(url, tok))
            print(f"  system.ai.{svc:16} tools: {', '.join(tools)}")
        except Exception as e:  # noqa: BLE001
            print(f"  system.ai.{svc:16} FALHOU (Login OAuth feito?): {str(e)[:100]}")


if __name__ == "__main__":
    main()
