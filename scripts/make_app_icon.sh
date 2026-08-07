#!/bin/bash
#
# Regenerate the icon of the Automator app "Whisper Toolkit.app" from an emoji,
# and apply it to the bundle.
#
# With no argument: regenerates assets/app-icon.icns without touching the app.
# With --apply   : additionally applies the icon to the installed app.
#
#   ./scripts/make_app_icon.sh
#   ./scripts/make_app_icon.sh --apply
#   EMOJI=🎧 ./scripts/make_app_icon.sh --apply
#
# Four macOS traps are handled here. Removing them breaks something that works,
# each of them silently — hence this script rather than a note:
#
#   1. The Automator bundle ships an `Assets.car` holding the robot icon in
#      layers, designated by `CFBundleIconName`. That catalogue takes priority
#      over `CFBundleIconFile`: replacing the .icns without deleting that key
#      changes nothing on screen, without the slightest error message.
#   2. `codesign` REFUSES to sign a bundle carrying a `com.apple.FinderInfo`
#      xattr. The app had one (a leftover Finder tag). Without removing it, the
#      signature is invalidated without being replaced: the app ends up broken.
#   3. The app is ad-hoc signed: any edit to `Contents/` breaks the seal, and it
#      has to be re-signed (`--sign -`).
#   4. The Automator stub sets `LSUIElement`, which deprives the app of a Dock
#      tile while it runs. We remove the key so it behaves as a normal app.
#
set -euo pipefail

EMOJI="${EMOJI:-🎙️}"
APP="${APP:-/Applications/Whisper Toolkit.app}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS="$ROOT/assets"
ICNS="$ASSETS/app-icon.icns"
PNG="$ASSETS/app-icon-1024.png"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python_bin() {
    # Pillow lives in the project venv, not in the system python.
    if [ -x "$ROOT/venv/bin/python" ]; then
        echo "$ROOT/venv/bin/python"
    else
        echo "python3"
    fi
}

echo "== rendering $EMOJI =="
mkdir -p "$ASSETS"
# Wide canvas + font at 62%: the glyph overflows its em box, drawing it at 100%
# would clip it at the edges. compose_icon.py crops afterwards.
swift "$ROOT/scripts/render_emoji.swift" "$EMOJI" 2048 "$TMP/render.png" 0.62
"$(python_bin)" "$ROOT/scripts/compose_icon.py" "$TMP/render.png" "$PNG"

echo "== building the .icns =="
ICONSET="$TMP/icon.iconset"
mkdir -p "$ICONSET"
"$(python_bin)" - "$PNG" "$ICONSET" <<'PY'
import sys
from PIL import Image

src = Image.open(sys.argv[1]).convert("RGBA")
folder = sys.argv[2]
for base in (16, 32, 128, 256, 512):
    for suffix, px in (("", base), ("@2x", base * 2)):
        src.resize((px, px), Image.LANCZOS).save(f"{folder}/icon_{base}x{base}{suffix}.png")
PY
iconutil -c icns "$ICONSET" -o "$ICNS"
echo "wrote $ICNS"

if [ "${1:-}" != "--apply" ]; then
    echo "(icon not applied — run again with --apply)"
    exit 0
fi

if [ ! -d "$APP" ]; then
    echo "app not found: $APP" >&2
    exit 1
fi

echo "== applying to $APP =="
cp "$ICNS" "$APP/Contents/Resources/ApplicationStub.icns"

# Trap 1: without this deletion, Assets.car keeps supplying the icon.
/usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$APP/Contents/Info.plist" 2>/dev/null || true
# Trap 4: makes the Dock tile visible while the app runs.
/usr/libexec/PlistBuddy -c "Delete :LSUIElement" "$APP/Contents/Info.plist" 2>/dev/null || true
# Trap 2: do this before signing, otherwise codesign refuses and leaves the app broken.
xattr -d com.apple.FinderInfo "$APP" 2>/dev/null || true
# Trap 3: re-seal the ad-hoc bundle.
codesign --force --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo "signature: valid"

LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
"$LSREG" -f "$APP"
touch "$APP"
killall Dock 2>/dev/null || true
killall Finder 2>/dev/null || true
echo "icon applied; Finder and Dock restarted"
