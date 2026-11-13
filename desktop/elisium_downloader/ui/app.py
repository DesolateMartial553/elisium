"""Build and run the application."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtWidgets import QApplication

from elisium_downloader.engine import paths
from elisium_downloader.engine.archive import Archive
from elisium_downloader.engine.history import History
from elisium_downloader.engine.queue import DownloadQueue

from . import settings as settings_mod
from .main_window import MainWindow

__all__ = ["create_app", "run"]


def create_app(
    argv: Sequence[str] | None = None,
    *,
    queue: DownloadQueue | None = None,
    data_path: str | os.PathLike[str] | None = None,
    output_path: str | os.PathLike[str] | None = None,
    temp_path: str | os.PathLike[str] | None = None,
    settings_path: str | os.PathLike[str] | None = None,
    version_fn: Callable[[], str | None] | None = None,
) -> tuple[QApplication, MainWindow, DownloadQueue]:
    """Return ``(app, window, queue)``; the window is not shown.

    With an injected *queue* and no *settings_path* nothing on disk is touched
    (default settings, not applied). Otherwise a real
    history, archive and queue are built (in the injected folders if given,
    else the real XDG ones) and the queue is started.
    """
    app = QApplication.instance() or QApplication(list(argv if argv is not None else sys.argv))
    app.setApplicationName("Elisium Downloader")
    injected = queue is not None
    if queue is None:
        data = Path(data_path) if data_path else paths.data_dir(create=True)
        data.mkdir(parents=True, exist_ok=True)
        output = Path(output_path) if output_path else paths.output_dir(create=True)
        temp = Path(temp_path) if temp_path else paths.temp_dir(create=True)
        history = History(data / "history.sqlite")
        archive = Archive(data / "archive.txt")
        queue = DownloadQueue(history, archive, output, temp)
        queue.start()
    if settings_path is None and not injected:
        settings_path = settings_mod.default_path()
    settings = settings_mod.load(settings_path) if settings_path else settings_mod.Settings()
    if settings_path or not injected:
        settings_mod.apply(settings, queue)
    window = MainWindow(
        queue, settings=settings, settings_path=settings_path, version_fn=version_fn
    )
    return app, window, queue


def run(argv: Sequence[str] | None = None) -> int:
    app, window, queue = create_app(argv)
    window.show()
    try:
        return app.exec()
    finally:
        queue.stop()
        queue.history.close()
