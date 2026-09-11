# Checklist de pré-requisitos (o que um humano faz no workspace)

O que precisa estar configurado no workspace Databricks para o Porto Insights rodar. Itens
marcados com ✅ já foram feitos/validados no workspace de field engineering
`fevm-pzanela-classic-aws`. Um engenheiro da Porto reproduz isto no workspace deles.

## No workspace (admin, uma vez)

- [x] ✅ **Preview "Managed MCP Servers" habilitado** (Settings → Previews). Sem isso, o
      endpoint `/api/2.0/mcp/genie` não responde. Verificação: `initialize` no servidor
      retorna serverInfo `genie_chat`.
- [ ] **Genie One configurado** com ontologia/semântica do domínio. Para o Porto Bank:
  - [x] ✅ metric views `mv_carteira_credito` e `mv_contratos_credito` criadas e comentadas;
  - [x] ✅ `/Workspace/.genie_workspace_instructions.md` publicado;
  - [x] ✅ Genie Agent de suporte `Porto Bank — Carteira e Crédito` criado (opcional, via flag).
- [x] ✅ **SQL warehouse serverless** disponível (`848374d85d2bad86`).
- [x] ✅ **Endpoints de modelo com tool calling** disponíveis (Claude/GPT/Gemini/Llama nativos).

## Por usuário (cada executivo que usar o app)

- [ ] **Login OAuth no Google** para os três serviços, uma vez, antes do primeiro uso:
      Catalog Explorer → `system.ai.gmail` / `system.ai.google_calendar` /
      `system.ai.google_drive` → botão **Login**. Se pular, o app mostra o card
      "Conecte sua conta Google" com o link direto (o resto do agente continua funcionando).
      - [x] ✅ feito para `pedro.zanela@databricks.com`.
- [ ] **Acesso aos serviços `system.ai.*`** (grant de execução no serviço). No FEVM o
      usuário admin já tem; na Porto, conceder ao grupo de usuários do app.
- [ ] **Permissões de Unity Catalog** do próprio usuário sobre `pzanela_classic_aws_catalog.porto_insights`
      (as respostas do Genie One respeitam as permissões UC do usuário via OBO).

## Lakebase (histórico de chat persistente)

- [x] ✅ Projeto Lakebase `porto-insights` criado (branch `production`, endpoint `primary`,
      db `databricks_postgres`). Serverless, scale-to-zero.
- [x] ✅ Recurso `lakebase` declarado no app (databricks.yml) → dá ao SP do app o direito de
      conectar e gerar credencial.
- [ ] **Ownership do schema (fazer no deploy):** o schema `porto_insights` é criado por quem
      roda a inicialização primeiro. Em dev local fui eu; ao deployar, o SP do app precisa
      poder criar/usar o schema. Duas opções: (A) **deployar antes de rodar local** (o SP cria
      e vira dono — recomendado pela doc); ou (B) se o schema já existe (criado por mim em dev),
      conceder ao SP: `GRANT ALL ON SCHEMA porto_insights TO "<sp>"; GRANT ALL ON ALL TABLES IN
      SCHEMA porto_insights TO "<sp>"; ALTER DEFAULT PRIVILEGES IN SCHEMA porto_insights GRANT
      ALL ON TABLES TO "<sp>";`. Tratar na Fase 5.
- Nota: o histórico usa a identidade do **app** (SP), não o OBO do usuário — é infra do app.
  O isolamento por usuário é por `user_email` nas queries.

## No app (deploy)

- [ ] **Scopes OBO declarados** no recurso `app` do DAB (`user_api_scopes`):
      `genie`, `ai-gateway`, `serving.serving-endpoints` (model serving). Os scopes de
      identidade vêm por padrão.
- [ ] **Consent do usuário:** na primeira visita ao app, o Databricks pede que o usuário
      autorize o app a agir em cada scope. Documentar isso para os executivos.
- [ ] **Variáveis de ambiente** preenchidas (ver `.env.example` / `app.yaml`): `MODEL_ENDPOINTS`,
      `DEFAULT_MODEL_ENDPOINT`, `SQL_WAREHOUSE_ID`, etc. Nenhum segredo em texto no `app.yaml`.
- [ ] **Build do frontend** feito antes do deploy (`npm run build`), com o `dist/`
      sincronizado. Não rodar `npm install` no startup do app.

## Notas de reprodução na Porto

- O catálogo/schema pode mudar; ajustar `PORTO_CATALOG`/`PORTO_SCHEMA` e reexecutar os
  scripts da Fase 0 (todos idempotentes).
- Rodar `scripts/discover.py` para revalidar endpoints, warehouse e tools MCP no workspace de
  destino antes de fixar a config.
