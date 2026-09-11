import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { nodeColors, nodeLabels } from "../../theme";
import type { GraphData } from "../../state/types";

// Grafo de relacionamentos. Fase 3: nós genie_answer/data_asset com arestas cites/follows_up.
// (Detalhe de nó, filtros e nós do Google entram na Fase 4.)
export function GraphPanel({ graph }: { graph: GraphData }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  // Reenquadra sempre que o grafo cresce (senão o force-simulation joga nós para fora da tela).
  useEffect(() => {
    if (graph.nodes.length && fgRef.current) {
      const t = setTimeout(() => fgRef.current?.zoomToFit(400, 50), 300);
      return () => clearTimeout(t);
    }
  }, [graph.nodes.length, size.w]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  // react-force-graph consome {nodes, links}. Clona para não mutar o estado do React.
  const data = useMemo(
    () => ({
      nodes: graph.nodes.map((n) => ({ ...n })),
      links: graph.edges.map((e) => ({ ...e, source: e.source, target: e.target })),
    }),
    [graph],
  );

  const empty = graph.nodes.length === 0;
  const types = useMemo(() => [...new Set(graph.nodes.map((n) => n.type))], [graph.nodes]);

  return (
    <div className="flex h-full flex-col bg-surface">
      <div className="flex items-center justify-between border-b border-borderc px-5 py-3">
        <h2 className="text-sm font-semibold text-textc">Grafo de relacionamentos</h2>
        {!empty && <span className="text-xs text-muted">{graph.nodes.length} nós</span>}
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
            <ForceGraph2D
              ref={fgRef}
              width={size.w}
              height={size.h}
              graphData={data}
              backgroundColor="#ffffff"
              nodeRelSize={5}
              linkColor={() => "#cbd5e1"}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={1}
              cooldownTicks={80}
              onEngineStop={() => fgRef.current?.zoomToFit(400, 50)}
              nodeCanvasObject={(node: any, ctx, scale) => {
                const color = nodeColors[node.type] ?? "#64748b";
                const r = 6;
                ctx.beginPath();
                ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
                ctx.fillStyle = color;
                ctx.fill();
                const label = String(node.label ?? "");
                const fontSize = Math.max(10 / scale, 3);
                ctx.font = `${fontSize}px system-ui`;
                ctx.fillStyle = "#1a1f24";
                ctx.textBaseline = "middle";
                ctx.fillText(label.length > 22 ? label.slice(0, 22) + "…" : label, node.x + r + 2, node.y);
              }}
              nodePointerAreaPaint={(node: any, color, ctx) => {
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI);
                ctx.fill();
              }}
            />
          )
        )}
      </div>

      {!empty && (
        <div className="flex flex-wrap gap-3 border-t border-borderc px-5 py-2">
          {types.map((t) => (
            <span key={t} className="flex items-center gap-1.5 text-xs text-muted">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: nodeColors[t] ?? "#64748b" }} />
              {nodeLabels[t] ?? t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
