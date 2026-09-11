import { useState } from "react";
import type { ToolTrace as Trace } from "../../state/types";

// Linha do tempo das ferramentas (transparência). Tom de assistente explicando, não log.
export function ToolTrace({ trace }: { trace: Trace }) {
  const [open, setOpen] = useState(true);
  const last = trace.steps[trace.steps.length - 1];

  return (
    <div className="mb-2 rounded-lg border border-borderc bg-surfaceMuted px-3 py-2 text-sm">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 text-left text-muted"
      >
        <span className={`inline-block h-2 w-2 rounded-full ${trace.done ? "bg-emerald-500" : "bg-accent animate-pulse"}`} />
        <span className="flex-1 truncate">
          {trace.done ? trace.label.replace("…", "") : last || trace.label}
        </span>
        <span className="text-xs">{open ? "ocultar" : "ver passos"}</span>
      </button>
      {trace.narrations.length > 0 && (
        <div className="mt-1.5 space-y-0.5">
          {trace.narrations.map((n, i) => (
            <p key={i} className="text-xs italic text-muted">{n}</p>
          ))}
        </div>
      )}
      {open && trace.steps.length > 0 && (
        <ol className="mt-2 space-y-1 border-l border-borderc pl-3">
          {trace.steps.map((s, i) => (
            <li key={i} className="text-xs text-muted">
              {s.length > 160 ? s.slice(0, 160) + "…" : s}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
