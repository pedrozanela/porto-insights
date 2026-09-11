// Tokens de identidade visual do Porto Insights.
//
// TODO: hex oficiais da Porto. Os valores abaixo são PROVISÓRIOS (azul neutro, nível
// executivo) até o Pedro fornecer os oficiais. Não são o azul oficial da Porto.
//
// Estes tokens também são espelhados como CSS variables em index.css (:root), que o Tailwind
// consome. Ao trocar pelos oficiais, atualize os dois lugares (ou centralize aqui e injete).

export const theme = {
  primary: "#1B4A9C", // TODO: hex oficial Porto (azul primário)
  primaryDark: "#0F2F63", // TODO: hex oficial Porto (azul escuro / hover)
  accent: "#2E86DE", // TODO: hex oficial Porto (destaque)
  surface: "#FFFFFF",
  surfaceMuted: "#F5F7FA",
  border: "#E3E8EF",
  text: "#1A2332",
  muted: "#6B7688",
} as const;

// Paleta por tipo de nó do grafo (provisória, harmônica com o azul executivo).
// TODO: alinhar com a paleta oficial Porto quando disponível.
export const nodeColors: Record<string, string> = {
  person: "#2E86DE",
  calendar_event: "#1B4A9C",
  email: "#7A5AF8",
  email_thread: "#9B8AFB",
  drive_file: "#12A594",
  genie_answer: "#E8843C",
  data_asset: "#556170",
};

export const nodeLabels: Record<string, string> = {
  person: "Pessoa",
  calendar_event: "Evento",
  email: "Email",
  email_thread: "Thread",
  drive_file: "Documento",
  genie_answer: "Resposta Genie",
  data_asset: "Dado",
};
