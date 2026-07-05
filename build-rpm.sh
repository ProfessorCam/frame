#!/usr/bin/env bash
# Build an RPM package for frame (Fedora/RHEL/DNF)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="${1:-1.1.0}"
RELEASE="${2:-1}"
PKG="frame"

echo "Building ${PKG}-${VERSION}-${RELEASE} RPM..."

BUILD_ROOT="$SCRIPT_DIR/build/rpm"
rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# ── Create tarball ────────────────────────────────────────────────
TARDIR="$BUILD_ROOT/SOURCES/${PKG}-${VERSION}"
mkdir -p "$TARDIR/frame"
cp "$SCRIPT_DIR/frame/__init__.py"      "$TARDIR/frame/"
cp "$SCRIPT_DIR/frame/__main__.py"      "$TARDIR/frame/"
cp "$SCRIPT_DIR/frame/app.py"           "$TARDIR/frame/"
cp "$SCRIPT_DIR/frame/recorder.py"      "$TARDIR/frame/"
cp "$SCRIPT_DIR/frame/config.py"        "$TARDIR/frame/"
cp "$SCRIPT_DIR/frame/overlay.py"       "$TARDIR/frame/"
cp "$SCRIPT_DIR/frame/dbus_control.py"  "$TARDIR/frame/"
cp "$SCRIPT_DIR/frame/globalshortcuts.py" "$TARDIR/frame/"
# GNOME Shell extension
EXT_UUID="frame@professorcam.github.io"
mkdir -p "$TARDIR/gnome-shell-extension/$EXT_UUID"
cp "$SCRIPT_DIR/gnome-shell-extension/$EXT_UUID"/*.json \
   "$SCRIPT_DIR/gnome-shell-extension/$EXT_UUID"/*.js \
   "$SCRIPT_DIR/gnome-shell-extension/$EXT_UUID"/*.css \
   "$TARDIR/gnome-shell-extension/$EXT_UUID/"
# Icons
mkdir -p "$TARDIR/icons"
cp "$SCRIPT_DIR/icons/frame-"*.png "$TARDIR/icons/"
cp "$SCRIPT_DIR/frame.svg" "$TARDIR/"
(cd "$BUILD_ROOT/SOURCES" && tar czf "${PKG}-${VERSION}.tar.gz" "${PKG}-${VERSION}")
rm -rf "$TARDIR"

# ── Spec file ─────────────────────────────────────────────────────
cat > "$BUILD_ROOT/SPECS/${PKG}.spec" << SPEC
Name:           ${PKG}
Version:        ${VERSION}
Release:        ${RELEASE}%{?dist}
Summary:        Screen area recorder for GNOME Wayland
License:        MIT
URL:            https://github.com/ProfessorCam/frame
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       gstreamer1-plugins-base
Requires:       gstreamer1-plugins-good
Requires:       gstreamer1-plugins-ugly-free
Requires:       gstreamer1-plugins-bad-free
Requires:       pipewire-gstreamer
Requires:       ffmpeg-free
Recommends:     libnotify

%description
A Peek-like screen recorder that captures GIF, WebM, and MP4
files on GNOME Wayland. Uses Mutter ScreenCast and PipeWire
for screen capture, with a GTK4/libadwaita UI.

%prep
%setup -q

%install
mkdir -p %{buildroot}/usr/lib/%{name}/frame
install -m 644 frame/__init__.py      %{buildroot}/usr/lib/%{name}/frame/
install -m 644 frame/__main__.py      %{buildroot}/usr/lib/%{name}/frame/
install -m 644 frame/app.py           %{buildroot}/usr/lib/%{name}/frame/
install -m 644 frame/recorder.py      %{buildroot}/usr/lib/%{name}/frame/
install -m 644 frame/config.py        %{buildroot}/usr/lib/%{name}/frame/
install -m 644 frame/overlay.py       %{buildroot}/usr/lib/%{name}/frame/
install -m 644 frame/dbus_control.py  %{buildroot}/usr/lib/%{name}/frame/
install -m 644 frame/globalshortcuts.py %{buildroot}/usr/lib/%{name}/frame/

mkdir -p %{buildroot}/usr/share/gnome-shell/extensions/frame@professorcam.github.io
install -m 644 gnome-shell-extension/frame@professorcam.github.io/metadata.json  %{buildroot}/usr/share/gnome-shell/extensions/frame@professorcam.github.io/
install -m 644 gnome-shell-extension/frame@professorcam.github.io/extension.js   %{buildroot}/usr/share/gnome-shell/extensions/frame@professorcam.github.io/
install -m 644 gnome-shell-extension/frame@professorcam.github.io/stylesheet.css %{buildroot}/usr/share/gnome-shell/extensions/frame@professorcam.github.io/

mkdir -p %{buildroot}/usr/share/icons/hicolor/scalable/apps
install -m 644 frame.svg %{buildroot}/usr/share/icons/hicolor/scalable/apps/frame.svg
mkdir -p %{buildroot}/usr/share/icons/hicolor/16x16/apps
install -m 644 icons/frame-16.png  %{buildroot}/usr/share/icons/hicolor/16x16/apps/frame.png
mkdir -p %{buildroot}/usr/share/icons/hicolor/32x32/apps
install -m 644 icons/frame-32.png  %{buildroot}/usr/share/icons/hicolor/32x32/apps/frame.png
mkdir -p %{buildroot}/usr/share/icons/hicolor/48x48/apps
install -m 644 icons/frame-48.png  %{buildroot}/usr/share/icons/hicolor/48x48/apps/frame.png
mkdir -p %{buildroot}/usr/share/icons/hicolor/64x64/apps
install -m 644 icons/frame-64.png  %{buildroot}/usr/share/icons/hicolor/64x64/apps/frame.png
mkdir -p %{buildroot}/usr/share/icons/hicolor/128x128/apps
install -m 644 icons/frame-128.png %{buildroot}/usr/share/icons/hicolor/128x128/apps/frame.png
mkdir -p %{buildroot}/usr/share/icons/hicolor/256x256/apps
install -m 644 icons/frame-256.png %{buildroot}/usr/share/icons/hicolor/256x256/apps/frame.png
mkdir -p %{buildroot}/usr/share/icons/hicolor/512x512/apps
install -m 644 icons/frame-512.png %{buildroot}/usr/share/icons/hicolor/512x512/apps/frame.png

mkdir -p %{buildroot}/usr/bin
cat > %{buildroot}/usr/bin/%{name} << 'LAUNCHER'
#!/usr/bin/python3
"""Launch frame."""
import sys
sys.path.insert(0, '/usr/lib/frame')
from frame.__main__ import main
sys.exit(main())
LAUNCHER
chmod 755 %{buildroot}/usr/bin/%{name}

mkdir -p %{buildroot}/usr/share/applications
cat > %{buildroot}/usr/share/applications/com.github.frame.desktop << 'DESKTOP'
[Desktop Entry]
Name=Frame
Comment=Screen area recorder for GNOME Wayland
Exec=frame
Icon=frame
Terminal=false
Type=Application
Categories=AudioVideo;Video;Recorder;
Keywords=screencast;recording;gif;video;
StartupNotify=true
X-GNOME-Introspect=true
DESKTOP

%files
/usr/lib/%{name}/
/usr/bin/%{name}
/usr/share/applications/com.github.frame.desktop
/usr/share/gnome-shell/extensions/frame@professorcam.github.io/
/usr/share/icons/hicolor/*/apps/frame.png
/usr/share/icons/hicolor/scalable/apps/frame.svg

%changelog
* $(date '+%a %b %d %Y') Cameron Ryan <cameronaryan@gmail.com> - ${VERSION}-${RELEASE}
- Initial RPM package
SPEC

# ── Build ─────────────────────────────────────────────────────────
rpmbuild --define "_topdir $BUILD_ROOT" -bb "$BUILD_ROOT/SPECS/${PKG}.spec"

RPM=$(find "$BUILD_ROOT/RPMS" -name '*.rpm' | head -1)
if [ -n "$RPM" ]; then
    cp "$RPM" "$SCRIPT_DIR/build/"
    BASENAME=$(basename "$RPM")
    echo ""
    echo "Package built: $SCRIPT_DIR/build/$BASENAME"
    echo ""
    echo "Install with:"
    echo "  sudo dnf install $SCRIPT_DIR/build/$BASENAME"
    echo ""
    echo "Uninstall with:"
    echo "  sudo dnf remove frame"
else
    echo "ERROR: rpmbuild failed — is rpm-build installed?" >&2
    echo "  sudo dnf install rpm-build" >&2
    exit 1
fi
