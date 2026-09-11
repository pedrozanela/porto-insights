import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { nodeColors, nodeLabels } from "../../theme";
import type { GraphData, GraphNode } from "../../state/types";
import { shortLabel, EDGE_LABELS } from "../../graph/labels";
import { glyph } from "../../graph/glyphs";
import { NodeDetail } from "./NodeDetail";

const SELF_COLOR = "#005bbf";

export function GraphPanel({
  graph,
  onAskAbout,
  onPromote,
}: {
  graph: GraphData;
  onAskAbout: (node: GraphNode) => void;
  onPromote: (ids: string[]) => void;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hideSelf, setHideSelf] = useState(false);
  const [hoverEdge, setHoverEdge] = useState<string | null>(null);
  const manualRef = useRef(false); // usuário deu pan/zoom → suspende auto-fit
  const highlightUntil = useRef(0);
  const [, forceTick] = useState(0);

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
    const t = setTimeout(() => { if (!manualRef.current) fitWithCap(); }, 250);
    // anima o pulso por 3s
    const iv = setInterval(() => {
      forceTick((x) => x + 1);
      fgRef.current?.refresh?.();
      if (Date.now() > highlightUntil.current) clearInterval(iv);
    }, 80);
    return () => { clearTimeout(t); clearInterval(iv); };
  }, [graph.lastTurn, graph.nodes.length, size.w]);

  const fitWithCap = () => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.zoomToFit(600, 60);
    setTimeout(() => {
      const z = fg.zoom();
      if (z > 2.5) fg.zoom(2.5, 400);
      if (z < 0.25) fg.zoom(0.25, 400);
    }, 620);
  };

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

  return (
    <div className="flex h-full flex-col bg-surface">
      <div className="flex items-center justify-between border-b border-borderc px-5 py-3">
        <h2 className="text-sm font-semibold text-textc">Grafo de relacionamentos</h2>
        {!empty && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">{visibleCount} nós</span>
            <button onClick={() => { manualRef.current = false; fitWithCap(); }}
              className="rounded-md border border-borderc px-2 py-1 text-xs text-textc hover:bg-surfaceMuted">
              Recentrar
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
                maxZoom={2.5}
                cooldownTicks={40}
                d3AlphaDecay={0.08}
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
                    const g = glyph(node.type);
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
