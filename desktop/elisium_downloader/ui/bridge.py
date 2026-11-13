"""Marshal queue events from worker threads onto the GUI thread."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Qt, Signal, Slot

from elisium_downloader.engine.queue import DownloadQueue

__all__ = ["QueueBridge"]


class QueueBridge(QObject):
    """Re-emit every queue event as the Qt signal :attr:`event`.

    Queue listeners run on worker threads with the queue lock held, so the
    listener does nothing except emit :attr:`_raw`. That signal is connected to
    :meth:`_relay` with a queued connection, so ``_relay`` (and therefore every
    receiver of :attr:`event`) runs on this object's (the GUI) thread.
    """

    event = Signal(dict)
    _raw = Signal(dict)

    def __init__(self, queue: DownloadQueue, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue = queue
        self._raw.connect(self._relay, Qt.ConnectionType.QueuedConnection)
        queue.add_listener(self._on_queue_event)

    def _on_queue_event(self, event: dict[str, Any]) -> None:
        # Worker thread, queue lock held: emit only.
        self._raw.emit(event)

    @Slot(dict)
    def _relay(self, event: dict[str, Any]) -> None:
        self.event.emit(event)

    def close(self) -> None:
        """Stop listening to the queue."""
        self._queue.remove_listener(self._on_queue_event)
