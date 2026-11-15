"""The "Sign in" dialog: find the signed-in browser, use it, retry failed items.

It opens only from the existing entry points (the failed item's "Sign in..."
menu entry and the status-bar hint); it never opens by itself. Detection only
asks whether a signed-in Instagram session exists (see ``engine/browsers.py``).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from elisium_downloader.engine import browsers

from .quality_dialog import dialog_scale

__all__ = ["BROWSER_LABELS", "Detector", "SignInDialog", "browser_label"]

BROWSER_LABELS: dict[str, str] = {
    "firefox": "Firefox",
    "chrome": "Chrome",
    "chromium": "Chromium",
    "brave": "Brave",
    "edge": "Microsoft Edge",
    "vivaldi": "Vivaldi",
    "opera": "Opera",
}


def browser_label(key: str) -> str:
    return BROWSER_LABELS.get(key, key.title())


class Detector(QObject):
    """Runs a detect function on a worker thread and reports with ``done(list)``."""

    done = Signal(object)

    def __init__(self, fn: Callable[[], list[str]] | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fn = fn

    def start(self) -> None:
        # Look the default up at call time so tests can replace it.
        fn = self._fn or browsers.detect_default
        signal = self.done

        def work() -> None:
            try:
                found = [b for b in fn() if b in BROWSER_LABELS]
            except Exception:  # noqa: BLE001 - any failure means "not detected"
                found = []
            try:
                signal.emit(found)
            except RuntimeError:  # owner already destroyed
                pass

        threading.Thread(target=work, name="browser-detect", daemon=True).start()


class SignInDialog(QDialog):
    """Explain sign-in, offer the detected browser, retry the sign-in failures."""

    browserChosen = Signal(str)   # "Use this browser and retry": set the browser ...
    retryRequested = Signal()     # ... then retry every sign-in failure
    settingsRequested = Signal()  # "Open Settings > Accounts"

    def __init__(
        self,
        detect_fn: Callable[[], list[str]] | None = None,
        parent: QWidget | None = None,
        detected: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign in")
        self.setAccessibleName("Sign in")
        self.setModal(True)
        self.setMinimumWidth(round(440 * dialog_scale(self)))
        self._build()
        self._detector = Detector(detect_fn, self)
        self._detector.done.connect(self._on_detected)
        if detected is not None:
            self._on_detected(detected)
        else:
            self._detector.start()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        self.intro = QLabel(
            "Sign in to Instagram in your browser, then come back and retry."
        )
        self.intro.setWordWrap(True)
        self.intro.setAccessibleName("How to sign in")
        root.addWidget(self.intro)

        self.status_label = QLabel("Looking for a signed-in browser...")
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Detection result")
        self.status_label.setAccessibleDescription("Whether a signed-in browser was found.")
        root.addWidget(self.status_label)

        self.browser_combo = QComboBox()
        self.browser_combo.setAccessibleName("Signed-in browser")
        self.browser_combo.setAccessibleDescription("Browsers where Instagram looks signed in.")
        self.browser_combo.hide()
        root.addWidget(self.browser_combo)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.use_button = QPushButton("Use this browser and retry")
        self.use_button.setProperty("primary", True)
        self.use_button.setAccessibleName("Use this browser and retry")
        self.use_button.setAccessibleDescription(
            "Use the chosen browser for sign-in, then retry the downloads that needed it."
        )
        self.use_button.hide()
        self.retry_button = QPushButton("Retry")
        self.retry_button.setAccessibleName("Retry")
        self.retry_button.setAccessibleDescription(
            "Retry the downloads that failed because they needed a sign-in."
        )
        self.retry_button.hide()
        self.settings_button = QPushButton("Open Settings > Accounts")
        self.settings_button.setAccessibleName("Open Settings, Accounts")
        self.settings_button.setAccessibleDescription(
            "Choose a browser or a cookies.txt file yourself."
        )
        self.close_button = QPushButton("Close")
        self.close_button.setAccessibleName("Close")
        row.addStretch(1)
        for button in (self.use_button, self.retry_button, self.settings_button, self.close_button):
            row.addWidget(button)
        root.addLayout(row)

        self.use_button.clicked.connect(self._use)
        self.retry_button.clicked.connect(self._retry)
        self.settings_button.clicked.connect(self._settings)
        self.close_button.clicked.connect(self.reject)
        self.setTabOrder(self.browser_combo, self.use_button)
        self.setTabOrder(self.use_button, self.retry_button)
        self.setTabOrder(self.retry_button, self.settings_button)
        self.setTabOrder(self.settings_button, self.close_button)

    def _on_detected(self, found: Any) -> None:
        found = [b for b in (found or []) if b in BROWSER_LABELS]
        self.browser_combo.clear()
        for key in found:
            self.browser_combo.addItem(browser_label(key), key)
        has = bool(found)
        self.browser_combo.setVisible(has)
        self.use_button.setVisible(has)
        self.retry_button.setVisible(not has)
        if has:
            names = ", ".join(browser_label(b) for b in found)
            self.status_label.setText(f"Signed in to Instagram in: {names}.")
            self.use_button.setDefault(True)
            self.use_button.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self.status_label.setText(
                "No signed-in browser was found. Sign in to Instagram in your browser, "
                "or choose a browser or cookies.txt file in Settings."
            )
            self.retry_button.setDefault(True)
            self.retry_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def _use(self) -> None:
        key = self.browser_combo.currentData()
        if key:
            self.browserChosen.emit(str(key))
            self.retryRequested.emit()
            self.accept()

    def _retry(self) -> None:
        self.retryRequested.emit()
        self.accept()

    def _settings(self) -> None:
        self.settingsRequested.emit()
        self.accept()
