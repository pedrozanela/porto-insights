# Conjunto de perguntas-ouro do grafo

Cenários fixos para validar a **lógica de promoção** do grafo (evidência, não exploração). As
expectativas são **estruturais**, não exatas — a agenda/emails reais mudam a cada dia, então
checamos formas ("todo evento citado visível", "zero órfãos"), não valores.

Rodar: suba o backend local com `DEBUG_GRAPH=true` (usa seu perfil / token) e execute
`python scripts/run_graph_golden.py`. O runner abre **uma conversa nova por caso**, consome o
stream do `/api/chat`, lê o grafo final em `/api/debug/graph/{id}` e escreve um relatório em
`docs/screenshots/golden-<timestamp>.md` com nós/arestas visíveis, staging e o **motivo** de cada
decisão de promoção.

## Invariantes universais (todos os casos)

- **Zero órfãos**: todo nó visível (exceto `genie_answer`/`data_asset`) tem ≥1 aresta visível, ou
  é o assunto direto da pergunta, ou é o único nó do grafo.
- **Arestas fechadas**: toda aresta visível tem as duas pontas visíveis.
- **Sem rótulo em formato de email**: nenhum rótulo de nó visível parece `x@y.z`.
- **Sem rótulo `(documento)`**: anexos sem nome viram `Documento sem título`.
- **Sugestões só sobre nós visíveis**: todo `node_id` de sugestão é um nó visível.

## Casos

| # | Pergunta | Expectativa estrutural |
|---|----------|------------------------|
| a | Onde encontro o transcript da reunião do dia 10/09 de manhã com o Lucca da Porto? | Exatamente **1** `calendar_event` visível; Lucca ligado por `participou`; **≥1** `drive_file` ligado ao evento; eventos verificados/descartados no trace; **≤ 6** nós visíveis. |
| b | O que tenho com Fernando Custodio esta semana? | **Todo** evento citado na resposta visível; Fernando ligado a cada um por `participou`; **zero órfãos**; evento com muitos participantes mostra **+N** (só Fernando + organizador visíveis). |
| c | Qual é a reunião do Comitê de Crédito PJ e quem participa? Traga a pauta. | 1 evento, **3** pessoas, documento de pauta por `anexo`. |
| d | Como está a carteira de Capital de Giro PJ neste mês em relação à meta? | `genie_answer` ligado a `data_asset` por `fonte`; nada mais. |
| e | (c) → (d) → Isso tem relação com alguma reunião da minha agenda? | Aresta `related_to` entre `genie_answer` e o evento do comitê. |
| f | Quais emails recebi sobre o Comitê de Crédito PJ? | Emails visíveis ligados a remetentes; thread só se houver 2+ mensagens; remetentes automáticos não são pessoas. |
| g | Quem organiza o BR SA Tech Weekly Meeting? | 1 evento, organizador visível, demais colapsados em **+N**. |
| h | O que é inadimplência 90 dias? | Grafo **não muda** (pergunta conceitual, sem dados pessoais). |

O caso **e** é multi-turno (mantém a mesma conversa entre c, d e a pergunta de relação).
