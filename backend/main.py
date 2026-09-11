"""Porto Insights — app FastAPI de processo único.

Serve a API em /api/* e o build do frontend (dist/) como arquivos estáticos. CORS fechado:
o frontend é servido pelo mesmo host. Escuta na porta de DATABRICKS_APP_PORT (fallback 8000).
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent.loop import run_turn
from .auth import UserContext, get_user_context
from .config import get_settings
from .store.memory import InMemoryConversationStore

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="Porto Insights", docs_url=None, redoc_url=None)

# POC: store em memória por sessão, atrás da interface ConversationStore (troca por Lakebase depois).
store = InMemoryConversationStore()


class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    model: str = ""

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


@app.post("/api/chat")
def chat(req: ChatRequest, user: UserContext = Depends(get_user_context)) -> StreamingResponse:
    """Um turno de conversa, streamado como SSE. Toda chamada de modelo usa o token do usuário."""
    generator = run_turn(user, settings, store, req.conversation_id, req.message, req.model)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/conversations/{conversation_id}/reset")
def reset_conversation(conversation_id: str, user: UserContext = Depends(get_user_context)) -> dict:
    """Limpa a conversa (mensagens + fio do Genie). Usado pelo botão 'Nova conversa'."""
    store.reset(user.email, conversation_id)
    return {"status": "ok"}


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
