#!/bin/bash
set -euo pipefail

PROJECT_ROOT="/Users/mac/openclaw-projects/stock-quant"
PLIST_TEMPLATE="$PROJECT_ROOT/deploy/com.stockquant.web.plist.template"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_TARGET="$LAUNCH_AGENTS_DIR/com.stockquant.web.plist"
SERVICE_LABEL="${SERVICE_LABEL:-com.stockquant.web}"
STOCKQUANT_HOST="${STOCKQUANT_HOST:-0.0.0.0}"
STOCKQUANT_PORT="${STOCKQUANT_PORT:-5004}"

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$PROJECT_ROOT/logs"
mkdir -p "$PROJECT_ROOT/config"

if [[ ! -f "$PROJECT_ROOT/config/production.env" ]]; then
  cp "$PROJECT_ROOT/config/production.env.example" "$PROJECT_ROOT/config/production.env"
fi

sed \
  -e "s|__SERVICE_LABEL__|$SERVICE_LABEL|g" \
  -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  -e "s|__HOST__|$STOCKQUANT_HOST|g" \
  -e "s|__PORT__|$STOCKQUANT_PORT|g" \
  "$PLIST_TEMPLATE" > "$PLIST_TARGET"

launchctl unload "$PLIST_TARGET" >/dev/null 2>&1 || true
launchctl load "$PLIST_TARGET"

echo "launchd service installed: $PLIST_TARGET"
echo "config file:"
echo "  $PROJECT_ROOT/config/production.env"
echo "log files:"
echo "  $PROJECT_ROOT/logs/stockquant.stdout.log"
echo "  $PROJECT_ROOT/logs/stockquant.stderr.log"
