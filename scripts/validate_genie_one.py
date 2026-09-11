"""Valida o Genie One rodando as perguntas de dados da demo via MCP (com o token do usuário).

Para cada pergunta registra: resposta final, SQL executado, fontes citadas (deep links) e o
deep link "Explore in Databricks". A pergunta 2 é um follow-up da 1 (mesmo conversation_id),
exercitando a continuidade de conversa.

Uso:
    python validate_genie_one.py            # 1 execução, imprime relatório
    python validate_genie_one.py --runs 2   # 2 execuções (checa estabilidade)
    python validate_genie_one.py --md docs/discovery_genie.md   # grava fragmento markdown

Autentica pelo profile fevm-pzanela-classic-aws (o "usuário" em dev local sou eu).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from typing import Any

import httpx2
from databricks.sdk import WorkspaceClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

PROFILE = "fevm-pzanela-classic-aws"

# (pergunta, é_follow_up_da_anterior)
QUESTIONS: list[tuple[str, bool]] = [
    ("Como está a carteira de Capital de Giro PJ neste mês em relação à meta de originação?", False),
    ("E a inadimplência 90d, por segmento?", True),
    ("Qual o saldo total da carteira por produto no mês corrente?", False),
    ("Qual produto teve a maior originação neste mês?", False),
    ("A inadimplência de Capital de Giro PJ está acima do teto da meta neste mês?", False),
]

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def best_sql(query_items: list[dict[str, Any]]) -> str:
    """Escolhe a query de agregação relevante, ignorando SHOW CREATE / DESCRIBE de inspeção."""
    sqls = [(qi.get("sql") or "").strip() for qi in query_items if qi.get("sql")]
    agg = [s for s in sqls if s.upper().lstrip().startswith("SELECT") and "SHOW CREATE" not in s.upper()]
    return (agg[-1] if agg else (sqls[-1] if sqls else ""))


def token() -> str:
    return WorkspaceClient(profile=PROFILE).config.oauth_token().access_token


def host() -> str:
    return WorkspaceClient(profile=PROFILE).config.host.rstrip("/")


async def ask_and_poll(session: ClientSession, question: str, conversation_id: str | None) -> dict[str, Any]:
    args: dict[str, Any] = {"question": question}
    if conversation_id:
        args["conversation_id"] = conversation_id
    started = time.time()
    res = await session.call_tool("genie_ask", args)
    ask = _structured(res)
    cid = ask.get("conversation_id") or conversation_id
    rid = ask.get("response_id")

    steps: list[str] = []
    while time.time() - started < 260:
        await asyncio.sleep(3)
        poll = _structured(await session.call_tool(
            "genie_poll_response", {"conversation_id": cid, "response_id": rid}))
        for s in (poll.get("progress_steps") or []):
            if s not in steps:
                steps.append(s)
        if poll.get("status") and poll["status"] != "in_progress":
            body = _text(await session.call_tool(
                "genie_poll_response", {"conversation_id": cid, "response_id": rid}))
            return {
                "question": question, "conversation_id": cid, "response_id": rid,
                "status": poll["status"], "elapsed_s": round(time.time() - started, 1),
                "final_answer": poll.get("final_answer"), "deep_link": poll.get("deep_link"),
                "query_items": poll.get("query_items") or [], "progress_steps": steps,
                "links": LINK_RE.findall(body),
            }
    return {"question": question, "conversation_id": cid, "response_id": rid,
            "status": "timeout", "elapsed_s": round(time.time() - started, 1), "progress_steps": steps}


def _structured(res: Any) -> dict[str, Any]:
    sc = getattr(res, "structured_content", None)
    if sc:
        return sc
    txt = _text(res)
    if txt.strip().startswith("{"):
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            pass
    return {}


def _text(res: Any) -> str:
    return "\n".join(c.text for c in (res.content or []) if getattr(c, "text", None))


async def run_once() -> list[dict[str, Any]]:
    url = f"{host()}/api/2.0/mcp/genie"
    headers = {"Authorization": f"Bearer {token()}"}
    out: list[dict[str, Any]] = []
    async with httpx2.AsyncClient(headers=headers, timeout=300) as hc:
        async with streamable_http_client(url, http_client=hc) as st:
            async with ClientSession(st[0], st[1]) as session:
                await session.initialize()
                last_cid: str | None = None
                for question, is_follow in QUESTIONS:
                    r = await ask_and_poll(session, question, last_cid if is_follow else None)
                    last_cid = r.get("conversation_id")
                    out.append(r)
                    sql = best_sql(r.get("query_items") or [])
                    print(f"\n[{r['status']}] {question}  ({r.get('elapsed_s')}s)")
                    print("  resposta:", (r.get("final_answer") or "")[:200].replace("\n", " "))
                    if sql:
                        print("  sql:", " ".join(sql.split())[:160])
    return out


def to_markdown(runs: list[list[dict[str, Any]]]) -> str:
    lines = ["# Validação do Genie One — perguntas da demo\n"]
    for run_i, run in enumerate(runs, 1):
        lines.append(f"\n## Execução {run_i}\n")
        for i, r in enumerate(run, 1):
            sql = best_sql(r.get("query_items") or [])
            lines.append(f"### {i}. {r['question']}")
            lines.append(f"- **status:** {r['status']} ({r.get('elapsed_s')}s)")
            lines.append(f"- **resposta:** {(r.get('final_answer') or '').strip()}")
            if sql:
                lines.append(f"- **SQL:** `{' '.join(sql.split())}`")
            srcs = [f"[{t}]({u})" for t, u in r.get("links", []) if "explore/data" in u or "/genie" in u]
            if srcs:
                lines.append(f"- **fontes citadas:** {', '.join(srcs)}")
            if r.get("deep_link"):
                lines.append(f"- **Explore in Databricks:** {r['deep_link']}")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--md", type=str, default="")
    args = ap.parse_args()

    runs = [asyncio.run(run_once()) for _ in range(args.runs)]
    if args.md:
        import pathlib
        pathlib.Path(args.md).write_text(to_markdown(runs), encoding="utf-8")
        print(f"\nrelatório gravado em {args.md}")


if __name__ == "__main__":
    main()
