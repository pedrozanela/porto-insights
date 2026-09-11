import { useEffect, useState } from "react";
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
  const conv = useConversation();

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
      <main className="grid flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[1fr_45%]">
        <section className="min-h-0 border-r border-borderc bg-surfaceMuted">
          <ChatPanel
            messages={conv.messages}
            streaming={conv.streaming}
            warning={conv.warning}
            error={conv.error}
            suggestions={conv.suggestions}
            onSend={(text) => conv.send(text, selectedModel)}
          />
        </section>
        <aside className="hidden min-h-0 lg:block">
          <GraphPanel
            graph={conv.graph}
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
