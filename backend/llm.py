"""Acesso aos endpoints de modelo via AI Gateway, com OBO (token do usuário).

Cliente OpenAI-compatible assíncrono (base_url = {host}/serving-endpoints, api_key = token do
usuário). Assíncrono porque o loop do agente também faz chamadas MCP assíncronas ao Genie.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

logger = logging.getLogger("porto_insights.llm")


def build_async_client(host_url: str, user_token: str) -> AsyncOpenAI:
    """Cliente OBO: api_key = token do usuário (x-forwarded-access-token)."""
    return AsyncOpenAI(base_url=f"{host_url}/serving-endpoints", api_key=user_token)


# Token do service principal do app (M2M), com cache/refresh — mesma identidade que o Lakebase usa.
_sp_wsc = None
_sp_token: str = ""
_sp_token_at: float = 0.0
_SP_TTL_S = 40 * 60  # tokens M2M ~1h; renova antes


def _sp_token_cached(profile: str) -> str:
    global _sp_wsc, _sp_token, _sp_token_at
    now = time.time()
    if _sp_token and now - _sp_token_at < _SP_TTL_S:
        return _sp_token
    from databricks.sdk import WorkspaceClient
    if _sp_wsc is None:
        # Prod (Databricks Apps): identidade do SP via default credential chain (M2M).
        # Dev local: profile do CLI.
        _sp_wsc = WorkspaceClient() if os.environ.get("DATABRICKS_APP_PORT") else WorkspaceClient(profile=profile)
    hdrs = _sp_wsc.config.authenticate()  # {"Authorization": "Bearer <token>"}
    auth = hdrs.get("Authorization", "")
    _sp_token = auth.split(" ", 1)[1].strip() if " " in auth else auth
    _sp_token_at = now
    return _sp_token


def build_sp_client(host_url: str, profile: str) -> AsyncOpenAI:
    """Cliente com a identidade do SERVICE PRINCIPAL do app (M2M), para as chamadas de modelo
    quando MODELS_USE_SP=true. Os dados (Genie/Google) continuam OBO."""
    return AsyncOpenAI(base_url=f"{host_url}/serving-endpoints", api_key=_sp_token_cached(profile))


def _delta_text(content: Any) -> str:
    """Extrai texto visível do delta.content. Modelos com raciocínio (ex.: Claude no Databricks)
    entregam uma LISTA de blocos; só os blocos de texto viram tokens (reasoning é ignorado)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for block in content:
            if isinstance(block, str):
                out.append(block)
            elif isinstance(block, dict) and block.get("type") in ("text", "output_text") and block.get("text"):
                out.append(block["text"])
        return "".join(out)
    return ""


async def stream_turn(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    *,
    max_tokens: int = 4000,
    effort: str = "low",
) -> AsyncIterator[dict[str, Any]]:
    """Streama uma chamada ao modelo. Emite {"type":"token","text":...} durante e, ao final,
    {"type":"complete","content":str,"tool_calls":[...]} (tool_calls no formato OpenAI).

    effort="low": reduz a profundidade do reasoning (menos tokens/latência) — adequado a um chat
    executivo. Passado via output_config no corpo (a interface OpenAI-compat do Databricks aceita;
    `reasoning_effort` NÃO é aceito). Cache de prompt: o chamador marca o prefixo estável
    (tools + system) com cache_control; aqui só repassamos as mensagens."""
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens,
                              "stream": True, "extra_body": {"output_config": {"effort": effort}},
                              "stream_options": {"include_usage": True}}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    stream = await client.chat.completions.create(**kwargs)

    content_parts: list[str] = []
    # acumula tool_calls por índice (chegam fragmentados no streaming)
    tool_acc: dict[int, dict[str, Any]] = {}
    finish_reason: str | None = None
    usage = None

    async for chunk in stream:
        if getattr(chunk, "usage", None):  # chunk final (include_usage) — sem choices
            usage = chunk.usage
        if not chunk.choices:
            continue
        if chunk.choices[0].finish_reason:
            finish_reason = chunk.choices[0].finish_reason
        delta = chunk.choices[0].delta
        text = _delta_text(getattr(delta, "content", None)) if delta else ""
        if text:
            content_parts.append(text)
            yield {"type": "token", "text": text}
        for tc in (getattr(delta, "tool_calls", None) or []):
            acc = tool_acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
            if tc.id:
                acc["id"] = tc.id
            if tc.function and tc.function.name:
                acc["name"] = tc.function.name
            if tc.function and tc.function.arguments:
                acc["arguments"] += tc.function.arguments

    tool_calls = [
        {"id": a["id"], "type": "function",
         "function": {"name": a["name"], "arguments": a["arguments"]}}
        for _, a in sorted(tool_acc.items())
    ]
    if finish_reason == "length":
        logger.warning("resposta truncada por max_tokens=%d (finish_reason=length)", max_tokens)
    if usage is not None:  # observabilidade do cache de prompt
        cr = getattr(usage, "cache_read_input_tokens", 0) or 0
        cc = getattr(usage, "cache_creation_input_tokens", 0) or 0
        logger.info("llm usage in=%s out=%s cache_read=%s cache_create=%s",
                    getattr(usage, "prompt_tokens", "?"), getattr(usage, "completion_tokens", "?"), cr, cc)
    yield {"type": "complete", "content": "".join(content_parts), "tool_calls": tool_calls,
           "finish_reason": finish_reason}
