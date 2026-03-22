#!/usr/bin/env python3
import json, os, glob

pip_dir = os.path.expanduser("~/linux-downloader/pip-packages")
whl_files = sorted(glob.glob(os.path.join(pip_dir, "*.whl")))

pip_sources = [{"type": "file", "path": f"pip-packages/{os.path.basename(w)}"} for w in whl_files]
pip_installs = [f"pip3 install --no-index --find-links=/run/build/python3-deps --prefix=/app {os.path.basename(w)}" for w in whl_files]

manifest = {
    "app-id": "com.tanjim.LDM",
    "runtime": "org.kde.Platform",
    "runtime-version": "6.8",
    "sdk": "org.kde.Sdk",
    "command": "ldm",
    "finish-args": [
        "--share=network",
        "--share=ipc",
        "--socket=x11",
        "--socket=wayland",
        "--filesystem=home",
        "--talk-name=org.freedesktop.Notifications",
        "--talk-name=org.freedesktop.FileManager1"
    ],
    "modules": [
        {
            "name": "python3-deps",
            "buildsystem": "simple",
            "build-commands": pip_installs,
            "sources": pip_sources
        },
        {
            "name": "ldm",
            "buildsystem": "simple",
            "build-commands": [
                "cp -r . /app/ldm",
                "install -Dm755 download_manager.py /app/bin/ldm",
                "install -Dm644 icons/linux-downloader-256.png /app/share/icons/hicolor/256x256/apps/com.tanjim.LDM.png",
                "install -Dm644 com.tanjim.LDM.desktop /app/share/applications/com.tanjim.LDM.desktop"
            ],
            "sources": [
                {
                    "type": "dir",
                    "path": "."
                }
            ]
        }
    ]
}

out = os.path.expanduser("~/linux-downloader/com.tanjim.LDM.json")
with open(out, "w") as f:
    json.dump(manifest, f, indent=2)
print(f"Written: {out}")
print(f"Included {len(whl_files)} packages:")
for w in whl_files:
    print(f"  {os.path.basename(w)}")