// Fonte ÚNICA de decisão de aparência do grafo: visibilidade, opacidade, ênfase, raio, LOD e
// estilo de aresta. Os callbacks do react-force-graph só CONSULTAM este módulo — nada de cálculo
// de estilo espalhado nos componentes. Puro e testável (sem React, sem canvas).
import { graph as G, nodeColors } from "../theme";

export type Emphasis = "focus" | "new" | "normal";
export type LodBand = "far" | "mid" | "near";

export interface NodeState {
  visible: boolean;
  alpha: number;
  emphasis: Emphasis;
}

export interface LinkState {
  visible: boolean;
  alpha: number;
  focused: boolean;
}

/** Contexto de estilo do turno/interação atual. `episode` é reservado para a fase futura. */
export interface StyleCtx {
  focusNodeId: string | null;
  focusPinned: boolean;
  focusNeighbors: Set<string>;
  localMode: { rootId: string; depth: number; nodeIds: Set<string> } | null;
  replay: { turn: number } | null;
  recentTurn: number;
  episode: { currentId: string | null; dimmedAlpha: number } | null;
}

export const emptyCtx = (): StyleCtx => ({
  focusNodeId: null,
  focusPinned: false,
  focusNeighbors: new Set(),
  localMode: null,
  replay: null,
  recentTurn: 0,
  episode: null,
});

export interface StyleNode {
  id: string;
  type: string;
  first_seen_turn?: number;
  props?: Record<string, unknown>;
}

const HIDDEN: NodeState = { visible: false, alpha: 0, emphasis: "normal" };

/**
 * Única fonte de verdade para o estado de um nó. Precedência (mais forte → mais fraca):
 *  1. replay ativo e nó do futuro → invisível
 *  2. modo local ativo e nó fora do conjunto → invisível
 *  3. foco ativo → nó em foco/vizinho a 100% (ênfase "focus"); demais a 15%
 *  4. episódio (reservado) → nó fora do episódio atual a 30%
 *  5. nó do turno atual → ênfase "new" a 100%
 *  6. padrão → 100%
 */
export function resolveNodeState(node: StyleNode, ctx: StyleCtx): NodeState {
  const turn = node.first_seen_turn ?? 0;

  if (ctx.replay && turn > ctx.replay.turn) return HIDDEN;                 // 1
  if (ctx.localMode && !ctx.localMode.nodeIds.has(node.id)) return HIDDEN; // 2

  if (ctx.focusNodeId) {                                                   // 3
    const inFocus = node.id === ctx.focusNodeId || ctx.focusNeighbors.has(node.id);
    return inFocus
      ? { visible: true, alpha: 1, emphasis: "focus" }
      : { visible: true, alpha: G.alpha.dim, emphasis: "normal" };
  }

  if (ctx.episode && ctx.episode.currentId) {                             // 4 (reservado)
    const epId = node.props?.episode_id;
    if (epId && epId !== ctx.episode.currentId) {
      return { visible: true, alpha: ctx.episode.dimmedAlpha ?? G.alpha.episodeDim, emphasis: "normal" };
    }
  }

  if (ctx.recentTurn > 0 && turn === ctx.recentTurn) {                    // 5
    return { visible: true, alpha: 1, emphasis: "new" };
  }
  return { visible: true, alpha: 1, emphasis: "normal" };                 // 6
}

/** Estado de uma aresta a partir dos estados dos dois nós que ela liga. */
export function resolveLinkState(src: NodeState, tgt: NodeState, linkType: string): LinkState {
  if (!src.visible || !tgt.visible) return { visible: false, alpha: 0, focused: false };
  const base = linkType === "related_to" ? G.alpha.semantic : G.alpha.structural;
  if (src.emphasis === "focus" && tgt.emphasis === "focus") {
    return { visible: true, alpha: G.alpha.focusEdge, focused: true };
  }
  return { visible: true, alpha: Math.min(src.alpha, tgt.alpha) * base, focused: false };
}

// ---------------------------------------------------------------- geometria / cor

export function radiusOf(degree: number, isSelf = false): number {
  if (isSelf) return G.radius.self;
  return Math.max(G.radius.min, Math.min(G.radius.max, G.radius.min + G.radius.perDegree * degree));
}

export function nodeColor(node: StyleNode): string {
  if (node.props?.is_self) return "#005bbf";
  return nodeColors[node.type] ?? "#64748b";
}

// ---------------------------------------------------------------- LOD (nível de detalhe por zoom)

export function lodBand(scale: number): LodBand {
  if (scale < G.lod.far) return "far";
  if (scale < G.lod.near) return "mid";
  return "near";
}

export const showIcon = (band: LodBand): boolean => band !== "far";

/** Rótulo do nó em foco é sempre visível (qualquer LOD). Fora disso:
 *  far = nenhum; mid = grau ≥ 3 ou foco/vizinho ou nó do turno atual; near = todos. */
export function showNodeLabel(band: LodBand, node: StyleNode, degree: number, ctx: StyleCtx): boolean {
  const isFocus = ctx.focusNodeId === node.id;
  if (isFocus) return true;
  if (band === "far") return false;
  if (band === "near") return true;
  const inFocus = !!ctx.focusNodeId && ctx.focusNeighbors.has(node.id);
  const isNew = ctx.recentTurn > 0 && (node.first_seen_turn ?? 0) === ctx.recentTurn;
  return degree >= 3 || inFocus || isNew;
}

/** Rótulo de aresta: em foco, só nas arestas focadas; senão, só na faixa "perto". */
export function showEdgeLabel(band: LodBand, link: LinkState, ctx: StyleCtx): boolean {
  if (ctx.focusNodeId) return link.focused;
  return band === "near";
}

export const edgeDash = (linkType: string, scale: number): number[] | null =>
  linkType === "related_to" ? [4 / scale, 2 / scale] : null;
