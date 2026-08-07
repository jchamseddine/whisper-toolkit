#!/bin/bash
#
# Construit ~/Applications/WhisperToolkitLauncher.app : une copie du bundle
# Python.app de l'interpréteur, rebaptisée aux couleurs du projet.
#
#   ./scripts/make_launcher_bundle.sh
#
# Pourquoi ce détour. macOS identifie un processus par le bundle `.app` auquel
# appartient son exécutable. Or le `python3.12` de Homebrew n'est qu'un relais :
# il se ré-exécute dans `Python.framework/.../Resources/Python.app`, dont
# l'`Info.plist` annonce « Python » et une fusée. Tout ce qui vient du bundle —
# infobulle du Dock, nom du processus dans `ps` — hérite donc de l'interpréteur,
# et aucun réglage à l'exécution ne le rattrape : `set_dock_identity()` dans
# `launch_desktop.py` corrige l'icône et le menu, pas le reste.
#
# La copie règle le problème à la racine : même binaire, `Info.plist` à nous.
# L'original n'est jamais touché — il n'est que lu, et le bundle produit garde
# sa provenance dans Contents/Resources/ORIGINE.txt.
#
# Trois pièges, chacun silencieux :
#
#   1. **Le venv se perd.** Lancer le binaire du bundle directement court-circuite
#      `venv/bin/python` : plus de streamlit, plus de pywebview. La variable
#      `__PYVENV_LAUNCHER__` — celle-là même que le relais de Homebrew utilise
#      pour survivre à sa ré-exécution — remet l'interpréteur dans le venv. C'est
#      l'app Automator qui la pose ; voir le README.
#   2. **La signature saute.** Le binaire copié est signé ; retoucher
#      `Info.plist` invalide le sceau et macOS refuse alors de lancer le bundle.
#      Il faut resigner ad-hoc après coup.
#   3. **LaunchServices garde en mémoire.** Sans `lsregister -f`, le Dock
#      continue d'afficher l'ancien nom et l'ancienne icône, y compris après
#      reconstruction du bundle.
#
# À relancer après chaque mise à jour de Python par Homebrew : le binaire copié
# pointe vers la version exacte du framework, qu'un `brew upgrade` déplace.
#
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$RACINE/venv/bin/python"
ICNS="$RACINE/assets/app-icon.icns"

NOM="Whisper Toolkit"
IDENTIFIANT="com.jad.whisper-toolkit"

# Le nom du bundle n'est pas cosmétique : c'est lui, et non `CFBundleName`, que
# le Dock affiche au survol. D'où « Whisper Toolkit.app » à l'identique.
#
# Rangé hors de ~/Applications à dessein. Ce bundle n'est pas une app qu'on
# lance : double-cliqué, il ouvrirait un interpréteur Python sans fenêtre. Il
# n'est qu'un costume, porté par l'applet Automator qui reste le seul point
# d'entrée visible.
DEST="${DEST:-$HOME/Library/Application Support/Whisper Toolkit/$NOM.app}"

if [ ! -x "$VENV_PY" ]; then
    echo "venv introuvable : $VENV_PY" >&2
    exit 1
fi
if [ ! -f "$ICNS" ]; then
    echo "icône introuvable : $ICNS — lancer d'abord make_app_icon.sh" >&2
    exit 1
fi

# base_prefix pointe vers la version du framework réellement utilisée par le
# venv, en passant par le lien /opt/homebrew/opt qui survit aux mises à jour.
SOURCE="$("$VENV_PY" -c 'import os, sys; print(os.path.join(sys.base_prefix, "Resources", "Python.app"))')"
if [ ! -d "$SOURCE" ]; then
    echo "Python.app introuvable dans le framework : $SOURCE" >&2
    exit 1
fi

echo "== copie de $SOURCE =="
mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$SOURCE" "$DEST"
chmod -R u+w "$DEST"

PLIST="$DEST/Contents/Info.plist"

echo "== identité : $NOM ($IDENTIFIANT) =="
# Renommer l'exécutable fait suivre le nom du processus dans `ps` et le moniteur
# d'activité, que l'Info.plist seul ne change pas.
mv "$DEST/Contents/MacOS/Python" "$DEST/Contents/MacOS/$NOM"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable $NOM" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleName $NOM" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string $NOM" "$PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $NOM" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $IDENTIFIANT" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile app-icon" "$PLIST"
# Héritées de l'interpréteur et sans objet ici : l'aide de MacPython et
# l'association de l'app à tous les types de fichiers.
/usr/libexec/PlistBuddy -c "Delete :CFBundleDocumentTypes" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Delete :CFBundleHelpBookFolder" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Delete :CFBundleHelpBookName" "$PLIST" 2>/dev/null || true

cp "$ICNS" "$DEST/Contents/Resources/app-icon.icns"
rm -f "$DEST/Contents/Resources/PythonInterpreter.icns"

cat > "$DEST/Contents/Resources/ORIGINE.txt" <<TXT
Bundle produit par scripts/make_launcher_bundle.sh du dépôt whisper-toolkit.
Copie de : $SOURCE
Seul l'Info.plist et l'icône diffèrent de l'original, qui n'est jamais modifié.
À reconstruire après une mise à jour de Python par Homebrew.
TXT

# Piège 2 : sans cette signature, macOS refuse de lancer un bundle dont
# l'Info.plist ne correspond plus au sceau du binaire.
echo "== signature =="
codesign --force --sign - "$DEST"
codesign --verify --strict "$DEST" && echo "signature : valide"

# Piège 3 : force LaunchServices à relire le bundle plutôt que son cache.
LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
"$LSREG" -f "$DEST"

echo
echo "bundle prêt : $DEST"
echo "à invoquer avec le venv :"
echo "  __PYVENV_LAUNCHER__=\"$VENV_PY\" \"$DEST/Contents/MacOS/$NOM\" launch_desktop.py"
