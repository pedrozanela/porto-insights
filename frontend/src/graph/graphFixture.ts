// Fixture de desenvolvimento para exercitar o grafo com N nós em telas de teste (checkpoint A).
// Ativado só em dev via ?fixture=N na URL. Não entra em produção.
import type { GraphData, GraphEdge, GraphNode } from "../state/types";

const TYPES = ["person", "calendar_event", "email", "drive_file", "genie_answer", "data_asset"];

export function fixtureFromUrl(): GraphData | null {
  if (!(import.meta as any).env?.DEV) return null;
  const n = Number(new URLSearchParams(window.location.search).get("fixture") || 0);
  return n > 0 ? devFixture(n) : null;
}

/** Grafo sintético determinístico com `n` nós: alguns hubs (grau alto) e satélites. */
export function devFixture(n: number): GraphData {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const rnd = mulberry32(n * 7 + 13);

  nodes.push({ id: "self", type: "person", label: "Você", source: "gmail",
               props: { is_self: true }, first_seen_turn: 1 });
  for (let i = 0; i < n - 1; i++) {
    const type = TYPES[Math.floor(rnd() * TYPES.length)];
    nodes.push({
      id: `n${i}`, type,
      label: `${labelFor(type)} ${i}`,
      source: "gmail",
      props: type === "calendar_event" && i % 5 === 0 ? { staged_participants: 3 } : {},
      first_seen_turn: 1 + Math.floor(rnd() * 3),
    });
  }
  // liga cada nó a um "hub" próximo + algumas arestas extras para criar graus variados
  for (let i = 1; i < nodes.length; i++) {
    const hub = Math.floor(rnd() * Math.min(i, 5));
    edges.push(edge(nodes[i].id, nodes[hub].id, i % 4 === 0 ? "related_to" : "attendee"));
  }
  for (let k = 0; k < n / 4; k++) {
    const a = Math.floor(rnd() * nodes.length), b = Math.floor(rnd() * nodes.length);
    if (a !== b) edges.push(edge(nodes[a].id, nodes[b].id, "links_to"));
  }
  return { nodes, edges, lastTurn: 1, promoted: [] };
}

function edge(source: string, target: string, type: string): GraphEdge {
  return { id: `${source}|${type}|${target}`, source, target, type, weight: 1, confidence: 1, first_seen_turn: 1 };
}

function labelFor(type: string): string {
  return ({ person: "Pessoa", calendar_event: "Reunião", email: "Email",
            drive_file: "Documento", genie_answer: "Resposta", data_asset: "Tabela" } as Record<string, string>)[type] || type;
}

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
