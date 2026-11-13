"""Fetch and scale a video thumbnail; never cached on disk."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

__all__ = ["THUMB_WIDTH", "ThumbnailLoader", "placeholder_pixmap", "qt_fetcher"]

THUMB_WIDTH = 240
_THUMB_HEIGHT = 135

# fetcher(url, callback): call callback(bytes) on success or callback(None) on failure.
Fetcher = Callable[[str, Callable[[bytes | None], None]], None]


def placeholder_pixmap(text: str = "No preview") -> QPixmap:
    """A neutral grey box shown while loading or when the image failed."""
    pixmap = QPixmap(THUMB_WIDTH, _THUMB_HEIGHT)
    pixmap.fill(QColor("#8a8f98"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#ffffff"))
    font = QFont()
    font.setPointSize(11)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), int(Qt.AlignmentFlag.AlignCenter), text)
    painter.end()
    return pixmap


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
                self.pixmap = QPixmap.fromImage(image).scaledToWidth(
                    THUMB_WIDTH, Qt.TransformationMode.SmoothTransformation
                )
                self.loaded = True
            else:
                self.pixmap = placeholder_pixmap("Preview unavailable")
            self.changed.emit(self.pixmap)

        self._fetcher(url, deliver)

    def cancel(self) -> None:
        self._generation += 1
