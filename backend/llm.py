"""Acesso aos endpoints de modelo via AI Gateway, com OBO (token do usuário).

Usa o cliente OpenAI-compatible direto (base_url = {host}/serving-endpoints, api_key = token
do usuário) em vez de WorkspaceClient.serving_endpoints.get_open_ai_client(), que está
deprecado no SDK. O resultado é o mesmo endpoint, com controle explícito do token por request.
"""
from __future__ import annotations

import logging
from typing import Iterator

from openai import OpenAI

logger = logging.getLogger("porto_insights.llm")


def build_client(host_url: str, user_token: str) -> OpenAI:
    """Cliente OpenAI apontando para o Model Serving do workspace, autenticado como o usuário."""
    return OpenAI(base_url=f"{host_url}/serving-endpoints", api_key=user_token)


def stream_tokens(
    client: OpenAI,
    model: str,
    messages: list[dict],
    *,
    max_tokens: int = 1500,
) -> Iterator[str]:
    """Streama o texto da resposta token a token. Levanta exceção em erro de API."""
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
