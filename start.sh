#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
exec python3 -m uvicorn backend.app:app --host 0.0.0.0 --port "${APP_PORT:-3000}"
