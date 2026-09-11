// Cliente HTTP mínimo da API do backend (mesmo host). Sem tokens no frontend.

export interface ModelInfo {
  name: string;
  label: string;
}

export interface MeResponse {
  email: string;
  is_local_dev: boolean;
  models: ModelInfo[];
  default_model: string;
  google_services: string[];
}

export async function fetchMe(): Promise<MeResponse> {
  const res = await fetch("/api/me");
  if (!res.ok) throw new Error(`GET /api/me falhou: ${res.status}`);
  return res.json();
}

export interface ConversationMeta {
  conversation_id: string;
  title: string;
  updated_at: string;
  message_count: number;
}

export interface StoredMessage {
  role: "user" | "assistant";
  content: string;
}

export async function listConversations(): Promise<ConversationMeta[]> {
  const res = await fetch("/api/conversations");
  if (!res.ok) throw new Error(`GET /api/conversations falhou: ${res.status}`);
  return (await res.json()).conversations ?? [];
}

export async function getConversation(id: string): Promise<StoredMessage[]> {
  const res = await fetch(`/api/conversations/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(`GET /api/conversations/${id} falhou: ${res.status}`);
  return (await res.json()).messages ?? [];
}

export async function deleteConversation(id: string): Promise<void> {
  await fetch(`/api/conversations/${encodeURIComponent(id)}/reset`, { method: "POST" });
}

export async function promoteGraphNodes(conversationId: string, nodeIds: string[]): Promise<any> {
  const res = await fetch("/api/graph/promote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, node_ids: nodeIds }),
  });
  if (!res.ok) throw new Error(`promote falhou: ${res.status}`);
  return res.json();
}
