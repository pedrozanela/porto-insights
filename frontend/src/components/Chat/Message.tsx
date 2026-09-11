import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../../state/types";
import { ToolTrace } from "./ToolTrace";
import { GenieAnswerCard } from "../Genie/GenieAnswerCard";
import { AuthRequiredCard } from "../Genie/AuthRequiredCard";

// Bolha de mensagem. Usuário à direita; assistente à esquerda com trace, card do Genie e markdown.
export function Message({ msg, streaming }: { msg: ChatMessage; streaming?: boolean }) {
  const isUser = msg.role === "user";
  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-bubbleUser px-4 py-2.5 text-textc">
          <p className="whitespace-pre-wrap">{msg.content}</p>
        </div>
      </div>
    );
  }

  const empty = !msg.content && !msg.trace && !msg.card && !(msg.auth && msg.auth.length);
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%]">
        {msg.trace && <ToolTrace trace={msg.trace} />}
        {msg.auth && msg.auth.length > 0 && <AuthRequiredCard auth={msg.auth} />}
        {msg.card && <GenieAnswerCard card={msg.card} />}
        {(msg.content || empty) && (
          <div className="rounded-2xl rounded-bl-md bg-surface px-4 py-2.5 text-textc shadow-soft">
            <div className="prose-chat">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              {streaming && !msg.content && <span className="text-muted">Pensando…</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
