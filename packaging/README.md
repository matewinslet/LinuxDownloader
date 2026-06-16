# Packaging

Native packages for Linux Download Manager. Each package is **self-contained**:
it bundles the app's Python dependencies (PyQt6, yt-dlp, `curl_cffi<0.15`,
pycryptodome, …) in a venv under `/opt/linux-downloader`, so it doesn't depend
on distro Python package versions. The launcher `/usr/bin/linux-downloader`
runs the app with that bundled interpreter.

> **Build on the target distro family.** The bundled venv contains compiled
> wheels tied to that platform's Python. Build the `.deb` on Debian/Ubuntu/Mint,
> the `.rpm` on Fedora, and let `makepkg` build the AUR package on Arch.

`deno` (YouTube JS runtime) is **optional** — the app offers to install it on
first use, so it's an `optdepends`/`Recommends`, not a hard requirement.

## Layout

```
/opt/linux-downloader/
    download_manager.py        # the app
    assets/ icons/ fonts/      # resources (loaded relative to the script)
    venv/                      # bundled Python deps
/usr/bin/linux-downloader      # launcher
/usr/share/applications/linux-download-manager.desktop
/usr/share/icons/hicolor/*/apps/linux-downloader.*
```

## .deb (Debian / Ubuntu / Mint / Zorin)

```bash
packaging/build-deb.sh
# -> dist/linux-download-manager_2.0.0_amd64.deb
sudo apt install ./dist/linux-download-manager_2.0.0_amd64.deb
```

The control file depends on the build host's `python3.X` interpreter package, so
install on a release that ships the same Python minor (e.g. Ubuntu 24.04 / Mint
22 / Zorin 18 all ship 3.12).

## .rpm (Fedora / RHEL / openSUSE) — build on Fedora

```bash
sudo dnf install -y rpm-build python3 python3-pip
packaging/rpm/build-rpm.sh
# -> dist/linux-download-manager-2.0.0-1.fc*.x86_64.rpm
sudo dnf install ./dist/linux-download-manager-2.0.0-1.*.x86_64.rpm
```

## AUR (Arch / Manjaro)

`packaging/aur/` holds `PKGBUILD` and `.SRCINFO`. To publish:

```bash
git clone ssh://aur@aur.archlinux.org/linux-download-manager.git aur-ldm
cp packaging/aur/PKGBUILD packaging/aur/.SRCINFO aur-ldm/
cd aur-ldm
# verify it builds:
makepkg -si
# regenerate .SRCINFO if you change PKGBUILD:
makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD .SRCINFO && git commit -m "Initial import" && git push
```

Publishing to the AUR requires your AUR account + registered SSH key.

## Distributing the .deb / .rpm

Attach the built `.deb` / `.rpm` to a GitHub Release (e.g. the `v2.0` release)
so users can download them directly.

## Already works today

`install.sh` at the repo root already supports `apt`, `dnf`, `pacman`, and
`zypper` — so Fedora and Arch users can install right now without these
packages. These exist to make installation a one-click/native experience.
