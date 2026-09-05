#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
python3 -m pip install -r backend/requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python3 backend/init_db.py
