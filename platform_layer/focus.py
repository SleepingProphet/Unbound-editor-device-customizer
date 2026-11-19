# platform_layer/focus.py — foreground-application watcher (platform-neutral part)
#
# The platform modules provide get_foreground_app(); this module owns the polling
# thread, the debouncing and the "ignore our own window" rule.

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple


@dataclass(frozen=True)
class ForegroundApp:
    """The application that currently owns the foreground.

    ids   — identifiers it can be matched by, e.g. ('spotify.exe',) on Windows or
            ('com.spotify.client', 'Spotify') on macOS. Empty if the process could not
            be queried (elevated window, protected process, ...).
    pid   — process id (0 if unknown)
    """
    ids: Tuple[str, ...]
    pid: int = 0


def normalize_app_id(s: str) -> str:
    """Case-insensitive, extension-insensitive form used for comparing app identifiers."""
    s = (s or "").strip().lower()
    for ext in (".exe", ".app"):
        if s.endswith(ext):
            s = s[: -len(ext)]
    return s


class FocusWatcher:
    """Polls the foreground app on a background thread and calls `callback(app)` on change.

    * Runs entirely off the HID and GUI threads; `callback` is invoked from the watcher
      thread, so it must be thread-safe (emitting a Qt signal is).
    * Debounced: a new foreground app must stay in front for `settle` seconds before
      `callback` fires, so Alt-Tab flicker and transient popups are ignored.
    * Our own windows are ignored (the previous app stays "current"), so clicking
      into the Unbound window to edit a layer never switches layers.
    * Any exception from the platform query is swallowed and treated as "no change".
    """

    def __init__(self, get_foreground: Callable[[], Optional[ForegroundApp]],
                 callback: Callable[[ForegroundApp], None],
                 interval: float = 0.15, settle: float = 0.3):
        self._get = get_foreground
        self._callback = callback
        self._interval = interval
        self._settle = settle
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="focus-watcher", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        own_pid = os.getpid()
        reported: Optional[ForegroundApp] = None   # last app we called back with
        candidate: Optional[ForegroundApp] = None  # seen but not yet settled
        candidate_since = 0.0
        last_error = ''
        while not self._stop.wait(self._interval):
            try:
                app = self._get()
            except Exception as e:           # never let a query kill the watcher
                if str(e) != last_error:     # log once per distinct error, not every poll
                    last_error = str(e)
                    print(f'[focus] query failed: {e}')
                continue
            if app is None or app.pid == own_pid:
                candidate = None             # keep whatever was current
                continue
            if app != candidate:
                candidate, candidate_since = app, time.monotonic()
                continue
            if app != reported and time.monotonic() - candidate_since >= self._settle:
                reported = app
                try:
                    self._callback(app)
                except Exception as e:
                    print(f'[focus] callback failed: {e}')
