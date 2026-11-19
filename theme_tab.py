# theme_tab.py — "Theme" settings tab: color pickers, image pickers, reset, import/export
#
# Changes are applied live (the whole UI restyles as you pick) and saved to theme.json
# shortly after the last change.

import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel, QPushButton,
    QLineEdit, QComboBox, QSlider, QScrollArea, QColorDialog, QFileDialog, QMessageBox,
)

import theme

_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All files (*)"


def _contrast(hex_color: str) -> str:
    q = QColor(hex_color)
    return "#000000" if (q.red() * 299 + q.green() * 587 + q.blue() * 114) / 1000 > 140 else "#ffffff"


class _Swatch(QPushButton):
    """Button showing a color; opens a live-preview color dialog when clicked."""

    def __init__(self, get_hex, set_hex, title, on_commit, parent=None):
        super().__init__(parent)
        self._get, self._set, self._title, self._commit = get_hex, set_hex, title, on_commit
        self.setMinimumWidth(110)
        self.clicked.connect(self._pick)
        self.refresh()

    def refresh(self):
        h = self._get()
        self.setText(h)
        # Intentionally not themed: the swatch must show the actual color it represents.
        self.setStyleSheet(f"QPushButton {{ background-color: {h}; color: {_contrast(h)};"
                           f" border: 1px solid #888888; border-radius: 6px; padding: 4px 8px; }}")

    def _pick(self):
        original = self._get()
        dlg = QColorDialog(QColor(original), self)
        dlg.setWindowTitle(self._title)
        dlg.currentColorChanged.connect(lambda col: self._set(col.name(), False))   # live preview
        if dlg.exec():
            self._set(dlg.currentColor().name(), False)
            self._commit()
        else:
            self._set(original, False)       # cancelled: put the old color back
        self.refresh()


class ThemeTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._building = False
        self._swatches: list[_Swatch] = []
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(theme.save)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._colors_group())
        layout.addWidget(self._advanced_group())
        layout.addWidget(self._actions_group())
        layout.addWidget(self._images_group())
        layout.addLayout(self._buttons_row())
        self._status = QLabel("")
        layout.addWidget(self._status)

        theme.add_listener(self._refresh)
        self._refresh()

    # -- construction ------------------------------------------------------

    def _swatch(self, grid, row, label, get_hex, set_hex, title=None):
        grid.addWidget(QLabel(label), row, 0)
        sw = _Swatch(get_hex, set_hex, title or label, self._schedule_save)
        grid.addWidget(sw, row, 1)
        self._swatches.append(sw)

    def _colors_group(self):
        g = QGroupBox("Colors")
        grid = QGridLayout(g)
        for i, (token, label) in enumerate(theme.BASIC_COLORS):
            self._swatch(grid, i, label, lambda t=token: theme.c(t),
                         lambda v, s, t=token: theme.set_basic(t, v, save_now=False))
        note = QLabel("Changing a color here also shifts the related shades (hover, pressed, …). "
                      "Fine-tune them under Advanced colors.")
        note.setWordWrap(True)
        grid.addWidget(note, len(theme.BASIC_COLORS), 0, 1, 2)
        return g

    def _advanced_group(self):
        g = QGroupBox("Advanced colors")
        toggle = QPushButton("Show")
        toggle.setCheckable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(0, 0, 0, 0)
        tokens = [t for t in theme.COLOR_LABELS]
        for i, token in enumerate(tokens):
            self._swatch(grid, i, theme.COLOR_LABELS[token], lambda t=token: theme.c(t),
                         lambda v, s, t=token: theme.set_color(t, v, save_now=False))
        lay = QVBoxLayout(g)
        lay.addWidget(toggle)
        lay.addWidget(inner)
        inner.setVisible(False)
        toggle.toggled.connect(inner.setVisible)
        toggle.toggled.connect(lambda on: toggle.setText("Hide" if on else "Show"))
        return g

    def _actions_group(self):
        g = QGroupBox("Button colors by action")
        grid = QGridLayout(g)
        for i, (atype, label) in enumerate(theme.ACTION_LABELS.items()):
            self._swatch(grid, i, label, lambda a=atype: theme.action_color(a),
                         lambda v, s, a=atype: theme.set_action_color(a, v, save_now=False))
        return g

    def _images_group(self):
        g = QGroupBox("Images")
        grid = QGridLayout(g)
        self._img = {}
        row = 0
        for slot in theme.IMAGE_SLOTS:
            grid.addWidget(QLabel(theme.IMAGE_SLOT_LABELS[slot]), row, 0, 1, 4)
            path = QLineEdit()
            path.setReadOnly(True)
            path.setPlaceholderText("No image")
            browse = QPushButton("Browse…")
            clear = QPushButton("Clear")
            grid.addWidget(path, row + 1, 0, 1, 2)
            grid.addWidget(browse, row + 1, 2)
            grid.addWidget(clear, row + 1, 3)
            opacity = QSlider(Qt.Orientation.Horizontal)
            opacity.setRange(0, 100)
            olabel = QLabel("100%")
            mode = QComboBox()
            for m in theme.IMAGE_MODES:
                mode.addItem(m.capitalize(), m)
            grid.addWidget(QLabel("Opacity"), row + 2, 0)
            grid.addWidget(opacity, row + 2, 1)
            grid.addWidget(olabel, row + 2, 2)
            grid.addWidget(mode, row + 2, 3)
            err = QLabel("")
            err.setStyleSheet("color: #f87171;")     # status text, intentionally not themed
            grid.addWidget(err, row + 3, 0, 1, 4)
            browse.clicked.connect(lambda _=False, s=slot: self._browse(s))
            clear.clicked.connect(lambda _=False, s=slot: self._set_image(s, path=""))
            opacity.valueChanged.connect(lambda v, s=slot: self._set_image(s, opacity=v))
            mode.currentIndexChanged.connect(
                lambda _i, s=slot: self._set_image(s, mode=self._img[s]["mode"].currentData()))
            self._img[slot] = {"path": path, "opacity": opacity, "olabel": olabel,
                               "mode": mode, "err": err}
            row += 4
        return g

    def _buttons_row(self):
        row = QHBoxLayout()
        reset = QPushButton("Reset to default")
        exp = QPushButton("Export theme…")
        imp = QPushButton("Import theme…")
        reset.clicked.connect(self._reset)
        exp.clicked.connect(self._export)
        imp.clicked.connect(self._import)
        for b in (reset, exp, imp):
            row.addWidget(b)
        row.addStretch()
        return row

    # -- actions -----------------------------------------------------------

    def _schedule_save(self):
        self._save_timer.start()

    def _set_image(self, slot, **fields):
        if self._building:
            return
        theme.set_image(slot, save_now=False, **fields)
        self._schedule_save()

    def _browse(self, slot):
        start = os.path.dirname(theme.get()["images"][slot]["path"]) or ""
        path, _ = QFileDialog.getOpenFileName(self, theme.IMAGE_SLOT_LABELS[slot], start, _IMAGE_FILTER)
        if path:
            self._set_image(slot, path=path)

    def _reset(self):
        if QMessageBox.question(self, "Reset theme", "Reset all colors and images to the default theme?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) == QMessageBox.StandardButton.Yes:
            theme.reset()
            self._say("Theme reset.")

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export theme", "theme.json", "JSON files (*.json)")
        if not path:
            return
        try:
            theme.export_to(path)
            self._say("Theme exported (images are referenced by path, not embedded).")
        except OSError as e:
            self._say(f"Export failed: {e}", error=True)

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import theme", "", "JSON files (*.json)")
        if not path:
            return
        try:
            theme.import_from(path)
            self._say("Theme imported.")
        except (OSError, ValueError) as e:
            self._say(f"Import failed: {e}", error=True)

    def _say(self, text, error=False):
        self._status.setText(text)
        self._status.setStyleSheet("color: #f87171;" if error else "color: #4ade80;")

    # -- sync UI <- theme --------------------------------------------------

    def _refresh(self):
        self._building = True
        try:
            for sw in self._swatches:
                sw.refresh()
            for slot, w in self._img.items():
                img = theme.get()["images"][slot]
                w["path"].setText(img["path"])
                w["opacity"].setValue(img["opacity"])
                w["olabel"].setText(f"{img['opacity']}%")
                w["mode"].setCurrentIndex(max(0, w["mode"].findData(img["mode"])))
                _, error = theme.pixmap(slot)
                w["err"].setText(f"{error}: {img['path']}" if error else "")
        finally:
            self._building = False
