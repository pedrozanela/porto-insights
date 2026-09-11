// Cliente SSE sobre POST. EventSource só faz GET; como enviamos corpo (mensagem, modelo),
// lemos a resposta como stream e parseamos os frames "data: {...}\n\n" manualmente.

export interface SSEEvent {
  type: string;
  [key: string]: unknown;
}

export interface ChatRequest {
  conversation_id: string;
  message: string;
  model: string;
}

// Abre o stream do turno e chama onEvent para cada evento. Retorna quando o stream fecha.
export async function streamChat(
  req: ChatRequest,
  onEvent: (e: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`POST /api/chat falhou: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Frames separados por linha em branco.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as SSEEvent);
      } catch {
        // frame parcial/ruído — ignora
      }
    }
  }
}

export async function resetConversation(conversationId: string): Promise<void> {
  await fetch(`/api/conversations/${conversationId}/reset`, { method: "POST" });
}
