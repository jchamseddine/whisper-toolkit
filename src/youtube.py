"""Transcription from a YouTube URL.

Holds no transcription logic: it downloads the audio with yt-dlp, then delegates
to `transcribe.py` or `diarize.py`. Imports are flat for the same reason as in
`batch.py` — this module runs as a script.
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

# Downloaded files land in test-audio/, already ignored by git: content pulled
# from YouTube has no business in the repository.
DEFAULT_AUDIO_DIR = "test-audio"

# Format chosen after measurement, see README (Test 7). YouTube natively serves
# an Opus stream that yt-dlp extracts with `-acodec copy`, so without
# re-encoding: ~1 MB per minute, against ~11 MB as wav. `.opus` is already in
# SUPPORTED_EXTENSIONS. Changing this constant is enough to switch to "m4a" or
# "wav".
AUDIO_FORMAT = "opus"
FORMAT_SELECTOR = f"bestaudio[acodec={AUDIO_FORMAT}]/bestaudio/best"

# Beyond that, names become unmanageable on the command line. YouTube titles
# regularly exceed this length.
MAX_STEM_LENGTH = 80


class _QuietLogger:
    """Swallows yt-dlp's output.

    `quiet` does not cover errors: yt-dlp writes them to stderr regardless.
    Since `_download_error_help()` then rephrases them, without this logger the
    user sees the raw message *and* the clear one.
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
    """Predictable file name from the title, falling back to the video id.

    The title is transliterated to ASCII: accents become their base letter, and
    anything that is neither a letter nor a digit becomes `_`. A title that is
    entirely non-Latin (Japanese, Arabic…) or made of punctuation leaves nothing
    usable — hence the fallback to the video id, which is always a valid ASCII
    slug.
    """
    ascii_title = (
        unicodedata.normalize("NFKD", title or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    stem = re.sub(r"[^A-Za-z0-9]+", "_", ascii_title).strip("_")[:MAX_STEM_LENGTH]
    return stem.strip("_") or video_id


def _download_error_help(error: Exception, url: str) -> str:
    """Turn a yt-dlp failure into an actionable message.

    yt-dlp surfaces nearly everything as a `DownloadError` carrying free text:
    that message is what has to be inspected to tell the cases apart.
    """
    message = str(error)
    lowered = message.lower()

    if "private video" in lowered or "sign in" in lowered:
        return f"Private video: {url}\nIt is not reachable without an authorised account."

    if "not available in your country" in lowered or (
        "geo" in lowered and "block" in lowered
    ):
        return (
            f"Video blocked in this region: {url}\n"
            f"YouTube denies access from the current IP address."
        )

    if "unsupported url" in lowered or "is not a valid url" in lowered:
        return f"URL not handled by yt-dlp: {url}"

    if "video unavailable" in lowered or "removed" in lowered or "terminated" in lowered:
        return (
            f"Video unavailable: {url}\n"
            f"It has been deleted, made private, or the id is wrong."
        )

    return f"Failed to download {url}\nDetail: {message}"


def download_audio(url: str, output_dir: str = DEFAULT_AUDIO_DIR) -> str:
    """Download the audio track of a YouTube URL and return its path.

    The file is named after the video title, cleaned up to serve as a file name.
    Two videos with the same title therefore overwrite the same file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # First call without downloading: the title is needed to build the output
    # name, and therefore to know the final path before writing.
    probe_options = {
        "quiet": True,
        "no_warnings": True,
        "logger": _QuietLogger(),
        # A `watch?v=…&list=…` URL designates a video, not the playlist that
        # contains it — that is the shape you get when copying from YouTube.
        "noplaylist": True,
        # `True` would flatten the single video too, which would lose its title
        # and fall back to the id. `in_playlist` only flattens the contents of a
        # playlist: we detect one without resolving each of its entries.
        "extract_flat": "in_playlist",
    }
    try:
        with yt_dlp.YoutubeDL(probe_options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as error:
        raise ValueError(_download_error_help(error, url)) from error

    # `noplaylist` does not cover pure playlist URLs, which have no single video
    # to isolate. Without this guard, the videos would all download under the
    # same name and overwrite each other, and only the last one would be
    # transcribed — under the playlist's title.
    if info.get("_type") == "playlist" or info.get("entries"):
        count = len(info.get("entries") or [])
        raise ValueError(
            f"Playlist URL ({count} videos): {url}\n"
            f"youtube.py handles one video at a time. Pass a video URL."
        )

    stem = _safe_stem(info.get("title", ""), info.get("id", "video"))
    audio_path = os.path.join(output_dir, f"{stem}.{AUDIO_FORMAT}")

    duration = info.get("duration")
    print(
        f"Downloading: {info.get('title', '?')}"
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

    # The path is given explicitly rather than left to PATH: launched anywhere
    # other than from an interactive shell — an Automator app, for instance —
    # the process has no `/opt/homebrew/bin` and yt-dlp fails in
    # post-processing with "ffprobe and ffmpeg not found", even though ffmpeg is
    # installed. We pass the **directory**, not the binary: audio extraction
    # also needs ffprobe, which yt-dlp looks for next to it.
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
            f"Download finished without producing {audio_path}.\n"
            f"The requested format ({AUDIO_FORMAT}) may not have been available."
        )

    return audio_path


def transcribe_youtube(url: str, diarize: bool = False, **kwargs) -> tuple[str, str]:
    """Download a video then transcribe it, with or without speakers.

    Returns `(text, output path)`. The name of the file produced depends on the
    video title, known only here: without returning it, a caller that wants to
    chain onto the transcript — `cli.py --summarize` — cannot find it. The
    `kwargs` are forwarded to `diarize_file()` or `transcribe_file()` depending
    on the mode — they are not interchangeable.
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
        description="Transcribe the audio of a YouTube video."
    )
    parser.add_argument("url", help="Video URL")
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
        "--language",
        default=None,
        help="Force the language (e.g. fr, en). Default: auto-detect",
    )
    args = parser.parse_args()

    extra: dict = {"num_speakers": args.num_speakers} if args.diarize else {}
    if args.language and not args.diarize:
        extra["language"] = args.language

    try:
        text, output_path = transcribe_youtube(args.url, diarize=args.diarize, **extra)
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    print(text)
    print(f"\nTranscript saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
