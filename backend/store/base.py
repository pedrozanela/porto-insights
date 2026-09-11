"""Interface de persistência de conversas.

Duas implementações: InMemory (POC/dev sem Lakebase) e Lakebase (Postgres, histórico real).
A escolha é feita em main.py conforme a config. O restante do app (agent loop, endpoints) só
conhece esta interface.

Isolamento por usuário: toda operação recebe user_email e a implementação garante que um
usuário só enxerga as próprias conversas.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class ConversationMeta:
    conversation_id: str
    title: str
    updated_at: str  # ISO 8601
    message_count: int


class ConversationStore(ABC):
    @abstractmethod
    def add_message(self, user_email: str, conversation_id: str, role: str, content: str) -> None:
        """Anexa uma mensagem. Cria a conversa se não existir (título = 1ª mensagem do usuário)."""

    @abstractmethod
    def get_messages(self, user_email: str, conversation_id: str) -> list[Message]:
        """Histórico da conversa, em ordem cronológica."""

    @abstractmethod
    def list_conversations(self, user_email: str) -> list[ConversationMeta]:
        """Conversas do usuário, mais recentes primeiro."""

    @abstractmethod
    def reset(self, user_email: str, conversation_id: str) -> None:
        """Remove a conversa (mensagens + metadados + fio do Genie)."""

    @abstractmethod
    def get_genie_conversation_id(self, user_email: str, conversation_id: str) -> str | None:
        """Fio do Genie One associado (Fase 3), para follow-ups."""

    @abstractmethod
    def set_genie_conversation_id(self, user_email: str, conversation_id: str, genie_id: str) -> None:
        ...
