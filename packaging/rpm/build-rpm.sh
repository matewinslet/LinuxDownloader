#!/usr/bin/env bash
# Build an .rpm for Fedora/RHEL/openSUSE. RUN THIS ON FEDORA (or a Fedora
# container/COPR) so the bundled venv matches Fedora's Python.
#
# Requires: rpm-build, python3 with the venv module, internet access (pip).
#   sudo dnf install -y rpm-build python3 python3-pip
#   packaging/rpm/build-rpm.sh
# Output: dist/linux-download-manager-<ver>-1.<dist>.x86_64.rpm
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SPEC="$SRC_DIR/packaging/rpm/linux-download-manager.spec"
TOP="$(mktemp -d)"
trap 'rm -rf "$TOP"' EXIT

mkdir -p "$TOP"/{SOURCES,SPECS,BUILD,RPMS,SRPMS}
# Provide the repo as a source tree the spec's %install reads from.
cp -r "$SRC_DIR" "$TOP/SOURCES/LinuxDownloader"

rpmbuild \
  --define "_topdir $TOP" \
  -bb "$SPEC"

mkdir -p "$SRC_DIR/dist"
find "$TOP/RPMS" -name '*.rpm' -exec cp -v {} "$SRC_DIR/dist/" \;
echo "==> RPM(s) copied to $SRC_DIR/dist/"
