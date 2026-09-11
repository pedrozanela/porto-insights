"""Cria (ou atualiza) o Genie Agent de suporte 'Porto Bank — Carteira e Crédito'.

Controlado pela flag CREATE_SUPPORT_GENIE_AGENT (padrão true). O app NÃO chama este agent
diretamente — ele existe para que o Genie One roteie perguntas do Porto Bank de forma
previsível, já que este workspace tem muitos Genie Agents concorrendo pelo roteamento.

Idempotente: procura um space com o mesmo título; se existir, faz PATCH; senão, POST.
Usa o builder da skill genie-rooms para montar o serialized_space (version 2).
"""
from __future__ import annotations

import os
import sys

from databricks.sdk import WorkspaceClient

SKILL_RES = (
    "/Users/pedro.zanela/.vibe/marketplace/plugins/fe-internal-tools/"
    "skills/genie-rooms/resources"
)
sys.path.insert(0, SKILL_RES)
from genie_space_builder import GenieSpaceBuilder  # noqa: E402

PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "fevm-pzanela-classic-aws")
WAREHOUSE_ID = os.environ.get("SQL_WAREHOUSE_ID", "848374d85d2bad86")
CATALOG = os.environ.get("PORTO_CATALOG", "pzanela_classic_aws_catalog")
SCHEMA = os.environ.get("PORTO_SCHEMA", "porto_insights")
FQ = f"{CATALOG}.{SCHEMA}"
TITLE = "Porto Bank — Carteira e Crédito"

INSTRUCTIONS = f"""\
Você responde perguntas sobre a carteira de crédito e consórcio do Porto Bank em português
do Brasil. Fontes no schema {FQ}.

Definições de negócio (use exatamente estas):
- Inadimplência: contrato com dias_atraso > 90, em pontos percentuais do saldo.
- Carteira ativa: contratos com status = 'ATIVO'.
- Originação/produção: valor contratado no mês (novas_originacoes).
- Competência: primeiro dia do mês. "Mês corrente" = maior competência em carteira_mensal.
- Segmento: PF (pessoa física) ou PJ (pessoa jurídica).

Prefira a metric view mv_carteira_credito para perguntas agregadas de carteira, originação,
inadimplência e metas por mês/produto/segmento. Use mv_contratos_credito para cortes por UF,
cidade, canal de origem e ticket médio.

Sempre que a pergunta envolver desempenho, compare o realizado com a meta do mesmo mês,
produto e segmento e diga se foi atingida ou estourada.

Formato: comece com um resumo de 2 a 3 frases antes de qualquer tabela; valores em R$ com
separador brasileiro; percentuais com 1 casa decimal.
"""


def build() -> GenieSpaceBuilder:
    space = GenieSpaceBuilder(
        title=TITLE,
        description="Carteira, originação, inadimplência e metas do Porto Bank (dados sintéticos de demo).",
        warehouse_id=WAREHOUSE_ID,
    )
    space.set_instructions(INSTRUCTIONS)
    space.add_metric_view(f"{FQ}.mv_carteira_credito")
    space.add_metric_view(f"{FQ}.mv_contratos_credito")
    for t in ("carteira_mensal", "contratos", "clientes", "produtos", "metas_comerciais"):
        space.add_table(f"{FQ}.{t}")

    space.add_example_sql(
        title="Carteira de Capital de Giro PJ no mês corrente vs meta",
        sql=(
            f"SELECT `Produto`, MEASURE(`Originação`) AS originacao, "
            f"MEASURE(`Meta de originação`) AS meta, "
            f"MEASURE(`Atingimento da meta de originação %`) AS atingimento "
            f"FROM {FQ}.mv_carteira_credito "
            f"WHERE `Produto` = 'Capital de Giro PJ' "
            f"AND `Competência` = (SELECT MAX(`Competência`) FROM {FQ}.mv_carteira_credito) "
            f"GROUP BY `Produto`"
        ),
        description="Padrão de comparação realizado vs meta no mês corrente.",
        item_id=format(1, "032x"),
    )
    space.add_example_sql(
        title="Inadimplência 90d por segmento no mês corrente",
        sql=(
            f"SELECT `Segmento`, MEASURE(`Inadimplência 90d %`) AS inadimplencia "
            f"FROM {FQ}.mv_carteira_credito "
            f"WHERE `Competência` = (SELECT MAX(`Competência`) FROM {FQ}.mv_carteira_credito) "
            f"GROUP BY `Segmento` ORDER BY `Segmento`"
        ),
        item_id=format(2, "032x"),
    )
    space.validate()
    return space


def find_existing(w: WorkspaceClient) -> str | None:
    resp = w.api_client.do("GET", "/api/2.0/genie/spaces", query={"page_size": 100})
    for s in resp.get("spaces", []) or []:
        if s.get("title") == TITLE:
            return s.get("space_id") or s.get("id")
    return None


def main() -> None:
    if os.environ.get("CREATE_SUPPORT_GENIE_AGENT", "true").lower() != "true":
        print("CREATE_SUPPORT_GENIE_AGENT != true — pulando criação do Genie Agent.")
        return

    space = build()
    payload = {
        "title": space.title,
        "description": space.description,
        "warehouse_id": space.warehouse_id,
        "serialized_space": space.to_json(),
    }

    w = WorkspaceClient(profile=PROFILE)
    existing = find_existing(w)
    if existing:
        w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{existing}", body=payload)
        print(f"Genie Agent atualizado (PATCH): {existing}")
        space_id = existing
    else:
        resp = w.api_client.do("POST", "/api/2.0/genie/spaces", body=payload)
        space_id = resp.get("space_id") or resp.get("id")
        print(f"Genie Agent criado (POST): {space_id}")

    host = w.config.host.rstrip("/")
    print(f"URL: {host}/genie/rooms/{space_id}")


if __name__ == "__main__":
    main()
