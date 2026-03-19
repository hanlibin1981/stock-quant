#!/bin/bash
set -euo pipefail

PORT="${1:-${STOCKQUANT_PORT:-5004}}"
URL="http://127.0.0.1:${PORT}/api/strategies"

echo "Healthcheck: $URL"
curl --fail --silent --show-error --max-time 10 "$URL"
echo
echo "Healthcheck passed"
