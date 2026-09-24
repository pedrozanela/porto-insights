"""MLflow Tracing do loop agentic (observabilidade por turno).

Desligado por padrão: só liga se MLFLOW_EXPERIMENT_PATH estiver configurado. Best-effort —
NENHUMA falha de tracing pode quebrar o request (tudo em try/except).

Quando ligado, cada turno do chat vira UM trace:
  chat.turn (raiz, duração = latência total)
  ├─ LLM chat.completions   (autolog do OpenAI SDK: tokens, latência, prompt/resposta)
  ├─ TOOL genie__ask        (span manual: ciclo do Genie)
  ├─ TOOL <google>          (span manual por chamada MCP)
  └─ LLM linker             (autolog)
O trace é marcado com session=conversation_id e user=email → filtrável por chat.

Governança: o trace captura pergunta e entradas/saídas do modelo (dados sensíveis). Um
SpanProcessor redige PII (email, telefone, CPF/CNPJ, cartão) antes de persistir, e o
experimento deve ter acesso restrito ao time.
"""
from __future__ import annotations

import contextlib
import logging
import re
from typing import Any, Iterator

logger = logging.getLogger("porto_insights.tracing")

_enabled = False

# Padrões de PII redigidos das entradas/saídas dos spans (defesa em profundidade).
_PII = {
    "EMAIL": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "CPF": re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "CNPJ": re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    "CARTAO": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
    "TELEFONE": re.compile(r"\b(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b"),
}


def _redact_str(text: str) -> str:
    for tag, pat in _PII.items():
        text = pat.sub(f"[{tag}]", text)
    return text


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_str(value)
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _pii_filter(span) -> None:
    """Span processor (API mlflow.tracing.configure): redige PII de inputs/outputs antes do export."""
    try:
        if span.inputs:
            span.set_inputs(_redact(span.inputs))
        if span.outputs:
            span.set_outputs(_redact(span.outputs))
    except Exception:  # noqa: BLE001
        pass


def init_tracing(experiment_path: str) -> None:
    global _enabled
    if not experiment_path:
        return
    try:
        import mlflow

        mlflow.set_tracking_uri("databricks")
        mlflow.set_experiment(experiment_path)
        mlflow.openai.autolog()  # traça o AsyncOpenAI (turnos do modelo + linker semântico)
        _enabled = True
        logger.info("MLflow tracing habilitado em %s", experiment_path)
    except Exception:  # noqa: BLE001
        logger.warning("MLflow indisponível — tracing desligado", exc_info=True)
        return

    # Redação de PII — separada, pra NUNCA derrubar o tracing se a API mudar de versão.
    try:
        import mlflow
        mlflow.tracing.configure(span_processors=[_pii_filter])
    except Exception:  # noqa: BLE001
        logger.warning("redação de PII indisponível nesta versão do MLflow — tracing segue ligado")


def is_enabled() -> bool:
    return _enabled


def set_turn_metrics(*, graph_nodes: int, timing: dict[str, Any] | None) -> None:
    """Anota nº de nós do grafo + latências (total/genie/linker) no span raiz do turno."""
    if not _enabled:
        return
    try:
        import mlflow
        span = mlflow.get_current_active_span()
        if span is not None:
            span.set_attributes({"graph_nodes": graph_nodes, **(timing or {})})
    except Exception:  # noqa: BLE001
        logger.debug("falha ao anotar métricas do turno", exc_info=True)


@contextlib.contextmanager
def turn_span(*, question: str, model: str, conversation_id: str, user_email: str) -> Iterator[Any]:
    """Span raiz do turno. Filhos (LLM via autolog, tools) aninham por contexto. No-op se OFF."""
    if not _enabled:
        yield None
        return
    try:
        import mlflow
        from mlflow.entities import SpanType
        cm = mlflow.start_span(name="chat.turn", span_type=SpanType.AGENT)
    except Exception:  # noqa: BLE001
        logger.debug("falha ao abrir turn_span", exc_info=True)
        yield None
        return
    with cm as span:
        try:
            span.set_inputs({"question": question, "model": model})
            mlflow.update_current_trace(metadata={
                "mlflow.trace.user": user_email or "anon",
                "mlflow.trace.session": conversation_id or "default",
            })
        except Exception:  # noqa: BLE001
            pass
        yield span


@contextlib.contextmanager
def tool_span(name: str, *, inputs: dict[str, Any] | None = None) -> Iterator[Any]:
    """Span de uma chamada de ferramenta (Genie/Google). No-op se OFF."""
    if not _enabled:
        yield None
        return
    try:
        import mlflow
        from mlflow.entities import SpanType
        cm = mlflow.start_span(name=name, span_type=SpanType.TOOL)
    except Exception:  # noqa: BLE001
        logger.debug("falha ao abrir tool_span %s", name, exc_info=True)
        yield None
        return
    with cm as span:
        try:
            if inputs:
                span.set_inputs(inputs)
        except Exception:  # noqa: BLE001
            pass
        yield span
