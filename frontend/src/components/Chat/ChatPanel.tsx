import { useEffect, useRef } from "react";
import type { ChatMessage, Suggestion } from "../../state/types";
import { Message } from "./Message";
import { Composer } from "./Composer";

// Exemplos agnósticos de domínio: mostram o que o app FAZ (agenda + email + documentos +
// dados + grafo), sem presumir assunto — os temas de dados variam conforme o Genie do banco.
const SUGGESTIONS = [
  "O que tenho na agenda esta semana?",
  "Resuma minha próxima reunião e traga documentos e emails relacionados.",
  "Quais são os principais indicadores de negócio deste mês?",
];

interface Props {
  messages: ChatMessage[];
  streaming: boolean;
  warning: string | null;
  error: string | null;
  suggestions: Suggestion[];
  onSend: (text: string) => void;
  onStop?: () => void;
}

export function ChatPanel({ messages, streaming, warning, error, suggestions, onSend, onStop }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const empty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      {empty ? (
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
                onClick={() => onSend(s)}
                className="rounded-full border border-borderc bg-surface px-4 py-2 text-sm text-textc shadow-soft hover:border-primary hover:text-primary"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          {messages.map((m, i) => (
            <Message key={i} msg={m} streaming={streaming && i === messages.length - 1} />
          ))}
          {warning && <div className="text-center text-xs text-accent">{warning}</div>}
          {error && (
            <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
          )}
          <div ref={bottomRef} />
        </div>
      )}
      {!empty && suggestions.length > 0 && !streaming && (
        <div className="flex flex-wrap gap-2 border-t border-borderc bg-surfaceMuted px-4 pt-3">
          {suggestions.map((s) => (
            <button
              key={s.prompt}
              onClick={() => onSend(s.prompt)}
              className="rounded-full border border-borderc bg-surface px-3 py-1.5 text-xs text-textc shadow-soft hover:border-primary hover:text-primary"
              title={s.prompt}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
      <Composer onSend={onSend} onStop={onStop} streaming={streaming} />
    </div>
  );
}
