#!/bin/bash
# Run this once to install the icon system-wide
# Usage: bash install_icon.sh

ICON_NAME="linux-downloader"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Linux Downloader icons..."

for size in 16 32 48 64 128 256; do
    DEST="/usr/share/icons/hicolor/${size}x${size}/apps"
    sudo mkdir -p "$DEST"
    sudo cp "$SCRIPT_DIR/icons/${ICON_NAME}-${size}.png" "$DEST/${ICON_NAME}.png"
    echo "  Installed ${size}x${size}"
done

# Also copy SVG to scalable
sudo mkdir -p /usr/share/icons/hicolor/scalable/apps
sudo cp "$SCRIPT_DIR/${ICON_NAME}.svg" "/usr/share/icons/hicolor/scalable/apps/${ICON_NAME}.svg"
echo "  Installed scalable SVG"

# Update icon cache so Zorin/GTK picks it up
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor/
echo "Icon cache updated."

# Install the .desktop file
sudo cp "$SCRIPT_DIR/downloader.desktop" /usr/share/applications/
echo "Desktop entry installed."

echo ""
echo "Done! The icon will appear in Zorin's start menu and taskbar."
echo "You may need to log out and back in if it doesn't appear immediately."
