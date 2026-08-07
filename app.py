"""Streamlit web interface, alongside the CLI — not in its place.

An exact counterpart of `cli.py`: no transcription, diarization, download or
summarization logic is written here. Each tab calls the functions of the modules
that carry them, then displays what they produced. Both entry points therefore
share the same business code, and outputs land in the same place (`output/`),
under the same names.

One deliberate exception: the "Quick dictation" tab, which has no CLI equivalent
and writes nothing — neither the audio nor the text, unless explicitly asked.
See `_transcribe_recording()`.

Run with: `streamlit run app.py` from the repository root.
"""

import hashlib
import os
import sys
import tempfile
from datetime import datetime

# `python src/cli.py` puts `src/` at the front of `sys.path`, which is what
# makes the toolkit modules' flat imports (`from transcribe import …`) work.
# `streamlit run app.py` puts the repository root there instead: without this
# addition, no module from `src/` is importable.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import streamlit as st  # noqa: E402  -- must follow the src/ addition to sys.path

# Same rule as at the top of `cli.py`: only free imports happen here.
# `transcribe` costs nothing (mlx_whisper is lazy) and its constant is needed as
# early as the uploader's construction. Everything else — `diarize`, `batch`,
# `youtube`, `summarize` — is imported inside the functions that use it,
# otherwise every Streamlit rerun would pay for nltk and yt-dlp just to display
# a few tabs.
from ffmpeg_path import ensure_on_path  # noqa: E402
from transcribe import SUPPORTED_EXTENSIONS  # noqa: E402

# Allowed root for the batch tab's "folder" field. That field accepts a
# hand-typed path: with no bound, merely exposing the app on the network would
# let anyone list and transcribe any folder on the machine. The intended use is
# local, but the guard rail is put in now rather than later.
# `WHISPER_TOOLKIT_ROOT` widens the root deliberately (e.g. `~/Documents/courses`).
BROWSE_ROOT = os.path.realpath(os.environ.get("WHISPER_TOOLKIT_ROOT", PROJECT_ROOT))

LANGUAGE_HELP = (
    "Leave this on “Auto-detect” unless you have a precise need: forcing a "
    "language that is not the audio's does not raise an error, it produces an "
    "invented translation, fluent and undetectable in the output. "
    "Type to filter the list."
)

# Languages of the selector, Whisper code as the value. `None` leaves detection
# automatic, which stays the default everywhere in the toolkit.
#
# This is a common subset, not the 100 languages Whisper knows. The full list is
# only readable in `mlx_whisper.tokenizer.LANGUAGES`, which only installs on
# Apple Silicon: pulling it from there would make the app undisplayable
# elsewhere — and cost 0.8 s at startup — for a dropdown. Adding a language here
# takes one line, and the CLI stays open to any Whisper code via `--language`.
#
# The codes were checked one by one against `mlx_whisper.tokenizer.LANGUAGES`.
LANGUAGES: dict[str, str | None] = {
    "Auto-detect": None,
    "French": "fr",
    "English": "en",
    "Spanish": "es",
    "German": "de",
    "Italian": "it",
    "Portuguese": "pt",
    "Dutch": "nl",
    "Arabic": "ar",
    "Catalan": "ca",
    "Chinese": "zh",
    "Korean": "ko",
    "Danish": "da",
    "Finnish": "fi",
    "Greek": "el",
    "Hebrew": "he",
    "Hindi": "hi",
    "Hungarian": "hu",
    "Indonesian": "id",
    "Japanese": "ja",
    "Norwegian": "no",
    "Polish": "pl",
    "Romanian": "ro",
    "Russian": "ru",
    "Swedish": "sv",
    "Czech": "cs",
    "Thai": "th",
    "Turkish": "tr",
    "Ukrainian": "uk",
    "Vietnamese": "vi",
}


def _resolve_browse_path(raw: str) -> str:
    """Resolve a typed path and refuse anything outside `BROWSE_ROOT`.

    Relative paths start from the allowed root; an absolute path is kept as-is
    by `os.path.join`, then rejected by the containment test. `realpath` is
    indispensable: it resolves `..` and symbolic links, so a link placed in the
    repository cannot serve as a gateway to `/`.
    """
    candidate = raw.strip()
    if not candidate:
        raise ValueError("Give a folder to process.")

    resolved = os.path.realpath(
        os.path.join(BROWSE_ROOT, os.path.expanduser(candidate))
    )
    if resolved != BROWSE_ROOT and not resolved.startswith(BROWSE_ROOT + os.sep):
        raise ValueError(
            f"Path outside the allowed root: {resolved}\n"
            f"Only {BROWSE_ROOT} and its subfolders are reachable. "
            f"Set WHISPER_TOOLKIT_ROOT before launching the app to widen it."
        )

    return resolved


def _save_upload(uploaded, directory: str) -> str:
    """Write the received file into `directory` and return its path.

    The name comes from the browser, hence from the outside: it is reduced to
    its basename, otherwise a name like `../../x.wav` would write outside the
    temporary directory. It is otherwise preserved, because it is what gives the
    output its name (`output/{name}.txt`) — exactly as in the CLI.
    """
    name = os.path.basename(uploaded.name.replace("\\", "/"))
    if not name or name in {".", ".."}:
        raise ValueError(f"Unusable file name: {uploaded.name!r}")

    path = os.path.join(directory, name)
    with open(path, "wb") as f:
        f.write(uploaded.getbuffer())

    return path


def _audio_options(prefix: str) -> dict:
    """Render the option set common to three tabs and return the values.

    Counterpart of `cli.py`'s parent `audio` parser: the options are declared
    once, not three times. `prefix` separates the widget keys, which Streamlit
    wants unique across the whole app.
    """
    left, right = st.columns(2)

    with left:
        diarize = st.checkbox(
            "Identify speakers",
            key=f"{prefix}_diarize",
            help="Goes through whisperx instead of mlx-whisper. Runs on CPU: "
            "expect several times the audio's duration.",
        )
        num_speakers = st.number_input(
            "Number of speakers, if known",
            min_value=1,
            max_value=20,
            value=None,
            step=1,
            key=f"{prefix}_num_speakers",
            disabled=not diarize,
            placeholder="auto-detect",
        )

    with right:
        summarize = st.checkbox(
            "Summarize via the Claude API",
            key=f"{prefix}_summarize",
            help="The only paid option, and the only step that leaves the "
            "machine: the text is sent to the Claude API.",
        )
        # A selector rather than a free-text field: an invented value would not
        # be rejected by Whisper, it would produce a translation. The field is
        # greyed out when diarizing, where whisperx detects the language on its
        # own — the native equivalent of the warning the CLI prints.
        language_label = st.selectbox(
            "Language",
            options=list(LANGUAGES),
            index=0,
            key=f"{prefix}_language",
            disabled=diarize,
            help=LANGUAGE_HELP,
        )

    return {
        "diarize": diarize,
        "num_speakers": int(num_speakers) if num_speakers else None,
        "language": LANGUAGES[language_label],
        "summarize": summarize,
    }


def _result_from_output(output_path: str, options: dict) -> dict:
    """Re-read the written output and, if asked, chain the summary.

    The transcript is re-read from disk rather than reformatted here, for the
    same reason as in `cli.py`: the `[SPEAKER_XX] text` format has a single
    definition, in `diarize.py`.

    A failing summary does not erase the transcript, which is already written:
    it is reported separately.
    """
    with open(output_path, encoding="utf-8") as f:
        text = f.read()

    result = {
        "path": output_path,
        "text": text,
        "summary": None,
        "summary_path": None,
        "summary_error": None,
    }

    if options["summarize"]:
        from summarize import save_summary, summarize_text

        try:
            with st.spinner("Summarizing via the Claude API…"):
                summary = summarize_text(text)
        except ValueError as error:
            result["summary_error"] = str(error)
        else:
            result["summary"] = summary
            result["summary_path"] = save_summary(summary, output_path)

    return result


def _transcribe_one(audio_path: str, options: dict) -> dict:
    """Transcribe a file already on disk, with or without speakers."""
    label = os.path.basename(audio_path)

    if options["diarize"]:
        from diarize import diarize_file, save_diarized_transcript

        with st.spinner(f"Diarizing {label}… (CPU, allow plenty of time)"):
            segments = diarize_file(audio_path, num_speakers=options["num_speakers"])
            output_path = save_diarized_transcript(segments, audio_path)
    else:
        from transcribe import save_transcript, transcribe_file

        with st.spinner(f"Transcribing {label}…"):
            text = transcribe_file(audio_path, language=options["language"])
            output_path = save_transcript(text, audio_path)

    return _result_from_output(output_path, options)


def _render_result(key: str) -> None:
    """Display the transcript remembered for a tab, and its summary."""
    result = st.session_state.get(key)
    if not result:
        return

    st.success(f"Transcript saved: {result['path']}")
    st.text_area("Transcript", result["text"], height=280, key=f"{key}_text_area")
    st.download_button(
        "Download the .txt",
        data=result["text"],
        file_name=os.path.basename(result["path"]),
        mime="text/plain",
        key=f"{key}_download",
    )

    if result["summary_error"]:
        st.error(result["summary_error"])
    elif result["summary"]:
        st.divider()
        st.markdown("#### Summary")
        st.markdown(result["summary"])
        st.caption(f"Summary saved: {result['summary_path']}")
        st.download_button(
            "Download the summary",
            data=result["summary"],
            file_name=os.path.basename(result["summary_path"]),
            mime="text/plain",
            key=f"{key}_summary_download",
        )


def _tab_single() -> None:
    uploaded = st.file_uploader(
        "Audio file",
        type=[extension.lstrip(".") for extension in SUPPORTED_EXTENSIONS],
        key="single_upload",
    )
    options = _audio_options("single")

    if st.button(
        "Transcribe", key="single_run", type="primary", disabled=uploaded is None
    ):
        # The received file only serves to feed the pipeline: it is written into
        # a temporary folder, erased when the block exits. Only the transcript,
        # in `output/`, survives.
        with tempfile.TemporaryDirectory() as workdir:
            try:
                audio_path = _save_upload(uploaded, workdir)
                st.session_state["single"] = _transcribe_one(audio_path, options)
            except (FileNotFoundError, ValueError) as error:
                st.session_state["single"] = None
                st.error(str(error))

    _render_result("single")


def _run_folder(folder: str, options: dict, force: bool) -> dict:
    """Process a folder, then summarize its transcripts if asked."""
    from batch import process_folder

    with st.spinner(f"Processing {folder}…"):
        summary = process_folder(
            folder,
            diarize=options["diarize"],
            num_speakers=options["num_speakers"],
            force=force,
            language=options["language"],
        )

    summaries_failed = None
    if options["summarize"] and (summary["success"] or summary["skipped"]):
        # The batch summarization rule — also summarize the files skipped by the
        # resume logic, but not those whose `_summary.txt` already exists —
        # lives in `cli.summarize_batch()`. We call it rather than rewrite it
        # here: duplicated, it would end up diverging from the CLI's.
        from cli import summarize_batch

        with st.spinner("Summaries via the Claude API…"):
            summaries_failed = summarize_batch(
                summary, diarize=options["diarize"], force=force
            )

    return {"summary": summary, "summaries_failed": summaries_failed}


def _render_batch() -> None:
    """Display a batch report as counters and a table.

    `batch.report_summary()` produces the same report on stdout: what differs is
    the rendering, not what is reported.
    """
    state = st.session_state.get("batch")
    if not state:
        return

    from batch import short_reason

    summary = state["summary"]
    success, skipped, failed = (
        summary["success"],
        summary["skipped"],
        summary["failed"],
    )

    if not (success or skipped or failed):
        st.info("No audio file in this folder.")
        return

    columns = st.columns(3)
    columns[0].metric("Succeeded", len(success))
    columns[1].metric("Skipped", len(skipped))
    columns[2].metric("Failed", len(failed))

    rows = [
        {"File": os.path.basename(path), "Status": "✅ Succeeded", "Detail": ""}
        for path in success
    ]
    rows += [
        {
            "File": os.path.basename(path),
            "Status": "⏭️ Skipped",
            "Detail": "already done — tick “Reprocess” to redo it",
        }
        for path in skipped
    ]
    rows += [
        {
            "File": os.path.basename(path),
            "Status": "❌ Failed",
            "Detail": short_reason(reason),
        }
        for path, reason in failed
    ]
    st.dataframe(rows, hide_index=True)

    if failed:
        st.error(f"{len(failed)} file(s) failed — the batch still ran to the end.")
    else:
        st.success("Batch finished with no failure.")

    summaries_failed = state["summaries_failed"]
    if summaries_failed:
        st.error(f"{summaries_failed} summary/summaries failed.")
    elif summaries_failed == 0:
        st.success("Summaries written to output/, next to the transcripts.")


def _tab_batch() -> None:
    folder_input = st.text_input(
        "Folder to process",
        value="test-audio",
        key="batch_path",
        help=f"Path relative to {BROWSE_ROOT}, or absolute under that root.",
    )
    st.caption(
        f"Allowed root: `{BROWSE_ROOT}` — a path that leaves it is refused."
    )

    options = _audio_options("batch")
    force = st.checkbox(
        "Reprocess files already done",
        key="batch_force",
        help="Without this box, a file whose output already exists is skipped: "
        "that is what lets an interrupted batch restart without redoing "
        "everything.",
    )

    if st.button("Run the batch", key="batch_run", type="primary"):
        try:
            folder = _resolve_browse_path(folder_input)
            st.session_state["batch"] = _run_folder(folder, options, force)
        except (NotADirectoryError, ValueError) as error:
            st.session_state["batch"] = None
            st.error(str(error))

    _render_batch()


def _transcribe_recording(data: bytes, language: str | None) -> dict:
    """Transcribe a recording held in memory, never putting it in the repository.

    Dictated audio is a draft: it has no business surviving its transcription,
    nor joining `test-audio/` or `output/` among the files we keep. It therefore
    touches the disk only in the system temporary folder, and the `finally`
    erases it there — success, failure or unforeseen exception. Nothing is left
    to the garbage collector, which promises neither when it runs nor that it
    will.

    `transcribe_file()` asks for a path because mlx-whisper decodes the file
    itself, by calling ffmpeg: that detour through the disk is unavoidable.
    """
    from transcribe import transcribe_file

    path = None
    try:
        # `delete=False` because the file must stay readable after the handle is
        # closed, long enough for ffmpeg to decode it.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            handle.write(data)
            path = handle.name

        with st.spinner("Transcribing the dictation…"):
            text = transcribe_file(path, language=language)
    except (FileNotFoundError, ValueError) as error:
        return {"text": None, "error": str(error), "path": None}
    finally:
        if path:
            os.unlink(path)

    return {"text": text.strip(), "error": None, "path": None}


def _reset_dictation() -> None:
    """Start again from a blank widget, keeping none of the previous recording.

    Passed as `on_click`, this function runs *before* the script reruns: the
    keys are therefore cleared while no widget is instantiated, which deleting
    mid-render would not allow.

    The previous round's audio is removed from `session_state` explicitly.
    Incrementing the counter would be enough to display a fresh widget, but the
    dictation's bytes would stay in memory until the end of the session — for a
    tab whose commitment is to keep nothing, that would be an oversight.
    """
    round_number = st.session_state.get("dictation_round", 0)
    st.session_state.pop(f"dictation_input_{round_number}", None)
    st.session_state.pop(f"dictation_save_{round_number}", None)
    st.session_state.pop("dictation", None)
    st.session_state["dictation_round"] = round_number + 1


def _tab_dictation() -> None:
    """Dictate into the microphone and get the text back, leaving nothing behind.

    No diarization here: you dictate alone. No saving by default either — the
    intended use is to paste the text somewhere else within seconds, and writing
    a file on every attempt would clutter `output/` for nothing.
    """
    st.caption(
        "Single-speaker dictation: the audio is neither kept nor written into "
        "the repository, and the text is only saved if you ask for it."
    )

    language_label = st.selectbox(
        "Language",
        options=list(LANGUAGES),
        index=0,
        key="dictation_language",
        help=LANGUAGE_HELP,
    )
    language = LANGUAGES[language_label]

    # The widget key carries a round number, because Streamlit offers no way to
    # empty an `audio_input` in place: without a fresh key it would keep its
    # recording and the tab would stay stuck on the first dictation. Changing
    # the key makes it build a blank widget — that is what "New dictation" does.
    round_number = st.session_state.setdefault("dictation_round", 0)
    recording = st.audio_input("Recording", key=f"dictation_input_{round_number}")
    if recording is None:
        # Recording deleted by the user: the text that went with it no longer
        # has a subject.
        st.session_state.pop("dictation", None)
        return

    data = recording.getvalue()

    # Streamlit reruns the whole script on the slightest click — ticking the
    # save box would be enough to start a transcription over. So we only
    # re-transcribe if the audio or the language changed, the language counting
    # because changing it is an explicit request to redo the pass.
    signature = (hashlib.sha1(data).hexdigest(), language)
    state = st.session_state.get("dictation")
    if not state or state["signature"] != signature:
        state = _transcribe_recording(data, language)
        state["signature"] = signature
        st.session_state["dictation"] = state

    if state["error"]:
        st.error(state["error"])
    elif not state["text"]:
        st.warning("Nothing was transcribed — empty or inaudible recording.")
    else:
        # `st.code` rather than a `text_area`: it carries a native "copy"
        # button, which is the gesture expected here.
        st.code(state["text"], language=None, wrap_lines=True)

        if st.checkbox(
            "Save to output/ anyway",
            key=f"dictation_save_{round_number}",
            help="Unticked, nothing is written: the dictation only lives on "
            "this screen.",
        ):
            if not state["path"]:
                from transcribe import save_transcript

                # `save_transcript()` does not read the audio, it only uses this
                # path to name its output — which is exactly what lets us name
                # it without rebuilding the convention here. The temporary file
                # itself stopped existing long ago.
                timestamp = datetime.now().strftime("%Y-%m-%d-%Hh%M")
                state["path"] = save_transcript(
                    state["text"], f"dictation-{timestamp}.wav"
                )
            st.success(f"Transcript saved: {state['path']}")

    # Offered in all three cases, including when nothing was transcribed: an
    # inaudible dictation is as much a dead end as a successful one, and this is
    # the only way to start another.
    st.button("New dictation", key="dictation_reset", on_click=_reset_dictation)


def _tab_youtube() -> None:
    url = st.text_input("Video URL", key="youtube_url", placeholder="https://youtu.be/…")
    options = _audio_options("youtube")

    if st.button(
        "Transcribe", key="youtube_run", type="primary", disabled=not url.strip()
    ):
        from youtube import transcribe_youtube

        # As in `cli.py`: the kwargs go to `diarize_file()` or to
        # `transcribe_file()` depending on the mode, they are not
        # interchangeable.
        extra: dict = {"num_speakers": options["num_speakers"]} if options["diarize"] else {}
        if options["language"] and not options["diarize"]:
            extra["language"] = options["language"]

        try:
            with st.spinner("Downloading the audio, then transcribing…"):
                _, output_path = transcribe_youtube(
                    url.strip(), diarize=options["diarize"], **extra
                )
            st.session_state["youtube"] = _result_from_output(output_path, options)
        except (FileNotFoundError, ValueError) as error:
            st.session_state["youtube"] = None
            st.error(str(error))

    _render_result("youtube")


def main() -> None:
    st.set_page_config(page_title="Whisper Toolkit", page_icon="🎙️", layout="centered")

    # Launched anywhere other than from an interactive shell — Automator app,
    # Finder, launchd — the interface inherits a minimal PATH without
    # `/opt/homebrew/bin`. ffmpeg is then installed but unreachable for the
    # subprocesses of mlx_whisper and whisperx, which call it by its bare name.
    # Repaired here, at the entry point concerned: the CLI always starts from a
    # shell.
    ffmpeg = ensure_on_path()

    st.title("🎙️ Whisper Toolkit")
    st.caption(
        "Local audio transcription — the same thing as `python src/cli.py`, "
        "in the browser. Outputs are written to `output/`."
    )

    if not ffmpeg:
        # Without this, a missing ffmpeg only shows up at the bottom of a
        # traceback, once the file has been dropped and the model loaded.
        st.error(
            "ffmpeg cannot be found — no transcription will work.\n\n"
            "Install it (`brew install ffmpeg`), or launch the app from a "
            "terminal where `ffmpeg` answers."
        )

    single, batch, youtube, dictation = st.tabs(
        ["Single file", "Folder (batch)", "YouTube", "Quick dictation"]
    )

    with single:
        _tab_single()
    with batch:
        _tab_batch()
    with youtube:
        _tab_youtube()
    with dictation:
        _tab_dictation()


if __name__ == "__main__":
    main()
