#!/usr/bin/env bash
set -euo pipefail

python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

