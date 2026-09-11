import type { ModelInfo } from "../../api/client";
import { BrandLogo } from "./BrandLogo";
import { ModelSelector } from "./ModelSelector";

interface Props {
  email: string;
  isLocalDev: boolean;
  models: ModelInfo[];
  selectedModel: string;
  onModelChange: (name: string) => void;
  onNewConversation: () => void;
  onToggleHistory: () => void;
}

export function Header({
  email,
  isLocalDev,
  models,
  selectedModel,
  onModelChange,
  onNewConversation,
  onToggleHistory,
}: Props) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-borderc bg-surface px-6 py-3">
      <BrandLogo />
      <div className="flex items-center gap-4">
        <ModelSelector models={models} value={selectedModel} onChange={onModelChange} />
        <button
          onClick={onToggleHistory}
          className="rounded-lg border border-borderc px-3 py-1.5 text-sm text-textc hover:bg-surfaceMuted"
        >
          Histórico
        </button>
        <button
          onClick={onNewConversation}
          className="rounded-lg border border-borderc px-3 py-1.5 text-sm text-textc hover:bg-surfaceMuted"
        >
          Nova conversa
        </button>
        <div className="hidden text-right text-xs text-muted sm:block">
          <div>{email || "—"}</div>
          {isLocalDev && <div className="text-accent">dev local</div>}
        </div>
      </div>
    </header>
  );
}
