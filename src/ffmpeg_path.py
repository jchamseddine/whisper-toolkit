"""Locating ffmpeg, without depending on the PATH inherited at launch.

The whole toolkit leans on ffmpeg: `mlx_whisper` and `whisperx` call it as a
subprocess to decode audio, yt-dlp to extract the track. All of them look it up
in `PATH`, and that is where things break.

An interactive shell loads `~/.zshrc`, and therefore `/opt/homebrew/bin`. An
Automator app, a `launchd` job, a Finder shortcut: they do not. The process
inherits a minimal PATH (`/usr/bin:/bin:/usr/sbin:/sbin`) that has no ffmpeg in
it, even though ffmpeg is installed and works perfectly. Hence a failure that
only ever happens on a graphical launch, never from the terminal.

This module does nothing but find the binary. It is deliberately a lookup, not
an abstraction over ffmpeg.
"""

import os
import shutil

# Homebrew locations, Apple Silicon then Intel. Consulted only when the
# process PATH turned up nothing: PATH stays the authority, these paths are the
# safety net.
FALLBACK_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")


def find_ffmpeg() -> str | None:
    """Return the path to the ffmpeg executable, or None if it cannot be found."""
    found = shutil.which("ffmpeg")
    if found:
        return found

    for directory in FALLBACK_DIRS:
        candidate = os.path.join(directory, "ffmpeg")
        if os.access(candidate, os.X_OK):
            return candidate

    return None


def ensure_on_path() -> str | None:
    """Add ffmpeg's directory to the process PATH. Return its path.

    Returns `None` if ffmpeg is still nowhere to be found — reporting that is
    the caller's job.

    Going through PATH rather than an argument is the only route here:
    `mlx_whisper` and `whisperx` invoke `ffmpeg` by its bare name, with no
    parameter to point at it. Unlike yt-dlp, which `youtube.py` hands the path
    explicitly (`ffmpeg_location`) and which therefore needs none of this.

    Mutating `os.environ` is a deliberate side effect: it is what subprocesses
    inherit, and that is exactly what we are repairing. The call is idempotent.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None

    directory = os.path.dirname(ffmpeg)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if directory not in parts:
        os.environ["PATH"] = os.pathsep.join([directory, *parts])

    return ffmpeg
