import { useEffect, useRef, useState } from "react";
import { fetchMe, type MeResponse } from "../api/client";
import { useConversation } from "../state/useConversation";
import { Header } from "./Header/Header";
import { ChatPanel } from "./Chat/ChatPanel";
import { GraphPanel } from "./Graph/GraphPanel";
import { ConversationList } from "./History/ConversationList";

export function AppShell() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [selectedModel, setSelectedModel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [graphPct, setGraphPct] = useState(45); // largura do grafo (%), arrastável entre 40 e 60
  const mainRef = useRef<HTMLElement>(null);
  const conv = useConversation();

  // Divisória arrastável chat/grafo (só no layout lg). Clampa o grafo em 40–60%.
  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    const onMove = (ev: MouseEvent) => {
      const el = mainRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const pct = ((rect.right - ev.clientX) / rect.width) * 100;
      setGraphPct(Math.min(60, Math.max(40, pct)));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
    };
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  useEffect(() => {
    fetchMe()
      .then((data) => {
        setMe(data);
        setSelectedModel(data.default_model);
      })
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="flex h-full flex-col">
      <Header
        email={me?.email ?? ""}
        isLocalDev={me?.is_local_dev ?? false}
        models={me?.models ?? []}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        onNewConversation={() => { conv.startNew(); setHistoryOpen(false); }}
        onToggleHistory={() => setHistoryOpen((v) => !v)}
      />
      {historyOpen && (
        <ConversationList
          activeId={conv.conversationId}
          refreshToken={conv.changeToken}
          onOpen={(id) => { void conv.open(id); setHistoryOpen(false); }}
          onDeleted={(id) => { if (id === conv.conversationId) conv.startNew(); }}
          onClose={() => setHistoryOpen(false)}
        />
      )}
      {error && (
        <div className="bg-red-50 px-6 py-2 text-sm text-red-700">
          Não foi possível carregar a configuração: {error}
        </div>
      )}
      <main ref={mainRef} className="flex flex-1 overflow-hidden">
        <section className="min-h-0 flex-1 border-r border-borderc bg-surfaceMuted">
          <ChatPanel
            messages={conv.messages}
            streaming={conv.streaming}
            warning={conv.warning}
            error={conv.error}
            suggestions={conv.suggestions}
            onSend={(text) => conv.send(text, selectedModel)}
            onStop={conv.stop}
          />
        </section>
        <div onMouseDown={startDrag} title="Arraste para redimensionar"
          className="hidden w-1 shrink-0 cursor-col-resize bg-borderc hover:bg-primary lg:block" />
        <aside className="hidden min-h-0 shrink-0 lg:block" style={{ width: `${graphPct}%` }}>
          <GraphPanel
            graph={conv.graph}
            debugGraph={me?.debug_graph ?? false}
            conversationId={conv.conversationId}
            streaming={conv.streaming}
            onPromote={conv.promoteNodes}
            onAskAbout={(node) => {
              const kind = { calendar_event: "o evento", email: "o email", email_thread: "a thread",
                drive_file: "o documento", person: "a pessoa", genie_answer: "esta resposta de dados",
                data_asset: "este dado" }[node.type] ?? "isto";
              conv.send(`Sobre ${kind} "${node.label}": traga mais contexto e relações relevantes.`, selectedModel);
            }}
          />
        </aside>
      </main>
    </div>
  );
}
