// Estado da conversa: mensagens (com trace de ferramentas e card do Genie), grafo acumulativo,
// streaming, troca de modelo e navegação entre conversas persistidas.
import { useCallback, useRef, useState } from "react";
import { streamChat, type SSEEvent } from "../api/sse";
import { getConversation, promoteGraphNodes } from "../api/client";
import type { ChatMessage, GraphData, GraphNode, GraphEdge, GenieCard, Suggestion } from "./types";

function newConversationId(): string {
  return `c-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

const EMPTY_GRAPH: GraphData = { nodes: [], edges: [], lastTurn: 0, promoted: [], turns: [] };

export function useConversation() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [graph, setGraph] = useState<GraphData>(EMPTY_GRAPH);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
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

  const mergeGraph = (nodes: GraphNode[], edges: GraphEdge[], turn: number, removed: string[], promoted: string[]) =>
    setGraph((g) => {
      const byId = new Map(g.nodes.map((n) => [n.id, n]));
      nodes.forEach((n) => byId.set(n.id, n)); // merge por id (atualiza props, ex.: is_self, +N)
      removed.forEach((id) => byId.delete(id));
      const eById = new Map(g.edges.map((e) => [e.id, e]));
      edges.forEach((e) => eById.set(e.id, e));
      const alive = new Set(byId.keys());
      for (const [id, e] of [...eById]) if (!alive.has(e.source) || !alive.has(e.target)) eById.delete(id);
      return { nodes: [...byId.values()], edges: [...eById.values()], lastTurn: turn || g.lastTurn, promoted, turns: g.turns };
    });

  // Move a narração pendente (texto antes de uma tool) para o trace, tirando-a da resposta.
  const flushNarration = () =>
    setMessages((ms) => {
      const copy = [...ms];
      for (let i = copy.length - 1; i >= 0; i--) {
        if (copy[i].role !== "assistant") continue;
        const m = copy[i];
        const text = (m.content || "").trim();
        const trace = m.trace ?? { label: "Consultando…", steps: [], narrations: [], done: false };
        copy[i] = {
          ...m,
          content: "",
          trace: text ? { ...trace, narrations: [...trace.narrations, text] } : trace,
        };
        break;
      }
      return copy;
    });

  const send = useCallback(
    async (text: string, model: string) => {
      const trimmed = text.trim();
      if (!trimmed || streaming) return;

      setError(null);
      setWarning(null);
      setSuggestions([]);
      setMessages((m) => [...m, { role: "user", content: trimmed }, { role: "assistant", content: "" }]);
      setGraph((g) => ({ ...g, turns: [...g.turns, { index: g.turns.length + 1, question: trimmed }] }));
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
                flushNarration(); // texto antes desta tool é narração → vai pro trace
                patchLastAssistant((m) => ({
                  ...m,
                  trace: {
                    label: String(e.label ?? "Consultando…"),
                    steps: m.trace?.steps ?? [],
                    narrations: m.trace?.narrations ?? [],
                    done: false,
                  },
                }));
                break;
              case "tool_progress":
                patchLastAssistant((m) => ({
                  ...m,
                  trace: m.trace
                    ? { ...m.trace, steps: [...m.trace.steps, String(e.step ?? "")] }
                    : { label: "Consultando…", steps: [String(e.step ?? "")], narrations: [], done: false },
                }));
                break;
              case "tool_call_result":
                patchLastAssistant((m) => ({
                  ...m,
                  card: e.card ? (e.card as GenieCard) : m.card,
                  trace: m.trace ? { ...m.trace, done: true } : m.trace,
                }));
                break;
              case "auth_required":
                patchLastAssistant((m) => {
                  const svc = String(e.service ?? "");
                  const exists = (m.auth ?? []).some((a) => a.service === svc);
                  return exists
                    ? m
                    : { ...m, auth: [...(m.auth ?? []), { service: svc, login_url: String(e.login_url ?? "") }] };
                });
                break;
              case "graph_delta":
                mergeGraph(
                  (e.added_nodes as GraphNode[]) ?? [],
                  (e.added_edges as GraphEdge[]) ?? [],
                  Number(e.turn ?? 0),
                  (e.removed_node_ids as string[]) ?? [],
                  (e.promoted_node_ids as string[]) ?? [],
                );
                break;
              case "suggestions":
                setSuggestions((e.suggestions as Suggestion[]) ?? []);
                break;
              case "warning":
                setWarning(String(e.message ?? ""));
                break;
              case "error":
                setError(String(e.message ?? "Erro ao responder."));
                break;
              case "done":
                patchLastAssistant((m) => (m.trace ? { ...m, trace: { ...m.trace, done: true } } : m));
                break;
            }
          },
          abort.signal,
        );
      } catch (err) {
        if (abort.signal.aborted) {
          // Interrompido pelo usuário (botão Parar): mantém o parcial, marca e fecha o trace.
          patchLastAssistant((m) => ({
            ...m,
            content: (m.content ? m.content + "\n\n" : "") + "_(resposta interrompida)_",
            trace: m.trace ? { ...m.trace, done: true } : m.trace,
          }));
        } else {
          setError(String(err));
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
        setChangeToken((t) => t + 1);
      }
    },
    [streaming, conversationId],
  );

  // Botão Parar: aborta o stream do turno atual. O catch/finally do send cuida do resto.
  const stop = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
  }, []);

  const startNew = useCallback(() => {
    abortRef.current?.abort();
    setConversationId(newConversationId());
    setMessages([]);
    setGraph(EMPTY_GRAPH);
    setSuggestions([]);
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
    setSuggestions([]);
    try {
      const msgs = await getConversation(id);
      setMessages(msgs.map((m) => ({ role: m.role, content: m.content })));
    } catch (e) {
      setError(String(e));
      setMessages([]);
    }
  }, []);

  // Promoção manual (ex.: participante colapsado escolhido no painel de detalhe).
  const promoteNodes = useCallback(async (ids: string[]) => {
    try {
      const d = await promoteGraphNodes(conversationId, ids);
      mergeGraph(d.added_nodes ?? [], d.added_edges ?? [], 0, d.removed_node_ids ?? [], d.promoted_node_ids ?? []);
    } catch { /* silencioso */ }
  }, [conversationId]);

  return {
    messages, graph, suggestions, conversationId, streaming, warning, error, changeToken,
    send, stop, startNew, open, promoteNodes,
  };
}
