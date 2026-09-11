"""Shared helper: run SQL on a Databricks SQL warehouse via the Statement Execution API."""
from __future__ import annotations

import os
import time
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import ExecuteStatementRequestOnWaitTimeout, StatementState

PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "fevm-pzanela-classic-aws")
WAREHOUSE_ID = os.environ.get("SQL_WAREHOUSE_ID", "848374d85d2bad86")
CATALOG = os.environ.get("PORTO_CATALOG", "pzanela_classic_aws_catalog")
SCHEMA = os.environ.get("PORTO_SCHEMA", "porto_insights")
FQ = f"{CATALOG}.{SCHEMA}"

_TERMINAL = {StatementState.SUCCEEDED, StatementState.FAILED, StatementState.CANCELED, StatementState.CLOSED}


def client() -> WorkspaceClient:
    return WorkspaceClient(profile=PROFILE)


def run(w: WorkspaceClient, sql: str, *, timeout_s: int = 300) -> list[list[Any]]:
    """Execute one statement, wait for a terminal state, return rows (empty for DDL)."""
    resp = w.statement_execution.execute_statement(
        statement=sql, warehouse_id=WAREHOUSE_ID, wait_timeout="30s",
        on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CONTINUE,
    )
    deadline = time.time() + timeout_s
    while resp.status and resp.status.state not in _TERMINAL:
        if time.time() > deadline:
            raise TimeoutError(f"statement {resp.statement_id} still {resp.status.state} after {timeout_s}s")
        time.sleep(2)
        resp = w.statement_execution.get_statement(resp.statement_id)

    state = resp.status.state if resp.status else None
    if state is not StatementState.SUCCEEDED:
        detail = resp.status.error.message if (resp.status and resp.status.error) else "sem detalhe"
        raise RuntimeError(f"SQL falhou ({state}): {detail}\n--- statement ---\n{sql[:800]}")
    return (resp.result.data_array or []) if resp.result else []


def scalar(w: WorkspaceClient, sql: str) -> Any:
    rows = run(w, sql)
    return rows[0][0] if rows and rows[0] else None
