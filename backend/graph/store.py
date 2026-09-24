"""Estado do grafo por conversa. Em memória durante a sessão, com persistência opcional
(Lakebase via ConversationStore) para reexibir o grafo ao reabrir a conversa — inclusive
depois de o app reiniciar."""
from __future__ import annotations

import logging
import threading
from typing import Protocol

from .schema import GraphState

logger = logging.getLogger("porto_insights.graph.store")


class _GraphPersistence(Protocol):
    def save_graph(self, user_email: str, conversation_id: str, data: dict) -> None: ...
    def load_graph(self, user_email: str, conversation_id: str) -> dict | None: ...


class GraphStore:
    def __init__(self, persistence: _GraphPersistence | None = None) -> None:
        self._lock = threading.Lock()
        self._states: dict[tuple[str, str], GraphState] = {}
        self._persistence = persistence  # ConversationStore (save_graph/load_graph); None = só memória

    def get(self, user_email: str, conversation_id: str) -> GraphState:
        key = (user_email, conversation_id)
        with self._lock:
            st = self._states.get(key)
            if st is not None:
                return st
        # Miss frio: tenta carregar o grafo persistido FORA do lock (pode tocar o banco).
        loaded = self._load(user_email, conversation_id) or GraphState()
        with self._lock:
            st = self._states.get(key)  # outro thread pode ter criado nesse meio tempo
            if st is None:
                self._states[key] = loaded
                st = loaded
            return st

    def _load(self, user_email: str, conversation_id: str) -> GraphState | None:
        if self._persistence is None:
            return None
        try:
            data = self._persistence.load_graph(user_email, conversation_id)
            return GraphState.from_dict(data) if data else None
        except Exception:  # noqa: BLE001 — persistência é best-effort
            logger.warning("falha ao carregar grafo persistido", exc_info=True)
            return None

    def save(self, user_email: str, conversation_id: str) -> None:
        """Persiste o estado atual do grafo da conversa (best-effort). Chamado ao fim do turno."""
        if self._persistence is None:
            return
        with self._lock:
            st = self._states.get((user_email, conversation_id))
        if st is None:
            return
        try:
            self._persistence.save_graph(user_email, conversation_id, st.to_dict())
        except Exception:  # noqa: BLE001
            logger.warning("falha ao salvar grafo", exc_info=True)

    def reset(self, user_email: str, conversation_id: str) -> None:
        with self._lock:
            self._states.pop((user_email, conversation_id), None)
        # A linha persistida é apagada pelo store.reset() (endpoint /reset).
