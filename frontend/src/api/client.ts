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
