#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -d .venv || python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock.txt
.venv/bin/python -m pip install --no-deps -e .
npm --prefix apps/console ci --ignore-scripts
npm --prefix apps/console run build
.venv/bin/python -m pytest
printf '%s\n' 'Ready: .venv/bin/python scripts/serve.py'
