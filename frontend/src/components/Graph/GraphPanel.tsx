import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { nodeColors, nodeLabels } from "../../theme";
import type { GraphData, GraphNode } from "../../state/types";
import { NodeDetail } from "./NodeDetail";

// Grafo de relacionamentos interativo: zoom/pan (nativo), clique no nó abre detalhe,
// hover em aresta mostra tipo/justificativa, filtro por tipo, recentrar, e destaque dos
// nós adicionados no último turno.
export function GraphPanel({
  graph,
  onAskAbout,
}: {
  graph: GraphData;
  onAskAbout: (node: GraphNode) => void;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hoverEdge, setHoverEdge] = useState<{ x: number; y: number; text: string } | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (graph.nodes.length && fgRef.current) {
      const t = setTimeout(() => fgRef.current?.zoomToFit(400, 60), 300);
      return () => clearTimeout(t);
    }
  }, [graph.nodes.length, size.w]);

  const types = useMemo(() => [...new Set(graph.nodes.map((n) => n.type))], [graph.nodes]);

  const data = useMemo(() => {
    const visibleNodes = graph.nodes.filter((n) => !hidden.has(n.type));
    const ids = new Set(visibleNodes.map((n) => n.id));
    return {
      nodes: visibleNodes.map((n) => ({ ...n })),
      links: graph.edges
        .filter((e) => ids.has(e.source) && ids.has(e.target))
        .map((e) => ({ ...e })),
    };
  }, [graph, hidden]);

  const empty = graph.nodes.length === 0;

  const toggleType = (t: string) =>
    setHidden((h) => {
      const next = new Set(h);
      next.has(t) ? next.delete(t) : next.add(t);
      return next;
    });

  return (
    <div className="flex h-full flex-col bg-surface">
      <div className="flex items-center justify-between border-b border-borderc px-5 py-3">
        <h2 className="text-sm font-semibold text-textc">Grafo de relacionamentos</h2>
        {!empty && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">{graph.nodes.length} nós</span>
            <button
              onClick={() => fgRef.current?.zoomToFit(400, 60)}
              className="rounded-md border border-borderc px-2 py-1 text-xs text-textc hover:bg-surfaceMuted"
            >
              Recentrar
            </button>
          </div>
        )}
      </div>

      <div ref={wrapRef} className="relative flex-1 overflow-hidden">
        {empty ? (
          <div className="flex h-full items-center justify-center px-8 text-center">
            <p className="max-w-xs text-sm text-muted">
              Conforme você pergunta, as conexões entre agenda, emails, documentos e dados
              aparecem aqui.
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
                nodeRelSize={5}
                maxZoom={4}
                linkColor={(l: any) => (l.type === "related_to" ? "#94a3b8" : "#cbd5e1")}
                linkLineDash={(l: any) => (l.type === "related_to" ? [4, 3] : null)}
                linkWidth={(l: any) => 1 + (l.weight || 0.5) * 2}
                linkDirectionalArrowLength={4}
                linkDirectionalArrowRelPos={1}
                cooldownTicks={80}
                onEngineStop={() => fgRef.current?.zoomToFit(400, 60)}
                onNodeClick={(n: any) => setSelected(graph.nodes.find((x) => x.id === n.id) ?? null)}
                onBackgroundClick={() => { setSelected(null); setHoverEdge(null); }}
                onLinkHover={(l: any) => {
                  if (l && (l.rationale || l.type)) {
                    setHoverEdge({ x: 0, y: 0, text: l.rationale ? `${l.type}: ${l.rationale}` : l.type });
                  } else {
                    setHoverEdge(null);
                  }
                }}
                nodeCanvasObject={(node: any, ctx, scale) => {
                  const isNew = node.first_seen_turn === graph.lastTurn && graph.lastTurn > 0;
                  const color = nodeColors[node.type] ?? "#64748b";
                  const r = 6 / scale;
                  if (isNew) {
                    ctx.beginPath();
                    ctx.arc(node.x, node.y, (10) / scale, 0, 2 * Math.PI);
                    ctx.fillStyle = color + "33";
                    ctx.fill();
                  }
                  ctx.beginPath();
                  ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
                  ctx.fillStyle = color;
                  ctx.fill();
                  const label = String(node.label ?? "");
                  ctx.font = `${11 / scale}px system-ui`;
                  ctx.fillStyle = "#1a1f24";
                  ctx.textBaseline = "middle";
                  ctx.fillText(label.length > 22 ? label.slice(0, 22) + "…" : label, node.x + r + 3 / scale, node.y);
                }}
                nodePointerAreaPaint={(node: any, color, ctx, scale) => {
                  ctx.fillStyle = color;
                  ctx.beginPath();
                  ctx.arc(node.x, node.y, 8 / scale, 0, 2 * Math.PI);
                  ctx.fill();
                }}
              />
              {hoverEdge && (
                <div className="pointer-events-none absolute left-1/2 top-2 -translate-x-1/2 rounded-md bg-textc/90 px-2 py-1 text-xs text-white">
                  {hoverEdge.text}
                </div>
              )}
              {selected && (
                <NodeDetail
                  node={selected}
                  graph={graph}
                  onAskAbout={(n) => { onAskAbout(n); setSelected(null); }}
                  onClose={() => setSelected(null)}
                />
              )}
            </>
          )
        )}
      </div>

      {!empty && (
        <div className="flex flex-wrap gap-2 border-t border-borderc px-5 py-2">
          {types.map((t) => (
            <button
              key={t}
              onClick={() => toggleType(t)}
              className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs ${
                hidden.has(t) ? "border-borderc text-muted opacity-50" : "border-borderc text-textc"
              }`}
              title={hidden.has(t) ? "Mostrar" : "Ocultar"}
            >
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: nodeColors[t] ?? "#64748b" }} />
              {nodeLabels[t] ?? t}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
