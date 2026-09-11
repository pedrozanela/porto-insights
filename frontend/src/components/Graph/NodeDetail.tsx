import { nodeLabels } from "../../theme";
import type { GraphData, GraphNode } from "../../state/types";

interface Props {
  node: GraphNode;
  graph: GraphData;
  onAskAbout: (node: GraphNode) => void;
  onClose: () => void;
}

const SOURCE_LABEL: Record<string, string> = {
  gmail: "Gmail", calendar: "Google Agenda", drive: "Google Drive", genie: "Genie One",
};

export function NodeDetail({ node, graph, onAskAbout, onClose }: Props) {
  // Vizinhos: nós ligados por qualquer aresta.
  const neighborIds = new Set<string>();
  graph.edges.forEach((e) => {
    if (e.source === node.id) neighborIds.add(e.target);
    if (e.target === node.id) neighborIds.add(e.source);
  });
  const neighbors = graph.nodes.filter((n) => neighborIds.has(n.id));

  const props = node.props ?? {};
  const shown = Object.entries(props).filter(
    ([k, v]) => !k.startsWith("_") && v != null && v !== "" && typeof v !== "object",
  );

  return (
    <div className="absolute inset-x-3 bottom-3 z-10 max-h-[60%] overflow-y-auto rounded-xl border border-borderc bg-surface p-4 shadow-lg">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted">
            {nodeLabels[node.type] ?? node.type} · {SOURCE_LABEL[node.source] ?? node.source}
          </div>
          <div className="mt-0.5 font-semibold text-textc">{node.label}</div>
        </div>
        <button onClick={onClose} className="text-muted hover:text-textc" title="Fechar">✕</button>
      </div>

      {shown.length > 0 && (
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          {shown.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k}</dt>
              <dd className="truncate text-textc">{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}

      {neighbors.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-semibold text-muted">Conexões ({neighbors.length})</div>
          <ul className="mt-1 space-y-0.5 text-sm text-textc">
            {neighbors.slice(0, 8).map((n) => (
              <li key={n.id} className="truncate">· {n.label}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          onClick={() => onAskAbout(node)}
          className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primaryDark"
        >
          Perguntar sobre isso
        </button>
        {node.url && (
          <a
            href={node.url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-borderc px-3 py-1.5 text-sm text-textc hover:bg-surfaceMuted"
          >
            Abrir original →
          </a>
        )}
      </div>
    </div>
  );
}
