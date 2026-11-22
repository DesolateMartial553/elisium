"""Fetch and scale a video thumbnail; never cached on disk."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QFont, QImage, QPainter, QPainterPath, QPixmap

from . import theme
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

__all__ = ["THUMB_WIDTH", "ThumbnailCache", "ThumbnailLoader", "placeholder_pixmap", "qt_fetcher",
           "row_placeholder", "row_thumbnail"]

THUMB_WIDTH = 240
_THUMB_HEIGHT = 135

# fetcher(url, callback): call callback(bytes) on success or callback(None) on failure.
Fetcher = Callable[[str, Callable[[bytes | None], None]], None]


def _rounded(pixmap: QPixmap) -> QPixmap:
    """The same pixmap with rounded corners (transparent outside)."""
    out = QPixmap(pixmap.size())
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    radius = float(theme.RADIUS["thumb"])
    path.addRoundedRect(0, 0, pixmap.width(), pixmap.height(), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return out


def placeholder_pixmap(text: str = "No preview") -> QPixmap:
    """A soft box in the theme's colours, shown while loading or when the image failed."""
    p = theme.current()
    pixmap = QPixmap(THUMB_WIDTH, _THUMB_HEIGHT)
    pixmap.fill(p.color("raised"))
    painter = QPainter(pixmap)
    painter.setPen(p.color("faint"))
    font = QFont()
    font.setPointSize(11)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), int(Qt.AlignmentFlag.AlignCenter), text)
    painter.end()
    return _rounded(pixmap)


def _rounded_to(pixmap: QPixmap, radius: float) -> QPixmap:
    out = QPixmap(pixmap.size())
    out.setDevicePixelRatio(pixmap.devicePixelRatio())
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    ratio = pixmap.devicePixelRatio() or 1.0
    path.addRoundedRect(QRectF(0, 0, pixmap.width() / ratio, pixmap.height() / ratio), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return out


def row_placeholder(site: str, width: int, height: int, ratio: float = 1.0,
                    font: QFont | None = None) -> QPixmap:
    """The download row's thumbnail stand-in: a ``raised`` block with the site name in ``faint``.

    Never an icon. *width* x *height* are logical pixels; *ratio* is the screen's pixel ratio.
    """
    p = theme.current()
    pixmap = QPixmap(round(width * ratio), round(height * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(p.color("raised"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setPen(p.color("faint"))
    label = QFont(font) if font is not None else QFont()
    label.setPixelSize(12)
    label.setWeight(QFont.Weight.DemiBold)
    painter.setFont(label)
    text = painter.fontMetrics().elidedText(site, Qt.TextElideMode.ElideRight, width - 8)
    painter.drawText(QRectF(0, 0, width, height), int(Qt.AlignmentFlag.AlignCenter), text)
    painter.end()
    return _rounded_to(pixmap, float(theme.RADIUS["thumb"]))


def row_thumbnail(image: QImage, width: int, height: int, ratio: float = 1.0) -> QPixmap:
    """*image* cropped to fill ``width x height`` (cover), with rounded corners."""
    scaled = image.scaled(round(width * ratio), round(height * ratio),
                          Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation)
    x = max(0, (scaled.width() - round(width * ratio)) // 2)
    y = max(0, (scaled.height() - round(height * ratio)) // 2)
    cropped = scaled.copy(x, y, round(width * ratio), round(height * ratio))
    pixmap = QPixmap.fromImage(cropped)
    pixmap.setDevicePixelRatio(ratio)
    return _rounded_to(pixmap, float(theme.RADIUS["thumb"]))


class ThumbnailCache(QObject):
    """Row thumbnails by link, fetched once and kept in memory only (never on disk).

    ``get(url, size)`` returns the finished pixmap or ``None`` (the caller paints the
    placeholder) and starts the one fetch; ``ready`` is emitted when a picture arrives.
    The queue snapshot does not carry a thumbnail link yet, so nothing is fetched until
    a row has a ``thumbnail`` field.
    """

    ready = Signal()

    def __init__(self, fetcher: Fetcher | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fetcher = fetcher
        self._images: dict[str, QImage | None] = {}
        self._pixmaps: dict[tuple[str, int, int, float], QPixmap] = {}
        self._pending: set[str] = set()

    def get(self, url: str | None, width: int, height: int, ratio: float = 1.0) -> QPixmap | None:
        if not url:
            return None
        image = self._images.get(url)
        if image is None:
            if url not in self._pending and url not in self._images:
                self._start(url)
            return None
        key = (url, width, height, ratio)
        if key not in self._pixmaps:
            self._pixmaps[key] = row_thumbnail(image, width, height, ratio)
        return self._pixmaps[key]

    def _start(self, url: str) -> None:
        if self._fetcher is None:
            self._fetcher = qt_fetcher(self)
        self._pending.add(url)

        def deliver(data: bytes | None) -> None:
            self._pending.discard(url)
            image = QImage()
            if data and image.loadFromData(data) and not image.isNull():
                self._images[url] = image
                self._pixmaps = {k: v for k, v in self._pixmaps.items() if k[0] != url}
                self.ready.emit()
            else:
                self._images[url] = None

        self._fetcher(url, deliver)

    def clear(self) -> None:
        self._images.clear()
        self._pixmaps.clear()


def qt_fetcher(parent: QObject | None = None) -> Fetcher:
    """The real fetcher, built on ``QNetworkAccessManager``."""
    manager = QNetworkAccessManager(parent)

    def fetch(url: str, callback: Callable[[bytes | None], None]) -> None:
        qurl = QUrl(url)
        if qurl.scheme().lower() not in ("http", "https"):
            callback(None)
            return
        request = QNetworkRequest(qurl)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setTransferTimeout(15000)
        reply = manager.get(request)

        def done(reply: QNetworkReply = reply) -> None:
            ok = reply.error() == QNetworkReply.NetworkError.NoError
            data = bytes(reply.readAll()) if ok else None
            reply.deleteLater()
            callback(data)

        reply.finished.connect(done)

    return fetch


class ThumbnailLoader(QObject):
    """``load(url)`` then listen to ``changed``; ``pixmap`` is always usable."""

    changed = Signal(QPixmap)

    def __init__(self, fetcher: Fetcher | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fetcher = fetcher
        self._generation = 0
        self.pixmap: QPixmap = placeholder_pixmap()
        self.loaded = False

    def load(self, url: str | None) -> None:
        self._generation += 1
        self.loaded = False
        self.pixmap = placeholder_pixmap()
        if not url:
            return
        if self._fetcher is None:
            self._fetcher = qt_fetcher(self)
        generation = self._generation

        def deliver(data: bytes | None) -> None:
            if generation != self._generation:
                return
            image = QImage()
            if data and image.loadFromData(data) and not image.isNull():
                self.pixmap = _rounded(QPixmap.fromImage(image).scaledToWidth(
                    THUMB_WIDTH, Qt.TransformationMode.SmoothTransformation
                ))
                self.loaded = True
            else:
                self.pixmap = placeholder_pixmap("Preview unavailable")
            self.changed.emit(self.pixmap)

        self._fetcher(url, deliver)

    def cancel(self) -> None:
        self._generation += 1
