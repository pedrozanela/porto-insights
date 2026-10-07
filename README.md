# Porto Insights

Copiloto executivo do **Porto Bank** sobre Databricks. Um único app onde um executivo pergunta,
em linguagem natural, sobre **sua agenda, emails e documentos** (Google Workspace) e sobre os
**dados do banco** (carteira de crédito, inadimplência, metas) — e vê as **conexões entre tudo
isso crescerem num grafo interativo** ao longo da conversa.

POC de Field Engineering. Roda no workspace FEVM com **dados sintéticos** com cara de Porto Bank.
UI, conteúdo de demo e instruções em português; código em inglês.

## O que ele faz

- **Chat multi-modelo** via Unity AI Gateway (Claude, GPT, Gemini, Llama), com seletor de modelo.
- **Perguntas sobre dados** via **Genie One** (MCP gerenciado): escreve e roda SQL sobre o Unity
  Catalog, com card de tabela + SQL + fontes citadas + deep link, fundamentado na Genie Ontology
  (metric views + tabelas comentadas + instruções de workspace).
- **Agenda/emails/documentos** via **MCP Services built-in** do Databricks para o Google
  (`system.ai.gmail`, `system.ai.google_calendar`, `system.ai.google_drive`) — só leitura.
- **Grafo de relacionamentos** que cruza agenda ↔ pessoas ↔ email ↔ documento ↔ dados do Genie,
  com arestas determinísticas (pessoas em comum, links de Drive, proximidade temporal, fontes
  citadas) e semânticas (`related_to` inferidas pelo LLM).
- **Histórico persistente** de conversas (Lakebase Postgres).

## Arquitetura

- **Frontend:** React + TypeScript (TSX) + Tailwind **sem build e sem npm**: `frontend/src/` é código
  React comum, e o próprio navegador traduz cada `.tsx` para JS ao carregar (Sucrase via
  es-module-shims, ~20 ms no total). Servido como estático pelo FastAPI (processo único, uma porta).
  As bibliotecas (React, `react-force-graph-2d`, `react-markdown`, Tailwind v3 de navegador) ficam
  prontas em `frontend/vendor/`, mapeadas por um import map no `index.html` — nada é baixado da
  internet, nem no deploy nem no navegador. Sem checagem de tipos (os tipos só são removidos).
- **Backend:** FastAPI + Uvicorn (Python 3.11+). Loop de agente assíncrono com tool calling;
  streaming ao frontend via **SSE**.
- **Autenticação: 100% on-behalf-of-user (OBO).** Toda chamada a Model Serving, Genie One e
  MCP Services usa o token do usuário logado (header `x-forwarded-access-token`); o service
  principal do app só faz health check e conecta ao Lakebase (infra do app). Em dev local, cai
  para o profile do CLI.
- **Empacotamento:** Databricks Asset Bundle (`databricks.yml`, resource `app` com
  `user_api_scopes`) + `app.yaml`.

```
porto-insights/
  databricks.yml  app.yaml  requirements.txt  .env.example
  backend/    main.py config.py auth.py llm.py tracing.py lakebase.py
              mcp/  genie/  graph/  store/  agent/  tests/
  frontend/   index.html (import map + config do Tailwind + CSS global)
              src/ (components, state, api, graph, theme) — o app; é aqui que se edita
              vendor/ (bibliotecas prontas, geradas por scripts/build_vendor.sh — não editar)
              public/ (logo)  tests/ (vitest-compatíveis, rodam no node puro)
  scripts/    discover, publish_workspace_instructions, build_vendor, deploy, run_graph_golden
    sample-fevm/  SEED do demo do FEVM (dados sintéticos de crédito) — NÃO é parte do produto:
                  seed_data, create_metric_views(.sql), create_genie_agent, validate_genie_one, _sql
  docs/       discovery, prerequisites-checklist, demo-script, demo-seed-google
```

## Pré-requisitos

Ver `docs/prerequisites-checklist.md`. Resumo:
- Preview **Managed MCP Servers** habilitado (admin do workspace).
- Genie One configurado (metric views + `/Workspace/.genie_workspace_instructions.md` + Genie Agent).
- SQL warehouse serverless; endpoints de modelo com tool calling.
- Cada usuário faz o **Login OAuth** dos 3 serviços Google uma vez (Catalog Explorer → Login).
- Projeto **Lakebase** para o histórico (o app conecta como seu service principal).

## Setup (Fase 0 — provisionamento, idempotente)

```bash
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt faker
export DATABRICKS_CONFIG_PROFILE=fevm-pzanela-classic-aws

./.venv/bin/python scripts/discover.py                       # valida endpoints, warehouse, MCP
./.venv/bin/python scripts/publish_workspace_instructions.py # instruções do Genie One (template)

# Seed do DEMO do FEVM (dados sintéticos de crédito) — só para reproduzir a demonstração.
# Um banco real usa o próprio Genie Space com seus dados; NÃO precisa rodar isto.
./.venv/bin/python scripts/sample-fevm/seed_data.py --drop            # dados sintéticos
./.venv/bin/python scripts/sample-fevm/create_metric_views.py         # metric views governadas
CREATE_SUPPORT_GENIE_AGENT=true ./.venv/bin/python scripts/sample-fevm/create_genie_agent.py
./.venv/bin/python scripts/sample-fevm/validate_genie_one.py --runs 2 --md docs/discovery_genie.md
```

## Rodar localmente

```bash
# backend (o "usuário" em dev local é o dono do profile)
export MODEL_ENDPOINTS="databricks-claude-sonnet-5:Claude Sonnet 5,databricks-gpt-5-5:GPT-5.5"
export DEFAULT_MODEL_ENDPOINT="databricks-claude-sonnet-5"
./.venv/bin/python -m uvicorn backend.main:app --port 8000
# frontend: nada a rodar — abra http://localhost:8000. Edite frontend/src/ e recarregue a página.
```

Bibliotecas do frontend: só ao **adicionar/atualizar uma biblioteca** (nunca para editar telas),
rode `bash scripts/build_vendor.sh` (requer node + registry npm) — regenera `frontend/vendor/`
e versione o resultado.

## Deploy (Databricks Apps via DAB)

```bash
bash scripts/deploy.sh            # bundle deploy -t dev + run
```

### Deploy pelo próprio workspace (sem CLI)

Importe a pasta inteira do repo no Workspace e rode `notebooks/deploy_porto_insights.py` (cria o
Lakebase, publica o código e cria/atualiza o App). Para **alterar o frontend no workspace** (à mão
ou com o Genie Code), edite os `.tsx` em `frontend/src/` (React/JSX normal) e rode o notebook de
novo — não há build nem npm. Peça ao Genie Code para editar **só `frontend/src/`** (nunca
`frontend/vendor/`). Se uma edição quebrar a tela, o erro aparece no console do navegador (F12),
com o arquivo e a linha.

Na **primeira visita** de cada usuário, o Databricks pede consentimento dos scopes OBO
(`genie`, `model-serving`, `ai-gateway`). O histórico no Lakebase exige que o service principal
do app seja dono do schema `porto_insights` — ver `docs/prerequisites-checklist.md`.

## Testes

```bash
./.venv/bin/python -m pytest -q   # extratores, linker, allowlist, máquina de estados do Genie
node --import ./frontend/tests/register.mjs --test 'frontend/tests/*.test.ts'  # grafo (node puro, sem npm)
```

## Observabilidade (opcional)

Defina `MLFLOW_EXPERIMENT_PATH` para registrar um trace por turno (modelo, pergunta, nº de tool
calls, nº de nós do grafo). Vazio = desligado.

## Segurança

Read-only em tudo (agenda, email, drive, dados). OBO em todas as chamadas de dados/ferramentas.
Allowlist read-only no backend (defesa em profundidade). Tokens nunca são logados nem guardados
no frontend. Só o necessário dos resultados vai ao LLM. CORS fechado (mesmo host).
