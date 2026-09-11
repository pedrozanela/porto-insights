"""Camada da tool composta `genie__ask` exposta ao LLM.

O LLM enxerga UMA tool simples; o ciclo assíncrono ask→poll→result fica escondido em
client.run_genie_ask. Aqui ficam: o schema da tool, o resultado compacto para o LLM e o
payload do card para o frontend.
"""
from __future__ import annotations

from typing import Any

from .client import GenieResult

# Schema no formato de tools do OpenAI.
GENIE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "genie__ask",
        "description": (
            "Responde perguntas sobre os DADOS do Porto Bank (carteira de crédito, originação, "
            "inadimplência, produtos, metas, contratos por UF/segmento/canal) consultando o Genie "
            "One, que escreve e executa SQL sobre o Unity Catalog. Use sempre que a pergunta pedir "
            "números, tendências ou fatos do negócio. Não invente dados — use esta ferramenta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "A pergunta de dados, em português, autocontida.",
                },
                "follow_up": {
                    "type": "boolean",
                    "description": (
                        "true se esta pergunta dá continuidade à anterior sobre os mesmos dados "
                        "(ex.: 'e por segmento?'), para manter o mesmo fio no Genie One."
                    ),
                },
            },
            "required": ["question"],
        },
    },
}


def compact_result_for_llm(r: GenieResult, max_rows: int = 10) -> str:
    """Resultado enxuto para o LLM narrar. O detalhamento (tabela/SQL/fontes) vai no card."""
    if r.status == "timeout":
        return "O Genie One não respondeu a tempo. Avise o usuário e sugira tentar de novo."
    if r.status == "failed":
        return "O Genie One não conseguiu responder a esta pergunta."

    lines = ["Resposta do Genie One (já exibida ao usuário em um card com tabela, SQL e fontes):", ""]
    lines.append(r.answer or "(sem texto)")
    if r.columns and r.rows:
        lines.append("")
        lines.append("Amostra do resultado (para conferência):")
        lines.append(" | ".join(r.columns))
        for row in r.rows[:max_rows]:
            lines.append(" | ".join(str(c) for c in row))
    lines.append("")
    lines.append(
        "Instrução: componha uma resposta curta em português para o executivo, destacando os "
        "números-chave em negrito. NÃO repita o SQL nem a tabela inteira (já estão no card)."
    )
    return "\n".join(lines)


def _sources(r: GenieResult) -> list[dict[str, str]]:
    out = []
    for label, url in r.links:
        if "/explore/data/" in url:
            out.append({"label": label, "url": url, "type": "data_asset"})
        elif "/genie" in url and "Explore" not in label:
            out.append({"label": label, "url": url, "type": "genie"})
    return out


def card_payload(r: GenieResult) -> dict[str, Any]:
    """Dados do GenieAnswerCard para o frontend."""
    return {
        "status": r.status,
        "answer": r.answer,
        "sql": r.sql,
        "columns": r.columns,
        "rows": r.rows,
        "truncated": r.truncated,
        "sources": _sources(r),
        "deep_link": r.deep_link,
        "conversation_id": r.conversation_id,
        "response_id": r.response_id,
        "item_id": r.item_id,
    }
