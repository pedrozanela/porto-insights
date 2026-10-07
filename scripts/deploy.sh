#!/usr/bin/env bash
# Deploy do bundle no FEVM (target dev). Idempotente. O frontend não tem build.
set -euo pipefail
PROFILE="${DATABRICKS_CONFIG_PROFILE:-fevm-pzanela-classic-aws}"
cd "$(dirname "$0")/.."

echo "==> databricks bundle deploy -t dev"
databricks bundle deploy -t dev -p "$PROFILE"

echo "==> iniciando o app (bundle run)"
databricks bundle run porto_insights -t dev -p "$PROFILE"

echo "==> pronto. URL do app:"
databricks apps get porto-insights -p "$PROFILE" --output json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('url','(veja no workspace)'))" || true
