#!/bin/zsh
set -euo pipefail

ROOT_DIR="/Volumes/my application/code/fastapi"
PORT="${PORT:-8011}"
BASE_URL="http://127.0.0.1:${PORT}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/artifacts/playwright}"
PW_DIR="/tmp/playwright-check"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"
./.conda/bin/python3.11 -m uvicorn main:app --host 127.0.0.1 --port "$PORT" >/tmp/fastapi_playwright_server.log 2>&1 &
SERVER_PID=$!

for _ in {1..60}; do
  if python3 - <<PY
import socket
s = socket.socket()
try:
    s.connect(("127.0.0.1", $PORT))
    print("ok")
finally:
    s.close()
PY
  then
    break
  fi
  sleep 0.5
done

mkdir -p "$PW_DIR"
/Users/xiaoyuanshen/.nvm/versions/node/v20.20.1/bin/npm install --prefix "$PW_DIR" playwright >/tmp/playwright_install.log 2>&1
NODE_PATH="$PW_DIR/node_modules" BASE_URL="$BASE_URL" OUT_DIR="$OUT_DIR" /Users/xiaoyuanshen/.nvm/versions/node/v20.20.1/bin/node "$ROOT_DIR/playwright_check_runner.js"
