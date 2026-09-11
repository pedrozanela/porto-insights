// Estado da conversa: mensagens (com trace de ferramentas e card do Genie), grafo acumulativo,
// streaming, troca de modelo e navegação entre conversas persistidas.
import { useCallback, useRef, useState } from "react";
import { streamChat, type SSEEvent } from "../api/sse";
import { getConversation } from "../api/client";
import type { ChatMessage, GraphData, GraphNode, GraphEdge, GenieCard } from "./types";

function newConversationId(): string {
  return `c-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

const EMPTY_GRAPH: GraphData = { nodes: [], edges: [], lastTurn: 0 };

export function useConversation() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [graph, setGraph] = useState<GraphData>(EMPTY_GRAPH);
  const [conversationId, setConversationId] = useState<string>(() => newConversationId());
  const [streaming, setStreaming] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [changeToken, setChangeToken] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  // Helpers de atualização da última mensagem do assistente.
  const patchLastAssistant = (fn: (m: ChatMessage) => ChatMessage) =>
    setMessages((ms) => {
      const copy = [...ms];
      for (let i = copy.length - 1; i >= 0; i--) {
        if (copy[i].role === "assistant") {
          copy[i] = fn(copy[i]);
          break;
        }
      }
      return copy;
    });

  const mergeGraph = (nodes: GraphNode[], edges: GraphEdge[], turn: number) =>
    setGraph((g) => {
      const byId = new Map(g.nodes.map((n) => [n.id, n]));
      nodes.forEach((n) => byId.set(n.id, n));
      const eById = new Map(g.edges.map((e) => [e.id, e]));
      edges.forEach((e) => eById.set(e.id, e));
      return { nodes: [...byId.values()], edges: [...eById.values()], lastTurn: turn };
    });

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

      try {
        await streamChat(
          { conversation_id: conversationId, message: trimmed, model },
          (e: SSEEvent) => {
            switch (e.type) {
              case "token":
                patchLastAssistant((m) => ({ ...m, content: m.content + String(e.text ?? "") }));
                break;
              case "tool_call_start":
                patchLastAssistant((m) => ({
                  ...m,
                  trace: { label: String(e.label ?? "Consultando…"), steps: [], done: false },
                }));
                break;
              case "tool_progress":
                patchLastAssistant((m) => ({
                  ...m,
                  trace: m.trace
                    ? { ...m.trace, steps: [...m.trace.steps, String(e.step ?? "")] }
                    : { label: "Consultando…", steps: [String(e.step ?? "")], done: false },
                }));
                break;
              case "tool_call_result":
                patchLastAssistant((m) => ({
                  ...m,
                  card: e.card as GenieCard,
                  trace: m.trace ? { ...m.trace, done: true } : m.trace,
                }));
                break;
              case "graph_delta":
                mergeGraph(
                  (e.added_nodes as GraphNode[]) ?? [],
                  (e.added_edges as GraphEdge[]) ?? [],
                  Number(e.turn ?? 0),
                );
                break;
              case "warning":
                setWarning(String(e.message ?? ""));
                break;
              case "error":
                setError(String(e.message ?? "Erro ao responder."));
                break;
            }
          },
          abort.signal,
        );
      } catch (err) {
        setError(String(err));
      } finally {
        setStreaming(false);
        abortRef.current = null;
        setChangeToken((t) => t + 1);
      }
    },
    [streaming, conversationId],
  );

  const startNew = useCallback(() => {
    abortRef.current?.abort();
    setConversationId(newConversationId());
    setMessages([]);
    setGraph(EMPTY_GRAPH);
    setWarning(null);
    setError(null);
    setStreaming(false);
  }, []);

  const open = useCallback(async (id: string) => {
    abortRef.current?.abort();
    setWarning(null);
    setError(null);
    setStreaming(false);
    setConversationId(id);
    setGraph(EMPTY_GRAPH); // o grafo é reconstruído conforme novas perguntas nesta sessão
    try {
      const msgs = await getConversation(id);
      setMessages(msgs.map((m) => ({ role: m.role, content: m.content })));
    } catch (e) {
      setError(String(e));
      setMessages([]);
    }
  }, []);

  return {
    messages, graph, conversationId, streaming, warning, error, changeToken,
    send, startNew, open,
  };
}
