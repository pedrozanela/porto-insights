-- Metric views governadas do Porto Insights.
-- Alimentam a Genie Ontology: é por aqui que o Genie One entende carteira, originação,
-- inadimplência e metas sem precisar reinventar as regras de negócio em cada pergunta.
-- Idempotente: CREATE OR REPLACE.
--
-- Nota de engenharia: os relacionamentos entram por um SELECT achatado no `source`, não
-- por `joins`. A versão do engine de metric views deste workspace falha com
-- INVALID_EXTRACT_BASE_FIELD_TYPE quando duas dimensões referenciam o mesmo alias de join
-- (ex.: produto.nome e produto.linha). Achatar no source contorna isso e mantém as
-- dimensões referenciando apenas colunas simples.

CREATE OR REPLACE VIEW ${FQ}.mv_carteira_credito
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: >
  Carteira de crédito do Porto Bank por mês, produto e segmento, com metas comerciais do
  mesmo mês para comparação. Fonte única para perguntas sobre saldo da carteira, originação,
  inadimplência acima de 90 dias e atingimento de meta. Competência é sempre o primeiro dia do mês.
source: |
  SELECT c.competencia, c.segmento, c.saldo_carteira, c.novas_originacoes,
         c.inadimplencia_90d_percentual, c.quantidade_contratos,
         p.nome AS produto_nome, p.linha AS produto_linha,
         m.meta_originacao, m.meta_inadimplencia_maxima
  FROM ${FQ}.carteira_mensal c
  JOIN ${FQ}.produtos p
    ON c.produto_id = p.produto_id
  LEFT JOIN ${FQ}.metas_comerciais m
    ON c.produto_id = m.produto_id
   AND c.competencia = m.competencia
   AND c.segmento = m.segmento
dimensions:
  - name: Competência
    expr: competencia
    comment: Mês de referência da carteira, sempre no primeiro dia do mês.
    synonyms: [mes, competencia, período, data de referência]
  - name: Produto
    expr: produto_nome
    comment: "Nome comercial do produto (ex.: Capital de Giro PJ, Cartão Porto)."
    synonyms: [produto, nome do produto]
  - name: Linha de negócio
    expr: produto_linha
    comment: Linha de negócio do produto (Cartão de Crédito, Financiamento, Consórcio, Crédito, Crédito PJ).
    synonyms: [linha, linha de produto]
  - name: Segmento
    expr: segmento
    comment: Segmento do cliente atendido pelo produto - PF (pessoa física) ou PJ (pessoa jurídica).
    synonyms: [segmento, PF ou PJ, tipo de cliente]
measures:
  - name: Saldo da carteira
    expr: SUM(saldo_carteira)
    comment: Saldo devedor total da carteira no fim do mês, em reais.
    synonyms: [carteira, estoque, saldo, saldo devedor]
    format:
      type: currency
      currency_code: BRL
  - name: Originação
    expr: SUM(novas_originacoes)
    comment: Valor total contratado no mês, em reais.
    synonyms: [originação, produção, novas contratações, desembolso]
    format:
      type: currency
      currency_code: BRL
  - name: Inadimplência 90d %
    expr: SUM(saldo_carteira * inadimplencia_90d_percentual) / NULLIF(SUM(saldo_carteira), 0)
    comment: >
      Percentual do saldo da carteira com atraso acima de 90 dias, ponderado pelo saldo.
      Resultado em pontos percentuais (8.13 significa 8,13%).
    synonyms: [inadimplência, inadimplência 90 dias, NPL, atraso acima de 90 dias]
  - name: Quantidade de contratos
    expr: SUM(quantidade_contratos)
    comment: Quantidade de contratos ativos na carteira no mês.
    synonyms: [contratos, número de contratos, quantidade]
  - name: Meta de originação
    expr: SUM(meta_originacao)
    comment: Meta de originação do mês, em reais.
    synonyms: [meta, meta de produção]
    format:
      type: currency
      currency_code: BRL
  - name: Atingimento da meta de originação %
    expr: SUM(novas_originacoes) / NULLIF(SUM(meta_originacao), 0) * 100
    comment: >
      Originação realizada dividida pela meta do mês, em percentual. Acima de 100 significa
      que a meta foi superada.
    synonyms: [atingimento, atingimento de meta, "% da meta", realizado vs meta]
  - name: Teto de inadimplência da meta
    expr: SUM(saldo_carteira * meta_inadimplencia_maxima) / NULLIF(SUM(saldo_carteira), 0)
    comment: Teto de inadimplência 90d aceito na meta do mês, em pontos percentuais, ponderado pelo saldo.
    synonyms: [teto de inadimplência, limite de inadimplência]
  - name: Gap de inadimplência vs meta
    expr: >
      (SUM(saldo_carteira * inadimplencia_90d_percentual) - SUM(saldo_carteira * meta_inadimplencia_maxima))
      / NULLIF(SUM(saldo_carteira), 0)
    comment: >
      Inadimplência realizada menos o teto da meta, em pontos percentuais. Positivo significa
      que a inadimplência estourou a meta.
    synonyms: [gap de inadimplência, estouro de inadimplência, folga de inadimplência]
$$;

CREATE OR REPLACE VIEW ${FQ}.mv_contratos_credito
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: >
  Contratos individuais de crédito e consórcio do Porto Bank, com produto e cliente.
  Use para cortes que a carteira mensal não tem: UF, cidade, canal de origem, status do
  contrato e ticket médio. Inadimplência é definida como dias_atraso maior que 90.
source: |
  SELECT c.data_contratacao, c.valor_contratado, c.saldo_devedor, c.taxa_mensal,
         c.status, c.dias_atraso,
         p.nome AS produto_nome, p.linha AS produto_linha,
         cl.segmento, cl.uf, cl.cidade, cl.canal_origem
  FROM ${FQ}.contratos c
  JOIN ${FQ}.produtos p
    ON c.produto_id = p.produto_id
  JOIN ${FQ}.clientes cl
    ON c.cliente_id = cl.cliente_id
dimensions:
  - name: Data de contratação
    expr: data_contratacao
    comment: Data em que o contrato foi assinado.
    synonyms: [data de originação, data do contrato]
  - name: Mês de contratação
    expr: DATE_TRUNC('MONTH', data_contratacao)
    comment: Primeiro dia do mês em que o contrato foi assinado.
    synonyms: [competencia de originação, mes de contratação]
  - name: Produto
    expr: produto_nome
    comment: Nome comercial do produto contratado.
    synonyms: [produto]
  - name: Linha de negócio
    expr: produto_linha
    comment: Linha de negócio do produto.
    synonyms: [linha]
  - name: Segmento
    expr: segmento
    comment: Segmento do cliente - PF ou PJ.
    synonyms: [segmento, PF ou PJ]
  - name: UF
    expr: uf
    comment: Unidade federativa do cliente (sigla de 2 letras).
    synonyms: [estado, uf, unidade federativa]
  - name: Cidade
    expr: cidade
    comment: Cidade do cliente.
    synonyms: [cidade, município]
  - name: Canal de origem
    expr: canal_origem
    comment: Canal pelo qual o cliente foi originado (Agência, App, Site, Corretor Parceiro, Telefone).
    synonyms: [canal, canal de aquisição]
  - name: Status do contrato
    expr: status
    comment: Situação do contrato - ATIVO, LIQUIDADO ou CANCELADO. Carteira ativa é status ATIVO.
    synonyms: [status, situação do contrato]
measures:
  - name: Valor contratado
    expr: SUM(valor_contratado)
    comment: Soma do valor contratado, em reais.
    synonyms: [valor contratado, originação, produção]
    format:
      type: currency
      currency_code: BRL
  - name: Saldo devedor
    expr: SUM(saldo_devedor)
    comment: Soma do saldo devedor atual, em reais.
    synonyms: [saldo, saldo devedor, carteira]
    format:
      type: currency
      currency_code: BRL
  - name: Quantidade de contratos
    expr: COUNT(1)
    comment: Quantidade de contratos.
    synonyms: [contratos, quantidade]
  - name: Ticket médio
    expr: SUM(valor_contratado) / NULLIF(COUNT(1), 0)
    comment: Valor contratado médio por contrato, em reais.
    synonyms: [ticket médio, valor médio]
    format:
      type: currency
      currency_code: BRL
  - name: Taxa média mensal %
    expr: SUM(valor_contratado * taxa_mensal) / NULLIF(SUM(valor_contratado), 0) * 100
    comment: Taxa de juros mensal média ponderada pelo valor contratado, em percentual.
    synonyms: [taxa média, juros médio]
  - name: Inadimplência 90d %
    expr: SUM(CASE WHEN dias_atraso > 90 THEN saldo_devedor ELSE 0 END) / NULLIF(SUM(saldo_devedor), 0) * 100
    comment: >
      Percentual do saldo devedor em contratos com mais de 90 dias de atraso, em pontos percentuais.
    synonyms: [inadimplência, inadimplência 90 dias, NPL]
$$;
