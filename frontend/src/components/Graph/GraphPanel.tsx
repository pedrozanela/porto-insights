// Painel do grafo — Fase 1: só o estado vazio. Renderização com react-force-graph-2d e os
// deltas por SSE entram na Fase 3/4.

export function GraphPanel() {
  return (
    <div className="flex h-full flex-col bg-surface">
      <div className="border-b border-borderc px-5 py-3">
        <h2 className="text-sm font-semibold text-textc">Grafo de relacionamentos</h2>
      </div>
      <div className="flex flex-1 items-center justify-center px-8 text-center">
        <p className="max-w-xs text-sm text-muted">
          Conforme você pergunta, as conexões entre agenda, emails, documentos e dados
          aparecem aqui.
        </p>
      </div>
    </div>
  );
}
