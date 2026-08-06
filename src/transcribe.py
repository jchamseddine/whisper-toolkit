"""Transcription audio locale via mlx-whisper (macOS Apple Silicon)."""

import argparse
import os
import sys

DEFAULT_MODEL = "mlx-community/whisper-large-v3-mlx"
DEFAULT_LANGUAGE = "fr"
SUPPORTED_EXTENSIONS = (".mp3", ".wav", ".m4a", ".mp4")


def transcribe_file(
    audio_path: str,
    model: str = DEFAULT_MODEL,
    language: str = DEFAULT_LANGUAGE,
) -> str:
    """Transcrit un fichier audio et retourne le texte."""
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Fichier introuvable : {audio_path}")

    extension = os.path.splitext(audio_path)[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Extension non supportée : '{extension or 'aucune'}'. "
            f"Formats acceptés : {', '.join(SUPPORTED_EXTENSIONS)}."
        )

    # Import paresseux : mlx_whisper n'est installable que sur Apple Silicon.
    import mlx_whisper

    result = mlx_whisper.transcribe(
        audio_path, path_or_hf_repo=model, language=language
    )
    return result["text"]


def save_transcript(text: str, audio_path: str, output_dir: str = "output") -> str:
    """Écrit la transcription dans output_dir et retourne le chemin du fichier."""
    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    output_path = os.path.join(output_dir, f"{stem}.txt")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcrit un fichier audio en local via mlx-whisper."
    )
    parser.add_argument(
        "audio_path", help=f"Fichier audio à transcrire ({', '.join(SUPPORTED_EXTENSIONS)})"
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Modèle Whisper (défaut : {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--language", default=DEFAULT_LANGUAGE, help=f"Langue (défaut : {DEFAULT_LANGUAGE})"
    )
    args = parser.parse_args()

    try:
        text = transcribe_file(args.audio_path, model=args.model, language=args.language)
    except (FileNotFoundError, ValueError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)

    print(text)
    output_path = save_transcript(text, args.audio_path)
    print(f"\nTranscription enregistrée : {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
