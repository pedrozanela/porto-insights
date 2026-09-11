"""Porto Insights — app FastAPI de processo único.

Serve a API em /api/* e o build do frontend (dist/) como arquivos estáticos. CORS fechado:
o frontend é servido pelo mesmo host. Escuta na porta de DATABRICKS_APP_PORT (fallback 8000).
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import UserContext, get_user_context
from .config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="Porto Insights", docs_url=None, redoc_url=None)

# dist/ do frontend (buildado antes do deploy). Em dev antes do 1º build pode não existir.
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.get("/api/health")
def health() -> dict:
    """Health check — usa a identidade do service principal do app, não do usuário."""
    return {"status": "ok", "service": "porto-insights"}


@app.get("/api/me")
def me(user: UserContext = Depends(get_user_context)) -> dict:
    """Identidade do usuário logado e configuração visível ao frontend (sem segredos)."""
    return {
        "email": user.email,
        "is_local_dev": user.is_local_dev,
        "models": [{"name": e.name, "label": e.label} for e in settings.endpoints],
        "default_model": settings.default_endpoint,
        "google_services": settings.google_services,
    }


# --- Arquivos estáticos do frontend (registrado por último; não intercepta /api/*) ---
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        """Fallback SPA: qualquer rota não-API devolve o index.html do React."""
        candidate = DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    def no_build() -> dict:
        return {"detail": "frontend não buildado — rode scripts/build_frontend.sh"}
