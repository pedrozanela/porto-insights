# Semente de demo no Google Workspace

Tudo no Porto Insights é **read-only** — o app lê sua agenda, emails e Drive, mas não escreve.
Então **você** cria manualmente, no seu Google Workspace, os objetos abaixo antes da demo. O
conteúdo já está pronto para copiar e colar e é **coerente com os dados sintéticos** (mesmos
nomes de produto e números-chave de setembro/2026 que o Genie One responde).

Números de referência (batem com o Genie): **Capital de Giro PJ** — originação **R$ 43,19 mi**,
**118%** da meta; inadimplência 90d **8,1%** vs teto **6,7%** (gap **+1,4 p.p.**).

> Preencha os `<...>`. Onde pedir colegas, use 2 pessoas reais do seu workspace (você recebe/vê
> os emails). Crie tudo com a **sua** conta (a mesma logada no app).

---

## 1. Google Doc — "Pauta — Comitê de Crédito PJ (setembro/2026)"

Crie um Google Doc com esse título e este conteúdo:

```
Pauta — Comitê de Crédito PJ (setembro/2026)

1. Capital de Giro PJ — desempenho do mês
   - Originação de R$ 43,19 mi, atingindo 118% da meta (R$ 36,60 mi).
   - Ponto de atenção: inadimplência 90d em 8,1%, acima do teto de 6,7% da meta (+1,4 p.p.).

2. Diagnóstico da inadimplência
   - Avaliar se o estouro está concentrado em safras recentes de originação.
   - Comparar com Antecipação de Recebíveis PJ (dentro da meta).

3. Ações propostas
   - Revisar política de crédito para novas originações de Capital de Giro PJ.
   - Reforçar cobrança na faixa de 60–90 dias de atraso.

4. Decisão
   - Aprovar (ou não) o ajuste de apetite de risco para o 4º trimestre.
```

Depois de criar, **copie o link do Doc** (Compartilhar → Copiar link). Vai colar nos itens 2 e 3.
Deixe o compartilhamento pelo menos como "qualquer pessoa da organização com o link pode ver".

---

## 2. Evento de agenda — "Comitê de Crédito PJ — Porto Bank"

Crie um evento **para amanhã** (ou o próximo dia útil), com:

- **Título:** `Comitê de Crédito PJ — Porto Bank`
- **Convidados:** você + `<colega1@databricks.com>` + `<colega2@databricks.com>`
- **Descrição** (cole e troque o link):

```
Comitê mensal de crédito PJ. Pauta e números do mês em:
<COLAR_LINK_DO_DOC>

Foco: desempenho de Capital de Giro PJ (originação 118% da meta) e o ponto de atenção
na inadimplência (8,1% vs teto 6,7%).
```

---

## 3. Thread de email — assunto "Comitê de Crédito PJ — pauta e números"

Envie um email para os mesmos convidados (você pode enviar para si mesmo com os colegas em
cópia). Assunto: `Comitê de Crédito PJ — pauta e números`. Depois responda 1–2 vezes para virar
uma thread. Sugestão de conteúdo:

**Mensagem 1 (você):**
```
Pessoal, segue a pauta do Comitê de Crédito PJ de amanhã:
<COLAR_LINK_DO_DOC>

Destaque do mês: Capital de Giro PJ originou R$ 43,19 mi (118% da meta). O ponto de
atenção é a inadimplência 90d em 8,1%, acima do teto de 6,7%.
```

**Mensagem 2 (resposta de um colega, ou sua simulando):**
```
Obrigado. Vale abrir o diagnóstico da inadimplência por safra antes da decisão de apetite.
```

**Mensagem 3 (você):**
```
Combinado. Levo o comparativo com Antecipação de Recebíveis PJ, que está dentro da meta.
```

---

## Checklist antes da demo

- [ ] O Doc existe e o link abre.
- [ ] O evento de amanhã tem os convidados e a descrição com o link do Doc.
- [ ] A thread de email tem o assunto com "Comitê de Crédito PJ" e cita o link do Doc.
- [ ] Você está logado no app com a mesma conta Google e já fez o Login OAuth dos 3 serviços
      (Catalog Explorer → system.ai.gmail / google_calendar / google_drive → Login).
- [ ] Rodou o roteiro de `docs/demo-script.md` uma vez para pré-aquecer (o Genie leva ~60–90s).

## Por que isso faz o grafo "acender"

Com esses três objetos, ao rodar o cenário o app conecta:
- **evento ↔ pessoas** (convidados), **email ↔ pessoas** (remetente/destinatários) → pessoas em comum;
- **evento → documento** e **email → documento** (`links_to`, pelo link do Doc no corpo/descrição);
- **evento ↔ email** (`same_time_window`, pessoas em comum + proximidade de data);
- **resposta do Genie → `mv_carteira_credito`** (`cites`);
- e a aresta semântica **`related_to`** entre a resposta do Genie sobre a carteira e o evento do
  comitê, com a justificativa em português.
