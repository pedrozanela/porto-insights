#!/usr/bin/env python
"""Generate and load synthetic Porto Bank data into Unity Catalog.

Idempotent: re-running replaces table contents. Use --drop to remove the tables first.
Data is deterministic (fixed seed), so the demo numbers are stable across runs.

    python scripts/seed_data.py [--drop]
"""
from __future__ import annotations

import argparse
import random
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from faker import Faker

from _sql import FQ, client, run, scalar

SEED = 20260910
MONTHS = 18            # months of history in carteira_mensal, ending in the current month
N_CLIENTES = 800
N_CONTRATOS = 2400

fake = Faker("pt_BR")
Faker.seed(SEED)
rng = random.Random(SEED)

UFS = [("SP", 0.42), ("MG", 0.11), ("RJ", 0.10), ("PR", 0.08), ("RS", 0.07),
       ("SC", 0.06), ("BA", 0.05), ("GO", 0.04), ("PE", 0.04), ("CE", 0.03)]
CANAIS = ["Agência", "App", "Site", "Corretor Parceiro", "Telefone"]
FAIXAS_PF = ["Até 3 mil", "3 a 7 mil", "7 a 15 mil", "15 a 30 mil", "Acima de 30 mil"]
FAIXAS_PJ = ["Até 500 mil", "500 mil a 5 milhões", "5 a 50 milhões", "Acima de 50 milhões"]


@dataclass(frozen=True)
class Produto:
    produto_id: int
    nome: str
    linha: str
    publico: str
    ticket: tuple[int, int]     # min/max contracted amount, in BRL
    prazo: tuple[int, int]      # min/max term, in months
    taxa: tuple[float, float]   # min/max monthly rate, as a fraction
    inad_base: float            # baseline 90d delinquency, in percentage points


PRODUTOS = [
    Produto(1, "Cartão Porto", "Cartão de Crédito", "PF", (1_500, 25_000), (12, 24), (0.0790, 0.1350), 6.8),
    Produto(2, "Financiamento de Veículos", "Financiamento", "PF", (25_000, 180_000), (24, 60), (0.0135, 0.0225), 3.4),
    Produto(3, "Consórcio Imobiliário", "Consórcio", "PF", (90_000, 600_000), (120, 200), (0.0000, 0.0000), 1.9),
    Produto(4, "Crédito Pessoal", "Crédito", "PF", (2_000, 60_000), (12, 48), (0.0210, 0.0480), 8.1),
    Produto(5, "Capital de Giro PJ", "Crédito PJ", "PJ", (80_000, 2_500_000), (12, 36), (0.0165, 0.0290), 4.2),
    Produto(6, "Antecipação de Recebíveis PJ", "Crédito PJ", "PJ", (40_000, 900_000), (3, 12), (0.0185, 0.0320), 3.1),
]
PRODUTOS_BY_ID = {p.produto_id: p for p in PRODUTOS}

# The demo hangs on this product: PJ working capital originating above target with
# delinquency climbing in the current month.
DEMO_PRODUTO_ID = 5


def competencias() -> list[date]:
    """First day of each month, oldest first, ending in the current month."""
    today = date.today()
    out: list[date] = []
    y, m = today.year, today.month
    for _ in range(MONTHS):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


COMPETENCIAS = competencias()
FIRST_MONTH, CURRENT_MONTH = COMPETENCIAS[0], COMPETENCIAS[-1]


def sql_str(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, date):
        return f"DATE '{value.isoformat()}'"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def pick_uf() -> str:
    return rng.choices([u for u, _ in UFS], weights=[w for _, w in UFS])[0]


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


# ---------------------------------------------------------------- generators

def gen_clientes() -> list[tuple]:
    rows = []
    for cid in range(1, N_CLIENTES + 1):
        is_pj = rng.random() < 0.28
        segmento = "PJ" if is_pj else "PF"
        nome = fake.company() if is_pj else fake.name()
        rows.append((
            cid, nome, segmento, pick_uf(), fake.city(),
            rng.choice(FAIXAS_PJ if is_pj else FAIXAS_PF),
            fake.date_between(start_date=date(2015, 1, 1), end_date=date(2026, 6, 30)),
            rng.choice(CANAIS),
        ))
    return rows


def gen_contratos(clientes: list[tuple]) -> list[tuple]:
    """One row per contract. Origination dates spread across the history window,
    biased towards recent months so the current month looks alive."""
    by_seg: dict[str, list[int]] = {"PF": [], "PJ": []}
    for c in clientes:
        by_seg[c[2]].append(c[0])

    rows = []
    for contrato_id in range(1, N_CONTRATOS + 1):
        produto = rng.choices(PRODUTOS, weights=[26, 20, 9, 22, 14, 9])[0]
        cliente_id = rng.choice(by_seg[produto.publico])

        # Origination: uniform over the window, with extra mass in the last 3 months.
        span = months_between(FIRST_MONTH, CURRENT_MONTH)
        offset = rng.randint(0, span) if rng.random() > 0.22 else rng.randint(max(0, span - 2), span)
        base = COMPETENCIAS[offset]
        data_contratacao = date(base.year, base.month, rng.randint(1, 28))

        valor = round(rng.uniform(*produto.ticket), -2)
        prazo = rng.randint(*produto.prazo)
        taxa = round(rng.uniform(*produto.taxa), 4)

        idade = months_between(data_contratacao, CURRENT_MONTH)
        if idade >= prazo:
            status = "LIQUIDADO"
        elif rng.random() < 0.04:
            status = "CANCELADO"
        else:
            status = "ATIVO"

        # Delinquency: baseline per product, heavier for the demo product in recent months.
        inad_p = produto.inad_base / 100
        if produto.produto_id == DEMO_PRODUTO_ID and idade <= 2:
            inad_p *= 2.6
        if status != "ATIVO":
            dias_atraso = 0
        elif rng.random() < inad_p:
            dias_atraso = rng.randint(91, 240)
        elif rng.random() < 0.10:
            dias_atraso = rng.randint(1, 89)
        else:
            dias_atraso = 0

        saldo = 0.0 if status == "LIQUIDADO" else round(valor * max(0.0, 1 - idade / prazo), 2)
        if status == "CANCELADO":
            saldo = 0.0

        rows.append((contrato_id, cliente_id, produto.produto_id, data_contratacao,
                     valor, saldo, taxa, prazo, status, dias_atraso))
    return rows


def gen_carteira_mensal(contratos: list[tuple]) -> list[tuple]:
    """Monthly snapshot aggregated from contratos, so the two tables always agree."""
    buckets: dict[tuple[date, int, str], dict[str, float]] = {}
    for (_cid, _cliente, produto_id, dt_contr, valor, _saldo, _taxa, prazo, status, dias_atraso) in contratos:
        if status == "CANCELADO":
            continue                                       # cancelled contracts leave the book entirely
        produto = PRODUTOS_BY_ID[produto_id]
        segmento = produto.publico
        for comp in COMPETENCIAS:
            if dt_contr > date(comp.year, comp.month, 28):
                continue
            idade = months_between(dt_contr, comp)
            if idade >= prazo:
                continue                                   # already paid off by this month
            saldo = valor * max(0.0, 1 - idade / prazo)
            key = (comp, produto_id, segmento)
            b = buckets.setdefault(key, {"saldo": 0.0, "orig": 0.0, "qtd": 0.0, "saldo_inad": 0.0})
            b["saldo"] += saldo
            b["qtd"] += 1
            if (dt_contr.year, dt_contr.month) == (comp.year, comp.month):
                b["orig"] += valor
            # A contract counts as 90d-delinquent from the month it went bad onwards.
            if dias_atraso > 90 and idade >= 1:
                b["saldo_inad"] += saldo

    rows = []
    for (comp, produto_id, segmento), b in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        inad = (b["saldo_inad"] / b["saldo"] * 100) if b["saldo"] else 0.0
        rows.append((comp, produto_id, segmento, round(b["saldo"], 2), round(b["orig"], 2),
                     round(inad, 2), int(b["qtd"])))
    return rows


def gen_metas(carteira: list[tuple]) -> list[tuple]:
    """Targets sit close to actuals, except for the demo product in the current month,
    where origination beats target and delinquency breaches the ceiling."""
    rows = []
    for (comp, produto_id, segmento, _saldo, orig, inad, _qtd) in carteira:
        is_demo_now = produto_id == DEMO_PRODUTO_ID and comp == CURRENT_MONTH
        if is_demo_now:
            meta_orig = round(orig / 1.176, 2)         # ~117,6% da meta (valor não redondo)
            meta_inad_max = round(max(0.5, inad - 1.4), 2)   # actual breaches the ceiling
        else:
            meta_orig = round(orig * rng.uniform(0.94, 1.09), 2)
            meta_inad_max = round(max(0.5, inad * rng.uniform(1.02, 1.22)), 2)
        rows.append((comp, produto_id, segmento, meta_orig, meta_inad_max))
    return rows


# ---------------------------------------------------------------- DDL / load

TABLES: dict[str, tuple[str, str, list[tuple[str, str, str]]]] = {
    # name: (table comment, primary-key-ish note, [(column, type, comment)])
    "clientes": (
        "Cadastro de clientes do Porto Bank (dados sintéticos). Uma linha por cliente.",
        "cliente_id",
        [
            ("cliente_id", "BIGINT", "Identificador único do cliente."),
            ("nome", "STRING", "Razão social (PJ) ou nome completo (PF). Dado fictício."),
            ("segmento", "STRING", "Segmento do cliente: 'PF' (pessoa física) ou 'PJ' (pessoa jurídica)."),
            ("uf", "STRING", "Unidade federativa (sigla de 2 letras) do endereço principal."),
            ("cidade", "STRING", "Cidade do endereço principal."),
            ("faixa_renda_ou_faturamento", "STRING",
             "Faixa de renda mensal para PF ou de faturamento anual para PJ, em reais."),
            ("data_abertura_conta", "DATE", "Data de abertura do relacionamento com o banco."),
            ("canal_origem", "STRING", "Canal pelo qual o cliente foi originado (Agência, App, Site, Corretor Parceiro, Telefone)."),
        ],
    ),
    "produtos": (
        "Catálogo de produtos de crédito e consórcio do Porto Bank. Uma linha por produto.",
        "produto_id",
        [
            ("produto_id", "BIGINT", "Identificador único do produto."),
            ("nome", "STRING", "Nome comercial do produto."),
            ("linha", "STRING", "Linha de negócio: Cartão de Crédito, Financiamento, Consórcio, Crédito ou Crédito PJ."),
            ("publico", "STRING", "Público-alvo do produto: 'PF' ou 'PJ'."),
        ],
    ),
    "contratos": (
        "Contratos individuais de crédito e consórcio. Uma linha por contrato. "
        "Inadimplência é definida como dias_atraso > 90. Carteira ativa é status = 'ATIVO'.",
        "contrato_id",
        [
            ("contrato_id", "BIGINT", "Identificador único do contrato."),
            ("cliente_id", "BIGINT", "Cliente titular do contrato. Referencia clientes.cliente_id."),
            ("produto_id", "BIGINT", "Produto contratado. Referencia produtos.produto_id."),
            ("data_contratacao", "DATE", "Data em que o contrato foi assinado (data da originação)."),
            ("valor_contratado", "DECIMAL(18,2)", "Valor total contratado, em reais."),
            ("saldo_devedor", "DECIMAL(18,2)",
             "Saldo devedor atual, em reais. Zero para contratos liquidados ou cancelados."),
            ("taxa_mensal", "DECIMAL(8,4)",
             "Taxa de juros mensal como fração (0.0185 = 1,85% ao mês). Zero em consórcio."),
            ("prazo_meses", "INT", "Prazo total do contrato, em meses."),
            ("status", "STRING", "Situação do contrato: 'ATIVO', 'LIQUIDADO' ou 'CANCELADO'."),
            ("dias_atraso", "INT",
             "Dias de atraso do pagamento mais antigo em aberto. Acima de 90 o contrato é considerado inadimplente."),
        ],
    ),
    "carteira_mensal": (
        "Fotografia mensal da carteira de crédito por produto e segmento, consistente com a tabela contratos. "
        "Use esta tabela para séries temporais de saldo, originação e inadimplência. "
        "Competência é sempre o primeiro dia do mês.",
        "competencia + produto_id + segmento",
        [
            ("competencia", "DATE", "Mês de referência, sempre no primeiro dia do mês (ex.: 2026-09-01)."),
            ("produto_id", "BIGINT", "Produto. Referencia produtos.produto_id."),
            ("segmento", "STRING", "Segmento atendido pelo produto: 'PF' ou 'PJ'."),
            ("saldo_carteira", "DECIMAL(18,2)",
             "Saldo devedor total da carteira no fim do mês, em reais. Também chamado de carteira ou estoque."),
            ("novas_originacoes", "DECIMAL(18,2)",
             "Valor total contratado no mês, em reais. Também chamado de originação, produção ou desembolso."),
            ("inadimplencia_90d_percentual", "DECIMAL(8,2)",
             "Percentual do saldo da carteira com atraso acima de 90 dias. Já vem em pontos percentuais (4.25 = 4,25%)."),
            ("quantidade_contratos", "BIGINT", "Quantidade de contratos ativos na carteira no mês."),
        ],
    ),
    "metas_comerciais": (
        "Metas comerciais mensais por produto e segmento. Compare sempre o realizado da carteira_mensal "
        "com a meta correspondente do mesmo mês, produto e segmento.",
        "competencia + produto_id + segmento",
        [
            ("competencia", "DATE", "Mês da meta, sempre no primeiro dia do mês."),
            ("produto_id", "BIGINT", "Produto. Referencia produtos.produto_id."),
            ("segmento", "STRING", "Segmento: 'PF' ou 'PJ'."),
            ("meta_originacao", "DECIMAL(18,2)", "Meta de originação do mês, em reais."),
            ("meta_inadimplencia_maxima", "DECIMAL(8,2)",
             "Teto de inadimplência 90d aceito no mês, em pontos percentuais. Acima disso a meta foi estourada."),
        ],
    ),
}


def ddl(name: str) -> str:
    table_comment, _pk, cols = TABLES[name]
    col_sql = ",\n  ".join(f"{c} {t} COMMENT {sql_str(cc)}" for c, t, cc in cols)
    return (f"CREATE OR REPLACE TABLE {FQ}.{name} (\n  {col_sql}\n)\n"
            f"USING DELTA\nCOMMENT {sql_str(table_comment)}")


def insert_batches(w, name: str, rows: list[tuple], batch: int = 200) -> None:
    cols = ", ".join(c for c, _t, _cc in TABLES[name][2])
    for i in range(0, len(rows), batch):
        values = ",\n".join("(" + ", ".join(sql_str(v) for v in r) + ")" for r in rows[i:i + batch])
        run(w, f"INSERT INTO {FQ}.{name} ({cols}) VALUES\n{values}")
        print(f"    {name}: {min(i + batch, len(rows))}/{len(rows)}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", action="store_true", help="drop the tables before recreating them")
    args = ap.parse_args()

    w = client()
    print(f"Alvo: {FQ}  (competências {FIRST_MONTH} .. {CURRENT_MONTH})")
    run(w, f"CREATE SCHEMA IF NOT EXISTS {FQ} COMMENT "
           f"'Dados sintéticos do Porto Bank para a POC Porto Insights (carteira de crédito, produtos, metas).'")

    if args.drop:
        for name in TABLES:
            run(w, f"DROP TABLE IF EXISTS {FQ}.{name}")
            print(f"  dropped {name}")

    clientes = gen_clientes()
    produtos = [(p.produto_id, p.nome, p.linha, p.publico) for p in PRODUTOS]
    contratos = gen_contratos(clientes)
    carteira = gen_carteira_mensal(contratos)
    metas = gen_metas(carteira)
    payload = {"clientes": clientes, "produtos": produtos, "contratos": contratos,
               "carteira_mensal": carteira, "metas_comerciais": metas}

    for name, rows in payload.items():
        print(f"  {name}: criando tabela ({len(rows)} linhas)")
        run(w, ddl(name))
        insert_batches(w, name, rows)

    print("\nValidação:")
    checks = {
        "linhas por tabela": f"SELECT 'clientes', COUNT(*) FROM {FQ}.clientes UNION ALL "
                             f"SELECT 'contratos', COUNT(*) FROM {FQ}.contratos UNION ALL "
                             f"SELECT 'carteira_mensal', COUNT(*) FROM {FQ}.carteira_mensal UNION ALL "
                             f"SELECT 'metas_comerciais', COUNT(*) FROM {FQ}.metas_comerciais",
        "carteira x contratos (mês corrente, ATIVO)":
            f"SELECT ROUND(SUM(c.saldo_carteira)/1e6, 1) AS carteira_mi, "
            f"(SELECT ROUND(SUM(saldo_devedor)/1e6, 1) FROM {FQ}.contratos WHERE status = 'ATIVO') AS contratos_mi "
            f"FROM {FQ}.carteira_mensal c WHERE c.competencia = DATE '{CURRENT_MONTH}'",
        "Capital de Giro PJ no mês corrente vs meta":
            f"SELECT ROUND(c.novas_originacoes/1e6, 2) AS orig_mi, ROUND(m.meta_originacao/1e6, 2) AS meta_mi, "
            f"c.inadimplencia_90d_percentual AS inad, m.meta_inadimplencia_maxima AS teto "
            f"FROM {FQ}.carteira_mensal c JOIN {FQ}.metas_comerciais m USING (competencia, produto_id, segmento) "
            f"WHERE c.produto_id = {DEMO_PRODUTO_ID} AND c.competencia = DATE '{CURRENT_MONTH}'",
        "inadimplência por segmento (mês corrente)":
            f"SELECT segmento, ROUND(SUM(saldo_carteira * inadimplencia_90d_percentual)/SUM(saldo_carteira), 2) AS inad "
            f"FROM {FQ}.carteira_mensal WHERE competencia = DATE '{CURRENT_MONTH}' GROUP BY segmento ORDER BY segmento",
    }
    for label, sql in checks.items():
        print(f"  {label}: {run(w, sql)}")


if __name__ == "__main__":
    main()
