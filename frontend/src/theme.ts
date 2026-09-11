// Tokens de identidade visual do Porto Insights — cores oficiais da Porto
// (extraídas do app ai-prism-porto). Azul da vela = #00a1fc.
//
// Espelhados como CSS variables em index.css (:root), que o Tailwind consome. Ao ajustar,
// atualize os dois lugares.

export const theme = {
  primary: "#005bbf", // azul Porto profundo (botões/links, contraste com texto branco)
  primaryDark: "#00408c", // hover/pressed
  accent: "#00a1fc", // azul da vela — acento de marca
  surface: "#FFFFFF",
  surfaceMuted: "#F7F8FA",
  border: "#E2E6EA",
  text: "#1A1F24",
  muted: "#5C6670",
} as const;

// Paleta por tipo de nó do grafo, harmônica com o azul Porto.
export const nodeColors: Record<string, string> = {
  person: "#00a1fc",
  calendar_event: "#005bbf",
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
