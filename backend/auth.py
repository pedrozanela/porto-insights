"""Autenticação on-behalf-of-user (OBO).

Em produção, o Databricks Apps entrega o token do usuário no header
`x-forwarded-access-token`. Toda chamada a serviços Databricks (Model Serving, Genie One MCP,
MCP Services) usa esse token — nunca o service principal do app.

Em dev local, quando o header não existe, caímos para o profile do CLI
(fevm-pzanela-classic-aws) e o "usuário" é o dono do profile (eu).

Os WorkspaceClient não são cacheados entre usuários: um por request.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from databricks.sdk import WorkspaceClient
from fastapi import Request

from .config import get_settings

logger = logging.getLogger("porto_insights.auth")

ACCESS_TOKEN_HEADER = "x-forwarded-access-token"
EMAIL_HEADER = "x-forwarded-email"
USER_HEADER = "x-forwarded-user"


@dataclass
class UserContext:
    """Identidade + credenciais de um request. `token` é o bearer para MCP e serving."""

    token: str
    email: str
    is_local_dev: bool
    _wsc: WorkspaceClient

    @property
    def wsc(self) -> WorkspaceClient:
        return self._wsc


def _build_from_profile() -> tuple[str, str, WorkspaceClient]:
    """Dev local: usa o profile do CLI. Token OAuth extraído do profile."""
    s = get_settings()
    wsc = WorkspaceClient(profile=s.databricks_config_profile)
    token = wsc.config.oauth_token().access_token
    email = wsc.current_user.me().user_name or "dev-local"
    return token, email, wsc


def get_user_context(request: Request) -> UserContext:
    """Dependency do FastAPI: resolve a identidade/credencial do request."""
    s = get_settings()
    token = request.headers.get(ACCESS_TOKEN_HEADER)

    if token:
        # Produção: OBO. auth_type="pat" força o uso do token do usuário e ignora o OAuth do
        # service principal do app (DATABRICKS_CLIENT_ID/SECRET no ambiente) — senão o SDK
        # recusa com "more than one authorization method configured: oauth and pat".
        wsc = WorkspaceClient(host=s.host_url, token=token, auth_type="pat")
        email = request.headers.get(EMAIL_HEADER) or request.headers.get(USER_HEADER) or ""
        if not email:
            try:
                email = wsc.current_user.me().user_name or ""
            except Exception:  # noqa: BLE001
                email = ""
        return UserContext(token=token, email=email, is_local_dev=False, _wsc=wsc)

    # Dev local
    token, email, wsc = _build_from_profile()
    logger.info("sem %s — usando profile do CLI (dev local, usuário=%s)", ACCESS_TOKEN_HEADER, email)
    return UserContext(token=token, email=email, is_local_dev=True, _wsc=wsc)
