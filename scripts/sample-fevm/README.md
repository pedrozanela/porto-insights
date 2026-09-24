# Seed do demo (FEVM) — NÃO é parte do produto

Estes scripts criam a **demonstração sintética de crédito** no workspace FEVM de desenvolvimento
(`pzanela_classic_aws_catalog.porto_insights`). São **seeders de demonstração**, não código do app:

- O app **não** importa nem executa nada daqui (runtime desacoplado).
- O deploy **não** inclui esta pasta (`scripts/` fica fora do bundle e do notebook de deploy).
- O domínio de crédito (`mv_carteira_credito`, etc.) é **exemplo**. O app é agnóstico de domínio.

## O que tem aqui

| Script | Faz |
|---|---|
| `seed_data.py` | Gera os dados sintéticos de crédito (carteira, contratos, clientes, metas) |
| `create_metric_views.py` / `.sql` | Cria as metric views governadas sobre esses dados |
| `create_genie_agent.py` | Cria um Genie Agent de crédito para roteamento previsível no FEVM |
| `validate_genie_one.py` | Valida as respostas do Genie One sobre o sample de crédito |
| `_sql.py` | Helper de execução SQL usado pelos seeders |

## Para um banco real (ex.: Porto)

Não rode nada daqui. O banco usa o **próprio Genie Space** apontando para os **dados reais dele**
(qualquer assunto). O app descobre esse space automaticamente via Genie One
(`/api/2.0/mcp/genie`) — sem tabela, sem domínio e sem space id cravados no código.
