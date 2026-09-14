// Fonte ÚNICA das forças do d3 do grafo. O componente chama configureForces uma vez (após montar)
// e reheatWithPins a cada delta. A fase futura de episódios pluga uma força de ancoragem via
// applyEpisodeAnchors — ponto de extensão deixado explícito.
import { forceCollide } from "d3-force";

// react-force-graph expõe .d3Force(name[, force]) e .d3ReheatSimulation() como MÉTODOS do ref.
// velocityDecay/alphaDecay são PROPS do componente (setados no JSX), não métodos do ref.
interface ForceGraphLike {
  d3Force: (name: string, force?: unknown) => any;
  d3ReheatSimulation: () => void;
}

interface PhysNode { id: string; x?: number; y?: number; fx?: number; fy?: number; __dragPin?: boolean; }

export interface ForceOptions {
  charge?: number;                          // padrão -150
  linkDistance?: (link: { type?: string }) => number;
  collideRadius: (node: any) => number;     // raio + meia-largura do rótulo (medido no componente)
}

/** Configura charge, link.distance e a força de colisão (via ref.d3Force). velocityDecay é prop
 * do componente. Idempotente. */
export function configureForces(fg: ForceGraphLike, opts: ForceOptions): void {
  const charge = fg.d3Force("charge");
  if (charge?.strength) charge.strength(opts.charge ?? -150);

  const link = fg.d3Force("link");
  if (link?.distance) {
    link.distance((l: { type?: string }) =>
      (opts.linkDistance ? opts.linkDistance(l) : (l.type === "related_to" ? 120 : 60)));
  }

  fg.d3Force("collide", forceCollide((n: any) => opts.collideRadius(n)).iterations(2));
}

/**
 * Reaquecimento suave a cada graph_delta: fixa (fx/fy) os nós já existentes na posição atual,
 * reaquece a simulação e libera os fixados após 1s — assim só os nós NOVOS se acomodam e o resto
 * não pula. Não libera nós com pin temporário de arraste (__dragPin).
 */
export function reheatWithPins(
  fg: ForceGraphLike,
  nodes: PhysNode[],
  isExisting: (id: string) => boolean,
  holdMs = 1000,
): void {
  const pinned: PhysNode[] = [];
  for (const n of nodes) {
    if (isExisting(n.id) && typeof n.x === "number" && typeof n.y === "number") {
      n.fx = n.x;
      n.fy = n.y;
      pinned.push(n);
    }
  }
  fg.d3ReheatSimulation();
  setTimeout(() => {
    for (const n of pinned) {
      if (!n.__dragPin) { n.fx = undefined; n.fy = undefined; }
    }
    fg.d3ReheatSimulation();
  }, holdMs);
}

/** Pin temporário ao soltar um nó arrastado: fica onde foi solto por `holdMs`, depois reacomoda. */
export function pinAfterDrag(fg: ForceGraphLike, node: PhysNode, holdMs = 2000): void {
  node.__dragPin = true;
  node.fx = node.x;
  node.fy = node.y;
  setTimeout(() => {
    node.__dragPin = false;
    node.fx = undefined;
    node.fy = undefined;
    fg.d3ReheatSimulation();
  }, holdMs);
}

/** Ponto de extensão para a fase de episódios: ancorar nós de cada episódio numa região. No-op
 * por enquanto (mantém a assinatura estável para o futuro). */
export function applyEpisodeAnchors(_sim: unknown, _anchors: Map<string, { x: number; y: number }>): void {
  // reservado — os episódios plugarão uma força de ancoragem aqui.
}
