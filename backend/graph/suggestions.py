"""Sugestões de próxima pergunta a partir das lacunas do grafo (Bloco 5). Determinístico.

Emitidas no evento SSE `suggestions` após cada turno. Até 3, em ordem de prioridade,
deduplicadas, sem repetir perguntas já feitas na conversa.
"""
from __future__ import annotations

from .schema import GraphState

DATA_TERMS = ("carteira", "inadimplência", "inadimplencia", "originação", "originacao",
              "meta", "receita", "clientes", "contratos", "r$")


def _adjacency(state: GraphState):
    """node_id -> (set de tipos vizinhos, lista de nós vizinhos)."""
    types: dict[str, set[str]] = {}
    neigh: dict[str, list] = {}
    for e in state.edges.values():
        for a, b in ((e.source, e.target), (e.target, e.source)):
            if a in state.nodes and b in state.nodes:
                types.setdefault(a, set()).add(state.nodes[b].type)
                neigh.setdefault(a, []).append(state.nodes[b])
    return types, neigh


def _date(node) -> str:
    d = str(node.props.get("start") or node.props.get("date") or "")[:10]
    return d


def build_suggestions(state: GraphState, asked: set[str] | None = None, limit: int = 3) -> list[dict]:
    asked_norm = {(q or "").strip().lower() for q in (asked or set())}
    types, _ = _adjacency(state)
    out: list[dict] = []
    seen_prompts: set[str] = set()

    def visible(n) -> bool:  # sugestões só sobre o grafo visível (não staging)
        return not n.props.get("staged")

    def add(label: str, prompt: str, node_id: str) -> None:
        key = prompt.strip().lower()
        if key in asked_norm or key in seen_prompts or len(out) >= limit:
            return
        seen_prompts.add(key)
        out.append({"label": label, "prompt": prompt, "node_id": node_id})

    def has(nid: str, *t: str) -> bool:
        return bool(types.get(nid, set()) & set(t))

    events = [n for n in state.nodes.values() if n.type == "calendar_event" and visible(n)]
    emails = [n for n in state.nodes.values() if n.type == "email" and visible(n)]
    docs = [n for n in state.nodes.values() if n.type == "drive_file" and visible(n)]
    genies = [n for n in state.nodes.values() if n.type == "genie_answer" and visible(n)]

    # 1. evento sem email
    for ev in events:
        if not has(ev.id, "email", "email_thread"):
            add(f"Ver emails sobre {ev.label}",
                f"Quais emails têm relação com a reunião {ev.label}"
                + (f" de {_date(ev)}" if _date(ev) else "") + "?", ev.id)

    # 2. evento/email sem documento
    for n in events + emails:
        if not has(n.id, "drive_file"):
            add(f"Há documentos ligados a {n.label}?",
                f"Há documentos no Drive ligados a {n.label}?", n.id)

    # 3. doc/email com tema de dado, sem genie_answer
    for n in docs + emails:
        text = f"{n.label} {n.props.get('subject','')} {n.props.get('snippet','')}".lower()
        if not has(n.id, "genie_answer") and any(t in text for t in DATA_TERMS):
            tema = next((t for t in ("carteira", "inadimplência", "originação", "meta", "receita",
                                     "clientes", "contratos") if t in text), "esse tema")
            add(f"Há dados no Genie sobre {tema}?",
                f"O que os dados do Porto Bank mostram sobre {tema}?", n.id)

    # 4. genie_answer sem evento
    for g in genies:
        if not has(g.id, "calendar_event"):
            add("Isso aparece em alguma reunião da minha agenda?",
                "Isso tem relação com alguma reunião da minha agenda?", g.id)

    # 5. pessoa (real, não Você) com 2+ objetos ligados
    types2, neigh = _adjacency(state)
    for p in state.nodes.values():
        if p.type != "person" or p.props.get("provisional") or p.props.get("is_self") or not visible(p):
            continue
        objs = [x for x in neigh.get(p.id, []) if x.type != "person"]
        if len(objs) >= 2:
            add(f"O que tenho com {p.label} esta semana?",
                f"O que tenho com {p.label} esta semana?", p.id)

    return out[:limit]
