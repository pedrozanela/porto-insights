import { useEffect, useState } from "react";
import { listConversations, deleteConversation, type ConversationMeta } from "../../api/client";

interface Props {
  activeId: string;
  refreshToken: number;
  onOpen: (id: string) => void;
  onDeleted: (id: string) => void;
  onClose: () => void;
}

function relativeTime(iso: string): string {
  const d = new Date(iso).getTime();
  const diff = Date.now() - d;
  const min = Math.round(diff / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h} h`;
  return new Date(iso).toLocaleDateString("pt-BR");
}

export function ConversationList({ activeId, refreshToken, onOpen, onDeleted, onClose }: Props) {
  const [items, setItems] = useState<ConversationMeta[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    listConversations()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [refreshToken]);

  const remove = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await deleteConversation(id).catch(() => undefined);
    setItems((xs) => xs.filter((x) => x.conversation_id !== id));
    onDeleted(id);
  };

  return (
    <>
      {/* Backdrop para fechar ao clicar fora */}
      <div className="fixed inset-0 z-10" onClick={onClose} />
      <div className="absolute right-6 top-14 z-20 max-h-[70vh] w-80 overflow-y-auto rounded-xl border border-borderc bg-surface shadow-lg">
        <div className="border-b border-borderc px-4 py-2.5 text-sm font-semibold text-textc">
          Histórico de conversas
        </div>
        {loading ? (
          <div className="px-4 py-6 text-center text-sm text-muted">Carregando…</div>
        ) : items.length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-muted">
            Nenhuma conversa ainda. Suas conversas ficam salvas aqui.
          </div>
        ) : (
          <ul className="py-1">
            {items.map((c) => (
              <li key={c.conversation_id}>
                <button
                  onClick={() => onOpen(c.conversation_id)}
                  className={`group flex w-full items-center gap-2 px-4 py-2.5 text-left hover:bg-surfaceMuted ${
                    c.conversation_id === activeId ? "bg-surfaceMuted" : ""
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-textc">{c.title}</div>
                    <div className="text-xs text-muted">
                      {relativeTime(c.updated_at)} · {c.message_count} msgs
                    </div>
                  </div>
                  <span
                    onClick={(e) => remove(c.conversation_id, e)}
                    className="hidden rounded-md px-2 py-1 text-xs text-muted hover:bg-red-50 hover:text-red-600 group-hover:block"
                    title="Apagar conversa"
                  >
                    Apagar
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
