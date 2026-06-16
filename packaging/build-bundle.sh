#!/usr/bin/env bash
# Build the self-contained app bundle (app tree + Python venv) into a prefix.
#
#   build-bundle.sh <dest-prefix>
#
# Installs the app to <dest-prefix>/opt/linux-downloader. Run this on the
# TARGET distro family (Debian for .deb, Fedora for .rpm, Arch for the AUR
# package) so the venv's compiled wheels match that platform's Python.
set -euo pipefail

SRC_DIR="${SRC_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DEST="${1:?usage: build-bundle.sh <dest-prefix>}"
APPDIR="$DEST/opt/linux-downloader"

echo "==> Source:  $SRC_DIR"
echo "==> Bundle:  $APPDIR"
mkdir -p "$APPDIR"

# 1. App tree — everything the app loads relative to download_manager.py.
cp "$SRC_DIR/download_manager.py" "$APPDIR/"
cp -r "$SRC_DIR/assets" "$SRC_DIR/icons" "$SRC_DIR/fonts" "$APPDIR/"
cp "$SRC_DIR/LICENSE.txt" "$APPDIR/" 2>/dev/null || true

# 2. Python venv with the pinned runtime deps (wheel-only, no compiler needed).
echo "==> Creating venv and installing dependencies (this can take a minute)..."
python3 -m venv "$APPDIR/venv"
"$APPDIR/venv/bin/pip" install --quiet --upgrade pip
"$APPDIR/venv/bin/pip" install --quiet -r "$SRC_DIR/packaging/requirements.txt"

# 3. Trim bloat so the package is as small as a bundled Qt app can be.
find "$APPDIR/venv" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
"$APPDIR/venv/bin/pip" cache purge 2>/dev/null || true

# 4. Rewrite the staging/buildroot prefix out of the venv's text files
#    (shebangs, activate scripts, pyvenv.cfg) so they reference the final
#    install path. Required for rpm's check-buildroot QA, and correct for the
#    .deb too (the launcher calls venv/bin/python directly, but the console
#    scripts and pyvenv.cfg should still point at /opt/linux-downloader).
RUNTIME_DIR="/opt/linux-downloader"
if [ "$APPDIR" != "$RUNTIME_DIR" ]; then
  grep -rIlZ -- "$APPDIR" "$APPDIR/venv" 2>/dev/null \
    | xargs -0 -r sed -i "s|$APPDIR|$RUNTIME_DIR|g"
fi

echo "==> Bundle ready: $(du -sh "$APPDIR" | cut -f1)"
