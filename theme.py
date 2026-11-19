# theme.py — theming for the whole UI: colors, per-action colors, background images
#
# Everything visual that used to be hardcoded in app.py lives here:
#   * tokens          semantic color names -> hex (defaults == the original look)
#   * QSS templates   written with $token placeholders, rendered from the active theme
#   * images          optional backgrounds for the main window / editor widget and an
#                     overlay image above the device graphic
#   * persistence     theme.json next to config.json; import/export of theme files
#
# The active theme is module state (one theme per process). Call apply_all(app) after
# changing it; widgets styled with bind() are restyled automatically.

import colorsys
import copy
import json
import os
import string
import weakref

from PyQt6.QtCore import Qt, QRect, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPixmap

import config as cfg

THEME_FILE = os.path.join(cfg._app_dir(), "theme.json")

# --------------------------------------------------------------------------- defaults

DEFAULT_COLORS = {
    # basics (user-facing)
    "accent":          "#6366f1",
    "bg":              "#080d18",
    "panel":           "#10172a",
    "button":          "#1a2540",
    "text":            "#e2e8f0",
    "border":          "#1e2d50",
    "text_muted":      "#64748b",
    # derived / advanced
    "card":            "#0c1220",
    "panel_focus":     "#131c33",
    "tab_hover":       "#162040",
    "button_hover":    "#243260",
    "button_border":   "#2d3f6e",
    "button_disabled": "#0f1525",
    "border_strong":   "#3d5080",
    "accent_strong":   "#4338ca",
    "accent_hover":    "#4f46e5",
    "accent_light":    "#818cf8",
    "accent_lighter":  "#a5b4fc",
    "tab_active":      "#3730a3",
    "text_strong":     "#ffffff",
    "text_title":      "#c7d2fe",
    "text_bright":     "#e0e7ff",
    "text_label":      "#cbd5e1",
    "text_soft":       "#94a3b8",
    "text_disabled":   "#334155",
    # dial widget / dial-mode buttons
    "dial_button_active": "#5b21b6",
    "dial_fill_active":   "#4c1d95",
}

DEFAULT_ACTIONS = {
    cfg.ACTION_NONE:         "#141c30",  # unassigned — deep navy slate
    cfg.ACTION_HOTKEY:       "#1e3a8a",  # indigo blue
    cfg.ACTION_HOLD_KEY:     "#0e4b4b",  # deep teal
    cfg.ACTION_TOGGLE_HOLD:  "#0a4060",  # dark cyan
    cfg.ACTION_APP_SWITCH:   "#14532d",  # emerald dark
    cfg.ACTION_APP_LAUNCH:   "#1a5c35",  # forest green dark
    cfg.ACTION_OBS_SCENE:    "#7c1d1d",  # deep crimson
    cfg.ACTION_OBS_TOGGLE:   "#4c1d95",  # deep violet
    cfg.ACTION_LAYER_PUSH:   "#78350f",  # amber dark
    cfg.ACTION_LAYER_POP:    "#1e3a6a",  # steel blue
    cfg.ACTION_DIAL_MODE:    "#3b0f6e",  # ultra-deep purple
}

IMAGE_SLOTS = ("window", "editor", "device")
IMAGE_SLOT_LABELS = {"window": "Main window background",
                     "editor": "Editor widget background",
                     "device": "Overlay above the device graphic"}
IMAGE_MODES = ("cover", "contain", "tile")

DEFAULT_IMAGES = {
    "window": {"path": "", "opacity": 100, "mode": "cover"},
    "editor": {"path": "", "opacity": 100, "mode": "cover"},
    "device": {"path": "", "opacity": 100, "mode": "contain"},
}

DEFAULT_THEME = {"version": 1, "colors": DEFAULT_COLORS, "actions": DEFAULT_ACTIONS,
                 "images": DEFAULT_IMAGES}

# The "basic" pickers. Editing one also moves its derived tokens by the same HSL delta,
# so a red accent gets red hover/pressed shades instead of leftover indigo ones.
BASIC_COLORS = [
    ("accent", "Accent"), ("bg", "Background"), ("panel", "Panels"), ("button", "Buttons"),
    ("text", "Text"), ("border", "Borders"), ("text_muted", "Muted text"),
]
DERIVED_FROM = {
    "accent":     ["accent_strong", "accent_hover", "accent_light", "accent_lighter", "tab_active"],
    "bg":         ["card"],
    "panel":      ["panel_focus", "tab_hover"],
    "button":     ["button_hover", "button_border", "button_disabled", "border_strong"],
    "text":       ["text_title", "text_bright", "text_label"],
    "text_muted": ["text_soft", "text_disabled"],
}
COLOR_LABELS = {
    "card": "Editor card", "panel_focus": "Input (focused)", "tab_hover": "Tab hover",
    "button_hover": "Button hover", "button_border": "Button border",
    "button_disabled": "Button disabled", "border_strong": "Border (strong)",
    "accent_strong": "Accent (pressed/selected)", "accent_hover": "Accent (hover)",
    "accent_light": "Accent (light)", "accent_lighter": "Accent (lighter)",
    "tab_active": "Active tab", "text_strong": "Text (on accent)", "text_title": "Text (titles)",
    "text_bright": "Text (bright)", "text_label": "Text (labels)", "text_soft": "Text (soft)",
    "text_disabled": "Text (disabled)", "dial_button_active": "Dial button (active)",
    "dial_fill_active": "Dial circle (active)",
}
ACTION_LABELS = {
    cfg.ACTION_NONE: "Unassigned", cfg.ACTION_HOTKEY: "Hotkey", cfg.ACTION_HOLD_KEY: "Hold key",
    cfg.ACTION_TOGGLE_HOLD: "Toggle hold", cfg.ACTION_APP_SWITCH: "App switch",
    cfg.ACTION_APP_LAUNCH: "App launch", cfg.ACTION_OBS_SCENE: "OBS scene",
    cfg.ACTION_OBS_TOGGLE: "OBS toggle", cfg.ACTION_LAYER_PUSH: "Layer push",
    cfg.ACTION_LAYER_POP: "Layer back", cfg.ACTION_DIAL_MODE: "Dial mode",
}

# --------------------------------------------------------------------------- QSS templates

GLOBAL_QSS = """
/* ── Base ──────────────────────────────────────────────────────────────────── */
QMainWindow {
    background-color: $bg;
}
QDialog {
    background-color: $panel;
}

/* ── Tabs (main Buttons / Settings tabs) ───────────────────────────────────── */
QTabWidget::pane {
    background-color: $page_bg;
    border: 1px solid $border;
    border-radius: 0 10px 10px 10px;
}
QTabWidget > QWidget {
    background-color: $page_bg;
}
QTabBar::tab {
    background-color: $panel;
    color: $text_muted;
    border: 1px solid $border;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 7px 20px;
    margin-right: 3px;
    font-weight: 600;
    font-size: 13px;
    letter-spacing: 0.3px;
}
QTabBar::tab:selected {
    background-color: $tab_active;
    color: $text_bright;
    border-color: $accent_strong;
}
QTabBar::tab:hover:!selected {
    background-color: $tab_hover;
    color: $text_title;
    border-color: $accent_strong;
}

/* ── Generic QPushButton ───────────────────────────────────────────────────── */
QPushButton {
    background-color: $button;
    color: $text_title;
    border: 1px solid $button_border;
    border-radius: 7px;
    padding: 5px 14px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover {
    background-color: $button_hover;
    border-color: $accent;
    color: $text_bright;
}
QPushButton:pressed {
    background-color: $accent_strong;
    border-color: $accent_light;
    color: $text_strong;
}
QPushButton:disabled {
    background-color: $button_disabled;
    color: $text_disabled;
    border-color: $border;
}

/* ── QLineEdit ──────────────────────────────────────────────────────────────── */
QLineEdit {
    background-color: $panel;
    color: $text;
    border: 1px solid $button_border;
    border-radius: 7px;
    padding: 5px 10px;
    selection-background-color: $accent_strong;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: $accent;
    background-color: $panel_focus;
}
QLineEdit:disabled {
    color: $text_disabled;
}

/* ── QComboBox ──────────────────────────────────────────────────────────────── */
QComboBox {
    background-color: $button;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 7px;
    padding: 4px 10px;
    min-height: 28px;
    font-size: 13px;
}
QComboBox:hover  { border-color: $accent; background-color: $border; }
QComboBox:focus  { border-color: $accent; }
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow {
    width: 0; height: 0;
    border-left:  5px solid transparent;
    border-right: 5px solid transparent;
    border-top:   5px solid $text_soft;
    margin-right: 8px;
}

/* QComboBox popup colors/hover are handled entirely by QPalette (see MainWindow.__init__) */

/* ── QGroupBox ──────────────────────────────────────────────────────────────── */
QGroupBox {
    background-color: $panel;
    border: 1px solid $border;
    border-radius: 12px;
    margin-top: 16px;
    padding: 14px 12px 12px 12px;
    font-weight: 700;
    font-size: 11px;
    color: $text_muted;
    letter-spacing: 0.8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: -1px;
    color: $accent;
    background-color: $panel;
    padding: 0 6px;
    text-transform: uppercase;
}

/* ── QListWidget ────────────────────────────────────────────────────────────── */
QListWidget {
    border: 1px solid $border;
    border-radius: 8px;
    outline: none;
    font-size: 13px;
}

/* ── QSlider ────────────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 4px;
    background: $border;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: $accent;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: $accent_light;
    border: 2px solid $accent;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background: $accent_lighter;
    border-color: $accent_light;
}

/* ── QLabel ─────────────────────────────────────────────────────────────────── */
QLabel {
    color: $text_label;
    background: transparent;
}

/* ── QStatusBar ─────────────────────────────────────────────────────────────── */
QStatusBar {
    background-color: $panel;
    color: $text_muted;
    border-top: 1px solid $border;
    font-size: 12px;
}

/* ── QScrollBar ─────────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: $panel;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: $button_border;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover  { background: $accent; }
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical      { height: 0; }

/* ── QScrollArea / generic pane backgrounds ─────────────────────────────────── */
QScrollArea { border: none; background: transparent; }

/* ── QSpinBox ───────────────────────────────────────────────────────────────── */
QSpinBox {
    background-color: $panel;
    color: $text;
    border: 1px solid $button_border;
    border-radius: 7px;
    padding: 4px 8px;
}
QSpinBox:focus { border-color: $accent; }

/* ── QDialogButtonBox ───────────────────────────────────────────────────────── */
QDialogButtonBox QPushButton { min-width: 80px; }

/* ── QMessageBox ────────────────────────────────────────────────────────────── */
QMessageBox QLabel { color: $text; }
"""

# Former inline styles. Names are used with bind(widget, TEMPLATES[name]).
MUTED_LABEL = "color: $text_muted; font-size: 12px;"
HINT_LABEL = "color: $text_muted; font-size: 11px;"
TITLE_LABEL = "color: $text_title; padding-bottom: 8px; font-size: 13px;"
DIAL_TITLE_LABEL = "color: $text_title; padding-bottom: 8px;"
PAGE_BG = "background-color: $page_bg;"
EDITOR_TRANSPARENT = "background: transparent; border: none;"

SAVE_BUTTON = """
    QPushButton {
        background-color: $accent_strong;
        color: $text_strong;
        border: 1px solid $accent;
        border-radius: 7px;
        padding: 7px 16px;
        font-weight: 700;
        font-size: 13px;
    }
    QPushButton:hover {
        background-color: $accent_hover;
        border-color: $accent_light;
    }
    QPushButton:pressed {
        background-color: $accent;
    }
    QPushButton:disabled {
        background-color: $button;
        color: $text_disabled;
        border-color: $border;
    }
"""

LAYER_TABS = """
    QTabBar::tab {
        background-color: $button;
        color: $text_muted;
        border: 1px solid $button_border;
        border-radius: 6px;
        padding: 5px 16px;
        margin-right: 3px;
        font-weight: 600;
        font-size: 12px;
    }
    QTabBar::tab:selected {
        background-color: $tab_active;
        color: $text_bright;
        border-color: $accent_strong;
    }
    QTabBar::tab:hover:!selected {
        background-color: $button_hover;
        color: $text_title;
        border-color: $accent_strong;
    }
"""

LAYER_BUTTON = """
    QPushButton {
        background-color: $button;
        color: $text_soft;
        border: 1px solid $button_border;
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton:hover {
        background-color: $button_hover;
        border-color: $accent;
        color: $text_bright;
    }
    QPushButton:pressed {
        background-color: $accent_strong;
        color: $text_strong;
    }
    QPushButton:disabled {
        color: $text_disabled;
        border-color: $border;
        background-color: $button_disabled;
    }
"""

EDITOR_CARD = """
    QWidget {
        background-color: $card;
        border: 1px solid $border;
        border-radius: 12px;
    }
"""

ACTION_PANEL = """
    ActionPanel {
        background-color: $panel;
        border: 1px solid $border;
        border-radius: 12px;
    }
"""

# --------------------------------------------------------------------------- state

_theme: dict = copy.deepcopy(DEFAULT_THEME)
_listeners: list = []
_bound: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_save_error = ""


def _norm_hex(value):
    """'#RRGGBB' lower-case, or None if value is not a valid color."""
    if not isinstance(value, str):
        return None
    c = QColor(value.strip())
    if not c.isValid():
        return None
    return c.name(QColor.NameFormat.HexRgb).lower()


def _normalize(data) -> dict:
    """Merge arbitrary (possibly corrupt/hand-edited) data over the defaults."""
    out = copy.deepcopy(DEFAULT_THEME)
    if not isinstance(data, dict):
        return out
    for section, defaults in (("colors", DEFAULT_COLORS), ("actions", DEFAULT_ACTIONS)):
        src = data.get(section)
        if isinstance(src, dict):
            for k in defaults:
                v = _norm_hex(src.get(k))
                if v:
                    out[section][k] = v
    imgs = data.get("images")
    if isinstance(imgs, dict):
        for slot in IMAGE_SLOTS:
            s = imgs.get(slot)
            if not isinstance(s, dict):
                continue
            if isinstance(s.get("path"), str):
                out["images"][slot]["path"] = s["path"]
            try:
                out["images"][slot]["opacity"] = max(0, min(100, int(s.get("opacity", 100))))
            except (TypeError, ValueError):
                pass
            if s.get("mode") in IMAGE_MODES:
                out["images"][slot]["mode"] = s["mode"]
    return out


# --------------------------------------------------------------------------- access

def get() -> dict:
    return _theme


def c(token: str) -> str:
    """Hex color of a token."""
    return _theme["colors"][token]


def qc(token: str) -> QColor:
    return QColor(c(token))


def rgb(token: str) -> str:
    q = qc(token)
    return f"{q.red()}, {q.green()}, {q.blue()}"


def action_color(atype: str) -> str:
    return _theme["actions"].get(atype) or _theme["actions"][cfg.ACTION_NONE]


def selected_border() -> str:
    return f"2px solid {c('accent_light')}"


def default_border() -> str:
    return f"1px solid {c('button_border')}"


def window_image_active() -> bool:
    return pixmap("window")[0] is not None


def _values() -> dict:
    v = dict(_theme["colors"])
    v["accent_rgb"] = rgb("accent")
    v["page_bg"] = "transparent" if window_image_active() else v["bg"]
    return v


def render(template: str) -> str:
    return string.Template(template).safe_substitute(_values())


def bind(widget, template: str):
    """Style a widget from a $token template and restyle it whenever the theme changes."""
    _bound[widget] = template
    widget.setStyleSheet(render(template))


def add_listener(fn):
    """fn() is called after every theme change (colors, images, reset, import)."""
    _listeners.append(fn)


# --------------------------------------------------------------------------- mutation

def _changed(save_now=False):
    apply_all()
    if save_now:
        save()


def set_color(token: str, value: str, save_now=True):
    v = _norm_hex(value)
    if v and token in DEFAULT_COLORS:
        _theme["colors"][token] = v
        _changed(save_now)


def _shift(derived_hex, base_old_hex, base_new_hex) -> str:
    ho, lo, so = colorsys.rgb_to_hls(*QColor(base_old_hex).getRgbF()[:3])
    hn, ln, sn = colorsys.rgb_to_hls(*QColor(base_new_hex).getRgbF()[:3])
    h, l, s = colorsys.rgb_to_hls(*QColor(derived_hex).getRgbF()[:3])
    h = (h + (hn - ho)) % 1.0
    l = max(0.0, min(1.0, l + (ln - lo)))
    s = max(0.0, min(1.0, s * (sn / so) if so > 0.02 else s + (sn - so)))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return QColor.fromRgbF(r, g, b).name(QColor.NameFormat.HexRgb).lower()


def set_basic(token: str, value: str, save_now=True):
    """Set a basic color and move the colors derived from it accordingly."""
    v = _norm_hex(value)
    if not v or token not in DEFAULT_COLORS:
        return
    _theme["colors"][token] = v
    for d in DERIVED_FROM.get(token, []):
        _theme["colors"][d] = _shift(DEFAULT_COLORS[d], DEFAULT_COLORS[token], v)
    _changed(save_now)


def set_action_color(atype: str, value: str, save_now=True):
    v = _norm_hex(value)
    if v and atype in DEFAULT_ACTIONS:
        _theme["actions"][atype] = v
        _changed(save_now)


def set_image(slot: str, save_now=True, **fields):
    img = _theme["images"][slot]
    if "path" in fields:
        img["path"] = str(fields["path"] or "")
    if "opacity" in fields:
        img["opacity"] = max(0, min(100, int(fields["opacity"])))
    if "mode" in fields and fields["mode"] in IMAGE_MODES:
        img["mode"] = fields["mode"]
    _changed(save_now)


def reset(save_now=True):
    global _theme
    _theme = copy.deepcopy(DEFAULT_THEME)
    _changed(save_now)


# --------------------------------------------------------------------------- persistence

def load():
    """Load theme.json. A missing, unreadable or corrupt file yields the default theme."""
    global _theme
    try:
        with open(THEME_FILE, "r", encoding="utf-8") as f:
            _theme = _normalize(json.load(f))
    except FileNotFoundError:
        _theme = copy.deepcopy(DEFAULT_THEME)
    except (OSError, ValueError) as e:
        print(f"[theme] could not read {THEME_FILE} ({e}); using default theme")
        _theme = copy.deepcopy(DEFAULT_THEME)


def save() -> bool:
    global _save_error
    try:
        _write(THEME_FILE)
        _save_error = ""
        return True
    except OSError as e:
        _save_error = str(e)
        print(f"[theme] could not save theme: {e}")
        return False


def _write(path: str):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_theme, f, indent=2)
    os.replace(tmp, path)


def export_to(path: str):
    _write(path)


def import_from(path: str):
    """Replace the theme with the one in `path`. Raises ValueError if it is not a theme file."""
    global _theme
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not any(k in data for k in ("colors", "actions", "images")):
        raise ValueError("Not a theme file (expected 'colors', 'actions' or 'images').")
    _theme = _normalize(data)
    _changed(True)


# --------------------------------------------------------------------------- application

def build_palette(base: QPalette) -> QPalette:
    pal = QPalette(base)
    roles = {
        QPalette.ColorRole.Highlight: "accent_strong", QPalette.ColorRole.HighlightedText: "text_strong",
        QPalette.ColorRole.Window: "bg", QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "button", QPalette.ColorRole.AlternateBase: "panel",
        QPalette.ColorRole.Text: "text", QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.Button: "button", QPalette.ColorRole.Mid: "border_strong",
        QPalette.ColorRole.Dark: "border", QPalette.ColorRole.Shadow: "bg",
    }
    # Fusion ignores QSS ::item:hover and uses QPalette::Highlight instead.
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, token in roles.items():
            pal.setColor(group, role, qc(token))
    return pal


def apply_all(app=None):
    """Re-render the app stylesheet + palette, restyle bound widgets, notify listeners."""
    from PyQt6.QtWidgets import QApplication
    app = app or QApplication.instance()
    if app is None:
        return
    app.setStyleSheet(render(GLOBAL_QSS))
    app.setPalette(build_palette(app.palette()))
    for widget, template in list(_bound.items()):
        try:
            widget.setStyleSheet(render(template))
        except RuntimeError:        # underlying C++ widget already deleted
            pass
    for fn in list(_listeners):
        try:
            fn()
        except Exception as e:
            print(f"[theme] listener failed: {e}")


# --------------------------------------------------------------------------- images

_pix_cache: dict = {}      # path -> (mtime, QPixmap | None, error)
_scaled_cache: dict = {}   # slot -> (key, QPixmap)


def _load_pixmap(path: str):
    if not path:
        return None, ""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None, "File not found"
    cached = _pix_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    pm = QPixmap(path)
    if pm.isNull():
        entry = (mtime, None, "Could not read image (unsupported or corrupt file)")
    else:
        entry = (mtime, pm, "")
    _pix_cache[path] = entry
    return entry[1], entry[2]


def pixmap(slot: str):
    """(QPixmap | None, error text). Never raises; missing/corrupt files give (None, reason)."""
    return _load_pixmap(_theme["images"][slot]["path"])


def paint_image(painter: QPainter, rect: QRect, slot: str, radius: float = 0):
    """Draw the slot's image into rect using its mode and opacity (no-op if unavailable)."""
    img = _theme["images"][slot]
    pm, _ = pixmap(slot)
    if pm is None or rect.width() <= 0 or rect.height() <= 0:
        return
    painter.save()
    painter.setOpacity(img["opacity"] / 100)
    if radius:
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(rect), radius, radius)
        painter.setClipPath(clip)
    else:
        painter.setClipRect(rect)
    mode = img["mode"]
    if mode == "tile":
        painter.drawTiledPixmap(rect, pm)
    else:
        aspect = (Qt.AspectRatioMode.KeepAspectRatioByExpanding if mode == "cover"
                  else Qt.AspectRatioMode.KeepAspectRatio)
        key = (img["path"], rect.width(), rect.height(), mode)
        cached = _scaled_cache.get(slot)
        if cached and cached[0] == key:
            scaled = cached[1]
        else:
            scaled = pm.scaled(rect.size(), aspect, Qt.TransformationMode.SmoothTransformation)
            _scaled_cache[slot] = (key, scaled)
        x = rect.x() + (rect.width() - scaled.width()) // 2
        y = rect.y() + (rect.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
    painter.restore()
