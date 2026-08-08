# whisper-toolkit

Python CLI for **local** audio transcription, built on Whisper.

> **Status: under development.** Local transcription, diarization, batch
> processing, transcription from a YouTube URL and summarization via the Claude
> API are implemented and actually run for real, behind a unified CLI — doubled
> by a Streamlit web interface that calls the same code.
> Two caveats: speaker separation has only been tested on synthetic voices, with
> no overlapping speech, and summarization has only been measured on a
> hand-written transcript, not on a real long Whisper output.
> Folder watching has not been started.
> Details in [Testing Status](#testing-status).

## Usage

Everything goes through a single command, with one subcommand per input mode.

```bash
source venv/bin/activate

python src/cli.py transcribe lecture.m4a            # one file
python src/cli.py batch my-lectures/                # a whole folder
python src/cli.py youtube 'https://youtu.be/...'    # a YouTube URL
python src/cli.py summarize output/lecture.txt      # summarize an existing text
```

The first three write into `output/`. `python src/cli.py --help`, and
`python src/cli.py <subcommand> --help`, list the rest.

### Web interface

A Streamlit interface covers the three audio inputs, **on top of** the CLI — it
does not replace it, and both call exactly the same code.

```bash
source venv/bin/activate
streamlit run app.py           # http://localhost:8501
```

Four tabs. *Single file* (drag and drop), *Folder (batch)* and *YouTube* carry
the command line's options over, write into `output/` under the same names, and
offer a download button for the `.txt`.

*Quick dictation* stands apart: you speak into the microphone, the text appears
in a block you copy with one click, and **nothing is written** — neither the
audio, which never leaves the system temporary folder, nor the text, unless you
tick the save box. No diarization either: you dictate alone. It is the only tab
that leaves no trace, and that is deliberate — the intended use is to paste the
text somewhere else within seconds, not to archive it.

What the app does not expose: the `summarize` subcommand on its own (the summary
is ticked on the fly there), `--summary-model` and `--summary-style`. Details in
[`app.py` — web interface](#apppy--web-interface-presentation-only).

> ⚠️ **Streamlit listens on every interface by default**, not just on
> `localhost`: launched as-is, it shows a "Network URL" reachable by the whole
> local network. On a network that is not yours:
>
> ```bash
> streamlit run app.py --server.address localhost
> ```

### Native window, no browser

`launch_desktop.py` serves the same interface in a macOS window (pywebview)
rather than in a tab. That is what the Automator app launches.

```bash
source venv/bin/activate
python launch_desktop.py
```

It starts Streamlit as a subprocess, waits for the server to answer (15 s at
most), then opens the window. When the window closes, the server is stopped
along with all its descendants — `lsof -i :8501` must be empty right after. If
the server does not answer within the delay, no window is opened: the script
writes the error to its standard error and stops. Launched by the applet, all of
that goes to `~/Library/Logs/WhisperToolkit.log`, whose tail the applet surfaces
in a dialog box — see *The Automator app* below.

Six points are worth knowing before touching it:

- **`--server.headless true` is not cosmetic.** Without it, Streamlit opens a
  browser tab of its own at startup: the native window would show up *on top of*
  the browser.
- **Port 8501 is checked before launching.** A server already in place would
  answer the probe, and the window would open on that foreign instance while our
  subprocess dies for want of a port.
- **Streamlit runs in its own process session.** Killing only the parent would
  leave its children holding the port; the whole group is terminated.
- **The "Deploy / Rerun / Clear cache" menu is removed**
  (`--client.toolbarMode minimal`). It addresses whoever develops the app, not
  whoever uses it, and its actions make no sense for a local app in a window.
- **The app's identity rests on a purpose-built bundle** — see just below.
- **The microphone takes two additions**, without which dictation stays mute —
  see *The microphone in the native window*.

#### The microphone in the native window

The *Quick dictation* tab records through `getUserMedia`. In a browser, the
browser asks for permission and that is that. In a WKWebView, the host
application is the one being asked, and two pieces were needed:

- **`NSMicrophoneUsageDescription` in the bundle's `Info.plist`**, set by
  `make_launcher_bundle.sh`. Without it, macOS kills the process at the first
  request instead of showing the prompt.
- **The `webView:requestMediaCapturePermissionForOrigin:…` delegate**, grafted
  by `allow_microphone()` in `launch_desktop.py`. pywebview 6.2.1 does not
  implement it: its `BrowserDelegate` covers alert panels and the file picker,
  not capture.

Without that delegate, the failure is particularly painful to diagnose:
`getUserMedia` **does not reject, it simply never answers**. No console error,
no prompt, a record button that stays inert. Measured: the promise was still
pending after 20 s. Once the delegate is in place, WebKit calls it with type 1
(microphone) and the promise resolves with an audio track.

Grafting a method onto a dependency's class remains a patch to keep an eye on:
if a version of pywebview implements this delegate, `allow_microphone()` has no
reason to exist. It already checks `instancesRespondToSelector_` before writing,
and therefore never covers over an official implementation.

Granting inside the delegate short-circuits nothing: macOS then asks the user
its own question, and the answer is revoked in System Settings › Privacy ›
Microphone. To trigger the prompt again:

```bash
tccutil reset Microphone com.jad.whisper-toolkit
```

#### Icon and name in the Dock

macOS identifies a process by the `.app` bundle its executable belongs to.
Homebrew's `python3.12` is only a relay: it re-executes into
`Python.framework/…/Resources/Python.app`, whose `Info.plist` announces "Python"
and a rocket. The whole identity therefore came from the interpreter.

`scripts/make_launcher_bundle.sh` builds the costume that was missing: a copy of
that `Python.app`, under `~/Library/Application Support/Whisper Toolkit/`, with
our `Info.plist` and our icon. Same binary, our own identity. The original is
never modified, and the bundle produced keeps its provenance in
`Contents/Resources/ORIGIN.txt`.

| What you see | Before | After |
|---|---|---|
| Dock icon | Python rocket | **microphone** ✅ |
| Menu name, next to the Apple logo | Python | **Whisper Toolkit** ✅ |
| Dock tooltip, on hover | Python | **Whisper Toolkit** ✅ |
| Process name (`ps`, Activity Monitor) | Python | **Whisper Toolkit** ✅ |

Four details decide the outcome, and each takes its revenge in silence:

- **`__PYVENV_LAUNCHER__` is vital.** Running the bundle's binary directly
  bypasses `venv/bin/python`: no more streamlit, no more pywebview. That
  variable — the very one Homebrew's relay uses to survive its own re-execution
  — puts the interpreter back in the venv. The applet is what sets it.
- **What the Dock displays is the bundle's file name**, not `CFBundleName`. A
  bundle named `WhisperToolkitLauncher.app` gives a "WhisperToolkitLauncher"
  tooltip, immaculate `Info.plist` or not. Hence `Whisper Toolkit.app`, spelled
  identically.
- **Renaming the inner executable** makes the process name follow in `ps` and
  Activity Monitor, which the `Info.plist` alone does not change.
- **It has to be re-signed.** Editing the `Info.plist` of a signed binary breaks
  the seal, and macOS then refuses to launch the bundle.

`set_dock_identity()`, in `launch_desktop.py`, is redundant once the app is
launched by the applet — but stays useful in development, when running
`python launch_desktop.py` from a terminal, without going through the bundle.

**A single tile appears in the Dock**, and that owes more to the applet's script
than to the bundle. An Automator applet lives as long as its script: while it
waited for Python to finish, it occupied its own tile on top of the app's. It
therefore now launches Python in the background, then withdraws as soon as
Streamlit answers.

#### The Automator app

`Whisper Toolkit.app` is not versioned here — it is an Automator applet living
in `/Applications`. To recreate it, first build the bundle:

```bash
./scripts/make_launcher_bundle.sh
```

then Automator › Application › *Run Shell Script* action, shell `/bin/zsh`, with
exactly this content:

```bash
cd ~/Code/whisper-toolkit

LAUNCHER="$HOME/Library/Application Support/Whisper Toolkit/Whisper Toolkit.app/Contents/MacOS/Whisper Toolkit"
LOG="$HOME/Library/Logs/WhisperToolkit.log"

mkdir -p "$(dirname "$LOG")"
echo "=== $(date) ===" > "$LOG"

__PYVENV_LAUNCHER__="$PWD/venv/bin/python" nohup "$LAUNCHER" launch_desktop.py < /dev/null >> "$LOG" 2>&1 &
PID=$!
disown

for _ in {1..80}; do
    sleep 0.25
    if ! kill -0 $PID 2>/dev/null; then
        { tail -n 3 "$LOG"; echo; echo "Full log: $LOG"; } >&2
        exit 1
    fi
    curl -sf -m 1 http://localhost:8501/_stcore/health >/dev/null 2>&1 && exit 0
done
exit 0
```

The loop is not decorative. Returning immediately after the `&` would make any
startup failure perfectly mute: no terminal, no dialog. The applet therefore
watches until Streamlit answers — the app is visible, it has no further reason
to exist — or until the process dies, the only case where it has something to
say.

**`< /dev/null` is not decoration either.** Automator hands its shell script a
pipe on standard input. Redirecting the background process's output leaves that
pipe untouched: the launcher keeps its read end open for the whole session, and
so does Streamlit, which inherits its streams. Checked with `lsof -p <pid> -a
-d 0` — `PIPE` without the redirect, `/dev/null` with it, on both processes.
An applet that has withdrawn should leave nothing of itself behind in the
processes it started.

**The pairing of "message on stderr + `exit 1`" is what triggers Automator's
dialog box**, and that is the only one guaranteed to show. A `display alert` via
osascript would require the applet's permission to drive System Events, which it
does not have: it fails in silence, drawing nothing and reporting nothing.
Tried, and abandoned for that reason. Symmetrically, exiting with a non-zero
code when all is well would make Automator show a box with an empty message.

**When something goes wrong at launch, everything is in
`~/Library/Logs/WhisperToolkit.log`** — the full output of Python and Streamlit,
rewritten on every launch. The dialog only shows its last three lines.

The bundle has to be rebuilt after every Homebrew update of Python: the copied
binary points at the exact framework version, which a `brew upgrade` moves.

Its icon is regenerated with `./scripts/make_app_icon.sh --apply` (see the macOS
traps documented at the top of the script). Two details are worth noting if you
edit the applet by hand rather than through Automator: the bundle is ad-hoc
signed, so any edit to `Contents/` requires re-signing
(`codesign --force --sign -`); and `Contents/document.wflow` is signed as a
separate object, whose `com.apple.cs.*` xattrs must be removed before
re-signing, otherwise verification fails on that subcomponent.

### Options

| Option | `transcribe` | `batch` | `youtube` | Effet |
|---|:---:|:---:|:---:|---|
| `--diarize` | ✅ | ✅ | ✅ | identify speakers (whisperx) instead of a plain transcription |
| `--num-speakers N` | ✅ | ✅ | ✅ | exact number of speakers, if known (with `--diarize`) |
| `--language fr` | ✅ | ✅ | ✅ | force the language — by default it is **detected**, and forcing it wrongly produces a silent translation (see [Language](#language-detected-never-forced-by-default)) |
| `--summarize` | ✅ | ✅ | ✅ | chain a summary via the Claude API — **the only paid option** |
| `--summary-model`, `--summary-style` | ✅ | ✅ | ✅ | model and style of the chained summary |
| `--force` | — | ✅ | — | reprocess what already exists, summaries included |

The `summarize` subcommand takes `--model` and `--style` (same values, without
the prefix: that is all it does).

```bash
# transcription + speakers + summary, in a single command
python src/cli.py transcribe meeting.wav --diarize --num-speakers 3 --summarize

# a whole folder, a summary of each file, resuming where it stopped
python src/cli.py batch my-lectures/ --summarize

# a tailored summary of an already-produced transcript
python src/cli.py summarize output/lecture.txt --style "in three bullets"
```

Exit code `0` if everything went well, `1` otherwise — including when a single
file in a batch failed.

### Why `python src/cli.py` and not an installed `whisper-toolkit` command

The CLI could have been exposed as an executable (`pip install -e .` plus an
`entry_point` in a `pyproject.toml`), to type `whisper-toolkit transcribe
lecture.m4a`. That is **not** done, for three reasons:

- **The `src/` modules import flat** (`from transcribe import …`), which works
  because `python src/cli.py` puts `src/` at the front of `sys.path`. An
  installable package would require either converting the six files to package
  imports — a refactor of working code, for zero functional gain — or publishing
  `transcribe`, `batch`, `summarize` and `youtube` as **top-level** modules in
  the venv's `site-packages`. Those names are too generic not to collide one day.
- **The gain amounts to a few characters.** The venv has to be activated either
  way: an installed command does not spare you `source venv/bin/activate`.
- **`output/` is relative to the current directory.** An installed command
  invites you to run the toolkit from anywhere, and therefore to scatter
  transcripts across as many `output/` folders as working directories. Today the
  convention is simple: you run from the repository root.

To shorten the line without installing anything, an alias is enough:

```bash
alias wt="$PWD/venv/bin/python $PWD/src/cli.py"
```

The question will come back if the toolkit has to be distributed to someone
else. It will then be a real package (`whisper_toolkit/` with package imports),
not an `entry_point` laid on top of the current structure.

## Planned features

- **Local transcription** via [`mlx-whisper`](https://github.com/ml-explore/mlx-examples) (optimised for Apple Silicon)
- **Diarization** (speaker identification) via [`whisperx`](https://github.com/m-bain/whisperX)
- **Batch**: processing a whole folder
- **Folder watching**: automatic transcription of new files
- **YouTube**: direct transcription from a URL via [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
- **Automatic summarization** of the transcript via the Claude API
- All of it in a **unified CLI** (`argparse`), doubled by a **web interface**
  (Streamlit) that calls exactly the same code — displayable in a browser or in
  a **native window** (`launch_desktop.py`)

## Structure

```
whisper-toolkit/
├── CLAUDE.md          # dev guidelines + project context
├── README.md
├── app.py             # Streamlit web interface (presentation only)
├── launch_desktop.py  # same interface, in a native window (pywebview)
├── requirements.txt
├── .gitignore
├── .env               # HF_TOKEN for diarization (not versioned)
├── .nltk_data/        # project-local NLTK cache (not versioned, regenerable)
├── venv/              # virtual environment (not versioned)
├── test-audio/        # test samples (ignored, except the synthetic fixture)
├── output/            # produced transcripts (not versioned)
├── assets/            # Automator app icon (.icns + source PNG)
├── scripts/           # tooling outside the pipeline — icon, launcher bundle
├── src/
│   ├── cli.py         # unified CLI — entry point, orchestration only
│   ├── transcribe.py  # plain transcription (mlx-whisper)
│   ├── diarize.py     # transcription + speakers (whisperx)
│   ├── batch.py       # processing a whole folder
│   ├── youtube.py     # transcription from a URL (yt-dlp)
│   ├── summarize.py   # summarizing a transcript (Claude API)
│   └── ffmpeg_path.py # locating ffmpeg, outside PATH if need be
└── tests/             # tests (empty for now)
```

## Architecture

The project has **two distinct audio pipelines**, sharing neither backend nor
model. That is not an accident: each is the best tool for its job.

| | `transcribe.py` | `diarize.py` |
|---|---|---|
| Backend | `mlx-whisper` | `whisperx` → `faster-whisper` |
| Runtime | MLX | CTranslate2 |
| Hardware | **Metal GPU** (Apple Silicon) | **CPU only** |
| Default model | `mlx-community/whisper-large-v3-mlx` | `large-v3` (CTranslate2) |
| Output | plain text | `{start, end, text, speaker}` segments |
| Credentials required | none | Hugging Face token |

**Why two backends.** CTranslate2, which whisperx rests on, has no Metal or MPS
support: the diarization path therefore runs entirely on CPU, without the
acceleration `transcribe.py` enjoys. Conversely, mlx-whisper offers neither
word-level alignment nor diarization. Use `transcribe.py` when you just want the
text, fast; `diarize.py` when you need to know who is speaking.

The two modules are independent: no cross-imports, no shared state.
`diarize.py` redoes its own transcription rather than reusing `transcribe.py`'s,
because word-level alignment requires faster-whisper's internal outputs.

### Language: detected, never forced by default

`transcribe_file()` takes `language: str | None = None`: Whisper detects the
language. The three CLIs expose `--language` to force it (`fr`, `en`, …), with
no effect when diarizing, where whisperx detects on its own, file by file.

**Forcing a language never produces an error — it produces a translation.**
Whisper, given a language that is not the audio's, returns text in the requested
language, fluent and plausible, without the slightest signal. Nothing in the
output distinguishes a transcription from an invented translation. That is the
flaw the first English YouTube video revealed, transcribed into French; the
French fixture with `--language en` reproduces it identically in the other
direction (see Test 8).

A default hard-coded to `fr` was therefore untenable for a toolkit that swallows
YouTube URLs and heterogeneous folders. And removing it costs nothing:
**strictly identical text** across the 5 French fixtures, for a **fixed**
overhead of about 0.3 s — one pass over the first window, not proportional to
the duration (0.5% on a 76 s file).

### `cli.py` — one command, four subcommands

`cli.py` is an orchestration layer just like `batch.py`: it contains **no**
transcription, diarization, download or summarization logic. Each subcommand
calls the functions of the modules that carry it, then displays what they wrote.

```
transcribe FILE  ──> transcribe_file() | diarize_file()  ──> output/{name}[_diarized].txt ─┐
batch FOLDER     ──> process_folder()      (delegates file by file)                        ├─> --summarize
youtube URL      ──> transcribe_youtube()  (yt-dlp then delegation)                        ─┘     │
                                                                                                  ▼
summarize FILE.txt ───────────────────────> summarize_text()  ─────────────> output/{name}_summary.txt
```

**`argparse` with subparsers, no new dependency.** Four subcommands and a dozen
options: `click` or `typer` would bring nothing here but a little syntactic
sugar, against one more dependency to install and follow. The options common to
the three audio inputs are moreover declared **only once**, in a parent parser
(`parents=[audio]`) — so there is not even the duplication `click` would remedy.

**Sibling modules are imported inside the functions, not at the top of the
file.** Importing `youtube` pulls in yt-dlp, and `diarize`/`batch` pull in nltk:
**0.72 s paid on every launch**, including for a `--help` or a summary that have
no use for it. With lazy imports, `--help` answers in **0.03 s**. Same reasoning
as for `mlx_whisper`, `whisperx` and `anthropic` elsewhere in the toolkit,
applied one level up.

**`--summarize` re-reads the written file rather than the in-memory text.**
After delegating the transcription, `cli.py` re-reads the output and passes it to
`summarize_text()` — exactly the `summarize` subcommand's path. The
`[SPEAKER_XX] text` format thus keeps a single definition, in `diarize.py`,
instead of being rebuilt here for display.

**In a batch, summarization follows the same resume rule as transcription.**
`batch --summarize` summarizes the files processed **and** those skipped because
their transcript already existed, but skips those whose `_summary.txt` is
already present — unless `--force`. Without the first rule, resuming an
interrupted batch would only summarize the remaining part; without the second,
every rerun would pay for all the API calls again.

**What the unified CLI does not expose.** `--model` (Whisper model) and
`--diarization-model` stay reachable through `python src/transcribe.py` and
`python src/diarize.py`. These are rare settings: exposing them on every
subcommand would have lengthened the help without serving everyday use.

**Three adjustments in the existing modules**, so `cli.py` has nothing to
duplicate: `summarize.summary_path()` (counterpart of `transcript_path()`,
without which there is no telling that a summary already exists),
`batch.report_summary()` (the batch report moves out of `main()` to be callable
from both sides), and `transcribe_youtube()`, which now returns `(text, output
path)` — the name of the file produced depends on the video title, known only
there.

### `app.py` — web interface, presentation only

Exact counterpart of `cli.py`, in the browser: **no** transcription,
diarization, download or summarization logic is written there. The two entry
points coexist and call the same functions, so a fix made in `src/` holds for
both without copying anything.

```
Single file tab ──> received file written into a temporary folder
                ──> transcribe_file() | diarize_file()   ──> output/{name}[_diarized].txt
Folder tab      ──> process_folder()                     ──> succeeded / skipped / failed table
YouTube tab     ──> transcribe_youtube()                 ──> same
                                  │
              "Summarize" box ──> summarize_text()       ──> output/{name}_summary.txt
```

**The received file's name is preserved**, because it is what gives the output
its name: a `lecture.m4a` dropped in the browser produces `output/lecture.txt`,
as in the CLI. It is reduced to its basename before writing — it comes from the
browser, hence from the outside, and a name like `../../x.wav` would write
elsewhere. The audio itself lands in a temporary folder erased right away: only
the transcript survives.

**The "folder" field is confined to an allowed root.** It is the only place in
the app where the user types a free path. With no bound, merely exposing the app
on the network — which Streamlit does by default, see the warning above — would
let anyone list and transcribe any folder on the machine. The root is the
repository's; `WHISPER_TOOLKIT_ROOT` widens it deliberately:

```bash
WHISPER_TOOLKIT_ROOT=~/Documents/courses streamlit run app.py
```

The check goes through `os.path.realpath`, which resolves `..` **and** symbolic
links: neither `/etc`, nor `../../../../etc`, nor a link placed in the
repository leaves the root (verified, Test 11). The intended use stays local;
the guard rail is put in now rather than later.

**The options are declared once for the three tabs** that transcribe a file, as
`cli.py`'s parent `audio` parser does for the three subcommands. The warnings
the CLI prints become greying out here: ticking "Identify speakers" disables the
language field, which whisperx would ignore. *Quick dictation* stays outside:
neither diarization nor summarization makes sense there, it only carries the
language selector over.

**Dictated audio touches the disk only in the system temporary folder.**
`_transcribe_recording()` writes it there — mlx-whisper decodes the file through
ffmpeg, that detour is unavoidable — then erases it in a `finally`, on success
as on failure. Nothing is left to the garbage collector, which promises neither
when it runs nor that it will. Verified: after a transcription, no file in the
repository had been modified and no `.wav` remained in the temporary folder.

**The language is a dropdown, not a free-text field.** That is a direct
consequence of the flaw documented below: a wrong language produces not an error
but a translation. A text field accepted `random language` without flinching;
the selector can only return one of the 30 entries of the `LANGUAGES` constant,
and `LANGUAGES[label]` would raise a loud `KeyError` rather than let anything
else through. Typing filters the list — `Spa` leaves only `Spanish` — without
ever allowing you out of it.

It is a common subset, not the 100 languages Whisper knows: the full list is
only readable in `mlx_whisper.tokenizer.LANGUAGES`, which installs only on Apple
Silicon and costs 0.8 s at import. Reading it from there would make the app
undisplayable elsewhere, for a dropdown. The 29 codes were therefore copied
over, then **checked one by one** against the official list. The CLI stays open
to any Whisper code via `--language` — it is the interface that restricts, not
the toolkit.

**What the app reuses without copying**, beyond the pipeline functions:
`cli.summarize_batch()` for the batch summarization rule — also summarize the
files skipped by the resume logic, but not those whose `_summary.txt` already
exists — and `batch.short_reason()` to reduce the ffmpeg banner to one line in
the table. Both are **public**, and `summarize_batch()` takes explicit
parameters rather than the argparse `Namespace` it read when it only served the
CLI: the same adjustment as `batch.report_summary()` at step 8, for the same
reason — a rule that holds for both entry points does not have to be written
twice, nor go through a command line fabricated for the occasion.

**Heavy imports stay inside the functions**, for the same reason as elsewhere
and one more: Streamlit re-executes the whole script on every interaction, so
anything at the top of the file is paid for on every ticked box.

### `batch.py` — orchestration, not a third pipeline

`batch.py` **contains no audio processing logic**. It lists a folder's files and
delegates, file by file, to one of the two pipelines above:

```
folder ──> list_audio_files()          (filters on SUPPORTED_EXTENSIONS)
       ──> for each file:
             output already present? ──> skipped        (unless --force)
             transcribe_file() + save_transcript()            (default)
             diarize_file()    + save_diarized_transcript()   (--diarize)
       ──> {"success": [...], "failed": [(path, error), ...], "skipped": [...]}
```

It imports `SUPPORTED_EXTENSIONS` from `transcribe.py` instead of redefining it:
adding a format there makes it available here without touching anything.

**Robustness to partial failures.** Each file is processed inside its own
`try/except`: an unreadable file does not interrupt the batch. The final report
lists the failures with their reason, and the process exits with code 1 if at
least one file failed — handy for chaining inside a script.

**Resuming: that is the default behaviour.** Before processing a file,
`batch.py` looks at whether its output already exists in `output/`; if so, it
skips it. Restarting an interrupted batch therefore only redoes what is missing.
`--force` reprocesses everything, existing output or not.

```bash
python src/batch.py my-folder/           # resume: only redoes what is missing
python src/batch.py my-folder/ --force   # reprocesses everything
```

Three points to know:

- **Skipped files are counted separately**, under `"skipped"`, and listed by
  name in the report. It is never a silent skip: a skipped file is neither a
  success nor a failure, and does not change the exit code.
- **Resuming is per mode.** The expected output is `output/{name}.txt` when
  transcribing and `output/{name}_diarized.txt` when diarizing: having already
  transcribed a file does not skip its diarization, and vice versa.
- **Only the file's presence counts, not its content.** An output truncated by
  an interruption mid-write will be considered done; it is `--force` (or
  deleting the `.txt`) that redoes it. In exchange, a failed file produces no
  output at all, so it is properly retried on the next run.

The output paths come from `transcript_path()` and
`diarized_transcript_path()`, exported by the modules that write them.
`batch.py` does not reimplement the naming convention: changing a suffix on one
side cannot desynchronise the resume detection on the other.

**No continuous folder watching.** Plain batch processing covers the real usage
("transcribe all of this week's lectures in one go"). The watchdog mode will
only be added if the need is confirmed.

### `youtube.py` — download, then delegate

Like `batch.py`, this module transcribes nothing itself: it fetches the audio
with yt-dlp and hands over.

```
URL ──> extract_info()      (title + id, without downloading)
    ──> _safe_stem()        (predictable file name)
    ──> download            (test-audio/{name}.opus, gitignored)
    ──> transcribe_file()   or  diarize_file()   (--diarize)
    ──> output/{name}.txt   or  output/{name}_diarized.txt
```

**Downloaded format: `.opus`, chosen after measurement.** YouTube natively
serves an Opus stream, which yt-dlp extracts with `-acodec copy` — so **without
re-encoding**. For a one-minute video: **960 KB as opus against 11.4 MB as
wav**, where wav additionally imposes an ffmpeg pass. `.opus` is already in
`SUPPORTED_EXTENSIONS`, so `transcribe_file()` accepts it as-is. The
`AUDIO_FORMAT` constant at the top of the module is enough to switch to `m4a` or
`wav`.

The detail that settled it: with identical audio content, **the container has no
effect** on the transcription — the same stream as `.m4a` and as `.wav` gives
the same text, word for word, in the same time. What counts is the **source
stream chosen at YouTube**, not the extension. Measurements in Test 7 below.

**Naming.** `_safe_stem()` transliterates the title to ASCII and replaces
everything else with `_`. A title that is entirely non-Latin, empty, or made of
punctuation leaves nothing usable: we then fall back to the YouTube id. A useful
side effect: a title like `../../etc/passwd` becomes `etc_passwd`, so nothing is
written outside `test-audio/`. In exchange, **two videos with the same title
write the same file** — that is the price of a predictable name.

**Language: auto-detected**, as everywhere else since the `fr` default was
removed from `transcribe_file()` — see "Language" below.

### `ffmpeg_path.py` — finding ffmpeg when PATH is not enough

The whole toolkit depends on ffmpeg: `mlx_whisper` and `whisperx` call it as a
subprocess to decode audio, yt-dlp to extract the track. All of them look it up
in `PATH` — and that is exactly where it breaks.

An interactive shell loads `~/.zshrc`, and therefore `/opt/homebrew/bin`. An
Automator app, a `launchd` job, a Finder shortcut: they do not. The process
inherits a minimal PATH (`/usr/bin:/bin:…`) with no ffmpeg in it, **even though
it is installed and works perfectly**. Hence a failure that only happens on a
graphical launch and disappears as soon as you rerun from a terminal — the worst
kind of bug to diagnose.

The module does nothing but look up: `shutil.which()` first, Homebrew locations
(Apple Silicon then Intel) as a fallback. `PATH` stays the authority; those
paths are the safety net.

It is used in **two different ways**, because the two families of callers do not
offer the same handles:

| Caller | Fix | Why |
|---|---|---|
| yt-dlp | `ffmpeg_location` in the download options | it accepts an explicit path: PATH stops mattering entirely |
| `mlx_whisper`, `whisperx` | `ensure_on_path()` at `app.py` startup | they launch `ffmpeg` by its bare name, with no parameter to locate it — PATH is the only handle |

yt-dlp is given the **directory**, not the binary: audio extraction also needs
`ffprobe`, which yt-dlp looks for next to it.

`ensure_on_path()` modifies `os.environ["PATH"]`. That is a deliberate side
effect: it is precisely what subprocesses inherit, hence what has to be
repaired. The call is idempotent. The precedent already exists in the repo —
`diarize.py` sets `NLTK_DATA` in the environment for the same reason.

**The fix is placed in `app.py`, not in `cli.py`.** It is the web interface you
launch from an icon; the CLI always starts from a shell, which has its PATH. If
one day the CLI is launched from Automator, it will need the same call — the
module is there, it is one line.

If ffmpeg still cannot be found, the app says so plainly at load time rather
than letting the failure surface at the bottom of a traceback, once the file has
been dropped and the model loaded.

### `summarize.py` — the only step that leaves the machine

Everything else in the toolkit runs locally. `summarize.py` sends text to the
Claude API: it is the only module that exposes content to an external service,
and the only feature that costs money.

```
transcript (.txt) ──> summarize_text()   (Claude API)
                  ──> output/{name}_summary.txt
```

**It takes a text file, never audio.** Summarization is a separate step chained
after transcription, not one more mode inside `transcribe.py`: you summarize an
already-produced text, possibly corrected by hand, without paying for a
transcription again.

```bash
python src/transcribe.py lecture.m4a          # produces output/lecture.txt
python src/summarize.py output/lecture.txt    # produces output/lecture_summary.txt
```

**API key.** It is read from `.env` under `ANTHROPIC_API_KEY`, the same
mechanism as `HF_TOKEN` — see "Anthropic API key" below. `load_dotenv()` looks
for the `.env` starting from the calling file, so the CLI works from any
directory.

**The system prompt describes the material, not only the task.** It tells the
model the text comes out of speech recognition — misheard words, approximate
punctuation, hesitations — and that it must read through those flaws without
commenting on them. It also tells it that the `[SPEAKER_00]` labels of a
diarized output are arbitrary identifiers, not names. Without that, the model
tends either to comment on the transcription's quality or to invent speaker
names.

**The `style` parameter is free text**, injected as-is into the prompt
(`concise` by default, but `in three bullets` or `for someone who was not there`
work too). No closed enumeration: the model understands the instruction in plain
words, a lookup table would add nothing.

**Default model: `claude-sonnet-5`.** `--model` allows changing it case by case,
`claude-opus-5` being the most capable should the need arise.

**Input guard: 150,000 characters.** Far below the model's context window — it
does not protect the API, it turns an obscure remote refusal into a readable
local error, **before** paying for the call. Beyond that, the module refuses and
invites you to split: there is no automatic chunking, and none is planned as
long as the usage stays meetings and lectures.

Imports between `src/` modules are **flat** (`from transcribe import …`),
because these files run as scripts: `python src/batch.py` puts `src/` at the
front of `sys.path`. A `python -m src.batch` would not work without relative
imports.

### `diarize.py` pipeline

```
audio ──> whisperx.load_model + transcribe   (faster-whisper, CPU)
      ──> whisperx.load_align_model + align  (wav2vec2, word-level timings)
      ──> DiarizationPipeline                (pyannote, gated model)
      ──> whisperx.assign_word_speakers      (labelled segments)
```

## Installation

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

`ffmpeg` has to be installed — it is required by `yt-dlp` **and** by both
Whisper backends, which decode audio by calling it as a subprocess.

It does not need to be on the process's `PATH`: `src/ffmpeg_path.py` finds it in
the usual Homebrew locations if `PATH` does not provide it. That is what makes
it possible to launch the app from somewhere other than a terminal (see
[Test 12](#test-12--ffmpeg-not-found-outside-an-interactive-shell-2026-08-07)).

### Hugging Face token (diarization only)

`diarize.py` builds on `pyannote/speaker-diarization-community-1`, a **gated**
model. So you need to:

1. create a token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens);
2. accept the model's terms on its Hugging Face page;
3. put it in a `.env` file at the root (already ignored by git):

```
HF_TOKEN=hf_xxxxxxxxxxxxxxxx
```

The token can also be passed directly as an argument to `diarize_file()`.
`transcribe.py` does not need it.

### Anthropic API key (summarization only)

`summarize.py` calls the Claude API, which is **paid** — it is the toolkit's
only feature that consumes a budget. Create a key at
[console.anthropic.com](https://console.anthropic.com/settings/keys) and put it
in the same `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

`.env` is ignored by git (`.gitignore:24`, checked with `git check-ignore`) and
has never been tracked. No key appears in the module's error messages: they
quote the variable's name and the console URL, never the value.

The other modules do not need it — the `anthropic` import is lazy, so the rest
of the toolkit works even without the package installed.

### NLTK cache — `.nltk_data/`

During alignment, whisperx downloads the `punkt_tab` sentence tokenizer (~4 MB)
through NLTK. By default NLTK writes it to `~/nltk_data`, at the root of the
user account. `diarize.py` redirects that cache to `.nltk_data/` at the repo
root, so that everything concerning the project stays inside the project.

`.nltk_data/` is a **local, regenerable, never-committed cache**: it is in
`.gitignore`, contains only downloaded third-party data, and rebuilds itself on
the next run. It can be deleted at any time — the only cost is a re-download.

The redirection happens at the top of `diarize.py`, and rests on two NLTK
details that must not be "simplified":

- **`os.environ["NLTK_DATA"]` has to be set before `import nltk`.** At import
  time, `nltk.downloader` instantiates a singleton whose destination folder is
  frozen once and for all. A later `nltk.data.path.insert()` fixes *reading* the
  cache, but no longer *writing* it: the download goes back to `~/nltk_data`.
- **The folder has to exist before the import.** NLTK only keeps a path if it
  exists and is writable. Since `.nltk_data/` is gitignored, it is absent from a
  fresh clone: hence the `os.makedirs(..., exist_ok=True)`.

`batch.py` inherits the configuration by importing `diarize`; `transcribe.py`
(mlx-whisper) touches neither whisperx nor NLTK.

## Installation state per machine

### ⚠️ Mac M5 (Apple Silicon) — target machine, not configured yet

**`mlx-whisper` has to be installed on the M5 Mac.** The package rests on
Apple's MLX framework and only installs on macOS Apple Silicon. It is present in
`requirements.txt` with an environment marker (`sys_platform == "darwin" and
platform_machine == "arm64"`): it is therefore installed automatically on the
Mac, and silently ignored elsewhere.

On the Mac, a plain `pip install -r requirements.txt` is enough.

### Current dev machine — Windows 11, x86_64 (AMD64), Python 3.14.6

This is not an Apple Silicon Mac, so `mlx-whisper` is **not** installed there.

| Package | Status |
|---|---|
| `yt-dlp` | ✅ installed (2026.7.4) |
| `whisperx` | ❌ **not installed** — incompatible with Python 3.14 |
| `mlx-whisper` | ⏭️ ignored (Apple Silicon only) |

**Why whisperx fails here:** every recent version of `whisperx` declares
`Requires-Python >=3.10,<3.14`. pip then falls back to the old 3.2.0 version,
which pins `ctranslate2==4.4.0` — a package with no wheel for Python 3.14. The
installation stops on:

```
ERROR: No matching distribution found for ctranslate2==4.4.0
```

**Fix:** recreate the venv with Python 3.12 (or 3.13), then reinstall:

```powershell
py -3.12 -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

Python 3.12 is not installed on this machine yet (only 3.14 is). This has no
impact on the target machine: on the M5 Mac, using a Python 3.12/3.13 for the
venv is enough.

## Testing Status

Tracking what is **written** vs what is **actually run**. "Tested" here means:
run for real and output checked — not merely compiled. To be updated at every
step.

> The captured terminal output in the tests below is kept **verbatim**, in the
> French the programs emitted at the time. Translating it would falsify the
> record; the surrounding commentary is in English.

| Module / function | Written | Compiles | Actually run | Notes |
|---|---|---|---|---|
| `src/transcribe.py` | ✅ | ✅ | ✅ | validated end to end on 2026-08-06 |
| └ `transcribe_file()` | ✅ | ✅ | ✅ | `whisper-large-v3-mlx`, detected language, `.m4a` `.wav` `.opus` `.ogg` |
| └ `save_transcript()` | ✅ | ✅ | ✅ | `output/*.txt` files created and re-read |
| └ `argparse` CLI | ✅ | ✅ | ✅ | `--help`, nominal run, exit codes |
| └ missing file error | ✅ | ✅ | ✅ | clear message + `exit 1` |
| └ extension error | ✅ | ✅ | ✅ | clear message + `exit 1` |
| `src/diarize.py` | ✅ | ✅ | ✅ | full pipeline validated on 2026-08-06 |
| └ faster-whisper ASR | ✅ | ✅ | ✅ | `large-v3` int8 CPU, `fr` language detected on its own |
| └ wav2vec2 alignment | ✅ | ✅ | ✅ | 9 words aligned, word-level timings |
| └ `DiarizationPipeline` | ✅ | ✅ | ✅ | **2 speakers out of 2 separated correctly** |
| └ `assign_word_speakers()` | ✅ | ✅ | ✅ | distinct labels on both segments |
| └ `save_diarized_transcript()` | ✅ | ✅ | ✅ | `[SPEAKER_XX] text` format verified |
| └ `diarization_model` | ✅ | ✅ | ✅ | tested via `--diarization-model` on another repo |
| └ `_resolve_token()` | ✅ | ✅ | ✅ | missing token detected, clear message |
| └ 401 vs 403 error | ✅ | ✅ | ✅ | distinct messages, checked over real HTTP |
| └ missing file error | ✅ | ✅ | ✅ | clear message + `exit 1` |
| └ `--num-speakers` | ✅ | ✅ | ✅ | `2` honoured on the 2-voice fixture |
| `src/batch.py` | ✅ | ✅ | ✅ | validated on 2026-08-07 |
| └ `list_audio_files()` | ✅ | ✅ | ✅ | filters extensions, ignores `.txt` and subfolders |
| └ `process_folder()` | ✅ | ✅ | ✅ | transcription mode and `--diarize` mode |
| └ partial failure | ✅ | ✅ | ✅ | **the batch carries on**, 2/3 processed with a corrupted file |
| └ `--num-speakers` forwarded | ✅ | ✅ | ✅ | `[2, 2]` bound properly received by pyannote |
| └ `short_reason()` | ✅ | ✅ | ✅ | 13-line ffmpeg banner reduced to 1 |
| └ folder missing / empty | ✅ | ✅ | ✅ | `exit 1` / `exit 0` with a message |
| `src/youtube.py` | ✅ | ✅ | ✅ | validated on 2026-08-07 (Test 7) |
| └ `transcribe_youtube()` | ✅ | ✅ | ✅ | returns `(text, path)` since step 8 |
| `src/summarize.py` | ✅ | ✅ | ✅ | `claude-sonnet-5`, 26/26 facts captured over 2,411 words, ≈ $0.039 (Test 9) |
| └ `summary_path()` | ✅ | ✅ | ✅ | added at step 8, exercised by `batch --summarize` resuming |
| `src/cli.py` | ✅ | ✅ | ✅ | validated on 2026-08-07 (Test 10) |
| └ `transcribe` | ✅ | ✅ | ✅ | alone, and with `--diarize --num-speakers 2 --summarize` |
| └ `batch` | ✅ | ✅ | ✅ | 2 successes / 1 isolated failure, resuming at two levels |
| └ `youtube` | ✅ | ✅ | ✅ | NASA video, with `--summarize` |
| └ `summarize` | ✅ | ✅ | ✅ | `--model claude-haiku-4-5` and `--style` verified |
| └ chained `--summarize` | ✅ | ✅ | ✅ | on all three audio inputs |
| └ option warnings | ✅ | ✅ | ✅ | `--num-speakers` without `--diarize`, `--language` with it |
| └ exit codes | ✅ | ✅ | ✅ | `0` / `1`, partial batch failure included |
| └ lazy imports | ✅ | ✅ | ✅ | `--help` in 0.03 s against 0.72 s with direct imports |
| `app.py` | ✅ | ✅ | ✅ | validated on 2026-08-07 in a real browser (Test 11) |
| └ *Single file* tab | ✅ | ✅ | ✅ | upload → `output/two_voices_generated.txt` |
| └ *Folder (batch)* tab | ✅ | ✅ | ✅ | 2 successes / 1 isolated failure, then a resume with 2 skipped |
| └ *YouTube* tab | ✅ | ✅ | ✅ | NASA video, alone or with a chained summary |
| └ "Summarize" box | ✅ | ✅ | ✅ | real call, summary displayed and written to `output/` |
| └ allowed root | ✅ | ✅ | ✅ | `/etc` and `../../../../etc` refused |
| └ language / speakers greying | ✅ | ✅ | ✅ | equivalent of the CLI's warnings |
| └ language selector | ✅ | ✅ | ✅ | invalid value impossible, forced `en` confirmed by the translation |
| `src/ffmpeg_path.py` | ✅ | ✅ | ✅ | validated on 2026-08-07 under a stripped PATH (Test 12) |
| └ `find_ffmpeg()` | ✅ | ✅ | ✅ | via `PATH`, and via the Homebrew fallback when `which` fails |
| └ `ensure_on_path()` | ✅ | ✅ | ✅ | `PATH` fixed, idempotent call verified |
| └ `ffmpeg_location` (yt-dlp) | ✅ | ✅ | ✅ | download succeeded with no ffmpeg on `PATH` |
| `src/__init__.py` | ✅ (empty) | ✅ | n/a | plain package marker |
| Folder watching | ❌ | — | — | deliberately not implemented |
| `tests/` | ❌ empty | — | — | no automated tests |

### Real transcriptions run (2026-08-06)

The test audio files live in `test-audio/`, **ignored by git** — this
repository is public, no real recording must be versioned in it. The only
exception: the entirely synthetic fixture of test 4. The content of transcripts
of real recordings is not reproduced here, for the same reason.

**Test 1 — synthetic sample (macOS `Thomas` voice, fr_FR, 6.3 s, `.m4a`)**

| | |
|---|---|
| **Expected text** | « Bonjour, ceci est un test de transcription pour le projet whisper toolkit. Il fait beau aujourd'hui à Paris. » |
| **Text obtained** | « Bonjour, ceci est un test de transcription pour le projet Wisp et Tolkien. Il fait beau aujourd'hui à Paris. » |

The only discrepancy: "whisper toolkit" → "Wisp et Tolkien". That is an artefact
of the sample, not of the model — the French voice pronounces those two English
words the French way, and Whisper faithfully transcribes what it hears.
Punctuation, accents and apostrophes are correct.

**Test 2 — real WhatsApp voice note (human voice, fr, 2.47 s)**

Source: `.opus` mono 48 kHz (ogg container, 18.6 kbit/s). Transcription
**correct**: coherent sentence, correct punctuation and accents, despite
WhatsApp's heavy compression and a very short duration. Content not reproduced
(public repository).

The same excerpt was run in four forms — `.opus`, `.ogg` (remuxed opus), `.ogg`
(stereo vorbis) and `.wav` 16 kHz mono — with output **identical down to the
character** in all four cases.

> **Why no conversion is done in the code.** `mlx_whisper` already decodes
> everything through ffmpeg, imposing 16 kHz mono itself
> (`ffmpeg -i <file> -f s16le -ac 1 -ar 16000 -`, see `mlx_whisper/audio.py`).
> Converting upstream would therefore redo exactly the same work, twice over and
> with a temporary file to manage. `SUPPORTED_EXTENSIONS` serves only as a guard
> rail to reject an obviously non-audio file early; any format ffmpeg reads
> works as soon as it appears there.

**Performance** (M5 Mac, `whisper-large-v3-mlx`):

| Run | Duration | Detail |
|---|---|---|
| 1st | 4 min 16 s | of which 3 min 49 s downloading the model (~3 GB) |
| Subsequent | 3.1 – 3.6 s | model cached, for 2.5 – 6.3 s of audio |

Time is dominated by loading the model, not by the audio's duration: these
measurements say nothing about throughput on a long file.

### Test 3 — `diarize.py`, full pipeline validated (2026-08-06)

**Diarization runs end to end.** After accepting the terms of
`pyannote/speaker-diarization-community-1`, the entire pipeline runs without
error on the WhatsApp voice note (2.47 s, `.opus`):

| Pipeline step | Status | Measured detail |
|---|---|---|
| `whisperx.load_audio` | ✅ | 39,256 samples at 16 kHz |
| `whisperx.load_model` | ✅ | `large-v3` int8 CPU |
| pyannote VAD | ✅ | ran without error |
| `.transcribe()` | ✅ | `fr` language detected on its own (confidence 1.00), 1 segment |
| `load_align_model` + `align` | ✅ | 9 words aligned, segment 0.28 s → 2.40 s |
| `DiarizationPipeline` | ✅ | `community-1` loaded on CPU |
| `assign_word_speakers` | ✅ | `speaker` key present on the segment |
| `save_diarized_transcript()` | ✅ | `output/..._diarized.txt` file written and re-read |

Output: one line in `[SPEAKER_00] <text>` format, exactly the expected shape
(content not reproduced, public repository). **Full run: 18.1 s**, models cached.

A single speaker here, the sample being single-speaker: this test validates the
pipeline's execution, not voice separation. That is what test 4 is for.

**History of the blockage** (resolved). The first run with a valid token failed
with a **403**: `community-1`'s terms had not been accepted on the account,
although the 3.1 family's had. No parameter offered a way around it — with
`pyannote.audio` 4.0.7, pointing explicitly at `speaker-diarization-3.1` still
demands `plda/xvec_transform.npz`, hosted in `community-1`, and falls back to a
401.

> ℹ️ **The token is only required at the first download.** Once the pyannote
> weights are in the local cache, `Pipeline.from_pretrained` stops consulting
> it: an invalid token, or none at all, then passes without error. Observed
> while trying to replay the error cases after a successful run.

**Divergence between the two backends.** On the same excerpt, faster-whisper and
mlx-whisper produce transcripts that differ by one word (58 vs 57 characters).
Nothing abnormal — two implementations, two quantizations — but worth keeping in
mind: the two pipelines are not interchangeable down to the character.

**The CPU cost is measured, not assumed** (models cached):

| Step | Duration |
|---|---|
| `load_model` | 5.6 s |
| `.transcribe()` | **10.4 s** for 2.47 s of audio |
| `load_align_model` | 0.3 s |
| `align` | 0.1 s |
| **Total** | **17.6 s** |

That is **~4× slower than real time** on transcription alone, where
`transcribe.py` handles the same file in 3.1 s end to end — the expected gap
between MLX/Metal and CTranslate2/CPU. First run: 15 min 42, dominated by
downloading the models (`large-v3` CTranslate2 + French wav2vec2).

**Errors verified under real conditions:**

The three token cases are now **told apart**, each checked against a real HTTP
response:

| Case | Message produced | Verified with |
|---|---|---|
| Token missing | "Hugging Face token not found" + link to the token settings | `load_dotenv` neutralised, `HF_TOKEN` removed |
| Invalid token (**401**) | "Token rejected" → regenerate the token | bogus token on an uncached gated repo |
| Terms not accepted (**403**) | "Access denied to model *X*" → direct link to the HF page **of the requested model** | valid token on `pyannote/speaker-diarization` |
| File not found | `File not found: ...` | non-existent path |

All four exit with `exit 1`. The 403 case names the model actually requested, so
the link stays correct even with `--diarization-model`.

### Test 4 — separating two speakers (2026-08-07)

The first test that validates diarization's **reason for existing**, and not
merely its execution. Fixture: `test-audio/two_voices_generated.wav`, 9.5 s.

**Ground truth**, established by measurement rather than by trust:

| | |
|---|---|
| Voice 1 | `Amélie` (fr_CA), median F0 **225 Hz**, 0 → 4.06 s |
| Voice 2 | `Thomas` (fr_FR), median F0 **128 Hz**, 4.06 → 9.48 s |
| Switch | **4.06 s** (end of the first line) |

**Result**, with `--num-speakers 2`:

| start | end | speaker | voix réelle |
|---|---|---|---|
| 0,23 s | 4,08 s | `SPEAKER_01` | Amélie |
| 4,13 s | 9,36 s | `SPEAKER_00` | Thomas |

| Criterion | Expected | Obtained | |
|---|---|---|---|
| Number of speakers | 2 | 2 | ✅ |
| Number of segments | 2 | 2 | ✅ |
| Switch point | 4.06 s | 4.08 – 4.13 s | ✅ within **±70 ms** |
| Voices mixed up | none | none | ✅ |

The 20 to 70 ms discrepancy corresponds to the silence between the two lines:
the boundaries fall on either side of the real junction. Full run: 17.5 s.

> ⚠️ **`SPEAKER_XX` labels do not follow the order of appearance.** Here Amélie
> speaks first and receives `SPEAKER_01`, while Thomas receives `SPEAKER_00`.
> Never assume `SPEAKER_00` is the first to speak: the identifiers are arbitrary
> and stable only within a single run.

**About the fixture.** `test-audio/two_voices_generated.wav` is the repository's
only versioned audio file (an explicit exception in `.gitignore`). It is
**entirely synthetic**, generated with the macOS `say` command from two system
voices, then concatenated with ffmpeg:

```bash
say -v "Amélie" -o a.aiff "…"      # mind the accent, see below
say -v Thomas   -o b.aiff "…"
# conversion to 16 kHz mono wav, then ffmpeg concat
```

No real voice, no personal data. It serves as a non-regression fixture for
`diarize.py`.

> ⚠️ **`say` trap: the voice name has to be exact, accents included.**
> `say -v Amelie` (without the accent) raises **no error** — the command
> silently falls back to the default voice. You then get two excerpts of the
> *same* voice, and a fixture that tests nothing. The check that revealed it:
> measuring the F0 of both excerpts before using them. 225 Hz against 128 Hz
> validates the fixture; two neighbouring values disqualify it.

### Test 5 — `batch.py`, robustness to partial failures (2026-08-07)

A test folder set up outside the repository, deliberately containing what it
takes to make the batch fail:

| File | Nature | Expected |
|---|---|---|
| `01_deux_voix.wav` | synthetic 2-voice fixture, 9.5 s | processed |
| `02_vocal.wav` | real recording, single speaker | processed |
| `03_corrompu.wav` | text file renamed to `.wav` | **isolated failure** |
| `04_ignore.txt` | non-audio extension | ignored at listing |
| `sous_dossier/` | directory | ignored at listing |

**Result, transcription mode** (`python src/batch.py <folder>`):

| Criterion | Obtained | |
|---|---|---|
| Files listed | 3 out of 5 entries | ✅ `.txt` and folder set aside |
| Processed successfully | 2 | ✅ |
| Failures | 1 (`03_corrompu.wav`) | ✅ isolated |
| The batch carried on after the failure | yes | ✅ |
| Output produced for the failing file | none | ✅ |
| Exit code | 1 | ✅ partial failure reported |
| Duration | 6.9 s | |

**Result, diarization mode** (`--diarize --num-speakers 2`): same counts, 2
successes and 1 isolated failure, `*_diarized.txt` outputs produced, 39.5 s. The
`--num-speakers 2` bound did reach pyannote — it reported it as unreachable on
the single-speaker file, which confirms the parameter propagates through
`batch.py`.

Edge cases checked separately: non-existent folder → clear message and
`exit 1`; folder with no audio file at all → message and `exit 0`, without
error.

> **Readability of the report.** When ffmpeg fails, it spits out its build
> banner: the raw error of the corrupted file is **13 lines and 1,173
> characters**, which drowned the entire batch report. `short_reason()` reduces
> it to its first line for display. The full error stays reachable in the dict
> returned by `process_folder()`.

### Test 6 — `batch.py` resuming (2026-08-07)

Run on `test-audio/`, which contains **6 files, all processable** (`.opus`,
`.ogg` ×2, `.wav` ×3), after setting `output/` aside to start from a clean
state. Three successive runs, in transcription mode:

| # | Command | Processed | Skipped | Output |
|---|---|---|---|---|
| 1 | `batch.py test-audio/` | 6 | 0 | 6 `.txt` created, 8.7 s |
| 2 | `batch.py test-audio/` | 0 | **6** | no rewriting, `exit 0` |
| 3 | `batch.py test-audio/ --force` | 6 | 0 | 6 `.txt` rewritten |

Run 3 was validated on the **mtimes** and not on the display alone: the six
timestamps move from `12:03:4x` to `12:04:0x`, so the files really were
rewritten, not merely re-announced.

Complementary cases checked:

| Scenario | Expected | Obtained |
|---|---|---|
| Deleting **one** output out of 6, rerun | 1 processed, 5 skipped | ✅ |
| `--diarize` while the 6 `.txt` exist | nothing skipped | ✅ 2/2 diarized |
| `--diarize` rerun afterwards | 2 skipped | ✅ |
| Transcription rerun after diarization | 2 skipped | ✅ |

> **The test that really counts is the one crossing the modes.** A naive
> implementation looking for "any output for this file" would have skipped the
> diarization of already-transcribed files — and the batch would have appeared
> to succeed while producing nothing. That is why the expected output is asked
> of `transcript_path()` / `diarized_transcript_path()` depending on the mode,
> rather than rebuilt inside `batch.py`.

### Test 7 — `youtube.py` (2026-08-07)

Test video: `V0oo_Nybo6w`, "NASA Artemis II: Counting Down to Our Next Moon
Mission", 60 s, official NASA channel. Chosen because a NASA production is in
the public domain (a work of the US government) and because its duration keeps
the test fast. **Neither the audio nor the transcript is versioned** —
`test-audio/*` and `output/` are ignored, checked with `git check-ignore`.

**Format choice: measured, not assumed.** The starting point was "`.wav` or
`.m4a`". The measurement showed the question was badly posed.

| Source | Container | Time | Words | Subtitle ref. |
|---|---|---|---|---|
| AAC stream | `.m4a` | 20.1 s | 338 | 121 |
| AAC stream | `.wav` | 20.3 s | 338 | 121 |
| Opus stream | `.m4a` | 5.0 s | 124 | 121 |
| Opus stream | `.wav` | 5.0 s | 123 | 121 |

With identical content, the two containers give **exactly** the same result (3
runs each, figures stable to the tenth). The container therefore does not come
into it; only the **source stream** matters. On this video, the AAC stream goes
into a hallucination loop: 338 words instead of 121, including `the` **77
times**, i.e. 23% of the text.

Checked on 3 other short NASA videos, transcription compared against YouTube's
automatic subtitles taken as a reference:

| Video | AAC | Opus | Ref. |
|---|---|---|---|
| `XYMuC2MDbwo` | 7.8 s / 176 words | 6.1 s / 179 words | 168 |
| `MLgYJh6OFbY` | 36.5 s / 143 words | 15.1 s / 130 words | 130 |
| `oqRwrlJbjOg` | 33.3 s / 141 words | 5.6 s / 132 words | 131 |

The Opus stream is faster in all 4 cases (up to 6×) and closer to the reference.
Hence the choice of `.opus`: a better input for Whisper, no re-encoding
(`-acodec copy`, verified in the ffmpeg command line yt-dlp emits), and 12×
lighter than the wav.

> ⚠️ **The first real run produced an entirely wrong transcription.** The audio
> is English, but `transcribe.py` was forcing `language="fr"` at the time:
> Whisper returned an invented French text, fluent and plausible, that bore only
> a distant relation to the original. Nothing in the output flagged the problem.
> After the fix, the transcription matches the YouTube subtitles (123 words
> against 121 in the reference).
>
> The fix applied here was local to `youtube.py`. The flaw also held for
> `transcribe.py` and `batch.py`: it was removed at the root in Test 8.

**Functional results:**

| Scenario | Expected | Obtained |
|---|---|---|
| CLI, auto-detection | correct English transcription | ✅ 8.6 s end to end |
| CLI, `--language en` | identical | ✅ |
| CLI, `--diarize` | labelled segments | ✅ 13 segments, 2 speakers, 73.5 s |
| Downloaded audio | in `test-audio/`, ignored | ✅ `.gitignore:44` |
| Transcript | in `output/`, ignored | ✅ `.gitignore:54` |

**Error handling**, messages verified on real URLs:

| Case | Obtained |
|---|---|
| Non-existent id | « Vidéo indisponible … supprimée, privée, ou identifiant erroné » |
| A string that is not a URL | same (yt-dlp treats it as an id) |
| Non-YouTube URL returning 404 | « Échec du téléchargement » + yt-dlp detail |
| Pure playlist URL | explicit refusal, « 8 vidéos … passe l'URL d'une vidéo » |
| `watch?v=…&list=…` URL | the single video is processed, title preserved |

> ⚠️ **A playlist URL would have downloaded 8 videos under a single name.**
> `noplaylist` only settles `watch?v=…&list=…` URLs; on a pure playlist URL,
> yt-dlp returns all 8 entries. Since the name template is fixed before
> downloading, the 8 files would have overwritten one another and only the last
> video would have been transcribed — under the playlist's title, without the
> slightest warning. Hence the explicit refusal in `download_audio()`.
>
> The guard itself cost a fix: `extract_flat=True`, added so as not to resolve
> the 8 entries, *also* flattened the single video, which lost its title and
> fell back to the id. `in_playlist` is what is needed, not `True`.

yt-dlp's raw message was displayed **in addition to** the rephrased one:
`quiet=True` does not cover errors, which go to stderr whatever happens. A mute
`logger` passed to `YoutubeDL` settles it.

Cases **not tested** for want of being able to provoke them: a genuinely private
video, a region-blocked video. Their detection rests on message patterns
(`private video`, `not available in your country`) taken from the yt-dlp
documentation, never triggered under real conditions.

Naming verified unit by unit — accents transliterated (`Café à la crème` →
`Cafe_a_la_creme`), a Japanese title and a pure-punctuation title falling back
to the id, truncation at 80 characters, and `../../etc/passwd` neutralised into
`etc_passwd`.

### Test 8 — language detection generalised (2026-08-07)

The `language="fr"` default of `transcribe_file()` is removed. The default also
affected `batch.py`, which called `transcribe_file()` with no argument: Test 7
had only brought one symptom out of three to light.

**No degradation** on French content, measured before changing the default. For
each fixture, `language="fr"` then `language=None`:

| Fixture | forced `fr` | auto | detected | text |
|---|---|---|---|---|
| `conversation_test.wav` | 0.85 s | 1.21 s | `fr` | identical |
| `two_voices_generated.wav` | 1.40 s | 1.78 s | `fr` | identical |
| `whatsapp_test.wav` | 0.79 s | 1.17 s | `fr` | identical |
| `WhatsApp Audio ….opus` | 0.79 s | 1.17 s | `fr` | identical |
| `test_vorbis.ogg` | 0.79 s | 1.14 s | `fr` | identical |

The text is **strictly identical** in all five cases — detection does not change
the result, it only avoids corrupting it when the language differs.

The overhead is **fixed, not proportional**: constant around 0.35 s on these
short fixtures, and 0.32 s on a 76 s French file (61.39 s → 61.71 s, i.e. 0.5%).
Detection runs only once, on the first window.

> ⚠️ **Forcing the language produces a translation, not an error.** The French
> fixture run with `--language en` comes back in perfectly fluent English:
> "Hello, did you have time to look at the supplier's file this morning?" where
> the audio says « Bonjour, est-ce que tu as eu le temps de regarder le dossier
> fournisseur ce matin ? ». No warning, no error code, a plausible output. It is
> the same flaw as in Test 7, reproduced in the other direction — and the reason
> a hard-coded language default has no place here.

**Functional checks:**

| Scenario | Obtained |
|---|---|
| `transcribe.py` without `--language` on a fr fixture | ✅ correct French |
| `transcribe.py --language en` on the same one | ✅ translated — flaw reproduced |
| `batch.py --force` on a **mixed** `test-audio/` | ✅ 7/7, each in its own language |
| `batch.py --language en` | ✅ forcing propagated down to `transcribe_file()` |
| `batch.py --force` afterwards | ✅ back to French |

The mixed batch is the test that counts: `test-audio/` contains 6 French files
and Test 7's English NASA video. A single pass transcribes each in its own
language. With the old default, the English video would have come back as
invented French, without the batch report flagging anything.

`youtube.py` loses its `kwargs.setdefault("language", None)` in the process,
which was only a local workaround for the now-deleted default.

### Test 9 — `summarize.py`, real call on a long transcript (2026-08-07)

The first test with credits on the account: the API call did happen and a
summary was produced. The first attempt's blockage (`HTTP 400`, insufficient
balance) is lifted — the corresponding error branch stays in place and had been
validated at that moment.

**About the test text.** The transcripts in `output/` add up to fewer than 400
words all together: concatenating them did not give a representative case. The
test transcript is therefore **written by hand** — a project follow-up meeting
in French, **2,411 words / 14,495 characters**, with `[SPEAKER_XX]` labels,
hesitations, repetitions and interrupted sentences.

> ⚠️ It **simulates** a speech recognition output, it is not one. The flaws are
> plausible but chosen; a real ASR gets things wrong differently, particularly
> on proper nouns and figures. This test validates the summary's behaviour on a
> long, noisy text, not its robustness to Whisper's real errors.

In exchange, since the text is written, **the ground truth is known**: 26
verifiable facts were deliberately planted in it — decisions, actions, amounts,
dates, one settled disagreement and one deliberately unsettled topic.

**Run measurements:**

| | |
|---|---|
| Model | `claude-sonnet-5` |
| Duration | 15.1 s |
| Tokens | 6,935 in, 1,237 out |
| Cost | ≈ **$0.039** per summary (Sonnet rate $3/$15 per MTok) |
| Compression | 470 words for 2,400, i.e. 20% |
| `stop_reason` | `end_turn` — no truncation |

**Coverage: 26 / 26 planted facts found**, checked by script rather than by eye.
Including the secondary details (12,000 users of the old portal, contractual
penalties capped at ~€3,000) that a first run had left aside — coverage
therefore varies from one call to the next.

**Nothing invented.** Systematic check of the output: the sixteen numeric values
in the summary (€240,000, €180,000, €60,000, €15,000–25,000, €3,000, 12,000, 23
tickets, 80%, 5 years, 4 h…) all appear in the transcript, and so do the six
proper nouns cited (Kepler, Amélie, Thomas, Karim, Léa, OVH).

**Structure and reading.** A title, an opening sentence placing the meeting, key
points in batches, then a decisions/actions section naming names. Three
behaviours that were not a given:

- The **disagreement** is rendered as a disagreement — both positions are laid
  out in the key points, and the arbitration appears separately in the
  decisions, without the summary taking sides.
- The **unsettled** topic (hosting) is marked as such, "put on hold, to be
  reopened once payment is secured", instead of being presented as decided or
  omitted.
- The `[SPEAKER_XX]` labels are **kept and matched** to the first names spoken
  in the meeting, without inventing any. The transcript contained a deliberate
  diarization inconsistency — `SPEAKER_00` asks Karim a question then answers it
  — and the model resolved it coherently rather than getting lost in it.

**Input guard**, checked at the bounds: 150,000 characters pass, 150,001 raise
"Transcript too long" without calling the API.

**What this test does not say.** A single call, a single text, a single
language, a single style (`concise`). Variation between runs is real — it showed
across two calls. And since the text is written by us, the coverage measured is
an optimistic ceiling compared with a real Whisper transcript.

### Test 10 — `cli.py`, the four subcommands under real conditions (2026-08-07)

Each subcommand was run for real, not merely with `--help`.

| Command | Result | Duration |
|---|---|---|
| `transcribe test-audio/two_voices_generated.wav` | correct French text, `output/two_voices_generated.txt` | 4.0 s |
| `transcribe … --diarize --num-speakers 2 --summarize` | 2 speakers separated **then** a chained summary | 23.4 s |
| `batch <folder> --summarize` | 2 transcripts + 2 summaries, 1 isolated failure, `exit 1` | — |
| `youtube 'https://youtu.be/V0oo_Nybo6w' --summarize` | English transcription + French summary | 19.8 s |
| `summarize output/…NASA….txt --style "en trois puces exactement"` | exactly 3 bullets | — |

**The `--diarize --summarize` chain is the case that counts**: it crosses the
toolkit's two furthest-apart modules in one command. Output obtained on the
2-voice fixture — `[SPEAKER_01]` then `[SPEAKER_00]`, consistent with Test 4 —
and the summary written to
`output/two_voices_generated_diarized_summary.txt`, not to `…_summary.txt`: it
really is the **diarized** output that was summarized, and the file name says so.

**Batch resuming, verified across three successive runs.** Test folder set up
outside the repository: two valid audio files, one corrupted `.wav`, one `.txt`.

| # | Starting state | Processed | Skipped | Summaries | Code |
|---|---|---|---|---|---|
| 1 | nothing in `output/` | 2 | 0 | 2 produced | 1 *(corrupted file)* |
| 2 | everything is there | 0 | 2 | **2 skipped — no API call** | 1 *(same)* |
| 3 | one `_summary.txt` deleted, corrupted file removed | 0 | 2 | 1 regenerated | 0 |

Run 2 takes **2.0 s** and costs nothing: that is what this test checks. Run 3
checks the other half of the rule — a skipped transcript stays a candidate for
summarization, otherwise resuming an interrupted batch would only summarize the
remaining part.

**Errors and warnings**, all verified for real:

| Case | Obtained |
|---|---|
| `transcribe` missing file / unsupported extension | clear message, `exit 1` |
| `batch` folder not found | « Dossier introuvable : … », `exit 1` |
| `summarize` missing file | « Fichier introuvable : … », `exit 1` |
| `--num-speakers` without `--diarize` | « Attention : --num-speakers est ignoré sans --diarize. » |
| `--language` with `--diarize` | equivalent warning (whisperx detects on its own) |

**The modules stay usable on their own.** `batch.py`, `youtube.py` and
`summarize.py` were rerun directly after the refactor: identical batch report,
`youtube.py` now also displays the output path, `summarize.py`'s help unchanged.

> ⚠️ **An observation outside the CLI's scope, but worth noting.** The
> `--model claude-haiku-4-5` test did route the model, but on a transcript of a
> **single sentence** (75 characters) Haiku answered as if being addressed
> directly — "I do not have access to external files…" — instead of
> summarizing. Sonnet, on a text that short, correctly says the text is too
> short to summarize. `summarize.py`'s system prompt has only been calibrated on
> Sonnet; `--summary-model` therefore remains something to use knowingly.

### Test 11 — `app.py`, the three tabs in a real browser (2026-08-07)

The app was launched (`streamlit run app.py`) and driven in Chromium, not merely
imported: each tab was used the way a user would — dropping a file, typing a
path, clicking the button — and the rendering checked on a screenshot.

| Tab | Scenario | Result |
|---|---|---|
| Single file | dropping `two_voices_generated.wav` | correct French text, `output/two_voices_generated.txt`, download button |
| Folder (batch) | 3 audio files + 1 `.txt` + 1 corrupted `.wav` | **2 successes / 0 skipped / 1 failure**, the `.txt` ignored at listing |
| Folder (batch) | same folder rerun | **0 / 2 skipped / 1**, resuming visible in the table |
| YouTube | `https://youtu.be/V0oo_Nybo6w` (NASA) | English transcription consistent with Test 7 |
| YouTube | the same, "Summarize" box ticked | French summary displayed **and** written to `output/` |

Durations measured end to end from the driving script — browser launch and page
load included, therefore inflated compared with the processing alone: 9.5 s for
the file tab, 12.0 s for the 3-file batch, 14.7 s for the NASA video, 21.5 s
with the chained summary. No Streamlit exception (`stException`) on any run.

**The corrupted file is the case that counts** in the batch tab: processing
reaches the end, the failing row appears in the table with the ffmpeg banner
reduced to one line by `batch.short_reason()`, and the other two files are
transcribed. That is the CLI's behaviour (Test 5), obtained without rewriting it.

**Allowed root, verified by trying to get around it** rather than by reading the
code:

| Input | Obtained |
|---|---|
| `test-audio/batch_demo` | accepted, batch processed |
| `/etc` | refused — « Chemin hors de la racine autorisée : /private/etc » |
| `../../../../etc` | refused, identical message |

The path shown in the refusal is `/private/etc` and not `/etc`: `realpath`
resolved macOS's symbolic link **before** the containment test. That is exactly
what it is there for.

**Interface edge cases checked:** "Transcribe" button greyed out as long as no
file is dropped, language field greyed out as soon as "Identify speakers" is
ticked, "number of speakers" field greyed out in the opposite case.

**Language selector** (replacing the first draft's free-text field, which
accepted `langue random`):

| Test | Obtained |
|---|---|
| Dropdown | 30 entries, "Auto-detect" at the top and by default |
| `Esp` filter | a single suggestion, `Espagnol` |
| `langue random` filter | **"No results"**, nothing to select |
| Same input + `Enter` + losing focus | the field returns to "Auto-detect", the input is discarded |
| The 29 codes | all present in `mlx_whisper.tokenizer.LANGUAGES`, no duplicates |
| *Folder* and *YouTube* tabs | same selector, a single declaration in `_audio_options()` |

**The value passed through was verified by the discrepancy, not by the display.**
Selecting "French" on a French fixture proves nothing: auto-detection would have
returned the same text. It is "English" on that same fixture that settles it —
the output comes back translated into English, word for word the one from Test 8
("Hello, did you have time to look at the supplier's file this morning?"). The
`en` code therefore did reach `transcribe_file()`. Switched back to "French", the
correct French text returns.

> The selector's labels were French at the time of this test — the dropdown now
> reads "Auto-detect", "French", "English". The codes sent to Whisper are
> unchanged.

**What this test does not say.** The batch fixtures were small files set up for
the occasion, in a temporary subfolder of `test-audio/`. Diarization was **not**
exercised from the app — the path is the same `diarize_file()` call as in the
CLI, but that is not a verification. A single browser (Chromium), a single
session, no test of two browser tabs open at once on the same app.

### Test 12 — ffmpeg not found outside an interactive shell (2026-08-07)

**Symptom:** the YouTube tab fails with "ffprobe and ffmpeg not found. Please
install or provide the path using --ffmpeg-location", even though ffmpeg is
installed and the CLI works. Observed with the app launched by an Automator app,
which runs the script without going through a full interactive shell.

**Cause, reproduced identically.** `ffmpeg` is in `/opt/homebrew/bin`, which
only a shell that has loaded `~/.zshrc` puts on `PATH`:

```bash
env PATH=/usr/bin:/bin sh -c 'command -v ffmpeg'   # → nothing
```

**The bug had two halves, not one.** The error message only showed the first,
because the download failed before reaching the second:

| `transcribe_youtube()` step | Under a stripped PATH, before the fix |
|---|---|
| yt-dlp download | ❌ "ffprobe and ffmpeg not found" |
| `mlx_whisper` transcription | ❌ "[Errno 2] No such file or directory: 'ffmpeg'" |

Fixing only yt-dlp would therefore have moved the failure one notch instead of
lifting it — verified: with `ffmpeg_location` alone, the download goes through
and then the transcription hits `Errno 2`. Hence the two fixes.

**After the fix:**

| Scenario | Result |
|---|---|
| `streamlit run app.py` from a terminal | ✅ full YouTube tab, transcription as expected |
| `env PATH=/usr/bin:/bin … streamlit run app.py` | ✅ **identical**, download and transcription |
| `cli.py youtube` from a terminal | ✅ no regression, `exit 0` |
| `cli.py transcribe` from a terminal | ✅ no regression |

Mechanics verified under `PATH=/usr/bin:/bin`: `shutil.which("ffmpeg")` returns
`None`, the Homebrew fallback finds `/opt/homebrew/bin/ffmpeg`,
`ensure_on_path()` turns `PATH` into `/opt/homebrew/bin:/usr/bin:/bin`, and a
second call does not duplicate it.

> ⚠️ **What the error message did not say.** "ffmpeg not found" on a machine
> where `which ffmpeg` answers is almost always a problem of inherited `PATH`,
> not of installation. The reflex — reinstalling ffmpeg — could not have helped
> here.

**What this test does not say.** The restricted PATH is *simulated* with `env`:
the real Automator app was not relaunched to confirm, and its actual PATH was
not recorded. `/usr/local/bin` (Homebrew on Intel) is among the fallback
locations but has never been exercised — this machine is Apple Silicon. The case
"ffmpeg genuinely absent from the machine" was not provoked: the app's error
banner has therefore never been seen.

### Test environment (checked on 2026-08-06)

M5 Mac (`Darwin arm64`) — everything is in place:

| Élément | Statut |
|---|---|
| `venv/` | ✅ Python 3.12.13 |
| `mlx-whisper` | ✅ 0.4.3 (avec `mlx` 0.32.0) |
| `whisperx` | ✅ 3.8.6 |
| `yt-dlp` | ✅ 2026.7.4 |
| `python-dotenv` | ✅ 1.2.2 |
| `ffmpeg` | ✅ 8.1.2 on `PATH` |
| `anthropic` | ✅ 0.120.2 |
| `ANTHROPIC_API_KEY` / `.env` | ✅ present, valid, account credited |
| `HF_TOKEN` / `.env` | ✅ present and valid (classic read token) |
| `pyannote/speaker-diarization-community-1` access | ✅ terms accepted |

> ⚠️ The "Installation state per machine" section above describes a Windows 11 /
> Python 3.14 machine: it is **out of date** and does not correspond to the
> current dev machine.

> ℹ️ `torchcodec` is broken in this venv: it expects the ffmpeg 4 to 7 libraries
> (`libavutil.56` to `.59`) while the machine has ffmpeg 8.1.2
> (`libavutil.60`), hence a noisy pyannote warning at startup. **Confirmed to
> have no impact**: pyannote's VAD, language detection, ASR and alignment all
> run normally. whisperx preloads the audio into memory and passes it as a
> waveform, which is exactly the workaround pyannote documents. It is not the
> cause of the diarization blockage.

### Still to validate

- **Diarization under realistic conditions**: separation is validated, but on an
  easy case — two synthetic voices, far apart in pitch, without overlap, with a
  single switch. Still untested: overlapping speech, closely spaced turns, two
  similar voices, more than two speakers, and real human voices in noise.
- **Automatic detection of the number of speakers**: always tested with an
  explicit `--num-speakers`, never by letting pyannote decide on its own on a
  multi-voice file.
- Other extensions: `.m4a`, `.wav`, `.opus` and `.ogg` have been run; `.mp3` and
  `.mp4` are accepted by the code but never passed through `mlx_whisper`.
- `diarize.py` does not validate the file extension, unlike `transcribe.py`: a
  non-audio file will produce a raw ffmpeg error there.
- Corrupted or truncated audio file: currently surfaces as a raw `RuntimeError`
  from `mlx_whisper` with a stack trace, instead of a clean message.
- Long file (> 30 min): memory behaviour and chunking not observed.
- `batch.py` on a real batch: tested on 3 short files. Behaviour on several
  dozen long files — total duration, memory, reloading the model for each file —
  has not been observed.
- `batch.py`'s resuming trusts the output file's **presence**, never its
  content. An output truncated by an interruption mid-write would be considered
  complete and skipped on the next run. That case was not provoked in testing;
  the workaround is `--force`, or deleting the `.txt`.
- `youtube.py`: a genuinely private video and a region-blocked video are not
  tested — impossible to provoke one. Their detection rests on yt-dlp message
  patterns (`private video`, `not available in your country`) that have never
  been triggered for real.
- `youtube.py`: two videos with the same title produce the same file name and
  overwrite each other. With `batch.py`'s resuming, the second would even be
  skipped.
- `youtube.py`: tested on one-minute videos. Nothing is known about the
  behaviour on an hour-long video — duration, memory, `.opus` size.
- Language detection: verified on French (5 fixtures) and English (NASA video).
  No other language tested, and no case of the language switching *within* a
  single file — Whisper only detects on the first window, so a bilingual
  recording would be transcribed in a single language.
- `summarize.py` has never been run on a **real** long Whisper transcript: the
  only test text at that scale is written by hand (Test 9). The typical errors
  of an ASR — mangled proper nouns, misheard figures — are therefore not
  represented, and those are exactly what trip a summary up.
- `summarize.py`: a single measured call, a single style (`concise`), a single
  language. Coverage varies from one run to the next — observed across two calls.
- `summarize.py` does not chunk its input: beyond 150,000 characters it refuses
  with a clear message rather than letting the API fail, but there is no
  chunking. The `MAX_TOKENS = 4096` output ceiling has never been approached
  (1,237 tokens on the largest run) and truncation has only been checked by
  simulating `stop_reason: max_tokens`.
- `summarize.py`: the summary's language is not instructed, it is inherited from
  the transcript — measured on French and English only (4 English runs out of 4,
  3 French out of 3). A transcript of a few dozen characters carries too little
  signal and can come back in English; no other language pair was measured.
- `cli.py`: `--summary-model` and `--summary-style` have only been exercised
  through the `summarize` subcommand, never chained behind `--summarize` on an
  audio input. The wiring is the same parent parser for all three inputs, but
  that is not a verification.
- `cli.py`: a batch where **the summary** fails (missing key, quota exceeded)
  was not provoked. The code counts the failures and exits with 1 without
  interrupting the series, as for transcriptions; that path has not been run.
- `cli.py`: summary resuming trusts, like transcription resuming, the
  **presence** of the `_summary.txt`, never its content.
- `summarize.py`: the system prompt is only calibrated for `claude-sonnet-5`. On
  `claude-haiku-4-5` with a one-sentence input, the model answers beside the
  point (Test 10). No other model has been tried.
- `app.py`: diarization has never been run from the web interface, nor has the
  summarization of a whole batch ("Summarize" box on the folder tab). Both go
  through the same calls as the CLI, but the path has not been executed.
- `app.py`: a long job blocks the page until it finishes — no per-file progress
  bar, only a spinner. On a batch of several dozen files, nothing distinguishes
  "running" from "frozen". `process_folder()`'s detailed output goes to stdout,
  hence to the terminal, not to the browser.
- `app.py`: `st.session_state` is specific to a browser session. Two tabs open
  on the same app each have their own result, but write into the same `output/`
  — two simultaneous jobs on the same file were not provoked.
- `app.py`: the language selector only offers 30 entries out of the 100
  languages Whisper knows. The others stay reachable from the CLI
  (`--language`), or by adding a line to `LANGUAGES`. Only `fr` and `en` have
  been exercised from the app; the other 27 codes are verified valid but never
  run.
- `app.py`: tested on Chromium only, at a single window size.
- `ffmpeg_path.py`: the restricted PATH is simulated with `env`, the real
  Automator app was not used as a counter-check. The `/usr/local/bin` fallback
  (Homebrew on Intel) has never been exercised, and the "ffmpeg absent from the
  machine" case — hence the error banner when the app loads — was not provoked.
- `cli.py` does not call `ensure_on_path()`: launched anywhere other than from a
  shell, it would fail the way the app did. Deliberate as long as the CLI starts
  from a terminal; the fix is one line if that changes.
- The toolkit is not installable (`pip install -e .`): see
  [Why `python src/cli.py`](#why-python-srcclipy-and-not-an-installed-whisper-toolkit-command).
- Models other than `whisper-large-v3-mlx`.
- Automated tests in `tests/`: none for now, everything has been checked by hand.

## Development

The contribution conventions and the project context are in
[CLAUDE.md](CLAUDE.md).
