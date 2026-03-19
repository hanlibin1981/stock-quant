#!/bin/bash
set -euo pipefail

PROJECT_ROOT="/Users/mac/openclaw-projects/stock-quant"
cd "$PROJECT_ROOT"

ENV_FILE="${STOCKQUANT_ENV_FILE:-$PROJECT_ROOT/config/production.env}"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

source venv/bin/activate

export STOCKQUANT_HOST="${STOCKQUANT_HOST:-0.0.0.0}"
export STOCKQUANT_PORT="${STOCKQUANT_PORT:-5004}"

mkdir -p "$PROJECT_ROOT/logs"

exec python -m src.ui.prod_server
