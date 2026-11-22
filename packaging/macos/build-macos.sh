#!/usr/bin/env bash
# Build "Ferospark LDM.app" + a .dmg for Apple Silicon (arm64) Macs.
# Runs on a macOS arm64 machine (GitHub's macos-14 runner, or any M-series Mac
# with Python 3.12). Bundles Python + deps (PyInstaller), plus static ffmpeg,
# ffprobe and deno so nothing has to be installed with Homebrew.
#
#   packaging/macos/build-macos.sh
# Output: dist/Ferospark_LDM-<ver>-macOS-arm64.dmg
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VER="${VER:-3.1.0}"
APP_NAME="Ferospark LDM"
WORK="$SRC_DIR/build/macos"
rm -rf "$WORK" "$SRC_DIR/dist/$APP_NAME.app"
mkdir -p "$WORK" "$SRC_DIR/dist"
cd "$WORK"

[ "$(uname -m)" = "arm64" ] || { echo "ERROR: run this on an arm64 Mac"; exit 1; }

echo "==> Python venv + deps"
python3 -m venv venv
. venv/bin/activate
pip install -q --upgrade pip
pip install -q -r "$SRC_DIR/packaging/requirements.txt" pyinstaller

echo "==> App icon (.icns)"
mkdir -p ldm.iconset
SRC_PNG="$SRC_DIR/icons/linux-downloader-512.png"
for s in 16 32 128 256 512; do
  sips -z $s $s "$SRC_PNG" --out "ldm.iconset/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2)); [ $d -le 512 ] && sips -z $d $d "$SRC_PNG" --out "ldm.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
cp "$SRC_PNG" ldm.iconset/icon_256x256@2x.png
iconutil -c icns ldm.iconset -o ldm.icns

echo "==> PyInstaller"
pyinstaller --noconfirm --clean --windowed \
  --name "$APP_NAME" \
  --icon ldm.icns \
  --osx-bundle-identifier io.github.matewinslet.ferosparkldm \
  --target-architecture arm64 \
  --add-data "$SRC_DIR/assets:assets" \
  --add-data "$SRC_DIR/icons:icons" \
  --add-data "$SRC_DIR/fonts:fonts" \
  --collect-all curl_cffi \
  --collect-all yt_dlp \
  --hidden-import PyQt6.QtSvg \
  --distpath "$WORK/dist" --workpath "$WORK/pyi" --specpath "$WORK" \
  "$SRC_DIR/download_manager.py"

APP="$WORK/dist/$APP_NAME.app"
BIN="$APP/Contents/Resources/bin"
mkdir -p "$BIN"

echo "==> Static ffmpeg + ffprobe (arm64)"
for tool in ffmpeg ffprobe; do
  curl -fsSL "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/$tool.zip" -o "$tool.zip"
  unzip -oq "$tool.zip" -d "$tool-x"
  cp "$(find "$tool-x" -type f -name "$tool" | head -1)" "$BIN/$tool"
done

echo "==> deno (yt-dlp's JavaScript runtime for YouTube)"
curl -fsSL "https://github.com/denoland/deno/releases/latest/download/deno-aarch64-apple-darwin.zip" -o deno.zip
unzip -oq deno.zip -d deno-x
cp deno-x/deno "$BIN/deno"
chmod +x "$BIN"/*

# Info.plist touches: version + minimum macOS.
PL="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VER" "$PL" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VER" "$PL"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 11.0" "$PL" 2>/dev/null || true

echo "==> Ad-hoc signing (Apple Silicon refuses unsigned code)"
for f in "$BIN"/*; do codesign --force -s - "$f"; done
codesign --force --deep -s - "$APP"
codesign --verify --deep --strict "$APP"

echo "==> .dmg"
DMGROOT="$WORK/dmgroot"
rm -rf "$DMGROOT"; mkdir -p "$DMGROOT"
cp -R "$APP" "$DMGROOT/"
ln -s /Applications "$DMGROOT/Applications"
cat > "$DMGROOT/READ ME FIRST.txt" <<'TXT'
Ferospark LDM for Mac (Apple Silicon)

1. Drag "Ferospark LDM" into Applications.
2. The app is not notarized by Apple, so macOS will block it the first time.
   Open Terminal and run:

       xattr -cr "/Applications/Ferospark LDM.app"

   Then open it normally. (Or: System Settings > Privacy & Security >
   "Open Anyway" after the first blocked attempt.)
3. Install the Ferospark LDM extension in Firefox so the Download button
   appears on web pages. LDM must be running for it to work.

When you close the window, LDM keeps running in the menu bar (top right).
Click the Dock icon or the menu-bar icon to bring it back; quit from the
menu-bar icon.
TXT
OUT="$SRC_DIR/dist/Ferospark_LDM-${VER}-macOS-arm64.dmg"
rm -f "$OUT"
hdiutil create -volname "$APP_NAME" -srcfolder "$DMGROOT" -ov -format UDZO "$OUT" >/dev/null
cp -R "$APP" "$SRC_DIR/dist/"
echo "==> Done: $OUT ($(du -h "$OUT" | cut -f1))"
