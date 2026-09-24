// Formatação pt-BR das colunas da tabela do Genie (Bloco B5). Classifica cada coluna por
// tipo do UC (quando vem) + nome + amostra de valores, e formata células em português:
// moeda (R$, abreviada em mi/bi com toggle de valores brutos), percentual, competência
// (ex.: "set/2026"), inteiros com separador de milhar. Numéricas são alinhadas à direita.

export type ColKind = "currency" | "currency_mi" | "percent" | "date" | "int" | "num" | "text";

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Rótulos pt-BR para nomes de coluna genéricos e comuns; fallback = Title Case.
// Sem termos de domínio específico — os dados do banco variam de assunto.
const HEADER_MAP: Record<string, string> = {
  competencia: "Competência",
  periodo: "Período",
  mes: "Mês",
  data: "Data",
  nome: "Nome",
  categoria: "Categoria",
  segmento: "Segmento",
  produto: "Produto",
  produto_id: "Produto",
  regiao: "Região",
  uf: "UF",
  valor: "Valor",
  total: "Total",
  quantidade: "Quantidade",
};

export function toNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(String(v).trim());
  return Number.isFinite(n) ? n : null;
}

function looksLikeDate(v: unknown): boolean {
  return typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v.trim());
}

export function classify(name: string, type: string | undefined, sample: unknown[]): ColKind {
  const nm = (name || "").toLowerCase();
  const t = (type || "").toUpperCase();
  const isDate = /DATE|TIMESTAMP/.test(t) || sample.some(looksLikeDate);
  if (isDate || /competenc|^data$|_data$|per[íi]odo|(^|_)mes(_|$)/.test(nm)) return "date";

  const nums = sample.map(toNumber).filter((x) => x !== null) as number[];
  const isNum = /INT|LONG|DECIMAL|DOUBLE|FLOAT|NUMERIC|BIGINT|SHORT|BYTE/.test(t)
    || (nums.length > 0 && nums.length >= sample.filter((s) => s !== null && s !== "").length);
  if (!isNum) return "text";

  if (/_id$/.test(nm)) return "text";                                   // ids não são grandezas
  // Genérico e agnóstico de domínio. Percentual e moeda só quando o nome sinaliza claramente;
  // caso contrário, número simples (evita rotular errado grandezas de outros assuntos).
  if (/percent|_pct$|(^|_)pct(_|$)|taxa|[íi]ndice|propor[çc]|%/.test(nm)) return "percent";
  if (/_mi$|_mm$|milh[oõ]/.test(nm)) return "currency_mi";
  if (/valor|saldo|receita|custo|despesa|fatur|montante|pre[çc]o|pr[êe]mio|sinistro|desembolso|arrecad|ticket|gasto|r\$/.test(nm)) return "currency";
  if (/qtd|quantidade|contagem|n[uú]mero/.test(nm)) return "int";
  return "num";
}

export function header(name: string): string {
  if (HEADER_MAP[name]) return HEADER_MAP[name];
  return (name || "")
    .split(/[_\s]+/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

function fmtCurrencyRaw(v: number, gross: boolean): string {
  if (gross) return "R$ " + nf2.format(v);
  const a = Math.abs(v);
  if (a >= 1e9) return "R$ " + nf2.format(v / 1e9) + " bi";
  if (a >= 1e6) return "R$ " + nf2.format(v / 1e6) + " mi";
  if (a >= 1e3) return "R$ " + nf1.format(v / 1e3) + " mil";
  return "R$ " + nf2.format(v);
}

// Formata uma célula. `gross` só afeta moeda (toggle "valores brutos").
export function formatCell(value: unknown, kind: ColKind, gross: boolean): string {
  if (value === null || value === undefined || value === "") return "—";
  if (kind === "date") {
    const s = String(value).trim();
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    if (m) return `${MESES[Number(m[2]) - 1]}/${m[1]}`;
    return s;
  }
  const n = toNumber(value);
  if (n === null) return String(value);
  switch (kind) {
    case "percent": return nf1.format(n) + "%";
    case "currency": return fmtCurrencyRaw(n, gross);
    case "currency_mi": return gross ? "R$ " + nf2.format(n * 1e6) : "R$ " + nf2.format(n) + " mi";
    case "int": return nf0.format(n);
    case "num": return Number.isInteger(n) ? nf0.format(n) : nf2.format(n);
    default: return String(value);
  }
}

export const isNumericKind = (k: ColKind): boolean => k !== "text" && k !== "date";
export const hasCurrency = (kinds: ColKind[]): boolean =>
  kinds.some((k) => k === "currency" || k === "currency_mi");
