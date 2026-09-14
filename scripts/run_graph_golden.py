#!/usr/bin/env python
"""Roda o conjunto de perguntas-ouro do grafo contra o backend LOCAL e gera um relatório.

Pré-requisitos:
  - backend local no ar com DEBUG_GRAPH=true (usa seu perfil/token):
        DEBUG_GRAPH=true .venv/bin/uvicorn backend.main:app --port 8000
  - você conectado ao Google (Gmail/Calendar/Drive) e com acesso ao Genie/UC.

Uso:
    python scripts/run_graph_golden.py [--base-url http://localhost:8000] [--model <nome>]

Uma conversa nova por caso; consome o SSE de /api/chat, lê o grafo final em
/api/debug/graph/{id} e escreve docs/screenshots/golden-<timestamp>.md. Expectativas são
ESTRUTURAIS (a agenda real muda): checa formas, não valores.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

import httpx

EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", re.I)

CASES = [
    ("a", ["Onde encontro o transcript da reunião do dia 10/09 de manhã com o Lucca da Porto?"]),
    ("b", ["O que tenho com Fernando Custodio esta semana?"]),
    ("c", ["Qual é a reunião do Comitê de Crédito PJ e quem participa? Traga a pauta."]),
    ("d", ["Como está a carteira de Capital de Giro PJ neste mês em relação à meta?"]),
    ("e", ["Qual é a reunião do Comitê de Crédito PJ e quem participa? Traga a pauta.",
           "Como está a carteira de Capital de Giro PJ neste mês em relação à meta?",
           "Isso tem relação com alguma reunião da minha agenda?"]),
    ("f", ["Quais emails recebi sobre o Comitê de Crédito PJ?"]),
    ("g", ["Quem organiza o BR SA Tech Weekly Meeting?"]),
    ("h", ["O que é inadimplência 90 dias?"]),
]


def _norm(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s or "")
    no_accent = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", no_accent.lower()).split())


def run_turn(client: httpx.Client, base: str, cid: str, message: str, model: str) -> dict:
    """Envia um turno; devolve {answer, trace, suggestions}."""
    answer, trace, suggestions = [], [], []
    with client.stream("POST", f"{base}/api/chat",
                        json={"conversation_id": cid, "message": message, "model": model}) as r:
        for line in r.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                evt = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            t = evt.get("type")
            if t == "token":
                answer.append(evt.get("text", ""))
            elif t == "tool_progress":
                trace.append(evt.get("step", ""))
            elif t == "suggestions":
                suggestions = evt.get("suggestions", [])
            elif t in ("done", "error"):
                break
    return {"answer": "".join(answer), "trace": trace, "suggestions": suggestions}


def edges_of(dbg: dict, nid: str, *, visible_only=True):
    out = []
    for e in dbg["edges"]:
        if visible_only and not e["visible"]:
            continue
        if e["source"] == nid:
            out.append((e["type"], e["target"]))
        elif e["target"] == nid:
            out.append((e["type"], e["source"]))
    return out


def universal_checks(dbg: dict, suggestions: list) -> list[tuple[str, bool, str]]:
    vis = dbg["visible"]
    vis_ids = {n["id"] for n in vis}
    checks = []

    # zero órfãos
    orphans = []
    for n in vis:
        if n["type"] in ("genie_answer", "data_asset"):
            continue
        if len(vis) <= 1:
            break
        if not edges_of(dbg, n["id"]):
            orphans.append(n["label"])
    checks.append(("zero órfãos", not orphans, f"órfãos: {orphans}" if orphans else "ok"))

    # arestas fechadas (as visíveis já têm as duas pontas visíveis por construção)
    bad = [e for e in dbg["edges"] if e["visible"] and (e["source"] not in vis_ids or e["target"] not in vis_ids)]
    checks.append(("arestas fechadas", not bad, "ok" if not bad else f"{len(bad)} abertas"))

    # sem rótulo em formato de email
    emailish = [n["label"] for n in vis if EMAIL_RE.search(n["label"] or "")]
    checks.append(("sem rótulo email", not emailish, f"{emailish}" if emailish else "ok"))

    # sem rótulo (documento)
    docish = [n["label"] for n in vis if n["label"] == "(documento)"]
    checks.append(("sem '(documento)'", not docish, f"{docish}" if docish else "ok"))

    # sugestões só sobre visíveis
    bad_sugg = [s.get("node_id") for s in suggestions if s.get("node_id") and s.get("node_id") not in vis_ids]
    checks.append(("sugestões sobre visíveis", not bad_sugg, f"{bad_sugg}" if bad_sugg else "ok"))
    return checks


def case_checks(case_id: str, dbg: dict) -> list[tuple[str, bool, str]]:
    vis = dbg["visible"]
    events = [n for n in vis if n["type"] == "calendar_event"]
    persons = [n for n in vis if n["type"] == "person"]
    drives = [n for n in vis if n["type"] == "drive_file"]
    emails = [n for n in vis if n["type"] == "email"]
    genie = [n for n in vis if n["type"] == "genie_answer"]
    assets = [n for n in vis if n["type"] == "data_asset"]
    c = []

    def linked(a_id, b_id, types=None):
        return any(t for (t, o) in edges_of(dbg, a_id) if o == b_id and (types is None or t in types))

    if case_id == "a":
        c.append(("exatamente 1 evento", len(events) == 1, f"{len(events)} eventos"))
        lucca = [p for p in persons if "lucca" in _norm(p["label"])]
        c.append(("Lucca por participou", bool(lucca) and any(linked(events[0]["id"], p["id"], {"attendee", "organizer"}) for p in lucca) if events else False,
                  f"lucca={[p['label'] for p in lucca]}"))
        c.append(("≥1 doc ligado ao evento", any(linked(ev["id"], d["id"]) for ev in events for d in drives),
                  f"{len(drives)} docs"))
        c.append(("≤ 6 nós visíveis", len(vis) <= 6, f"{len(vis)} nós"))
    elif case_id == "b":
        fer = [p for p in persons if "fernando" in _norm(p["label"])]
        c.append(("Fernando visível", bool(fer), f"{[p['label'] for p in fer]}"))
        all_linked = all(any(linked(ev["id"], p["id"], {"attendee", "organizer"}) for p in fer) for ev in events) if (events and fer) else False
        c.append(("Fernando ligado a cada evento", all_linked, f"{len(events)} eventos"))
        plusn = [ev for ev in events if (ev.get("staged_participants") or 0) > 0]
        c.append(("algum evento com +N", bool(plusn), f"{[(e['label'], e.get('staged_participants')) for e in plusn]}"))
    elif case_id == "c":
        c.append(("≥1 evento", bool(events), f"{len(events)}"))
        c.append(("pessoas visíveis", len(persons) >= 1, f"{len(persons)}"))
        c.append(("doc por anexo", any(linked(ev["id"], d["id"], {"attached"}) for ev in events for d in drives),
                  f"{len(drives)} docs"))
    elif case_id == "d":
        c.append(("genie_answer + data_asset", bool(genie) and bool(assets), f"g={len(genie)} a={len(assets)}"))
        c.append(("cites entre eles", any(linked(g["id"], a["id"], {"cites"}) for g in genie for a in assets), ""))
        c.append(("nada de agenda/email/pessoa", not events and not emails and not persons,
                  f"ev={len(events)} em={len(emails)} p={len(persons)}"))
    elif case_id == "e":
        rel = any(e["visible"] and e["type"] == "related_to" and
                  {dbg_type(dbg, e['source']), dbg_type(dbg, e['target'])} == {"genie_answer", "calendar_event"}
                  for e in dbg["edges"])
        c.append(("related_to genie↔evento", rel, ""))
    elif case_id == "f":
        c.append(("≥1 email visível", bool(emails), f"{len(emails)}"))
        c.append(("email ligado a remetente", any(linked(em["id"], p["id"], {"sender"}) for em in emails for p in persons),
                  ""))
    elif case_id == "g":
        c.append(("1 evento", len(events) == 1, f"{len(events)}"))
        c.append(("organizador visível", any(linked(ev["id"], p["id"], {"organizer"}) for ev in events for p in persons), ""))
        c.append(("demais em +N", any((ev.get("staged_participants") or 0) > 0 for ev in events), ""))
    elif case_id == "h":
        c.append(("grafo não muda (0 visíveis)", len(vis) == 0, f"{len(vis)} nós visíveis"))
    return c


def dbg_type(dbg: dict, nid: str) -> str:
    for n in dbg["visible"] + dbg["staging"]:
        if n["id"] == nid:
            return n["type"]
    return "?"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--model", default="")
    ap.add_argument("--only", default="", help="ids de casos separados por vírgula (ex.: a,g)")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    only = {c.strip() for c in args.only.split(",") if c.strip()}
    cases = [c for c in CASES if not only or c[0] in only]

    with httpx.Client(timeout=400) as client:
        me = client.get(f"{base}/api/me").json()
        model = args.model or me.get("default_model", "")
        if not me.get("debug_graph"):
            print("AVISO: DEBUG_GRAPH não está ligado no backend — /api/debug/graph vai falhar.")

        report = [f"# Golden set do grafo — {datetime.now().isoformat(timespec='seconds')}",
                  f"\nBackend: `{base}` · modelo: `{model}` · usuário: `{me.get('email')}`\n"]
        summary = []

        for case_id, turns in cases:
            cid = "golden-" + case_id + "-" + uuid.uuid4().hex[:8]
            print(f"\n=== caso {case_id} ({cid}) ===")
            last = {"answer": "", "trace": [], "suggestions": []}
            for i, q in enumerate(turns):
                print(f"  turno {i+1}: {q}")
                last = run_turn(client, base, cid, q, model)
            try:
                dbg = client.get(f"{base}/api/debug/graph/{cid}").json()
            except Exception as e:  # noqa: BLE001
                report.append(f"\n## Caso {case_id}\n\nFALHA ao ler debug graph: {e}\n")
                continue

            uni = universal_checks(dbg, last["suggestions"])
            spec = case_checks(case_id, dbg)
            all_ok = all(ok for _, ok, _ in uni + spec)
            summary.append((case_id, all_ok))

            report.append(f"\n## Caso {case_id} — {'✅' if all_ok else '❌'}\n")
            report.append("**Perguntas:** " + " ⇢ ".join(f"“{t}”" for t in turns))
            report.append(f"\n**Resposta (fim):** {last['answer'][-400:].strip() or '(vazia)'}")
            if last["trace"]:
                report.append("\n**Trace:** " + " · ".join(last["trace"][-6:]))
            report.append(f"\n**Visíveis ({dbg['counts']['visible']}):** "
                          + ", ".join(f"{n['label']} [{n['type']}]" for n in dbg["visible"]) or "—")
            vis_edges = [e for e in dbg["edges"] if e["visible"]]
            report.append(f"\n**Arestas visíveis ({len(vis_edges)}):** "
                          + ", ".join(f"{e['type']}" for e in vis_edges) or "—")
            report.append("\n**Checagens:**")
            for name, ok, detail in spec + uni:
                report.append(f"- {'✅' if ok else '❌'} {name} — {detail}")
            report.append(f"\n**Staging ({dbg['counts']['staging']}):**")
            for n in dbg["staging"][:40]:
                report.append(f"- {n['label']} [{n['type']}] — {n['reason'] or '—'}")

        head = "## Resumo\n\n" + " · ".join(f"{cid}:{'✅' if ok else '❌'}" for cid, ok in summary) + "\n"
        report.insert(2, head)

        out = Path("docs/screenshots") / f"golden-{datetime.now():%Y%m%d-%H%M%S}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(report), encoding="utf-8")
        print(f"\nRelatório: {out}")
        print("Resumo:", " ".join(f"{cid}:{'ok' if ok else 'X'}" for cid, ok in summary))


if __name__ == "__main__":
    main()
