"""Diarization (who speaks when) via whisperx.

A pipeline distinct from `transcribe.py`: whisperx builds on faster-whisper
(CTranslate2 backend), which has no Metal support — everything here therefore
runs on CPU, unlike mlx-whisper transcription.
"""

import argparse
import os
import sys

# whisperx calls `nltk.download('punkt_tab')` during alignment. By default NLTK
# writes to ~/nltk_data; we want the cache inside the repo.
#
# `NLTK_DATA` must be set BEFORE `import nltk`, and not merely topped up with a
# later `nltk.data.path.insert()`: at import time, nltk.downloader builds a
# `_downloader` singleton whose destination folder is frozen once and for all
# (`Downloader.__init__` → `default_download_dir()`). Changing `nltk.data.path`
# afterwards fixes *reading*, but no longer writing.
#
# The makedirs is not optional either: NLTK only keeps a path if it exists and
# is writable, and `.nltk_data/` is gitignored, hence absent from a clone.
_NLTK_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".nltk_data")
)
os.makedirs(_NLTK_DATA_DIR, exist_ok=True)
os.environ["NLTK_DATA"] = _NLTK_DATA_DIR

import nltk  # noqa: E402  -- must follow NLTK_DATA
from dotenv import load_dotenv  # noqa: E402

# Safety net: if another module already imported nltk, the environment variable
# arrived too late to populate `nltk.data.path`.
if _NLTK_DATA_DIR not in nltk.data.path:
    nltk.data.path.insert(0, _NLTK_DATA_DIR)

DEFAULT_MODEL = "large-v3"
DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"
TOKEN_ENV_VAR = "HF_TOKEN"
TOKENS_URL = "https://huggingface.co/settings/tokens"

# CTranslate2 supports neither Metal nor MPS: CPU is mandatory. int8 rather than
# the default float32, otherwise large-v3 on CPU is very slow.
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

MISSING_TOKEN_HELP = (
    f"Hugging Face token not found.\n"
    f"1. Create a token at {TOKENS_URL}\n"
    f"2. Put it in a .env file at the project root:\n"
    f"       {TOKEN_ENV_VAR}=hf_xxxxxxxxxxxxxxxx\n"
    f"   (or pass it as an argument to diarize_file)"
)


def _resolve_token(hf_token: str | None) -> str:
    """Return the supplied token, otherwise the one from .env."""
    if hf_token:
        return hf_token

    load_dotenv()
    token = os.getenv(TOKEN_ENV_VAR)
    if not token:
        raise ValueError(MISSING_TOKEN_HELP)

    return token


def _http_status(error: Exception) -> int | None:
    """Extract the HTTP code from a huggingface_hub error, if present."""
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status is not None:
        return status

    # pyannote sometimes rewraps the error and loses the `response` object.
    message = str(error)
    for code in (401, 403):
        if f"{code} Client Error" in message:
            return code

    return None


def _diarization_error_help(error: Exception, diarization_model: str) -> str:
    """Turn a pyannote loading failure into an actionable message.

    401 and 403 both surface as `GatedRepoError`, but call for opposite fixes:
    redo the token, or accept the terms.
    """
    status = _http_status(error)

    if status == 403:
        return (
            f"Access denied to model {diarization_model} (HTTP 403).\n"
            f"The token is valid, but this model's terms of use have not been\n"
            f"accepted on the account that holds it.\n"
            f"→ Accept them at https://huggingface.co/{diarization_model}\n"
            f"  (access is granted immediately), then run again."
        )

    if status == 401:
        return (
            f"Hugging Face token rejected (HTTP 401).\n"
            f"It is invalid, expired, or lacks the right to read gated\n"
            f"repositories.\n"
            f"→ Check or regenerate it at {TOKENS_URL},\n"
            f"  then update {TOKEN_ENV_VAR} in .env."
        )

    return (
        f"Failed to load diarization model {diarization_model}.\n"
        f"Detail: {error}"
    )


def diarize_file(
    audio_path: str,
    hf_token: str | None = None,
    model: str = DEFAULT_MODEL,
    num_speakers: int | None = None,
    diarization_model: str = DEFAULT_DIARIZATION_MODEL,
) -> list[dict]:
    """Transcribe, align and diarize an audio file.

    Returns a list of `{start, end, text, speaker}` segments.
    """
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"File not found: {audio_path}")

    token = _resolve_token(hf_token)

    # Lazy import: whisperx pulls in torch and pyannote, several seconds.
    import whisperx
    from whisperx.diarize import DiarizationPipeline

    audio = whisperx.load_audio(audio_path)

    asr_model = whisperx.load_model(model, DEVICE, compute_type=COMPUTE_TYPE)
    result = asr_model.transcribe(audio)

    align_model, metadata = whisperx.load_align_model(
        language_code=result["language"], device=DEVICE
    )
    result = whisperx.align(result["segments"], align_model, metadata, audio, DEVICE)

    try:
        diarize_pipeline = DiarizationPipeline(
            model_name=diarization_model, token=token, device=DEVICE
        )
    except Exception as error:
        # pyannote surfaces an HTTP error, or a None that breaks at .to(device).
        raise ValueError(_diarization_error_help(error, diarization_model)) from error

    diarize_segments = diarize_pipeline(audio, num_speakers=num_speakers)
    result = whisperx.assign_word_speakers(diarize_segments, result)

    return [
        {
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"].strip(),
            "speaker": segment.get("speaker", "UNKNOWN"),
        }
        for segment in result["segments"]
    ]


def diarized_transcript_path(audio_path: str, output_dir: str = "output") -> str:
    """Expected output path for `audio_path`, without writing anything.

    Counterpart of `transcribe.transcript_path()` for diarization mode: this is
    what lets `batch.py` detect an already-processed file.
    """
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    return os.path.join(output_dir, f"{stem}_diarized.txt")


def save_diarized_transcript(
    segments: list[dict], audio_path: str, output_dir: str = "output"
) -> str:
    """Write the speaker-labelled segments and return the file path."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = diarized_transcript_path(audio_path, output_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        for segment in segments:
            f.write(f"[{segment['speaker']}] {segment['text']}\n")

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcribe an audio file and identify its speakers (whisperx)."
    )
    parser.add_argument("audio_path", help="Audio file to diarize")
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Whisper model (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Exact number of speakers, if known (otherwise detected automatically)",
    )
    parser.add_argument(
        "--diarization-model",
        default=DEFAULT_DIARIZATION_MODEL,
        help=f"pyannote diarization model (default: {DEFAULT_DIARIZATION_MODEL})",
    )
    args = parser.parse_args()

    try:
        segments = diarize_file(
            args.audio_path,
            model=args.model,
            num_speakers=args.num_speakers,
            diarization_model=args.diarization_model,
        )
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    for segment in segments:
        print(f"[{segment['speaker']}] {segment['text']}")

    output_path = save_diarized_transcript(segments, args.audio_path)
    print(f"\nDiarized transcript saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
