# overlay.py — small on-screen display showing which button was pressed and what it did
#
# Frameless, always-on-top, translucent, click-through and non-activating, so it never
# takes focus or mouse input from the game / app you are using.

import os
import sys

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics, QCursor, QGuiApplication
from PyQt6.QtWidgets import QWidget

import config as cfg

CORNERS = [("Top left", "top_left"), ("Top right", "top_right"),
           ("Bottom left", "bottom_left"), ("Bottom right", "bottom_right")]

DIAL_ACTION_NAMES = {"sys_vol": "System volume", "app_vol": "App volume", "brightness": "Brightness"}
_DIAL_NAMES = DIAL_ACTION_NAMES
_DIAL_MODE_NAMES = {"jog": "Jog", "shuttle": "Shuttle", "scroll": "Scroll"}


def describe_action(action: dict, config: dict) -> str:
    """One-line human readable description of a button action."""
    atype = action.get("action", cfg.ACTION_NONE)
    if atype == cfg.ACTION_NONE:
        return "Unassigned"
    if atype == cfg.ACTION_HOTKEY:
        return f"Hotkey: {action.get('keys', '').strip() or '?'}"
    if atype == cfg.ACTION_HOLD_KEY:
        return f"Hold: {action.get('keys', '').strip() or '?'}"
    if atype == cfg.ACTION_TOGGLE_HOLD:
        return f"Latch: {action.get('keys', '').strip() or '?'}"
    if atype == cfg.ACTION_APP_SWITCH:
        return f"Switch to {action.get('app', '').strip() or '?'}"
    if atype == cfg.ACTION_APP_LAUNCH:
        path = action.get("path", "").strip()
        return f"Launch {os.path.basename(path) if path else '?'}"
    if atype == cfg.ACTION_OBS_SCENE:
        return f"OBS scene: {action.get('scene', '').strip() or '?'}"
    if atype == cfg.ACTION_OBS_TOGGLE:
        return "OBS: " + {"stream": "toggle stream", "record": "toggle record",
                          "mute_mic": "toggle mic mute"}.get(action.get("toggle", ""), "toggle")
    if atype == cfg.ACTION_LAYER_PUSH:
        lid = action.get("layer", "")
        return f"Layer: {config.get('layers', {}).get(lid, {}).get('name', lid)}"
    if atype == cfg.ACTION_LAYER_POP:
        return "Layer: back"
    if atype == cfg.ACTION_DIAL_MODE:
        mode = action.get("mode", "normal")
        if mode == "normal":
            return "Dial: reset"
        name = _DIAL_NAMES.get(mode, mode)
        if mode == "app_vol" and action.get("app"):
            name += f" ({action['app']})"
        return f"Dial: {name}"
    return atype


def pretty_button_name(key_name: str, original_label: str = "") -> str:
    label = (original_label or "").replace("\n", " ").strip()
    return label or key_name.replace("_", " ").title()


class PressOverlay(QWidget):
    PAD_X, PAD_Y = 18, 12

    def __init__(self, config: dict):
        super().__init__(None)
        self._config = config
        self._title = ""
        self._detail = ""

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)  # macOS: stay when app inactive
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_fade)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(350)
        self._fade.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade.finished.connect(self._after_fade)
        self._native_done = False

    # -- settings ----------------------------------------------------------

    def settings(self) -> dict:
        s = dict(cfg.DEFAULT_CONFIG["overlay"])
        s.update(self._config.get("overlay", {}))
        return s

    def apply_settings(self):
        """Call after the overlay settings changed."""
        if not self.settings()["enabled"]:
            self._hide_timer.stop()
            self._fade.stop()
            self.hide()
        elif self.isVisible():
            self._relayout()
            self.setWindowOpacity(self.settings()["opacity"] / 100)

    # -- public API --------------------------------------------------------

    def show_press(self, button_name: str, action_label: str):
        self._show(button_name, action_label)

    def show_dial(self, mode_name: str, direction: str, action_label: str):
        arrow = "→ right" if direction == "right" else "← left"
        self._show(f"Jog wheel {arrow}", f"{_DIAL_MODE_NAMES.get(mode_name, mode_name)}: {action_label}")

    # -- internals ---------------------------------------------------------

    def _show(self, title: str, detail: str):
        s = self.settings()
        if not s["enabled"]:
            return
        self._title, self._detail = title, detail
        self._fade.stop()
        self._relayout()
        self.setWindowOpacity(s["opacity"] / 100)
        if not self.isVisible():
            self.show()          # WA_ShowWithoutActivating: does not take focus
        self._apply_native_flags()
        self.raise_()
        self.update()
        self._hide_timer.start(int(s["duration"] * 1000))

    def _fonts(self):
        size = int(self.settings()["font_size"])
        title = QFont(self.font()); title.setPointSize(size); title.setBold(True)
        detail = QFont(self.font()); detail.setPointSize(max(6, round(size * 0.8)))
        return title, detail

    def _relayout(self):
        tf, df = self._fonts()
        tw = QFontMetrics(tf).horizontalAdvance(self._title)
        dw = QFontMetrics(df).horizontalAdvance(self._detail)
        th, dh = QFontMetrics(tf).height(), QFontMetrics(df).height()
        w = max(tw, dw) + 2 * self.PAD_X
        h = th + dh + 2 * self.PAD_Y + 2
        self.setFixedSize(w, h)
        s = self.settings()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        m = int(s["margin"])
        x = geo.left() + m if s["corner"].endswith("left") else geo.right() - w - m + 1
        y = geo.top() + m if s["corner"].startswith("top") else geo.bottom() - h - m + 1
        self.move(x, y)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 18, 32, 235))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        tf, df = self._fonts()
        p.setFont(tf)
        p.setPen(QColor("#e0e7ff"))
        th = QFontMetrics(tf).height()
        p.drawText(self.PAD_X, self.PAD_Y + QFontMetrics(tf).ascent(), self._title)
        p.setFont(df)
        p.setPen(QColor("#94a3b8"))
        p.drawText(self.PAD_X, self.PAD_Y + th + 2 + QFontMetrics(df).ascent(), self._detail)

    def _start_fade(self):
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _after_fade(self):
        if self.windowOpacity() <= 0.01:
            self.hide()

    def _apply_native_flags(self):
        """Belt and braces on Windows: click-through + no-activate + layered tool window."""
        if self._native_done or sys.platform != "win32":
            return
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = 0x20, 0x08000000
            WS_EX_TOOLWINDOW, WS_EX_LAYERED = 0x80, 0x80000
            user32 = ctypes.windll.user32
            get = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            setl = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get.restype = ctypes.c_ssize_t
            setl.restype = ctypes.c_ssize_t
            setl.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            get.argtypes = [ctypes.c_void_p, ctypes.c_int]
            hwnd = int(self.winId())
            ex = get(hwnd, GWL_EXSTYLE)
            setl(hwnd, GWL_EXSTYLE, ex | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
                 | WS_EX_TOOLWINDOW | WS_EX_LAYERED)
            self._native_done = True
        except Exception as e:
            print(f'[overlay] could not set native window flags: {e}')
