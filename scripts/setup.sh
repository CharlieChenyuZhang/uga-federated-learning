#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v node >/dev/null || { echo 'Install Node.js 20.9 or newer, then retry.'; exit 1; }
node -e 'const [a,b]=process.versions.node.split(".").map(Number);if(a<20||(a===20&&b<9)){console.error("Node.js 20.9 or newer is required.");process.exit(1)}'
npm ci
if [[ ! -x .venv/bin/python ]]; then
  if command -v uv >/dev/null; then
    uv venv --python 3.12 .venv
  else
    python3 -c 'import sys; assert sys.version_info >= (3, 10), "Install Python 3.10+ or uv"'
    python3 -m venv .venv
  fi
fi
if command -v uv >/dev/null; then
  uv pip install --python .venv/bin/python -r backend/requirements-ml.txt
else
  .venv/bin/python -m pip install -r backend/requirements-ml.txt
fi
echo 'Ready. Run ./scripts/dev.sh and open http://127.0.0.1:3000'
echo 'The first training or chat request downloads TinyLlama (~2.2 GB).'
