// Estado da conversa da sessão: mensagens, streaming e troca de modelo.
// A persistência real é no backend (por sessão); aqui é só o espelho da UI.
import { useCallback, useRef, useState } from "react";
import { streamChat, resetConversation, type SSEEvent } from "../api/sse";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

// Um id de conversa por montagem do app; "Nova conversa" gera um novo.
function newConversationId(): string {
  return `c-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function useConversation() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const conversationId = useRef<string>(newConversationId());
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(async (text: string, model: string) => {
    const trimmed = text.trim();
    if (!trimmed || streaming) return;

    setError(null);
    setWarning(null);
    setMessages((m) => [...m, { role: "user", content: trimmed }, { role: "assistant", content: "" }]);
    setStreaming(true);

    const abort = new AbortController();
    abortRef.current = abort;

    const appendToLast = (chunk: string) =>
      setMessages((m) => {
        const copy = [...m];
        const last = copy[copy.length - 1];
        if (last && last.role === "assistant") copy[copy.length - 1] = { ...last, content: last.content + chunk };
        return copy;
      });

    try {
      await streamChat(
        { conversation_id: conversationId.current, message: trimmed, model },
        (e: SSEEvent) => {
          if (e.type === "token") appendToLast(String(e.text ?? ""));
          else if (e.type === "warning") setWarning(String(e.message ?? ""));
          else if (e.type === "error") setError(String(e.message ?? "Erro ao responder."));
        },
        abort.signal,
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [streaming]);

  const reset = useCallback(async () => {
    abortRef.current?.abort();
    const old = conversationId.current;
    conversationId.current = newConversationId();
    setMessages([]);
    setWarning(null);
    setError(null);
    setStreaming(false);
    await resetConversation(old).catch(() => undefined);
  }, []);

  return { messages, streaming, warning, error, send, reset };
}
