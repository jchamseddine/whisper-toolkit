"""Transcription depuis une URL YouTube.

Ne contient aucune logique de transcription : télécharge l'audio avec yt-dlp,
puis délègue à `transcribe.py` ou `diarize.py`. Les imports sont plats pour la
même raison que dans `batch.py` — ce module s'exécute comme un script.
"""

import argparse
import os
import re
import sys
import unicodedata

import yt_dlp

from diarize import diarize_file, save_diarized_transcript
from ffmpeg_path import find_ffmpeg
from transcribe import save_transcript, transcribe_file

# Les fichiers téléchargés atterrissent dans test-audio/, déjà ignoré par git :
# le contenu récupéré depuis YouTube n'a rien à faire dans le dépôt.
DEFAULT_AUDIO_DIR = "test-audio"

# Format retenu après mesure, cf. README (Test 7). YouTube sert nativement un
# flux Opus que yt-dlp extrait en `-acodec copy`, donc sans ré-encodage : ~1 Mo
# par minute, contre ~11 Mo en wav. `.opus` est déjà dans SUPPORTED_EXTENSIONS.
# Changer cette constante suffit à basculer sur "m4a" ou "wav".
AUDIO_FORMAT = "opus"
FORMAT_SELECTOR = f"bestaudio[acodec={AUDIO_FORMAT}]/bestaudio/best"

# Au-delà, les noms deviennent ingérables en ligne de commande. Les titres
# YouTube dépassent régulièrement cette longueur.
MAX_STEM_LENGTH = 80


class _QuietLogger:
    """Avale la sortie de yt-dlp.

    `quiet` ne couvre pas les erreurs : yt-dlp les écrit sur stderr de toute
    façon. Comme `_download_error_help()` les retraduit ensuite, sans ce logger
    l'utilisateur voit le message brut *et* le message clair.
    """

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def _safe_stem(title: str, video_id: str) -> str:
    """Nom de fichier prévisible à partir du titre, avec repli sur l'identifiant.

    Le titre est translittéré en ASCII : les accents deviennent leur lettre de
    base, et tout ce qui n'est ni lettre ni chiffre devient `_`. Un titre
    entièrement non latin (japonais, arabe…) ou fait de ponctuation ne laisse
    rien d'exploitable — d'où le repli sur l'identifiant de la vidéo, qui est
    toujours un slug ASCII valide.
    """
    ascii_title = (
        unicodedata.normalize("NFKD", title or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    stem = re.sub(r"[^A-Za-z0-9]+", "_", ascii_title).strip("_")[:MAX_STEM_LENGTH]
    return stem.strip("_") or video_id


def _download_error_help(error: Exception, url: str) -> str:
    """Traduit un échec yt-dlp en message actionnable.

    yt-dlp remonte presque tout en `DownloadError` avec un texte libre : c'est
    le message qu'il faut inspecter pour distinguer les cas.
    """
    message = str(error)
    lowered = message.lower()

    if "private video" in lowered or "sign in" in lowered:
        return f"Vidéo privée : {url}\nElle n'est pas accessible sans compte autorisé."

    if "not available in your country" in lowered or (
        "geo" in lowered and "block" in lowered
    ):
        return (
            f"Vidéo bloquée dans cette région : {url}\n"
            f"YouTube en refuse l'accès depuis l'adresse IP courante."
        )

    if "unsupported url" in lowered or "is not a valid url" in lowered:
        return f"URL non gérée par yt-dlp : {url}"

    if "video unavailable" in lowered or "removed" in lowered or "terminated" in lowered:
        return (
            f"Vidéo indisponible : {url}\n"
            f"Elle est supprimée, privée, ou l'identifiant est erroné."
        )

    return f"Échec du téléchargement de {url}\nDétail : {message}"


def download_audio(url: str, output_dir: str = DEFAULT_AUDIO_DIR) -> str:
    """Télécharge la piste audio d'une URL YouTube et retourne son chemin.

    Le fichier est nommé d'après le titre de la vidéo, nettoyé pour servir de
    nom de fichier. Deux vidéos de même titre écrasent donc le même fichier.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Premier appel sans téléchargement : il faut le titre pour construire le
    # nom de sortie, donc pour connaître le chemin final avant d'écrire.
    probe_options = {
        "quiet": True,
        "no_warnings": True,
        "logger": _QuietLogger(),
        # Une URL `watch?v=…&list=…` désigne une vidéo, pas la playlist qui la
        # contient — c'est la forme qu'on obtient en copiant depuis YouTube.
        "noplaylist": True,
        # `True` aplatirait aussi la vidéo seule, qui perdrait son titre et
        # retomberait sur l'identifiant. `in_playlist` n'aplatit que le contenu
        # d'une playlist : on la détecte sans en résoudre chaque entrée.
        "extract_flat": "in_playlist",
    }
    try:
        with yt_dlp.YoutubeDL(probe_options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as error:
        raise ValueError(_download_error_help(error, url)) from error

    # `noplaylist` ne couvre pas les URL de playlist pure, qui n'ont aucune
    # vidéo à isoler. Sans ce garde-fou, les vidéos se téléchargeraient toutes
    # sous le même nom en s'écrasant, et seule la dernière serait transcrite —
    # sous le titre de la playlist.
    if info.get("_type") == "playlist" or info.get("entries"):
        count = len(info.get("entries") or [])
        raise ValueError(
            f"URL de playlist ({count} vidéos) : {url}\n"
            f"youtube.py traite une vidéo à la fois. Passe l'URL d'une vidéo."
        )

    stem = _safe_stem(info.get("title", ""), info.get("id", "video"))
    audio_path = os.path.join(output_dir, f"{stem}.{AUDIO_FORMAT}")

    duration = info.get("duration")
    print(
        f"Téléchargement : {info.get('title', '?')}"
        f"{f' ({duration // 60}:{duration % 60:02d})' if duration else ''}",
        file=sys.stderr,
    )

    options = {
        "format": FORMAT_SELECTOR,
        "outtmpl": os.path.join(output_dir, f"{stem}.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": AUDIO_FORMAT}
        ],
        "quiet": True,
        "no_warnings": True,
        "logger": _QuietLogger(),
        "noplaylist": True,
    }

    # Chemin donné explicitement plutôt que laissé à la charge du PATH : lancé
    # autrement que depuis un shell interactif — une app Automator, par exemple —
    # le processus n'a pas `/opt/homebrew/bin` et yt-dlp échoue en
    # post-traitement sur « ffprobe and ffmpeg not found », alors que ffmpeg est
    # installé. On passe le **dossier**, pas le binaire : l'extraction audio
    # réclame aussi ffprobe, que yt-dlp cherche à côté.
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        options["ffmpeg_location"] = os.path.dirname(ffmpeg)

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except Exception as error:
        raise ValueError(_download_error_help(error, url)) from error

    if not os.path.isfile(audio_path):
        raise ValueError(
            f"Téléchargement terminé sans produire {audio_path}.\n"
            f"Le format demandé ({AUDIO_FORMAT}) n'était peut-être pas disponible."
        )

    return audio_path


def transcribe_youtube(url: str, diarize: bool = False, **kwargs) -> tuple[str, str]:
    """Télécharge une vidéo puis la transcrit, avec ou sans locuteurs.

    Retourne `(texte, chemin de sortie)`. Le nom du fichier produit dépend du
    titre de la vidéo, connu seulement ici : sans le retourner, un appelant qui
    veut enchaîner sur la transcription — `cli.py --summarize` — ne peut pas la
    retrouver. Les `kwargs` sont transmis à `diarize_file()` ou à
    `transcribe_file()` selon le mode — ils ne sont pas interchangeables.
    """
    audio_path = download_audio(url)

    if diarize:
        segments = diarize_file(audio_path, **kwargs)
        output_path = save_diarized_transcript(segments, audio_path)
        text = "\n".join(f"[{s['speaker']}] {s['text']}" for s in segments)
        return text, output_path

    text = transcribe_file(audio_path, **kwargs)
    return text, save_transcript(text, audio_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcrit l'audio d'une vidéo YouTube."
    )
    parser.add_argument("url", help="URL de la vidéo")
    parser.add_argument(
        "--diarize",
        action="store_true",
        help="Identifier les locuteurs (whisperx) au lieu d'une simple transcription",
    )
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Nombre exact de locuteurs, si connu (avec --diarize)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Forcer la langue (ex. fr, en). Par défaut : détection automatique",
    )
    args = parser.parse_args()

    extra: dict = {"num_speakers": args.num_speakers} if args.diarize else {}
    if args.language and not args.diarize:
        extra["language"] = args.language

    try:
        text, output_path = transcribe_youtube(args.url, diarize=args.diarize, **extra)
    except (FileNotFoundError, ValueError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)

    print(text)
    print(f"\nTranscription enregistrée : {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
