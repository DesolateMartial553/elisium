"""Run a (slow, blocking) link probe off the GUI thread."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

from elisium_downloader.engine.errors import ErrorInfo, explain
from elisium_downloader.engine.runner import ProbeError

__all__ = ["ProbeWorker"]

# A cancelled probe cannot be interrupted (it is a blocking subprocess call), so
# its thread is parked here until it ends; destroying a running QThread aborts.
_parked: set[QThread] = set()


class _ProbeThread(QThread):
    done = Signal(int, dict)
    error = Signal(int, object, str)

    def __init__(self, token: int, probe: Callable[[], dict[str, Any]]) -> None:
        super().__init__()
        self._token = token
        self._probe = probe

    def run(self) -> None:
        try:
            info = self._probe()
            if not isinstance(info, dict):
                raise TypeError("probe did not return a dict")
        except ProbeError as exc:
            self.error.emit(self._token, exc.info, exc.raw)
        except Exception as exc:  # noqa: BLE001 - never let a worker thread die silently
            text = str(exc)
            self.error.emit(self._token, explain(text), text)
        else:
            self.done.emit(self._token, info)


class ProbeWorker(QObject):
    """Probe one URL on a ``QThread``.

    ``finished(dict)`` or ``failed(ErrorInfo, raw)`` is emitted on the GUI
    thread. ``probe`` is called as ``probe(url)``; inject a fake in tests.
    :meth:`cancel` (or starting again) makes any late result be ignored.
    """

    finished = Signal(dict)
    failed = Signal(object, str)

    def __init__(
        self,
        probe: Callable[[str], dict[str, Any]],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._probe = probe
        self._token = 0
        self._thread: _ProbeThread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None

    def start(self, url: str) -> None:
        """Begin probing *url*, dropping the result of any earlier probe."""
        self.cancel()
        self._token += 1
        thread = _ProbeThread(self._token, lambda: self._probe(url))
        thread.done.connect(self._on_done)
        thread.error.connect(self._on_error)
        thread.finished.connect(self._reap)
        self._thread = thread
        _parked.add(thread)
        thread.start()

    def cancel(self) -> None:
        """Ignore the running probe's result (the thread ends on its own)."""
        self._token += 1
        self._thread = None

    @Slot()
    def _reap(self) -> None:
        thread = self.sender()
        if not isinstance(thread, _ProbeThread):
            return
        _parked.discard(thread)
        thread.deleteLater()
        if self._thread is thread:
            self._thread = None

    def _on_done(self, token: int, info: dict) -> None:
        if token != self._token:
            return
        self._thread = None
        self.finished.emit(info)

    def _on_error(self, token: int, info: ErrorInfo, raw: str) -> None:
        if token != self._token:
            return
        self._thread = None
        self.failed.emit(info, raw)
