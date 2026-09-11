// Estado da conversa: mensagens, streaming, troca de modelo, e navegação entre conversas
// persistidas (histórico no Lakebase). A persistência real é no backend; aqui é o espelho da UI.
import { useCallback, useRef, useState } from "react";
import { streamChat, type SSEEvent } from "../api/sse";
import { getConversation } from "../api/client";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

function newConversationId(): string {
  return `c-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function useConversation() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string>(() => newConversationId());
  const [streaming, setStreaming] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Incrementa quando o histórico muda (turno concluído, nova conversa), para a lista refazer o fetch.
  const [changeToken, setChangeToken] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (text: string, model: string) => {
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
          { conversation_id: conversationId, message: trimmed, model },
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
        setChangeToken((t) => t + 1); // atualiza a lista de histórico (título/ordem)
      }
    },
    [streaming, conversationId],
  );

  // Nova conversa: NÃO apaga a atual — só começa uma nova (a anterior fica no histórico).
  const startNew = useCallback(() => {
    abortRef.current?.abort();
    setConversationId(newConversationId());
    setMessages([]);
    setWarning(null);
    setError(null);
    setStreaming(false);
  }, []);

  // Abre uma conversa do histórico, carregando as mensagens do backend.
  const open = useCallback(async (id: string) => {
    abortRef.current?.abort();
    setWarning(null);
    setError(null);
    setStreaming(false);
    setConversationId(id);
    try {
      const msgs = await getConversation(id);
      setMessages(msgs.map((m) => ({ role: m.role, content: m.content })));
    } catch (e) {
      setError(String(e));
      setMessages([]);
    }
  }, []);

  return {
    messages, conversationId, streaming, warning, error, changeToken,
    send, startNew, open,
    notifyChanged: () => setChangeToken((t) => t + 1),
  };
}
