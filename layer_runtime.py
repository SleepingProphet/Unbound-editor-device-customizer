# layer_runtime.py — which layer is active right now
#
# PRECEDENCE (read this before touching layer switching):
#
#   effective layer = top of manual stack   if the stack is non-empty
#                     else the base layer
#
#   * base layer   — chosen automatically from the foreground application: the first
#                    layer (in config order, default excluded) whose "match" list fits
#                    the focused app, otherwise the default layer.
#   * manual stack — layers pushed by "Layer: Push" buttons and removed by "Layer: Back".
#                    They sit ON TOP of the base layer, so a manual push always wins
#                    over the focus-matched layer for as long as the user stays in that app.
#   * focus change — any (debounced) change of foreground app RESETS the manual stack and
#                    sets a new base. Pushed layers are a temporary "menu"; once the
#                    user moves to another app that menu is stale, so we drop it.
#
# If no layer defines a "match" list the focus feature is inert: focus changes are
# ignored entirely, so users who don't use it never see their pushed layers reset.
#
# All methods are thread-safe: they are called from the HID thread (push/pop/current)
# and the focus watcher thread (on_focus). `on_change(layer_id)` is invoked OUTSIDE the
# lock with the new effective layer, and only when that layer actually changed or the
# manual stack was cleared; wire it to a Qt signal.

import threading
from typing import Callable, Optional

import config as cfg
from platform_layer.focus import ForegroundApp


class LayerRuntime:
    def __init__(self, config: dict, on_change: Callable[[str], None]):
        self._config = config
        self._on_change = on_change
        self._lock = threading.RLock()
        self._base = cfg.DEFAULT_LAYER_ID
        self._manual: list[str] = []

    # -- queries -----------------------------------------------------------

    def current(self) -> str:
        with self._lock:
            return self._manual[-1] if self._manual else self._base

    # -- manual layer switching (HID thread) --------------------------------

    def push(self, layer_id: str):
        with self._lock:
            self._manual.append(layer_id)
            new = self._manual[-1]
        self._on_change(new)

    def pop(self):
        with self._lock:
            if self._manual:
                self._manual.pop()
            new = self._manual[-1] if self._manual else self._base
        self._on_change(new)

    # -- focus-driven switching (focus watcher thread) ----------------------

    def on_focus(self, app: Optional[ForegroundApp]):
        if app is None:
            return
        try:
            if not cfg.any_layer_has_match(self._config):
                return                      # feature unused: leave manual state alone
            target = cfg.find_layer_for_app(self._config, app.ids)
        except Exception as e:              # config is edited by the GUI thread concurrently
            print(f'[focus] could not evaluate layer matches: {e}')
            return
        with self._lock:
            before = self.current()
            self._base = target
            self._manual.clear()            # focus change resets manual pushes (see top)
            after = self._base
        print(f'[focus] {app.ids or "<unqueryable>"} -> layer {after!r}')
        if after != before:
            self._on_change(after)
