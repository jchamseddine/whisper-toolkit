"""Summarizing a transcript via the Claude API.

A step distinct from transcription: this module takes a text file already
produced by `transcribe.py`, `diarize.py` or `batch.py`, never audio. It is also
the only module in the toolkit that leaves the machine — everything else runs
locally.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# Current Sonnet. `claude-opus-5` is more capable should the need arise:
# changing this constant, or passing --model, is enough.
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_STYLE = "concise"

API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"
CONSOLE_URL = "https://console.anthropic.com/settings/keys"

# A summary is short by nature; the bound is there to avoid a surprise bill if
# the model wanders off. Truncation is detected further down.
MAX_TOKENS = 4096

# Input guard, far below the model's context window (1M tokens, i.e. several
# million characters). Its purpose is not to protect the API but to turn an
# obscure remote refusal into a readable local error, before paying for the
# call. No chunking: outside current usage.
MAX_INPUT_CHARS = 150_000

MISSING_KEY_HELP = (
    f"Anthropic API key not found.\n"
    f"1. Create a key at {CONSOLE_URL}\n"
    f"2. Put it in a .env file at the project root:\n"
    f"       {API_KEY_ENV_VAR}=sk-ant-...\n"
    f"   (.env is already ignored by git)"
)

SYSTEM_PROMPT = """\
You summarize audio transcripts: meetings, lectures, interviews, voice notes.

The text comes from a speech recognition system. It may contain misheard words,
approximate punctuation and marks of speech (hesitations, repetitions,
interrupted sentences). Read through those flaws without commenting on them.
When the text is labelled by speaker — lines in `[SPEAKER_00]` — use that to
attribute statements, keeping those identifiers as they are: they correspond to
no known name.

Structure the summary as follows:
- an opening sentence saying what this is about;
- the key points, as a list;
- the decisions and action items worth keeping, if there are any — otherwise do
  not invent the section.

Rephrase in your own words rather than copying whole sentences. If a passage is
too degraded to be understood, say so instead of guessing.

Answer in English, whatever the language of the transcript, and give the summary
alone, with no preamble or comment about the task."""


def _resolve_api_key(api_key: str | None) -> str:
    """Return the supplied key, otherwise the one from .env."""
    if api_key:
        return api_key

    load_dotenv()
    key = os.getenv(API_KEY_ENV_VAR)
    if not key:
        raise ValueError(MISSING_KEY_HELP)

    return key


def _api_error_help(error: Exception) -> str:
    """Turn an API error into an actionable message.

    The exception text is reused as-is for unforeseen cases: the SDK never puts
    the key in it, only the code and the reason.
    """
    import anthropic

    if isinstance(error, anthropic.AuthenticationError):
        return (
            f"API key rejected (HTTP 401).\n"
            f"It is invalid, revoked, or mistyped in .env.\n"
            f"→ Check or regenerate it at {CONSOLE_URL}."
        )

    if isinstance(error, anthropic.PermissionDeniedError):
        return (
            f"Access denied (HTTP 403).\n"
            f"The key is valid but is not allowed to call this model.\n"
            f"→ Check the key's permissions at {CONSOLE_URL}."
        )

    if isinstance(error, anthropic.NotFoundError):
        return (
            f"Model not found (HTTP 404).\n"
            f"The requested id does not exist or is not accessible.\n"
            f"Detail: {error}"
        )

    if isinstance(error, anthropic.RateLimitError):
        return "Rate limit exceeded (HTTP 429). Wait a moment and run again."

    # Exhausted balance: surfaces as a 400, not a 401/403. The key is valid, so
    # without this case the message pointed at regenerating a key that has
    # nothing wrong with it.
    if "credit balance is too low" in str(error):
        return (
            "Insufficient credit balance on the Anthropic account (HTTP 400).\n"
            "The key is valid: it is the account that has run out of credits.\n"
            "→ Add credits under Plans & Billing on console.anthropic.com,\n"
            "  then run again."
        )

    if isinstance(error, anthropic.APIConnectionError):
        return (
            "Could not reach the Anthropic API.\n"
            "Check the network connection, then run again."
        )

    return f"Call to the Claude API failed.\nDetail: {error}"


def summarize_text(
    text: str,
    model: str = DEFAULT_MODEL,
    style: str = DEFAULT_STYLE,
    api_key: str | None = None,
) -> str:
    """Summarize a transcript and return the summary text."""
    if not text.strip():
        raise ValueError("Empty transcript: nothing to summarize.")

    if len(text) > MAX_INPUT_CHARS:
        raise ValueError(
            f"Transcript too long: {len(text):,} characters for a maximum of "
            f"{MAX_INPUT_CHARS:,}.\n"
            f"Split the file and summarize each part separately.".replace(",", " ")
        )

    key = _resolve_api_key(api_key)

    # Lazy import, as for whisperx and mlx_whisper: the rest of the toolkit
    # works without the `anthropic` package.
    import anthropic

    client = anthropic.Anthropic(api_key=key)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=f"{SYSTEM_PROMPT}\n\nExpected style for this summary: {style}.",
            messages=[{"role": "user", "content": text}],
        )
    except Exception as error:
        raise ValueError(_api_error_help(error)) from error

    if response.stop_reason == "refusal":
        raise ValueError(
            "The model refused to summarize this content.\n"
            "Nothing was produced; the transcript is unchanged."
        )

    summary = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    if response.stop_reason == "max_tokens":
        print(
            f"Warning: summary truncated at {MAX_TOKENS} tokens.",
            file=sys.stderr,
        )

    return summary


def summary_path(transcript_path: str, output_dir: str = "output") -> str:
    """Expected output path for `transcript_path`, without writing anything.

    Counterpart of `transcribe.transcript_path()`: this is what lets `cli.py`
    know a summary already exists, and therefore not pay for an API call to
    redo it.
    """
    stem = os.path.splitext(os.path.basename(transcript_path))[0]
    return os.path.join(output_dir, f"{stem}_summary.txt")


def save_summary(summary: str, audio_path: str, output_dir: str = "output") -> str:
    """Write the summary into output_dir and return the file path."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = summary_path(audio_path, output_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(summary)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize an already-produced transcript, via the Claude API."
    )
    parser.add_argument(
        "transcript_path", help="Text file to summarize (not an audio file)"
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Claude model (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--style",
        default=DEFAULT_STYLE,
        help=f"Summary style, in plain words (default: {DEFAULT_STYLE})",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.transcript_path):
        print(f"Error: file not found: {args.transcript_path}", file=sys.stderr)
        sys.exit(1)

    with open(args.transcript_path, encoding="utf-8") as f:
        text = f.read()

    try:
        summary = summarize_text(text, model=args.model, style=args.style)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    print(summary)

    output_path = save_summary(summary, args.transcript_path)
    print(f"\nSummary saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
