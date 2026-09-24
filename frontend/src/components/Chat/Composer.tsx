import { useState } from "react";

interface Props {
  onSend: (text: string) => void;
  onStop?: () => void;
  streaming?: boolean;
  disabled?: boolean;
}

export function Composer({ onSend, onStop, streaming, disabled }: Props) {
  const [text, setText] = useState("");

  const submit = () => {
    const t = text.trim();
    if (!t || disabled || streaming) return;
    onSend(t);
    setText("");
  };

  return (
    <div className="border-t border-borderc bg-surface p-4">
      <div className="flex items-center gap-2 rounded-xl border border-borderc px-4 py-2 focus-within:border-primary">
        <input
          id="chat-input"
          name="pergunta"
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder={streaming ? "Respondendo… clique em Parar para interromper" : "Escreva sua pergunta…"}
          disabled={streaming}
          className="flex-1 bg-transparent text-textc outline-none placeholder:text-muted disabled:opacity-60"
        />
        {streaming ? (
          <button
            onClick={() => onStop?.()}
            title="Parar a resposta"
            className="flex items-center gap-1.5 rounded-lg bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700"
          >
            <span className="inline-block h-2.5 w-2.5 rounded-[2px] bg-white" /> Parar
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={disabled || !text.trim()}
            className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primaryDark disabled:opacity-40"
          >
            Enviar
          </button>
        )}
      </div>
    </div>
  );
}
