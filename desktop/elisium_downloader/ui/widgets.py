"""Afterglow widgets: glow progress, card delegates, horizon header, empty state, icons.

No colour literals here: every colour is a token fetched from ``theme.current()``.
"""

from __future__ import annotations

import math
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
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from . import theme
from .model import STATUS_TEXT, format_bytes, format_eta, format_speed

__all__ = [
    "Breath",
    "EmptyState",
    "GlowProgress",
    "HistoryDelegate",
    "HorizonHeader",
    "QueueDelegate",
    "RowHeightKeeper",
    "action_icon",
    "app_icon",
    "breath",
    "caption_parts",
    "chip_colours",
    "draw_glyph",
    "paint_glow_bar",
    "visible_parts",
]

_RUNNING = ("downloading", "merging", "converting")
_CHIP_KEY = {
    "queued": "muted", "probing": "muted", "downloading": "accent", "merging": "accent",
    "converting": "accent", "paused": "warning", "done": "success", "failed": "error",
    "skipped": "muted", "cancelled": "muted",
}
CHIP_TINT = 0.10


def chip_colours(state: str, p: theme.Palette | None = None) -> tuple[QColor, QColor]:
    """``(background, text)`` of the state chip: the semantic token tinted on ``surface``."""
    p = p or theme.current()
    key = _CHIP_KEY.get(state, "muted")
    return p.blend(key, "surface", CHIP_TINT), p.color(key)


# -- breathing animation -----------------------------------------------------
def _motion_off() -> bool:
    from .quality_dialog import reduce_motion  # local: avoids an import cycle

    return reduce_motion()


class Breath(QVariantAnimation):
    """ONE shared slow loop that makes the glow edge of every running bar breathe."""

    PERIOD_MS = 2600

    def __init__(self) -> None:
        super().__init__()
        self.setStartValue(0.0)
        self.setEndValue(1.0)
        self.setDuration(self.PERIOD_MS)
        self.setLoopCount(-1)
        self.setEasingCurve(QEasingCurve.Type.Linear)
        self._wanted = False
        theme.notifier().changed.connect(self._sync)

    def phase(self) -> float:
        """0..1..0 smooth; a still 0.5 when motion is reduced or nothing is running."""
        if _motion_off() or self.state() != QVariantAnimation.State.Running:
            return 0.5
        return 0.5 - 0.5 * math.cos(2 * math.pi * float(self.currentValue() or 0.0))

    def set_active(self, wanted: bool) -> None:
        self._wanted = wanted
        self._sync()

    def _sync(self) -> None:
        run = self._wanted and not _motion_off()
        running = self.state() == QVariantAnimation.State.Running
        if run and not running:
            self.start()
        elif not run and running:
            self.stop()


_breath: Breath | None = None


def breath() -> Breath:
    global _breath
    if _breath is None:
        _breath = Breath()
    return _breath


# -- glyph and icons -----------------------------------------------------------
def draw_glyph(painter: QPainter, rect: QRectF, brush: Any, weight: float = 12.0) -> None:
    """The arrow-into-tray glyph (same geometry as ``packaging/elisium.svg``)."""
    s = rect.width() / 128.0
    painter.save()
    painter.translate(rect.topLeft())
    painter.scale(s, s)
    pen = QPen(brush, weight)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(64, 26), QPointF(64, 76))
    chevron = QPainterPath()
    chevron.moveTo(42, 56)
    chevron.lineTo(64, 78)
    chevron.lineTo(86, 56)
    painter.drawPath(chevron)
    painter.drawLine(QPointF(30, 94), QPointF(98, 94))
    painter.restore()


def _glow_gradient(p: theme.Palette, a: QPointF, b: QPointF, alpha: float = 1.0) -> QLinearGradient:
    grad = QLinearGradient(a, b)
    for pos, key in ((0.0, "glowA"), (0.55, "glowB"), (1.0, "glowC")):
        grad.setColorAt(pos, p.color(key, alpha))
    return grad


def app_icon() -> QIcon:
    """The launcher icon, drawn: glow glyph on an ink-violet rounded square (night palette)."""
    p = theme.NIGHT
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        g = QPainter(image)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, size, size)
        bg = QLinearGradient(rect.topLeft(), rect.bottomRight())
        bg.setColorAt(0, p.color("raised"))
        bg.setColorAt(1, p.color("bg"))
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(bg)
        g.drawRoundedRect(rect, size * 0.22, size * 0.22)
        halo = QRadialGradient(QPointF(size * 0.5, size * 0.81), size * 0.47)
        halo.setColorAt(0, p.color("glowB", 0.35))
        halo.setColorAt(1, p.color("glowB", 0.0))
        g.setBrush(halo)
        g.drawRoundedRect(rect, size * 0.22, size * 0.22)
        draw_glyph(g, rect, _glow_gradient(p, QPointF(size * 0.23, size * 0.2),
                                           QPointF(size * 0.77, size * 0.74)), 11.0)
        g.end()
        icon.addPixmap(QPixmap.fromImage(image))
    return icon


def action_icon(kind: str, p: theme.Palette | None = None, enabled: bool = True) -> QIcon:
    """Small monochrome toolbar icons in theme colours (so they never vanish on a theme)."""
    p = p or theme.current()
    icon = QIcon()
    for state, key in ((QIcon.Mode.Normal, "text"), (QIcon.Mode.Disabled, "muted")):
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


# -- glow progress -------------------------------------------------------------
def paint_glow_bar(
    painter: QPainter,
    rect: QRectF,
    percent: float | None,
    state: str,
    p: theme.Palette | None = None,
    phase: float = 0.5,
    glow_clip: QRectF | None = None,
) -> None:
    """A thick rounded bar filled with the glow gradient and a soft glowing leading cap.

    running = glow gradient + breathing cap; paused = muted, no glow; done = ``success``;
    failed = ``error``; queued/probing = empty track. *phase* (0..1) breathes the cap.
    """
    p = p or theme.current()
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    radius = rect.height() / 2
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(p.color("outline"))
    painter.drawRoundedRect(rect, radius, radius)

    if state == "done":
        fraction = 1.0
    elif percent is None:
        fraction = 0.0
    else:
        fraction = max(0.0, min(1.0, percent / 100.0))
    if fraction > 0.0:
        width = max(rect.height(), rect.width() * fraction)
        fill = QRectF(rect.left(), rect.top(), width, rect.height())
        if state == "done":
            brush: Any = p.color("success")
        elif state == "failed":
            brush = p.color("error")
        elif state == "paused":
            brush = p.color("muted")
        else:
            brush = _glow_gradient(p, fill.topLeft(), fill.topRight())
        # The leading cap glow bleeds outside the track, so it goes first and softly.
        if state in _RUNNING or state == "downloading":
            cx = fill.right() - radius
            cy = fill.center().y()
            reach = rect.height() * (2.1 + 0.5 * phase)
            halo = QRadialGradient(QPointF(cx, cy), reach)
            halo.setColorAt(0.0, p.color("glowC", 0.50 + 0.30 * phase))
            halo.setColorAt(0.45, p.color("glowB", 0.16 + 0.10 * phase))
            halo.setColorAt(1.0, p.color("glowB", 0.0))
            if glow_clip is not None:
                painter.setClipRect(glow_clip)
            painter.setBrush(halo)
            painter.drawEllipse(QPointF(cx, cy), reach, reach * 0.9)
            painter.setClipping(False)
        painter.setBrush(brush)
        painter.drawRoundedRect(fill, radius, radius)
        if state in _RUNNING and fill.width() > rect.height():
            # The brighter cap: a small light disc at the very end of the fill.
            cap = p.color("glowC").lighter(125)
            cap.setAlphaF(0.55 + 0.35 * phase)
            painter.setBrush(cap)
            painter.drawEllipse(QPointF(fill.right() - radius, fill.center().y()),
                                radius * 0.62, radius * 0.62)
    painter.restore()


class GlowProgress(QWidget):
    """The glow bar as a plain widget (used where a delegate does not fit, and in tests)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._percent: float | None = 0.0
        self._state = "downloading"
        self.setMinimumHeight(14)
        self.setAccessibleName("Progress")
        theme.notifier().changed.connect(self.update)

    def set_progress(self, percent: float | None, state: str = "downloading") -> None:
        self._percent, self._state = percent, state
        text = "unknown" if percent is None else f"{percent:.0f} percent"
        self.setAccessibleDescription(text)
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(160, 16)

    def paintEvent(self, _event: QEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        bar = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bar.setHeight(min(bar.height(), 12.0))
        bar.moveCenter(QRectF(self.rect()).center())
        paint_glow_bar(painter, bar, self._percent, self._state, phase=breath().phase())
        painter.end()


# -- caption (speed - size - time left) ------------------------------------------
def caption_parts(row: dict[str, Any]) -> list[tuple[str, str]]:
    """The info line of a queue card as ``[(key, text)]``; keys are ``speed``, ``size``,
    ``eta`` or ``note``. Low-priority parts (size, then time left, then speed) are
    dropped first when the window is narrow (see ``visible_parts``)."""
    state = row["state"]
    progress = row.get("progress") or {}
    size = format_bytes(progress.get("total_bytes") or progress.get("downloaded_bytes"))
    if state in _RUNNING:
        parts = []
        if state == "downloading" or progress.get("speed"):
            speed = format_speed(progress.get("speed"))
            if speed:
                parts.append(("speed", speed))
        if size:
            parts.append(("size", size))
        eta = format_eta(progress.get("eta"))
        if eta:
            parts.append(("eta", f"{eta} left"))
        if not parts:
            parts.append(("note", "Starting"))
        return parts
    if state == "queued":
        return [("note", "Waiting in line")]
    if state == "probing":
        return [("note", "Checking the link")]
    if state == "paused":
        parts = [("note", "Paused")]
        if size:
            parts.append(("size", size))
        return parts
    if state == "done":
        return [("note", "Finished"), *([("size", size)] if size else [])]
    if state in ("failed", "skipped"):
        error = row.get("error") or {}
        message = error.get("message") or ("Could not finish" if state == "failed" else "Skipped")
        return [("note", message)]
    return [("note", "Cancelled")]


def visible_parts(parts: list[tuple[str, str]], fm: QFontMetrics, width: int,
                  separator: str = "  ·  ") -> list[tuple[str, str]]:
    """Drop the lowest-priority parts until the line fits *width*."""
    keep = list(parts)
    for drop in ("size", "eta", "speed"):
        if fm.horizontalAdvance(separator.join(t for _k, t in keep)) <= width:
            break
        keep = [(k, t) for k, t in keep if k != drop]
    return keep


# -- card delegates ------------------------------------------------------------
def _scale(fm: QFontMetrics) -> float:
    return max(1.0, fm.height() / 18.0)


def _font(base: QFont, weight: QFont.Weight, factor: float = 1.0, tabular: bool = False) -> QFont:
    font = QFont(base)
    font.setWeight(weight)
    if factor != 1.0:
        font.setPointSizeF(max(1.0, base.pointSizeF() * factor)) if base.pointSizeF() > 0 else None
    if tabular:
        try:
            font.setFeature(QFont.Tag("tnum"), 1)
        except (AttributeError, TypeError):  # pragma: no cover - older PySide
            pass
    return font


class _CardDelegate(QStyledItemDelegate):
    """Shared card chrome: rounded raised rectangle, outline, gradient selection, focus ring."""

    H_MARGIN = 4
    V_MARGIN = 4

    def card_rect(self, rect: Any, u: float) -> QRectF:
        return QRectF(rect).adjusted(self.H_MARGIN * u, self.V_MARGIN * u,
                                     -self.H_MARGIN * u, -self.V_MARGIN * u)

    @staticmethod
    def fonts(base: QFont) -> tuple[QFont, QFont, QFont]:
        return (_font(base, QFont.Weight.Bold), _font(base, QFont.Weight.Normal, 0.9, True),
                _font(base, QFont.Weight.DemiBold, 0.9))

    def paint_card(self, painter: QPainter, card: QRectF, option: QStyleOptionViewItem,
                   u: float) -> None:
        p = theme.current()
        radius = float(theme.RADIUS["medium"])
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(p.color("raised"))
        pen = QPen(p.color("outline"), 1.0)
        painter.setPen(pen)
        painter.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        if selected:
            grad = _glow_gradient(p, card.topLeft(), card.topRight())
            painter.setPen(QPen(grad, 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(card.adjusted(0.8, 0.8, -0.8, -0.8), radius, radius)
        view = option.widget
        if (
            selected and view is not None and view.hasFocus()
            and option.state & QStyle.StateFlag.State_HasFocus
        ):
            painter.setPen(QPen(p.color("accent"), 2.0))
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
    """A download as a card: title, state chip, glow progress, speed - size - time left."""

    def metrics(self, base: QFont) -> dict[str, float]:
        title_f, cap_f, _chip_f = self.fonts(base)
        tfm, cfm = QFontMetrics(title_f), QFontMetrics(cap_f)
        u = _scale(QFontMetrics(base))
        pad = 14 * u
        bar = max(10.0, 10 * u)
        gap = 8 * u
        inner = max(tfm.height(), self.chip_height(cfm)) + gap + bar + gap * 0.75 + cfm.height()
        return {"u": u, "pad": pad, "bar": bar, "gap": gap,
                "height": inner + 2 * pad + 2 * self.V_MARGIN * u}

    def row_height(self, base: QFont) -> int:
        return int(math.ceil(self.metrics(base)["height"]))

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(200, self.row_height(option.font))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        model = index.model()
        row = model.snapshot_at(index.row()) if hasattr(model, "snapshot_at") else None
        if row is None:
            return
        p = theme.current()
        m = self.metrics(option.font)
        u, pad, bar_h, gap = m["u"], m["pad"], m["bar"], m["gap"]
        title_f, cap_f, chip_f = self.fonts(option.font)
        tfm, cfm = QFontMetrics(title_f), QFontMetrics(cap_f)
        card = self.card_rect(option.rect, u)
        painter.save()
        self.paint_card(painter, card, option, u)
        inner = card.adjusted(pad, pad, -pad, -pad)
        state = row["state"]

        chip_h = self.chip_height(QFontMetrics(chip_f))
        line_h = max(tfm.height(), chip_h)
        left = self.paint_chip(painter, STATUS_TEXT.get(state, state), state, inner.right(),
                               inner.top() + (line_h - chip_h) / 2, chip_h, chip_f)
        title_w = max(40.0, left - inner.left() - gap)
        painter.setFont(title_f)
        painter.setPen(p.color("text"))
        title = tfm.elidedText(_title(row), Qt.TextElideMode.ElideRight, int(title_w))
        painter.drawText(QRectF(inner.left(), inner.top(), title_w, line_h),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), title)

        percent = _percent(row)
        painter.setFont(cap_f)
        pct_text = "" if percent is None else f"{percent:.0f}%"
        pct_w = cfm.horizontalAdvance("100%") + 4 * u
        bar_top = inner.top() + line_h + gap
        bar = QRectF(inner.left(), bar_top, inner.width() - pct_w - gap, bar_h)
        paint_glow_bar(painter, bar, percent, state, p, breath().phase(), glow_clip=card)
        painter.setPen(p.color("text"))
        painter.drawText(QRectF(bar.right() + gap, bar_top - cfm.height() / 2 + bar_h / 2,
                                pct_w, cfm.height()),
                         int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), pct_text)

        cap_top = bar_top + bar_h + gap * 0.75
        parts = visible_parts(caption_parts(row), cfm, int(inner.width()))
        painter.setPen(p.color("error" if state == "failed" else "muted"))
        text = cfm.elidedText("  ·  ".join(t for _k, t in parts), Qt.TextElideMode.ElideRight,
                              int(inner.width()))
        painter.drawText(QRectF(inner.left(), cap_top, inner.width(), cfm.height()),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)
        painter.restore()


class HistoryDelegate(_CardDelegate):
    """A history entry as a card: title, state chip, then site - date - file."""

    def metrics(self, base: QFont) -> dict[str, float]:
        title_f, cap_f, _c = self.fonts(base)
        tfm, cfm = QFontMetrics(title_f), QFontMetrics(cap_f)
        u = _scale(QFontMetrics(base))
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


def _title(row: dict[str, Any]) -> str:
    return row.get("title") or row.get("url") or ""


def _percent(row: dict[str, Any]) -> float | None:
    if row["state"] == "done":
        return 100.0
    value = (row.get("progress") or {}).get("percent")
    return None if value is None else float(value)


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


# -- horizon header --------------------------------------------------------------
class HorizonHeader(QWidget):
    """The top of the window: a faint glow band behind the gradient "Elisium" wordmark."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Elisium")
        theme.notifier().changed.connect(self.update)

    def _font(self) -> QFont:
        font = QFont(self.font())
        font.setWeight(QFont.Weight.ExtraBold)
        base = self.font().pointSizeF() if self.font().pointSizeF() > 0 else 11.0
        font.setPointSizeF(base * 2.1)  # about 28 px at the default size
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 97)
        return font

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(self._font())
        return QSize(260, fm.height() + 2 * int(14 * _scale(QFontMetrics(self.font()))))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, _event: QEvent) -> None:  # noqa: N802
        p = theme.current()
        w, h = self.width(), self.height()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        # Glow band: the gradient at ~16% opacity, fading to nothing towards the bottom.
        band = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        band.fill(Qt.GlobalColor.transparent)
        bp = QPainter(band)
        bp.fillRect(0, 0, w, h, _glow_gradient(p, QPointF(0, 0), QPointF(w, 0), 0.20 if p.dark else 0.20))
        bp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        fade = QLinearGradient(0, 0, 0, h)
        fade.setColorAt(0, QColor(0, 0, 0, 255))
        fade.setColorAt(0.6, QColor(0, 0, 0, 120))
        fade.setColorAt(1, QColor(0, 0, 0, 0))
        bp.fillRect(0, 0, w, h, fade)
        bp.end()
        painter.drawImage(0, 0, band)
        # Wordmark with the glyph in front, both filled with the glow gradient.
        u = _scale(QFontMetrics(self.font()))
        glyph = QRectF(16 * u, h / 2 - 17 * u, 34 * u, 34 * u)
        draw_glyph(painter, glyph, _glow_gradient(p, glyph.topLeft(), glyph.bottomRight()), 12.0)
        font = self._font()
        fm = QFontMetrics(font)
        text_x = glyph.right() + 12 * u
        text_w = fm.horizontalAdvance("Elisium")
        baseline = (h - fm.height()) / 2 + fm.ascent()
        path = QPainterPath()
        path.addText(QPointF(text_x, baseline), font, "Elisium")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_glow_gradient(p, QPointF(text_x, 0), QPointF(text_x + text_w, 0)))
        painter.drawPath(path)
        # Hairline horizon under the band.
        painter.setPen(QPen(p.color("outline"), 1))
        painter.drawLine(0, h - 1, w, h - 1)
        painter.end()


# -- empty state --------------------------------------------------------------------
class EmptyState(QWidget):
    """A large soft glowing glyph and one warm sentence, laid over an empty list."""

    def __init__(self, parent: QWidget, text: str = "Paste a link to begin") -> None:
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
        u = _scale(QFontMetrics(self.font()))
        size = min(120 * u, self.height() * 0.42, self.width() * 0.5)
        font = QFont(self.font())
        font.setWeight(QFont.Weight.Bold)
        font.setPointSizeF(max(1.0, self.font().pointSizeF() * 1.45))
        fm = QFontMetrics(font)
        total = size + 18 * u + fm.height()
        top = (self.height() - total) / 2
        cx = self.width() / 2
        glyph = QRectF(cx - size / 2, top, size, size)
        for radius, alpha in ((size * 1.25, 0.20), (size * 0.8, 0.22)):
            halo = QRadialGradient(glyph.center() + QPointF(0, size * 0.1), radius)
            halo.setColorAt(0, p.color("glowB", alpha))
            halo.setColorAt(0.6, p.color("glowA", alpha * 0.4))
            halo.setColorAt(1, p.color("glowA", 0.0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(glyph.center() + QPointF(0, size * 0.1), radius, radius)
        draw_glyph(painter, glyph, _glow_gradient(p, glyph.topLeft(), glyph.bottomRight()), 10.0)
        painter.setFont(font)
        painter.setPen(p.color("text"))
        painter.drawText(QRectF(0, glyph.bottom() + 18 * u, self.width(), fm.height()),
                         int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                         self.text)
        painter.end()

