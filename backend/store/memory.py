"""ConversationStore em memória, com TTL. Fallback para dev sem Lakebase — não persiste."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .base import ConversationMeta, ConversationStore, Message

DEFAULT_TTL_S = 60 * 60 * 4  # 4h


@dataclass
class _Conv:
    title: str = ""
    messages: list[Message] = field(default_factory=list)
    genie_conversation_id: str | None = None
    graph: dict | None = None
    updated_at: float = field(default_factory=time.time)


class InMemoryConversationStore(ConversationStore):
    def __init__(self, ttl_s: int = DEFAULT_TTL_S) -> None:
        self._ttl = ttl_s
        self._lock = threading.Lock()
        self._data: dict[tuple[str, str], _Conv] = {}

    def _evict(self) -> None:
        cutoff = time.time() - self._ttl
        for k in [k for k, c in self._data.items() if c.updated_at < cutoff]:
            del self._data[k]

    def add_message(self, user_email: str, conversation_id: str, role: str, content: str) -> None:
        with self._lock:
            self._evict()
            key = (user_email, conversation_id)
            conv = self._data.setdefault(key, _Conv())
            if role == "user" and not conv.title:
                conv.title = content[:80]
            conv.messages.append(Message(role=role, content=content))
            conv.updated_at = time.time()

    def get_messages(self, user_email: str, conversation_id: str) -> list[Message]:
        with self._lock:
            conv = self._data.get((user_email, conversation_id))
            return list(conv.messages) if conv else []

    def list_conversations(self, user_email: str) -> list[ConversationMeta]:
        with self._lock:
            out = []
            for (email, cid), conv in self._data.items():
                if email != user_email:
                    continue
                out.append(ConversationMeta(
                    conversation_id=cid,
                    title=conv.title or "(sem título)",
                    updated_at=datetime.fromtimestamp(conv.updated_at, timezone.utc).isoformat(),
                    message_count=len(conv.messages),
                ))
            return sorted(out, key=lambda m: m.updated_at, reverse=True)

    def reset(self, user_email: str, conversation_id: str) -> None:
        with self._lock:
            self._data.pop((user_email, conversation_id), None)

    def get_genie_conversation_id(self, user_email: str, conversation_id: str) -> str | None:
        with self._lock:
            conv = self._data.get((user_email, conversation_id))
            return conv.genie_conversation_id if conv else None

    def set_genie_conversation_id(self, user_email: str, conversation_id: str, genie_id: str) -> None:
        with self._lock:
            conv = self._data.setdefault((user_email, conversation_id), _Conv())
            conv.genie_conversation_id = genie_id

    def save_graph(self, user_email: str, conversation_id: str, data: dict) -> None:
        with self._lock:
            conv = self._data.setdefault((user_email, conversation_id), _Conv())
            conv.graph = data
            conv.updated_at = time.time()

    def load_graph(self, user_email: str, conversation_id: str) -> dict | None:
        with self._lock:
            conv = self._data.get((user_email, conversation_id))
            return conv.graph if conv else None
