"""Localisation de ffmpeg, sans dépendre du PATH hérité au lancement.

Tout le toolkit s'appuie sur ffmpeg : `mlx_whisper` et `whisperx` l'appellent en
sous-processus pour décoder l'audio, yt-dlp pour extraire la piste. Tous le
cherchent dans le `PATH`, et c'est là que ça casse.

Un shell interactif charge `~/.zshrc`, donc `/opt/homebrew/bin`. Une app
Automator, un `launchd`, un raccourci du Finder : non. Le processus hérite d'un
PATH minimal (`/usr/bin:/bin:/usr/sbin:/sbin`) où ffmpeg n'est pas, alors qu'il
est installé et parfaitement fonctionnel. D'où un échec qui ne se produit qu'au
lancement graphique, jamais depuis le terminal.

Ce module ne s'occupe que de retrouver le binaire. C'est volontairement du
repérage, pas une abstraction sur ffmpeg.
"""

import os
import shutil

# Emplacements Homebrew, Apple Silicon puis Intel. Consultés seulement quand le
# PATH du processus n'a rien donné : le PATH reste la source d'autorité, ces
# chemins sont le filet.
FALLBACK_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")


def find_ffmpeg() -> str | None:
    """Retourne le chemin de l'exécutable ffmpeg, ou None s'il est introuvable."""
    found = shutil.which("ffmpeg")
    if found:
        return found

    for directory in FALLBACK_DIRS:
        candidate = os.path.join(directory, "ffmpeg")
        if os.access(candidate, os.X_OK):
            return candidate

    return None


def ensure_on_path() -> str | None:
    """Ajoute le dossier de ffmpeg au PATH du processus. Retourne son chemin.

    Retourne `None` si ffmpeg reste introuvable — à l'appelant de le signaler.

    Passer par le PATH plutôt que par un argument est ici la seule voie :
    `mlx_whisper` et `whisperx` lancent `ffmpeg` par son nom nu, sans offrir de
    paramètre pour le situer. Contrairement à yt-dlp, à qui `youtube.py` donne
    le chemin explicitement (`ffmpeg_location`) et qui n'a donc pas besoin de
    ça.

    Modifier `os.environ` est un effet de bord assumé : c'est ce qui est hérité
    par les sous-processus, et c'est exactement ce qu'on veut réparer. L'appel
    est idempotent.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None

    directory = os.path.dirname(ffmpeg)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if directory not in parts:
        os.environ["PATH"] = os.pathsep.join([directory, *parts])

    return ffmpeg
