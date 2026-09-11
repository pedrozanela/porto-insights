// Marca do app. Usa o símbolo oficial da Porto (a vela) — porto-symbol.png,
// copiado do app ai-prism-porto (cropado do logo oficial 2022).

export function BrandLogo() {
  return (
    <div className="flex items-center gap-2.5">
      <img
        src="/porto-symbol.png"
        width={30}
        height={30}
        alt="Porto"
        className="select-none rounded-[22%]"
        draggable={false}
      />
      <span className="text-lg font-semibold tracking-tight text-textc">
        Porto <span className="text-primary">Insights</span>
      </span>
    </div>
  );
}
