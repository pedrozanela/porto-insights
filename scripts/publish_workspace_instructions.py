"""Publica scripts/workspace_instructions.md em /Workspace/.genie_workspace_instructions.md.

O Genie One lê esse arquivo automaticamente e aplica as instruções a todo chat do workspace
(não a Genie Agents). Limite de 20.000 caracteres. Idempotente: sobrescreve (overwrite).
"""
from __future__ import annotations

import os
import pathlib

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat

PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "fevm-pzanela-classic-aws")
TARGET = "/Workspace/.genie_workspace_instructions.md"
MAX_CHARS = 20_000

SRC = pathlib.Path(__file__).with_name("workspace_instructions.md")


def main() -> None:
    content = SRC.read_text(encoding="utf-8")
    if len(content) > MAX_CHARS:
        raise SystemExit(f"instruções com {len(content)} caracteres; limite é {MAX_CHARS}")

    w = WorkspaceClient(profile=PROFILE)
    w.workspace.upload(
        path=TARGET,
        content=content.encode("utf-8"),
        format=ImportFormat.RAW,
        overwrite=True,
    )
    print(f"publicado {TARGET} ({len(content)} caracteres)")


if __name__ == "__main__":
    main()
