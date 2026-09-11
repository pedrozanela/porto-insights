"""Loop de um turno de conversa.

Fase 2: streaming de chat via AI Gateway (OBO), sem ferramentas. Estruturado como gerador de
eventos SSE para que as Fases 3/4 insiram tool calls, progresso e deltas de grafo sem reescrever
o endpoint. Gerador síncrono (a StreamingResponse do FastAPI o roda em threadpool); as chamadas
MCP assíncronas das próximas fases entram via helper dedicado.
"""
from __future__ import annotations

import logging
from typing import Iterator

from ..auth import UserContext
from ..config import Settings
from ..llm import build_client, stream_tokens
from ..sse import sse
from ..store.base import ConversationStore
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger("porto_insights.agent")


def _resolve_model(settings: Settings, requested: str) -> tuple[str, str | None]:
    """Valida o modelo contra a allowlist. Retorna (modelo, aviso_ou_None)."""
    allowed = {e.name for e in settings.endpoints}
    if requested and requested in allowed:
        return requested, None
    default = settings.default_endpoint
    if requested:
        return default, f"Modelo '{requested}' não está disponível; usando {default}."
    return default, None


def run_turn(
    user: UserContext,
    settings: Settings,
    store: ConversationStore,
    conversation_id: str,
    user_message: str,
    requested_model: str,
) -> Iterator[str]:
    """Processa um turno e streama eventos SSE."""
    user_message = (user_message or "").strip()
    if not user_message:
        yield sse("error", message="Mensagem vazia.")
        return

    model, warning = _resolve_model(settings, requested_model)

    # Histórico anterior + a nova mensagem do usuário (persistida no store).
    history = store.get_messages(user.email, conversation_id)
    store.add_message(user.email, conversation_id, "user", user_message)

    yield sse("turn_start", conversation_id=conversation_id, model=model)
    if warning:
        yield sse("warning", message=warning)

    # Monta o contexto: system + histórico + mensagem atual.
    payload = [{"role": "system", "content": SYSTEM_PROMPT}]
    payload += [{"role": m.role, "content": m.content} for m in history]
    payload.append({"role": "user", "content": user_message})

    # Trace básico: registra qual modelo respondeu este turno.
    logger.info("turno usuário=%s conversa=%s modelo=%s", user.email, conversation_id, model)

    parts: list[str] = []
    try:
        client = build_client(settings.host_url, user.token)
        for token in stream_tokens(client, model, payload, max_tokens=1500):
            parts.append(token)
            yield sse("token", text=token)
    except Exception as e:  # noqa: BLE001
        logger.exception("erro no turno (modelo=%s)", model)
        # Mensagem amigável em pt-BR; detalhe técnico só no log.
        yield sse(
            "error",
            message=f"Não consegui obter a resposta do modelo {model}. "
            "Tente novamente ou troque de modelo.",
            detail=str(e)[:200],
        )
        return

    answer = "".join(parts)
    store.add_message(user.email, conversation_id, "assistant", answer)
    yield sse("done", conversation_id=conversation_id, model=model)
