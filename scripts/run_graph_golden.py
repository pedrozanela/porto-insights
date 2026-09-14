#!/usr/bin/env python
"""Roda o conjunto de perguntas-ouro do grafo contra o backend LOCAL e gera um relatório.

Pré-requisitos:
  - backend local no ar com DEBUG_GRAPH=true (usa seu perfil/token):
        DEBUG_GRAPH=true .venv/bin/uvicorn backend.main:app --port 8000
  - você conectado ao Google (Gmail/Calendar/Drive) e com acesso ao Genie/UC.

Uso:
    python scripts/run_graph_golden.py [--base-url http://localhost:8000]
                                       [--models m1,m2] [--only a,g]

Uma conversa nova por caso e POR MODELO; consome o SSE de /api/chat (inclui o timing do evento
`done`), lê o grafo final em /api/debug/graph/{id} e escreve docs/screenshots/golden-<ts>.md com
uma TABELA por modelo (caso, passou?, critérios falhos, nós vis/staging, duração, tool calls,
linker ok?, screenshot) + latência p50/p95 por modelo. Expectativas ESTRUTURAIS (a agenda muda).
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
P95_BUDGET_MS = 45_000  # acima disso: avisar, não otimizar por conta própria

# screenshots commitados por caso (quando existirem)
SCREENSHOTS = {
    "a": "golden-a-lucca-10-09.png",
    "b": "golden-b-fernando-semana.png",
    "e": "golden-e-relacao-genie-agenda.png",
}

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


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def run_turn(client: httpx.Client, base: str, cid: str, message: str, model: str) -> dict:
    """Envia um turno; devolve {answer, trace, suggestions, timing}."""
    answer, trace, suggestions, timing = [], [], [], {}
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
            elif t == "done":
                timing = evt.get("timing", {})
                break
            elif t == "error":
                break
    return {"answer": "".join(answer), "trace": trace, "suggestions": suggestions, "timing": timing}


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
    orphans = []
    for n in vis:
        if n["type"] in ("genie_answer", "data_asset") or len(vis) <= 1:
            continue
        if not edges_of(dbg, n["id"]):
            orphans.append(n["label"])
    checks.append(("zero órfãos", not orphans, f"órfãos: {orphans}" if orphans else "ok"))
    bad = [e for e in dbg["edges"] if e["visible"] and (e["source"] not in vis_ids or e["target"] not in vis_ids)]
    checks.append(("arestas fechadas", not bad, "ok" if not bad else f"{len(bad)} abertas"))
    emailish = [n["label"] for n in vis if EMAIL_RE.search(n["label"] or "")]
    checks.append(("sem rótulo email", not emailish, f"{emailish}" if emailish else "ok"))
    docish = [n["label"] for n in vis if n["label"] == "(documento)"]
    checks.append(("sem '(documento)'", not docish, f"{docish}" if docish else "ok"))
    bad_sugg = [s.get("node_id") for s in suggestions if s.get("node_id") and s.get("node_id") not in vis_ids]
    checks.append(("sugestões sobre visíveis", not bad_sugg, f"{bad_sugg}" if bad_sugg else "ok"))
    return checks


def dbg_type(dbg: dict, nid: str) -> str:
    for n in dbg["visible"] + dbg["staging"]:
        if n["id"] == nid:
            return n["type"]
    return "?"


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
        c.append(("Lucca por participou",
                  bool(lucca) and bool(events) and any(linked(ev["id"], p["id"], {"attendee", "organizer"}) for ev in events for p in lucca),
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
        c.append(("evento grande com +N", bool(plusn) or all(len(edges_of(dbg, ev["id"])) <= 3 for ev in events),
                  f"{[(e['label'], e.get('staged_participants')) for e in plusn]}"))
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
        c.append(("email ligado a remetente", any(linked(em["id"], p["id"], {"sender"}) for em in emails for p in persons), ""))
    elif case_id == "g":
        c.append(("1 evento", len(events) == 1, f"{len(events)}"))
        c.append(("organizador visível", any(linked(ev["id"], p["id"], {"organizer"}) for ev in events for p in persons), ""))
        c.append(("demais em +N", any((ev.get("staged_participants") or 0) > 0 for ev in events), ""))
    elif case_id == "h":
        c.append(("grafo não muda (0 visíveis)", len(vis) == 0, f"{len(vis)} nós visíveis"))
    return c


def linker_str(dbg: dict) -> str:
    h = dbg.get("linker")
    if not h:
        return "n/a"
    if h.get("failed"):
        return f"falhou ({h.get('error', '?')[:40]})"
    return f"ok (in={h.get('input_size')}, rel={h.get('relevant')})"


def run_model(client: httpx.Client, base: str, model: str, cases: list) -> dict:
    """Roda todos os casos para um modelo. Devolve {rows, details, turn_ms}."""
    rows, details, turn_ms = [], [], []
    for case_id, turns in cases:
        cid = "golden-" + case_id + "-" + uuid.uuid4().hex[:8]
        print(f"  [{model}] caso {case_id} ({cid})")
        last = {"answer": "", "trace": [], "suggestions": [], "timing": {}}
        case_ms, tool_calls = [], 0
        for i, q in enumerate(turns):
            print(f"    turno {i+1}: {q}")
            last = run_turn(client, base, cid, q, model)
            tm = last.get("timing") or {}
            if tm.get("total_ms"):
                case_ms.append(tm["total_ms"])
                turn_ms.append(tm["total_ms"])
            tool_calls += int(tm.get("tool_calls") or 0)
        try:
            dbg = client.get(f"{base}/api/debug/graph/{cid}").json()
        except Exception as e:  # noqa: BLE001
            rows.append({"case": case_id, "ok": False, "fails": [f"debug: {e}"], "vis": "?", "stg": "?",
                         "dur": sum(case_ms) / 1000, "tools": tool_calls, "linker": "?"})
            continue
        uni = universal_checks(dbg, last["suggestions"])
        spec = case_checks(case_id, dbg)
        fails = [name for name, ok, _ in spec + uni if not ok]
        ok = not fails
        rows.append({
            "case": case_id, "ok": ok, "fails": fails,
            "vis": dbg["counts"]["visible"], "stg": dbg["counts"]["staging"],
            "dur": round(sum(case_ms) / 1000, 1), "tools": tool_calls,
            "linker": linker_str(dbg), "p95_ms": max(case_ms) if case_ms else 0,
        })
        details.append((case_id, turns, last, dbg, spec + uni))
    return {"rows": rows, "details": details, "turn_ms": turn_ms}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--models", default="", help="nomes separados por vírgula; default = Opus 5 + Sonnet 5")
    ap.add_argument("--only", default="", help="ids de casos separados por vírgula (ex.: a,g)")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    only = {c.strip() for c in args.only.split(",") if c.strip()}
    cases = [c for c in CASES if not only or c[0] in only]

    with httpx.Client(timeout=600) as client:
        me = client.get(f"{base}/api/me").json()
        if not me.get("debug_graph"):
            print("AVISO: DEBUG_GRAPH não está ligado no backend — /api/debug/graph vai falhar.")
        available = {m["name"] for m in me.get("models", [])}
        if args.models:
            models = [m.strip() for m in args.models.split(",") if m.strip()]
        else:  # default: Opus 5 + Sonnet 5 (mínimo exigido)
            models = [m for m in ("databricks-claude-opus-5", "databricks-claude-sonnet-5") if m in available] \
                or [me.get("default_model", "")]

        ts = datetime.now()
        report = [f"# Golden set do grafo — {ts.isoformat(timespec='seconds')}",
                  f"\nBackend: `{base}` · usuário: `{me.get('email')}` · modelos: {', '.join(f'`{m}`' for m in models)}\n"]
        alerts = []
        per_model = {}

        for model in models:
            print(f"\n=== MODELO {model} ===")
            per_model[model] = run_model(client, base, model, cases)

        # ---- tabela por modelo + latência
        for model in models:
            res = per_model[model]
            report.append(f"\n## Modelo `{model}`\n")
            report.append("| Caso | Passou? | Critérios falhos | Vis/Staging | Duração (s) | Tool calls | Linker ok? | Screenshot |")
            report.append("|------|---------|------------------|-------------|-------------|-----------|-----------|-----------|")
            for r in res["rows"]:
                shot = SCREENSHOTS.get(r["case"], "—")
                report.append(f"| {r['case']} | {'✅' if r['ok'] else '❌'} | {', '.join(r['fails']) or '—'} "
                              f"| {r['vis']}/{r['stg']} | {r['dur']} | {r['tools']} | {r.get('linker', '?')} | {shot} |")
            p50 = _pct(res["turn_ms"], 0.5) / 1000
            p95 = _pct(res["turn_ms"], 0.95) / 1000
            report.append(f"\nLatência por turno — p50 **{p50:.1f}s**, p95 **{p95:.1f}s** ({len(res['turn_ms'])} turnos).")
            over = [r["case"] for r in res["rows"] if r.get("p95_ms", 0) > P95_BUDGET_MS]
            if over:
                msg = f"`{model}`: casos acima de 45s (p95 do turno): {', '.join(over)}"
                alerts.append(msg)
                report.append(f"\n> ⚠️ {msg} — avisar o usuário; não otimizar sem confirmação.")

        # ---- resumo no topo
        head = ["## Resumo\n"]
        for model in models:
            passed = sum(1 for r in per_model[model]["rows"] if r["ok"])
            head.append(f"- `{model}`: {passed}/{len(per_model[model]['rows'])} casos ✅")
        if alerts:
            head.append("\n**Alertas de latência:** " + "; ".join(alerts))
        report.insert(2, "\n".join(head) + "\n")

        # ---- detalhes por caso (staging + motivos), por modelo
        for model in models:
            report.append(f"\n---\n### Detalhes — `{model}`")
            for case_id, turns, last, dbg, checks in per_model[model]["details"]:
                report.append(f"\n#### Caso {case_id}")
                report.append("**Perguntas:** " + " ⇢ ".join(f"“{t}”" for t in turns))
                report.append(f"\n**Resposta (fim):** {last['answer'][-320:].strip() or '(vazia)'}")
                report.append(f"\n**Visíveis ({dbg['counts']['visible']}):** "
                              + (", ".join(f"{n['label']} [{n['type']}]" for n in dbg["visible"]) or "—"))
                report.append("\n**Checagens:** " + " · ".join(f"{'✅' if ok else '❌'}{name}" for name, ok, _ in checks))
                if dbg["staging"]:
                    report.append("\n**Staging:** " + " · ".join(
                        f"{n['label']}[{n['type']}]={n['reason'] or '—'}" for n in dbg["staging"][:20]))

        out = Path("docs/screenshots") / f"golden-{ts:%Y%m%d-%H%M%S}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(report), encoding="utf-8")
        print(f"\nRelatório: {out}")
        for model in models:
            passed = sum(1 for r in per_model[model]["rows"] if r["ok"])
            print(f"  {model}: {passed}/{len(per_model[model]['rows'])} ✅")
        if alerts:
            print("ALERTAS:", "; ".join(alerts))


if __name__ == "__main__":
    main()
