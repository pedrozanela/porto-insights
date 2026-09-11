"""MLflow Tracing opcional do loop agentic.

Desligado por padrão: só liga se MLFLOW_EXPERIMENT_PATH estiver configurado. Best-effort —
nenhuma falha de tracing pode quebrar o request. Registra um trace por turno com atributos
(modelo, pergunta, nº de tool calls, nº de nós do grafo). Versão enxuta; pode evoluir para
spans por tool/poll depois.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("porto_insights.tracing")

_enabled = False


def init_tracing(experiment_path: str) -> None:
    global _enabled
    if not experiment_path:
        return
    try:
        import mlflow

        mlflow.set_experiment(experiment_path)
        _enabled = True
        logger.info("MLflow tracing habilitado em %s", experiment_path)
    except Exception:  # noqa: BLE001
        logger.warning("MLflow indisponível — tracing desligado", exc_info=True)


def is_enabled() -> bool:
    return _enabled


def trace_turn(*, model: str, question: str, tool_calls: int, graph_nodes: int) -> None:
    """Registra um trace resumido do turno. No-op se desligado."""
    if not _enabled:
        return
    try:
        import mlflow

        with mlflow.start_span(name="porto_insights.turn") as span:
            span.set_inputs({"question": question, "model": model})
            span.set_attributes({"tool_calls": tool_calls, "graph_nodes": graph_nodes})
    except Exception:  # noqa: BLE001
        logger.debug("falha ao registrar trace do turno", exc_info=True)
