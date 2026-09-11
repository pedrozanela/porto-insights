// Painel de chat — Fase 1: só o estado vazio com chips de sugestão e a caixa de entrada.
// A lógica de streaming/turnos entra na Fase 2.

const SUGGESTIONS = [
  "O que eu tenho na agenda amanhã?",
  "Tem algum email relacionado ao Comitê de Crédito PJ?",
  "Como está a carteira de Capital de Giro PJ neste mês em relação à meta?",
];

export function ChatPanel() {
  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <h1 className="text-2xl font-semibold text-textc">Como posso ajudar?</h1>
        <p className="mt-2 max-w-md text-muted">
          Pergunte sobre sua agenda, emails, documentos e os dados do Porto Bank. As conexões
          entre eles aparecem no grafo ao lado.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              className="rounded-full border border-borderc bg-surface px-4 py-2 text-sm text-textc shadow-soft hover:border-primary hover:text-primary"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="border-t border-borderc bg-surface p-4">
        <div className="flex items-center gap-2 rounded-xl border border-borderc px-4 py-2">
          <input
            id="chat-input"
            name="pergunta"
            type="text"
            placeholder="Escreva sua pergunta…"
            className="flex-1 bg-transparent text-textc outline-none placeholder:text-muted"
          />
          <button className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primaryDark">
            Enviar
          </button>
        </div>
      </div>
    </div>
  );
}
