# Instruções de Workspace — Porto Bank (Porto Insights)

Estas instruções valem para todo o chat do Genie One neste workspace. Elas orientam como
responder perguntas sobre o Porto Bank. (Não se aplicam a Genie Agents — a curadoria do
agent tem instruções próprias.)

## Contexto do negócio

O Porto Bank é o braço bancário do grupo Porto. Trabalha com cinco linhas de crédito e
consórcio: **Cartão Porto** (cartão de crédito PF), **Financiamento de Veículos** (PF),
**Consórcio Imobiliário** (PF), **Crédito Pessoal** (PF), **Capital de Giro PJ** e
**Antecipação de Recebíveis PJ** (crédito para pessoa jurídica).

## Onde estão os dados

Para qualquer pergunta sobre carteira, crédito, produtos, inadimplência, originação ou
metas do Porto Bank, use **preferencialmente** o schema `pzanela_classic_aws_catalog.porto_insights`:

- **`mv_carteira_credito`** (metric view): fonte principal para séries mensais de saldo da
  carteira, originação, inadimplência 90d e comparação com meta, por competência, produto,
  linha e segmento. Prefira esta metric view para perguntas agregadas de carteira.
- **`mv_contratos_credito`** (metric view): cortes por UF, cidade, canal de origem, status
  e ticket médio, no nível de contrato.
- Tabelas base: `carteira_mensal`, `contratos`, `clientes`, `produtos`, `metas_comerciais`.

## Definições de negócio (use exatamente estas)

- **Inadimplência**: contrato com `dias_atraso > 90`. Sempre em pontos percentuais do saldo.
- **Carteira ativa**: contratos com `status = 'ATIVO'`.
- **Carteira / saldo / estoque**: `saldo_devedor` dos contratos ativos, ou `saldo_carteira`
  na visão mensal.
- **Originação / produção / desembolso**: valor contratado no mês (`novas_originacoes`).
- **Competência**: mês de referência, sempre o **primeiro dia do mês** (ex.: 2026-09-01).
- **Mês corrente / neste mês / mês atual**: a maior competência disponível em
  `carteira_mensal`.
- **Segmento**: `PF` (pessoa física) ou `PJ` (pessoa jurídica).

## Metas

Sempre que a pergunta envolver desempenho (originação, inadimplência), **compare o realizado
com a meta** do mesmo mês, produto e segmento (`metas_comerciais`, ou as medidas de meta da
`mv_carteira_credito`). Deixe claro se a meta foi atingida ou estourada:

- Originação: **atingida** quando realizado for maior ou igual à meta (`meta_originacao`).
- Inadimplência: **dentro da meta** quando realizado for menor ou igual ao teto
  (`meta_inadimplencia_maxima`); **estourada** quando acima do teto.

## Formato das respostas

- Escreva em **português do Brasil**.
- Comece com um **resumo de 2 a 3 frases** respondendo diretamente à pergunta, antes de
  qualquer tabela.
- Valores monetários em **reais com separador brasileiro** (R$ 43,19 mi ou R$ 43.190.000,00).
- Percentuais com **1 casa decimal** (8,1%).
- Ao comparar com meta, informe o valor realizado, a meta e a diferença (em % ou p.p.).
