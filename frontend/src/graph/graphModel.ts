// Modelo do grafo (estrutura, sem aparência nem física): grau, adjacência e BFS de vizinhança.
// Usado por graphStyle (foco/visibilidade) e pelo modo "Focar". Puro e testável.

export interface MiniNode { id: string; }
export interface MiniEdge { source: string | { id: string }; target: string | { id: string }; }

const endId = (e: string | { id: string }): string => (typeof e === "string" ? e : e.id);

/** Grau (não-direcionado) de cada nó a partir das arestas. */
export function degreeMap(edges: MiniEdge[]): Map<string, number> {
  const d = new Map<string, number>();
  for (const e of edges) {
    const s = endId(e.source), t = endId(e.target);
    d.set(s, (d.get(s) || 0) + 1);
    d.set(t, (d.get(t) || 0) + 1);
  }
  return d;
}

/** Adjacência id → vizinhos (não-direcionada). Recalcular só quando o grafo muda, não por frame. */
export function buildNeighbors(edges: MiniEdge[]): Map<string, Set<string>> {
  const m = new Map<string, Set<string>>();
  const add = (a: string, b: string) => {
    if (!m.has(a)) m.set(a, new Set());
    m.get(a)!.add(b);
  };
  for (const e of edges) {
    const s = endId(e.source), t = endId(e.target);
    if (s === t) continue;
    add(s, t);
    add(t, s);
  }
  return m;
}

/** Conjunto de vizinhos diretos (1 salto) de um nó. */
export function neighborsOf(neighbors: Map<string, Set<string>>, id: string): Set<string> {
  return neighbors.get(id) ?? new Set();
}

/** BFS a partir de `rootId` até `depth` saltos (inclui a raiz). `allowed` restringe os nós
 * navegáveis (ex.: só os visíveis), para o modo "Focar" não atravessar nós escondidos. */
export function bfs(
  neighbors: Map<string, Set<string>>,
  rootId: string,
  depth: number,
  allowed?: Set<string>,
): Set<string> {
  const seen = new Set<string>([rootId]);
  let frontier = [rootId];
  for (let d = 0; d < Math.max(0, depth); d++) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const nb of neighbors.get(id) ?? []) {
        if (seen.has(nb)) continue;
        if (allowed && !allowed.has(nb)) continue;
        seen.add(nb);
        next.push(nb);
      }
    }
    frontier = next;
    if (!frontier.length) break;
  }
  return seen;
}
