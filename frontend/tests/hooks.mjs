// Hooks do Node para os testes do frontend: traduzem TS/TSX com o MESMO Sucrase que o navegador
// usa (frontend/vendor/sucrase.js), resolvem imports sem extensão e trocam "vitest" pelo shim local.
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const { transform } = await import(new URL("../vendor/sucrase.js", import.meta.url));
const VITEST_SHIM = new URL("./vitest.js", import.meta.url).href;
const SOURCE_EXTS = [".tsx", ".ts", ".jsx", ".js"];

export async function resolve(specifier, context, next) {
  if (specifier === "vitest") return { url: VITEST_SHIM, shortCircuit: true };
  if (/^\.\.?\//.test(specifier) && !/\.[cm]?[jt]sx?$/.test(specifier)) {
    for (const ext of SOURCE_EXTS) {
      const url = new URL(specifier + ext, context.parentURL);
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true };
    }
  }
  return next(specifier, context);
}

export async function load(url, context, next) {
  const ext = url.startsWith("file:") && url.match(/\.(tsx|ts|jsx)$/)?.[1];
  if (!ext) return next(url, context);
  const transforms = ext === "ts" ? ["typescript"] : ext === "tsx" ? ["typescript", "jsx"] : ["jsx"];
  const { code } = transform(readFileSync(fileURLToPath(url), "utf8"), {
    transforms, jsxRuntime: "automatic", production: true, filePath: fileURLToPath(url),
  });
  return { format: "module", source: code, shortCircuit: true };
}
