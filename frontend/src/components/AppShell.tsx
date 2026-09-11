import { useEffect, useState } from "react";
import { fetchMe, type MeResponse } from "../api/client";
import { useConversation } from "../state/useConversation";
import { Header } from "./Header/Header";
import { ChatPanel } from "./Chat/ChatPanel";
import { GraphPanel } from "./Graph/GraphPanel";

export function AppShell() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [selectedModel, setSelectedModel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const conv = useConversation();

  useEffect(() => {
    fetchMe()
      .then((data) => {
        setMe(data);
        setSelectedModel(data.default_model);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const newConversation = () => {
    void conv.reset();
  };

  return (
    <div className="flex h-full flex-col">
      <Header
        email={me?.email ?? ""}
        isLocalDev={me?.is_local_dev ?? false}
        models={me?.models ?? []}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        onNewConversation={newConversation}
      />
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
            onSend={(text) => conv.send(text, selectedModel)}
          />
        </section>
        <aside className="hidden min-h-0 lg:block">
          <GraphPanel />
        </aside>
      </main>
    </div>
  );
}
