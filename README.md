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

__PYVENV_LAUNCHER__="$PWD/venv/bin/python" nohup "$LAUNCHER" launch_desktop.py >> "$LOG" 2>&1 &
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

**Robustesse aux échecs partiels.** Chaque fichier est traité dans son propre
`try/except` : un fichier illisible n'interrompt pas le lot. Le résumé final
liste les échecs avec leur raison, et le processus sort en code 1 si au moins un
fichier a échoué — pratique pour enchaîner dans un script.

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

### Transcriptions réelles exécutées (2026-08-06)

Les fichiers audio de test vivent dans `test-audio/`, **ignoré par git** — ce
dépôt est public, aucun enregistrement réel ne doit y être versionné. Seule
exception : la fixture entièrement synthétique du test 4. Le contenu des
transcriptions d'enregistrements réels n'est pas reproduit ici, même raison.

**Test 1 — échantillon synthétique (voix macOS `Thomas`, fr_FR, 6,3 s, `.m4a`)**

| | |
|---|---|
| **Texte attendu** | « Bonjour, ceci est un test de transcription pour le projet whisper toolkit. Il fait beau aujourd'hui à Paris. » |
| **Texte obtenu** | « Bonjour, ceci est un test de transcription pour le projet Wisp et Tolkien. Il fait beau aujourd'hui à Paris. » |

Seul écart : « whisper toolkit » → « Wisp et Tolkien ». C'est un artefact de
l'échantillon, pas du modèle — la voix française prononce ces deux mots anglais
à la française, et Whisper transcrit fidèlement ce qu'il entend. Ponctuation,
accents et apostrophes sont corrects.

**Test 2 — vocal WhatsApp réel (voix humaine, fr, 2,47 s)**

Source : `.opus` mono 48 kHz (conteneur ogg, 18,6 kbit/s). Transcription
**correcte** : phrase cohérente, ponctuation et accents corrects, malgré la
forte compression WhatsApp et une durée très courte. Contenu non reproduit
(dépôt public).

Le même extrait a été passé sous quatre formes — `.opus`, `.ogg` (opus remuxé),
`.ogg` (vorbis stéréo) et `.wav` 16 kHz mono — avec une sortie **identique au
caractère près** dans les quatre cas.

> **Pourquoi aucune conversion n'est faite dans le code.** `mlx_whisper`
> décode déjà tout via ffmpeg, en imposant lui-même 16 kHz mono
> (`ffmpeg -i <fichier> -f s16le -ac 1 -ar 16000 -`, cf. `mlx_whisper/audio.py`).
> Convertir en amont referait donc exactement le même travail, en double et avec
> un fichier temporaire à gérer. `SUPPORTED_EXTENSIONS` sert uniquement de
> garde-fou pour rejeter tôt un fichier manifestement non audio ; tout format lu
> par ffmpeg fonctionne dès qu'il y figure.

**Performance** (Mac M5, `whisper-large-v3-mlx`) :

| Run | Durée | Détail |
|---|---|---|
| 1er | 4 min 16 s | dont 3 min 49 s de téléchargement du modèle (~3 Go) |
| Suivants | 3,1 – 3,6 s | modèle en cache, pour 2,5 – 6,3 s d'audio |

Le temps est dominé par le chargement du modèle, pas par la durée de l'audio :
ces mesures ne disent rien du débit sur un fichier long.

### Test 3 — `diarize.py`, pipeline complet validé (2026-08-06)

**La diarisation tourne de bout en bout.** Après acceptation des conditions de
`pyannote/speaker-diarization-community-1`, le pipeline entier s'exécute sans
erreur sur le vocal WhatsApp (2,47 s, `.opus`) :

| Étape du pipeline | Statut | Détail mesuré |
|---|---|---|
| `whisperx.load_audio` | ✅ | 39 256 échantillons à 16 kHz |
| `whisperx.load_model` | ✅ | `large-v3` int8 CPU |
| VAD pyannote | ✅ | exécutée sans erreur |
| `.transcribe()` | ✅ | langue `fr` détectée seule (confiance 1.00), 1 segment |
| `load_align_model` + `align` | ✅ | 9 mots alignés, segment 0,28 s → 2,40 s |
| `DiarizationPipeline` | ✅ | `community-1` chargée sur CPU |
| `assign_word_speakers` | ✅ | clé `speaker` présente sur le segment |
| `save_diarized_transcript()` | ✅ | fichier `output/..._diarized.txt` écrit et relu |

Sortie : une ligne au format `[SPEAKER_00] <texte>`, soit exactement le format
attendu (contenu non reproduit, dépôt public). **Run complet : 18,1 s**, modèles
en cache.

Un seul locuteur ici, l'échantillon étant mono-locuteur : ce test valide
l'exécution du pipeline, pas la séparation des voix. Celle-ci fait l'objet du
test 4.

**Historique du blocage** (résolu). Le premier run avec token valide échouait
en **403** : les conditions de `community-1` n'avaient pas été acceptées sur le
compte, alors que celles de la famille 3.1 l'étaient. Aucun contournement par
paramètre n'existait — avec `pyannote.audio` 4.0.7, pointer explicitement
`speaker-diarization-3.1` réclame quand même `plda/xvec_transform.npz`, hébergé
dans `community-1`, et retombe sur un 401.

> ℹ️ **Le token n'est requis qu'au premier téléchargement.** Une fois les poids
> pyannote en cache local, `Pipeline.from_pretrained` ne le consulte plus : un
> token invalide, ou absent, passe alors sans erreur. Constaté en tentant de
> rejouer les cas d'erreur après un run réussi.

**Écart entre les deux backends.** Sur le même extrait, faster-whisper et
mlx-whisper produisent des transcriptions qui diffèrent d'un mot (58 vs
57 caractères). Rien d'anormal — deux implémentations, deux quantifications —
mais à garder en tête : les deux pipelines ne sont pas interchangeables au
caractère près.

**Le coût du CPU est mesuré, pas supposé** (modèles en cache) :

| Étape | Durée |
|---|---|
| `load_model` | 5,6 s |
| `.transcribe()` | **10,4 s** pour 2,47 s d'audio |
| `load_align_model` | 0,3 s |
| `align` | 0,1 s |
| **Total** | **17,6 s** |

Soit **~4× plus lent que le temps réel** sur la seule transcription, là où
`transcribe.py` traite le même fichier en 3,1 s de bout en bout — l'écart
attendu entre MLX/Metal et CTranslate2/CPU. Premier run : 15 min 42, dominé par
le téléchargement des modèles (`large-v3` CTranslate2 + wav2vec2 français).

**Erreurs vérifiées en conditions réelles :**

Les trois cas de token sont désormais **distingués**, chacun vérifié contre une
vraie réponse HTTP :

| Cas | Message produit | Vérifié avec |
|---|---|---|
| Token absent | « Token Hugging Face introuvable » + lien vers les réglages de token | `load_dotenv` neutralisé, `HF_TOKEN` retiré |
| Token invalide (**401**) | « Token refusé » → régénérer le token | token bidon sur un dépôt gated non caché |
| Conditions non acceptées (**403**) | « Accès refusé au modèle *X* » → lien direct vers la page HF **du modèle demandé** | token valide sur `pyannote/speaker-diarization` |
| Fichier introuvable | `Fichier introuvable : ...` | chemin inexistant |

Les quatre sortent en `exit 1`. Le cas 403 nomme le modèle réellement demandé,
donc le lien reste correct même avec `--diarization-model`.

### Test 4 — séparation de deux locuteurs (2026-08-07)

Premier test qui valide la **raison d'être** de la diarisation, et non seulement
son exécution. Fixture : `test-audio/two_voices_generated.wav`, 9,5 s.

**Vérité terrain**, établie par mesure et non par confiance :

| | |
|---|---|
| Voix 1 | `Amélie` (fr_CA), F0 médiane **225 Hz**, 0 → 4,06 s |
| Voix 2 | `Thomas` (fr_FR), F0 médiane **128 Hz**, 4,06 → 9,48 s |
| Bascule | **4,06 s** (fin de la première réplique) |

**Résultat**, avec `--num-speakers 2` :

| start | end | speaker | voix réelle |
|---|---|---|---|
| 0,23 s | 4,08 s | `SPEAKER_01` | Amélie |
| 4,13 s | 9,36 s | `SPEAKER_00` | Thomas |

| Critère | Attendu | Obtenu | |
|---|---|---|---|
| Nombre de locuteurs | 2 | 2 | ✅ |
| Nombre de segments | 2 | 2 | ✅ |
| Point de bascule | 4,06 s | 4,08 – 4,13 s | ✅ à **±70 ms** |
| Mélange de voix | aucun | aucun | ✅ |

L'écart de 20 à 70 ms correspond au silence entre les deux répliques : les
bornes tombent de part et d'autre de la jonction réelle. Run complet : 17,5 s.

> ⚠️ **Les labels `SPEAKER_XX` ne suivent pas l'ordre d'apparition.** Ici Amélie
> parle en premier et reçoit `SPEAKER_01`, tandis que Thomas reçoit
> `SPEAKER_00`. Ne jamais supposer que `SPEAKER_00` est le premier à parler :
> les identifiants sont arbitraires et stables seulement à l'intérieur d'un run.

**À propos de la fixture.** `test-audio/two_voices_generated.wav` est le seul
fichier audio versionné du dépôt (exception explicite dans `.gitignore`). Il est
**intégralement synthétique**, généré avec la commande macOS `say` à partir de
deux voix système, puis concaténé avec ffmpeg :

```bash
say -v "Amélie" -o a.aiff "…"      # attention à l'accent, voir ci-dessous
say -v Thomas   -o b.aiff "…"
# conversion en wav 16 kHz mono, puis concat ffmpeg
```

Aucune voix réelle, aucune donnée personnelle. Il sert de fixture de
non-régression pour `diarize.py`.

> ⚠️ **Piège `say` : le nom de voix doit être exact, accents compris.**
> `say -v Amelie` (sans accent) ne lève **aucune erreur** — la commande retombe
> silencieusement sur la voix par défaut. On obtient alors deux extraits de la
> *même* voix, et une fixture qui ne teste rien. Le contrôle qui l'a révélé :
> mesurer la F0 des deux extraits avant de s'en servir. 225 Hz contre 128 Hz
> valide la fixture ; deux valeurs voisines la disqualifient.

### Test 5 — `batch.py`, robustesse aux échecs partiels (2026-08-07)

Dossier de test monté hors dépôt, contenant volontairement de quoi faire échouer
le lot :

| Fichier | Nature | Attendu |
|---|---|---|
| `01_deux_voix.wav` | fixture synthétique 2 voix, 9,5 s | traité |
| `02_vocal.wav` | enregistrement réel, mono-locuteur | traité |
| `03_corrompu.wav` | fichier texte renommé en `.wav` | **échec isolé** |
| `04_ignore.txt` | extension non audio | ignoré au listage |
| `sous_dossier/` | répertoire | ignoré au listage |

**Résultat, mode transcription** (`python src/batch.py <dossier>`) :

| Critère | Obtenu | |
|---|---|---|
| Fichiers listés | 3 sur 5 entrées | ✅ `.txt` et dossier écartés |
| Traités avec succès | 2 | ✅ |
| Échecs | 1 (`03_corrompu.wav`) | ✅ isolé |
| Le lot s'est poursuivi après l'échec | oui | ✅ |
| Sortie produite pour le fichier en échec | aucune | ✅ |
| Code de sortie | 1 | ✅ échec partiel signalé |
| Durée | 6,9 s | |

**Résultat, mode diarisation** (`--diarize --num-speakers 2`) : même comptage,
2 succès et 1 échec isolé, sorties `*_diarized.txt` produites, 39,5 s. La borne
`--num-speakers 2` est bien parvenue à pyannote — il l'a signalée comme
inatteignable sur le fichier mono-locuteur, ce qui confirme la propagation du
paramètre à travers `batch.py`.

Cas limites vérifiés séparément : dossier inexistant → message clair et `exit 1` ;
dossier sans aucun fichier audio → message et `exit 0`, sans erreur.

> **Lisibilité du résumé.** Quand ffmpeg échoue, il recrache sa bannière de
> compilation : l'erreur brute du fichier corrompu fait **13 lignes et
> 1173 caractères**, ce qui noyait tout le résumé du lot. `short_reason()` la
> réduit à sa première ligne pour l'affichage. L'erreur complète reste
> accessible dans le dict retourné par `process_folder()`.

### Test 6 — reprise de `batch.py` (2026-08-07)

Exécuté sur `test-audio/`, qui contient **6 fichiers tous traitables**
(`.opus`, `.ogg` ×2, `.wav` ×3), après avoir mis `output/` de côté pour partir
d'un état vierge. Trois lancements successifs, en mode transcription :

| # | Commande | Traités | Sautés | Sortie |
|---|---|---|---|---|
| 1 | `batch.py test-audio/` | 6 | 0 | 6 `.txt` créés, 8,7 s |
| 2 | `batch.py test-audio/` | 0 | **6** | aucune réécriture, `exit 0` |
| 3 | `batch.py test-audio/ --force` | 6 | 0 | 6 `.txt` réécrits |

Le run 3 a été validé sur les **mtimes** et non sur le seul affichage : les six
horodatages passent de `12:03:4x` à `12:04:0x`, donc les fichiers ont réellement
été réécrits, pas simplement re-annoncés.

Cas complémentaires vérifiés :

| Scénario | Attendu | Obtenu |
|---|---|---|
| Suppression d'**une** sortie sur 6, relance | 1 traité, 5 sautés | ✅ |
| `--diarize` alors que les 6 `.txt` existent | rien de sauté | ✅ 2/2 diarisés |
| `--diarize` relancé après coup | 2 sautés | ✅ |
| Transcription relancée après diarisation | 2 sautés | ✅ |

> **Le test qui compte vraiment est celui du croisement des modes.** Une
> implémentation naïve qui chercherait « une sortie quelconque pour ce fichier »
> aurait sauté la diarisation de fichiers déjà transcrits — et le lot aurait
> paru réussir en ne produisant rien. C'est pourquoi la sortie attendue est
> demandée à `transcript_path()` / `diarized_transcript_path()` selon le mode,
> plutôt que reconstruite dans `batch.py`.

### Test 7 — `youtube.py` (2026-08-07)

Vidéo de test : `V0oo_Nybo6w`, « NASA Artemis II: Counting Down to Our Next Moon
Mission », 60 s, chaîne officielle NASA. Choisie parce qu'une production de la
NASA est dans le domaine public (œuvre du gouvernement américain) et que sa
durée garde le test rapide. **Ni l'audio ni la transcription ne sont versionnés**
— `test-audio/*` et `output/` sont ignorés, vérifié avec `git check-ignore`.

**Choix du format : mesuré, pas supposé.** Le point de départ était « `.wav` ou
`.m4a` ». La mesure a montré que la question était mal posée.

| Source | Conteneur | Temps | Mots | Réf. sous-titres |
|---|---|---|---|---|
| flux AAC | `.m4a` | 20,1 s | 338 | 121 |
| flux AAC | `.wav` | 20,3 s | 338 | 121 |
| flux Opus | `.m4a` | 5,0 s | 124 | 121 |
| flux Opus | `.wav` | 5,0 s | 123 | 121 |

À contenu identique, les deux conteneurs donnent **exactement** le même résultat
(3 exécutions chacun, chiffres stables au dixième). Le conteneur n'entre donc pas
en compte ; seul le **flux source** compte. Sur cette vidéo, le flux AAC part en
boucle d'hallucination : 338 mots au lieu de 121, dont `the` **77 fois**, soit
23 % du texte.

Vérifié sur 3 autres vidéos NASA courtes, transcription comparée aux sous-titres
automatiques YouTube pris comme référence :

| Vidéo | AAC | Opus | Réf. |
|---|---|---|---|
| `XYMuC2MDbwo` | 7,8 s / 176 mots | 6,1 s / 179 mots | 168 |
| `MLgYJh6OFbY` | 36,5 s / 143 mots | 15,1 s / 130 mots | 130 |
| `oqRwrlJbjOg` | 33,3 s / 141 mots | 5,6 s / 132 mots | 131 |

Le flux Opus est plus rapide dans les 4 cas (jusqu'à 6×) et plus proche de la
référence. D'où le choix de `.opus` : meilleure entrée pour Whisper, aucun
ré-encodage (`-acodec copy`, vérifié dans la ligne de commande ffmpeg émise par
yt-dlp), et 12× plus léger que le wav.

> ⚠️ **Le premier run réel a produit une transcription entièrement fausse.**
> L'audio est anglais, mais `transcribe.py` forçait alors `language="fr"` :
> Whisper a rendu un texte français inventé, fluide et plausible, qui n'avait
> qu'un rapport lointain avec l'original. Rien dans la sortie ne signalait le
> problème. Après correction, la transcription correspond aux sous-titres
> YouTube (123 mots contre 121 de référence).
>
> Le correctif appliqué ici était local à `youtube.py`. Le défaut valait aussi
> pour `transcribe.py` et `batch.py` : il a été retiré à la racine au Test 8.

**Résultats fonctionnels :**

| Scénario | Attendu | Obtenu |
|---|---|---|
| CLI, détection auto | transcription anglaise correcte | ✅ 8,6 s bout en bout |
| CLI, `--language en` | identique | ✅ |
| CLI, `--diarize` | segments étiquetés | ✅ 13 segments, 2 locuteurs, 73,5 s |
| Audio téléchargé | dans `test-audio/`, ignoré | ✅ `.gitignore:44` |
| Transcription | dans `output/`, ignorée | ✅ `.gitignore:54` |

**Gestion d'erreurs**, messages vérifiés sur de vraies URL :

| Cas | Obtenu |
|---|---|
| Identifiant inexistant | « Vidéo indisponible … supprimée, privée, ou identifiant erroné » |
| Chaîne qui n'est pas une URL | idem (yt-dlp la traite comme un identifiant) |
| URL non-YouTube en 404 | « Échec du téléchargement » + détail yt-dlp |
| URL de playlist pure | refus explicite, « 8 vidéos … passe l'URL d'une vidéo » |
| URL `watch?v=…&list=…` | la seule vidéo est traitée, titre conservé |

> ⚠️ **Une URL de playlist aurait téléchargé 8 vidéos sous un seul nom.**
> `noplaylist` ne règle que les URL `watch?v=…&list=…` ; sur une URL de
> playlist pure, yt-dlp renvoie les 8 entrées. Comme le modèle de nom est fixé
> avant le téléchargement, les 8 fichiers se seraient écrasés l'un l'autre et
> seule la dernière vidéo aurait été transcrite — sous le titre de la playlist,
> sans le moindre avertissement. D'où le refus explicite dans `download_audio()`.
>
> Le garde-fou a lui-même coûté une correction : `extract_flat=True`, ajouté
> pour ne pas résoudre les 8 entrées, aplatissait *aussi* la vidéo seule, qui
> perdait son titre et retombait sur l'identifiant. C'est `in_playlist` qu'il
> faut, pas `True`.

Le message brut de yt-dlp était affiché **en plus** du message traduit :
`quiet=True` ne couvre pas les erreurs, qui partent sur stderr quoi qu'il
arrive. Un `logger` muet passé à `YoutubeDL` règle le problème.

Cas **non testés** faute de pouvoir les provoquer : vidéo réellement privée,
vidéo bloquée par région. Leur détection repose sur des motifs de message
(`private video`, `not available in your country`) repris de la documentation
yt-dlp, jamais déclenchés en conditions réelles.

Nommage vérifié unitairement — accents translittérés (`Café à la crème` →
`Cafe_a_la_creme`), titre japonais et titre de ponctuation pure repliés sur
l'identifiant, troncature à 80 caractères, et `../../etc/passwd` neutralisé en
`etc_passwd`.

### Test 8 — détection de langue généralisée (2026-08-07)

Le défaut `language="fr"` de `transcribe_file()` est retiré. Le défaut touchait
aussi `batch.py`, qui appelait `transcribe_file()` sans argument : le Test 7
n'avait mis en évidence qu'un symptôme sur trois.

**Aucune dégradation** sur du contenu français, mesurée avant de changer le
défaut. Pour chaque fixture, `language="fr"` puis `language=None` :

| Fixture | forcé `fr` | auto | détecté | texte |
|---|---|---|---|---|
| `conversation_test.wav` | 0,85 s | 1,21 s | `fr` | identique |
| `two_voices_generated.wav` | 1,40 s | 1,78 s | `fr` | identique |
| `whatsapp_test.wav` | 0,79 s | 1,17 s | `fr` | identique |
| `WhatsApp Audio ….opus` | 0,79 s | 1,17 s | `fr` | identique |
| `test_vorbis.ogg` | 0,79 s | 1,14 s | `fr` | identique |

Le texte est **strictement identique** dans les cinq cas — la détection ne change
pas le résultat, elle évite seulement de le corrompre quand la langue diffère.

Le surcoût est **fixe, pas proportionnel** : constant autour de 0,35 s sur ces
fixtures courtes, et 0,32 s sur un fichier français de 76 s (61,39 s → 61,71 s,
soit 0,5 %). La détection ne tourne qu'une fois, sur la première fenêtre.

> ⚠️ **Forcer la langue produit une traduction, pas une erreur.** La fixture
> française passée en `--language en` ressort en anglais parfaitement fluide :
> « Hello, did you have time to look at the supplier's file this morning? » là
> où l'audio dit « Bonjour, est-ce que tu as eu le temps de regarder le dossier
> fournisseur ce matin ? ». Aucun avertissement, aucun code d'erreur, une sortie
> plausible. C'est le même défaut qu'au Test 7, reproduit en sens inverse — et
> la raison pour laquelle un défaut de langue codé en dur n'a pas sa place ici.

**Vérifications fonctionnelles :**

| Scénario | Obtenu |
|---|---|
| `transcribe.py` sans `--language` sur fixture fr | ✅ français correct |
| `transcribe.py --language en` sur la même | ✅ traduit — défaut reproduit |
| `batch.py --force` sur `test-audio/` **mixte** | ✅ 7/7, chacun dans sa langue |
| `batch.py --language en` | ✅ forçage propagé jusqu'à `transcribe_file()` |
| `batch.py --force` ensuite | ✅ retour au français |

Le lot mixte est le test qui compte : `test-audio/` contient 6 fichiers français
et la vidéo NASA anglaise du Test 7. Un seul passage les transcrit chacun dans
sa langue. Avec l'ancien défaut, la vidéo anglaise serait ressortie en français
inventé, sans que le résumé du lot signale quoi que ce soit.

`youtube.py` perd du même coup son `kwargs.setdefault("language", None)`, qui
n'était qu'un contournement local du défaut désormais supprimé.

### Test 9 — `summarize.py`, appel réel sur transcription longue (2026-08-07)

Premier test avec des crédits sur le compte : l'appel à l'API a bien eu lieu et
un résumé a été produit. Le blocage du premier essai (`HTTP 400`, solde
insuffisant) est levé — la branche d'erreur correspondante reste en place et
avait été validée à ce moment-là.

**Sur le texte de test.** Les transcriptions de `output/` totalisent moins de
400 mots à elles toutes : les concaténer ne donnait pas un cas représentatif.
La transcription de test est donc **rédigée à la main** — une réunion de suivi
de projet en français, **2 411 mots / 14 495 caractères**, avec étiquettes
`[SPEAKER_XX]`, hésitations, répétitions et phrases interrompues.

> ⚠️ Elle **simule** une sortie de reconnaissance vocale, elle n'en est pas une.
> Les défauts sont plausibles mais choisis ; un vrai ASR se trompe autrement, en
> particulier sur les noms propres et les chiffres. Ce test valide le
> comportement du résumé sur un texte long et bruité, pas sa robustesse aux
> erreurs réelles de Whisper.

En contrepartie, comme le texte est écrit, **on connaît la vérité terrain** :
26 faits vérifiables y ont été placés délibérément — décisions, actions,
montants, dates, un désaccord tranché et un sujet volontairement non tranché.

**Mesures du run :**

| | |
|---|---|
| Modèle | `claude-sonnet-5` |
| Durée | 15,1 s |
| Tokens | 6 935 en entrée, 1 237 en sortie |
| Coût | ≈ **0,039 $** par résumé (tarif Sonnet 3 $/15 $ par MTok) |
| Compression | 470 mots pour 2 400, soit 20 % |
| `stop_reason` | `end_turn` — pas de troncature |

**Couverture : 26 / 26 faits plantés retrouvés**, vérifiés par script et non à
l'œil. Y compris les détails secondaires (12 000 utilisateurs de l'ancien
portail, pénalités contractuelles plafonnées à ~3 000 €) qu'un premier run avait
laissés de côté — la couverture varie donc d'un appel à l'autre.

**Aucune invention.** Contrôle systématique de la sortie : les seize valeurs
numériques du résumé (240 000 €, 180 000 €, 60 000 €, 15 000–25 000 €, 3 000 €,
12 000, 23 tickets, 80 %, 5 ans, 4 h…) figurent toutes dans la transcription, et
les six noms propres cités (Kepler, Amélie, Thomas, Karim, Léa, OVH) aussi.

**Structure et lecture.** Titre, phrase d'ouverture qui situe la réunion, points
clés par lot, puis une section décisions/actions nominative. Trois comportements
qui n'allaient pas de soi :

- Le **désaccord** est restitué comme un désaccord — les deux positions sont
  exposées dans les points clés, et l'arbitrage apparaît séparément dans les
  décisions, sans que le résumé prenne parti.
- Le sujet **non tranché** (hébergement) est marqué comme tel, « mis en attente,
  à rouvrir une fois le paiement sécurisé », au lieu d'être présenté comme
  décidé ou d'être omis.
- Les étiquettes `[SPEAKER_XX]` sont **conservées et rapprochées** des prénoms
  prononcés dans la réunion, sans en inventer. La transcription contenait une
  incohérence de diarisation volontaire — `SPEAKER_00` pose une question à Karim
  puis y répond — et le modèle l'a résolue de façon cohérente plutôt que de s'y
  perdre.

**Garde-fou d'entrée**, vérifié aux bornes : 150 000 caractères passent,
150 001 lèvent « Transcription trop longue » sans appeler l'API.

**Ce que ce test ne dit pas.** Un seul appel, un seul texte, une seule langue,
un seul style (`concis`). La variation entre runs est réelle — elle s'est vue
sur deux appels. Et le texte étant écrit par nos soins, la couverture mesurée
est un plafond optimiste par rapport à une vraie transcription Whisper.

### Test 10 — `cli.py`, les quatre sous-commandes en conditions réelles (2026-08-07)

Chaque sous-commande a été lancée pour de vrai, pas seulement en `--help`.

| Commande | Résultat | Durée |
|---|---|---|
| `transcribe test-audio/two_voices_generated.wav` | texte français correct, `output/two_voices_generated.txt` | 4,0 s |
| `transcribe … --diarize --num-speakers 2 --summarize` | 2 locuteurs séparés **puis** résumé enchaîné | 23,4 s |
| `batch <dossier> --summarize` | 2 transcriptions + 2 résumés, 1 échec isolé, `exit 1` | — |
| `youtube 'https://youtu.be/V0oo_Nybo6w' --summarize` | transcription anglaise + résumé français | 19,8 s |
| `summarize output/…NASA….txt --style "en trois puces exactement"` | exactement 3 puces | — |

**L'enchaînement `--diarize --summarize` est le cas qui compte** : il traverse
les deux modules les plus éloignés du toolkit en une commande. Sortie obtenue
sur la fixture 2 voix — `[SPEAKER_01]` puis `[SPEAKER_00]`, conforme au Test 4 —
et le résumé écrit dans `output/two_voices_generated_diarized_summary.txt`, pas
dans `…_summary.txt` : c'est bien la sortie **diarisée** qui a été résumée, et
le nom du fichier le dit.

**Reprise du lot, vérifiée sur trois lancements successifs.** Dossier de test
monté hors dépôt : deux fichiers audio valides, un `.wav` corrompu, un `.txt`.

| # | État de départ | Traités | Sautés | Résumés | Code |
|---|---|---|---|---|---|
| 1 | rien dans `output/` | 2 | 0 | 2 produits | 1 *(fichier corrompu)* |
| 2 | tout est là | 0 | 2 | **2 sautés — aucun appel à l'API** | 1 *(idem)* |
| 3 | un `_summary.txt` supprimé, fichier corrompu retiré | 0 | 2 | 1 seul régénéré | 0 |

Le run 2 dure **2,0 s** et ne coûte rien : c'est ce que vérifie ce test. Le
run 3 vérifie l'autre moitié de la règle — une transcription sautée reste
candidate au résumé, sinon reprendre un lot interrompu ne résumerait que la
partie restante.

**Erreurs et avertissements**, tous vérifiés en vrai :

| Cas | Obtenu |
|---|---|
| `transcribe` fichier absent / extension non gérée | message clair, `exit 1` |
| `batch` dossier introuvable | « Dossier introuvable : … », `exit 1` |
| `summarize` fichier absent | « Fichier introuvable : … », `exit 1` |
| `--num-speakers` sans `--diarize` | « Attention : --num-speakers est ignoré sans --diarize. » |
| `--language` avec `--diarize` | avertissement équivalent (whisperx détecte lui-même) |

**Les modules restent utilisables seuls.** `batch.py`, `youtube.py` et
`summarize.py` ont été relancés directement après refactor : bilan de lot
identique, `youtube.py` affiche désormais aussi le chemin de sortie, aide de
`summarize.py` inchangée.

> ⚠️ **Observation hors périmètre du CLI, mais à noter.** Le test
> `--model claude-haiku-4-5` a bien routé le modèle, mais sur une transcription
> d'**une seule phrase** (75 caractères) Haiku a répondu comme si on
> s'adressait à lui — « je n'ai pas accès à des dossiers externes… » — au lieu
> de résumer. Sonnet, sur un texte aussi court, dit correctement que le texte
> est trop court pour être résumé. Le prompt système de `summarize.py` n'a été
> calibré que sur Sonnet ; `--summary-model` reste donc à utiliser en
> connaissance de cause.

### Test 11 — `app.py`, les trois onglets dans un vrai navigateur (2026-08-07)

L'app a été lancée (`streamlit run app.py`) et pilotée dans Chromium, pas
seulement importée : chaque onglet a été utilisé comme un utilisateur le ferait —
dépôt de fichier, saisie de chemin, clic sur le bouton — et le rendu vérifié sur
capture d'écran.

| Onglet | Scénario | Résultat |
|---|---|---|
| Fichier unique | dépôt de `two_voices_generated.wav` | texte français correct, `output/two_voices_generated.txt`, bouton de téléchargement |
| Dossier (batch) | 3 fichiers audio + 1 `.txt` + 1 `.wav` corrompu | **2 succès / 0 sauté / 1 échec**, le `.txt` ignoré au listage |
| Dossier (batch) | même dossier relancé | **0 / 2 sautés / 1**, la reprise se voit dans le tableau |
| YouTube | `https://youtu.be/V0oo_Nybo6w` (NASA) | transcription anglaise conforme au Test 7 |
| YouTube | la même, case « Résumer » cochée | résumé français affiché **et** écrit dans `output/` |

Durées mesurées de bout en bout du script de pilotage — lancement du navigateur
et chargement de la page compris, donc majorées par rapport au traitement seul :
9,5 s pour l'onglet fichier, 12,0 s pour le lot de 3 fichiers, 14,7 s pour la
vidéo NASA, 21,5 s avec le résumé enchaîné. Aucune exception Streamlit
(`stException`) sur aucun run.

**Le fichier corrompu est le cas qui compte** dans l'onglet lot : le traitement
va au bout, la ligne en échec apparaît dans le tableau avec la bannière ffmpeg
réduite à une ligne par `batch.short_reason()`, et les deux autres fichiers sont
transcrits. C'est le comportement du CLI (Test 5), obtenu sans le réécrire.

**Racine autorisée, vérifiée par contournement** et non par lecture du code :

| Saisie | Obtenu |
|---|---|
| `test-audio/batch_demo` | accepté, lot traité |
| `/etc` | refusé — « Chemin hors de la racine autorisée : /private/etc » |
| `../../../../etc` | refusé, message identique |

Le chemin affiché dans le refus est `/private/etc` et non `/etc` : c'est
`realpath` qui a résolu le lien symbolique de macOS **avant** le test de
confinement. C'est exactement ce qu'on lui demande.

**Cas limites d'interface vérifiés :** bouton « Transcrire » grisé tant qu'aucun
fichier n'est déposé, champ langue grisé dès que « Identifier les locuteurs » est
coché, champ « nombre de locuteurs » grisé dans le cas inverse.

**Sélecteur de langue** (remplace le champ texte libre du premier jet, qui
acceptait `langue random`) :

| Test | Obtenu |
|---|---|
| Liste déroulante | 30 entrées, « Détection automatique » en tête et par défaut |
| Filtre `Esp` | une seule proposition, `Espagnol` |
| Filtre `langue random` | **« No results »**, rien à sélectionner |
| Même saisie + `Entrée` + perte du focus | le champ revient à « Détection automatique », la saisie est jetée |
| Les 29 codes | tous présents dans `mlx_whisper.tokenizer.LANGUAGES`, sans doublon |
| Onglets *Dossier* et *YouTube* | même sélecteur, une seule déclaration dans `_audio_options()` |

**La valeur transmise a été vérifiée par l'écart, pas par l'affichage.**
Sélectionner « Français » sur une fixture française ne prouve rien : la
détection automatique aurait rendu le même texte. C'est « Anglais » sur cette
même fixture qui tranche — la sortie ressort traduite en anglais, mot pour mot
celle du Test 8 (« Hello, did you have time to look at the supplier's file this
morning? »). Le code `en` est donc bien arrivé jusqu'à `transcribe_file()`.
Repassé en « Français », le texte français correct revient.

**Ce que ce test ne dit pas.** Les fixtures du lot étaient de petits fichiers
montés pour l'occasion, dans un sous-dossier temporaire de `test-audio/`. La
diarisation n'a **pas** été exercée depuis l'app — le chemin est le même appel
`diarize_file()` qu'en CLI, mais ce n'est pas une vérification. Un seul
navigateur (Chromium), une seule session, aucun test de deux onglets de
navigateur ouverts en même temps sur la même app.

### Test 12 — ffmpeg introuvable hors shell interactif (2026-08-07)

**Symptôme :** l'onglet YouTube échoue avec « ffprobe and ffmpeg not found.
Please install or provide the path using --ffmpeg-location », alors que ffmpeg
est installé et que le CLI marche. Constaté avec l'app lancée par une app
Automator, qui exécute le script sans passer par un shell interactif complet.

**Cause, reproduite à l'identique.** `ffmpeg` est dans `/opt/homebrew/bin`, que
seul un shell ayant chargé `~/.zshrc` met dans le `PATH` :

```bash
env PATH=/usr/bin:/bin sh -c 'command -v ffmpeg'   # → rien
```

**Le bug avait deux moitiés, pas une.** Le message d'erreur ne montrait que la
première, parce que le téléchargement échouait avant d'arriver à la seconde :

| Étape de `transcribe_youtube()` | Sous PATH amputé, avant correctif |
|---|---|
| téléchargement yt-dlp | ❌ « ffprobe and ffmpeg not found » |
| transcription `mlx_whisper` | ❌ « [Errno 2] No such file or directory: 'ffmpeg' » |

Ne corriger que yt-dlp aurait donc déplacé la panne d'un cran au lieu de la
lever — vérifié : avec `ffmpeg_location` seul, le téléchargement passe puis la
transcription tombe sur `Errno 2`. D'où les deux correctifs.

**Après correctif :**

| Scénario | Résultat |
|---|---|
| `streamlit run app.py` depuis un terminal | ✅ onglet YouTube complet, transcription conforme |
| `env PATH=/usr/bin:/bin … streamlit run app.py` | ✅ **identique**, téléchargement et transcription |
| `cli.py youtube` depuis un terminal | ✅ aucune régression, `exit 0` |
| `cli.py transcribe` depuis un terminal | ✅ aucune régression |

Mécanique vérifiée sous `PATH=/usr/bin:/bin` : `shutil.which("ffmpeg")` retourne
`None`, le repli Homebrew retrouve `/opt/homebrew/bin/ffmpeg`,
`ensure_on_path()` fait passer le `PATH` à `/opt/homebrew/bin:/usr/bin:/bin`, et
un second appel ne le duplique pas.

> ⚠️ **Ce que le message d'erreur ne disait pas.** « ffmpeg not found » sur une
> machine où `which ffmpeg` répond est presque toujours un problème de `PATH`
> hérité, pas d'installation. Le réflexe — réinstaller ffmpeg — ne pouvait rien
> donner ici.

**Ce que ce test ne dit pas.** Le PATH restreint est *simulé* avec `env` : la
vraie app Automator n'a pas été relancée pour confirmer, et son PATH réel n'a pas
été relevé. `/usr/local/bin` (Homebrew sur Intel) est dans les emplacements de
repli mais n'a jamais été exercé — cette machine est en Apple Silicon. Le cas
« ffmpeg réellement absent de la machine » n'a pas été provoqué : la bannière
d'erreur de l'app n'a donc jamais été vue.

### Environnement de test (vérifié le 2026-08-06)

Mac M5 (`Darwin arm64`) — tout est en place :

| Élément | Statut |
|---|---|
| `venv/` | ✅ Python 3.12.13 |
| `mlx-whisper` | ✅ 0.4.3 (avec `mlx` 0.32.0) |
| `whisperx` | ✅ 3.8.6 |
| `yt-dlp` | ✅ 2026.7.4 |
| `python-dotenv` | ✅ 1.2.2 |
| `ffmpeg` | ✅ 8.1.2 dans le `PATH` |
| `anthropic` | ✅ 0.120.2 |
| `ANTHROPIC_API_KEY` / `.env` | ✅ présente, valide, compte crédité |
| `HF_TOKEN` / `.env` | ✅ présent et valide (token classique, lecture) |
| Accès `pyannote/speaker-diarization-community-1` | ✅ conditions acceptées |

> ⚠️ La section « État d'installation par machine » ci-dessus décrit une machine
> Windows 11 / Python 3.14 : elle est **obsolète** et ne correspond pas à la
> machine de dev actuelle.

> ℹ️ `torchcodec` est cassé dans ce venv : il attend les bibliothèques ffmpeg 4
> à 7 (`libavutil.56` à `.59`) alors que la machine a ffmpeg 8.1.2
> (`libavutil.60`), d'où un avertissement pyannote bruyant au démarrage.
> **Confirmé sans impact** : la VAD pyannote, la détection de langue, l'ASR et
> l'alignement tournent tous normalement. whisperx pré-charge l'audio en mémoire
> et le passe sous forme de waveform, ce qui est exactement le contournement
> documenté par pyannote. Ce n'est pas la cause du blocage de la diarisation.

### Reste à valider

- **Diarisation en conditions réalistes** : la séparation est validée, mais sur
  un cas facile — deux voix de synthèse, très éloignées en hauteur, sans
  chevauchement, avec une seule bascule. Restent non testés : le chevauchement
  de parole, les tours de parole rapprochés, deux voix proches, plus de deux
  locuteurs, et de vraies voix humaines dans du bruit.
- **Détection automatique du nombre de locuteurs** : toujours testée avec
  `--num-speakers` explicite, jamais en laissant pyannote décider seul sur un
  fichier multi-voix.
- Autres extensions : `.m4a`, `.wav`, `.opus` et `.ogg` ont été exécutés ;
  `.mp3` et `.mp4` sont acceptés par le code mais jamais passés dans
  `mlx_whisper`.
- `diarize.py` ne valide pas l'extension du fichier, contrairement à
  `transcribe.py` : un fichier non audio y produira une erreur ffmpeg brute.
- Fichier audio corrompu ou tronqué : remonte aujourd'hui en `RuntimeError`
  brute de `mlx_whisper` avec une stacktrace, au lieu d'un message propre.
- Fichier long (> 30 min) : comportement mémoire et découpage non observés.
- `batch.py` sur un vrai lot : testé sur 3 fichiers courts. Le comportement sur
  plusieurs dizaines de fichiers longs — durée totale, mémoire, rechargement du
  modèle à chaque fichier — n'a pas été observé.
- La reprise de `batch.py` se fie à la **présence** du fichier de sortie, jamais
  à son contenu. Une sortie tronquée par une coupure en pleine écriture serait
  considérée comme complète et sautée au lancement suivant. Ce cas n'a pas été
  provoqué en test ; le contournement est `--force`, ou supprimer le `.txt`.
- `youtube.py` : vidéo réellement privée et vidéo bloquée par région ne sont pas
  testées — impossible d'en provoquer une. Leur détection repose sur des motifs
  de message yt-dlp (`private video`, `not available in your country`) qui n'ont
  jamais été déclenchés pour de vrai.
- `youtube.py` : deux vidéos de même titre produisent le même nom de fichier et
  s'écrasent. Avec la reprise de `batch.py`, la seconde serait même sautée.
- `youtube.py` : testé sur des vidéos d'une minute. Rien n'est connu du
  comportement sur une vidéo d'une heure — durée, mémoire, taille du `.opus`.
- Détection de langue : vérifiée sur du français (5 fixtures) et de l'anglais
  (vidéo NASA). Aucune autre langue testée, et aucun cas de bascule de langue
  *à l'intérieur* d'un même fichier — Whisper ne détecte que sur la première
  fenêtre, un enregistrement bilingue serait donc transcrit dans une seule
  langue.
- `summarize.py` n'a jamais été lancé sur une **vraie** transcription Whisper
  longue : le seul texte de test à l'échelle est écrit à la main (Test 9). Les
  erreurs typiques d'un ASR — noms propres déformés, chiffres mal reconnus — ne
  sont donc pas représentées, alors que ce sont elles qui piègent un résumé.
- `summarize.py` : un seul appel mesuré, un seul style (`concis`), une seule
  langue. La couverture varie d'un run à l'autre — observé sur deux appels.
- `summarize.py` ne découpe pas les entrées : au-delà de 150 000 caractères il
  refuse avec un message clair plutôt que de laisser l'API échouer, mais il n'y
  a pas de chunking. Le plafond `MAX_TOKENS = 4096` en sortie n'a jamais été
  approché (1 237 tokens sur le run le plus gros) et la troncature n'a été
  vérifiée qu'en simulant `stop_reason: max_tokens`.
- `cli.py` : `--summary-model` et `--summary-style` n'ont été exercés que via la
  sous-commande `summarize`, jamais enchaînés derrière `--summarize` sur une
  entrée audio. Le câblage est le même parseur parent pour les trois entrées,
  mais ce n'est pas une vérification.
- `cli.py` : un lot où **le résumé** échoue (clé absente, quota dépassé) n'a pas
  été provoqué. Le code compte les échecs et sort en 1 sans interrompre la
  série, comme pour les transcriptions ; ce chemin n'a pas été exécuté.
- `cli.py` : la reprise des résumés se fie, comme celle des transcriptions, à la
  **présence** du `_summary.txt`, jamais à son contenu.
- `summarize.py` : le prompt système n'est calibré que pour `claude-sonnet-5`.
  Sur `claude-haiku-4-5` et une entrée d'une phrase, le modèle répond à côté
  (Test 10). Aucun autre modèle n'a été essayé.
- `app.py` : la diarisation n'a jamais été lancée depuis l'interface web, ni le
  résumé d'un lot entier (case « Résumer » sur l'onglet dossier). Les deux
  passent par les mêmes appels qu'en CLI, mais le chemin n'a pas été exécuté.
- `app.py` : un traitement long bloque la page jusqu'à la fin — pas de barre de
  progression fichier par fichier, seulement un spinner. Sur un lot de plusieurs
  dizaines de fichiers, rien ne distingue « en cours » de « figé ». La sortie
  détaillée de `process_folder()` part sur stdout, donc dans le terminal, pas
  dans le navigateur.
- `app.py` : `st.session_state` est propre à une session de navigateur. Deux
  onglets ouverts sur la même app ont chacun leur résultat, mais écrivent dans le
  même `output/` — deux traitements simultanés du même fichier n'ont pas été
  provoqués.
- `app.py` : le sélecteur de langue ne propose que 30 entrées sur les 100 langues
  que Whisper connaît. Les autres restent atteignables en CLI (`--language`),
  ou en ajoutant une ligne à `LANGUAGES`. Seuls `fr` et `en` ont été exercés
  depuis l'app ; les 27 autres codes sont vérifiés valides mais jamais lancés.
- `app.py` : testé sur Chromium uniquement, à une seule taille de fenêtre.
- `ffmpeg_path.py` : le PATH restreint est simulé avec `env`, la vraie app
  Automator n'a pas servi de contre-épreuve. Le repli `/usr/local/bin` (Homebrew
  Intel) n'a jamais été exercé, et le cas « ffmpeg absent de la machine » — donc
  la bannière d'erreur au chargement de l'app — n'a pas été provoqué.
- `cli.py` n'appelle pas `ensure_on_path()` : lancé autrement que depuis un
  shell, il échouerait comme l'app le faisait. Volontaire tant que le CLI part
  d'un terminal ; le correctif tient en une ligne si ça change.
- Le toolkit n'est pas installable (`pip install -e .`) : voir
  [Pourquoi `python src/cli.py`](#pourquoi-python-srcclipy-et-pas-une-commande-whisper-toolkit-installée).
- Autres modèles que `whisper-large-v3-mlx`.
- Tests automatisés dans `tests/` : aucun pour l'instant, tout a été vérifié
  à la main.

## Développement

Les conventions de contribution et le contexte du projet sont dans
[CLAUDE.md](CLAUDE.md).
