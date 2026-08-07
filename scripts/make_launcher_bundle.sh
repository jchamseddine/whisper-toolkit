#!/bin/bash
#
# Build "~/Library/Application Support/Whisper Toolkit/Whisper Toolkit.app": a
# copy of the interpreter's Python.app bundle, rebadged in the project's colours.
#
#   ./scripts/make_launcher_bundle.sh
#
# Why the detour. macOS identifies a process by the `.app` bundle its executable
# belongs to. But Homebrew's `python3.12` is only a relay: it re-executes into
# `Python.framework/.../Resources/Python.app`, whose `Info.plist` announces
# "Python" and a rocket. Everything that comes from the bundle — the Dock
# tooltip, the process name in `ps` — is therefore inherited from the
# interpreter, and no runtime setting catches up with it: `set_dock_identity()`
# in `launch_desktop.py` fixes the icon and the menu, not the rest.
#
# The copy settles the problem at the root: same binary, our own `Info.plist`.
# The original is never touched — only read — and the bundle produced keeps its
# provenance in Contents/Resources/ORIGIN.txt.
#
# Three traps, each of them silent:
#
#   1. **The venv gets lost.** Running the bundle's binary directly bypasses
#      `venv/bin/python`: no more streamlit, no more pywebview. The
#      `__PYVENV_LAUNCHER__` variable — the very one Homebrew's relay uses to
#      survive its own re-execution — puts the interpreter back in the venv. The
#      Automator app is what sets it; see the README.
#   2. **The signature breaks.** The copied binary is signed; editing
#      `Info.plist` invalidates the seal and macOS then refuses to launch the
#      bundle. It has to be re-signed ad-hoc afterwards.
#   3. **LaunchServices remembers.** Without `lsregister -f`, the Dock keeps
#      showing the old name and the old icon, even after the bundle is rebuilt.
#
# Run again after every Homebrew update of Python: the copied binary points at
# the exact framework version, which a `brew upgrade` moves.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$ROOT/venv/bin/python"
ICNS="$ROOT/assets/app-icon.icns"

NAME="Whisper Toolkit"
IDENTIFIER="com.jad.whisper-toolkit"
MIC_USAGE="Whisper Toolkit needs the microphone for quick dictation."

# The bundle's name is not cosmetic: it is what the Dock shows on hover, not
# `CFBundleName`. Hence "Whisper Toolkit.app", spelled identically.
#
# Kept out of ~/Applications on purpose. This bundle is not an app you launch:
# double-clicked, it would open a Python interpreter with no window. It is only
# a costume, worn by the Automator applet, which stays the one visible entry
# point.
DEST="${DEST:-$HOME/Library/Application Support/Whisper Toolkit/$NAME.app}"

if [ ! -x "$VENV_PY" ]; then
    echo "venv not found: $VENV_PY" >&2
    exit 1
fi
if [ ! -f "$ICNS" ]; then
    echo "icon not found: $ICNS — run make_app_icon.sh first" >&2
    exit 1
fi

# base_prefix points at the framework version the venv actually uses, going
# through the /opt/homebrew/opt link that survives updates.
SOURCE="$("$VENV_PY" -c 'import os, sys; print(os.path.join(sys.base_prefix, "Resources", "Python.app"))')"
if [ ! -d "$SOURCE" ]; then
    echo "Python.app not found in the framework: $SOURCE" >&2
    exit 1
fi

echo "== copying $SOURCE =="
mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$SOURCE" "$DEST"
chmod -R u+w "$DEST"

PLIST="$DEST/Contents/Info.plist"

echo "== identity: $NAME ($IDENTIFIER) =="
# Renaming the executable makes the process name follow in `ps` and Activity
# Monitor, which the Info.plist alone does not change.
mv "$DEST/Contents/MacOS/Python" "$DEST/Contents/MacOS/$NAME"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable $NAME" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleName $NAME" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string $NAME" "$PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $NAME" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $IDENTIFIER" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile app-icon" "$PLIST"
# Without this key, macOS kills the process at the first microphone request
# instead of showing the permission prompt: the "Quick dictation" tab would have
# no way to record. The text is the one the user sees.
/usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string $MIC_USAGE" "$PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :NSMicrophoneUsageDescription $MIC_USAGE" "$PLIST"
# Inherited from the interpreter and pointless here: MacPython's help, and the
# app being associated with every file type.
/usr/libexec/PlistBuddy -c "Delete :CFBundleDocumentTypes" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Delete :CFBundleHelpBookFolder" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Delete :CFBundleHelpBookName" "$PLIST" 2>/dev/null || true

cp "$ICNS" "$DEST/Contents/Resources/app-icon.icns"
rm -f "$DEST/Contents/Resources/PythonInterpreter.icns"

cat > "$DEST/Contents/Resources/ORIGIN.txt" <<TXT
Bundle produced by scripts/make_launcher_bundle.sh of the whisper-toolkit repo.
Copy of: $SOURCE
Only the Info.plist and the icon differ from the original, which is never
modified. Rebuild after a Homebrew update of Python.
TXT

# Trap 2: without this signature, macOS refuses to launch a bundle whose
# Info.plist no longer matches the binary's seal.
echo "== signing =="
codesign --force --sign - "$DEST"
codesign --verify --strict "$DEST" && echo "signature: valid"

# Trap 3: forces LaunchServices to re-read the bundle rather than its cache.
LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
"$LSREG" -f "$DEST"

echo
echo "bundle ready: $DEST"
echo "invoke it with the venv:"
echo "  __PYVENV_LAUNCHER__=\"$VENV_PY\" \"$DEST/Contents/MacOS/$NAME\" launch_desktop.py"
