"""Acesso aos endpoints de modelo via AI Gateway, com OBO (token do usuário).

Cliente OpenAI-compatible assíncrono (base_url = {host}/serving-endpoints, api_key = token do
usuário). Assíncrono porque o loop do agente também faz chamadas MCP assíncronas ao Genie.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

logger = logging.getLogger("porto_insights.llm")


def build_async_client(host_url: str, user_token: str) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=f"{host_url}/serving-endpoints", api_key=user_token)


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
) -> AsyncIterator[dict[str, Any]]:
    """Streama uma chamada ao modelo. Emite {"type":"token","text":...} durante e, ao final,
    {"type":"complete","content":str,"tool_calls":[...]} (tool_calls no formato OpenAI)."""
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": True}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    stream = await client.chat.completions.create(**kwargs)

    content_parts: list[str] = []
    # acumula tool_calls por índice (chegam fragmentados no streaming)
    tool_acc: dict[int, dict[str, Any]] = {}
    finish_reason: str | None = None

    async for chunk in stream:
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
    yield {"type": "complete", "content": "".join(content_parts), "tool_calls": tool_calls,
           "finish_reason": finish_reason}
