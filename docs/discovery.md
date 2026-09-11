# Fase 0 — Descoberta e provisionamento

Ambiente descoberto e provisionado para o **Porto Insights** no workspace de field
engineering. Todos os valores abaixo foram confirmados por chamada real (não presumidos).

## Workspace e autenticação

| Item | Valor |
| --- | --- |
| Host | `fevm-pzanela-classic-aws.cloud.databricks.com` |
| Org ID | `7474645447198052` |
| Profile CLI (dev local) | `fevm-pzanela-classic-aws` |
| Usuário validado | `pedro.zanela@databricks.com` (admin) |
| Expira | 2026-10-07 |

> Observação sobre o prompt original: o profile chamado de `FEVM` **não existe** no
> `~/.databrickscfg`; o profile correto é `fevm-pzanela-classic-aws`. O código lê
> `DATABRICKS_CONFIG_PROFILE` (padrão `fevm-pzanela-classic-aws`).

## SQL Warehouse (Statement Execution + `_meta.warehouse_id` do Genie)

| Warehouse | ID | Tipo | Uso |
| --- | --- | --- | --- |
| Serverless Starter Warehouse | `848374d85d2bad86` | PRO serverless, X-Large | seed, metric views, `_meta.warehouse_id` do Genie |

Escolhido por ser serverless (sem cluster) e já disponível. Alternativas serverless:
`warehouse_principal` (`1f1cd7a4c3054941`).

## Endpoints de modelo (chat com tool calling)

Todos testados com um `tools/tool_choice` real (a tool `genie__ask`) — devem devolver
`tool_calls` bem-formados. Resultado do teste:

| Endpoint | Rótulo | Tool calling |
| --- | --- | --- |
| `databricks-claude-sonnet-5` | Claude Sonnet 5 | OK |
| `databricks-claude-opus-5` | Claude Opus 5 | OK |
| `databricks-claude-haiku-4-5` | Claude Haiku 4.5 | OK |
| `databricks-gpt-5-5` | GPT-5.5 | OK |
| `databricks-gpt-5-4` | GPT-5.4 | OK |
| `databricks-gemini-3-8-flash` | Gemini 3.8 Flash | OK |
| `databricks-llama-4-maverick` | Llama 4 Maverick | OK |
| `databricks-grok-4-6` | Grok 4.6 | OK |

`databricks-gemini-2-5-pro` está **deprecado** (BAD_REQUEST) — não usar. Há endpoints GPT
nativos (`databricks-gpt-5-*`), então **não** foi preciso criar endpoint de modelo externo.

**Proposta de configuração:**
```
MODEL_ENDPOINTS=databricks-claude-sonnet-5:Claude Sonnet 5,databricks-claude-opus-5:Claude Opus 5,databricks-gpt-5-5:GPT-5.5,databricks-gemini-3-8-flash:Gemini 3.8 Flash,databricks-llama-4-maverick:Llama 4 Maverick
DEFAULT_MODEL_ENDPOINT=databricks-claude-sonnet-5
```
Base OpenAI-compatible: `https://{host}/serving-endpoints`, `api_key` = token OBO do usuário.

## Genie One MCP

- **URL:** `https://{host}/api/2.0/mcp/genie` — respondeu `initialize` (serverInfo
  `genie_chat` v1.0.0, protocolo `2025-11-25`). Preview **Managed MCP Servers** já habilitado.
- **Scope OBO:** `genie`.
- **Tools reais** (via `tools/list`): `genie_ask`, `genie_poll_response`,
  `genie_get_query_result`, `genie_cancel_response`. **Não existe `view_ask`** neste servidor
  (a doc mencionava; ignorar).
- **`_meta`:** confirmado; `genie_ask` aceita `question` e `conversation_id` (opcional).
  O `_meta.warehouse_id` é aceito para roteamento determinístico ao warehouse.
- **Máquina de estados confirmada:** `genie_ask` (host de polling, sem `progressToken`)
  devolve `{response_id, conversation_id, status: in_progress}`; `genie_poll_response`
  devolve `structured_content` (snake_case!) com `status`, `deep_link`, `final_answer`,
  `progress_steps`, `narration_instruction`, `query_items[].{item_id, sql}`. Terminais:
  `completed` / `incomplete` / `failed`. `genie_get_query_result` devolve `columns`, `rows`,
  `total_row_count`, `truncated` — validado.
- **Cadência de polling:** doc recomenda 2–5 s entre polls; turnos completam em ~70–260 s.
  Config: `GENIE_POLL_INITIAL_MS=1500`, `GENIE_POLL_MAX_MS=5000`, `GENIE_MAX_WAIT_S=260`.
- **Atenção de implementação:** o campo é `structured_content` (snake_case) no pacote `mcp`
  2.x — não `structuredContent`. `InitializeResult.server_info`, `Tool.input_schema` também
  são snake_case nesta versão.

### `_meta.progressToken` (streaming) — achado não documentado
`genie_ask` tem duas formas: se o host anexa `_meta.progressToken`, o servidor segura a
conexão e **streama notificações de progresso**, devolvendo a resposta final na mesma
chamada (não chamar `genie_poll_response` depois). Sem `progressToken`, é o fluxo de polling.
Na POC usamos **polling** (mais simples de instrumentar no trace); o streaming fica como
otimização futura.

## MCP Services Google (`system.ai.*`)

- **URL:** `https://{host}/ai-gateway/mcp-services/system.ai.{service}` — transporte
  Streamable HTTP, token OBO no header `Authorization: Bearer`.
- **Scope OBO:** `ai-gateway`.
- **Serviços confirmados** (via `tools/list` + `tools/call` real retornando dados):
  - `system.ai.gmail` → `gmail_search`, `gmail_read_message`, `gmail_search_threads`,
    `gmail_get_thread`, `gmail_list_drafts`, `gmail_list_labels` (todos **read-only** na
    superfície exposta; as tools de escrita exigem escopo `gmail.modify` e não aparecem).
  - `system.ai.google_calendar` → `calendar_event_list`, `calendar_event_get`,
    `calendar_freebusy_query`, `calendar_calendar_list`.
  - `system.ai.google_drive` → `google_drive_search`, `google_drive_list_recent`,
    `google_file_read`, `google_file_download`, `google_file_metadata`,
    `google_file_permissions`.
- **OAuth do Google:** já autorizado para `pedro.zanela@databricks.com` — as três chamadas
  reais retornaram dados (agenda, emails, arquivos). Outros usuários precisam fazer o Login
  OAuth único no Catalog Explorer antes da primeira chamada.
- **Grant:** os `system.ai.*` **não** são funções UC (a API de permissions de function
  retorna `RESOURCE_DOES_NOT_EXIST`). A validação prática de acesso é uma `tools/call` real
  retornando dados. Para outros usuários, o acesso é por grant no serviço + Login OAuth.
- **Superfície read-only confirmada:** nenhuma tool de escrita (send/create/update/delete)
  foi exposta pelos três serviços — a service policy built-in bloqueia escrita. Mesmo assim
  mantemos allowlist read-only no backend (defesa em profundidade).

## Dados sintéticos

- Schema: **`pzanela_classic_aws_catalog.porto_insights`** (o catálogo `porto_insights` não
  pôde ser criado; usamos o catálogo padrão do FEVM).
- Tabelas: `clientes`, `produtos`, `contratos` (2.400 linhas), `carteira_mensal`,
  `metas_comerciais`. Geradas por `scripts/seed_data.py` (Faker pt_BR, seed fixa, idempotente).
- Metric views: `mv_carteira_credito` (108 linhas na base) e `mv_contratos_credito`
  (2.400 linhas), via `scripts/create_metric_views.py`.
- **Gotcha de metric view (importante):** o engine deste workspace falha com
  `INVALID_EXTRACT_BASE_FIELD_TYPE` quando duas dimensões referenciam o mesmo alias de
  `join` (ex.: `produto.nome` e `produto.linha`). Solução: achatar os relacionamentos num
  `source: SELECT ...` e referenciar só colunas simples. Também: comments com `: ` e itens
  de lista começando com `%` precisam de aspas no YAML.

### Números-chave do mês corrente (setembro/2026) — para a semente de demo no Google
- **Capital de Giro PJ:** originação **R$ 43,19 mi** vs meta **R$ 36,60 mi** → **118%** da meta.
- **Inadimplência 90d Capital de Giro PJ:** **8,1%** vs teto da meta **6,7%** → estourou (+1,4 p.p.).
- **Inadimplência por segmento:** PF **3,4%** (dentro do teto 3,9%), PJ **7,9%** (acima).
- **Saldo total da carteira:** **R$ 423,74 mi**.

## Instruções de workspace e Genie Agent

- `/Workspace/.genie_workspace_instructions.md` publicado (2.878 caracteres, limite 20.000)
  via `scripts/publish_workspace_instructions.py`. Aplica-se ao chat do Genie One (não a Agents).
- Genie Agent de suporte **`Porto Bank — Carteira e Crédito`** criado:
  `01f1ad73d67f170899b3728094274c9a`
  (`https://{host}/genie/rooms/01f1ad73d67f170899b3728094274c9a`), via
  `scripts/create_genie_agent.py` (flag `CREATE_SUPPORT_GENIE_AGENT`, idempotente por título).
  - Notas de API: benchmarks foram omitidos (o enum `BenchmarkAnswerFormat=TEXT` é inválido e
    o benchmark exige `answer`); `example_question_sqls` precisam de `id` ordenável em hex de
    32 chars (usamos `format(n, "032x")`).

## Validação do Genie One (as 5 perguntas da demo)

Rodadas via MCP com o meu token (`scripts/validate_genie_one.py`). Relatório detalhado em
[discovery_genie.md](discovery_genie.md). Resultado da 1ª execução: **5/5 corretas**, com
os números batendo com a base, e o follow-up (pergunta 2) continuou a mesma conversa.
Estabilidade em 2 execuções: ver `discovery_genie.md`.

| # | Pergunta | Correta |
| --- | --- | --- |
| 1 | Carteira de Capital de Giro PJ vs meta de originação | ✅ 118% |
| 2 | (follow-up) inadimplência 90d por segmento | ✅ PF 3,4% / PJ 7,9% |
| 3 | Saldo total da carteira por produto | ✅ R$ 423,74 mi |
| 4 | Produto com maior originação | ✅ Capital de Giro PJ |
| 5 | Inadimplência de Capital de Giro PJ vs teto | ✅ acima (8,1% vs 6,7%) |
