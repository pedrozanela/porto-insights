#!/usr/bin/env bash
# Gera frontend/vendor/: as bibliotecas do frontend como módulos ESM prontos para o navegador
# (o app NÃO tem build — o navegador traduz frontend/src/*.tsx na hora, ver index.html).
# Só precisa rodar ao adicionar/atualizar uma biblioteca; editar telas nunca exige isto.
# Requer node + acesso a um registry npm (usa node@22 do Homebrew; o node default quebra).
set -euo pipefail
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
cd "$(dirname "$0")/vendor"
OUT="../../frontend/vendor"
TAILWIND_VERSION="3.4.17"

npm ci --no-audit --no-fund
rm -rf "$OUT" && mkdir -p "$OUT"

# Um bundle com code splitting: cada entrada vira um arquivo do import map e os módulos comuns
# (o React, principalmente) ficam em chunks compartilhados — uma única instância de React.
./node_modules/.bin/esbuild entries/*.js \
  --bundle --splitting --format=esm --minify --target=es2020 \
  --define:process.env.NODE_ENV='"production"' \
  --legal-comments=eof --chunk-names='chunks/[name]-[hash]' \
  --outdir="$OUT"

# es-module-shims: carrega os módulos de /src passando cada um pelo Sucrase (ver index.html).
cp node_modules/es-module-shims/dist/es-module-shims.js "$OUT/es-module-shims.js"
# Babel: SÓ é baixado pelo navegador quando o Sucrase acusa erro de sintaxe — dá a linha exata.
cp node_modules/@babel/standalone/babel.min.js "$OUT/babel.min.js"

# Tailwind v3 que roda no navegador (gera o CSS das classes em tempo de execução).
curl -fsSL "https://cdn.tailwindcss.com/${TAILWIND_VERSION}" -o "$OUT/tailwind.js"

echo "vendor ok:"; ls -la "$OUT" "$OUT/chunks"
