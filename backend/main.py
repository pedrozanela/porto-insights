"""Porto Insights — app FastAPI de processo único.

Serve a API em /api/* e o frontend (frontend/, sem build) como arquivos estáticos. CORS fechado:
o frontend é servido pelo mesmo host. Escuta na porta de DATABRICKS_APP_PORT (fallback 8000).
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel

from .agent.loop import run_turn
from .auth import UserContext, get_user_context
from .config import get_settings
from .graph.store import GraphStore
from .store.base import ConversationStore
from .store.memory import InMemoryConversationStore

from .tracing import init_tracing

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("porto_insights.main")
init_tracing(settings.mlflow_experiment_path)  # no-op se MLFLOW_EXPERIMENT_PATH vazio

app = FastAPI(title="Porto Insights", docs_url=None, redoc_url=None)


def _build_store() -> ConversationStore:
    """Lakebase (histórico persistente) se configurado; senão, memória (fallback dev)."""
    if settings.lakebase_endpoint:
        try:
            from .lakebase import LakebaseConnection
            from .store.lakebase import LakebaseConversationStore

            conn = LakebaseConnection(
                endpoint=settings.lakebase_endpoint,
                database=settings.lakebase_database,
                profile=settings.databricks_config_profile,
            )
            store = LakebaseConversationStore(conn)
            logger.info("histórico: Lakebase (%s)", settings.lakebase_endpoint)
            return store
        except Exception:  # noqa: BLE001
            logger.exception("falha ao inicializar Lakebase — caindo para store em memória")
    logger.info("histórico: em memória (não persiste)")
    return InMemoryConversationStore()


store = _build_store()
graph_store = GraphStore(persistence=store)  # grafo durável: persiste/restaura via o store


class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    model: str = ""


class PromoteRequest(BaseModel):
    conversation_id: str
    node_ids: list[str]

# Frontend SEM build: index.html + src/ (TSX, traduzido no navegador) + vendor/ servidos como estão.
FRONTEND = (Path(__file__).resolve().parent.parent / "frontend").resolve()


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
        "debug_graph": settings.debug_graph,
    }


@app.post("/api/chat")
def chat(req: ChatRequest, user: UserContext = Depends(get_user_context)) -> StreamingResponse:
    """Um turno de conversa, streamado como SSE. Toda chamada (modelo, Genie) usa o token do usuário."""
    generator = run_turn(user, settings, store, graph_store, req.conversation_id, req.message, req.model)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/graph/promote")
def promote_graph(req: PromoteRequest, user: UserContext = Depends(get_user_context)) -> dict:
    """Promoção manual de nós em staging (ex.: participante escolhido no painel de detalhe)."""
    from .graph.promotion import promote_ids, visible_delta
    from .graph.schema import delta_payload

    state = graph_store.get(user.email, req.conversation_id)
    newly = promote_ids(state, req.node_ids)
    vis_nodes, vis_edges = visible_delta(state)
    return delta_payload(vis_nodes, vis_edges, turn=0, promoted_node_ids=list(newly))


@app.get("/api/graph/{conversation_id}")
def get_graph(conversation_id: str, user: UserContext = Depends(get_user_context)) -> dict:
    """Grafo visível da conversa (nós + arestas), para reexibir ao reabrir do histórico.
    graph_store.get carrega do Lakebase se não estiver em memória (durável)."""
    from .graph.promotion import visible_delta
    from .graph.schema import delta_payload

    state = graph_store.get(user.email, conversation_id)
    vis_nodes, vis_edges = visible_delta(state)
    return delta_payload(vis_nodes, vis_edges, turn=0)


@app.get("/api/debug/graph/{conversation_id}")
def debug_graph(conversation_id: str, user: UserContext = Depends(get_user_context)) -> dict:
    """Item 5: retrato do grafo (visíveis + staging + motivos). Só quando DEBUG_GRAPH=true."""
    if not settings.debug_graph:
        raise HTTPException(status_code=404, detail="debug desabilitado")
    from .graph.promotion import debug_snapshot
    return debug_snapshot(graph_store.get(user.email, conversation_id))


@app.get("/api/conversations")
def list_conversations(user: UserContext = Depends(get_user_context)) -> dict:
    """Conversas do usuário, mais recentes primeiro (para a lista de histórico)."""
    convs = store.list_conversations(user.email)
    return {"conversations": [vars(c) for c in convs]}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str, user: UserContext = Depends(get_user_context)) -> dict:
    """Mensagens de uma conversa, para retomar de onde parou."""
    msgs = store.get_messages(user.email, conversation_id)
    return {"conversation_id": conversation_id, "messages": [vars(m) for m in msgs]}


@app.post("/api/conversations/{conversation_id}/reset")
def reset_conversation(conversation_id: str, user: UserContext = Depends(get_user_context)) -> dict:
    """Apaga a conversa (mensagens + fio do Genie + grafo). Usado pelo botão 'Apagar'."""
    store.reset(user.email, conversation_id)
    graph_store.reset(user.email, conversation_id)
    return {"status": "ok"}


# --- Arquivos estáticos do frontend (registrado por último; não intercepta /api/*) ---
# no-cache = o navegador revalida a cada carga (ETag → 304 se nada mudou). Sem isso, como os
# arquivos têm nome fixo (não há build com hash), uma edição podia demorar horas para aparecer.
NO_CACHE = {"Cache-Control": "no-cache"}


SOURCE_EXTS = (".tsx", ".ts", ".jsx", ".js")  # ordem de resolução de import sem extensão
STATIC_DIRS = {"src", "vendor", "public"}       # arquivo inexistente aqui = 404 (não o index.html)


@app.get("/{full_path:path}")
def frontend(full_path: str) -> Response:
    """Serve o arquivo pedido de frontend/; qualquer outra rota não-API devolve o index.html."""
    candidate = (FRONTEND / full_path).resolve()
    if full_path and candidate.is_relative_to(FRONTEND):
        if candidate.is_file():
            return FileResponse(candidate, headers=NO_CACHE)
        # import sem extensão (`import App from "./App"`): redireciona para o arquivo real, como
        # faria um bundler — assim o código TSX fica igual ao de um projeto React comum.
        if full_path.startswith("src/") and not candidate.suffix:
            for base in (candidate, candidate / "index"):
                for ext in SOURCE_EXTS:
                    if base.with_name(base.name + ext).is_file():
                        target = "/" + str(base.relative_to(FRONTEND)) + ext
                        return RedirectResponse(target, status_code=307, headers=NO_CACHE)
        if full_path.split("/", 1)[0] in STATIC_DIRS:
            return Response(status_code=404, headers=NO_CACHE)
    return FileResponse(FRONTEND / "index.html", headers=NO_CACHE)
