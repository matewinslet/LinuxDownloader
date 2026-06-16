Name:           linux-download-manager
Version:        2.0.0
Release:        1%{?dist}
Summary:        Linux Download Manager (LDM)
License:        MIT
URL:            https://github.com/matewinslet/LinuxDownloader
BuildArch:      x86_64

# The app bundles its Python deps in a venv (built in %%install), so at runtime
# it only needs the system interpreter and the Qt/xcb runtime libraries.
Requires:       python3
Requires:       ffmpeg
Requires:       xcb-util-cursor
Requires:       libxkbcommon-x11
Requires:       fontconfig
Requires:       mesa-libEGL
Requires:       mesa-libGL
Recommends:     curl

# Bundled venv contains prebuilt content; skip debug/strip processing.
%global debug_package %{nil}
%global __brp_mangle_shebangs %{nil}
%global __requires_exclude ^/opt/linux-downloader/.*$
%global __provides_exclude ^/opt/linux-downloader/.*$

%description
Download files and videos with browser integration, yt-dlp powered streaming,
and a Qt6 interface. Self-contained: bundles its Python dependencies under
/opt/linux-downloader.

%install
rm -rf %{buildroot}
# %{_sourcedir}/LinuxDownloader must contain a checkout of the repo. See
# packaging/rpm/build-rpm.sh, which sets that up before calling rpmbuild.
REPO="%{_sourcedir}/LinuxDownloader"
SRC_DIR="$REPO" bash "$REPO/packaging/build-bundle.sh" "%{buildroot}"
install -Dm755 "$REPO/packaging/linux-downloader" %{buildroot}/usr/bin/linux-downloader
install -Dm644 "$REPO/packaging/linux-download-manager.desktop" \
  %{buildroot}/usr/share/applications/linux-download-manager.desktop
for sz in 16 32 48 64 128 256 512; do
  install -Dm644 "$REPO/icons/linux-downloader-${sz}.png" \
    %{buildroot}/usr/share/icons/hicolor/${sz}x${sz}/apps/linux-downloader.png
done
install -Dm644 "$REPO/icons/linux-downloader.svg" \
  %{buildroot}/usr/share/icons/hicolor/scalable/apps/linux-downloader.svg

%files
/opt/linux-downloader
/usr/bin/linux-downloader
/usr/share/applications/linux-download-manager.desktop
/usr/share/icons/hicolor/*/apps/linux-downloader.png
/usr/share/icons/hicolor/scalable/apps/linux-downloader.svg

%post
gtk-update-icon-cache -f /usr/share/icons/hicolor &>/dev/null || :
update-desktop-database /usr/share/applications &>/dev/null || :

%postun
gtk-update-icon-cache -f /usr/share/icons/hicolor &>/dev/null || :
update-desktop-database /usr/share/applications &>/dev/null || :

%changelog
* Tue Jun 16 2026 Tanjim <tpodbcs@gmail.com> - 2.0.0-1
- Initial RPM packaging (self-contained bundle).
