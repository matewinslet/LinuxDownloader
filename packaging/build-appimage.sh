#!/usr/bin/env bash
# Build a portable AppImage. Uses a manylinux "python-appimage" base so the
# Python interpreter AND the app's deps are bundled — it runs on most x86_64
# desktops without installing anything. No FUSE required (extract-and-run).
#
#   packaging/build-appimage.sh
# Output: dist/Linux_Download_Manager-<ver>-x86_64.AppImage
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="${VER:-2.0.0}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

echo "==> Fetching a portable manylinux Python (python-appimage base)..."
BASE_URL="$(curl -fsSL 'https://api.github.com/repos/niess/python-appimage/releases?per_page=100' \
  | grep -o 'https://[^"]*cp312-cp312-manylinux2014_x86_64.AppImage' | head -1)"
[ -n "$BASE_URL" ] || { echo "ERROR: could not find a cp312 manylinux2014 python base"; exit 1; }
wget -q "$BASE_URL" -O python-base.AppImage
chmod +x python-base.AppImage
./python-base.AppImage --appimage-extract >/dev/null
mv squashfs-root AppDir

# Use the real interpreter ELF under opt/ (usr/bin/python3.12 is a wrapper symlink).
APPPY="$(find "$WORK/AppDir/opt" -type f -path '*/bin/python3.12' | head -1)"
[ -n "$APPPY" ] || { echo "ERROR: bundled python not found"; exit 1; }
echo "==> Bundled interpreter: ${APPPY#$WORK/}"

echo "==> Installing app dependencies into the bundle (can take a minute)..."
"$APPPY" -m pip install --no-warn-script-location -q --upgrade pip
"$APPPY" -m pip install --no-warn-script-location -q -r "$SRC_DIR/packaging/requirements.txt"

echo "==> Adding the app tree..."
APPROOT="AppDir/opt/linux-downloader"
mkdir -p "$APPROOT"
cp "$SRC_DIR/download_manager.py" "$APPROOT/"
cp -r "$SRC_DIR/assets" "$SRC_DIR/icons" "$SRC_DIR/fonts" "$APPROOT/"
cp "$SRC_DIR/LICENSE.txt" "$APPROOT/" 2>/dev/null || true

# Launch our app with the bundled interpreter, preserving the python-appimage
# environment (APPDIR / Tcl-Tk / SSL certs) that its real ELF expects.
cat > AppDir/AppRun <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
APPDIR="${APPDIR:-$HERE}"
export APPDIR
export TCL_LIBRARY="${APPDIR}/usr/share/tcltk/tcl8.6"
export TK_LIBRARY="${APPDIR}/usr/share/tcltk/tk8.6"
export TKPATH="${TK_LIBRARY}"
export SSL_CERT_FILE="${APPDIR}/opt/_internal/certs.pem"
export PATH="$HOME/.deno/bin:/usr/local/bin:$PATH"
exec "${APPDIR}/opt/python3.12/bin/python3.12" \
     "${APPDIR}/opt/linux-downloader/download_manager.py" "$@"
EOF
chmod +x AppDir/AppRun

# Replace the python base's own desktop/icon metadata with the app's.
rm -f AppDir/*.desktop AppDir/*.png AppDir/.DirIcon 2>/dev/null || true
cp "$SRC_DIR/packaging/linux-download-manager.desktop" AppDir/linux-download-manager.desktop
cp "$SRC_DIR/icons/linux-downloader-256.png" AppDir/linux-downloader.png
ln -sf linux-downloader.png AppDir/.DirIcon

echo "==> Fetching appimagetool..."
wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage -O appimagetool
chmod +x appimagetool

mkdir -p "$SRC_DIR/dist"
OUT="$SRC_DIR/dist/Linux_Download_Manager-${VER}-x86_64.AppImage"
ARCH=x86_64 ./appimagetool --appimage-extract-and-run AppDir "$OUT"
echo "==> Built: $OUT"
ls -lh "$OUT"
