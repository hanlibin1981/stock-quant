#!/bin/bash
set -euo pipefail

PROJECT_ROOT="/Users/mac/openclaw-projects/stock-quant"
DIST_DIR="$PROJECT_ROOT/dist"
BUILD_DIR="$DIST_DIR/stockquant-release"
VERSION="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="$DIST_DIR/stockquant-${VERSION}.tar.gz"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

cp -R "$PROJECT_ROOT/src" "$BUILD_DIR/"
cp -R "$PROJECT_ROOT/scripts" "$BUILD_DIR/"
cp -R "$PROJECT_ROOT/deploy" "$BUILD_DIR/"
cp -R "$PROJECT_ROOT/config" "$BUILD_DIR/"
cp "$PROJECT_ROOT/README.md" "$BUILD_DIR/"
cp "$PROJECT_ROOT/SPEC.md" "$BUILD_DIR/"
cp "$PROJECT_ROOT/requirements.txt" "$BUILD_DIR/"
cp "$PROJECT_ROOT/requirements-gui.txt" "$BUILD_DIR/"
cp "$PROJECT_ROOT/requirements-vnpy.txt" "$BUILD_DIR/"
cp "$PROJECT_ROOT/start_server.sh" "$BUILD_DIR/"

cat > "$BUILD_DIR/build-meta.json" <<EOF
{
  "version": "${VERSION}",
  "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "python": "$("$PROJECT_ROOT/venv/bin/python" -V 2>&1)"
}
EOF

tar -czf "$ARCHIVE" -C "$DIST_DIR" "$(basename "$BUILD_DIR")"

echo "Release package created:"
echo "  $ARCHIVE"
