#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -x .venv/bin/python && -d node_modules ]] || { echo 'Run ./scripts/setup.sh first.'; exit 1; }
# Fail explicitly instead of silently attaching to another service or selecting a new port.
.venv/bin/python - <<'PY'
import socket
for port in (3000, 8000):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('127.0.0.1', port))
        except OSError:
            raise SystemExit(f'Port {port} is in use. Stop the previous lab process before restarting.')
PY
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 &
api_pid=$!
node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3000 &
web_pid=$!
cleanup() { kill "$api_pid" "$web_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
while kill -0 "$api_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do sleep 1; done
