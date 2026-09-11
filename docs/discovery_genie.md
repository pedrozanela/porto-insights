# Validação do Genie One — perguntas da demo


## Execução 1

### 1. Como está a carteira de Capital de Giro PJ neste mês em relação à meta de originação?
- **status:** completed (74.1s)
- **resposta:** ## Capital de Giro PJ — Originação vs Meta em Setembro/2026

A carteira de **Capital de Giro PJ** **superou a meta de originação** em setembro/2026, atingindo **118,0%** do objetivo. O valor originado foi de **R$ 43,19 mi** contra uma meta de **R$ 36,60 mi**, resultando em um excedente de **R$ 6,59 mi** acima do planejado. [Query Result](https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/00ca9602ff3d4a82b33e0405e5b7d581?o=7474645447198052#embed-query_7fe7ce)

### Resumo do mês (set/2026)

| Indicador | Realizado | Meta | Diferença |
|---|---|---|---|
| **Originação** | R$ 43,19 mi | R$ 36,60 mi | +R$ 6,59 mi (**+18,0%**) |
| **Inadimplência 90d** | 8,1% | 6,7% (teto) | +1,4 p.p. (estourada) |
| **Saldo da carteira** | R$ 277,88 mi | — | — |
| **Contratos ativos** | 305 | — | — |

### Ponto de atenção: inadimplência

Embora a originação esteja acima da meta, a **inadimplência 90d está em 8,1%**, acima do teto de **6,7%** definido na meta — um estouro de **1,4 p.p.**. Isso indica que, apesar do bom desempenho comercial, a qualidade da carteira merece acompanhamento. [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)

### Evolução dos últimos 6 meses| Competência | Originação | Meta de originação | Atingimento % |
| --- | --- | --- | --- |
| 2026-04-01 | 14599700.00 | 14486886.70 | 100.778727 |
| 2026-05-01 | 16209100.00 | 16631093.36 | 97.462624 |
| 2026-06-01 | 16118300.00 | 15868933.24 | 101.571415 |
| 2026-07-01 | 47886300.00 | 49877291.38 | 96.008221 |
| 2026-08-01 | 50694600.00 | 49865093.62 | 101.663501 |
| 2026-09-01 | 43190900.00 | 36602457.63 | 118.000000 |Nos últimos seis meses, a originação ficou acima da meta em quatro deles (abr, jun, ago e set). Setembro registra o **melhor atingimento do período** (118,0%), impulsionado por uma combinação de originação robusta e meta mais conservadora em relação aos meses anteriores.
- **SQL:** `SELECT `Competência`, MEASURE(`Originação`) AS `Originação`, MEASURE(`Meta de originação`) AS `Meta de originação`, MEASURE(`Atingimento da meta de originação %`) AS `Atingimento %` FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` WHERE `Produto` = 'Capital de Giro PJ' AND `Competência` >= '2026-04-01' AND `Competência` <= '2026-09-01' GROUP BY ALL ORDER BY `Competência` ASC`
- **Explore in Databricks:** https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/00ca9602ff3d4a82b33e0405e5b7d581?o=7474645447198052&utm_source=genie_chat_mcp

### 2. E a inadimplência 90d, por segmento?
- **status:** completed (33.1s)
- **resposta:** ## Inadimplência 90d por Segmento — Setembro/2026

O segmento **PF está dentro da meta**, com inadimplência de **3,4%** contra um teto de **3,9%** (folga de 0,5 p.p.). Já o segmento **PJ estourou a meta**, registrando **7,9%** contra um teto de **6,6%** — um gap de **+1,2 p.p.**. [Query Result](https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/00ca9602ff3d4a82b33e0405e5b7d581?o=7474645447198052#embed-query_93d654)| Segmento | Saldo da carteira | Inadimplência 90d % | Teto de inadimplência da meta | Gap de inadimplência vs meta |
| --- | --- | --- | --- | --- |
| PF | 114538891.41 | 3.446340 | 3.945442 | -0.499103 |
| PJ | 309201457.72 | 7.861526 | 6.618558 | 1.242968 |### Detalhe por produto

Dentro de cada segmento, todos os produtos PF operam com folga em relação ao teto. No PJ, o **Capital de Giro PJ** é o responsável pelo estouro, com inadimplência de **8,1%** vs teto de **6,7%** (+1,4 p.p.), enquanto **Antecipação de Recebíveis PJ** está marginalmente dentro da meta (5,5% vs 5,6%). [Query Result](https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/00ca9602ff3d4a82b33e0405e5b7d581?o=7474645447198052#embed-query_d3bbdb) [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)| Segmento | Produto | Saldo da carteira | Inadimplência 90d % | Teto de inadimplência da meta | Gap de inadimplência vs meta |
| --- | --- | --- | --- | --- | --- |
| PF | Consórcio Imobiliário | 59519260.62 | 1.920000 | 2.050000 | -0.130000 |
| PF | Financiamento de Veículos | 37622891.38 | 3.810000 | 4.550000 | -0.740000 |
| PF | Crédito Pessoal | 12437801.94 | 7.480000 | 8.510000 | -1.030000 |
| PF | Cartão Porto | 4958937.47 | 8.890000 | 10.660000 | -1.770000 |
| PJ | Capital de Giro PJ | 277875954.97 | 8.130000 | 6.730000 | 1.400000 |
| PJ | Antecipação de Recebíveis PJ | 31325502.75 | 5.480000 | 5.630000 | -0.150000 |O Capital de Giro PJ concentra **R$ 277,88 mi** dos R$ 309,20 mi do saldo PJ (90%), o que faz com que sua inadimplência elevada domine o indicador consolidado do segmento.
- **SQL:** `SELECT `Segmento`, MEASURE(`Saldo da carteira`) AS `Saldo da carteira`, MEASURE(`Inadimplência 90d %`) AS `Inadimplência 90d %`, MEASURE(`Teto de inadimplência da meta`) AS `Teto de inadimplência da meta`, MEASURE(`Gap de inadimplência vs meta`) AS `Gap de inadimplência vs meta` FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` WHERE `Competência` = '2026-09-01' GROUP BY ALL ORDER BY `Segmento``
- **fontes citadas:** [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **Explore in Databricks:** https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/00ca9602ff3d4a82b33e0405e5b7d581?o=7474645447198052&utm_source=genie_chat_mcp

### 3. Qual o saldo total da carteira por produto no mês corrente?
- **status:** completed (48.8s)
- **resposta:** ## Saldo da Carteira por Produto — Setembro/2026

No mês corrente (competência **setembro/2026**), o saldo total da carteira do Porto Bank é de **R$ 423,74 mi**, distribuído entre seis produtos. O **Capital de Giro PJ** concentra a maior parte, com quase dois terços do saldo total.

| Produto | Saldo da Carteira |
|---|---|
| Capital de Giro PJ | R$ 277.875.954,97 |
| Consórcio Imobiliário | R$ 59.519.260,62 |
| Financiamento de Veículos | R$ 37.622.891,38 |
| Antecipação de Recebíveis PJ | R$ 31.325.502,75 |
| Crédito Pessoal | R$ 12.437.801,94 |
| Cartão Porto | R$ 4.958.937,47 |
| **Total** | **R$ 423.740.349,13** || Produto | saldo_carteira |
| --- | --- |
| Capital de Giro PJ | 277875954.97 |
| Consórcio Imobiliário | 59519260.62 |
| Financiamento de Veículos | 37622891.38 |
| Antecipação de Recebíveis PJ | 31325502.75 |
| Crédito Pessoal | 12437801.94 |
| Cartão Porto | 4958937.47 |Fonte: metric view `mv_carteira_credito` [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **SQL:** `SELECT MAX(`Competência`) AS `mes_corrente`, MEASURE(`Saldo da carteira`) AS `saldo_total` FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` WHERE `Competência` = ( SELECT MAX(`Competência`) FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` ) GROUP BY ALL`
- **fontes citadas:** [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **Explore in Databricks:** https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/7fce7914249e4346b6bb4c334f24c1b4?o=7474645447198052&utm_source=genie_chat_mcp

### 4. Qual produto teve a maior originação neste mês?
- **status:** completed (48.7s)
- **resposta:** ## Capital de Giro PJ lidera a originação em setembro/2026

O produto com maior originação no mês corrente (setembro/2026) é o **Capital de Giro PJ**, com **R$ 43,19 mi** — superando a meta de R$ 36,60 mi em **18,0%**. É, de longe, o maior volume entre todos os produtos do Porto Bank neste mês.

### Originação por produto — setembro/2026| Produto | Segmento | originacao | meta_originacao | atingimento_pct |
| --- | --- | --- | --- | --- |
| Capital de Giro PJ | PJ | 43190900.00 | 36602457.63 | 118.000000 |
| Antecipação de Recebíveis PJ | PJ | 8085400.00 | 8120209.47 | 99.571323 |
| Consórcio Imobiliário | PF | 6077200.00 | 5937656.98 | 102.350136 |
| Financiamento de Veículos | PF | 5356900.00 | 5225717.39 | 102.510327 |
| Crédito Pessoal | PF | 1815500.00 | 1714929.00 | 105.864441 |
| Cartão Porto | PF | 977200.00 | 1063063.11 | 91.923047 || Produto | Segmento | Originação | Meta | Atingimento |
|---|---|---|---|---|
| **Capital de Giro PJ** | PJ | R$ 43,19 mi | R$ 36,60 mi | 118,0% ✅ |
| Antecipação de Recebíveis PJ | PJ | R$ 8,09 mi | R$ 8,12 mi | 99,6% ❌ |
| Consórcio Imobiliário | PF | R$ 6,08 mi | R$ 5,94 mi | 102,4% ✅ |
| Financiamento de Veículos | PF | R$ 5,36 mi | R$ 5,23 mi | 102,5% ✅ |
| Crédito Pessoal | PF | R$ 1,82 mi | R$ 1,71 mi | 105,9% ✅ |
| Cartão Porto | PF | R$ 0,98 mi | R$ 1,06 mi | 91,9% ❌ |

### Destaques

- **5 de 6 produtos** atingiram ou superaram a meta de originação.
- Os dois produtos que ficaram abaixo da meta são **Antecipação de Recebíveis PJ** (faltaram R$ 35 mil, praticamente na meta) e **Cartão Porto** (8,1 p.p. abaixo da meta).
- O segmento **PJ** concentra o maior volume absoluto, puxado pelo Capital de Giro.

[pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **SQL:** `SELECT `Produto`, `Segmento`, MEASURE(`Originação`) AS `originacao`, MEASURE(`Meta de originação`) AS `meta_originacao`, MEASURE(`Atingimento da meta de originação %`) AS `atingimento_pct` FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` WHERE `Competência` = '2026-09-01' GROUP BY ALL ORDER BY `originacao` DESC`
- **fontes citadas:** [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **Explore in Databricks:** https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/5c96bf845b8540b1a093511375cf8b56?o=7474645447198052&utm_source=genie_chat_mcp

### 5. A inadimplência de Capital de Giro PJ está acima do teto da meta neste mês?
- **status:** completed (54.8s)
- **resposta:** ## Sim — a inadimplência de Capital de Giro PJ está acima do teto da meta

Em **setembro/2026** (mês corrente), a inadimplência 90 dias do produto **Capital de Giro PJ** atingiu **8,1 p.p.**, enquanto o teto da meta é de **6,7 p.p.** — um estouro de **+1,4 p.p.** acima do limite aceito.

| Indicador | Valor |
|---|---|
| Inadimplência realizada (90d) | 8,1% |
| Teto da meta | 6,7% |
| Gap (estouro) | +1,4 p.p. |
| Saldo da carteira | R$ 277,9 mi || Competência | Produto | Segmento | inadimplencia_realizada | teto_meta | gap_inadimplencia | saldo_carteira |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-01 | Capital de Giro PJ | PJ | 8.130000 | 6.730000 | 1.400000 | 277875954.97 |A meta de inadimplência é considerada **estourada** quando o realizado supera o teto máximo do mês. Neste caso, o gap positivo de 1,4 p.p. confirma que o produto está fora do limite aceitável. [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **SQL:** `SELECT `Competência`, `Produto`, `Segmento`, MEASURE(`Inadimplência 90d %`) AS `inadimplencia_realizada`, MEASURE(`Teto de inadimplência da meta`) AS `teto_meta`, MEASURE(`Gap de inadimplência vs meta`) AS `gap_inadimplencia`, MEASURE(`Saldo da carteira`) AS `saldo_carteira` FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` WHERE `Produto` = 'Capital de Giro PJ' AND `Competência` = ( SELECT MAX(`Competência`) FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` ) GROUP BY ALL`
- **fontes citadas:** [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **Explore in Databricks:** https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/e7929939a7ea4f958e3f1b0ed035baaa?o=7474645447198052&utm_source=genie_chat_mcp


## Execução 2

### 1. Como está a carteira de Capital de Giro PJ neste mês em relação à meta de originação?
- **status:** completed (67.0s)
- **resposta:** ## Capital de Giro PJ — Originação vs Meta em Setembro/2026

A originação de **Capital de Giro PJ** em setembro/2026 foi de **R$ 43,19 mi**, superando a meta de **R$ 36,60 mi** com um atingimento de **118,0%** — a meta foi **atingida e superada** com folga de R$ 6,59 mi. [Query Result](https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/7d8a303b37d0430ebf6f58b1dd3d44af?o=7474645447198052#embed-query_bff6fa)

### Resumo do mês corrente

| Indicador | Valor |
|---|---|
| Originação realizada | R$ 43.190.900,00 |
| Meta de originação | R$ 36.602.457,63 |
| Atingimento | 118,0% ✅ |
| Saldo da carteira | R$ 277,88 mi |
| Inadimplência 90d | 8,1% |
| Teto de inadimplência (meta) | 6,7% |
| Gap de inadimplência | +1,4 p.p. ⚠️ |
| Contratos ativos | 305 |

### Contexto: evolução dos últimos 3 meses| Competência | originacao | meta_originacao | atingimento_pct | saldo_carteira | inadimplencia_90d |
| --- | --- | --- | --- | --- | --- |
| 2026-07-01 | 47886300.00 | 49877291.38 | 96.008221 | 215460295.61 | 5.250000 |
| 2026-08-01 | 50694600.00 | 49865093.62 | 101.663501 | 251337161.87 | 5.420000 |
| 2026-09-01 | 43190900.00 | 36602457.63 | 118.000000 | 277875954.97 | 8.130000 |A originação vinha abaixo da meta em julho (96,0%), recuperou em agosto (101,7%) e acelerou em setembro (118,0%). Apesar do bom desempenho em originação, a **inadimplência 90d subiu de 5,3% em julho para 8,1% em setembro**, estourando o teto da meta em **1,4 p.p.** — ponto que merece atenção. [Query Result](https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/7d8a303b37d0430ebf6f58b1dd3d44af?o=7474645447198052#embed-query_f3e254)

Fonte: metric view `mv_carteira_credito` do Porto Bank. [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **SQL:** `SELECT `Competência`, MEASURE(`Originação`) AS `originacao`, MEASURE(`Meta de originação`) AS `meta_originacao`, MEASURE(`Atingimento da meta de originação %`) AS `atingimento_pct`, MEASURE(`Saldo da carteira`) AS `saldo_carteira`, MEASURE(`Inadimplência 90d %`) AS `inadimplencia_90d` FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` WHERE `Produto` = 'Capital de Giro PJ' AND `Competência` >= '2026-07-01' AND `Competência` <= '2026-09-01' GROUP BY ALL ORDER BY `Competência` ASC`
- **Explore in Databricks:** https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/7d8a303b37d0430ebf6f58b1dd3d44af?o=7474645447198052&utm_source=genie_chat_mcp

### 2. E a inadimplência 90d, por segmento?
- **status:** completed (39.7s)
- **resposta:** ## Inadimplência 90d por Segmento — Setembro/2026

O segmento **PF está dentro da meta**, com inadimplência de **3,4%** contra um teto de 3,9% (folga de 0,5 p.p.). Já o segmento **PJ estourou a meta**, com inadimplência de **7,9%** contra um teto de 6,6% — gap de **+1,2 p.p.** [Query Result](https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/7d8a303b37d0430ebf6f58b1dd3d44af?o=7474645447198052#embed-query_03abdf)

### Visão consolidada por segmento

| Segmento | Saldo da Carteira | Inadimplência 90d | Teto (Meta) | Gap | Status |
|---|---|---|---|---|---|
| PF | R$ 114,54 mi | 3,4% | 3,9% | −0,5 p.p. | ✅ Dentro da meta |
| PJ | R$ 309,20 mi | 7,9% | 6,6% | +1,2 p.p. | ⚠️ Acima da meta |

### Detalhe por produto| Segmento | Produto | saldo_carteira | inadimplencia_90d | teto_inadimplencia | gap_inadimplencia |
| --- | --- | --- | --- | --- | --- |
| PF | Cartão Porto | 4958937.47 | 8.890000 | 10.660000 | -1.770000 |
| PF | Crédito Pessoal | 12437801.94 | 7.480000 | 8.510000 | -1.030000 |
| PF | Financiamento de Veículos | 37622891.38 | 3.810000 | 4.550000 | -0.740000 |
| PF | Consórcio Imobiliário | 59519260.62 | 1.920000 | 2.050000 | -0.130000 |
| PJ | Capital de Giro PJ | 277875954.97 | 8.130000 | 6.730000 | 1.400000 |
| PJ | Antecipação de Recebíveis PJ | 31325502.75 | 5.480000 | 5.630000 | -0.150000 |No **PF**, todos os quatro produtos estão dentro do teto de inadimplência, com destaque para **Consórcio Imobiliário** (1,9%, folga de 0,1 p.p.) e **Financiamento de Veículos** (3,8%, folga de 0,7 p.p.).

No **PJ**, o problema está concentrado em **Capital de Giro PJ** (8,1% vs teto de 6,7%, gap de +1,4 p.p.), que responde por 90% do saldo PJ. A **Antecipação de Recebíveis PJ** está marginalmente dentro da meta (5,5% vs teto de 5,6%). [Query Result](https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/7d8a303b37d0430ebf6f58b1dd3d44af?o=7474645447198052#embed-query_51dc5b)

Fonte: [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **SQL:** `SELECT `Segmento`, MEASURE(`Saldo da carteira`) AS `saldo_carteira`, MEASURE(`Inadimplência 90d %`) AS `inadimplencia_90d`, MEASURE(`Teto de inadimplência da meta`) AS `teto_inadimplencia`, MEASURE(`Gap de inadimplência vs meta`) AS `gap_inadimplencia` FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` WHERE `Competência` = '2026-09-01' GROUP BY ALL ORDER BY `Segmento``
- **fontes citadas:** [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **Explore in Databricks:** https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/7d8a303b37d0430ebf6f58b1dd3d44af?o=7474645447198052&utm_source=genie_chat_mcp

### 3. Qual o saldo total da carteira por produto no mês corrente?
- **status:** completed (48.2s)
- **resposta:** ## Saldo da Carteira por Produto — Setembro/2026

No mês corrente (competência **setembro/2026**), o saldo total da carteira do Porto Bank é de **R$ 423,74 mi**. O **Capital de Giro PJ** lidera com ampla margem, representando cerca de dois terços do estoque total.

| Produto | Saldo da Carteira |
|---|---|
| Capital de Giro PJ | R$ 277.875.954,97 |
| Consórcio Imobiliário | R$ 59.519.260,62 |
| Financiamento de Veículos | R$ 37.622.891,38 |
| Antecipação de Recebíveis PJ | R$ 31.325.502,75 |
| Crédito Pessoal | R$ 12.437.801,94 |
| Cartão Porto | R$ 4.958.937,47 |
| **Total** | **R$ 423.740.349,13** || Produto | Saldo da carteira |
| --- | --- |
| Capital de Giro PJ | 277875954.97 |
| Consórcio Imobiliário | 59519260.62 |
| Financiamento de Veículos | 37622891.38 |
| Antecipação de Recebíveis PJ | 31325502.75 |
| Crédito Pessoal | 12437801.94 |
| Cartão Porto | 4958937.47 |Fonte: metric view `mv_carteira_credito` [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **SQL:** `SELECT MEASURE(`Saldo da carteira`) AS `Saldo total da carteira` FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` WHERE `Competência` = '2026-09-01' GROUP BY ALL`
- **fontes citadas:** [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **Explore in Databricks:** https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/88298308e6e343b690eef75c1f231870?o=7474645447198052&utm_source=genie_chat_mcp

### 4. Qual produto teve a maior originação neste mês?
- **status:** completed (51.3s)
- **resposta:** ## Capital de Giro PJ lidera a originação em setembro/2026

O produto com a **maior originação** no mês corrente (setembro/2026) é o **Capital de Giro PJ**, com **R$ 43,19 mi** — superando a meta de R$ 36,60 mi em **18,0%**. É, de longe, o maior volume entre os seis produtos do Porto Bank.

### Originação por produto — Set/2026| Produto | Segmento | originacao | meta_originacao | atingimento_pct |
| --- | --- | --- | --- | --- |
| Capital de Giro PJ | PJ | 43190900.00 | 36602457.63 | 118.000000 |
| Antecipação de Recebíveis PJ | PJ | 8085400.00 | 8120209.47 | 99.571323 |
| Consórcio Imobiliário | PF | 6077200.00 | 5937656.98 | 102.350136 |
| Financiamento de Veículos | PF | 5356900.00 | 5225717.39 | 102.510327 |
| Crédito Pessoal | PF | 1815500.00 | 1714929.00 | 105.864441 |
| Cartão Porto | PF | 977200.00 | 1063063.11 | 91.923047 |### Destaques

- **Capital de Giro PJ** concentra mais da metade da originação total e foi o produto que mais superou a meta em termos absolutos (+R$ 6,59 mi).
- **Cartão Porto** é o único produto **abaixo da meta** (91,9% de atingimento), com R$ 977,2 mil originados contra uma meta de R$ 1,06 mi.
- Todos os demais produtos atingiram ou superaram suas metas no mês. [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **SQL:** `SELECT `Produto`, `Segmento`, MEASURE(`Originação`) AS `originacao`, MEASURE(`Meta de originação`) AS `meta_originacao`, MEASURE(`Atingimento da meta de originação %`) AS `atingimento_pct` FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` WHERE `Competência` = '2026-09-01' GROUP BY ALL ORDER BY `originacao` DESC`
- **fontes citadas:** [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **Explore in Databricks:** https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/42f471b88a974545825f5e93814aa027?o=7474645447198052&utm_source=genie_chat_mcp

### 5. A inadimplência de Capital de Giro PJ está acima do teto da meta neste mês?
- **status:** completed (42.3s)
- **resposta:** ## Inadimplência de Capital de Giro PJ — Setembro/2026

**Sim, a inadimplência de Capital de Giro PJ está acima do teto da meta neste mês.** O realizado ficou em **8,1 p.p.**, contra um teto de **6,7 p.p.**, resultando em um estouro de **+1,4 p.p.** acima do limite aceito.

| Indicador | Valor |
|---|---|
| Inadimplência realizada (90d) | 8,1% |
| Teto da meta | 6,7% |
| Gap (estouro) | +1,4 p.p. || Competência | Produto | Segmento | inadimplencia_realizada | teto_meta | gap_inadimplencia |
| --- | --- | --- | --- | --- | --- |
| 2026-09-01 | Capital de Giro PJ | PJ | 8.130000 | 6.730000 | 1.400000 |Fonte: [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052) — competência setembro/2026.
- **SQL:** `SELECT `Competência`, `Produto`, `Segmento`, MEASURE(`Inadimplência 90d %`) AS `inadimplencia_realizada`, MEASURE(`Teto de inadimplência da meta`) AS `teto_meta`, MEASURE(`Gap de inadimplência vs meta`) AS `gap_inadimplencia` FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` WHERE `Produto` = 'Capital de Giro PJ' AND `Competência` = ( SELECT MAX(`Competência`) FROM `pzanela_classic_aws_catalog`.`porto_insights`.`mv_carteira_credito` ) GROUP BY ALL`
- **fontes citadas:** [pzanela_classic_aws_catalog.porto_insights.mv_carteira_credito](https://fevm-pzanela-classic-aws.cloud.databricks.com/explore/data/pzanela_classic_aws_catalog/porto_insights/mv_carteira_credito?isDbOne=true&utm_source=one-chat&o=7474645447198052)
- **Explore in Databricks:** https://fevm-pzanela-classic-aws.cloud.databricks.com/one/chat/threads/73d31d14dc4f47a2aa62e97467a6c4e4?o=7474645447198052&utm_source=genie_chat_mcp
