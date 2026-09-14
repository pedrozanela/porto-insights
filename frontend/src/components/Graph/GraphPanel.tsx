import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { nodeColors, nodeLabels } from "../../theme";
import type { GraphData, GraphNode } from "../../state/types";
import { shortLabel, EDGE_LABELS } from "../../graph/labels";
import { glyph, glyphType } from "../../graph/glyphs";
import { NodeDetail } from "./NodeDetail";
import { fetchDebugGraph, type DebugGraph } from "../../api/client";

const SELF_COLOR = "#005bbf";

export function GraphPanel({
  graph,
  onAskAbout,
  onPromote,
  debugGraph = false,
  conversationId = "",
}: {
  graph: GraphData;
  onAskAbout: (node: GraphNode) => void;
  onPromote: (ids: string[]) => void;
  debugGraph?: boolean;
  conversationId?: string;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hideSelf, setHideSelf] = useState(false);
  const [hoverEdge, setHoverEdge] = useState<string | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [staging, setStaging] = useState<DebugGraph | null>(null); // painel de staging (dev)
  const manualRef = useRef(false); // usuário deu pan/zoom → suspende auto-fit
  const highlightUntil = useRef(0);
  const [, forceTick] = useState(0);

  const MIN_ZOOM = 0.2, MAX_ZOOM = 8;

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  // Grau de cada nó (para tamanho por grau) e destaque dos nós do último turno.
  const degree = useMemo(() => {
    const d: Record<string, number> = {};
    graph.edges.forEach((e) => { d[e.source] = (d[e.source] || 0) + 1; d[e.target] = (d[e.target] || 0) + 1; });
    return d;
  }, [graph.edges]);

  const radiusOf = (id: string) => Math.max(6, Math.min(14, 6 + (degree[id] || 0) * 1.2));

  // Auto-fit ao crescer o grafo (a menos que o usuário tenha mexido), com teto/piso de escala.
  // Também dispara o pulso de destaque por 3s.
  useEffect(() => {
    if (!graph.nodes.length || !fgRef.current) return;
    manualRef.current = false;
    highlightUntil.current = Date.now() + 3000;
    const t = setTimeout(() => { if (!manualRef.current) fitToScreen(); }, 250);
    // anima o pulso por 3s
    const iv = setInterval(() => {
      forceTick((x) => x + 1);
      fgRef.current?.refresh?.();
      if (Date.now() > highlightUntil.current) clearInterval(iv);
    }, 80);
    return () => { clearTimeout(t); clearInterval(iv); };
  }, [graph.lastTurn, graph.nodes.length, size.w]);

  // Ajustar à tela: enquadra tudo com folga de 40px. O teto de escala só vale para grafos
  // minúsculos (≤3 nós), senão deixamos aproximar até o zoomToFit natural (limitado por MAX_ZOOM).
  const fitToScreen = () => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.zoomToFit(600, 40);
    setTimeout(() => {
      const z = fg.zoom();
      if (z < MIN_ZOOM) fg.zoom(MIN_ZOOM, 400);
      if (data.nodes.length <= 3 && z > 2.5) fg.zoom(2.5, 400);   // não estourar 1–3 nós
    }, 620);
  };

  const zoomBy = (factor: number) => {
    const fg = fgRef.current;
    if (!fg) return;
    manualRef.current = true;
    const z = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, fg.zoom() * factor));
    fg.zoom(z, 250);
  };

  const toggleFullscreen = () => {
    const el = rootRef.current;
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else el.requestFullscreen?.();
  };

  useEffect(() => {
    const onFs = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  const types = useMemo(() => [...new Set(graph.nodes.map((n) => n.type))], [graph.nodes]);
  const visibleCount = useMemo(
    () => graph.nodes.filter((n) => !n.props?.is_self).length, [graph.nodes]);

  const data = useMemo(() => {
    const visibleNodes = graph.nodes.filter(
      (n) => !hidden.has(n.type) && !(hideSelf && n.props?.is_self));
    const ids = new Set(visibleNodes.map((n) => n.id));
    return {
      nodes: visibleNodes.map((n) => {
        const self = !!n.props?.is_self;
        return { ...n, ...(self ? { fx: 0, fy: 0 } : {}) };
      }),
      links: graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => ({ ...e })),
    };
  }, [graph, hidden, hideSelf]);

  const empty = graph.nodes.length === 0;
  const toggleType = (t: string) =>
    setHidden((h) => { const n = new Set(h); n.has(t) ? n.delete(t) : n.add(t); return n; });

  // Teclado: + aproxima, − afasta, 0 ajusta à tela (quando o cursor está sobre o painel).
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomBy(1.4); }
    else if (e.key === "-" || e.key === "_") { e.preventDefault(); zoomBy(1 / 1.4); }
    else if (e.key === "0") { e.preventDefault(); manualRef.current = false; fitToScreen(); }
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
                  try { setStaging(await fetchDebugGraph(conversationId)); }
                  catch { /* debug off */ }
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
                cooldownTicks={40}
                d3AlphaDecay={0.08}
                onEngineStop={() => { if (!manualRef.current) fitToScreen(); }}
                onZoom={() => { manualRef.current = true; }}
                onNodeClick={(n: any) => setSelected(graph.nodes.find((x) => x.id === n.id) ?? null)}
                onBackgroundClick={() => setSelected(null)}
                nodeLabel={(n: any) => {
                  const full = n.props?.title || n.label || "";
                  return n.props?.provisional ? `${full} (inferido a partir do documento)` : full;
                }}
                linkColor={(l: any) => (l.type === "related_to" ? "#94a3b8" : "#cbd5e1")}
                linkLineDash={(l: any) => (l.type === "related_to" ? [4, 3] : null)}
                linkWidth={(l: any) => 1 + (l.weight || 0.5) * 1.5}
                linkDirectionalArrowLength={4}
                linkDirectionalArrowRelPos={1}
                onLinkHover={(l: any) => setHoverEdge(l ? (l.rationale ? `${EDGE_LABELS[l.type] || l.type}: ${l.rationale}` : (EDGE_LABELS[l.type] || l.type)) : null)}
                linkCanvasObjectMode={() => "after"}
                linkCanvasObject={(l: any, ctx, scale) => {
                  if (visibleCount > 12) return; // rótulos de aresta só até 12 nós
                  if (typeof l.source !== "object" || typeof l.target !== "object") return;
                  const txt = EDGE_LABELS[l.type] || l.type;
                  const mx = (l.source.x + l.target.x) / 2, my = (l.source.y + l.target.y) / 2;
                  const fs = 9 / scale;
                  ctx.font = `${fs}px system-ui`;
                  const w = ctx.measureText(txt).width;

                  // B7: oculta o rótulo da aresta se colidir com o rótulo de qualquer nó.
                  const er = { x0: mx - w / 2 - 2 / scale, y0: my - fs / 2 - 1 / scale,
                               x1: mx + w / 2 + 2 / scale, y1: my + fs / 2 + 1 / scale };
                  const nfs = 11 / scale;
                  for (const nd of data.nodes as any[]) {
                    if (typeof nd.x !== "number" || typeof nd.y !== "number") continue;
                    ctx.font = `${nfs}px system-ui`;
                    const nw = ctx.measureText(shortLabel(nd)).width;
                    const nr = radiusOf(nd.id) / scale;
                    const ly = nd.y + nr + nfs * 0.9;
                    const box = { x0: nd.x - nw / 2 - 3 / scale, y0: ly - nfs / 2 - 1 / scale,
                                  x1: nd.x + nw / 2 + 3 / scale, y1: ly + nfs / 2 + 1 / scale };
                    if (er.x0 < box.x1 && er.x1 > box.x0 && er.y0 < box.y1 && er.y1 > box.y0) return;
                  }
                  ctx.font = `${fs}px system-ui`; // restaura fonte da aresta

                  ctx.fillStyle = "rgba(255,255,255,0.85)";
                  ctx.fillRect(mx - w / 2 - 2 / scale, my - fs / 2 - 1 / scale, w + 4 / scale, fs + 2 / scale);
                  ctx.fillStyle = "#64748b";
                  ctx.textAlign = "center"; ctx.textBaseline = "middle";
                  ctx.fillText(txt, mx, my);
                }}
                nodeCanvasObject={(node: any, ctx, scale) => {
                  const self = !!node.props?.is_self;
                  const provisional = !!node.props?.provisional;
                  const color = self ? SELF_COLOR : (nodeColors[node.type] ?? "#64748b");
                  const r = radiusOf(node.id) / scale;

                  // pulso de destaque para nós novos OU recém-promovidos
                  const isNew = node.first_seen_turn === graph.lastTurn || graph.promoted.includes(node.id);
                  if (isNew && Date.now() < highlightUntil.current) {
                    const pulse = 1 + 0.4 * Math.abs(Math.sin(Date.now() / 250));
                    ctx.beginPath(); ctx.arc(node.x, node.y, r * 1.6 * pulse, 0, 2 * Math.PI);
                    ctx.fillStyle = color + "22"; ctx.fill();
                  }

                  ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
                  ctx.fillStyle = color; ctx.fill();
                  if (provisional) { // provisório: contorno tracejado, mais claro
                    ctx.globalAlpha = 0.55;
                    ctx.setLineDash([3 / scale, 2 / scale]); ctx.lineWidth = 1.5 / scale;
                    ctx.strokeStyle = color; ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1;
                  }
                  if (self) { ctx.lineWidth = 2 / scale; ctx.strokeStyle = SELF_COLOR; ctx.stroke(); }

                  // ícone (glyph branco) dentro do nó; "Você" mostra iniciais
                  if (self) {
                    ctx.fillStyle = "#fff"; ctx.font = `${r}px system-ui`;
                    ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText("V", node.x, node.y);
                  } else {
                    const g = glyph(glyphType(node));
                    if (g) { const s = r * 1.3; ctx.globalAlpha = provisional ? 0.7 : 1;
                      ctx.drawImage(g, node.x - s / 2, node.y - s / 2, s, s); ctx.globalAlpha = 1; }
                  }

                  // rótulo com halo (pílula), abaixo do nó
                  const label = shortLabel(node);
                  const fs = 11 / scale;
                  ctx.font = `${fs}px system-ui`;
                  const w = ctx.measureText(label).width;
                  const ly = node.y + r + fs * 0.9;
                  ctx.fillStyle = "rgba(255,255,255,0.82)";
                  ctx.fillRect(node.x - w / 2 - 3 / scale, ly - fs / 2 - 1 / scale, w + 6 / scale, fs + 2 / scale);
                  ctx.fillStyle = self ? "#94a3b8" : "#1a1f24";
                  ctx.textAlign = "center"; ctx.textBaseline = "middle";
                  ctx.fillText(label, node.x, ly);

                  // badge "+N participantes" para eventos com participantes colapsados
                  const staged = Number(node.props?.staged_participants || 0);
                  if (node.type === "calendar_event" && staged > 0) {
                    const bt = `+${staged}`; const bfs = 9 / scale;
                    ctx.font = `${bfs}px system-ui`; const bw = ctx.measureText(bt).width + 6 / scale;
                    const bx = node.x + r, by = node.y - r;
                    ctx.fillStyle = "#64748b";
                    ctx.beginPath(); ctx.roundRect(bx - bw / 2, by - bfs, bw, bfs + 3 / scale, 3 / scale); ctx.fill();
                    ctx.fillStyle = "#fff"; ctx.fillText(bt, bx, by - bfs / 2 + 1 / scale);
                  }
                }}
                nodePointerAreaPaint={(node: any, color, ctx, scale) => {
                  ctx.fillStyle = color; ctx.beginPath();
                  ctx.arc(node.x, node.y, radiusOf(node.id) / scale + 2 / scale, 0, 2 * Math.PI); ctx.fill();
                }}
              />
              {hoverEdge && (
                <div className="pointer-events-none absolute left-1/2 top-2 -translate-x-1/2 rounded-md bg-textc/90 px-2 py-1 text-xs text-white">
                  {hoverEdge}
                </div>
              )}
              {/* Controles de zoom/enquadramento (canto inferior direito). */}
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
              </div>
              {staging && (
                <div className="absolute left-3 top-3 max-h-[80%] w-72 overflow-auto rounded-lg border border-borderc bg-surface/97 p-2 text-xs shadow-lg">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-semibold text-textc">Staging ({staging.counts.staging})</span>
                    <button onClick={() => setStaging(null)} className="text-muted hover:text-textc">✕</button>
                  </div>
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
                  onClose={() => setSelected(null)} />
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

// Mini-ícone na legenda (reusa o glyph offscreen).
function GlyphChip({ type }: { type: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const g = glyph(type);
    const el = ref.current;
    if (g && el) { const ctx = el.getContext("2d"); ctx?.clearRect(0, 0, 14, 14); ctx?.drawImage(g, 0, 0, 14, 14); }
  }, [type]);
  return <canvas ref={ref} width={14} height={14} className="h-2.5 w-2.5" />;
}
