"""The "Afterglow" theme: tokens, palettes, the application stylesheet and Inter.

This is the ONLY module that contains colour values. Everything else asks a
``Palette`` for a token by name (``palette.color("accent")``). The values below
are copied from ``design/tokens.json`` by hand (the file cannot be read at run
time: it is not packaged); ``tests/test_theme.py`` asserts they are equal, so
drift fails the test.
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
    "MOTION",
    "NIGHT",
    "Palette",
    "RADIUS",
    "SPACE",
    "TOKENS",
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
        "bg": "#0E0A1A",
        "surface": "#171126",
        "raised": "#211836",
        "outline": "#3B2E5C",
        "text": "#F4EFFF",
        "muted": "#B9ACD9",
        "accent": "#C4A1FF",
        "onAccent": "#1A0F33",
        "glowA": "#B388FF",
        "glowB": "#FF8FB8",
        "glowC": "#FFC47E",
        "success": "#7DE3B2",
        "error": "#FF8E9B",
        "warning": "#FFC47E",
        "outlineStrong": "#8472B5",
    },
    "light": {
        "bg": "#FBF8FF",
        "surface": "#FFFFFF",
        "raised": "#F1EAFE",
        "outline": "#CBBDEA",
        "text": "#1B1330",
        "muted": "#5B4D7C",
        "accent": "#6B3FD4",
        "onAccent": "#FFFFFF",
        "glowA": "#7C4DFF",
        "glowB": "#E0457B",
        "glowC": "#B3650A",
        "success": "#0B7A4B",
        "error": "#B3261E",
        "warning": "#8A5200",
        "outlineStrong": "#7A69A8",
    },
}
RADIUS = {"small": 10, "medium": 16, "large": 24}
SPACE = (4, 8, 12, 16, 24, 32)
MOTION = {"fastMs": 120, "baseMs": 220, "slowMs": 420}

_FONT_CLASSES = (
    "QAbstractItemView", "QTableView", "QListView", "QTreeView", "QListWidget", "QTableWidget",
    "QTipLabel", "QMessageBox", "QComboMenuItem", "QHeaderView", "QMenu", "QMenuBar", "QToolTip", "QStatusBar", "QLabel",
    "QPushButton", "QToolButton", "QCheckBox", "QRadioButton", "QComboBox", "QLineEdit",
    "QTextEdit", "QPlainTextEdit", "QAbstractSpinBox", "QTabBar", "QGroupBox", "QDialogButtonBox",
)
APPEARANCES = ("system", "night", "day")
_FONT_DIR = Path(__file__).resolve().parent / "fonts"


@dataclass(frozen=True)
class Palette:
    """One theme: ``night`` (Nightfall, dark) or ``day`` (Daybreak, light)."""

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

    def glow_stops(self) -> tuple[QColor, QColor, QColor]:
        return self.color("glowA"), self.color("glowB"), self.color("glowC")


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

    ``system`` follows the OS: Light gives Daybreak, anything else (Dark or
    Unknown, e.g. no portal) gives Nightfall, the identity of the app.
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
    """Register the bundled Inter files; False if none could be loaded."""
    loaded = 0
    for path in sorted(_FONT_DIR.glob("Inter-*.ttf")):
        if QFontDatabase.addApplicationFont(str(path)) >= 0:
            loaded += 1
    return loaded > 0


def _qt_palette(p: Palette) -> QPalette:
    qp = QPalette()
    role, group = QPalette.ColorRole, QPalette.ColorGroup
    mapping = {
        role.Window: "bg", role.WindowText: "text", role.Base: "surface",
        role.AlternateBase: "raised", role.Text: "text", role.Button: "raised",
        role.ButtonText: "text", role.BrightText: "text", role.Highlight: "accent",
        role.HighlightedText: "onAccent", role.ToolTipBase: "raised", role.ToolTipText: "text",
        role.PlaceholderText: "muted", role.Link: "accent", role.LinkVisited: "accent",
        role.Light: "raised", role.Midlight: "raised", role.Mid: "outline",
        role.Dark: "outline", role.Shadow: "bg",
    }
    for r, key in mapping.items():
        qp.setColor(r, p.color(key))
    for r in (role.Text, role.WindowText, role.ButtonText):
        qp.setColor(group.Disabled, r, p.color("muted"))
    qp.setColor(group.Disabled, role.Button, p.color("surface"))
    qp.setColor(group.Disabled, role.Highlight, p.color("outline"))
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
            edge = p.color("outline") if disabled else p.color("accent" if (focus or on) else "outlineStrong")
            fill = p.color("accent") if on and not disabled else p.color("surface")
            g.setBrush(fill)
            g.setPen(QPen(edge, 2 if focus else 1.4))
            g.drawRoundedRect(inset, inset, s - 2 * inset, s - 2 * inset, 5, 5)
            if on:
                path = QPainterPath()
                path.moveTo(s * 0.26, s * 0.52)
                path.lineTo(s * 0.43, s * 0.68)
                path.lineTo(s * 0.75, s * 0.32)
                g.setBrush(Qt.BrushStyle.NoBrush)
                pen = QPen(p.color("onAccent" if not disabled else "muted"), 2.2)
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
    """A 44 x 26 switch image (separate from the square helpers above)."""
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
        track = p.color("outline") if disabled else p.color("accent") if on else p.color("raised")
        edge = p.color("outline") if disabled else p.color("accent" if focus else "outlineStrong")
        g.setBrush(track)
        g.setPen(QPen(edge, 2 if focus else 1.4))
        radius = (h - 2 * inset) / 2
        g.drawRoundedRect(inset, inset, w - 2 * inset, h - 2 * inset, radius, radius)
        knob = p.color("onAccent") if (on and not disabled) else p.color("muted" if disabled else "text")
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
    r = RADIUS
    imgs = _make_images(p)
    sw = {
        f"{'on' if on else 'off'}{'-focus' if focus else ''}{'-off' if dis else ''}":
        _switch_image(p, on, focus, dis)
        for on in (False, True) for focus in (False, True) for dis in (False, True)
    }
    glow = (
        f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c('glowA')}, "
        f"stop:0.55 {c('glowB')}, stop:1 {c('glowC')})"
    )
    return f"""
QWidget {{ font-family: "Inter"; }}
QMainWindow, QDialog, QMessageBox {{ background: {c('bg')}; color: {c('text')}; }}
QLabel {{ background: transparent; color: {c('text')}; }}
QLabel#pageTitle {{ font-size: 28px; font-weight: 800; letter-spacing: -0.5px; }}
QLabel#cardTitle {{ font-size: 18px; font-weight: 700; }}
QLabel[muted="true"] {{ color: {c('muted')}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QFrame[card="true"] {{ background: {c('raised')}; border: 1px solid {c('outline')};
    border-radius: {r['medium']}px; }}
QFrame[card="true"] QLabel {{ background: transparent; }}
QToolTip {{ background: {c('raised')}; color: {c('text')}; border: 1px solid {c('outlineStrong')};
    padding: 6px 8px; border-radius: {r['small']}px; }}

QPushButton {{ background: {c('raised')}; color: {c('text')}; border: 1px solid {c('outlineStrong')};
    border-radius: {r['small']}px; padding: 0 18px; min-height: 42px; font-weight: 600; }}
QPushButton:hover {{ background: {c('outline')}; }}
QPushButton:pressed {{ background: {c('outline')}; border-color: {c('accent')}; }}
QPushButton:disabled {{ background: {c('surface')}; color: {c('muted')}; border-color: {c('outline')}; }}
QPushButton:focus {{ border: 2px solid {c('accent')}; padding: 0 17px; }}
QPushButton[primary="true"], QPushButton:default {{ background: {c('accent')}; color: {c('onAccent')};
    border: 1px solid {c('accent')}; }}
QPushButton[primary="true"]:hover, QPushButton:default:hover {{ background: {c('glowA')};
    color: {c('onAccent')}; }}
QPushButton[primary="true"]:disabled, QPushButton:default:disabled {{ background: {c('surface')};
    color: {c('muted')}; border-color: {c('outline')}; }}
QPushButton[primary="true"]:focus, QPushButton:default:focus {{ border: 2px solid {c('text')};
    padding: 0 17px; }}

QToolButton {{ background: transparent; color: {c('accent')}; border: 1px solid transparent;
    border-radius: {r['small']}px; padding: 6px 10px; font-weight: 600; }}
QToolButton:hover {{ background: {c('raised')}; }}
QToolButton:disabled {{ color: {c('muted')}; }}
QToolButton:focus {{ border: 2px solid {c('accent')}; padding: 5px 9px; }}
QToolButton#cardAction {{ background: {c('surface')}; color: {c('text')}; border: 1px solid {c('outline')};
    border-radius: {r['small']}px; padding: 0; }}
QToolButton#cardAction:hover {{ background: {c('outline')}; }}
QToolButton#cardAction:focus {{ border: 2px solid {c('accent')}; padding: 0; }}
QToolBar {{ background: transparent; border: none; spacing: 8px; padding: 4px 0; }}
QToolBar QToolButton {{ background: {c('raised')}; color: {c('text')}; border: 1px solid {c('outline')};
    border-radius: {r['small']}px; padding: 0 14px; min-height: 40px; }}
QToolBar QToolButton:hover {{ background: {c('outline')}; }}
QToolBar QToolButton:disabled {{ background: {c('surface')}; color: {c('muted')}; }}
QToolBar QToolButton:focus {{ border: 2px solid {c('accent')}; padding: 0 13px; }}

QLineEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox {{ background: {c('surface')}; color: {c('text')};
    border: 1px solid {c('outlineStrong')}; border-radius: {r['small']}px; padding: 0 12px;
    selection-background-color: {c('accent')}; selection-color: {c('onAccent')}; }}
QLineEdit, QAbstractSpinBox, QComboBox {{ min-height: 42px; }}
QPlainTextEdit {{ padding: 8px 12px; }}
QLineEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {{
    border: 2px solid {c('accent')}; padding: 0 11px; }}
QPlainTextEdit:focus {{ padding: 7px 11px; }}
QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {{ background: {c('surface')};
    color: {c('muted')}; border-color: {c('outline')}; }}
QComboBox::drop-down {{ border: none; width: 34px; }}
QComboBox::down-arrow {{ image: url({imgs['chevron-down']}); width: 16px; height: 16px; }}
QComboBox QAbstractItemView {{ background: {c('raised')}; color: {c('text')};
    border: 1px solid {c('outlineStrong')}; border-radius: {r['small']}px; padding: 4px;
    selection-background-color: {c('accent')}; selection-color: {c('onAccent')}; outline: none; }}
QAbstractSpinBox QLineEdit {{ background: transparent; border: none; padding: 0 0 0 6px; min-height: 0;
    selection-background-color: {c('accent')}; selection-color: {c('onAccent')}; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 26px; border: none;
    background: transparent; }}
QAbstractSpinBox::up-arrow {{ image: url({imgs['chevron-up']}); width: 14px; height: 14px; }}
QAbstractSpinBox::down-arrow {{ image: url({imgs['chevron-down']}); width: 14px; height: 14px; }}

QCheckBox {{ color: {c('text')}; spacing: 12px; background: transparent; }}
QCheckBox:disabled {{ color: {c('muted')}; }}
QCheckBox::indicator {{ width: 44px; height: 26px; }}
QCheckBox::indicator:unchecked {{ image: url({sw['off']}); }}
QCheckBox::indicator:unchecked:focus {{ image: url({sw['off-focus']}); }}
QCheckBox::indicator:unchecked:disabled {{ image: url({sw['off-off']}); }}
QCheckBox::indicator:checked {{ image: url({sw['on']}); }}
QCheckBox::indicator:checked:focus {{ image: url({sw['on-focus']}); }}
QCheckBox::indicator:checked:disabled {{ image: url({sw['on-off']}); }}
QRadioButton {{ color: {c('text')}; spacing: 10px; background: transparent; }}
QRadioButton:disabled {{ color: {c('muted')}; }}

QListView::indicator, QTableView::indicator {{ width: 20px; height: 20px; }}
QListView::indicator:unchecked, QTableView::indicator:unchecked {{ image: url({imgs['box-off']}); }}
QListView::indicator:unchecked:disabled {{ image: url({imgs['box-off-off']}); }}
QListView::indicator:checked, QTableView::indicator:checked {{ image: url({imgs['box-on']}); }}
QListView::indicator:checked:disabled {{ image: url({imgs['box-on-off']}); }}

QListView, QListWidget, QTableView, QTreeView {{ background: {c('surface')}; color: {c('text')};
    border: 1px solid {c('outline')}; border-radius: {r['small']}px; outline: none;
    selection-background-color: {c('accent')}; selection-color: {c('onAccent')};
    alternate-background-color: {c('raised')}; gridline-color: {c('outline')}; }}
QTableView:focus, QTreeView:focus, QListWidget#entries:focus {{ border: 2px solid {c('accent')}; }}
QListView:disabled, QListWidget:disabled, QTableView:disabled {{ color: {c('muted')}; }}
QListWidget::item {{ padding: 10px 12px; border-radius: {r['small']}px; margin: 2px 4px;
    border: 1px solid transparent; }}
QListWidget::item:selected {{ background: {c('raised')}; color: {c('text')};
    border: 1px solid {c('accent')}; }}
QListWidget::item:hover {{ background: {c('raised')}; }}
QListWidget::item:disabled {{ color: {c('muted')}; }}
QTableView::item {{ padding: 4px 8px; }}
QTableView::item:selected {{ background: {c('accent')}; color: {c('onAccent')}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {c('raised')}; color: {c('muted')}; border: none;
    border-bottom: 1px solid {c('outline')}; padding: 6px 10px; font-weight: 600; }}
QTableCornerButton::section {{ background: {c('raised')}; border: none; }}

QListWidget#sidebar, QListWidget#sidebar:focus, QListWidget#sidebar:hover {{ background: transparent;
    border: 0px solid transparent; border-radius: 0; padding: 4px 0; }}
QListWidget#sidebar::item {{ padding: 12px 16px; margin: 3px 0; border-radius: {r['small'] + 2}px;
    color: {c('muted')}; font-weight: 600; border: 1px solid transparent; }}
QListWidget#sidebar::item:hover {{ background: {c('surface')}; color: {c('text')}; }}
QListWidget#sidebar::item:selected {{ background: {c('raised')}; color: {c('accent')};
    border: 1px solid {c('outline')}; }}
QListWidget#sidebar::item:selected:focus {{ border: 2px solid {c('accent')}; padding: 11px 15px; }}

QTableView#cards, QTableView#cards:focus {{ background: transparent; border: none; border-radius: 0;
    selection-background-color: transparent; alternate-background-color: transparent; }}
QTableView#cards::item, QTableView#cards::item:selected, QTableView#cards::item:hover {{
    background: transparent; border: none; padding: 0; }}

QScrollBar:vertical {{ background: transparent; width: 14px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 14px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c('outlineStrong')}; border-radius: 5px; min-height: 36px; }}
QScrollBar::handle:horizontal {{ background: {c('outlineStrong')}; border-radius: 5px; min-width: 36px; }}
QScrollBar::handle:hover {{ background: {c('accent')}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; background: none; border: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {c('raised')}; color: {c('text')}; border: 1px solid {c('outlineStrong')};
    border-radius: {r['small']}px; padding: 6px; }}
QMenu::item {{ padding: 9px 22px 9px 16px; border-radius: 8px; background: transparent; }}
QMenu::item:selected {{ background: {c('accent')}; color: {c('onAccent')}; }}
QMenu::item:disabled {{ color: {c('muted')}; background: transparent; }}
QMenu::separator {{ height: 1px; background: {c('outline')}; margin: 6px 8px; }}

QProgressBar {{ background: {c('outline')}; color: {c('text')}; border: none; border-radius: 6px;
    min-height: 12px; max-height: 12px; text-align: center; }}
QProgressBar::chunk {{ border-radius: 6px; background: {glow}; }}

QStatusBar {{ background: transparent; color: {c('muted')}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {c('muted')}; }}
QDialogButtonBox {{ background: transparent; }}
"""


def apply(app: QApplication, setting: str = "system") -> Palette:
    """Style the whole application and return the palette now in force.

    Sets the Qt palette (so natively drawn parts and disabled states match),
    the stylesheet and the bundled Inter font (the system font if Inter cannot
    be loaded). With ``system`` it follows the OS light/dark switch live.
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
            _set_inter(app)
            # The platform theme puts its own font back when the first window is
            # shown; take Inter back whenever that happens.
            app.fontChanged.connect(_on_font_changed)
    p = resolve_scheme(setting)
    _state["palette"] = p
    # The stylesheet first: setting it makes Qt re-read the platform theme palette.
    app.setStyleSheet(build_stylesheet(p))
    app.setPalette(_qt_palette(p))
    notifier().changed.emit()
    return p


def _set_inter(app: QApplication) -> None:
    font = QFont("Inter")
    font.setPointSizeF(float(_state["font_size"]))  # type: ignore[arg-type]
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    # Platform themes (qt6ct, GTK, offscreen) give item views, menus and
    # tooltips a font of their own; make those Inter too.
    for cls in _FONT_CLASSES:
        app.setFont(font, cls)


def set_base_size(app: QApplication, points: float) -> None:
    """Change the base text size (pt) of the Inter font (used for large-text screenshots)."""
    _state["font_size"] = float(points)
    if "font_done" in _state and "font_size" in _state:
        _set_inter(app)


_reapplying = False


def _on_font_changed(font: QFont) -> None:
    global _reapplying
    if _reapplying or font.family() == "Inter":
        return
    app = QApplication.instance()
    if app is None:
        return
    _reapplying = True
    try:
        _set_inter(app)  # type: ignore[arg-type]
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
