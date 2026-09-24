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

- **Frontend:** React + TypeScript + Vite + Tailwind. Buildado e servido como estático pelo
  FastAPI (processo único, uma porta). Grafo com `react-force-graph-2d`.
- **Backend:** FastAPI + Uvicorn (Python 3.11+). Loop de agente assíncrono com tool calling;
  streaming ao frontend via **SSE**.
- **Autenticação: 100% on-behalf-of-user (OBO).** Toda chamada a Model Serving, Genie One e
  MCP Services usa o token do usuário logado (header `x-forwarded-access-token`); o service
  principal do app só faz health check e conecta ao Lakebase (infra do app). Em dev local, cai
  para o profile do CLI.
- **Empacotamento:** Databricks Asset Bundle (`databricks.yml`, resource `app` com
  `user_api_scopes`) + `app.yaml`. O build do frontend acontece antes do deploy.

```
porto-insights/
  databricks.yml  app.yaml  requirements.txt  .env.example
  backend/    main.py config.py auth.py llm.py tracing.py lakebase.py
              mcp/  genie/  graph/  store/  agent/  tests/
  frontend/   src/ (components, state, api, theme)
  scripts/    discover, publish_workspace_instructions, build_frontend, deploy, run_graph_golden
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

# frontend (outro terminal) — usa node@22; o Vite proxia /api para a 8000
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
cd frontend && npm install && npm run dev
```

## Deploy (Databricks Apps via DAB)

```bash
bash scripts/deploy.sh            # build do frontend + bundle deploy -t dev + run
```

Na **primeira visita** de cada usuário, o Databricks pede consentimento dos scopes OBO
(`genie`, `model-serving`, `ai-gateway`). O histórico no Lakebase exige que o service principal
do app seja dono do schema `porto_insights` — ver `docs/prerequisites-checklist.md`.

## Testes

```bash
./.venv/bin/python -m pytest -q   # extratores, linker, allowlist, máquina de estados do Genie
```

## Observabilidade (opcional)

Defina `MLFLOW_EXPERIMENT_PATH` para registrar um trace por turno (modelo, pergunta, nº de tool
calls, nº de nós do grafo). Vazio = desligado.

## Segurança

Read-only em tudo (agenda, email, drive, dados). OBO em todas as chamadas de dados/ferramentas.
Allowlist read-only no backend (defesa em profundidade). Tokens nunca são logados nem guardados
no frontend. Só o necessário dos resultados vai ao LLM. CORS fechado (mesmo host).
