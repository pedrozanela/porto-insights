// Ícones por tipo de nó, pré-renderizados uma vez em canvas offscreen (branco, transparente)
// e desenhados escalados no grafo — não redesenhamos o path a cada frame.
// Desenho vetorial simples (estilo lucide) por tipo.

const BASE = 48;
const cache = new Map<string, HTMLCanvasElement>();

function draw(type: string, ctx: CanvasRenderingContext2D): void {
  const c = BASE / 2;
  ctx.strokeStyle = "#ffffff";
  ctx.fillStyle = "#ffffff";
  ctx.lineWidth = 3.2;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  const box = 22; // meia-largura útil
  const L = c - box, R = c + box, T = c - box, B = c + box;

  switch (type) {
    case "calendar_event": {
      ctx.strokeRect(L, T + 4, box * 2, box * 2 - 4);
      ctx.beginPath(); ctx.moveTo(L, T + 12); ctx.lineTo(R, T + 12); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(L + 8, T); ctx.lineTo(L + 8, T + 8);
      ctx.moveTo(R - 8, T); ctx.lineTo(R - 8, T + 8); ctx.stroke();
      break;
    }
    case "email":
    case "email_thread": {
      ctx.strokeRect(L, T + 4, box * 2, box * 2 - 8);
      ctx.beginPath(); ctx.moveTo(L, T + 6); ctx.lineTo(c, c + 4); ctx.lineTo(R, T + 6); ctx.stroke();
      break;
    }
    case "drive_file": {
      ctx.beginPath();
      ctx.moveTo(L + 4, T); ctx.lineTo(R - 8, T); ctx.lineTo(R - 2, T + 8);
      ctx.lineTo(R - 2, B); ctx.lineTo(L + 4, B); ctx.closePath(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(L + 10, c); ctx.lineTo(R - 8, c);
      ctx.moveTo(L + 10, c + 8); ctx.lineTo(R - 8, c + 8); ctx.stroke();
      break;
    }
    case "person": {
      ctx.beginPath(); ctx.arc(c, T + 10, 7, 0, 2 * Math.PI); ctx.stroke();
      ctx.beginPath(); ctx.arc(c, B + 6, 15, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke();
      break;
    }
    case "data_asset": {
      ctx.beginPath(); ctx.ellipse(c, T + 8, box - 4, 6, 0, 0, 2 * Math.PI); ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(L + 4, T + 8); ctx.lineTo(L + 4, B - 8);
      ctx.ellipse(c, B - 8, box - 4, 6, 0, Math.PI, 0, true);
      ctx.moveTo(R - 4, B - 8); ctx.lineTo(R - 4, T + 8); ctx.stroke();
      break;
    }
    case "metric_view": {
      // eixos + 3 barras: distingue metric view (métricas) da tabela (cilindro).
      ctx.beginPath(); ctx.moveTo(L + 4, T + 2); ctx.lineTo(L + 4, B - 4); ctx.lineTo(R - 2, B - 4); ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(L + 12, B - 4); ctx.lineTo(L + 12, c + 4);
      ctx.moveTo(c, B - 4); ctx.lineTo(c, T + 8);
      ctx.moveTo(R - 8, B - 4); ctx.lineTo(R - 8, c - 2); ctx.stroke();
      break;
    }
    case "genie_answer": {
      ctx.beginPath();
      ctx.moveTo(c, T); ctx.lineTo(c + 5, c - 5); ctx.lineTo(R, c);
      ctx.lineTo(c + 5, c + 5); ctx.lineTo(c, B); ctx.lineTo(c - 5, c + 5);
      ctx.lineTo(L, c); ctx.lineTo(c - 5, c - 5); ctx.closePath(); ctx.fill();
      break;
    }
    default: {
      ctx.beginPath(); ctx.arc(c, c, 5, 0, 2 * Math.PI); ctx.fill();
    }
  }
}

// Chave de glyph efetiva: um data_asset marcado como metric view usa o ícone de barras.
export function glyphType(node: { type: string; props?: Record<string, unknown> }): string {
  if (node.type === "data_asset" && node.props?.asset_type === "metric_view") return "metric_view";
  return node.type;
}

export function glyph(type: string): HTMLCanvasElement | null {
  if (cache.has(type)) return cache.get(type)!;
  const el = document.createElement("canvas");
  el.width = BASE;
  el.height = BASE;
  const ctx = el.getContext("2d");
  if (!ctx) return null;
  draw(type, ctx);
  cache.set(type, el);
  return el;
}
