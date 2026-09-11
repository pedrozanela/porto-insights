import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../../state/useConversation";

// Bolha de mensagem. Usuário à direita; assistente à esquerda com markdown renderizado.
export function Message({ msg, streaming }: { msg: ChatMessage; streaming?: boolean }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={
          isUser
            ? "max-w-[80%] rounded-2xl rounded-br-md bg-bubbleUser px-4 py-2.5 text-textc"
            : "max-w-[85%] rounded-2xl rounded-bl-md bg-surface px-4 py-2.5 text-textc shadow-soft"
        }
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{msg.content}</p>
        ) : (
          <div className="prose-chat">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            {streaming && !msg.content && <span className="text-muted">Pensando…</span>}
          </div>
        )}
      </div>
    </div>
  );
}
