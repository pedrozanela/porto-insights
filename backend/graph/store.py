"""Estado do grafo por conversa, em memória (POC). Acumulativo enquanto a conversa existe."""
from __future__ import annotations

import threading

from .schema import GraphState


class GraphStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[tuple[str, str], GraphState] = {}

    def get(self, user_email: str, conversation_id: str) -> GraphState:
        with self._lock:
            key = (user_email, conversation_id)
            st = self._states.get(key)
            if st is None:
                st = GraphState()
                self._states[key] = st
            return st

    def reset(self, user_email: str, conversation_id: str) -> None:
        with self._lock:
            self._states.pop((user_email, conversation_id), None)
