"""System tray icon, tray menu and "download finished" notifications."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

__all__ = [
    "MIN_NOTIFY_GAP",
    "STILL_RUNNING_TEXT",
    "TrayController",
    "tray_wanted",
]

MIN_NOTIFY_GAP = 1.0  # seconds between two desktop notifications
STILL_RUNNING_TEXT = "Elisium is still running here"
_NOTIFY_MS = 6000


def tray_wanted() -> bool:
    """True on a real desktop session that has a system tray.

    The offscreen and minimal Qt platforms (used by tests) never get a tray.
    """
    if QGuiApplication.platformName() in ("offscreen", "minimal"):
        return False
    return QSystemTrayIcon.isSystemTrayAvailable()


def _open_folder(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class TrayController(QObject):
    """Owns the tray icon for one :class:`MainWindow`.

    ``tray`` is the object that behaves like a ``QSystemTrayIcon`` (tests pass a
    fake); ``notifier(title, message)`` shows one desktop notification (default:
    the tray's own balloon); ``folder_opener(path)`` opens a folder; ``clock``
    and ``quit_fn`` are injectable so nothing real happens in tests.
    """

    def __init__(
        self,
        window: Any,
        *,
        tray: Any | None = None,
        notifier: Callable[[str, str], None] | None = None,
        folder_opener: Callable[[Path], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        quit_fn: Callable[[], None] | None = None,
        manage_quit_policy: bool = True,
    ) -> None:
        super().__init__(window)
        self.window = window
        self.tray = tray if tray is not None else QSystemTrayIcon(self)
        self._notifier = notifier or self._tray_notify
        self._open_folder = folder_opener or _open_folder
        self._clock = clock
        self._quit_fn = quit_fn or self._default_quit
        self._manage_quit_policy = manage_quit_policy
        self._previous_quit_policy: bool | None = None
        self._hint_shown = False
        self._notified: dict[int, str] = {}
        self._pending: list[tuple[str, str, Path | None]] = []
        self._last_sent = float("-inf")
        self._last_folder: Path | None = None
        self.sent: list[tuple[str, str]] = []  # every notification actually shown
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)

        self.tray.setIcon(self._icon())
        self._build_menu()
        self.tray.setToolTip(self.window.summary_label.text() or "No downloads")
        self.tray.activated.connect(self._on_activated)
        self.tray.messageClicked.connect(self._on_message_clicked)
        self.tray.show()
        if self._manage_quit_policy and QApplication.instance() is not None:
            self._previous_quit_policy = QApplication.quitOnLastWindowClosed()
            QApplication.setQuitOnLastWindowClosed(False)

    # -- construction ----------------------------------------------------
    def _icon(self) -> QIcon:
        icon = self.window.windowIcon()
        if icon.isNull():
            icon = QIcon.fromTheme(
                "folder-download",
                self.window.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown),
            )
        return icon

    def _build_menu(self) -> None:
        menu = QMenu(self.window)
        self.toggle_action = QAction("Hide window", menu)
        self.pause_all_action = QAction("Pause all", menu)
        self.resume_all_action = QAction("Resume all", menu)
        self.open_folder_action = QAction("Open download folder", menu)
        self.quit_action = QAction("Quit", menu)
        self.toggle_action.triggered.connect(self.toggle_window)
        self.pause_all_action.triggered.connect(self.window.pause_all)
        self.resume_all_action.triggered.connect(self.window.resume_all)
        self.open_folder_action.triggered.connect(self._open_download_folder)
        self.quit_action.triggered.connect(self.window.quit_app)
        for action in (self.toggle_action, self.pause_all_action, self.resume_all_action):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.open_folder_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)
        menu.aboutToShow.connect(self._refresh_menu)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self._refresh_menu()

    def _refresh_menu(self) -> None:
        self.toggle_action.setText(
            "Hide window" if self.window.isVisible() else "Show window"
        )

    # -- window ----------------------------------------------------------
    def toggle_window(self) -> None:
        if self.window.isVisible() and not self.window.isMinimized():
            self.window.hide()
        else:
            self.show_window()
        self._refresh_menu()

    def show_window(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _on_activated(self, reason: Any) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_window()

    def _open_download_folder(self) -> None:
        self._open_folder(Path(self.window.queue.output_dir))

    def update_tooltip(self, summary: str) -> None:
        self.tray.setToolTip(summary)

    def announce_hidden(self) -> None:
        """First time the window hides into the tray, say the app is still running."""
        if self._hint_shown:
            return
        self._hint_shown = True
        self._last_sent = self._clock()
        self._notifier("Elisium", STILL_RUNNING_TEXT)

    # -- notifications ---------------------------------------------------
    def on_event(self, event: dict[str, Any]) -> None:
        """Feed a queue event; a finished or failed item may raise a notification."""
        item = event.get("item")
        if event.get("type") != "state" or not isinstance(item, dict):
            return
        item_id, state = item.get("id"), item.get("state")
        if state not in ("done", "failed"):
            self._notified.pop(item_id, None)
            return
        if self._notified.get(item_id) == state:
            return
        self._notified[item_id] = state
        if not self.window.settings.notify_on_done or self.window.isActiveWindow():
            return
        name = item.get("title") or item.get("url") or "A download"
        file_path = item.get("file_path")
        folder = Path(file_path).parent if file_path else Path(self.window.queue.output_dir)
        if state == "done":
            self._enqueue("done", f"Download finished: {name}", folder)
        else:
            error = item.get("error") or {}
            why = error.get("message") or "Download failed."
            self._enqueue("failed", f"Download failed: {name}. {why}", folder)

    def notify_added(self, count: int) -> None:
        """Tell the user links arrived from outside (``elisium add``, a link)."""
        if count <= 0 or not self.window.settings.notify_on_done:
            return
        message = "Added 1 link" if count == 1 else f"Added {count} links"
        self._last_folder = None
        self.sent.append(("Elisium", message))
        self._notifier("Elisium", message)

    def _enqueue(self, kind: str, text: str, folder: Path | None) -> None:
        self._pending.append((kind, text, folder))
        wait = MIN_NOTIFY_GAP - (self._clock() - self._last_sent)
        if wait <= 0:
            self.flush()
        elif not self._timer.isActive():
            self._timer.start(int(wait * 1000) + 1)

    def flush(self) -> None:
        """Show everything that is waiting as one notification."""
        if not self._pending:
            return
        pending, self._pending = self._pending, []
        self._timer.stop()
        folder = next((f for _k, _t, f in reversed(pending) if f is not None), None)
        if len(pending) == 1:
            kind, text, _folder = pending[0]
            title = "Download finished" if kind == "done" else "Download failed"
            message = text.split(": ", 1)[1] if ": " in text else text
        else:
            done = sum(1 for k, _t, _f in pending if k == "done")
            failed = len(pending) - done
            parts = []
            if done:
                parts.append(f"{done} downloads finished" if done > 1 else "1 download finished")
            if failed:
                parts.append(f"{failed} downloads failed" if failed > 1 else "1 download failed")
            message = ", ".join(parts)
            title = "Downloads finished" if not failed else "Downloads finished or failed"
        self._last_sent = self._clock()
        self._last_folder = folder
        self.sent.append((title, message))
        self._notifier(title, message)

    def _tray_notify(self, title: str, message: str) -> None:
        self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, _NOTIFY_MS)

    def _on_message_clicked(self) -> None:
        folder = self._last_folder
        if folder is not None:
            self._open_folder(folder)

    # -- shutdown --------------------------------------------------------
    @staticmethod
    def _default_quit() -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def shutdown(self) -> None:
        """Remove the icon, restore the quit policy and end the application."""
        self._timer.stop()
        self.tray.hide()
        if self._manage_quit_policy and self._previous_quit_policy is not None:
            QApplication.setQuitOnLastWindowClosed(self._previous_quit_policy)
            self._previous_quit_policy = None
        self._quit_fn()
