import { useMemo, useState } from "react";
import type { GenieCard } from "../../state/types";
import { classify, formatCell, hasCurrency, header, isNumericKind, type ColKind } from "./format";

// Card da resposta do Genie One: tabela, SQL colapsável, fontes citadas e "Explorar no Databricks".
export function GenieAnswerCard({ card }: { card: GenieCard }) {
  const [showSql, setShowSql] = useState(false);
  const [gross, setGross] = useState(false);

  // Classifica cada coluna uma vez (tipo do UC + nome + amostra dos valores).
  const kinds = useMemo<ColKind[]>(
    () => card.columns.map((c, j) =>
      classify(c, card.column_types?.[j], card.rows.slice(0, 12).map((r) => r[j]))),
    [card.columns, card.column_types, card.rows],
  );
  const currencyCols = hasCurrency(kinds);

  if (card.status !== "completed" && card.status !== "incomplete") {
    return (
      <div className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
        O Genie One não conseguiu concluir esta consulta.
      </div>
    );
  }

  const hasTable = card.columns.length > 0 && card.rows.length > 0;

  return (
    <div className="mb-3 overflow-hidden rounded-xl border border-borderc bg-surface">
      <div className="flex items-center gap-2 border-b border-borderc bg-surfaceMuted px-3 py-1.5">
        <span className="text-xs font-semibold text-primary">Genie One</span>
        <span className="text-xs text-muted">resposta fundamentada nos dados</span>
      </div>

      {hasTable && (
        <>
          {currencyCols && (
            <div className="flex justify-end border-b border-borderc bg-surface px-3 py-1">
              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted">
                <input type="checkbox" checked={gross} onChange={(e) => setGross(e.target.checked)}
                  className="h-3 w-3 accent-primary" />
                valores brutos
              </label>
            </div>
          )}
          <div className="max-h-72 overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surfaceMuted">
                <tr>
                  {card.columns.map((c, j) => (
                    <th key={c}
                      className={`border-b border-borderc px-3 py-1.5 font-semibold text-textc ${
                        isNumericKind(kinds[j]) ? "text-right" : "text-left"}`}>
                      {header(c)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {card.rows.map((row, i) => (
                  <tr key={i} className="odd:bg-surface even:bg-surfaceMuted/40">
                    {row.map((cell, j) => (
                      <td key={j}
                        className={`border-b border-borderc px-3 py-1.5 text-textc ${
                          isNumericKind(kinds[j]) ? "text-right tabular-nums" : "text-left"}`}>
                        {formatCell(cell, kinds[j], gross)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="space-y-2 px-3 py-2">
        {card.sql && (
          <div>
            <button onClick={() => setShowSql((v) => !v)} className="text-xs text-primary hover:underline">
              {showSql ? "ocultar SQL" : "ver como o Genie chegou nisso"}
            </button>
            {showSql && (
              <pre className="mt-1 overflow-x-auto rounded-lg bg-surfaceMuted p-2 text-xs text-textc">
                {card.sql}
              </pre>
            )}
          </div>
        )}

        {card.sources.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted">Fontes:</span>
            {card.sources.map((s) => (
              <a
                key={s.url}
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-full border border-borderc px-2 py-0.5 text-xs text-textc hover:border-primary hover:text-primary"
                title={s.label}
              >
                {s.label.split(".").pop()}
              </a>
            ))}
          </div>
        )}

        <div className="flex items-center gap-3 pt-1">
          {card.deep_link && (
            <a
              href={card.deep_link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium text-primary hover:underline"
            >
              Explorar no Databricks →
            </a>
          )}
          {card.truncated && card.deep_link && (
            <a href={card.deep_link} target="_blank" rel="noopener noreferrer" className="text-xs text-muted hover:underline">
              Carregar resultado completo
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
