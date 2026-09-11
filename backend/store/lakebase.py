"""ConversationStore com backing em Lakebase (Postgres). Histórico real, persistente.

Schema `porto_insights` criado on-demand (idempotente). Nota de ownership: quem cria o schema
vira dono. Em produção o app (SP) deve criar/possuir o schema — por isso, ao deployar, garanta
que o SP roda a inicialização (ou conceda grants ao SP). Ver docs/prerequisites-checklist.md.
"""
from __future__ import annotations

import logging

from ..lakebase import LakebaseConnection
from .base import ConversationMeta, ConversationStore, Message

logger = logging.getLogger("porto_insights.store.lakebase")

SCHEMA = "porto_insights"

_DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE TABLE IF NOT EXISTS {SCHEMA}.conversations (
  user_email            TEXT NOT NULL,
  conversation_id       TEXT NOT NULL,
  title                 TEXT,
  genie_conversation_id TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_email, conversation_id)
);
CREATE TABLE IF NOT EXISTS {SCHEMA}.messages (
  id              BIGSERIAL PRIMARY KEY,
  user_email      TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  role            TEXT NOT NULL,
  content         TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_conv
  ON {SCHEMA}.messages (user_email, conversation_id, id);
"""


class LakebaseConversationStore(ConversationStore):
    def __init__(self, conn: LakebaseConnection) -> None:
        self._conn = conn
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn.connect() as c:
            c.execute(_DDL)
        logger.info("schema %s pronto no Lakebase", SCHEMA)

    def add_message(self, user_email: str, conversation_id: str, role: str, content: str) -> None:
        with self._conn.connect() as c:
            # Cria/atualiza a conversa. Título = primeira mensagem do usuário (só se ainda vazio).
            title = content[:80] if role == "user" else None
            c.execute(
                f"""INSERT INTO {SCHEMA}.conversations (user_email, conversation_id, title, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (user_email, conversation_id) DO UPDATE
                    SET updated_at = now(),
                        title = COALESCE({SCHEMA}.conversations.title, EXCLUDED.title)""",
                (user_email, conversation_id, title),
            )
            c.execute(
                f"""INSERT INTO {SCHEMA}.messages (user_email, conversation_id, role, content)
                    VALUES (%s, %s, %s, %s)""",
                (user_email, conversation_id, role, content),
            )

    def get_messages(self, user_email: str, conversation_id: str) -> list[Message]:
        with self._conn.connect() as c:
            rows = c.execute(
                f"""SELECT role, content FROM {SCHEMA}.messages
                    WHERE user_email = %s AND conversation_id = %s ORDER BY id""",
                (user_email, conversation_id),
            ).fetchall()
        return [Message(role=r, content=ct) for r, ct in rows]

    def list_conversations(self, user_email: str) -> list[ConversationMeta]:
        with self._conn.connect() as c:
            rows = c.execute(
                f"""SELECT co.conversation_id,
                           COALESCE(co.title, '(sem título)'),
                           co.updated_at,
                           (SELECT count(*) FROM {SCHEMA}.messages m
                             WHERE m.user_email = co.user_email
                               AND m.conversation_id = co.conversation_id)
                    FROM {SCHEMA}.conversations co
                    WHERE co.user_email = %s
                    ORDER BY co.updated_at DESC""",
                (user_email,),
            ).fetchall()
        return [
            ConversationMeta(conversation_id=cid, title=title,
                             updated_at=updated.isoformat(), message_count=int(count))
            for cid, title, updated, count in rows
        ]

    def reset(self, user_email: str, conversation_id: str) -> None:
        with self._conn.connect() as c:
            c.execute(f"DELETE FROM {SCHEMA}.messages WHERE user_email=%s AND conversation_id=%s",
                      (user_email, conversation_id))
            c.execute(f"DELETE FROM {SCHEMA}.conversations WHERE user_email=%s AND conversation_id=%s",
                      (user_email, conversation_id))

    def get_genie_conversation_id(self, user_email: str, conversation_id: str) -> str | None:
        with self._conn.connect() as c:
            row = c.execute(
                f"""SELECT genie_conversation_id FROM {SCHEMA}.conversations
                    WHERE user_email=%s AND conversation_id=%s""",
                (user_email, conversation_id),
            ).fetchone()
        return row[0] if row and row[0] else None

    def set_genie_conversation_id(self, user_email: str, conversation_id: str, genie_id: str) -> None:
        with self._conn.connect() as c:
            c.execute(
                f"""INSERT INTO {SCHEMA}.conversations (user_email, conversation_id, genie_conversation_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_email, conversation_id) DO UPDATE
                    SET genie_conversation_id = EXCLUDED.genie_conversation_id""",
                (user_email, conversation_id, genie_id),
            )
