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

// Parâmetros de interação/aparência do grafo (fonte única; consumidos por graphStyle/graphPhysics).
export const graph = {
  // LOD relativo à escala do "Ajustar à tela": no fit o grafo cai na faixa MÉDIA (ícones +
  // rótulos), nunca em "longe". far/near = fatores da escala do fit, com piso/teto absolutos.
  lod: {
    farFactor: 0.55, nearFactor: 1.6,
    farFloor: 0.12, farCeil: 0.9,
    nearFloor: 0.9, nearCeil: 4.0,
  },
  alpha: {
    structural: 0.2,                          // arestas estruturais
    semantic: 0.3,                            // arestas related_to
    dim: 0.15,                                // nós fora do foco
    episodeDim: 0.3,                          // reservado p/ episódios
    focusEdge: 0.9,                           // aresta com as duas pontas em foco
  },
  radius: { min: 6, max: 16, perDegree: 1.5, self: 8 },
  edgeColor: "100, 116, 139",                 // slate-500 em RGB (usado com alpha via rgba)
  labelBase: 11,                              // px de tela do rótulo de nó (÷ globalScale)
  edgeLabelBase: 9,
  ease: 0.18,                                 // suavização de alpha por frame (~150ms)
} as const;

export const nodeLabels: Record<string, string> = {
  person: "Pessoa",
  calendar_event: "Evento",
  email: "Email",
  email_thread: "Thread",
  drive_file: "Documento",
  genie_answer: "Resposta Genie",
  data_asset: "Dado",
};
