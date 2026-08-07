#!/bin/bash
#
# Régénère l'icône de l'app Automator « Whisper Toolkit.app » à partir d'un
# emoji, et l'applique au bundle.
#
# Sans argument : régénère assets/app-icon.icns sans toucher à l'app.
# Avec --apply  : applique en plus l'icône à l'app installée.
#
#   ./scripts/make_app_icon.sh
#   ./scripts/make_app_icon.sh --apply
#   EMOJI=🎧 ./scripts/make_app_icon.sh --apply
#
# Quatre pièges macOS sont traités ici. Les retirer casse quelque chose qui
# marche, chacun de façon silencieuse — d'où ce script plutôt qu'une note :
#
#   1. Le bundle Automator embarque un `Assets.car` contenant l'icône en
#      calques du robot, désignée par `CFBundleIconName`. Ce catalogue prime sur
#      `CFBundleIconFile` : remplacer le .icns sans supprimer cette clé ne change
#      rien à l'écran, sans le moindre message d'erreur.
#   2. `codesign` REFUSE de signer un bundle portant un xattr
#      `com.apple.FinderInfo`. L'app en avait un (résidu de tag Finder). Sans le
#      retirer, la signature est invalidée sans être remplacée : l'app se
#      retrouve cassée.
#   3. L'app est signée ad-hoc : toute retouche de `Contents/` invalide le sceau,
#      il faut resigner (`--sign -`).
#   4. Le stub Automator pose `LSUIElement`, qui prive l'app de vignette Dock
#      pendant son exécution. On retire la clé pour qu'elle se comporte en app
#      normale.
#
set -euo pipefail

EMOJI="${EMOJI:-🎙️}"
APP="${APP:-/Applications/Whisper Toolkit.app}"

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS="$RACINE/assets"
ICNS="$ASSETS/app-icon.icns"
PNG="$ASSETS/app-icon-1024.png"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python_bin() {
    # Pillow vit dans le venv du projet, pas dans le python système.
    if [ -x "$RACINE/venv/bin/python" ]; then
        echo "$RACINE/venv/bin/python"
    else
        echo "python3"
    fi
}

echo "== rendu de $EMOJI =="
mkdir -p "$ASSETS"
# Toile large + police à 62 % : le glyphe déborde de sa boîte em, dessiner à
# 100 % le ferait rogner sur les bords. compose_icon.py recadre ensuite.
swift "$RACINE/scripts/render_emoji.swift" "$EMOJI" 2048 "$TMP/rendu.png" 0.62
"$(python_bin)" "$RACINE/scripts/compose_icon.py" "$TMP/rendu.png" "$PNG"

echo "== construction du .icns =="
ICONSET="$TMP/icon.iconset"
mkdir -p "$ICONSET"
"$(python_bin)" - "$PNG" "$ICONSET" <<'PY'
import sys
from PIL import Image

src = Image.open(sys.argv[1]).convert("RGBA")
dossier = sys.argv[2]
for base in (16, 32, 128, 256, 512):
    for suffixe, px in (("", base), ("@2x", base * 2)):
        src.resize((px, px), Image.LANCZOS).save(f"{dossier}/icon_{base}x{base}{suffixe}.png")
PY
iconutil -c icns "$ICONSET" -o "$ICNS"
echo "écrit $ICNS"

if [ "${1:-}" != "--apply" ]; then
    echo "(icône non appliquée — relancer avec --apply)"
    exit 0
fi

if [ ! -d "$APP" ]; then
    echo "app introuvable : $APP" >&2
    exit 1
fi

echo "== application à $APP =="
cp "$ICNS" "$APP/Contents/Resources/ApplicationStub.icns"

# Piège 1 : sans cette suppression, Assets.car continue de fournir l'icône.
/usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$APP/Contents/Info.plist" 2>/dev/null || true
# Piège 4 : rend la vignette Dock visible pendant l'exécution.
/usr/libexec/PlistBuddy -c "Delete :LSUIElement" "$APP/Contents/Info.plist" 2>/dev/null || true
# Piège 2 : à faire avant de signer, sinon codesign refuse et laisse l'app cassée.
xattr -d com.apple.FinderInfo "$APP" 2>/dev/null || true
# Piège 3 : resceller le bundle ad-hoc.
codesign --force --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo "signature : valide"

LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
"$LSREG" -f "$APP"
touch "$APP"
killall Dock 2>/dev/null || true
killall Finder 2>/dev/null || true
echo "icône appliquée ; Finder et Dock redémarrés"
