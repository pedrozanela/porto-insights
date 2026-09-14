import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { graph as G, nodeColors, nodeLabels } from "../../theme";
import type { GraphData, GraphNode } from "../../state/types";
import { shortLabel, EDGE_LABELS } from "../../graph/labels";
import { glyph, glyphType } from "../../graph/glyphs";
import { bfs, buildNeighbors, degreeMap } from "../../graph/graphModel";
import {
  edgeDash, lodBand, lodThresholds, nodeColor, radiusOf, resolveLinkState, resolveNodeState,
  showEdgeLabel, showIcon, showNodeLabel, type StyleCtx,
} from "../../graph/graphStyle";
import {
  configureForces, pinAfterDrag, pinExisting, releaseDragPin, releasePins,
} from "../../graph/graphPhysics";
import { fixtureFromUrl } from "../../graph/graphFixture";
import { NodeDetail } from "./NodeDetail";
import { fetchDebugGraph, type DebugGraph } from "../../api/client";

const MIN_ZOOM = 0.2, MAX_ZOOM = 8;
const PIN_CAP_MS = 3000;  // teto p/ liberar pins se o resfriamento demorar

const _measure = document.createElement("canvas").getContext("2d");
function labelWidth(text: string, px: number): number {
  if (!_measure) return text.length * px * 0.6;
  _measure.font = `${px}px system-ui`;
  return _measure.measureText(text).width;
}

export function GraphPanel({
  graph: graphProp,
  onAskAbout,
  onPromote,
  debugGraph = false,
  conversationId = "",
  streaming = false,
}: {
  graph: GraphData;
  onAskAbout: (node: GraphNode) => void;
  onPromote: (ids: string[]) => void;
  debugGraph?: boolean;
  conversationId?: string;
  streaming?: boolean;
}) {
  const graph = useMemo(() => fixtureFromUrl() ?? graphProp, [graphProp]);
  const rootRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hideSelf, setHideSelf] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [staging, setStaging] = useState<DebugGraph | null>(null);
  // Bloco B (Focar / vizinhança local) e Bloco C (Reproduzir)
  const [localMode, setLocalMode] = useState<{ rootId: string; label: string; depth: number; nodeIds: Set<string> } | null>(null);
  const [replay, setReplay] = useState<{ turn: number; playing: boolean; speed: number } | null>(null);

  // Estado de INTERAÇÃO em refs (lidos dentro de nodeCanvasObject/linkCanvasObject) — sem setState
  // por frame/hover; o redesenho é dirigido pelo loop de refresh (animateUntil).
  const focusIdRef = useRef<string | null>(null);
  const focusPinnedRef = useRef(false);
  const manualRef = useRef(false);
  const alphaRef = useRef<Map<string, number>>(new Map());
  const animateUntil = useRef(0);
  const fitScaleRef = useRef(1);                // escala do último fit → base do LOD
  const pinnedRef = useRef<any[]>([]);          // nós fixados no reaquecimento
  const dragPinsRef = useRef<Set<any>>(new Set());
  const capTimerRef = useRef<number | null>(null);

  const degree = useMemo(() => degreeMap(graph.edges), [graph.edges]);
  const neighbors = useMemo(() => buildNeighbors(graph.edges), [graph.edges]);
  const types = useMemo(() => [...new Set(graph.nodes.map((n) => n.type))], [graph.nodes]);
  const visibleCount = useMemo(
    () => graph.nodes.filter((n) => !n.props?.is_self).length, [graph.nodes]);
  const empty = graph.nodes.length === 0;

  // graphData: REUSA objetos de nó (preserva posição) e recria o container só quando o conjunto muda.
  const nodeObjs = useRef<Map<string, any>>(new Map());
  const data = useMemo(() => {
    const map = nodeObjs.current;
    const seen = new Set<string>();
    const nodes: any[] = [];
    for (const n of graph.nodes) {
      if (hidden.has(n.type) || (hideSelf && n.props?.is_self)) continue;
      seen.add(n.id);
      let obj = map.get(n.id);
      if (!obj) {
        obj = { ...n };
        if (n.props?.is_self) { obj.fx = 0; obj.fy = 0; }
        map.set(n.id, obj);
      } else {
        obj.label = n.label; obj.type = n.type; obj.props = n.props;
        obj.first_seen_turn = n.first_seen_turn; obj.url = n.url;
      }
      nodes.push(obj);
    }
    for (const id of [...map.keys()]) if (!seen.has(id)) map.delete(id);
    const ids = new Set(nodes.map((n) => n.id));
    const links = graph.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({ ...e }));
    return { nodes, links };
  }, [graph, hidden, hideSelf]);

  // contexto de estilo: foco vem de refs (hover/click), localMode/replay de state (mudam raramente)
  const buildCtx = (): StyleCtx => ({
    focusNodeId: focusIdRef.current,
    focusPinned: focusPinnedRef.current,
    focusNeighbors: focusIdRef.current ? (neighbors.get(focusIdRef.current) ?? new Set<string>()) : new Set<string>(),
    localMode,
    replay: replay ? { turn: replay.turn } : null,
    recentTurn: replay ? replay.turn : graph.lastTurn,   // no replay, o turno atual pulsa
    episode: null,
  });

  const easedAlpha = (id: string, target: number): number => {
    const cur = alphaRef.current.get(id);
    if (cur === undefined) { alphaRef.current.set(id, target); return target; }
    const next = cur + (target - cur) * G.ease;
    const v = Math.abs(next - target) < 0.01 ? target : next;
    alphaRef.current.set(id, v);
    return v;
  };

  const bumpAnim = (ms = 400) => { animateUntil.current = Date.now() + ms; };

  // --- observers e loops ---
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  useEffect(() => {   // refresh() só enquanto há transição de alpha/pulso pendente
    let raf = 0;
    const tick = () => {
      if (Date.now() < animateUntil.current) fgRef.current?.refresh?.();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    const onFs = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  useEffect(() => {   // hook só de dev p/ dirigir zoom/foco nas telas de teste
    if (!(import.meta as any).env?.DEV) return;
    (window as any).__graphDev = {
      fg: fgRef.current,
      focus: (id: string) => { focusIdRef.current = id; focusPinnedRef.current = true; bumpAnim(); },
      hover: (id: string | null) => { focusPinnedRef.current = false; focusIdRef.current = id; bumpAnim(); },
      fit: () => { manualRef.current = false; fitToScreen(); },
      list: () => graph.nodes.map((n) => ({ id: n.id, type: n.type, label: n.label })),
      screenOf: (id: string) => {
        const n = nodeObjs.current.get(id);
        if (!n || typeof n.x !== "number" || !fgRef.current?.graph2ScreenCoords) return null;
        return fgRef.current.graph2ScreenCoords(n.x, n.y);
      },
      curFocus: () => focusIdRef.current,
      focar: (id: string) => { const n = graph.nodes.find((x) => x.id === id); if (n) enterLocal(n); },
      depth: (d: number) => setLocalDepth(d),
      exitLocal,
      play: () => startReplay(),
      goto: (turn: number) => setReplay((r) => (r ? { ...r, playing: false, turn } : { turn, playing: false, speed: 1 })),
      endReplay,
    };
  });

  // libera todos os pins (reaquecimento + arraste) — chamado no resfriamento ou no teto de 3s
  const releaseAllPins = () => {
    if (capTimerRef.current) { clearTimeout(capTimerRef.current); capTimerRef.current = null; }
    releasePins(pinnedRef.current);
    pinnedRef.current = [];
    dragPinsRef.current.forEach((n) => releaseDragPin(n));
    dragPinsRef.current.clear();
  };

  // configura forças + reaquece com pin dos existentes + auto-fit, a cada delta
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !data.nodes.length || !size.w) return;
    configureForces(fg, {
      collideRadius: (n: any) => radiusOf(degree.get(n.id) || 0, !!n.props?.is_self)
        + labelWidth(shortLabel(n), G.labelBase) / 2 + 4,
    });
    pinnedRef.current = pinExisting(fg, data.nodes,
      (id) => nodeObjs.current.get(id)?.first_seen_turn !== graph.lastTurn);
    if (capTimerRef.current) clearTimeout(capTimerRef.current);
    capTimerRef.current = window.setTimeout(releaseAllPins, PIN_CAP_MS);   // teto de 3s
    manualRef.current = false;
    bumpAnim(3200);   // pulso dos novos ~3s
    const t = setTimeout(() => { if (!manualRef.current) fitToScreen(); }, 500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph.lastTurn, size.w, data.nodes.length]);

  // --- enquadramento (inclui rótulos; grava a escala do fit → base do LOD) ---
  const fitToScreen = () => {
    const fg = fgRef.current;
    if (!fg || !data.nodes.length) return;
    const ctx = buildCtx();
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, count = 0;
    for (const n of data.nodes as any[]) {
      if (typeof n.x !== "number" || !resolveNodeState(n, ctx).visible) continue;
      const r = radiusOf(degree.get(n.id) || 0, !!n.props?.is_self);
      const halfW = Math.max(r, labelWidth(shortLabel(n), G.labelBase) / 2 + 3);
      minX = Math.min(minX, n.x - halfW); maxX = Math.max(maxX, n.x + halfW);
      minY = Math.min(minY, n.y - r); maxY = Math.max(maxY, n.y + r + G.labelBase + 4);
      count++;
    }
    if (!isFinite(minX)) return;
    const pad = 40;
    const w = Math.max(1, maxX - minX), h = Math.max(1, maxY - minY);
    let scale = Math.min((size.w - pad * 2) / w, (size.h - pad * 2) / h);
    if (count <= 3) scale = (size.w * 0.4) / w;
    scale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, scale));
    fitScaleRef.current = scale;
    fg.centerAt((minX + maxX) / 2, (minY + maxY) / 2, 600);
    fg.zoom(scale, 600);
  };

  const zoomBy = (factor: number) => {
    const fg = fgRef.current;
    if (!fg) return;
    manualRef.current = true;
    fg.zoom(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, fg.zoom() * factor)), 250);
  };

  const toggleFullscreen = () => {
    const el = rootRef.current;
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else el.requestFullscreen?.();
  };

  const clearFocus = () => { focusIdRef.current = null; focusPinnedRef.current = false; bumpAnim(); };

  // --- Bloco B: Focar (vizinhança local por BFS sobre os nós VISÍVEIS) ---
  const visibleIds = () => new Set((data.nodes as any[]).map((n) => n.id));
  const computeLocal = (rootId: string, depth: number, label: string) =>
    ({ rootId, label, depth, nodeIds: bfs(neighbors, rootId, depth, visibleIds()) });

  const enterLocal = (node: GraphNode) => {
    clearFocus();
    setSelected(null);
    setLocalMode(computeLocal(node.id, 1, node.label));
  };
  const setLocalDepth = (depth: number) =>
    setLocalMode((lm) => (lm ? computeLocal(lm.rootId, depth, lm.label) : lm));
  const exitLocal = () => setLocalMode(null);

  useEffect(() => {   // ao entrar/mudar profundidade/sair do modo local, reenquadra
    if (!data.nodes.length) return;
    manualRef.current = false;
    bumpAnim(700);
    const t = setTimeout(fitToScreen, 60);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localMode]);

  // --- Bloco C: Reproduzir ---
  const canReplay = graph.turns.length > 1 && !streaming;
  const startReplay = () => {
    if (!canReplay) return;
    clearFocus(); setSelected(null); setLocalMode(null);
    setReplay({ turn: 1, playing: true, speed: 1 });
  };
  const endReplay = () => { setReplay(null); manualRef.current = false; bumpAnim(700); setTimeout(fitToScreen, 60); };
  const stepReplay = (dir: number) =>
    setReplay((r) => (r ? { ...r, playing: false, turn: Math.max(1, Math.min(graph.lastTurn, r.turn + dir)) } : r));
  const togglePlay = () => setReplay((r) => (r ? { ...r, playing: !r.playing } : r));
  const setSpeed = (s: number) => setReplay((r) => (r ? { ...r, speed: s } : r));

  useEffect(() => {   // avança o replay e reenquadra os nós já revelados a cada passo
    if (!replay) return;
    manualRef.current = false;
    bumpAnim(900);
    const t = setTimeout(fitToScreen, 60);
    let adv: number | undefined;
    if (replay.playing && replay.turn < graph.lastTurn) {
      adv = window.setTimeout(() => setReplay((r) => (r ? { ...r, turn: r.turn + 1 } : r)), 800 / replay.speed);
    } else if (replay.playing && replay.turn >= graph.lastTurn) {
      adv = window.setTimeout(() => setReplay((r) => (r ? { ...r, playing: false } : r)), 200);
    }
    return () => { clearTimeout(t); if (adv) clearTimeout(adv); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replay?.turn, replay?.playing, replay?.speed]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomBy(1.4); }
    else if (e.key === "-" || e.key === "_") { e.preventDefault(); zoomBy(1 / 1.4); }
    else if (e.key === "0") { e.preventDefault(); manualRef.current = false; fitToScreen(); }
    else if (e.key === "Escape") {
      if (replay) endReplay();
      else if (localMode) exitLocal();
      else { clearFocus(); setSelected(null); }
    }
  };

  const toggleType = (t: string) =>
    setHidden((h) => { const n = new Set(h); n.has(t) ? n.delete(t) : n.add(t); return n; });

  // --- desenho ---
  const drawNode = (node: any, c: CanvasRenderingContext2D, scale: number) => {
    const ctx = buildCtx();
    const st = resolveNodeState(node, ctx);
    if (!st.visible) return;
    const a = easedAlpha(node.id, st.alpha);
    if (a < 0.03) return;
    const band = lodBand(scale, lodThresholds(fitScaleRef.current));
    const self = !!node.props?.is_self;
    const deg = degree.get(node.id) || 0;
    const r = radiusOf(deg, self) / scale;
    const color = nodeColor(node);
    c.globalAlpha = a;

    if (st.emphasis === "new" && Date.now() < animateUntil.current) {
      const pulse = 1 + 0.4 * Math.abs(Math.sin(Date.now() / 250));
      c.beginPath(); c.arc(node.x, node.y, r * 1.7 * pulse, 0, 2 * Math.PI);
      c.fillStyle = color + "22"; c.fill();
    }

    c.beginPath(); c.arc(node.x, node.y, r, 0, 2 * Math.PI);
    c.fillStyle = color; c.fill();

    if (node.props?.provisional) {
      c.setLineDash([3 / scale, 2 / scale]); c.lineWidth = 1.5 / scale;
      c.strokeStyle = color; c.globalAlpha = a * 0.7; c.stroke();
      c.setLineDash([]); c.globalAlpha = a;
    }
    if (self) {
      c.lineWidth = 2 / scale; c.strokeStyle = "#005bbf"; c.stroke();
      c.fillStyle = "#fff"; c.font = `${r}px system-ui`;
      c.textAlign = "center"; c.textBaseline = "middle"; c.fillText("V", node.x, node.y);
    } else if (showIcon(band)) {
      const g = glyph(glyphType(node));
      if (g) { const s = r * 1.3; c.drawImage(g, node.x - s / 2, node.y - s / 2, s, s); }
    }

    if (showNodeLabel(band, node, deg, ctx)) {   // rótulo do nó em foco aparece em qualquer LOD
      const label = shortLabel(node);
      const fs = G.labelBase / scale;
      c.font = `${fs}px system-ui`;
      const w = c.measureText(label).width;
      const ly = node.y + r + fs * 0.9;
      c.fillStyle = `rgba(255,255,255,${0.82 * a})`;
      c.fillRect(node.x - w / 2 - 3 / scale, ly - fs / 2 - 1 / scale, w + 6 / scale, fs + 2 / scale);
      c.fillStyle = self ? "#94a3b8" : "#1a1f24";
      c.textAlign = "center"; c.textBaseline = "middle";
      c.fillText(label, node.x, ly);
    }

    const staged = Number(node.props?.staged_participants || 0);
    if (node.type === "calendar_event" && staged > 0 && band !== "far") {
      const bt = `+${staged}`, bfs = 9 / scale;
      c.font = `${bfs}px system-ui`;
      const bw = c.measureText(bt).width + 6 / scale;
      const bx = node.x + r, by = node.y - r;
      c.fillStyle = "#64748b";
      c.beginPath(); c.roundRect(bx - bw / 2, by - bfs, bw, bfs + 3 / scale, 3 / scale); c.fill();
      c.fillStyle = "#fff"; c.fillText(bt, bx, by - bfs / 2 + 1 / scale);
    }
    c.globalAlpha = 1;
  };

  const nodeLabelRect = (nd: any, c: CanvasRenderingContext2D, scale: number) => {
    const r = radiusOf(degree.get(nd.id) || 0, !!nd.props?.is_self) / scale;
    const nfs = G.labelBase / scale;
    c.font = `${nfs}px system-ui`;
    const nw = c.measureText(shortLabel(nd)).width;
    const ly = nd.y + r + nfs * 0.9;
    return { x0: nd.x - nw / 2 - 3 / scale, y0: ly - nfs / 2 - 1 / scale,
             x1: nd.x + nw / 2 + 3 / scale, y1: ly + nfs / 2 + 1 / scale };
  };

  const drawLink = (link: any, c: CanvasRenderingContext2D, scale: number) => {
    const s = link.source, t = link.target;
    if (typeof s !== "object" || typeof t !== "object") return;
    const ctx = buildCtx();
    const ss = resolveNodeState(s, ctx), ts = resolveNodeState(t, ctx);
    const sa = { ...ss, alpha: easedAlpha(s.id, ss.alpha) };
    const ta = { ...ts, alpha: easedAlpha(t.id, ts.alpha) };
    const ls = resolveLinkState(sa, ta, link.type);
    if (!ls.visible || ls.alpha < 0.02) return;

    const dash = edgeDash(link.type, scale);
    c.beginPath(); c.moveTo(s.x, s.y); c.lineTo(t.x, t.y);
    c.strokeStyle = `rgba(${G.edgeColor}, ${ls.alpha})`;
    c.lineWidth = (ls.focused ? 1.5 : 1) / scale;
    if (dash) c.setLineDash(dash); else c.setLineDash([]);
    c.stroke(); c.setLineDash([]);

    const band = lodBand(scale, lodThresholds(fitScaleRef.current));
    if (!showEdgeLabel(band, ls, ctx)) return;
    const txt = EDGE_LABELS[link.type] || link.type;
    const mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2;
    const fs = G.edgeLabelBase / scale;
    c.font = `${fs}px system-ui`;
    const w = c.measureText(txt).width;
    const er = { x0: mx - w / 2 - 2 / scale, y0: my - fs / 2 - 1 / scale,
                 x1: mx + w / 2 + 2 / scale, y1: my + fs / 2 + 1 / scale };
    for (const nd of data.nodes as any[]) {
      if (typeof nd.x !== "number" || !resolveNodeState(nd, ctx).visible) continue;
      const b = nodeLabelRect(nd, c, scale);
      if (er.x0 < b.x1 && er.x1 > b.x0 && er.y0 < b.y1 && er.y1 > b.y0) return;
    }
    c.font = `${fs}px system-ui`;
    c.fillStyle = `rgba(255,255,255,0.85)`;
    c.fillRect(er.x0, er.y0, w + 4 / scale, fs + 2 / scale);
    c.fillStyle = "#64748b"; c.textAlign = "center"; c.textBaseline = "middle";
    c.fillText(txt, mx, my);
  };

  const paintPointer = (node: any, color: string, c: CanvasRenderingContext2D, scale: number) => {
    if (!resolveNodeState(node, buildCtx()).visible) return;
    const r = radiusOf(degree.get(node.id) || 0, !!node.props?.is_self) / scale;
    c.fillStyle = color;
    c.beginPath(); c.arc(node.x, node.y, r + 2 / scale, 0, 2 * Math.PI); c.fill();
    const b = nodeLabelRect(node, c, scale);   // hit-area cobre o rótulo (hover no rótulo foca)
    c.fillRect(b.x0, b.y0, b.x1 - b.x0, b.y1 - b.y0);
  };

  return (
    <div ref={rootRef} tabIndex={0} onKeyDown={onKeyDown}
      className="flex h-full flex-col bg-surface outline-none">
      <div className="flex items-center justify-between border-b border-borderc px-5 py-3">
        <h2 className="text-sm font-semibold text-textc">Grafo de relacionamentos</h2>
        {!empty && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">{visibleCount} nós</span>
            {debugGraph && (
              <button
                onClick={async () => {
                  if (staging) { setStaging(null); return; }
                  try { setStaging(await fetchDebugGraph(conversationId)); } catch { /* off */ }
                }}
                className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-800 hover:bg-amber-100">
                Staging
              </button>
            )}
            <button onClick={() => { manualRef.current = false; fitToScreen(); }}
              className="rounded-md border border-borderc px-2 py-1 text-xs text-textc hover:bg-surfaceMuted">
              Ajustar à tela
            </button>
          </div>
        )}
      </div>

      <div ref={wrapRef} className="relative flex-1 overflow-hidden">
        {empty ? (
          <div className="flex h-full items-center justify-center px-8 text-center">
            <p className="max-w-xs text-sm text-muted">
              Conforme você pergunta, as conexões entre agenda, emails, documentos e dados aparecem aqui.
            </p>
          </div>
        ) : (
          size.w > 0 && (
            <>
              <ForceGraph2D
                ref={fgRef}
                width={size.w}
                height={size.h}
                graphData={data}
                backgroundColor="#ffffff"
                minZoom={MIN_ZOOM}
                maxZoom={MAX_ZOOM}
                cooldownTicks={60}
                d3AlphaDecay={0.08}
                d3VelocityDecay={0.3}
                enableNodeDrag
                onZoom={() => { manualRef.current = true; }}
                onEngineStop={() => { releaseAllPins(); if (!manualRef.current) fitToScreen(); }}
                onNodeHover={(n: any) => {
                  if (replay) return;   // durante o replay o hover não muda o foco
                  if (!focusPinnedRef.current) { focusIdRef.current = n?.id ?? null; bumpAnim(); }
                }}
                onNodeClick={(n: any) => {
                  focusIdRef.current = n.id; focusPinnedRef.current = true; bumpAnim();
                  setSelected(graph.nodes.find((x) => x.id === n.id) ?? null);
                }}
                onNodeDragEnd={(n: any) => { pinAfterDrag(n); dragPinsRef.current.add(n); bumpAnim(); }}
                onBackgroundClick={() => { clearFocus(); setSelected(null); }}
                nodeLabel={(n: any) => {
                  const full = n.props?.title || n.label || "";
                  return n.props?.provisional ? `${full} (inferido a partir do documento)` : full;
                }}
                nodeCanvasObjectMode={() => "replace"}
                nodeCanvasObject={drawNode}
                nodePointerAreaPaint={paintPointer}
                linkCanvasObjectMode={() => "replace"}
                linkCanvasObject={drawLink}
              />

              <div className="absolute bottom-3 right-3 flex flex-col items-stretch gap-1">
                <div className="flex overflow-hidden rounded-md border border-borderc bg-surface/95 shadow-sm">
                  <button onClick={() => zoomBy(1.4)} title="Aproximar (+)"
                    className="px-2.5 py-1 text-sm text-textc hover:bg-surfaceMuted">+</button>
                  <span className="w-px bg-borderc" />
                  <button onClick={() => zoomBy(1 / 1.4)} title="Afastar (−)"
                    className="px-2.5 py-1 text-sm text-textc hover:bg-surfaceMuted">−</button>
                </div>
                <button onClick={() => { manualRef.current = false; fitToScreen(); }}
                  className="rounded-md border border-borderc bg-surface/95 px-2 py-1 text-xs text-textc shadow-sm hover:bg-surfaceMuted">
                  Ajustar à tela
                </button>
                <button onClick={toggleFullscreen}
                  className="rounded-md border border-borderc bg-surface/95 px-2 py-1 text-xs text-textc shadow-sm hover:bg-surfaceMuted">
                  {fullscreen ? "Sair" : "Expandir"}
                </button>
                {!replay && (
                  <button onClick={startReplay} disabled={!canReplay} title={canReplay ? "" : "Precisa de 2+ turnos"}
                    className="rounded-md border border-borderc bg-surface/95 px-2 py-1 text-xs text-textc shadow-sm hover:bg-surfaceMuted disabled:opacity-40">
                    Reproduzir
                  </button>
                )}
              </div>

              {/* Bloco B: breadcrumb + profundidade do modo Focar */}
              {localMode && (
                <div className="absolute left-3 top-3 flex items-center gap-2 rounded-lg border border-borderc bg-surface/97 px-3 py-1.5 text-xs shadow-sm">
                  <button onClick={exitLocal} className="text-muted hover:text-primary">Grafo completo</button>
                  <span className="text-muted">›</span>
                  <span className="font-medium text-textc">Focar em {localMode.label}</span>
                  <span className="text-muted">· {localMode.nodeIds.size} objetos</span>
                  <span className="ml-2 flex overflow-hidden rounded-md border border-borderc">
                    {[1, 2, 3].map((d) => (
                      <button key={d} onClick={() => setLocalDepth(d)}
                        className={`px-1.5 py-0.5 ${localMode.depth === d ? "bg-primary text-white" : "text-textc hover:bg-surfaceMuted"}`}>
                        {d}
                      </button>
                    ))}
                  </span>
                  <button onClick={exitLocal}
                    className="ml-1 rounded-md border border-borderc px-2 py-0.5 text-textc hover:bg-surfaceMuted">
                    Voltar ao grafo completo
                  </button>
                </div>
              )}

              {/* Bloco C: legenda + controles do Reproduzir */}
              {replay && (
                <>
                  <div className="pointer-events-none absolute left-3 top-3 max-w-[60%] rounded-lg border border-borderc bg-surface/97 px-3 py-2 shadow-sm">
                    <div className="text-xs font-semibold text-primary">Turno {replay.turn} de {graph.lastTurn}</div>
                    <div className="mt-0.5 overflow-hidden text-sm text-textc"
                      style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                      {graph.turns.find((t) => t.index === replay.turn)?.question ?? ""}
                    </div>
                  </div>
                  <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-lg border border-borderc bg-surface/97 px-2 py-1 text-xs shadow-sm">
                    <button onClick={() => stepReplay(-1)} className="px-1.5 py-0.5 text-textc hover:bg-surfaceMuted" title="Anterior">‹</button>
                    <button onClick={togglePlay} className="px-2 py-0.5 font-medium text-primary hover:bg-surfaceMuted">
                      {replay.playing ? "Pausar" : "Continuar"}
                    </button>
                    <button onClick={() => stepReplay(1)} className="px-1.5 py-0.5 text-textc hover:bg-surfaceMuted" title="Próximo">›</button>
                    <span className="mx-1 w-px self-stretch bg-borderc" />
                    {[1, 2].map((s) => (
                      <button key={s} onClick={() => setSpeed(s)}
                        className={`px-1.5 py-0.5 ${replay.speed === s ? "text-primary font-semibold" : "text-muted hover:text-textc"}`}>
                        {s}×
                      </button>
                    ))}
                    <span className="mx-1 w-px self-stretch bg-borderc" />
                    <button onClick={endReplay} className="px-2 py-0.5 text-textc hover:bg-surfaceMuted">Encerrar</button>
                  </div>
                </>
              )}

              {staging && (
                <div className="absolute left-3 top-3 max-h-[80%] w-72 overflow-auto rounded-lg border border-borderc bg-surface/97 p-2 text-xs shadow-lg">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-semibold text-textc">Staging ({staging.counts.staging})</span>
                    <button onClick={() => setStaging(null)} className="text-muted hover:text-textc">✕</button>
                  </div>
                  {staging.linker && (
                    <div className={`mb-1 rounded px-1.5 py-1 ${staging.linker.failed ? "bg-amber-100 text-amber-800" : "bg-surfaceMuted text-muted"}`}>
                      linker: {staging.linker.failed ? `falhou — ${staging.linker.error || "?"}` : "ok"}
                      {" "}· entrada {staging.linker.input_size ?? "?"} (listados {staging.linker.listed ?? "?"})
                      {" "}· relevantes {staging.linker.relevant ?? 0}
                    </div>
                  )}
                  {staging.staging.length === 0 && <p className="text-muted">Nenhum nó em staging.</p>}
                  {staging.staging.map((r) => (
                    <div key={r.id} className="border-b border-borderc py-1">
                      <div className="text-textc">{r.label} <span className="text-muted">· {r.type}</span></div>
                      <div className="text-muted">turno {r.first_seen_turn} — {r.reason || "—"}</div>
                    </div>
                  ))}
                </div>
              )}

              {selected && (
                <NodeDetail node={selected} graph={graph}
                  onAskAbout={(n) => { onAskAbout(n); setSelected(null); }}
                  onPromote={onPromote}
                  onFocus={enterLocal}
                  onClose={() => { setSelected(null); clearFocus(); }} />
              )}
            </>
          )
        )}
      </div>

      {!empty && (
        <div className="flex flex-wrap items-center gap-2 border-t border-borderc px-5 py-2">
          {types.map((t) => (
            <button key={t} onClick={() => toggleType(t)}
              className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs ${hidden.has(t) ? "border-borderc text-muted opacity-50" : "border-borderc text-textc"}`}>
              <span className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full" style={{ background: nodeColors[t] ?? "#64748b" }}>
                <GlyphChip type={t} />
              </span>
              {nodeLabels[t] ?? t}
            </button>
          ))}
          {graph.nodes.some((n) => n.props?.is_self) && (
            <button onClick={() => setHideSelf((v) => !v)}
              className={`ml-auto rounded-full border border-borderc px-2 py-0.5 text-xs ${hideSelf ? "text-primary" : "text-muted"}`}>
              {hideSelf ? "Mostrar você" : "Ocultar você"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function GlyphChip({ type }: { type: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const g = glyph(type);
    const el = ref.current;
    if (g && el) { const c = el.getContext("2d"); c?.clearRect(0, 0, 14, 14); c?.drawImage(g, 0, 0, 14, 14); }
  }, [type]);
  return <canvas ref={ref} width={14} height={14} className="h-2.5 w-2.5" />;
}
