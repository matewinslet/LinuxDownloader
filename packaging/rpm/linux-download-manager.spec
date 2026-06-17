Name:           linux-download-manager
Version:        2.0.0
Release:        2%{?dist}
Summary:        Linux Download Manager (LDM)
License:        MIT
URL:            https://github.com/matewinslet/LinuxDownloader
BuildArch:      x86_64

# The app bundles its Python deps in a venv (built in %%install), so at runtime
# it only needs the matching interpreter and the Qt/xcb runtime libraries.
# Pin python3.12 (the version the bundle is built against, in the fedora:40 CI
# container) — Fedora ships a python3.12 package even on 41/42, so this keeps
# the package working across Fedora releases regardless of the default Python.
Requires:       python3.12
Requires:       ffmpeg
Requires:       xcb-util-cursor
Requires:       libxkbcommon-x11
Requires:       fontconfig
Requires:       mesa-libEGL
Requires:       mesa-libGL
Recommends:     curl

# The app is fully self-contained: the venv bundles PyQt6 (with its own Qt6
# libraries) and every other Python dep under /opt/linux-downloader. RPM's
# automatic dependency generator otherwise scans those bundled .so files and
# emits Requires for private Qt symbols and unrelated optional Qt SQL/3D/WebEngine
# plugin libs (Qt_6_PRIVATE_API, libQt6WebEngineQuick, libclntsh (Oracle),
# libmimerapi (Mimer), libtiff.so.5, ...) that no distro package provides, so the
# install fails with "nothing provides ...". Disable auto Requires/Provides and
# rely solely on the explicit Requires above.
#
# NOTE: the previous attempt used `__requires_exclude ^/opt/linux-downloader/.*$`,
# but that regex is matched against the generated dependency STRING (e.g.
# "libQt63DCore.so.6(...)"), not the file path, so it never fired. The path-based
# form is `__requires_exclude_from`; AutoReqProv:no is simpler and covers both.
AutoReqProv:    no

# Bundled venv contains prebuilt content; skip debug/strip processing.
%global debug_package %{nil}
%global __brp_mangle_shebangs %{nil}

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
* Wed Jun 17 2026 Tanjim <tpodbcs@gmail.com> - 2.0.0-2
- Fix install failure ("nothing provides libQt6...PRIVATE_API / libclntsh /
  libmimerapi / libtiff.so.5"): set AutoReqProv:no so the bundled venv's Qt/
  Python .so files no longer generate unsatisfiable system dependencies. The
  prior __requires_exclude matched the dep string, not the file path, so it
  never took effect.

* Tue Jun 16 2026 Tanjim <tpodbcs@gmail.com> - 2.0.0-1
- Initial RPM packaging (self-contained bundle).
