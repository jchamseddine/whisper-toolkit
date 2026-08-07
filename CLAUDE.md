# CLAUDE.md

Behavioural guidelines for all future development on this repo.

## Working principles

### Think Before Coding
Think before writing code. Understand the problem, read the existing code,
identify the files involved — then code. No throwaway code, no prototype meant
to be discarded afterwards: what gets written is meant to stay.

### Simplicity First
Prefer the simplest solution that works. No anticipatory abstraction, no
configuration layer for a single case, no design pattern where a function will
do. One more dependency has to be justified.

### Surgical Changes
Targeted, minimal changes. No unrequested refactor, no reformatting of files you
are not touching, no opportunistic renaming. If a refactor seems necessary,
propose it — do not do it in passing.

### Goal-Driven Execution
Stay focused on the goal of the task at hand. Do not spill over into the
project's later steps. If an idea falls outside the scope, note it and carry on.

## Project context

`whisper-toolkit` — a Python CLI for **local** audio transcription, built on
Whisper. A personal side project.

Features, all implemented and actually run for real:
- Local transcription via **mlx-whisper** (optimised for Apple Silicon)
- Diarization (speaker identification) via **whisperx**
- **Batch** processing of a whole folder, with resume
- Transcription from a **YouTube URL** via **yt-dlp**
- **Automatic summarization** via the Claude API
- All of it behind a **unified `argparse` CLI** (`python src/cli.py`), doubled by
  a Streamlit **web interface** (`streamlit run app.py`) that calls the same
  code — the two coexist

**Folder watching is deliberately set aside.** Batch processing covers the real
usage; the watchdog mode will only be added if the need is confirmed.

## Technical stack

| Purpose | Tool |
|---|---|
| Language | Python 3 (local venv, `venv/` folder) |
| Transcription | `mlx-whisper` (Apple Silicon only) |
| Diarization | `whisperx` |
| Audio download | `yt-dlp` |
| Summarization | Claude API (`anthropic`) |
| CLI | `argparse` (stdlib) |
| Web interface | `streamlit` |

## Folder structure

```
whisper-toolkit/
├── CLAUDE.md          # this file
├── README.md
├── app.py             # Streamlit web interface (presentation only)
├── requirements.txt
├── .gitignore
├── .env               # HF_TOKEN + ANTHROPIC_API_KEY (not versioned)
├── venv/              # virtual environment (not versioned)
├── output/            # produced transcripts (not versioned)
├── assets/            # Automator app icon (.icns + source PNG)
├── scripts/           # tooling outside the pipeline — icon, launcher bundle
├── src/
│   ├── cli.py         # unified CLI — entry point
│   ├── transcribe.py  # plain transcription (mlx-whisper)
│   ├── diarize.py     # transcription + speakers (whisperx)
│   ├── batch.py       # processing a whole folder
│   ├── youtube.py     # transcription from a URL (yt-dlp)
│   ├── summarize.py   # summarizing a transcript (Claude API)
│   └── ffmpeg_path.py # locating ffmpeg, outside PATH if need be
└── tests/             # tests (empty for now)
```

## Platform constraints

`mlx-whisper` installs **only on macOS Apple Silicon**. Development can happen
on another machine, but the `mlx_whisper` import must stay optional / lazy so
the rest of the CLI works elsewhere. See the README for the current machine's
installation state.

## Current state

**The 8 steps of the initial plan are finished**, each validated by real runs —
measurements and edge cases in the README, *Testing Status* section. There is no
longer a "do not anticipate" step: the next work is hardening, automated tests,
or a new feature to be defined.

### Two layers, not to be mixed

**Pipeline layer** — the real audio work. These two modules are independent: no
cross-imports, no shared state, no common backend. That is not an accident; each
is the best tool for its job.

| Module | Role | Backend |
|---|---|---|
| `transcribe.py` | audio → text | `mlx-whisper`, Metal GPU |
| `diarize.py` | audio → `{start, end, text, speaker}` segments | `whisperx` → faster-whisper, **CPU only** |

**Orchestration layer** — no audio logic, delegation only.

| Module | Role |
|---|---|
| `batch.py` | lists a folder, delegates file by file, resumes by default |
| `youtube.py` | downloads the audio (yt-dlp), then delegates |
| `summarize.py` | text → summary via the Claude API — the only module that leaves the machine, and the only one that costs money |
| `cli.py` | entry point: one command, four subcommands |
| `app.py` | second entry point: Streamlit web interface, four tabs. Coexists with the CLI, does not replace it. *Quick dictation* is the only one that writes neither audio nor text by default |

### How it fits together

```
cli.py transcribe FILE   ──> transcribe_file() | diarize_file()
cli.py batch FOLDER      ──> process_folder()      ──> same, file by file
cli.py youtube URL       ──> transcribe_youtube()  ──> same, after downloading
cli.py summarize F.txt   ──> summarize_text()
                                  ▲
                --summarize chains this step onto the output of the other three
```

The rules that hold the whole together — breaking them breaks things that work
today:

- **`cli.py` and `app.py` contain no business logic.** They call, they display.
  A new feature goes into the module concerned, never into an entry point —
  otherwise it only exists on one side.
- **Output naming conventions belong to the modules that write.**
  `transcript_path()`, `diarized_transcript_path()` and `summary_path()` are
  their single source — never rebuild an output path elsewhere, that is what
  keeps `batch.py`'s resume logic coherent.
- **Imports between `src/` modules are flat** (`from transcribe import …`)
  because these files run as scripts. A `python -m src.cli` would not work
  without relative imports.
- **Heavy dependencies are imported lazily**: `mlx_whisper`, `whisperx` and
  `anthropic` inside the functions that use them, sibling modules inside
  `cli.py`'s handlers. That is what keeps `--help` at 0.03 s and the rest of the
  toolkit usable off Apple Silicon.
- **Every module keeps its own `main()`** and stays runnable on its own
  (`python src/diarize.py file.wav`). That is where the rare settings live —
  `--model`, `--diarization-model` — which the unified CLI deliberately does not
  expose.
- **The language is never forced by default.** Forcing a language that is not
  the audio's does not raise an error, it produces an invented translation,
  fluent and undetectable in the output.
- **Never assume ffmpeg is on `PATH`.** The three backends call it as a
  subprocess, and a launch outside an interactive shell (Automator app, Finder,
  launchd) does not inherit `/opt/homebrew/bin`. Go through `ffmpeg_path.py`: an
  explicit path when the caller accepts one — yt-dlp — `ensure_on_path()`
  otherwise.

### What is not done

- Folder watching — deliberately set aside (see above).
- `tests/` is empty: no automated tests, everything was checked by hand.
- The toolkit is not installable (`pip install -e .`); the reason is documented
  in the README, *Usage* section.
- Known caveats (diarization tested on synthetic voices only, summarization
  never measured on a real long transcript, etc.) are listed in the README under
  *Still to validate* — read them before promising anything on those points.
