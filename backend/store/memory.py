"""ConversationStore em memória, com TTL. POC apenas — não sobrevive a restart do app."""
from __future__ import annotations

import threading
import time

from .base import Conversation, ConversationStore

DEFAULT_TTL_S = 60 * 60 * 4  # 4h


class InMemoryConversationStore(ConversationStore):
    def __init__(self, ttl_s: int = DEFAULT_TTL_S) -> None:
        self._ttl = ttl_s
        self._lock = threading.Lock()
        self._data: dict[tuple[str, str], Conversation] = {}

    def _key(self, user_email: str, conversation_id: str) -> tuple[str, str]:
        return (user_email, conversation_id)

    def _evict_expired(self) -> None:
        cutoff = time.time() - self._ttl
        stale = [k for k, c in self._data.items() if c.last_used < cutoff]
        for k in stale:
            del self._data[k]

    def get(self, user_email: str, conversation_id: str) -> Conversation:
        with self._lock:
            self._evict_expired()
            key = self._key(user_email, conversation_id)
            conv = self._data.get(key)
            if conv is None:
                conv = Conversation(user_email=user_email, conversation_id=conversation_id)
                self._data[key] = conv
            conv.touch()
            return conv

    def reset(self, user_email: str, conversation_id: str) -> None:
        with self._lock:
            self._data.pop(self._key(user_email, conversation_id), None)
