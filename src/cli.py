"""Unified CLI: one command, one subcommand per input mode.

A pure orchestration layer, just like `batch.py`: no transcription, diarization,
download or summarization logic is written here. Each subcommand calls the
functions of the modules that carry them, then displays what they produced.

Imports are flat because this module runs as a script (`python src/cli.py`),
which puts `src/` at the front of `sys.path`.

Sibling modules are imported **inside** the functions that need them, not at the
top of the file: importing `youtube` pulls in yt-dlp, and `diarize`/`batch` pull
in nltk, i.e. ~0.7 s paid on every launch — including for `--help` or for a
summary, which have no use for it. Same reason as the lazy imports of
`mlx_whisper`, `whisperx` and `anthropic` elsewhere in the toolkit.
"""

import argparse
import os
import sys

# `transcribe` is free to import (stdlib only, mlx_whisper is lazy) and
# `summarize` only pulls in dotenv; their constants are needed as early as
# parser construction.
from summarize import DEFAULT_MODEL as DEFAULT_SUMMARY_MODEL
from summarize import DEFAULT_STYLE, save_summary, summarize_text, summary_path
from transcribe import (
    SUPPORTED_EXTENSIONS,
    save_transcript,
    transcribe_file,
    transcript_path,
)


def _warn_ignored_options(args: argparse.Namespace) -> None:
    """Warn when an option will have no effect in the requested mode.

    The three audio inputs share the same set of options, but not all of them
    apply to both modes. A warning beats a silently ignored parameter.
    """
    if args.num_speakers is not None and not args.diarize:
        print("Warning: --num-speakers is ignored without --diarize.", file=sys.stderr)

    if args.language and args.diarize:
        print(
            "Warning: --language is ignored with --diarize "
            "(whisperx detects the language itself).",
            file=sys.stderr,
        )


def _show_transcript(output_path: str) -> None:
    """Display the transcript exactly as it was just written.

    Re-reading the file rather than reformatting the in-memory segments avoids
    redefining the `[SPEAKER_XX] text` format here, which belongs to
    `diarize.py`.
    """
    with open(output_path, encoding="utf-8") as f:
        print(f.read().rstrip("\n"))

    print(f"\nTranscript saved: {output_path}", file=sys.stderr)


def _summarize_transcript(transcript_file: str, model: str, style: str) -> str:
    """Summarize a transcript file and write the summary next to it."""
    with open(transcript_file, encoding="utf-8") as f:
        text = f.read()

    summary = summarize_text(text, model=model, style=style)
    print(summary)

    output_path = save_summary(summary, transcript_file)
    print(f"\nSummary saved: {output_path}", file=sys.stderr)
    return output_path


def summarize_batch(
    summary: dict,
    diarize: bool = False,
    force: bool = False,
    model: str = DEFAULT_SUMMARY_MODEL,
    style: str = DEFAULT_STYLE,
) -> int:
    """Summarize a batch's transcripts. Returns the number of failures.

    Files skipped by the resume logic are included: their transcript exists, so
    it can be summarized — without that, a resumed batch would only summarize
    the files that remained to be processed. A summary already present is in
    turn skipped, unless `force`: every API call costs money.

    A failing summary does not interrupt the series, as for the batch itself.

    Takes explicit parameters rather than argparse's `Namespace`, like
    `batch.report_summary()`: that is what makes it callable from `app.py`,
    which has no command line to hand it. The summary resume rule therefore has
    a single definition, valid for both entry points.
    """
    from diarize import diarized_transcript_path

    path_of = diarized_transcript_path if diarize else transcript_path
    transcripts = sorted(path_of(path) for path in summary["success"] + summary["skipped"])

    failed = 0
    for transcript_file in transcripts:
        expected_summary = summary_path(transcript_file)
        if not force and os.path.isfile(expected_summary):
            print(f"Summary skipped — already present: {expected_summary}", file=sys.stderr)
            continue

        print(f"\nSummary of {os.path.basename(transcript_file)}", file=sys.stderr)
        try:
            _summarize_transcript(transcript_file, model, style)
        except ValueError as error:
            failed += 1
            print(f"Error: {error}", file=sys.stderr)

    return failed


def _run_transcribe(args: argparse.Namespace) -> int:
    _warn_ignored_options(args)

    if args.diarize:
        from diarize import diarize_file, save_diarized_transcript

        segments = diarize_file(args.audio_path, num_speakers=args.num_speakers)
        output_path = save_diarized_transcript(segments, args.audio_path)
    else:
        text = transcribe_file(args.audio_path, language=args.language)
        output_path = save_transcript(text, args.audio_path)

    _show_transcript(output_path)

    if args.summarize:
        _summarize_transcript(output_path, args.summary_model, args.summary_style)

    return 0


def _run_batch(args: argparse.Namespace) -> int:
    _warn_ignored_options(args)

    from batch import process_folder, report_summary

    summary = process_folder(
        args.folder_path,
        diarize=args.diarize,
        num_speakers=args.num_speakers,
        force=args.force,
        language=args.language,
    )
    report_summary(summary)
    exit_code = 1 if summary["failed"] else 0

    if args.summarize and summarize_batch(
        summary,
        diarize=args.diarize,
        force=args.force,
        model=args.summary_model,
        style=args.summary_style,
    ):
        exit_code = 1

    return exit_code


def _run_youtube(args: argparse.Namespace) -> int:
    _warn_ignored_options(args)

    from youtube import transcribe_youtube

    # `transcribe_youtube` routes its kwargs to `diarize_file()` or
    # `transcribe_file()` depending on the mode: they are not interchangeable.
    extra: dict = {"num_speakers": args.num_speakers} if args.diarize else {}
    if args.language and not args.diarize:
        extra["language"] = args.language

    _, output_path = transcribe_youtube(args.url, diarize=args.diarize, **extra)
    _show_transcript(output_path)

    if args.summarize:
        _summarize_transcript(output_path, args.summary_model, args.summary_style)

    return 0


def _run_summarize(args: argparse.Namespace) -> int:
    if not os.path.isfile(args.transcript_path):
        raise FileNotFoundError(f"File not found: {args.transcript_path}")

    _summarize_transcript(args.transcript_path, args.model, args.style)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    # `prog` is the command actually typed: the toolkit is not installed as an
    # executable, see README ("Why not an installed command").
    parser = argparse.ArgumentParser(
        prog="python src/cli.py",
        description="Local audio transcription: a file, a folder or a YouTube URL.",
        epilog=(
            "Examples:\n"
            "  python src/cli.py transcribe lecture.m4a\n"
            "  python src/cli.py transcribe meeting.wav --diarize --num-speakers 3 --summarize\n"
            "  python src/cli.py batch my-lectures/ --language fr\n"
            "  python src/cli.py youtube 'https://youtu.be/...' --summarize\n"
            "  python src/cli.py summarize output/lecture.txt --style 'in three bullets'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Options common to the three audio inputs. A single parent parser rather
    # than three copies: an option added here is added everywhere at once.
    audio = argparse.ArgumentParser(add_help=False)
    audio.add_argument(
        "--diarize",
        action="store_true",
        help="Identify speakers (whisperx) instead of a plain transcription",
    )
    audio.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Exact number of speakers, if known (with --diarize)",
    )
    audio.add_argument(
        "--language",
        default=None,
        help="Force the language (e.g. fr, en), no effect with --diarize. "
        "Default: auto-detect",
    )
    audio.add_argument(
        "--summarize",
        action="store_true",
        help="Chain a summary of the transcript via the Claude API (paid call)",
    )
    audio.add_argument(
        "--summary-model",
        default=DEFAULT_SUMMARY_MODEL,
        help=f"Claude model for --summarize (default: {DEFAULT_SUMMARY_MODEL})",
    )
    audio.add_argument(
        "--summary-style",
        default=DEFAULT_STYLE,
        help=f"Summary style, in plain words (default: {DEFAULT_STYLE})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    transcribe_parser = subparsers.add_parser(
        "transcribe",
        parents=[audio],
        help="Transcribe an audio file",
        description="Transcribe an audio file locally.",
    )
    transcribe_parser.add_argument(
        "audio_path",
        help=f"Audio file to transcribe ({', '.join(SUPPORTED_EXTENSIONS)})",
    )
    transcribe_parser.set_defaults(handler=_run_transcribe)

    batch_parser = subparsers.add_parser(
        "batch",
        parents=[audio],
        help="Transcribe every audio file in a folder",
        description="Transcribe every audio file in a folder, resuming where a "
        "previous batch stopped.",
    )
    batch_parser.add_argument("folder_path", help="Folder containing the audio files")
    batch_parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess files whose output already exists, summaries included "
        "(default: resume, those files are skipped)",
    )
    batch_parser.set_defaults(handler=_run_batch)

    youtube_parser = subparsers.add_parser(
        "youtube",
        parents=[audio],
        help="Transcribe the audio of a YouTube video",
        description="Download the audio of a YouTube video, then transcribe it.",
    )
    youtube_parser.add_argument("url", help="Video URL")
    youtube_parser.set_defaults(handler=_run_youtube)

    summarize_parser = subparsers.add_parser(
        "summarize",
        help="Summarize an already-produced transcript",
        description="Summarize an already-produced transcript, via the Claude API. "
        "Takes a text file, never audio.",
    )
    summarize_parser.add_argument(
        "transcript_path", help="Text file to summarize (not an audio file)"
    )
    summarize_parser.add_argument(
        "--model",
        default=DEFAULT_SUMMARY_MODEL,
        help=f"Claude model (default: {DEFAULT_SUMMARY_MODEL})",
    )
    summarize_parser.add_argument(
        "--style",
        default=DEFAULT_STYLE,
        help=f"Summary style, in plain words (default: {DEFAULT_STYLE})",
    )
    summarize_parser.set_defaults(handler=_run_summarize)

    return parser


def main() -> None:
    args = _build_parser().parse_args()

    try:
        exit_code = args.handler(args)
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        # The same exceptions the modules' own CLIs intercept: they already
        # carry an actionable message, not a traceback.
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
