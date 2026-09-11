"""Interface de persistência de conversas.

POC: implementação em memória por sessão (ver memory.py). A interface existe para trocar
depois por Lakebase sem mexer no resto (agent loop, endpoints). Não implementar Lakebase agora.

Chave da conversa = identidade do usuário + id da conversa do app.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str


@dataclass
class Conversation:
    user_email: str
    conversation_id: str
    messages: list[Message] = field(default_factory=list)
    # id da conversa no Genie One (Fase 3) — mantém o mesmo fio nas perguntas de follow-up.
    genie_conversation_id: str | None = None
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_used = time.time()


class ConversationStore(ABC):
    @abstractmethod
    def get(self, user_email: str, conversation_id: str) -> Conversation:
        """Retorna a conversa (criando uma vazia se não existir)."""

    @abstractmethod
    def reset(self, user_email: str, conversation_id: str) -> None:
        """Limpa a conversa (mensagens + genie_conversation_id)."""
