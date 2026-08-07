"""Traitement par lot : transcrit (ou diarise) tous les fichiers d'un dossier.

Ne contient aucune logique de transcription propre : orchestre `transcribe.py`
et `diarize.py`. Les imports sont plats parce que ce module s'exécute comme un
script (`python src/batch.py`), ce qui place `src/` en tête de `sys.path`.
"""

import argparse
import os
import sys

from diarize import diarize_file, diarized_transcript_path, save_diarized_transcript
from transcribe import (
    SUPPORTED_EXTENSIONS,
    save_transcript,
    transcribe_file,
    transcript_path,
)


def _short_reason(reason: str, limit: int = 160) -> str:
    """Réduit une erreur à une ligne affichable.

    ffmpeg recrache sa bannière de compilation complète en cas d'échec : sans
    ça, un seul fichier en erreur noie tout le résumé du lot. L'erreur entière
    reste dans le dict retourné par `process_folder`.
    """
    first_line = reason.splitlines()[0].strip()
    if len(first_line) > limit:
        return first_line[:limit].rstrip() + "…"
    return first_line


def list_audio_files(folder_path: str) -> list[str]:
    """Retourne les fichiers audio du dossier, triés par nom."""
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"Dossier introuvable : {folder_path}")

    paths = []
    for name in sorted(os.listdir(folder_path)):
        path = os.path.join(folder_path, name)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
            paths.append(path)

    return paths


def process_folder(
    folder_path: str,
    diarize: bool = False,
    num_speakers: int | None = None,
    force: bool = False,
    language: str | None = None,
) -> dict:
    """Traite tous les fichiers audio d'un dossier.

    `language` ne concerne que la transcription : en diarisation, whisperx
    détecte la langue de son côté, fichier par fichier.

    Reprise par défaut : un fichier dont la sortie existe déjà est sauté, ce
    qui permet de relancer un lot interrompu sans tout refaire. `force=True`
    retraite tout. La présence du fichier de sortie est le seul critère — son
    contenu n'est pas inspecté.

    Un fichier en échec n'interrompt pas le lot. Retourne
    `{"success": [chemins], "failed": [(chemin, erreur)], "skipped": [chemins]}`.
    """
    audio_files = list_audio_files(folder_path)
    total = len(audio_files)
    summary: dict = {"success": [], "failed": [], "skipped": []}

    if not total:
        print(f"Aucun fichier audio dans {folder_path}", file=sys.stderr)
        return summary

    for index, audio_path in enumerate(audio_files, start=1):
        print(f"[{index}/{total}] {os.path.basename(audio_path)}", file=sys.stderr)

        # Chemin demandé aux modules qui l'écrivent, pour que la détection de
        # reprise suive automatiquement tout changement de convention.
        expected_output = (
            diarized_transcript_path(audio_path)
            if diarize
            else transcript_path(audio_path)
        )
        if not force and os.path.isfile(expected_output):
            summary["skipped"].append(audio_path)
            print(f"        sauté — déjà traité : {expected_output}", file=sys.stderr)
            continue

        try:
            if diarize:
                segments = diarize_file(audio_path, num_speakers=num_speakers)
                output_path = save_diarized_transcript(segments, audio_path)
            else:
                text = transcribe_file(audio_path, language=language)
                output_path = save_transcript(text, audio_path)
        except Exception as error:
            # Volontairement large : le but du lot est d'arriver au bout, quelle
            # que soit la façon dont un fichier échoue.
            summary["failed"].append((audio_path, f"{type(error).__name__}: {error}"))
            print(f"        échec — {type(error).__name__}", file=sys.stderr)
            continue

        summary["success"].append(audio_path)
        print(f"        → {output_path}", file=sys.stderr)

    processed = len(summary["success"]) + len(summary["failed"])
    print(
        f"\n{len(summary['success'])}/{processed} fichiers traités"
        f" ({len(summary['skipped'])} sautés sur {total})",
        file=sys.stderr,
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcrit tous les fichiers audio d'un dossier."
    )
    parser.add_argument("folder_path", help="Dossier contenant les fichiers audio")
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
        "--force",
        action="store_true",
        help="Retraiter les fichiers dont la sortie existe déjà "
        "(par défaut : reprise, ces fichiers sont sautés)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Forcer la langue (ex. fr, en), sans effet avec --diarize. "
        "Par défaut : détection automatique",
    )
    args = parser.parse_args()

    try:
        summary = process_folder(
            args.folder_path,
            diarize=args.diarize,
            num_speakers=args.num_speakers,
            force=args.force,
            language=args.language,
        )
    except NotADirectoryError as error:
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)

    print(f"Succès : {len(summary['success'])}")

    if summary["skipped"]:
        print(f"Sautés : {len(summary['skipped'])} (déjà traités — --force pour refaire)")
        for path in summary["skipped"]:
            print(f"  - {os.path.basename(path)}")

    if summary["failed"]:
        print(f"Échecs : {len(summary['failed'])}")
        for path, reason in summary["failed"]:
            print(f"  - {os.path.basename(path)} : {_short_reason(reason)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
