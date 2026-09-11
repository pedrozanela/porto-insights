# Roteiro de demo — Porto Insights

Demo executiva (~8 min). Pré-requisitos: `docs/demo-seed-google.md` semeado, Login OAuth dos 3
serviços Google feito, e uma passada de aquecimento (o Genie leva ~60–90s por pergunta).

Abra o app já logado. O grafo à direita começa vazio; ele cresce a cada pergunta — esse é o
efeito "uau".

## Passos

1. **"O que eu tenho na agenda amanhã?"**
   → Lista os eventos de amanhã (incluindo o *Comitê de Crédito PJ*). No grafo surgem nós de
   **evento** e **pessoas** (os convidados).

2. **"Tem algum email relacionado ao Comitê de Crédito PJ?"**
   → Traz a thread de email. No grafo aparecem **emails** e **threads**, e arestas ligando às
   **pessoas em comum** com o evento (mesmos participantes).

3. **"Algum documento no Drive foi mencionado nesses emails?"**
   → Encontra a *Pauta — Comitê de Crédito PJ*. Nó de **documento** ligado por `links_to` ao
   email e ao evento (o link do Doc está no corpo/descrição).

4. **"Como está a carteira de Capital de Giro PJ neste mês em relação à meta?"**
   → O **Genie One** responde: card com tabela, SQL e fontes. Números-chave: originação
   **R$ 43,19 mi** (**118%** da meta), inadimplência **8,1%** vs teto **6,7%**. No grafo,
   nós **Resposta Genie** e **mv_carteira_credito** ligados por `cites`.

5. **"E a inadimplência, por segmento?"**
   → Follow-up no **mesmo fio** do Genie One (`follows_up` no grafo). PF dentro da meta, PJ acima.

6. **"Isso tem relação com o que vamos discutir no comitê?"**
   → O linker semântico cria uma aresta **`related_to`** (tracejada) entre a resposta do Genie
   e o evento do comitê, com uma justificativa em português (passe o mouse na aresta para ler).

7. **Clique no nó do evento → "Perguntar sobre isso"**
   → Injeta uma pergunta contextual sobre o comitê, fechando o ciclo: agenda → dados → decisão.

## Dicas de condução

- Use o seletor de **modelo** no cabeçalho para mostrar a flexibilidade (Claude/GPT/Gemini).
- Abra o **SQL** do card ("ver como o Genie chegou nisso") para provar que a resposta é
  fundamentada, não inventada.
- Clique em **"Explorar no Databricks"** para abrir a conversa completa no Genie One.
- O **Histórico** (cabeçalho) mostra que as conversas ficam salvas (Lakebase).
- Perguntas escopadas ("amanhã", não "esta semana") mantêm o grafo limpo e legível.
