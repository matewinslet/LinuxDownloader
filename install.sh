#!/bin/bash

# ─────────────────────────────────────────────
#  Linux Download Manager — Installer
#  Copyright (c) 2026 Tanjim (tpodbcs@gmail.com)
# ─────────────────────────────────────────────

set -e

INSTALL_DIR="$HOME/linux-downloader"
DESKTOP_FILE="$HOME/.local/share/applications/downloader.desktop"
ICON_NAME="linux-downloader"

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║     Linux Download Manager — Installer     ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# ── Step 1: System packages ──────────────────────────────────────────────────
echo "► [1/6] Detecting package manager..."

PKG_MANAGER=""
if command -v apt-get &>/dev/null; then
    PKG_MANAGER="apt"
    echo "  Detected: apt (Debian/Ubuntu/Mint)"
elif command -v dnf &>/dev/null; then
    PKG_MANAGER="dnf"
    echo "  Detected: dnf (Fedora/RHEL)"
elif command -v pacman &>/dev/null; then
    PKG_MANAGER="pacman"
    echo "  Detected: pacman (Arch/Manjaro)"
elif command -v zypper &>/dev/null; then
    PKG_MANAGER="zypper"
    echo "  Detected: zypper (openSUSE)"
else
    echo "  ERROR: Unsupported package manager. Install dependencies manually."
    exit 1
fi

echo "► [2/6] Installing system packages..."
case $PKG_MANAGER in
    apt)
        sudo apt-get update -y -qq
        sudo apt-get install -y \
            ffmpeg curl \
            python3 python3-pip python3-pyqt6.qtsvg \
            libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
            libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
            libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0 \
            > /dev/null 2>&1
        ;;
    dnf)
        sudo dnf install -y \
            ffmpeg curl \
            python3 python3-pip \
            xcb-util-cursor xcb-util-icccm xcb-util-image \
            xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
            libxkbcommon-x11 \
            > /dev/null 2>&1
        ;;
    pacman)
        sudo pacman -S --noconfirm \
            ffmpeg curl \
            python python-pip \
            xcb-util-cursor xcb-util-icccm xcb-util-image \
            xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
            libxkbcommon-x11 \
            > /dev/null 2>&1
        ;;
    zypper)
        sudo zypper install -y \
            ffmpeg curl \
            python3 python3-pip \
            libxcb-cursor0 libxkbcommon-x11-0 \
            > /dev/null 2>&1
        ;;
esac
echo "  Done."

# ── Step 2: Python packages ──────────────────────────────────────────────────
echo "► [3/6] Installing Python packages (PyQt6, requests, yt-dlp, curl_cffi)..."
# curl_cffi is pinned <0.15: yt-dlp 2026.3.17 only supports 0.10.x–0.14.x and
# refuses to load 0.15+, which silently disables browser impersonation and
# breaks hosts that fingerprint the TLS/JA3 handshake (HTTP 410 Gone).
pip3 install PyQt6 requests yt-dlp browser-cookie3 "curl_cffi>=0.10,<0.15" pycryptodome --break-system-packages -q 2>/dev/null || \
pip3 install PyQt6 requests yt-dlp browser-cookie3 "curl_cffi>=0.10,<0.15" pycryptodome -q
echo "  Done."

# ── Step 3: Deno (JavaScript runtime for YouTube) ────────────────────────────
echo "► [4/6] Installing Deno (JavaScript runtime)..."
if command -v deno &>/dev/null; then
    echo "  Deno already installed: $(deno --version | head -1)"
else
    curl -fsSL https://deno.land/install.sh | sh -s -- --quiet
    export DENO_INSTALL="$HOME/.deno"
    export PATH="$DENO_INSTALL/bin:$PATH"
    # Add to shell profile permanently
    SHELL_RC="$HOME/.bashrc"
    [[ "$SHELL" == *"zsh"* ]] && SHELL_RC="$HOME/.zshrc"
    if ! grep -q "DENO_INSTALL" "$SHELL_RC"; then
        echo '' >> "$SHELL_RC"
        echo '# Deno' >> "$SHELL_RC"
        echo 'export DENO_INSTALL="$HOME/.deno"' >> "$SHELL_RC"
        echo 'export PATH="$DENO_INSTALL/bin:$PATH"' >> "$SHELL_RC"
    fi
    sudo ln -sf "$HOME/.deno/bin/deno" /usr/local/bin/deno 2>/dev/null || true
    echo "  Done."
fi

# ── Step 4: App icons ────────────────────────────────────────────────────────
echo "► [5/6] Installing icons..."

SVG_SRC=""
for c in "$INSTALL_DIR/icons/linux-downloader.svg" "$INSTALL_DIR/linux-downloader.svg"; do
    [ -f "$c" ] && SVG_SRC="$c" && break
done

# Pick a rasterizer (quality: rsvg-convert ≥ inkscape ≥ qt ≫ convert)
# qt is preferred over convert because ImageMagick fails on SVG gradients/filters
RASTERIZER=""
if command -v rsvg-convert &>/dev/null; then
    RASTERIZER="rsvg-convert"
elif command -v inkscape &>/dev/null; then
    RASTERIZER="inkscape"
elif python3 -c "from PyQt6.QtSvg import QSvgRenderer" &>/dev/null; then
    RASTERIZER="qt"
elif command -v convert &>/dev/null; then
    RASTERIZER="convert"
fi

mkdir -p "$INSTALL_DIR/icons"

if [ -n "$SVG_SRC" ] && [ -n "$RASTERIZER" ]; then
    echo "  Rasterizing SVG with $RASTERIZER..."
    if [ "$RASTERIZER" = "qt" ]; then
        SVG_SRC="$SVG_SRC" ICON_DIR="$INSTALL_DIR/icons" ICON_NAME="$ICON_NAME" python3 - << 'PYEOF'
import os, sys
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
with open(os.environ['SVG_SRC'], 'rb') as f:
    renderer = QSvgRenderer(QByteArray(f.read()))
for size in [16, 32, 48, 64, 128, 256]:
    over = size * 4
    big = QPixmap(over, over); big.fill(QColor(0,0,0,0))
    p = QPainter(big)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(p); p.end()
    out = big.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    out.save(os.path.join(os.environ['ICON_DIR'], f"{os.environ['ICON_NAME']}-{size}.png"), 'PNG')
PYEOF
    else
        for size in 16 32 48 64 128 256; do
            OUT="$INSTALL_DIR/icons/${ICON_NAME}-${size}.png"
            case "$RASTERIZER" in
                rsvg-convert)
                    rsvg-convert -w "$size" -h "$size" "$SVG_SRC" -o "$OUT" 2>/dev/null
                    ;;
                inkscape)
                    inkscape -w "$size" -h "$size" "$SVG_SRC" -o "$OUT" >/dev/null 2>&1
                    ;;
                convert)
                    convert -background none -density 384 -resize "${size}x${size}" "$SVG_SRC" "$OUT" 2>/dev/null
                    ;;
            esac
        done
    fi
    echo "  Icons rasterized from SVG."
else
    # Fallback: generate crude geometric PNGs (no rasterizer or no SVG)
    python3 << 'PYEOF'
import struct, zlib, os, math

def create_png(size):
    pixels = []
    cx, cy, r = size/2, size/2, size/2
    for y in range(size):
        row = []
        for x in range(size):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx*dx + dy*dy)
            alpha = max(0, min(255, int((r - dist) * 2 * 255)))
            if dist > r:
                row += [0,0,0,0]
                continue
            bg_r, bg_g, bg_b = 26, 86, 219
            nx, ny = x/size, y/size
            in_shaft = (0.43 <= nx <= 0.57) and (0.18 <= ny <= 0.54)
            def sign(p1,p2,p3):
                return (p1[0]-p3[0])*(p2[1]-p3[1])-(p2[0]-p3[0])*(p1[1]-p3[1])
            def in_tri(px,py,ax,ay,bx,by,ccx,ccy):
                d1=sign((px,py),(ax,ay),(bx,by))
                d2=sign((px,py),(bx,by),(ccx,ccy))
                d3=sign((px,py),(ccx,ccy),(ax,ay))
                has_neg=(d1<0)or(d2<0)or(d3<0)
                has_pos=(d1>0)or(d2>0)or(d3>0)
                return not(has_neg and has_pos)
            in_arrow = in_tri(nx,ny,0.22,0.50,0.78,0.50,0.50,0.76)
            in_tray = (0.18 <= nx <= 0.82) and (0.80 <= ny <= 0.88)
            if in_shaft or in_arrow or in_tray:
                row += [255,255,255,alpha]
            else:
                row += [bg_r,bg_g,bg_b,alpha]
        pixels.append(row)
    def chunk(name,data):
        c=zlib.crc32(name+data)&0xffffffff
        return struct.pack('>I',len(data))+name+data+struct.pack('>I',c)
    raw=b''.join(b'\x00'+bytes(r) for r in pixels)
    png=b'\x89PNG\r\n\x1a\n'
    png+=chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))
    png+=chunk(b'IDAT',zlib.compress(raw,9))
    png+=chunk(b'IEND',b'')
    return png

install_dir = os.path.expanduser("~/linux-downloader")
icons_dir = os.path.join(install_dir, "icons")
os.makedirs(icons_dir, exist_ok=True)
for s in [16,32,48,64,128,256]:
    path = os.path.join(icons_dir, f"linux-downloader-{s}.png")
    with open(path, 'wb') as f:
        f.write(create_png(s))
print("  Icons generated (fallback — install rsvg-convert for better quality).")
PYEOF
fi

for size in 16 32 48 64 128 256; do
    DEST="/usr/share/icons/hicolor/${size}x${size}/apps"
    sudo mkdir -p "$DEST"
    sudo cp "$INSTALL_DIR/icons/${ICON_NAME}-${size}.png" "$DEST/${ICON_NAME}.png" 2>/dev/null || true
done

# Install scalable SVG so DEs that prefer scalable can use it
if [ -n "$SVG_SRC" ]; then
    SCALABLE_DEST="/usr/share/icons/hicolor/scalable/apps"
    sudo mkdir -p "$SCALABLE_DEST"
    sudo cp "$SVG_SRC" "$SCALABLE_DEST/${ICON_NAME}.svg" 2>/dev/null || true
fi

sudo gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
echo "  Done."

# ── Step 5: Firefox profile detection ───────────────────────────────────────
echo "► [6/6] Detecting Firefox profile..."

FF_PROFILE=""
FF_CANDIDATES=(
    "$HOME/.mozilla/firefox"
    "$HOME/.var/app/org.mozilla.firefox/config/mozilla/firefox"
    "$HOME/.var/app/org.mozilla.firefox/.mozilla/firefox"
    "$HOME/snap/firefox/common/.mozilla/firefox"
    "$HOME/.config/mozilla/firefox"
)
for path in "${FF_CANDIDATES[@]}"; do
    if [ -d "$path" ]; then
        FF_PROFILE="$path"
        break
    fi
done

if [ -n "$FF_PROFILE" ]; then
    echo "  Firefox profile found: $FF_PROFILE"
else
    echo "  WARNING: Firefox profile not found — cookie-based downloads may not work."
fi

# ── Desktop entry ────────────────────────────────────────────────────────────
mkdir -p "$HOME/.local/share/applications"

cat > "$DESKTOP_FILE" << DESKTOP
[Desktop Entry]
Type=Application
Name=Linux Download Manager
Comment=Custom Python Download Manager
Exec=env PATH=$HOME/.deno/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin python3 $INSTALL_DIR/download_manager.py
Icon=linux-downloader
Terminal=false
Categories=Network;
StartupWMClass=download_manager.py
DESKTOP

update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null || true
sudo cp "$DESKTOP_FILE" /usr/share/applications/ 2>/dev/null || true
sudo update-desktop-database /usr/share/applications/ 2>/dev/null || true

chmod +x "$INSTALL_DIR/download_manager.py"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║         Installation Complete!             ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "  Launch from your app menu: Linux Download Manager"
echo "  Or run: python3 $INSTALL_DIR/download_manager.py"
echo ""
if [ -z "$FF_PROFILE" ]; then
    echo "  ⚠  Install Firefox to enable cookie-based YouTube downloads."
    echo ""
fi
echo "  Note: Log out and back in if the app icon"
echo "        does not appear in the start menu."
echo ""
