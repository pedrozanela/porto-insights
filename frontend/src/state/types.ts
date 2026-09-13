// Tipos compartilhados do frontend (espelham o contrato do backend).

export interface GenieSource {
  label: string;
  url: string;
  type: string;
}

export interface GenieCard {
  status: string;
  answer: string;
  sql: string | null;
  columns: string[];
  column_types?: string[];
  rows: (string | number)[][];
  truncated: boolean;
  sources: GenieSource[];
  deep_link: string | null;
  conversation_id: string;
  response_id: string;
  item_id: string | null;
}

export interface ToolTrace {
  label: string;
  steps: string[];
  narrations: string[]; // texto que o modelo produziu ANTES de uma tool (narração, não resposta)
  done: boolean;
}

export interface Suggestion {
  label: string;
  prompt: string;
  node_id: string;
}

export interface AuthRequired {
  service: string;
  login_url: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  trace?: ToolTrace;
  card?: GenieCard;
  auth?: AuthRequired[];
}

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  source: string;
  url?: string;
  props: Record<string, unknown>;
  first_seen_turn: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  weight: number;
  confidence: number;
  rationale?: string;
  first_seen_turn: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  lastTurn: number;
  promoted: string[]; // ids que passaram a visíveis no último delta (para animar)
}
