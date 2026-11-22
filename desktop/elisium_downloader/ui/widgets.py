"""Night shelf widgets: the mark, count cards, the download row, the empty state, icons.

No colour literals here: every colour is a token fetched from ``theme.current()``.
Nothing is drawn with a gradient, a glow or a shadow; rows are lifted by lightness only.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QModelIndex,
    QObject,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontInfo,
    QFontMetrics,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QRadioButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from . import theme
from .model import FILTER_LABELS, FILTERS, DownloadModel, RowText, describe_row, site_name
from .thumbnail import ThumbnailCache, row_placeholder

__all__ = [
    "BrandMark",
    "CountCard",
    "CountCards",
    "EmptyState",
    "EnterAnimation",
    "HistoryDelegate",
    "ProgressEase",
    "QueueDelegate",
    "RowGeometry",
    "RowHeightKeeper",
    "action_icon",
    "app_icon",
    "chip_colours",
    "contrast_ratio",
    "legible_colour",
    "draw_mark",
    "enter_animation",
    "paint_bar",
    "progress_ease",
]

_RUNNING = ("downloading", "merging", "converting")
# History chips: the state word is always written; this only picks its text colour.
_CHIP_KEY = {
    "queued": "faint", "probing": "faint", "downloading": "text", "merging": "text",
    "converting": "text", "paused": "warning", "done": "positive", "failed": "negative",
    "skipped": "faint", "cancelled": "faint",
}


def _luminance(c: QColor) -> float:
    def ch(v: int) -> float:
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


def contrast_ratio(a: QColor, b: QColor) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def legible_colour(p: theme.Palette, key: str, ground: str) -> QColor:
    """Token *key* for text on token *ground*; plain ``text`` when the pair is under 4.5:1.

    Only one pair needs the fallback (``positive`` on the day ``raised`` of a selected row).
    """
    colour = p.color(key)
    return colour if contrast_ratio(colour, p.color(ground)) >= 4.5 else p.color("text")


def chip_colours(state: str, p: theme.Palette | None = None) -> tuple[QColor, QColor]:
    """``(background, text)`` of a History state chip: coloured words on a ``ground`` pill."""
    p = p or theme.current()
    return p.color("ground"), p.color(_CHIP_KEY.get(state, "faint"))


def _motion_off() -> bool:
    from .quality_dialog import reduce_motion  # local: avoids an import cycle

    return reduce_motion()


# -- motion: one shared driver each, no loops --------------------------------------
class EnterAnimation(QVariantAnimation):
    """ONE shared driver for the row enter animation (fade + 6 px rise, 200 ms ease-out).

    Rows register by item id; each keeps its own start time, so rows added in quick
    succession do not restart each other and no row owns a timer. Nothing is
    registered (every row is simply drawn) when motion is reduced.
    """

    DURATION_MS = theme.MOTION["baseMs"]
    RISE_PX = 6.0

    def __init__(self) -> None:
        super().__init__()
        self.setStartValue(0.0)
        self.setEndValue(1.0)
        self.setDuration(self.DURATION_MS + 40)
        self.setEasingCurve(QEasingCurve.Type.Linear)
        self._starts: dict[int, float] = {}
        self.finished.connect(self._starts.clear)

    def add(self, item_id: int) -> bool:
        """Start the enter animation for a new row; False when motion is off."""
        if _motion_off():
            return False
        self._starts[item_id] = time.monotonic()
        if self.state() != QVariantAnimation.State.Running:
            self.start()
        return True

    @property
    def active(self) -> bool:
        return bool(self._starts)

    def progress(self, item_id: int) -> float:
        """0..1 with ease-out; 1.0 for a row that is not entering."""
        start = self._starts.get(item_id)
        if start is None or _motion_off():
            return 1.0
        t = (time.monotonic() - start) * 1000.0 / self.DURATION_MS
        if t >= 1.0:
            self._starts.pop(item_id, None)
            return 1.0
        return 1.0 - (1.0 - max(t, 0.0)) ** 3


_enter: EnterAnimation | None = None


def enter_animation() -> EnterAnimation:
    global _enter
    if _enter is None:
        _enter = EnterAnimation()
    return _enter


class ProgressEase(QVariantAnimation):
    """Eases each row's bar to its new percent (200 ms ease-out) instead of jumping.

    ``value(item_id, target)`` is what to draw now. The animation only ticks (so the
    view repaints) while some bar is still moving; it never loops. With reduced
    motion the target is returned unchanged.
    """

    DURATION_MS = theme.MOTION["baseMs"]

    def __init__(self) -> None:
        super().__init__()
        self.setStartValue(0.0)
        self.setEndValue(1.0)
        self.setDuration(self.DURATION_MS + 40)
        self.setEasingCurve(QEasingCurve.Type.Linear)
        # item id -> (from, to, started at)
        self._moves: dict[int, tuple[float, float, float]] = {}
        self._shown: dict[int, float] = {}
        self.finished.connect(self._moves.clear)

    def value_for(self, item_id: int, target: float) -> float:
        if _motion_off():
            self._shown[item_id] = target
            self._moves.pop(item_id, None)
            return target
        shown = self._shown.get(item_id)
        if shown is None:
            self._shown[item_id] = target
            return target
        move = self._moves.get(item_id)
        if move is not None and move[1] == target:
            start, end, began = move
        else:
            if abs(target - shown) < 0.05:
                self._shown[item_id] = target
                return target
            start, end, began = shown, target, time.monotonic()
            self._moves[item_id] = (start, end, began)
            if self.state() != QVariantAnimation.State.Running:
                self.start()
        t = (time.monotonic() - began) * 1000.0 / self.DURATION_MS
        if t >= 1.0:
            self._moves.pop(item_id, None)
            self._shown[item_id] = end
            return end
        eased = start + (end - start) * (1.0 - (1.0 - max(t, 0.0)) ** 3)
        self._shown[item_id] = eased
        return eased

    @property
    def active(self) -> bool:
        return bool(self._moves)


_ease: ProgressEase | None = None


def progress_ease() -> ProgressEase:
    global _ease
    if _ease is None:
        _ease = ProgressEase()
    return _ease


# -- the mark and icons -----------------------------------------------------------
def draw_mark(painter: QPainter, rect: QRectF, p: theme.Palette | None = None,
              ink: str = "text") -> None:
    """The mark: three stacked rounded bars getting shorter (a queue), the last in ``hue``.

    Same geometry as ``packaging/elisium.svg`` (a 22 x 22 box scaled to *rect*).
    """
    p = p or theme.current()
    s = min(rect.width(), rect.height()) / 22.0
    painter.save()
    painter.translate(rect.center().x() - 11.0 * s, rect.center().y() - 11.0 * s)
    painter.scale(s, s)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    for (x, y, w, h), colour in (
        ((2, 3, 18, 4), p.color(ink, 0.35)),
        ((2, 9, 13, 4), p.color(ink, 0.6)),
        ((2, 15, 8, 4), p.color("hue")),
    ):
        painter.setBrush(colour)
        painter.drawRoundedRect(QRectF(x, y, w, h), 2, 2)
    painter.restore()


def app_icon() -> QIcon:
    """The launcher and tray icon: the mark on a black rounded square (night palette)."""
    p = theme.NIGHT
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        g = QPainter(image)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, size, size)
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(p.color("ground"))
        g.drawRoundedRect(rect, size * 0.22, size * 0.22)
        draw_mark(g, rect.adjusted(size * 0.17, size * 0.17, -size * 0.17, -size * 0.17), p)
        g.end()
        icon.addPixmap(QPixmap.fromImage(image))
    return icon


def action_icon(kind: str, p: theme.Palette | None = None, enabled: bool = True) -> QIcon:
    """Small monochrome toolbar icons in theme colours (so they never vanish on a theme)."""
    p = p or theme.current()
    icon = QIcon()
    for state, key in ((QIcon.Mode.Normal, "text"), (QIcon.Mode.Disabled, "faint")):
        size = 40
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        g = QPainter(image)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        colour = p.color(key)
        pen = QPen(colour, 4.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        g.setPen(pen)
        g.setBrush(Qt.BrushStyle.NoBrush)
        if kind == "pause":
            g.drawLine(QPointF(14, 9), QPointF(14, 31))
            g.drawLine(QPointF(26, 9), QPointF(26, 31))
        elif kind == "play":
            path = QPainterPath()
            path.moveTo(13, 8)
            path.lineTo(32, 20)
            path.lineTo(13, 32)
            path.closeSubpath()
            g.setBrush(colour)
            g.drawPath(path)
        elif kind == "retry":
            g.drawArc(QRectF(9, 9, 22, 22), 40 * 16, 270 * 16)
            head = QPainterPath()
            head.moveTo(27, 5)
            head.lineTo(31, 12)
            head.lineTo(23, 14)
            g.drawPath(head)
        elif kind == "cancel":
            g.drawLine(QPointF(11, 11), QPointF(29, 29))
            g.drawLine(QPointF(29, 11), QPointF(11, 29))
        else:  # folder
            g.drawRoundedRect(QRectF(6, 12, 28, 20), 4, 4)
            g.drawLine(QPointF(6, 12), QPointF(6, 9))
            g.drawLine(QPointF(6, 9), QPointF(15, 9))
            g.drawLine(QPointF(15, 9), QPointF(18, 12))
        g.end()
        icon.addPixmap(QPixmap.fromImage(image), state)
    return icon


# -- the flat progress bar ----------------------------------------------------------
def paint_bar(painter: QPainter, rect: QRectF, fraction: float | None, fill: str = "hue",
              p: theme.Palette | None = None) -> None:
    """A flat 4 px bar: ``track`` with a rounded fill in ``hue`` (or ``faint`` when paused)."""
    p = p or theme.current()
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    radius = rect.height() / 2
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(p.color("track"))
    painter.drawRoundedRect(rect, radius, radius)
    fraction = 0.0 if fraction is None else max(0.0, min(1.0, fraction))
    if fraction > 0.0:
        width = max(rect.height(), rect.width() * fraction)
        painter.setBrush(p.color(fill))
        painter.drawRoundedRect(QRectF(rect.left(), rect.top(), width, rect.height()), radius, radius)
    painter.restore()


# -- the brand ------------------------------------------------------------------------
class BrandMark(QWidget):
    """The mark and "Elisium" (18/700) at the left of the top bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Elisium")
        theme.notifier().changed.connect(self.update)

    def _font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(round(18 * _u(self.font())))
        font.setWeight(QFont.Weight.Bold)
        return font

    def sizeHint(self) -> QSize:  # noqa: N802
        u = _u(self.font())
        fm = QFontMetrics(self._font())
        return QSize(round(22 * u + 9 * u + fm.horizontalAdvance("Elisium")),
                     max(round(32 * u), fm.height()))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, _event: QEvent) -> None:  # noqa: N802
        p = theme.current()
        u = _u(self.font())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        h = self.height()
        draw_mark(painter, QRectF(0, (h - 22 * u) / 2, 22 * u, 22 * u), p)
        font = self._font()
        painter.setFont(font)
        painter.setPen(p.color("text"))
        painter.drawText(QRectF(31 * u, 0, self.width() - 31 * u, h),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), "Elisium")
        painter.end()


# -- sizing helpers ---------------------------------------------------------------------
def _u(base: QFont) -> float:
    """The text scale: 1.0 at the normal size, 2.0 at 200%; every pixel size is multiplied by it."""
    px = QFontInfo(base).pixelSize()
    return max(1.0, (px if px > 0 else 16) / 16.0)


def _px(base: QFont, size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """*base* at a Night shelf pixel *size* (scaled with the text size); never under 12 px."""
    font = QFont(base)
    font.setPixelSize(max(12, round(size * _u(base))))
    font.setWeight(weight)
    try:
        font.setFeature(QFont.Tag("tnum"), 1)  # numbers that update keep a steady width
    except (AttributeError, TypeError):  # pragma: no cover - older PySide
        pass
    return font


# -- count cards = filters -----------------------------------------------------------------
class CountCard(QRadioButton):
    """One card: a 13 px label over a 16/600 count; the selected one has a 1.5 px ``hue`` outline.

    Built on a radio button so a screen reader says "radio button, checked" and the arrow
    keys move between the cards for free. It draws itself; its accessible name is
    "<label>: <count>".
    """

    def __init__(self, key: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.label = label
        self.count = 0
        self._previous = 0
        self._fade = 1.0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(theme.MOTION["fastMs"])
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_fade)
        theme.notifier().changed.connect(self.update)
        self._name()

    def _name(self) -> None:
        self.setAccessibleName(f"{self.label}: {self.count}")
        self.setAccessibleDescription(f"Show {self.label.lower()} downloads" if self.key != "all"
                                      else "Show every download")

    def set_count(self, count: int) -> None:
        if count == self.count:
            return
        self._previous, self.count = self.count, count
        self._name()
        if _motion_off() or not self.isVisible():
            self._fade = 1.0
            self.update()
        else:
            self._anim.stop()
            self._anim.start()

    def _on_fade(self, value: Any) -> None:
        self._fade = float(value)
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        u = _u(self.font())
        label = QFontMetrics(_px(self.font(), 13))
        count = QFontMetrics(_px(self.font(), 16, QFont.Weight.DemiBold))
        height = max(round(theme.SIZE["countCard"] * u), label.height() + count.height() + round(22 * u))
        return QSize(label.horizontalAdvance(self.label) + round(28 * u), height)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.sizeHint().width() // 2, self.sizeHint().height())

    def paintEvent(self, _event: QEvent) -> None:  # noqa: N802
        p = theme.current()
        u = _u(self.font())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect())
        radius = float(theme.RADIUS["card"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(p.color("surface" if self.isEnabled() else "ground"))
        painter.drawRoundedRect(rect, radius, radius)
        focused = self.hasFocus()
        if self.isChecked():
            inset = 3.5 if focused else 0.75
            painter.setPen(QPen(p.color("hue"), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(inset, inset, -inset, -inset),
                                    radius - inset, radius - inset)
        if focused:
            painter.setPen(QPen(p.color("focus"), 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius - 1, radius - 1)
        pad_x, pad_y = 14 * u, 11 * u
        label_font = _px(self.font(), 13)
        count_font = _px(self.font(), 16, QFont.Weight.DemiBold)
        lfm, cfm = QFontMetrics(label_font), QFontMetrics(count_font)
        painter.setFont(label_font)
        painter.setPen(p.color("muted"))
        painter.drawText(QRectF(pad_x, pad_y, rect.width() - 2 * pad_x, lfm.height()),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         lfm.elidedText(self.label, Qt.TextElideMode.ElideRight,
                                        int(rect.width() - 2 * pad_x)))
        painter.setFont(count_font)
        top = pad_y + lfm.height()
        area = QRectF(pad_x, top, rect.width() - 2 * pad_x, cfm.height())
        align = int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        if self._fade < 1.0:  # a count change cross-fades (120 ms)
            painter.setOpacity(1.0 - self._fade)
            painter.drawText(area.translated(0, 0), align, str(self._previous))
            painter.setOpacity(self._fade)
        painter.setPen(p.color("text"))
        painter.drawText(area, align, str(self.count))
        painter.end()


class CountCards(QWidget):
    """Five equal cards (All, Downloading, Waiting, Failed, Done) that filter the list."""

    filterChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Filters")
        self.setAccessibleDescription("Choose which downloads the list shows. Use the arrow keys to move.")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(int(theme.SPACE["gap"]))
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.cards: dict[str, CountCard] = {}
        for key in FILTERS:
            card = CountCard(key, FILTER_LABELS[key], self)
            card.setAutoExclusive(True)
            self.group.addButton(card)
            layout.addWidget(card, 1)
            self.cards[key] = card
        self.cards["all"].setChecked(True)
        self.group.buttonToggled.connect(self._toggled)

    def _toggled(self, button: Any, checked: bool) -> None:
        if checked:
            self.filterChanged.emit(button.key)

    def current_key(self) -> str:
        return next((k for k, c in self.cards.items() if c.isChecked()), "all")

    def set_current(self, key: str) -> None:
        if key in self.cards:
            self.cards[key].setChecked(True)

    def set_counts(self, counts: dict[str, int]) -> None:
        for key, card in self.cards.items():
            card.set_count(int(counts.get(key, 0)))


# -- download rows ---------------------------------------------------------------------------
def _title(row: dict[str, Any]) -> str:
    return row.get("title") or row.get("url") or ""


@dataclass
class RowGeometry:
    """Where every part of one download row goes (logical pixels, already scaled)."""

    card: QRectF
    thumb: QRectF
    title: QRectF
    meta: QRectF
    note: QRectF | None
    bar: QRectF | None
    big: QRectF
    sub: QRectF
    pill: QRectF | None
    link_open: QRectF | None
    link_folder: QRectF | None
    actions_right: float   # right edge of the icon buttons, left of the right column
    centre_y: float


class _CardDelegate(QStyledItemDelegate):
    """Shared card chrome: a flat rounded rectangle (``surface``; ``raised`` when selected)."""

    H_MARGIN = 0
    V_MARGIN = 4

    def card_rect(self, rect: Any, u: float) -> QRectF:
        return QRectF(rect).adjusted(self.H_MARGIN * u, self.V_MARGIN * u,
                                     -self.H_MARGIN * u, -self.V_MARGIN * u)

    @staticmethod
    def fonts(base: QFont) -> tuple[QFont, QFont, QFont]:
        def f(factor: float, weight: QFont.Weight) -> QFont:
            font = QFont(base)
            font.setWeight(weight)
            if base.pointSizeF() > 0:
                font.setPointSizeF(max(1.0, base.pointSizeF() * factor))
            return font
        return (f(1.0, QFont.Weight.DemiBold), f(0.92, QFont.Weight.Normal),
                f(0.92, QFont.Weight.DemiBold))

    def paint_card(self, painter: QPainter, card: QRectF, option: QStyleOptionViewItem,
                   u: float) -> None:
        p = theme.current()
        radius = float(theme.RADIUS["row"])
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(p.color("raised" if selected else "surface"))
        painter.drawRoundedRect(card, radius, radius)
        view = option.widget
        if (
            selected and view is not None and view.hasFocus()
            and option.state & QStyle.StateFlag.State_HasFocus
        ):
            painter.setPen(QPen(p.color("focus"), 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(card.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)

    def paint_chip(self, painter: QPainter, text: str, state: str, right: float, top: float,
                   height: float, font: QFont) -> float:
        """Draw a state chip ending at *right*; return its left edge."""
        fm = QFontMetrics(font)
        pad = height * 0.5
        width = fm.horizontalAdvance(text) + pad * 2
        rect = QRectF(right - width, top, width, height)
        bg, fg = chip_colours(state)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, height / 2, height / 2)
        painter.setPen(fg)
        painter.setFont(font)
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
        return rect.left()

    def chip_height(self, fm: QFontMetrics) -> float:
        return fm.height() + 6


class QueueDelegate(_CardDelegate):
    """A download as a row: thumbnail, title, meta line, 4 px bar, figure and speed on the right.

    The row is 80 px high (scaled with the text) on a ``surface`` card with an 8 px gap below.
    """

    GAP_PX = 8
    V_MARGIN = 0

    actions_row_id: int | None = None  # row showing action buttons (set by CardActions)
    actions_width: float = 0.0
    thumbnails: ThumbnailCache | None = None  # set by the window; None draws placeholders
    sign_in_codes: frozenset[str] = frozenset()  # set by the window: errors fixed by "Sign in"

    def pill_text(self, row: dict[str, Any]) -> str | None:
        """The one fix a failed row offers: "Sign in" for an expired or missing sign-in, else "Retry"."""
        if row["state"] != "failed":
            return None
        code = (row.get("error") or {}).get("code")
        return "Sign in" if code in self.sign_in_codes else "Retry"

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._placeholders: dict[tuple, QPixmap] = {}

    # -- sizes ------------------------------------------------------------
    def metrics(self, base: QFont) -> dict[str, float]:
        u = _u(base)
        return {"u": u, "pad": 16 * u, "gap": self.GAP_PX * u,
                "height": (theme.SIZE["rowHeight"] + self.GAP_PX) * u}

    def row_height(self, base: QFont) -> int:
        return int(math.ceil(self.metrics(base)["height"]))

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(200, self.row_height(option.font))

    def card_rect(self, rect: Any, u: float) -> QRectF:
        return QRectF(rect).adjusted(0, 0, 0, -self.GAP_PX * u)

    @staticmethod
    def row_fonts(base: QFont) -> dict[str, QFont]:
        semi, bold = QFont.Weight.DemiBold, QFont.Weight.Bold
        return {
            "title": _px(base, 15, semi), "meta": _px(base, 13), "figure": _px(base, 24, semi),
            "word": _px(base, 15, semi), "sub": _px(base, 12), "pill": _px(base, 13, semi),
            "link": _px(base, 12, semi), "bold": _px(base, 15, bold),
        }

    def geometry(self, rect: Any, row: dict[str, Any], base: QFont, text: RowText | None = None,
                 actions_width: float = 0.0) -> RowGeometry:
        """Lay out one row inside the item *rect* (also used to place the card's real buttons)."""
        text = text or describe_row(row)
        u = _u(base)
        f = self.row_fonts(base)
        fm = {k: QFontMetrics(v) for k, v in f.items()}
        card = self.card_rect(rect, u)
        thumb_w, thumb_h = theme.SIZE["thumbDesktop"]
        thumb = QRectF(card.left() + 9 * u, card.top() + (card.height() - thumb_h * u) / 2,
                       thumb_w * u, thumb_h * u)
        right_edge = card.right() - 16 * u
        # The right column: wide enough for "4.2 MB/s · 1 min 37 s left", never over 42% of the row.
        wanted = fm["sub"].horizontalAdvance("9.9 MB/s · 59 min 59 s left") + 2 * u
        if row["state"] == "failed":
            wanted = max(wanted, fm["sub"].horizontalAdvance(text.sub) + 2 * u)
        width = min(wanted, card.width() * 0.42)
        left = right_edge - width
        text_x = thumb.right() + 16 * u
        text_right = max(text_x + 40 * u, left - 16 * u - (actions_width + 8 * u if actions_width else 0))
        # Text block (title, meta, optional note, optional bar), centred vertically.
        th, mh, nh = fm["title"].height(), fm["meta"].height(), fm["meta"].height()
        total = th + 2 * u + mh
        if text.note:
            total += 2 * u + nh
        if text.bar:
            total += 7 * u + theme.SIZE["progress"] * u
        y = card.top() + (card.height() - total) / 2
        title = QRectF(text_x, y, text_right - text_x, th)
        y += th + 2 * u
        meta = QRectF(text_x, y, text_right - text_x, mh)
        y += mh
        note = None
        if text.note:
            y += 2 * u
            note = QRectF(text_x, y, text_right - text_x, nh)
            y += nh
        bar = None
        if text.bar:
            y += 7 * u
            bar = QRectF(text_x, y, text_right - text_x, theme.SIZE["progress"] * u)
        # Right column.
        big_h = fm["figure" if text.big_is_percent else "word"].height()
        sub_h = fm["sub"].height()
        pill = link_open = link_folder = None
        if row["state"] == "failed":
            pill_h = 28 * u
            pill_w = fm["pill"].horizontalAdvance(self.pill_text(row) or "Retry") + 28 * u
            block = sub_h + 6 * u + pill_h
            top = card.top() + (card.height() - block) / 2
            big = QRectF(left, top, width, 0.0)
            sub = QRectF(left, top, width, sub_h)
            pill = QRectF(right_edge - pill_w, sub.bottom() + 6 * u, pill_w, pill_h)
        else:
            block = (big_h if text.big else 0) + (sub_h if text.sub else 0)
            top = card.top() + (card.height() - block) / 2
            big = QRectF(left, top, width, big_h if text.big else 0.0)
            sub = QRectF(left, big.bottom(), width, sub_h)
            if row["state"] == "done":
                folder_w = fm["link"].horizontalAdvance("Show in folder") + 8 * u
                open_w = fm["link"].horizontalAdvance("Open") + 8 * u
                dot_w = fm["sub"].horizontalAdvance(" · ")
                link_folder = QRectF(right_edge - folder_w, sub.top(), folder_w, sub_h)
                link_open = QRectF(link_folder.left() - dot_w - open_w, sub.top(), open_w, sub_h)
        return RowGeometry(card, thumb, title, meta, note, bar, big, sub, pill, link_open,
                           link_folder, left - 8 * u, card.center().y())

    # -- painting ---------------------------------------------------------
    def thumbnail_for(self, row: dict[str, Any], rect: QRectF, ratio: float, base: QFont) -> QPixmap:
        pixmap = None
        if self.thumbnails is not None:
            pixmap = self.thumbnails.get(row.get("thumbnail"), round(rect.width()),
                                         round(rect.height()), ratio)
        if pixmap is not None:
            return pixmap
        site = site_name(row.get("url"))
        key = (site, round(rect.width()), round(rect.height()), ratio, theme.current().name,
               QFontInfo(base).family())
        if key not in self._placeholders:
            if len(self._placeholders) > 64:
                self._placeholders.clear()
            self._placeholders[key] = row_placeholder(site, round(rect.width()), round(rect.height()),
                                                      ratio, base)
        return self._placeholders[key]

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        model = index.model()
        row = model.snapshot_at(index.row()) if hasattr(model, "snapshot_at") else None
        if row is None:
            return
        p = theme.current()
        text = describe_row(row)
        active = row["id"] == self.actions_row_id
        geo = self.geometry(option.rect, row, option.font, text, self.actions_width if active else 0.0)
        f = self.row_fonts(option.font)
        fm = {k: QFontMetrics(v) for k, v in f.items()}
        u = _u(option.font)
        painter.save()
        entering = enter_animation().progress(row["id"])
        if entering < 1.0:
            painter.setOpacity(entering)
            painter.translate(0.0, EnterAnimation.RISE_PX * (1.0 - entering))
        self.paint_card(painter, geo.card, option, u)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        ratio = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
        painter.drawPixmap(geo.thumb.topLeft(), self.thumbnail_for(row, geo.thumb, ratio, option.font))

        left = int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        right = int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        painter.setFont(f["title"])
        painter.setPen(p.color("text"))
        painter.drawText(geo.title, left, fm["title"].elidedText(
            _title(row), Qt.TextElideMode.ElideRight, int(geo.title.width())))
        painter.setFont(f["meta"])
        painter.setPen(p.color("faint"))
        painter.drawText(geo.meta, left, fm["meta"].elidedText(
            text.meta, Qt.TextElideMode.ElideRight, int(geo.meta.width())))
        if geo.note is not None:
            painter.setPen(p.color("muted"))
            painter.drawText(geo.note, left, fm["meta"].elidedText(
                text.note, Qt.TextElideMode.ElideRight, int(geo.note.width())))
        if geo.bar is not None:
            percent = DownloadModel.percent_of(row)
            shown = None if percent is None else progress_ease().value_for(row["id"], percent)
            paint_bar(painter, geo.bar, None if shown is None else shown / 100.0, text.bar or "hue", p)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        tone = legible_colour(p, text.tone, "raised" if selected else "surface")
        if text.big:
            painter.setFont(f["figure"] if text.big_is_percent else f["word"])
            painter.setPen(p.color("text") if text.big_is_percent else tone)
            painter.drawText(geo.big, right, text.big)
        painter.setFont(f["sub"])
        if row["state"] == "done":
            # "Open · Show in folder": the card's real buttons draw the words while it is
            # hovered or selected; otherwise they are painted here.
            if geo.link_open is not None and geo.link_folder is not None:
                painter.setPen(p.color("muted"))
                gap = QRectF(geo.link_open.right(), geo.sub.top(),
                             geo.link_folder.left() - geo.link_open.right(), geo.sub.height())
                painter.drawText(gap, int(Qt.AlignmentFlag.AlignCenter), "·")
                if not active:
                    painter.setPen(p.color("text"))
                    painter.setFont(f["link"])
                    painter.drawText(geo.link_open, int(Qt.AlignmentFlag.AlignCenter), "Open")
                    painter.drawText(geo.link_folder, int(Qt.AlignmentFlag.AlignCenter), "Show in folder")
        elif text.sub:
            painter.setPen(legible_colour(p, "negative" if row["state"] == "failed" else "muted",
                                          "raised" if selected else "surface"))
            painter.drawText(geo.sub, right, fm["sub"].elidedText(
                text.sub, Qt.TextElideMode.ElideLeft, int(geo.sub.width())))
        if geo.pill is not None and not active:
            # The fix as an inverted pill (the real button takes over on hover or selection).
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(p.color("primary"))
            painter.drawRoundedRect(geo.pill, geo.pill.height() / 2, geo.pill.height() / 2)
            painter.setFont(f["pill"])
            painter.setPen(p.color("onPrimary"))
            painter.drawText(geo.pill, int(Qt.AlignmentFlag.AlignCenter), self.pill_text(row) or "Retry")
        painter.restore()


class HistoryDelegate(_CardDelegate):
    """A history entry as a card: title, state chip, then site - date - file.

    Restyled to the Night shelf look only; its layout belongs to brief 11C-2.
    """

    V_MARGIN = 4
    H_MARGIN = 4

    def metrics(self, base: QFont) -> dict[str, float]:
        title_f, cap_f, _c = self.fonts(base)
        tfm, cfm = QFontMetrics(title_f), QFontMetrics(cap_f)
        u = _u(base)
        pad = 14 * u
        gap = 6 * u
        inner = max(tfm.height(), self.chip_height(cfm)) + gap + cfm.height()
        return {"u": u, "pad": pad, "gap": gap, "height": inner + 2 * pad + 2 * self.V_MARGIN * u}

    def row_height(self, base: QFont) -> int:
        return int(math.ceil(self.metrics(base)["height"]))

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(200, self.row_height(option.font))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        model = index.model()
        row = model.row_at(index.row()) if hasattr(model, "row_at") else None
        if row is None:
            return
        from .history_page import HistoryModel, _date, _site  # local: avoids an import cycle

        p = theme.current()
        m = self.metrics(option.font)
        u, pad, gap = m["u"], m["pad"], m["gap"]
        title_f, cap_f, chip_f = self.fonts(option.font)
        tfm, cfm = QFontMetrics(title_f), QFontMetrics(cap_f)
        card = self.card_rect(option.rect, u)
        painter.save()
        self.paint_card(painter, card, option, u)
        inner = card.adjusted(pad, pad, -pad, -pad)
        missing = bool(row.get("file_missing"))
        state = "paused" if missing else row["state"]  # "File missing" reads as a warning
        chip_h = self.chip_height(QFontMetrics(chip_f))
        line_h = max(tfm.height(), chip_h)
        left = self.paint_chip(painter, HistoryModel.state_text(row), state, inner.right(),
                               inner.top() + (line_h - chip_h) / 2, chip_h, chip_f)
        title_w = max(40.0, left - inner.left() - gap)
        painter.setFont(title_f)
        painter.setPen(p.color("text"))
        painter.drawText(QRectF(inner.left(), inner.top(), title_w, line_h),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         tfm.elidedText(row.get("title") or row["url"],
                                        Qt.TextElideMode.ElideRight, int(title_w)))
        file_name = (row.get("file_path") or "").rsplit("/", 1)[-1]
        bits = [_site(row["url"]), _date(row)] + ([file_name] if file_name else [])
        painter.setFont(cap_f)
        painter.setPen(p.color("muted"))
        painter.drawText(
            QRectF(inner.left(), inner.top() + line_h + gap, inner.width(), cfm.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            cfm.elidedText("  ·  ".join(b for b in bits if b), Qt.TextElideMode.ElideRight,
                           int(inner.width())),
        )
        painter.restore()


class RowHeightKeeper(QObject):
    """Keeps a card view's fixed row height in step with its font (text size changes)."""

    def __init__(self, view: Any, delegate: Any) -> None:
        super().__init__(view)
        self._view, self._delegate = view, delegate
        view.installEventFilter(self)
        self.update()

    def update(self) -> None:
        self._view.verticalHeader().setDefaultSectionSize(
            self._delegate.row_height(self._view.font())
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange,
                            QEvent.Type.Polish, QEvent.Type.Show):
            self.update()
        return False


# -- empty state --------------------------------------------------------------------------
class EmptyState(QWidget):
    """The mark and one plain sentence, laid over an empty list. No clip-art."""

    def __init__(self, parent: QWidget,
                 text: str = "Paste a link from YouTube, Instagram, TikTok…") -> None:
        super().__init__(parent)
        self.text = text
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAccessibleName("Empty list")
        self.setAccessibleDescription(text)
        parent.installEventFilter(self)
        theme.notifier().changed.connect(self.update)
        self._fit()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.parent() and event.type() == QEvent.Type.Resize:
            self._fit()
        return False

    def _fit(self) -> None:
        self.setGeometry(self.parentWidget().rect())

    def paintEvent(self, _event: QEvent) -> None:  # noqa: N802
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        u = _u(self.font())
        size = min(64 * u, self.height() * 0.3, self.width() * 0.3)
        font = _px(self.font(), 15, QFont.Weight.DemiBold)
        fm = QFontMetrics(font)
        gap = 16 * u
        top = (self.height() - (size + gap + fm.height())) / 2
        cx = self.width() / 2
        draw_mark(painter, QRectF(cx - size / 2, top, size, size), p)
        painter.setFont(font)
        painter.setPen(p.color("muted"))
        painter.drawText(QRectF(0, top + size + gap, self.width(), fm.height()),
                         int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                         fm.elidedText(self.text, Qt.TextElideMode.ElideRight, self.width() - 32))
        painter.end()
