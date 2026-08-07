"""Local audio transcription via mlx-whisper (macOS Apple Silicon)."""

import argparse
import os
import sys

DEFAULT_MODEL = "mlx-community/whisper-large-v3-mlx"
# mlx_whisper decodes through ffmpeg (`-ac 1 -ar 16000`), so any format ffmpeg
# reads will do: the conversion to 16 kHz mono already happens internally.
SUPPORTED_EXTENSIONS = (".mp3", ".wav", ".m4a", ".mp4", ".opus", ".ogg")


def transcribe_file(
    audio_path: str,
    model: str = DEFAULT_MODEL,
    language: str | None = None,
) -> str:
    """Transcribe an audio file and return the text.

    `language=None` lets Whisper detect the language. Forcing a language on a
    file in another language does not raise an error — it produces an invented
    translation, fluent and plausible, a flaw invisible in the output. Detection
    costs a fixed amount (~0.3 s, one pass over the first window), not something
    proportional to the duration.
    """
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"File not found: {audio_path}")

    extension = os.path.splitext(audio_path)[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported extension: '{extension or 'none'}'. "
            f"Accepted formats: {', '.join(SUPPORTED_EXTENSIONS)}."
        )

    # Lazy import: mlx_whisper only installs on Apple Silicon.
    import mlx_whisper

    result = mlx_whisper.transcribe(
        audio_path, path_or_hf_repo=model, language=language
    )
    return result["text"]


def transcript_path(audio_path: str, output_dir: str = "output") -> str:
    """Expected output path for `audio_path`, without writing anything.

    Single source of the naming convention: `batch.py` relies on it to tell
    whether a file has already been processed, and must stay in agreement with
    `save_transcript()` even if the convention changes.
    """
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    return os.path.join(output_dir, f"{stem}.txt")


def save_transcript(text: str, audio_path: str, output_dir: str = "output") -> str:
    """Write the transcript into output_dir and return the file path."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = transcript_path(audio_path, output_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcribe an audio file locally via mlx-whisper."
    )
    parser.add_argument(
        "audio_path", help=f"Audio file to transcribe ({', '.join(SUPPORTED_EXTENSIONS)})"
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Whisper model (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Force the language (e.g. fr, en). Default: auto-detect",
    )
    args = parser.parse_args()

    try:
        text = transcribe_file(args.audio_path, model=args.model, language=args.language)
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    print(text)
    output_path = save_transcript(text, args.audio_path)
    print(f"\nTranscript saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
