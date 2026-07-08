#!/bin/bash
# AiM CSV to MD - arm64 .app builder
# macOS 15+ の bincache 保護を回避するため PYINSTALLER_CONFIG_DIR をプロジェクト内に向ける
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE_DIR="$SCRIPT_DIR/.pyinstaller_cache"

mkdir -p "$CACHE_DIR"
cd "$SCRIPT_DIR"

# ── icon.png → icon.icns 変換 ──────────────────────────
if [ -f icon.png ] && { [ ! -f icon.icns ] || [ icon.png -nt icon.icns ]; }; then
    echo "🎨 Converting icon.png → icon.icns ..."
    mkdir -p icon.iconset
    for SIZE in 16 32 64 128 256 512; do
        sips -z $SIZE $SIZE icon.png --out icon.iconset/icon_${SIZE}x${SIZE}.png > /dev/null
        DOUBLE=$((SIZE * 2))
        sips -z $DOUBLE $DOUBLE icon.png --out icon.iconset/icon_${SIZE}x${SIZE}@2x.png > /dev/null
    done
    iconutil -c icns icon.iconset -o icon.icns
    rm -rf icon.iconset
    echo "   → icon.icns 生成完了"
fi

# ── ビルド ──────────────────────────────────────────────
echo "🔨 Building AiM CSV to MD.app (arm64)..."
rm -rf build dist

PYTHON_BIN="${PYTHON_BIN:-$SCRIPT_DIR/.venv/bin/python3}"
if [ -x "$SCRIPT_DIR/.venv/bin/pyinstaller" ]; then
    PYINSTALLER_CMD=("$SCRIPT_DIR/.venv/bin/pyinstaller")
elif command -v pyinstaller >/dev/null 2>&1; then
    PYINSTALLER_CMD=("pyinstaller")
else
    PYINSTALLER_CMD=("$PYTHON_BIN" -m PyInstaller)
fi

# Use the spec file directly - no additional options
PYINSTALLER_CONFIG_DIR="$CACHE_DIR" \
    "${PYINSTALLER_CMD[@]}" AiM\ CSV\ to\ MD.spec

echo ""
echo "✅ Done: dist/AiM CSV to MD.app"
du -sh "dist/AiM CSV to MD.app"
