// Slot de marca. TODO: substituir pelo SVG oficial da Porto quando o Pedro fornecer.
// Não baixar nem desenhar o logo da Porto — por ora, wordmark em texto.

export function BrandLogo() {
  return (
    <div className="flex items-center gap-2">
      <div className="h-7 w-7 rounded-lg bg-primary" aria-hidden />
      <span className="text-lg font-semibold tracking-tight text-textc">
        Porto <span className="text-primary">Insights</span>
      </span>
    </div>
  );
}
