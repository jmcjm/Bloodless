#!/bin/bash
# Build Bloodless-<version>-x86_64.AppImage in the current directory.
#
# Run from the repository root on Ubuntu 24.04 with appimage-builder 1.1.0 on PATH and the
# packages binutils fakeroot desktop-file-utils libgdk-pixbuf2.0-dev patchelf squashfs-tools
# zsync gtk-update-icon-cache libglib2.0-bin installed.
set -euo pipefail

export VERSION=${VERSION:-$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')}
compat=AppDir/runtime/compat

appimage-builder --recipe AppImageBuilder.yml --skip-test --skip-appimage

# appimage-builder 1.1.0 leaves the bundled glibc unusable, so the image would only start on
# systems whose own glibc is newer than the bundled one. Two repairs make the fallback work:
#
# 1. It rewrites the program interpreter of libc.so.6 like that of an executable, which
#    corrupts the library (the process segfaults while loading it). Put the original back.
deb=$(ls appimage-build/apt/archives/libc6_*_amd64.deb)
dpkg-deb --fsys-tarfile "$deb" | tar -xO ./usr/lib/x86_64-linux-gnu/libc.so.6 \
    > "$compat/usr/lib/x86_64-linux-gnu/libc.so.6"
# 2. Programs are started through the relative path lib64/ld-linux-x86-64.so.2, but on a
#    merged-/usr distribution the loader is deployed under usr/lib64 only.
ln -sfn usr/lib64 "$compat/lib64"

appimage-builder --recipe AppImageBuilder.yml --skip-script --skip-build --skip-test
ls -l Bloodless-*.AppImage
