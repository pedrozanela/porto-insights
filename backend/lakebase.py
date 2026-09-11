"""Conexão com o Lakebase (Postgres) para o histórico de chat.

O histórico é infraestrutura do app, não dado governado por UC — por isso a conexão usa a
identidade do PRÓPRIO app (service principal em produção; profile do CLI em dev local), não o
token OBO do usuário. O isolamento por usuário é garantido nas queries (WHERE user_email = ...).

Token OAuth do Postgres expira em 1h: cacheamos e regeneramos a cada ~40 min. Conexão por
operação (o volume do histórico é baixo). Fallback de DNS para o gotcha de hostname longo no macOS.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from contextlib import contextmanager
from typing import Iterator

import psycopg
from databricks.sdk import WorkspaceClient

logger = logging.getLogger("porto_insights.lakebase")

_TOKEN_TTL_S = 40 * 60  # regenera antes da expiração de 1h


class LakebaseConnection:
    def __init__(self, endpoint: str, database: str, profile: str) -> None:
        self._endpoint = endpoint
        self._database = database
        self._profile = profile
        self._lock = threading.Lock()
        self._wsc: WorkspaceClient | None = None
        self._host: str | None = None
        self._user: str | None = None
        self._token: str | None = None
        self._token_at: float = 0.0

    def _app_client(self) -> WorkspaceClient:
        # Produção (Databricks Apps injeta DATABRICKS_APP_PORT): identidade do SP via default chain.
        # Dev local: profile do CLI.
        if self._wsc is None:
            if os.environ.get("DATABRICKS_APP_PORT"):
                self._wsc = WorkspaceClient()
            else:
                self._wsc = WorkspaceClient(profile=self._profile)
        return self._wsc

    def _refresh(self) -> None:
        w = self._app_client()
        if self._host is None:
            self._host = w.postgres.get_endpoint(name=self._endpoint).status.hosts.host
            self._user = w.current_user.me().user_name
        self._token = w.postgres.generate_database_credential(endpoint=self._endpoint).token
        self._token_at = time.time()

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        with self._lock:
            if self._token is None or (time.time() - self._token_at) > _TOKEN_TTL_S:
                self._refresh()
            host, user, token = self._host, self._user, self._token

        kwargs = dict(
            host=host, dbname=self._database, user=user, password=token,
            sslmode="require", connect_timeout=15,
        )
        # Gotcha macOS: socket.getaddrinfo pode falhar com hostname longo; passa hostaddr.
        try:
            kwargs["hostaddr"] = socket.gethostbyname(host)  # type: ignore[arg-type]
        except OSError:
            pass

        conn = psycopg.connect(**kwargs)  # type: ignore[arg-type]
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
