"""Promoção por evidência: o grafo mostra evidência, não exploração.

Extratores põem nós em staging (props.staged=True). A promoção decide o que fica visível no fim
do turno, e grava o motivo em props.promotion_reason (positivo ou negativo). Regras:

1. Semente por evidência direta: referência na resposta (id/url/id de Drive/**título**),
   relevância marcada pelo linker, ou pessoa que é o assunto da pergunta.
2. Casamento por título é regra de PRIMEIRA CLASSE (não último recurso) para calendar_event,
   drive_file, email (assunto) e email_thread — título normalizado contido na resposta
   normalizada. Eventos recorrentes desambiguam pela data citada (dd/mm); sem data, promove só a
   instância mais próxima de hoje.
3. Fechamento estrutural: ao promover um filho PRIMÁRIO (person via attendee/organizer/sender/
   recipient; drive_file via attached/links_to; email via in_thread), promove também o pai que o
   conecta (a relação é a evidência). Filhos promovidos só por colapso/anexo NÃO propagam.
4. Colapso de participantes: num evento visível, promove só quem foi perguntado, o organizador e
   quem já está ligado a outro visível; os demais viram "+N" (staged_participants/staged_people).
5. Invariante sem-órfãos (enforce_no_orphans, sobre o grafo FINAL do turno): um nó só é visível se
   tiver ao menos uma aresta visível, exceto se for o assunto direto da pergunta ou o único nó.

Nada é apagado: nós em staging ficam no store e podem ser promovidos num turno posterior.
"""
from __future__ import annotations

import re
from datetime import date

from .extractors.common import extract_drive_ids, normalize_title
from .schema import GraphState, is_visible

# arestas pai↔filho para o fechamento estrutural
_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/\d{2,4})?\b")

# tipos que nunca são rebaixados pelo invariante sem-órfãos (evidência determinística do Genie)
_ORPHAN_KEEP_TYPES = {"genie_answer", "data_asset"}


# ---------------------------------------------------------------- helpers de data / título

def _cited_daymonths(answer_text: str) -> set[tuple[int, int]]:
    """(dia, mês) citados na resposta (ex.: '14/09', '16/09', 'dia 10/09')."""
    out: set[tuple[int, int]] = set()
    for m in _DATE_RE.finditer(answer_text or ""):
        d, mo = int(m.group(1)), int(m.group(2))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            out.add((d, mo))
    return out


def _event_daymonth(ev) -> tuple[int, int] | None:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(ev.props.get("start") or "")[:10])
    return (int(m.group(3)), int(m.group(2))) if m else None


def _days_from_today(ev) -> int:
    try:
        return abs((date.fromisoformat(str(ev.props.get("start") or "")[:10]) - date.today()).days)
    except Exception:  # noqa: BLE001
        return 10**6


def _references(node, answer_text: str, answer_norm: str, answer_drive_ids: set[str]) -> bool:
    """Referência por ID CANÔNICO (id do nó / url / id de Drive) OU por título normalizado.
    O casamento por título é de primeira classe (item 2)."""
    if node.id and node.id in answer_text:
        return True
    url = node.url or node.props.get("url") or node.props.get("web_view_link")
    if url and str(url) in answer_text:
        return True
    fid = node.props.get("file_id")
    if fid and fid in answer_drive_ids:
        return True
    lab = normalize_title(node.props.get("title") or node.props.get("subject") or node.label)
    return len(lab) > 4 and lab in answer_norm


def _is_subject(node, subject_norm: str) -> bool:
    """O nó é o assunto DIRETO da pergunta (usado como exceção do invariante sem-órfãos)."""
    if not subject_norm:
        return False
    lab = normalize_title(node.props.get("title") or node.props.get("subject") or node.label)
    if not lab:
        return False
    if node.type == "person":
        return any(t in subject_norm.split() for t in lab.split() if len(t) > 2)
    return len(lab) > 4 and lab in subject_norm


# ---------------------------------------------------------------- promoção

def _set_visible(node, promoted: set[str], reason: str) -> None:
    node.props["staged"] = False
    node.props["promotion_reason"] = reason
    promoted.add(node.id)


def _child_parent(state: GraphState, e) -> tuple[str, str] | None:
    """(child_id, parent_id) para arestas estruturais; None se a aresta não é pai↔filho."""
    s, t = state.nodes.get(e.source), state.nodes.get(e.target)
    if not s or not t:
        return None
    ty = e.type
    if ty in ("attendee", "organizer") and s.type == "calendar_event" and t.type == "person":
        return t.id, s.id
    if ty in ("sender", "recipient") and s.type == "email" and t.type == "person":
        return t.id, s.id
    if ty == "attached" and t.type == "drive_file":
        return t.id, s.id
    if ty == "links_to" and t.type == "drive_file":
        return t.id, s.id
    if ty == "in_thread" and s.type == "email" and t.type == "email_thread":
        return s.id, t.id
    if ty == "notes_of" and s.type == "drive_file" and t.type == "calendar_event":
        return s.id, t.id
    return None


def _has_visible_parent(state: GraphState, child_id: str) -> bool:
    """O filho já está ligado a algum pai VISÍVEL (por aresta estrutural)?"""
    for e in state.edges.values():
        cp = _child_parent(state, e)
        if cp and cp[0] == child_id:
            parent = state.nodes.get(cp[1])
            if parent and is_visible(parent):
                return True
    return False


def _structural_closure(state: GraphState, promoted: set[str], primary: set[str]) -> bool:
    """Item 1: filho PRIMÁRIO visível ⇒ promove o pai que o conecta, mas SÓ se o filho ainda não
    tiver pai visível (evita puxar a vizinhança inteira — ex.: uma pessoa citada que participa de
    várias reuniões só ancora na reunião de fato pedida/citada). Só filhos primários propagam."""
    changed = False
    for e in list(state.edges.values()):
        cp = _child_parent(state, e)
        if not cp:
            continue
        child_id, parent_id = cp
        if child_id not in primary:
            continue
        child, parent = state.nodes.get(child_id), state.nodes.get(parent_id)
        if not (child and parent and is_visible(child) and not is_visible(parent)):
            continue
        if _has_visible_parent(state, child_id):  # já ancorado num pai visível → não puxa mais
            continue
        _set_visible(parent, promoted, f"fechamento estrutural via {e.type}")
        changed = True
    return changed


def _person_neighbors(state: GraphState, ev_id: str):
    out = []
    for e in state.edges.values():
        if e.type in ("attendee", "organizer"):
            other = e.target if e.source == ev_id else (e.source if e.target == ev_id else None)
            if other and other in state.nodes and state.nodes[other].type == "person":
                out.append((state.nodes[other], e.type))
    return out


def _person_linked_to_other_visible(state: GraphState, person_id: str, exclude_ev: str) -> bool:
    for e in state.edges.values():
        other = e.target if e.source == person_id else (e.source if e.target == person_id else None)
        if other and other != exclude_ev and other in state.nodes:
            n = state.nodes[other]
            if n.type != "person" and is_visible(n):
                return True
    return False


def _collapse_participants(state: GraphState, ev, asked_norm: str, promoted: set[str]) -> None:
    staged_people = []
    for p, etype in _person_neighbors(state, ev.id):
        if is_visible(p):
            continue
        name_tokens = [t for t in normalize_title(p.label).split() if len(t) > 2]
        asked = any(t in asked_norm.split() for t in name_tokens)
        is_org = etype == "organizer"
        linked = _person_linked_to_other_visible(state, p.id, ev.id)
        if asked:
            _set_visible(p, promoted, "colapso: perguntado")
        elif is_org:
            _set_visible(p, promoted, "colapso: organizador")
        elif linked:
            _set_visible(p, promoted, "colapso: ligado a visível")
        else:
            p.props["promotion_reason"] = "colapsado em +N"
            staged_people.append({"id": p.id, "name": p.label})
    ev.props["staged_participants"] = len(staged_people)
    ev.props["staged_people"] = staged_people


def _promote_attachments(state: GraphState, ev, promoted: set[str], limit: int = 5) -> None:
    """Promove os documentos anexados (aresta `attached`) de um evento visível, até `limit`."""
    count = 0
    for e in state.edges.values():
        if e.type != "attached":
            continue
        doc_id = e.target if e.source == ev.id else (e.source if e.target == ev.id else None)
        if not doc_id or doc_id not in state.nodes:
            continue
        doc = state.nodes[doc_id]
        if is_visible(doc):
            continue
        _set_visible(doc, promoted, "anexo de evento visível")
        count += 1
        if count >= limit:
            break


def _seed(state: GraphState, answer_text: str, answer_norm: str, answer_drive_ids: set[str],
          relevant_ids: set[str], question_norm: str, promoted: set[str], primary: set[str]) -> None:
    # Nós não-evento. PESSOAS: só por referência na resposta ou por serem o assunto da pergunta —
    # NUNCA por relevant_ids do linker (o colapso é quem decide quais participantes aparecem; senão
    # o linker despeja a lista inteira). Demais (doc/genie/email/thread): referência ou relevant_ids.
    for n in list(state.nodes.values()):
        if n.type == "calendar_event" or is_visible(n):
            continue
        if _references(n, answer_text, answer_norm, answer_drive_ids):
            _set_visible(n, promoted, "referência na resposta"); primary.add(n.id)
        elif n.type == "person":
            if _is_subject(n, question_norm):
                _set_visible(n, promoted, "assunto da pergunta"); primary.add(n.id)
        elif n.id in relevant_ids:
            _set_visible(n, promoted, "relevante (linker)"); primary.add(n.id)

    # Eventos: candidato = título citado (1ª classe) OU relevante (linker) OU notas de doc visível.
    # Recorrentes SEMPRE passam pela desambiguação (data citada; senão a instância mais próxima),
    # inclusive quando o linker marca várias instâncias como relevantes.
    notes_events = {
        e.target for e in state.edges.values()
        if e.type == "notes_of" and e.source in state.nodes and is_visible(state.nodes[e.source])
    }
    cited = _cited_daymonths(answer_text)
    events = [n for n in state.nodes.values() if n.type == "calendar_event" and not is_visible(n)]
    by_title: dict[str, list] = {}
    for ev in events:
        by_title.setdefault(normalize_title(ev.props.get("summary") or ev.label), []).append(ev)

    for title, evs in by_title.items():
        title_cited = len(title) > 4 and title in answer_norm
        cands = [e for e in evs if not is_visible(e)
                 and (title_cited or e.id in relevant_ids or e.id in notes_events)]
        if not cands:
            continue

        def _reason(e, dated=False) -> str:
            if title_cited:
                return "título + data citados" if dated else "título citado na resposta"
            return "relevante (linker)" if e.id in relevant_ids else "notas de evento visível"

        if len(evs) == 1:
            _set_visible(cands[0], promoted, _reason(cands[0])); primary.add(cands[0].id)
        else:  # recorrente → desambigua sempre
            date_conf = [e for e in cands if _event_daymonth(e) in cited]
            targets = date_conf or [min(cands, key=_days_from_today)]
            for e in targets:
                _set_visible(e, promoted,
                             _reason(e, dated=bool(date_conf)) if title_cited
                             else "recorrente: instância mais próxima de hoje")
                primary.add(e.id)
            for e in evs:
                if not is_visible(e) and not e.props.get("promotion_reason"):
                    e.props["promotion_reason"] = "instância recorrente não citada"


def promote(state: GraphState, *, answer_text: str, relevant_ids: set[str], asked_text: str) -> set[str]:
    """Aplica as regras de promoção. Retorna os ids que passaram a ser visíveis neste passo.
    NÃO aplica o invariante sem-órfãos (isso é enforce_no_orphans, sobre o grafo final do turno)."""
    answer_text = answer_text or ""
    answer_norm = normalize_title(answer_text)
    answer_drive_ids = set(extract_drive_ids(answer_text))
    asked_norm = normalize_title(f"{asked_text} {answer_text}")
    question_norm = normalize_title(asked_text)
    promoted: set[str] = set()
    primary: set[str] = set()

    _seed(state, answer_text, answer_norm, answer_drive_ids, relevant_ids, question_norm, promoted, primary)

    # ponto fixo: fechamento estrutural (filhos primários → pais) + colapso + anexos
    for _ in range(30):
        before = len(promoted)
        _structural_closure(state, promoted, primary)
        for ev in [n for n in state.nodes.values() if n.type == "calendar_event" and is_visible(n)]:
            _collapse_participants(state, ev, asked_norm, promoted)
            _promote_attachments(state, ev, promoted)
        if len(promoted) == before:
            break

    for n in state.nodes.values():  # razão negativa default para quem ficou em staging
        if not is_visible(n) and not n.props.get("promotion_reason"):
            n.props["promotion_reason"] = "sem referência na resposta"
    return promoted


def enforce_no_orphans(state: GraphState, *, asked_text: str = "") -> list[str]:
    """Invariante (item 3): um nó só é visível se tiver ≥1 aresta visível, exceto se for o assunto
    direto da pergunta ou o único nó. Roda sobre o grafo FINAL do turno; devolve os ids rebaixados.
    genie_answer/data_asset nunca são rebaixados (evidência determinística do Genie)."""
    subject_norm = normalize_title(asked_text)
    demoted: list[str] = []
    changed = True
    while changed:
        changed = False
        visible = [n for n in state.nodes.values() if is_visible(n)]
        if len(visible) <= 1:
            break
        vis_ids = {n.id for n in visible}
        for n in visible:
            if n.type in _ORPHAN_KEEP_TYPES:
                continue
            has_edge = any(
                (e.source == n.id and e.target in vis_ids and e.target != n.id)
                or (e.target == n.id and e.source in vis_ids and e.source != n.id)
                for e in state.edges.values())
            if has_edge or _is_subject(n, subject_norm):
                continue
            n.props["staged"] = True
            n.props["promotion_reason"] = "órfão"
            demoted.append(n.id)
            changed = True
    return demoted


def promote_ids(state: GraphState, ids: list[str], *, asked_text: str = "") -> set[str]:
    """Promoção manual (ex.: usuário clica em um participante). Também faz fechamento estrutural."""
    asked_norm = normalize_title(asked_text)
    promoted: set[str] = set()
    primary: set[str] = set()
    for nid in ids:
        n = state.nodes.get(nid)
        if n and not is_visible(n):
            _set_visible(n, promoted, "promoção manual")
            primary.add(nid)
    for _ in range(30):
        before = len(promoted)
        _structural_closure(state, promoted, primary)
        for ev in [n for n in state.nodes.values() if n.type == "calendar_event" and is_visible(n)]:
            _collapse_participants(state, ev, asked_norm, promoted)
            _promote_attachments(state, ev, promoted)
        if len(promoted) == before:
            break
    return promoted


def bare_visible_events(state: GraphState) -> list:
    """Eventos VISÍVEIS sem participante carregado (sem aresta attendee/organizer) e ainda não
    enriquecidos — candidatos ao `get` determinístico do backend (item 1). Ignora provisórios."""
    with_people: set[str] = set()
    for e in state.edges.values():
        if e.type in ("attendee", "organizer"):
            for end in (e.source, e.target):
                n = state.nodes.get(end)
                if n and n.type == "calendar_event":
                    with_people.add(n.id)
    return [n for n in state.nodes.values()
            if n.type == "calendar_event" and is_visible(n) and not n.props.get("provisional")
            and not n.props.get("bare_enriched") and n.id not in with_people]


def visible_delta(state: GraphState):
    """Todos os nós/arestas visíveis (o frontend deduplica por id)."""
    nodes = [n for n in state.nodes.values() if is_visible(n)]
    vis = {n.id for n in nodes}
    edges = [e for e in state.edges.values() if e.source in vis and e.target in vis]
    return nodes, edges


def debug_snapshot(state: GraphState) -> dict:
    """Item 5: retrato do grafo p/ depuração — visíveis, em staging e o MOTIVO de cada decisão."""
    def row(n):
        return {"id": n.id, "type": n.type, "label": n.label, "visible": is_visible(n),
                "first_seen_turn": n.first_seen_turn,
                "reason": n.props.get("promotion_reason"),
                "staged_participants": n.props.get("staged_participants")}
    rows = [row(n) for n in state.nodes.values()]
    edges = [{"source": e.source, "target": e.target, "type": e.type,
              "visible": is_visible(state.nodes[e.source]) and is_visible(state.nodes[e.target])}
             for e in state.edges.values() if e.source in state.nodes and e.target in state.nodes]
    visible = [r for r in rows if r["visible"]]
    staging = [r for r in rows if not r["visible"]]
    return {"visible": visible, "staging": staging, "edges": edges,
            "linker": getattr(state, "linker_health", None),  # saúde do linker (item 2e)
            "counts": {"visible": len(visible), "staging": len(staging), "edges": len(edges)}}
