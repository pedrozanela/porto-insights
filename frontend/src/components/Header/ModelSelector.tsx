import type { ModelInfo } from "../../api/client";

interface Props {
  models: ModelInfo[];
  value: string;
  onChange: (name: string) => void;
}

// Dropdown de seleção de modelo. A troca vale a partir do próximo turno (Fase 2).
export function ModelSelector({ models, value, onChange }: Props) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted">Modelo</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={models.length === 0}
        className="rounded-lg border border-borderc bg-surface px-3 py-1.5 text-textc shadow-soft focus:border-primary focus:outline-none"
      >
        {models.length === 0 && <option>carregando…</option>}
        {models.map((m) => (
          <option key={m.name} value={m.name}>
            {m.label}
          </option>
        ))}
      </select>
    </label>
  );
}
