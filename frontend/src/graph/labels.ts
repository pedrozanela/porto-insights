// Encurtamento de rótulos para o grafo (espelho em TS das regras do backend).
// Título completo fica no tooltip e no painel de detalhe (node.props.title / label original).
import type { GraphNode } from "../state/types";

function stripEmailPrefix(s: string): string {
  return s.replace(/^\s*(re|fwd|fw|enc|res)\s*:\s*/gi, "").trim();
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 1).trimEnd() + "…" : s;
}

// Nome e sobrenome (primeiro + último token).
function firstLast(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 2) return name.trim();
  return `${parts[0]} ${parts[parts.length - 1]}`;
}

export function shortLabel(node: GraphNode): string {
  const label = node.label || "";
  switch (node.type) {
    case "email":
    case "email_thread":
      return truncate(stripEmailPrefix(label.replace(/^Thread:\s*/i, "")), 28);
    case "person":
      return node.props?.is_self ? "Você" : firstLast(label);
    case "data_asset":
      return label.split(".").pop() || label;
    case "calendar_event":
    case "drive_file":
    default:
      return truncate(label, 30);
  }
}

// Rótulos de aresta em pt-BR (Bloco 4).
export const EDGE_LABELS: Record<string, string> = {
  attendee: "participou",
  organizer: "organizou",
  sender: "enviou",
  recipient: "recebeu",
  attached: "anexo",
  links_to: "referencia",
  in_thread: "mesma thread",
  mentions: "citado em",
  same_time_window: "mesma época",
  notes_of: "notas de",
  cites: "fonte",
  follows_up: "continuação",
  related_to: "relacionado",
};
