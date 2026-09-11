#!/usr/bin/env python
"""Apply scripts/create_metric_views.sql, substituting ${FQ} for the target schema.

Idempotent (CREATE OR REPLACE). Statements are split on ';\\n' at top level, which is
safe here because the YAML bodies are wrapped in $$ ... $$.
"""
from __future__ import annotations

import pathlib
import re

from _sql import FQ, client, run

SQL_FILE = pathlib.Path(__file__).with_name("create_metric_views.sql")


def statements(text: str) -> list[str]:
    """Split on semicolons that sit outside a $$ ... $$ block."""
    out, buf, in_body = [], [], False
    for chunk in re.split(r"(\$\$)", text):
        if chunk == "$$":
            in_body = not in_body
            buf.append(chunk)
            continue
        if in_body:
            buf.append(chunk)
            continue
        parts = chunk.split(";")
        for part in parts[:-1]:
            buf.append(part)
            out.append("".join(buf))
            buf = []
        buf.append(parts[-1])
    tail = "".join(buf)
    if tail.strip():
        out.append(tail)

    cleaned: list[str] = []
    for stmt in out:
        lines = stmt.splitlines()
        while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
            lines.pop(0)      # drop leading comment/blank lines, keep the real statement
        body = "\n".join(lines).strip()
        if body:
            cleaned.append(body)
    return cleaned


def main() -> None:
    w = client()
    sql = SQL_FILE.read_text().replace("${FQ}", FQ)
    for stmt in statements(sql):
        name = re.search(r"CREATE OR REPLACE VIEW\s+(\S+)", stmt)
        print(f"  aplicando {name.group(1) if name else '?'} ...", flush=True)
        run(w, stmt)
    for view in ("mv_carteira_credito", "mv_contratos_credito"):
        rows = run(w, f"SELECT COUNT(1) FROM {FQ}.{view}")
        print(f"  {view}: OK ({rows[0][0]} linhas na base)")


if __name__ == "__main__":
    main()
