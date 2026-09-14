import { describe, it, expect } from "vitest";
import {
  emptyCtx, lodBand, lodThresholds, resolveLinkState, resolveNodeState, showEdgeLabel,
  showIcon, showNodeLabel, type StyleCtx, type StyleNode,
} from "../graphStyle";

const node = (id: string, turn = 1, extra: Partial<StyleNode> = {}): StyleNode =>
  ({ id, type: "person", first_seen_turn: turn, props: {}, ...extra });

const ctxWith = (o: Partial<StyleCtx>): StyleCtx => ({ ...emptyCtx(), ...o });

describe("resolveNodeState — precedência", () => {
  it("replay vence local (nó do futuro fica invisível mesmo dentro do modo local)", () => {
    const ctx = ctxWith({
      replay: { turn: 1 },
      localMode: { rootId: "a", depth: 1, nodeIds: new Set(["a"]) },
    });
    expect(resolveNodeState(node("a", 2), ctx).visible).toBe(false); // turn 2 > replay.turn 1
  });

  it("local vence foco (nó fora do conjunto local é invisível, não só esmaecido)", () => {
    const ctx = ctxWith({
      localMode: { rootId: "a", depth: 1, nodeIds: new Set(["a"]) },
      focusNodeId: "b",
      focusNeighbors: new Set(["b"]),
    });
    expect(resolveNodeState(node("b"), ctx).visible).toBe(false); // b não está em nodeIds
  });

  it("foco vence episódio (nó em foco fica 100%, não esmaecido pelo episódio)", () => {
    const ctx = ctxWith({
      focusNodeId: "a",
      focusNeighbors: new Set(),
      episode: { currentId: "ep2", dimmedAlpha: 0.3 },
    });
    const s = resolveNodeState(node("a", 1, { props: { episode_id: "ep1" } }), ctx);
    expect(s.alpha).toBe(1);
    expect(s.emphasis).toBe("focus");
  });

  it("foco esmaece os não-vizinhos a 0.15", () => {
    const ctx = ctxWith({ focusNodeId: "a", focusNeighbors: new Set(["b"]) });
    expect(resolveNodeState(node("c"), ctx).alpha).toBeCloseTo(0.15);
    expect(resolveNodeState(node("b"), ctx).emphasis).toBe("focus");
  });

  it("episódio esmaece nós de outro episódio a 0.3 (quando não há foco)", () => {
    const ctx = ctxWith({ episode: { currentId: "ep2", dimmedAlpha: 0.3 } });
    const s = resolveNodeState(node("x", 1, { props: { episode_id: "ep1" } }), ctx);
    expect(s.alpha).toBeCloseTo(0.3);
  });

  it("nó do turno atual recebe ênfase new", () => {
    const ctx = ctxWith({ recentTurn: 3 });
    expect(resolveNodeState(node("a", 3), ctx).emphasis).toBe("new");
    expect(resolveNodeState(node("a", 2), ctx).emphasis).toBe("normal");
  });
});

describe("resolveLinkState", () => {
  const vis = { visible: true, alpha: 1, emphasis: "normal" as const };
  const dim = { visible: true, alpha: 0.15, emphasis: "normal" as const };
  const foc = { visible: true, alpha: 1, emphasis: "focus" as const };
  const hidden = { visible: false, alpha: 0, emphasis: "normal" as const };

  it("aresta com uma ponta invisível é invisível", () => {
    expect(resolveLinkState(vis, hidden, "attendee").visible).toBe(false);
  });

  it("estrutural = min(alpha)*0.2; semântica = *0.3", () => {
    expect(resolveLinkState(vis, vis, "attendee").alpha).toBeCloseTo(0.2);
    expect(resolveLinkState(vis, vis, "related_to").alpha).toBeCloseTo(0.3);
    expect(resolveLinkState(vis, dim, "attendee").alpha).toBeCloseTo(0.03); // min(1,0.15)*0.2
  });

  it("aresta com as duas pontas em foco vai a 0.9", () => {
    const s = resolveLinkState(foc, foc, "attendee");
    expect(s.alpha).toBeCloseTo(0.9);
    expect(s.focused).toBe(true);
  });
});

describe("LOD", () => {
  it("no fit (scale ≈ fitScale) a faixa é MÉDIA, não longe — inclusive p/ grafo grande", () => {
    const bigFit = 0.35;                          // fit típico de ~40 nós
    const th = lodThresholds(bigFit);
    expect(lodBand(bigFit, th)).toBe("mid");       // ícones + rótulos no fit
    expect(lodBand(bigFit * 0.4, th)).toBe("far"); // só zoom manual bem abaixo do fit → longe
    expect(lodBand(bigFit * 3, th)).toBe("near");
  });

  it("limiares relativos com piso/teto", () => {
    const th = lodThresholds(1.0);
    expect(th.far).toBeCloseTo(0.55);
    expect(th.near).toBeCloseTo(1.6);
  });

  it("ícone some no far", () => {
    expect(showIcon("far")).toBe(false);
    expect(showIcon("mid")).toBe(true);
  });

  it("rótulo do nó: far nada (salvo foco), mid por grau≥3/novo/foco, near tudo", () => {
    const ctx = emptyCtx();
    expect(showNodeLabel("far", node("a"), 9, ctx)).toBe(false);
    expect(showNodeLabel("mid", node("a"), 1, ctx)).toBe(false);
    expect(showNodeLabel("mid", node("a"), 3, ctx)).toBe(true);       // grau alto
    expect(showNodeLabel("near", node("a"), 0, ctx)).toBe(true);
    // rótulo do nó em foco sempre visível, mesmo no far
    const fctx = ctxWith({ focusNodeId: "a" });
    expect(showNodeLabel("far", node("a"), 0, fctx)).toBe(true);
    // nó do turno atual aparece no mid
    expect(showNodeLabel("mid", node("z", 5), 0, ctxWith({ recentTurn: 5 }))).toBe(true);
  });

  it("rótulo de aresta: near mostra; em foco só as focadas", () => {
    const near = { visible: true, alpha: 1, focused: false };
    const focused = { visible: true, alpha: 0.9, focused: true };
    expect(showEdgeLabel("near", near, emptyCtx())).toBe(true);
    expect(showEdgeLabel("mid", near, emptyCtx())).toBe(false);
    const fctx = ctxWith({ focusNodeId: "a" });
    expect(showEdgeLabel("near", near, fctx)).toBe(false);     // em foco: só focadas
    expect(showEdgeLabel("near", focused, fctx)).toBe(true);
  });
});
