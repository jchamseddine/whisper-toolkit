"""Launch the Streamlit interface in a native window, with no browser.

Third entry point, after `src/cli.py` and `app.py` — and like them, it holds no
business logic: it starts `app.py` then displays it. Nothing that touches audio
goes through here.

The need: `streamlit run app.py` opens a browser tab, which makes the Automator
app a shortcut to Chrome rather than an application. This module therefore wraps
the server in a WebKit window (pywebview) and makes sure the server lives and
dies with it.

Four things are less obvious than they look:

- **`--server.headless true` is indispensable**, not cosmetic. Without that
  flag, Streamlit opens a tab of its own at startup: the native window would
  show up *on top of* the browser, which is precisely what we are avoiding.
- **The port is checked before launching.** Without that, a server already
  sitting on 8501 would answer the probe immediately: the window would open on
  the foreign instance while our subprocess dies in silence, for want of a port.
- **Streamlit is started in its own session** (`start_new_session`) so the whole
  process group can be killed on close. Terminating only the parent process
  would leave its children holding port 8501.
- **The app's identity is not decided here.** It comes from the `.app` bundle
  the executable belongs to, which `scripts/make_launcher_bundle.sh` builds and
  the Automator applet invokes. `set_dock_identity()` below is only the safety
  net for direct launches, from a terminal.

Run with: `python launch_desktop.py` from the repository root.
"""

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HOST = "localhost"
PORT = 8501
URL = f"http://{HOST}:{PORT}"

# Streamlit's health endpoint: it only answers once the server is genuinely
# ready to serve the app, where an open socket only proves it is listening.
HEALTH_URL = f"{URL}/_stcore/health"

# Generous margin: the first startup pays for importing Streamlit and compiling
# the templates. Beyond that, it is a failure, not slowness.
STARTUP_TIMEOUT = 15.0
POLL_INTERVAL = 0.25

# Grace given to Streamlit to shut down on SIGTERM before the SIGKILL.
SHUTDOWN_GRACE = 5.0

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

WINDOW_TITLE = "Whisper Toolkit"
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800

# The same image as the Automator app's icon, but as PNG: NSImage reads it
# directly, where the .icns targets the Finder.
DOCK_ICON = os.path.join(PROJECT_ROOT, "assets", "app-icon-1024.png")


def set_dock_identity() -> None:
    """Fix up the Dock icon and name when the app is launched without its bundle.

    macOS identifies a process by the `.app` bundle its executable belongs to.
    Launched by the Automator applet, the app has one, cut to measure by
    `scripts/make_launcher_bundle.sh`: nothing to fix, and this function then
    merely repeats what the `Info.plist` already says.

    Launched by hand — `python launch_desktop.py` from a terminal — it inherits
    the interpreter's bundle instead, `org.python.python`, with its rocket and
    its "Python" name. That is the case the two lines below cover, via PyObjC,
    already installed since pywebview depends on it on macOS:

    - `setApplicationIconImage_()` replaces the Dock icon;
    - `CFBundleName`, written into the main bundle's dictionary, renames the
      app menu next to the Apple logo. This mutates the living dictionary of
      the current process, not anything on disk: nothing is modified outside
      the process.

    Order matters for the name: it must be set **before** `NSApplication`
    exists, because the menu is built at its creation. Hence the call before
    importing `webview`, which instantiates the Cocoa application.

    What those two lines do not reach, and what explains the bundle: the Dock
    tooltip and the process name come from the bundle on disk, out of reach of
    any runtime setting — `NSProcessInfo.setProcessName_()` included, tried
    without effect.

    Purely cosmetic: every failure is silent, a window with the wrong icon being
    better than no window.
    """
    try:
        from AppKit import NSApplication, NSImage
        from Foundation import NSBundle
    except ImportError:
        return

    info = NSBundle.mainBundle().infoDictionary()
    if info is not None:
        info["CFBundleName"] = WINDOW_TITLE

    image = NSImage.alloc().initWithContentsOfFile_(DOCK_ICON)
    if image is not None:
        NSApplication.sharedApplication().setApplicationIconImage_(image)


def allow_microphone() -> None:
    """Add to pywebview the delegate without which WKWebView refuses the mic.

    The "Quick dictation" tab records through `getUserMedia`. In a browser, the
    browser asks for permission; in a WKWebView, the host application is asked,
    via
    `webView:requestMediaCapturePermissionForOrigin:initiatedByFrame:type:decisionHandler:`.
    pywebview 6.2.1 does not implement it — its `BrowserDelegate` covers alert
    panels and the file picker, not capture — and WebKit then refuses the
    request. The method is therefore grafted onto its class.

    Two other guards sit alongside this one, and that is not redundant: the
    `NSMicrophoneUsageDescription` key in the bundle's `Info.plist`, without
    which macOS would kill the process, and the microphone permission the system
    asks the user for on the first attempt. Granting here short-circuits
    nothing: it only lets the question reach them.

    Grafting a method onto a dependency's class remains a patch to keep an eye
    on: if a version of pywebview implements this delegate, this one becomes
    useless and must go. Failure is silent — without a mic, the other tabs still
    work.
    """
    try:
        import objc
        from webview.platforms.cocoa import BrowserView
    except (ImportError, AttributeError):
        return

    delegate = getattr(BrowserView, "BrowserDelegate", None)
    if delegate is None:
        return

    selector = (
        b"webView:requestMediaCapturePermissionForOrigin:"
        b"initiatedByFrame:type:decisionHandler:"
    )
    if delegate.instancesRespondToSelector_(selector.decode()):
        return  # already provided by pywebview: overwrite nothing

    def grant(self, webview_, origin, frame, capture_type, decision_handler):
        decision_handler(1)  # WKPermissionDecisionGrant

    objc.classAddMethods(
        delegate,
        [
            objc.selector(
                grant,
                selector=selector,
                # v@:@@@q@? — nothing returned, four objects, the capture type
                # as an NSInteger, and the reply block.
                signature=b"v@:@@@q@?",
            )
        ],
    )


def port_is_taken(host: str, port: int) -> bool:
    """True if something is already listening on this port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def start_streamlit() -> subprocess.Popen:
    """Start `streamlit run app.py`, browserless, in its own session."""
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.address",
        HOST,
        "--server.port",
        str(PORT),
        # Stops Streamlit from opening a browser tab of its own.
        "--server.headless",
        "true",
        # Removes the "Deploy / Rerun / Clear cache" menu from the top right
        # corner: it addresses whoever develops the app, not whoever uses it,
        # and its actions make no sense for a local app in a window.
        "--client.toolbarMode",
        "minimal",
    ]
    # The streams stay inherited: launched by Automator, the app has no
    # terminal, and its output is directed to ~/Library/Logs/WhisperToolkit.log,
    # the only trace when something goes wrong. Redirecting to a pipe would make
    # it invisible.
    return subprocess.Popen(command, cwd=PROJECT_ROOT, start_new_session=True)


def wait_until_ready(process: subprocess.Popen, timeout: float) -> bool:
    """Probe the server until it answers. False if the delay expires or it dies."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # A dead server will never answer: no point waiting out the full delay.
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(POLL_INTERVAL)
    return False


def stop_streamlit(process: subprocess.Popen) -> None:
    """Terminate the server and all its descendants, leaving nothing on the port."""
    if process.poll() is not None:
        return
    try:
        group = os.getpgid(process.pid)
    except ProcessLookupError:
        return

    for signal_ in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(group, signal_)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=SHUTDOWN_GRACE)
            return
        except subprocess.TimeoutExpired:
            continue


def _quit_on_sigterm(signum, _frame) -> None:
    """Turn SIGTERM into an ordinary exit, so the `finally` runs.

    Without this, a `killall` or a "Force Quit" kills the launcher without
    unwinding its stack: Streamlit then outlives its parent and keeps port 8501.
    The net stays imperfect — during the Cocoa loop, the signal is only handled
    at the next pass through Python bytecode — but it covers the common case.
    """
    raise SystemExit(128 + signum)


def main() -> int:
    signal.signal(signal.SIGTERM, _quit_on_sigterm)

    if port_is_taken(HOST, PORT):
        print(
            f"Port {PORT} is already taken: an instance of Whisper Toolkit is "
            f"probably already running. Close it, or free the port with "
            f"`lsof -i :{PORT}`, then run again.",
            file=sys.stderr,
        )
        return 1

    server = start_streamlit()
    try:
        if not wait_until_ready(server, STARTUP_TIMEOUT):
            if server.poll() is not None:
                reason = f"the server stopped (code {server.returncode})"
            else:
                reason = f"no answer after {STARTUP_TIMEOUT:.0f} s"
            print(
                f"Streamlit did not start: {reason}. "
                f"The window was not opened; the details are above.",
                file=sys.stderr,
            )
            return 1

        set_dock_identity()

        # Imported here only: pywebview drags all of PyObjC along with it, and
        # paying for that before knowing whether the server answers is pointless.
        import webview

        # After the import, necessarily: the class to patch lives in pywebview.
        allow_microphone()

        webview.create_window(
            WINDOW_TITLE,
            URL,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
        )
        # Blocks until the user closes the window.
        webview.start()
        return 0
    finally:
        stop_streamlit(server)


if __name__ == "__main__":
    sys.exit(main())
