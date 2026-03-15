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
echo "► [1/5] Installing system packages (ffmpeg, curl)..."
sudo apt-get update -y -qq
sudo apt-get install -y ffmpeg curl python3 python3-pip > /dev/null 2>&1
echo "  Done."

# ── Step 2: Python packages ──────────────────────────────────────────────────
echo "► [2/5] Installing Python packages (PyQt6, requests, yt-dlp)..."
pip install PyQt6 requests yt-dlp --break-system-packages -q
echo "  Done."

# ── Step 3: Deno (JavaScript runtime for YouTube) ────────────────────────────
echo "► [3/5] Installing Deno (JavaScript runtime)..."
if command -v deno &> /dev/null; then
    echo "  Deno already installed: $(deno --version | head -1)"
else
    curl -fsSL https://deno.land/install.sh | sh -s -- --quiet
    # Add to PATH for this session
    export DENO_INSTALL="$HOME/.deno"
    export PATH="$DENO_INSTALL/bin:$PATH"
    # Link system-wide
    sudo ln -sf "$HOME/.deno/bin/deno" /usr/local/bin/deno
    echo "  Done."
fi

# ── Step 4: App icons ────────────────────────────────────────────────────────
echo "► [4/5] Installing icons..."

# Generate icons using Python
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

import os
install_dir = os.path.expanduser("~/linux-downloader")
icons_dir = os.path.join(install_dir, "icons")
os.makedirs(icons_dir, exist_ok=True)
for s in [16,32,48,64,128,256]:
    path = os.path.join(icons_dir, f"linux-downloader-{s}.png")
    if not os.path.exists(path):
        with open(path, 'wb') as f:
            f.write(create_png(s))
print("Icons generated.")
PYEOF

# Install icons to system theme
for size in 16 32 48 64 128 256; do
    DEST="/usr/share/icons/hicolor/${size}x${size}/apps"
    sudo mkdir -p "$DEST"
    sudo cp "$INSTALL_DIR/icons/${ICON_NAME}-${size}.png" "$DEST/${ICON_NAME}.png" 2>/dev/null || true
done
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
echo "  Done."

# ── Step 5: Desktop entry ────────────────────────────────────────────────────
echo "► [5/5] Creating desktop entry..."

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

# Also install system-wide
sudo cp "$DESKTOP_FILE" /usr/share/applications/ 2>/dev/null || true
sudo update-desktop-database /usr/share/applications/ 2>/dev/null || true

echo "  Done."

# ── Make executable ──────────────────────────────────────────────────────────
chmod +x "$INSTALL_DIR/download_manager.py"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║         Installation Complete!             ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "  You can now launch Linux Download Manager"
echo "  from your application menu or by running:"
echo ""
echo "    python3 $INSTALL_DIR/download_manager.py"
echo ""
echo "  Log out and back in if the app icon"
echo "  does not appear in the start menu."
echo ""
