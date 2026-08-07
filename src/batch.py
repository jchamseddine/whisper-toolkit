"""Batch processing: transcribe (or diarize) every file in a folder.

Holds no transcription logic of its own: it orchestrates `transcribe.py` and
`diarize.py`. Imports are flat because this module runs as a script
(`python src/batch.py`), which puts `src/` at the front of `sys.path`.
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


def short_reason(reason: str, limit: int = 160) -> str:
    """Reduce an error to a single displayable line.

    ffmpeg spits out its entire build banner when it fails: without this, one
    failing file drowns the whole batch summary. The full error stays in the
    dict returned by `process_folder`.

    Public for the same reason as `report_summary()`: the web interface's
    failure table needs it too, and this formatting has a single definition.
    """
    first_line = reason.splitlines()[0].strip()
    if len(first_line) > limit:
        return first_line[:limit].rstrip() + "…"
    return first_line


def list_audio_files(folder_path: str) -> list[str]:
    """Return the folder's audio files, sorted by name."""
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"Folder not found: {folder_path}")

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
    """Process every audio file in a folder.

    `language` only concerns transcription: when diarizing, whisperx detects the
    language on its own, file by file.

    Resuming is the default: a file whose output already exists is skipped,
    which is what lets an interrupted batch be restarted without redoing
    everything. `force=True` reprocesses everything. The presence of the output
    file is the only criterion — its content is never inspected.

    A failing file does not interrupt the batch. Returns
    `{"success": [paths], "failed": [(path, error)], "skipped": [paths]}`.
    """
    audio_files = list_audio_files(folder_path)
    total = len(audio_files)
    summary: dict = {"success": [], "failed": [], "skipped": []}

    if not total:
        print(f"No audio file in {folder_path}", file=sys.stderr)
        return summary

    for index, audio_path in enumerate(audio_files, start=1):
        print(f"[{index}/{total}] {os.path.basename(audio_path)}", file=sys.stderr)

        # The path is asked of the modules that write it, so that resume
        # detection automatically follows any change of convention.
        expected_output = (
            diarized_transcript_path(audio_path)
            if diarize
            else transcript_path(audio_path)
        )
        if not force and os.path.isfile(expected_output):
            summary["skipped"].append(audio_path)
            print(f"        skipped — already done: {expected_output}", file=sys.stderr)
            continue

        try:
            if diarize:
                segments = diarize_file(audio_path, num_speakers=num_speakers)
                output_path = save_diarized_transcript(segments, audio_path)
            else:
                text = transcribe_file(audio_path, language=language)
                output_path = save_transcript(text, audio_path)
        except Exception as error:
            # Deliberately broad: the point of a batch is to reach the end,
            # whatever way a single file fails.
            summary["failed"].append((audio_path, f"{type(error).__name__}: {error}"))
            print(f"        failed — {type(error).__name__}", file=sys.stderr)
            continue

        summary["success"].append(audio_path)
        print(f"        → {output_path}", file=sys.stderr)

    processed = len(summary["success"]) + len(summary["failed"])
    print(
        f"\n{len(summary['success'])}/{processed} files processed"
        f" ({len(summary['skipped'])} skipped out of {total})",
        file=sys.stderr,
    )
    return summary


def report_summary(summary: dict) -> None:
    """Print a batch report on stdout.

    Separate from `main()` because `cli.py` produces the same report: the
    batch display format has a single definition. Does not decide the exit
    code — that is the caller's job, from `summary["failed"]`.
    """
    print(f"Succeeded: {len(summary['success'])}")

    if summary["skipped"]:
        print(f"Skipped: {len(summary['skipped'])} (already done — --force to redo)")
        for path in summary["skipped"]:
            print(f"  - {os.path.basename(path)}")

    if summary["failed"]:
        print(f"Failed: {len(summary['failed'])}")
        for path, reason in summary["failed"]:
            print(f"  - {os.path.basename(path)}: {short_reason(reason)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcribe every audio file in a folder."
    )
    parser.add_argument("folder_path", help="Folder containing the audio files")
    parser.add_argument(
        "--diarize",
        action="store_true",
        help="Identify speakers (whisperx) instead of a plain transcription",
    )
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Exact number of speakers, if known (with --diarize)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess files whose output already exists "
        "(default: resume, those files are skipped)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Force the language (e.g. fr, en), no effect with --diarize. "
        "Default: auto-detect",
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
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    report_summary(summary)

    if summary["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
