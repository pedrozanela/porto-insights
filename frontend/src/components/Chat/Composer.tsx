import { useState } from "react";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function Composer({ onSend, disabled }: Props) {
  const [text, setText] = useState("");

  const submit = () => {
    const t = text.trim();
    if (!t || disabled) return;
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
          placeholder="Escreva sua pergunta…"
          className="flex-1 bg-transparent text-textc outline-none placeholder:text-muted"
        />
        <button
          onClick={submit}
          disabled={disabled || !text.trim()}
          className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primaryDark disabled:opacity-40"
        >
          Enviar
        </button>
      </div>
    </div>
  );
}
