#!/usr/bin/env bash
# Install & enable the frame GNOME Shell extension for the current user.
#
# This adds the top-bar Pause/Stop indicator that appears while frame is
# recording.  On Wayland a newly installed extension only loads after a
# logout/login (you can't restart GNOME Shell in place); on X11 you can restart
# the Shell with Alt+F2 → r.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UUID="frame@professorcam.github.io"
SRC="$SCRIPT_DIR/gnome-shell-extension/$UUID"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$UUID"

if [ ! -d "$SRC" ]; then
    echo "ERROR: extension source not found at $SRC" >&2
    exit 1
fi

echo "Installing $UUID → $DEST"
mkdir -p "$DEST"
cp "$SRC/metadata.json" "$SRC/extension.js" "$SRC/stylesheet.css" "$DEST/"

if command -v gnome-extensions >/dev/null 2>&1; then
    # enable may fail until the Shell rescans (Wayland); that's fine.
    gnome-extensions enable "$UUID" 2>/dev/null \
        && echo "Enabled." \
        || echo "Installed. Enable after re-login with: gnome-extensions enable $UUID"
else
    echo "Installed. Enable it from the Extensions app after re-login."
fi

SESSION_TYPE="${XDG_SESSION_TYPE:-unknown}"
if [ "$SESSION_TYPE" = "wayland" ]; then
    echo ""
    echo "Wayland session detected: log out and back in to load the extension."
else
    echo ""
    echo "X11 session: restart GNOME Shell with Alt+F2 then 'r', or re-login."
fi
