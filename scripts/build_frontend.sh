#!/usr/bin/env bash
# Builda o frontend (dist/) antes do deploy. Usa node@22 (o node default do Homebrew quebra).
set -euo pipefail
NODE_BIN="/opt/homebrew/opt/node@22/bin"
cd "$(dirname "$0")/../frontend"
export PATH="$NODE_BIN:$PATH"
npm install
npm run build
echo "build ok: frontend/dist"
