"""The "Night shelf" theme: tokens, palettes, the application stylesheet and Hanken Grotesk.

This is the ONLY module that contains colour values. Everything else asks a
``Palette`` for a token by name (``palette.color("hue")``). The values below
are copied from ``design/nightshelf/tokens.json`` by hand (the design folder is
not packaged, so it cannot be read at run time); ``tests/test_theme.py`` asserts
they are equal, so drift fails the test.

Night shelf has no gradients, glows, shadows at rest or borders on cards:
elevation is lightness alone (ground < surface < raised), the one hue is used
only for progress, the selected count card and the focus ring, and the primary
action is inverted (white on black at night, black on white by day).
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import QApplication, QWidget

__all__ = [
    "APPEARANCES",
    "DAY",
    "FAMILY",
    "MOTION",
    "NIGHT",
    "Palette",
    "RADIUS",
    "SIZE",
    "SPACE",
    "TOKENS",
    "TYPE",
    "apply",
    "build_stylesheet",
    "current",
    "load_fonts",
    "notifier",
    "reduce_motion_enabled",
    "reset",
    "resolve_scheme",
    "set_base_size",
    "set_reduce_motion",
    "system_scheme",
]

TOKENS: dict[str, dict[str, str]] = {
    "dark": {
        "ground": "#000000",
        "surface": "#111111",
        "raised": "#2A2A2A",
        "control": "#444444",
        "text": "#FFFFFF",
        "muted": "#B4B4B4",
        "faint": "#949494",
        "hue": "#7CC4FF",
        "track": "#2A2A2A",
        "primary": "#FFFFFF",
        "onPrimary": "#000000",
        "positive": "#9FE3B0",
        "negative": "#FF6B6F",
        "warning": "#E5A93B",
        "focus": "#7CC4FF",
    },
    "light": {
        "ground": "#F5F5F4",
        "surface": "#FFFFFF",
        "raised": "#E9E9E7",
        "control": "#C9C9C6",
        "text": "#0B0B0B",
        "muted": "#4F4F4D",
        "faint": "#626260",
        "hue": "#1769B5",
        "track": "#E9E9E7",
        "primary": "#0B0B0B",
        "onPrimary": "#FFFFFF",
        "positive": "#1F7A45",
        "negative": "#C4242A",
        "warning": "#8A5200",
        "focus": "#1769B5",
    },
}
RADIUS = {"thumb": 10, "row": 16, "card": 14, "pill": 999}
SIZE: dict[str, object] = {
    "topBar": 48, "topBarPhone": 56, "rowHeight": 80, "countCard": 61,
    "thumbDesktop": (112, 63), "thumbPhone": (104, 59), "progress": 4,
    "control": 36, "controlPhone": 44, "minTarget": 44,
}
SPACE = {"gap": 8, "gutter": 24, "gutterPhone": 16, "pad": 16}
TYPE: dict[str, object] = {
    "family": "Hanken Grotesk", "weights": (400, 600, 700),
    "title": 20, "rowTitle": 15, "figure": 24, "body": 14, "meta": 13, "small": 12,
    "minimum": 12,
}
MOTION = {"fastMs": 120, "baseMs": 200}
FAMILY = "Hanken Grotesk"

_FONT_CLASSES = (
    "QAbstractItemView", "QTableView", "QListView", "QTreeView", "QListWidget", "QTableWidget",
    "QTipLabel", "QMessageBox", "QComboMenuItem", "QHeaderView", "QMenu", "QMenuBar", "QToolTip", "QStatusBar", "QLabel",
    "QPushButton", "QToolButton", "QCheckBox", "QRadioButton", "QComboBox", "QLineEdit",
    "QTextEdit", "QPlainTextEdit", "QAbstractSpinBox", "QTabBar", "QGroupBox", "QDialogButtonBox",
)
APPEARANCES = ("system", "night", "day")
_FONT_DIR = Path(__file__).resolve().parent / "fonts"
_FONT_FILES = ("HankenGrotesk-Regular.ttf", "HankenGrotesk-SemiBold.ttf", "HankenGrotesk-Bold.ttf")


@dataclass(frozen=True)
class Palette:
    """One theme: ``night`` (dark) or ``day`` (light)."""

    name: str
    tokens: Mapping[str, str]

    @property
    def dark(self) -> bool:
        return self.name == "night"

    def hex(self, key: str) -> str:
        return self.tokens[key]

    def color(self, key: str, alpha: float = 1.0) -> QColor:
        colour = QColor(self.tokens[key])
        if alpha < 1.0:
            colour.setAlphaF(max(0.0, alpha))
        return colour

    def blend(self, over: str, base: str, amount: float) -> QColor:
        """Token *over* laid on token *base* at opacity *amount* (opaque result)."""
        a, b = QColor(self.tokens[over]), QColor(self.tokens[base])
        mix = lambda x, y: round(y + (x - y) * amount)  # noqa: E731
        return QColor(mix(a.red(), b.red()), mix(a.green(), b.green()), mix(a.blue(), b.blue()))


NIGHT = Palette("night", TOKENS["dark"])
DAY = Palette("day", TOKENS["light"])


class _Notifier(QObject):
    changed = Signal()


_state: dict[str, object] = {
    "palette": NIGHT,
    "setting": "system",
    "reduce_motion": False,
    "icons": None,
    "notifier": None,
    "connected": False,
}


def notifier() -> _Notifier:
    """Emits ``changed`` whenever the palette or the reduce-motion switch changes."""
    if _state["notifier"] is None:
        _state["notifier"] = _Notifier()
    return _state["notifier"]  # type: ignore[return-value]


def current() -> Palette:
    return _state["palette"]  # type: ignore[return-value]


def reduce_motion_enabled() -> bool:
    return bool(_state["reduce_motion"])


def set_reduce_motion(on: bool) -> None:
    if bool(on) != _state["reduce_motion"]:
        _state["reduce_motion"] = bool(on)
        notifier().changed.emit()


def system_scheme() -> Qt.ColorScheme:
    app = QGuiApplication.instance()
    if app is None:
        return Qt.ColorScheme.Unknown
    try:
        return QGuiApplication.styleHints().colorScheme()
    except (AttributeError, RuntimeError):  # pragma: no cover - old Qt
        return Qt.ColorScheme.Unknown


def resolve_scheme(setting: str, system: Qt.ColorScheme | None = None) -> Palette:
    """Palette for *setting* (``system``, ``night`` or ``day``).

    ``system`` follows the OS: Light gives Day, anything else (Dark or
    Unknown, e.g. no portal) gives Night, the identity of the app.
    """
    if setting == "night":
        return NIGHT
    if setting == "day":
        return DAY
    if system is None:
        system = system_scheme()
    return DAY if system == Qt.ColorScheme.Light else NIGHT


# -- fonts -----------------------------------------------------------------
def load_fonts() -> bool:
    """Register the bundled Hanken Grotesk files; False if none could be loaded."""
    loaded = 0
    for name in _FONT_FILES:
        if QFontDatabase.addApplicationFont(str(_FONT_DIR / name)) >= 0:
            loaded += 1
    return loaded > 0


def _qt_palette(p: Palette) -> QPalette:
    qp = QPalette()
    role, group = QPalette.ColorRole, QPalette.ColorGroup
    mapping = {
        role.Window: "ground", role.WindowText: "text", role.Base: "surface",
        role.AlternateBase: "raised", role.Text: "text", role.Button: "raised",
        role.ButtonText: "text", role.BrightText: "text", role.Highlight: "primary",
        role.HighlightedText: "onPrimary", role.ToolTipBase: "raised", role.ToolTipText: "text",
        role.PlaceholderText: "faint", role.Link: "text", role.LinkVisited: "text",
        role.Light: "raised", role.Midlight: "raised", role.Mid: "control",
        role.Dark: "control", role.Shadow: "ground",
    }
    for r, key in mapping.items():
        qp.setColor(r, p.color(key))
    for r in (role.Text, role.WindowText, role.ButtonText):
        qp.setColor(group.Disabled, r, p.color("faint"))
    qp.setColor(group.Disabled, role.Button, p.color("surface"))
    qp.setColor(group.Disabled, role.Highlight, p.color("control"))
    qp.setColor(group.Disabled, role.HighlightedText, p.color("muted"))
    return qp


# -- generated images used by the stylesheet ------------------------------
def _image_dir() -> Path:
    holder = _state.get("icons")
    if holder is None:
        holder = tempfile.TemporaryDirectory(prefix="elisium-theme-")
        _state["icons"] = holder
    return Path(holder.name)  # type: ignore[attr-defined]


def _save(name: str, draw, size: int) -> str:
    """Render ``draw(painter, size)`` as ``name.png`` (+ a 2x copy); return its path."""
    folder = _image_dir()
    for scale, suffix in ((1, ""), (2, "@2x")):
        image = QImage(size * scale, size * scale, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(scale, scale)
        draw(painter, size)
        painter.end()
        image.save(str(folder / f"{name}{suffix}.png"))
    return (folder / f"{name}.png").as_posix()


def _make_images(p: Palette) -> dict[str, str]:
    """Check boxes and chevrons in the palette's colours."""
    out: dict[str, str] = {}
    tag = p.name

    def box(on: bool, focus: bool, disabled: bool):
        def draw(g: QPainter, s: int) -> None:
            inset = 1.0
            edge = p.color("control") if disabled else p.color("focus" if focus else "faint")
            fill = p.color("primary") if on and not disabled else p.color("surface")
            g.setBrush(fill)
            g.setPen(QPen(edge, 2 if focus else 1.4))
            g.drawRoundedRect(inset, inset, s - 2 * inset, s - 2 * inset, 5, 5)
            if on:
                path = QPainterPath()
                path.moveTo(s * 0.26, s * 0.52)
                path.lineTo(s * 0.43, s * 0.68)
                path.lineTo(s * 0.75, s * 0.32)
                g.setBrush(Qt.BrushStyle.NoBrush)
                pen = QPen(p.color("onPrimary" if not disabled else "faint"), 2.2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                g.setPen(pen)
                g.drawPath(path)
        return draw

    def chevron(up: bool, colour_key: str):
        def draw(g: QPainter, s: int) -> None:
            pen = QPen(p.color(colour_key), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            g.setPen(pen)
            path = QPainterPath()
            y1, y2 = (s * 0.62, s * 0.36) if up else (s * 0.38, s * 0.64)
            path.moveTo(s * 0.25, y1)
            path.lineTo(s * 0.5, y2)
            path.lineTo(s * 0.75, y1)
            g.drawPath(path)
        return draw

    for on in (False, True):
        for focus in (False, True):
            for disabled in (False, True):
                key = f"{'on' if on else 'off'}{'-focus' if focus else ''}{'-off' if disabled else ''}"
                out[f"box-{key}"] = _save(f"{tag}-box-{key}", box(on, focus, disabled), 20)
    out["chevron-down"] = _save(f"{tag}-chev-down", chevron(False, "muted"), 16)
    out["chevron-up"] = _save(f"{tag}-chev-up", chevron(True, "muted"), 16)
    return out


def _switch_image(p: Palette, on: bool, focus: bool, disabled: bool) -> str:
    """A 44 x 26 switch image: filled ``primary`` when on, an outline when off."""
    key = f"{'on' if on else 'off'}{'-focus' if focus else ''}{'-off' if disabled else ''}"
    folder = _image_dir()
    for scale, suffix in ((1, ""), (2, "@2x")):
        image = QImage(44 * scale, 26 * scale, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        g = QPainter(image)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        g.scale(scale, scale)
        inset = 2.0 if focus else 1.0
        w, h = 44.0, 26.0
        if disabled:
            track, edge, knob = p.color("surface"), p.color("control"), p.color("control")
        elif on:
            track, edge, knob = p.color("primary"), p.color("focus" if focus else "primary"), p.color("onPrimary")
        else:
            track, edge, knob = p.color("surface"), p.color("focus" if focus else "faint"), p.color("faint")
        g.setBrush(track)
        g.setPen(QPen(edge, 2 if focus else 1.4))
        radius = (h - 2 * inset) / 2
        g.drawRoundedRect(inset, inset, w - 2 * inset, h - 2 * inset, radius, radius)
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(knob)
        r = 6.0
        cx = (w - inset - 5 - r) if on else (inset + 5 + r)
        g.drawEllipse(cx - r, h / 2 - r, 2 * r, 2 * r)
        g.end()
        image.save(str(folder / f"{p.name}-switch-{key}{suffix}.png"))
    return (folder / f"{p.name}-switch-{key}.png").as_posix()


# -- stylesheet --------------------------------------------------------------
def build_stylesheet(p: Palette) -> str:
    """QSS for the whole application; colours come from *p* only."""
    c = p.hex
    imgs = _make_images(p)
    sw = {
        f"{'on' if on else 'off'}{'-focus' if focus else ''}{'-off' if dis else ''}":
        _switch_image(p, on, focus, dis)
        for on in (False, True) for focus in (False, True) for dis in (False, True)
    }
    pill = 18  # half of the 36 px control height
    row, card, thumb = RADIUS["row"], RADIUS["card"], RADIUS["thumb"]
    return f"""
QWidget {{ font-family: "{FAMILY}"; }}
QMainWindow, QDialog, QMessageBox {{ background: {c('ground')}; color: {c('text')}; }}
QLabel {{ background: transparent; color: {c('text')}; }}
QLabel#pageTitle {{ font-size: 1.43em; font-weight: 700; }}
QLabel#cardTitle {{ font-size: 1.07em; font-weight: 600; }}
QLabel[muted="true"] {{ color: {c('muted')}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QFrame[card="true"] {{ background: {c('surface')}; border: none; border-radius: {row}px; }}
QFrame[card="true"] QLabel {{ background: transparent; }}
QToolTip {{ background: {c('raised')}; color: {c('text')}; border: none; padding: 6px 8px;
    border-radius: {thumb}px; }}

QWidget#topBar {{ background: {c('ground')}; }}
QFrame#barRule {{ background: {c('raised')}; border: none; }}

QPushButton {{ background: {c('raised')}; color: {c('text')}; border: 2px solid transparent;
    border-radius: {pill}px; padding: 0 16px; min-height: 32px; font-weight: 600; }}
QPushButton:hover {{ background: {c('control')}; }}
QPushButton:pressed {{ background: {c('control')}; }}
QPushButton:disabled {{ background: {c('surface')}; color: {c('faint')}; }}
QPushButton:focus {{ border: 2px solid {c('focus')}; }}
QPushButton[primary="true"], QPushButton:default {{ background: {c('primary')}; color: {c('onPrimary')}; }}
QPushButton[primary="true"]:hover, QPushButton:default:hover {{ background: {c('muted')};
    color: {c('onPrimary')}; }}
QPushButton[primary="true"]:pressed, QPushButton:default:pressed {{ background: {c('muted')};
    color: {c('onPrimary')}; }}
QPushButton[primary="true"]:disabled, QPushButton:default:disabled {{ background: {c('raised')};
    color: {c('faint')}; }}
QPushButton[primary="true"]:focus, QPushButton:default:focus {{ border: 2px solid {c('focus')}; }}
QPushButton[quiet="true"], QPushButton:flat {{ background: transparent; color: {c('muted')}; padding: 0 8px; }}
QPushButton[quiet="true"]:hover, QPushButton:flat:hover {{ background: transparent; color: {c('text')}; }}
QPushButton[quiet="true"]:disabled, QPushButton:flat:disabled {{ background: transparent; color: {c('faint')}; }}
QPushButton[quiet="true"]:focus, QPushButton:flat:focus {{ border: 2px solid {c('focus')}; }}
QPushButton#downloadButton {{ min-height: 32px; padding: 0 20px; }}

QToolButton {{ background: transparent; color: {c('text')}; border: 2px solid transparent;
    border-radius: {thumb}px; padding: 4px 10px; font-weight: 600; }}
QToolButton:hover {{ background: {c('raised')}; }}
QToolButton:disabled {{ color: {c('faint')}; }}
QToolButton:focus {{ border: 2px solid {c('focus')}; }}
QToolButton#cardAction[role="icon"] {{ background: {c('raised')}; color: {c('text')}; border: 2px solid transparent;
    border-radius: {card}px; padding: 0; }}
QToolButton#cardAction[role="icon"]:hover {{ background: {c('control')}; }}
QToolButton#cardAction[role="icon"]:focus {{ border: 2px solid {c('focus')}; padding: 0; }}
QToolButton#cardAction[role="link"] {{ background: transparent; color: {c('text')}; border: 2px solid transparent;
    border-radius: 6px; padding: 0 2px; font-size: 0.86em; font-weight: 600; }}
QToolButton#cardAction[role="link"]:hover {{ background: transparent; color: {c('muted')}; }}
QToolButton#cardAction[role="link"]:focus {{ border: 2px solid {c('focus')}; }}
QToolButton#cardAction[role="pill"] {{ background: {c('primary')}; color: {c('onPrimary')}; border: 2px solid transparent;
    border-radius: 14px; padding: 0 14px; font-size: 0.93em; font-weight: 600; }}
QToolButton#cardAction[role="pill"]:hover {{ background: {c('muted')}; color: {c('onPrimary')}; }}
QToolButton#cardAction[role="pill"]:focus {{ border: 2px solid {c('focus')}; }}
QToolBar {{ background: transparent; border: none; spacing: 4px; padding: 4px 0; }}
QToolBar QToolButton {{ background: transparent; color: {c('muted')}; border: 2px solid transparent;
    border-radius: {pill}px; padding: 0 12px; min-height: 32px; font-size: 0.93em; }}
QToolBar QToolButton:hover {{ background: {c('raised')}; color: {c('text')}; }}
QToolBar QToolButton:disabled {{ background: transparent; color: {c('faint')}; }}
QToolBar QToolButton:focus {{ border: 2px solid {c('focus')}; }}

QLineEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox {{ background: {c('raised')}; color: {c('text')};
    border: 2px solid transparent; border-radius: {thumb}px; padding: 0 12px;
    selection-background-color: {c('primary')}; selection-color: {c('onPrimary')}; }}
QLineEdit, QAbstractSpinBox, QComboBox {{ min-height: 32px; }}
QLineEdit#linkField {{ background: {c('surface')}; border-radius: {pill}px; padding: 0 16px;
    min-height: 32px; }}
QPlainTextEdit {{ padding: 8px 12px; }}
QLineEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {{
    border: 2px solid {c('focus')}; }}
QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {{ background: {c('surface')};
    color: {c('faint')}; }}
QComboBox::drop-down {{ border: none; width: 34px; }}
QComboBox::down-arrow {{ image: url({imgs['chevron-down']}); width: 16px; height: 16px; }}
QComboBox QAbstractItemView {{ background: {c('raised')}; color: {c('text')};
    border: none; border-radius: {thumb}px; padding: 4px;
    selection-background-color: {c('control')}; selection-color: {c('text')}; outline: none; }}
QAbstractSpinBox QLineEdit {{ background: transparent; border: none; padding: 0 0 0 6px; min-height: 0;
    selection-background-color: {c('primary')}; selection-color: {c('onPrimary')}; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 26px; border: none;
    background: transparent; }}
QAbstractSpinBox::up-arrow {{ image: url({imgs['chevron-up']}); width: 14px; height: 14px; }}
QAbstractSpinBox::down-arrow {{ image: url({imgs['chevron-down']}); width: 14px; height: 14px; }}

QCheckBox {{ color: {c('text')}; spacing: 12px; background: transparent; }}
QCheckBox:disabled {{ color: {c('faint')}; }}
QCheckBox::indicator {{ width: 44px; height: 26px; }}
QCheckBox::indicator:unchecked {{ image: url({sw['off']}); }}
QCheckBox::indicator:unchecked:focus {{ image: url({sw['off-focus']}); }}
QCheckBox::indicator:unchecked:disabled {{ image: url({sw['off-off']}); }}
QCheckBox::indicator:checked {{ image: url({sw['on']}); }}
QCheckBox::indicator:checked:focus {{ image: url({sw['on-focus']}); }}
QCheckBox::indicator:checked:disabled {{ image: url({sw['on-off']}); }}
QRadioButton {{ color: {c('text')}; spacing: 10px; background: transparent; }}
QRadioButton:disabled {{ color: {c('faint')}; }}

QListView::indicator, QTableView::indicator {{ width: 20px; height: 20px; }}
QListView::indicator:unchecked, QTableView::indicator:unchecked {{ image: url({imgs['box-off']}); }}
QListView::indicator:unchecked:disabled {{ image: url({imgs['box-off-off']}); }}
QListView::indicator:checked, QTableView::indicator:checked {{ image: url({imgs['box-on']}); }}
QListView::indicator:checked:disabled {{ image: url({imgs['box-on-off']}); }}

QListView, QListWidget, QTableView, QTreeView {{ background: {c('surface')}; color: {c('text')};
    border: none; border-radius: {thumb}px; outline: none;
    selection-background-color: {c('primary')}; selection-color: {c('onPrimary')};
    alternate-background-color: {c('raised')}; gridline-color: {c('raised')}; }}
QTableView:focus, QTreeView:focus, QListWidget#entries:focus {{ border: 2px solid {c('focus')}; }}
QListView:disabled, QListWidget:disabled, QTableView:disabled {{ color: {c('faint')}; }}
QListWidget::item {{ padding: 10px 12px; border-radius: {thumb}px; margin: 2px 4px;
    border: 2px solid transparent; }}
QListWidget::item:selected {{ background: {c('primary')}; color: {c('onPrimary')}; }}
QListWidget::item:selected:focus {{ border: 2px solid {c('focus')}; }}
QListWidget::item:hover {{ background: {c('raised')}; }}
QListWidget::item:selected:hover {{ background: {c('primary')}; color: {c('onPrimary')}; }}
QListWidget::item:disabled {{ color: {c('faint')}; }}
QTableView::item {{ padding: 4px 8px; }}
QTableView::item:selected {{ background: {c('primary')}; color: {c('onPrimary')}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {c('raised')}; color: {c('muted')}; border: none;
    padding: 6px 10px; font-weight: 600; }}
QTableCornerButton::section {{ background: {c('raised')}; border: none; }}

QListWidget#nav, QListWidget#nav:focus, QListWidget#nav:hover {{ background: transparent;
    border: none; border-radius: 0; padding: 0; margin: 0; }}
QListWidget#nav::item {{ padding: 0 6px; margin: 0 3px; border-radius: 8px; background: transparent;
    color: {c('faint')}; font-weight: 600; border: 2px solid transparent; }}
QListWidget#nav::item:hover {{ background: transparent; color: {c('muted')}; }}
QListWidget#nav::item:selected, QListWidget#nav::item:selected:hover {{ background: transparent;
    color: {c('text')}; }}
QListWidget#nav::item:selected:focus {{ border: 2px solid {c('focus')}; }}

QTableView#cards, QTableView#cards:focus {{ background: transparent; border: none; border-radius: 0;
    selection-background-color: transparent; alternate-background-color: transparent; }}
QTableView#cards::item, QTableView#cards::item:selected, QTableView#cards::item:hover {{
    background: transparent; border: none; padding: 0; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c('control')}; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:horizontal {{ background: {c('control')}; border-radius: 4px; min-width: 36px; }}
QScrollBar::handle:hover {{ background: {c('faint')}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; background: none; border: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {c('raised')}; color: {c('text')}; border: none;
    border-radius: {thumb}px; padding: 6px; }}
QMenu::item {{ padding: 9px 22px 9px 16px; border-radius: 8px; background: transparent; }}
QMenu::item:selected {{ background: {c('control')}; color: {c('text')}; }}
QMenu::item:disabled {{ color: {c('faint')}; background: transparent; }}
QMenu::separator {{ height: 1px; background: {c('control')}; margin: 6px 8px; }}

QProgressBar {{ background: {c('track')}; color: {c('text')}; border: none; border-radius: 2px;
    min-height: 4px; max-height: 4px; text-align: center; }}
QProgressBar::chunk {{ border-radius: 2px; background: {c('hue')}; }}

QStatusBar {{ background: transparent; color: {c('muted')}; font-size: 0.93em; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {c('muted')}; }}
QDialogButtonBox {{ background: transparent; }}
"""


def apply(app: QApplication, setting: str = "system") -> Palette:
    """Style the whole application and return the palette now in force.

    Sets the Qt palette (so natively drawn parts and disabled states match),
    the stylesheet and the bundled Hanken Grotesk font (the system font if it
    cannot be loaded). With ``system`` it follows the OS light/dark switch live.
    """
    if setting not in APPEARANCES:
        setting = "system"
    _state["setting"] = setting
    if not _state["connected"]:
        _state["connected"] = True
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(_on_system_scheme)
        except (AttributeError, RuntimeError):  # pragma: no cover
            pass
    # Wrapping the style resets the application font and palette, so do it first.
    from .main_window import install_accessible_style  # local: avoids an import cycle

    install_accessible_style()
    if "font_done" not in _state:
        _state["font_done"] = True
        if load_fonts():
            size = app.font().pointSizeF()
            _state["font_size"] = max(size if size > 0 else 0.0, 11.0)
            # Qt fills the per-class font table from the platform theme when the
            # first widget is made; make that happen now so ours is not undone.
            probe = QWidget()
            QApplication.font(probe)
            probe.deleteLater()
            _set_family(app)
            # The platform theme puts its own font back when the first window is
            # shown; take Hanken Grotesk back whenever that happens.
            app.fontChanged.connect(_on_font_changed)
    p = resolve_scheme(setting)
    _state["palette"] = p
    # The stylesheet first: setting it makes Qt re-read the platform theme palette.
    app.setStyleSheet(build_stylesheet(p))
    app.setPalette(_qt_palette(p))
    notifier().changed.emit()
    return p


def _set_family(app: QApplication) -> None:
    font = QFont(FAMILY)
    font.setPointSizeF(float(_state["font_size"]))  # type: ignore[arg-type]
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    # Platform themes (qt6ct, GTK, offscreen) give item views, menus and
    # tooltips a font of their own; make those Hanken Grotesk too.
    for cls in _FONT_CLASSES:
        app.setFont(font, cls)


def set_base_size(app: QApplication, points: float) -> None:
    """Change the base text size (pt) of the app font (used for large-text screenshots)."""
    _state["font_size"] = float(points)
    if "font_done" in _state and "font_size" in _state:
        _set_family(app)


_reapplying = False


def _on_font_changed(font: QFont) -> None:
    global _reapplying
    if _reapplying or font.family() == FAMILY:
        return
    app = QApplication.instance()
    if app is None:
        return
    _reapplying = True
    try:
        _set_family(app)  # type: ignore[arg-type]
    finally:
        _reapplying = False


def _on_system_scheme(*_args: object) -> None:
    if _state["setting"] == "system":
        app = QApplication.instance()
        if app is not None:
            apply(app, "system")  # type: ignore[arg-type]


def reset(app: QApplication) -> None:
    """Undo ``apply`` (used by tests so styling does not leak between them)."""
    app.setStyleSheet("")
    app.setPalette(QPalette())
    _state["palette"] = NIGHT
    _state["reduce_motion"] = False
    _state["setting"] = "system"
