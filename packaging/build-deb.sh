#!/usr/bin/env bash
# Build a .deb for Debian/Ubuntu/Mint/Zorin. Run on a Debian-family system.
#   packaging/build-deb.sh
# Output: dist/linux-download-manager_<ver>_<arch>.deb
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG=linux-download-manager
VER="${VER:-2.0.0}"
ARCH="$(dpkg --print-architecture)"
# Interpreter package the bundled venv is tied to (e.g. python3.12).
PYVER="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
PKGPY="python${PYVER}"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# 1. App + venv bundle into /opt/linux-downloader.
SRC_DIR="$SRC_DIR" bash "$SRC_DIR/packaging/build-bundle.sh" "$STAGE"

# 2. Launcher, desktop entry, icons.
install -Dm755 "$SRC_DIR/packaging/linux-downloader" "$STAGE/usr/bin/linux-downloader"
install -Dm644 "$SRC_DIR/packaging/linux-download-manager.desktop" \
  "$STAGE/usr/share/applications/linux-download-manager.desktop"
for sz in 16 32 48 64 128 256 512; do
  src="$SRC_DIR/icons/linux-downloader-${sz}.png"
  [ -f "$src" ] && install -Dm644 "$src" \
    "$STAGE/usr/share/icons/hicolor/${sz}x${sz}/apps/linux-downloader.png"
done
install -Dm644 "$SRC_DIR/icons/linux-downloader.svg" \
  "$STAGE/usr/share/icons/hicolor/scalable/apps/linux-downloader.svg"

# 3. Control metadata. The venv ties us to the build host's python3 minor, so
#    depend on that exact interpreter package as well as the python3 metapackage.
INSTALLED_KB="$(du -sk "$STAGE" | cut -f1)"
mkdir -p "$STAGE/DEBIAN"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VER
Section: net
Priority: optional
Architecture: $ARCH
Depends: python3, $PKGPY, ffmpeg, libxcb-cursor0, libxcb-xinerama0, libxkbcommon-x11-0, libegl1, libgl1, fontconfig
Recommends: curl
Installed-Size: $INSTALLED_KB
Maintainer: Tanjim <tpodbcs@gmail.com>
Homepage: https://github.com/matewinslet/LinuxDownloader
Description: Linux Download Manager (LDM)
 Download files and videos with browser integration, yt-dlp powered
 streaming, and a Qt6 interface. Self-contained: bundles its Python
 dependencies in /opt/linux-downloader.
EOF

# 4. Refresh icon/desktop caches on install and removal.
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
EOF
chmod 755 "$STAGE/DEBIAN/postinst"
cp "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

# 5. Build.
mkdir -p "$SRC_DIR/dist"
OUT="$SRC_DIR/dist/${PKG}_${VER}_${ARCH}.deb"
dpkg-deb --root-owner-group --build "$STAGE" "$OUT"

echo "==> Built: $OUT"
dpkg-deb --info "$OUT"
