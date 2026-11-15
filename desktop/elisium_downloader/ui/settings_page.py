"""The Settings page: saved immediately and applied to the queue live."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from elisium_downloader.engine.presets import PRESETS
from elisium_downloader.engine.queue import MAX_CONCURRENCY, DownloadQueue

from . import settings as settings_mod
from .settings import Settings
from .sign_in_dialog import Detector, browser_label

__all__ = ["SettingsPage", "fetch_ytdlp_version"]

# Dropdown order; the value is what yt-dlp's --cookies-from-browser accepts.
_COOKIE_BROWSER_LABELS: tuple[tuple[str, str], ...] = (
    ("Firefox", "firefox"),
    ("Chrome", "chrome"),
    ("Chromium", "chromium"),
    ("Brave", "brave"),
    ("Microsoft Edge", "edge"),
    ("Vivaldi", "vivaldi"),
    ("Opera", "opera"),
)


def fetch_ytdlp_version(ytdlp: str = "yt-dlp") -> str | None:
    """Return the output of ``yt-dlp --version``, or ``None`` if it cannot run."""
    try:
        done = subprocess.run(
            [ytdlp, "--version"], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = done.stdout.strip()
    return text if done.returncode == 0 and text else None


class _PageScroll(QScrollArea):
    """A scroll area whose content grows when wrapped labels need more height.

    QScrollArea sizes its page before the scroll bar appears; once the bar narrows the
    viewport, wrapped text needs more lines and would be clipped. So the page's minimum
    height is re-derived from the layout for the width it really gets.
    """

    def __init__(self) -> None:
        super().__init__()
        self.viewport().installEventFilter(self)

    def _fit(self) -> None:
        page = self.widget()
        if page is not None and page.layout() is not None:
            page.setMinimumHeight(page.layout().totalHeightForWidth(self.viewport().width()))

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._fit()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.viewport() and event.type() == QEvent.Type.Resize:
            self._fit()
        return super().eventFilter(watched, event)


class _WrapLabel(QLabel):
    """A wrapping label that always keeps the height its wrapped text needs."""

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        if self.wordWrap() and self.width() > 0:
            need = self.heightForWidth(self.width())
            if need > 0 and self.minimumHeight() != need:
                self.setMinimumHeight(need)


class _VersionSignal(QObject):
    done = Signal(object)


class SettingsPage(QWidget):
    settingsChanged = Signal(object)

    def __init__(
        self,
        settings: Settings,
        queue: DownloadQueue,
        path: str | Path | None = None,
        version_fn: Callable[[], str | None] | None = None,
        parent: QWidget | None = None,
        detect_fn: Callable[[], list[str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.queue = queue
        self.path = Path(path) if path is not None else None
        self._version_fn = version_fn or fetch_ytdlp_version
        self._detect_fn = detect_fn
        self.detected_browsers: list[str] = []
        self._loading = True
        self._build_ui()
        self._fit_to_font()
        self._load_controls()
        self._loading = False
        self._start_version_check()
        self._start_detection()

    # -- construction ----------------------------------------------------
    def _build_ui(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        scroll = _PageScroll()
        scroll.setObjectName("settingsScroll")
        self._scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        page.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        def card(heading: str) -> QFormLayout:
            frame = QFrame()
            frame.setProperty("card", True)
            box = QVBoxLayout(frame)
            box.setContentsMargins(20, 16, 20, 18)
            box.setSpacing(12)
            label = QLabel(heading)
            label.setObjectName("cardTitle")
            box.addWidget(label)
            form = QFormLayout()
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setVerticalSpacing(12)
            form.setHorizontalSpacing(24)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            box.addLayout(form)
            outer.addWidget(frame)
            return form

        form = card("Downloads")
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, MAX_CONCURRENCY)
        self._pad_spin(self.concurrency_spin)
        self._describe(self.concurrency_spin, "Parallel downloads",
                       "How many downloads run at the same time, from 1 to 5.")
        form.addRow(self._label("Parallel downloads", self.concurrency_spin), self.concurrency_spin)

        self.limit_check = QCheckBox("Limit speed")
        self._describe(self.limit_check, "Limit speed",
                       "Turn on to cap the download speed.")
        self.limit_spin = QDoubleSpinBox()
        self._pad_spin(self.limit_spin)
        self.limit_spin.setRange(0.1, 100000)
        self.limit_spin.setDecimals(1)
        self.limit_spin.setValue(2)
        self._describe(self.limit_spin, "Speed limit amount",
                       "The top download speed, in the unit chosen next to it.")
        self.limit_unit = QComboBox()
        self.limit_unit.addItem("KB/s", "K")
        self.limit_unit.addItem("MB/s", "M")
        self.limit_unit.setCurrentIndex(1)
        self._describe(self.limit_unit, "Speed limit unit",
                       "Kilobytes or megabytes per second.")
        limit_row = QHBoxLayout()
        limit_row.setSpacing(12)
        limit_row.addWidget(self.limit_check)
        limit_row.addWidget(self.limit_spin)
        limit_row.addWidget(self.limit_unit)
        limit_row.addStretch(1)
        form.addRow(self._label("Speed limit", self.limit_spin), limit_row)

        self.preset_combo = QComboBox()
        for preset in PRESETS.values():
            self.preset_combo.addItem(preset.label, preset.id)
        self._describe(self.preset_combo, "Default quality",
                       "The quality used for new downloads.")
        form.addRow(self._label("Default quality", self.preset_combo), self.preset_combo)

        form = card("Accounts")
        self.detect_row = QWidget()
        detect_layout = QHBoxLayout(self.detect_row)
        detect_layout.setContentsMargins(0, 0, 0, 0)
        detect_layout.setSpacing(12)
        self.detect_label = _WrapLabel("")
        self.detect_label.setWordWrap(True)
        self._describe(
            self.detect_label, "Signed-in browser found",
            "A browser where Instagram looks signed in. Only the fact that you are "
            "signed in was checked, never your cookies.",
        )
        self.detect_button = QPushButton("Use")
        self.detect_button.setProperty("primary", True)
        detect_layout.addWidget(self.detect_label, 1)
        detect_layout.addWidget(self.detect_button)
        form.addRow(self.detect_row)
        form.setRowVisible(self.detect_row, False)
        self._accounts_form = form
        self.cookies_combo = QComboBox()
        self.cookies_combo.addItem("Not signed in", None)
        for label, key in _COOKIE_BROWSER_LABELS:
            self.cookies_combo.addItem(label, key)
        self._describe(
            self.cookies_combo, "Signed-in browser",
            "The browser Elisium reads cookies from when a site needs a sign-in, "
            "such as Instagram stories. Choose Not signed in to turn this off.",
        )
        form.addRow(self._label("Browser", self.cookies_combo), self.cookies_combo)

        self.cookies_file_edit = QLineEdit()
        self.cookies_file_edit.setReadOnly(True)
        self.cookies_file_edit.setPlaceholderText("No file chosen")
        self._describe(
            self.cookies_file_edit, "cookies.txt file",
            "An optional cookies.txt file exported from a browser.",
        )
        self.cookies_choose_button = QPushButton("Choose...")
        self._describe(
            self.cookies_choose_button, "Choose cookies.txt file",
            "Pick a cookies.txt file to use instead of the browser.",
        )
        self.cookies_clear_button = QPushButton("Clear")
        self._describe(
            self.cookies_clear_button, "Clear cookies.txt file",
            "Stop using the cookies.txt file.",
        )
        file_row = QHBoxLayout()
        file_row.setSpacing(12)
        file_row.addWidget(self.cookies_file_edit, 1)
        file_row.addWidget(self.cookies_choose_button)
        file_row.addWidget(self.cookies_clear_button)
        form.addRow(self._label("cookies.txt file", self.cookies_choose_button), file_row)

        self.cookies_help = _WrapLabel(
            "Needed for Instagram stories and private posts. "
            "Elisium only reads cookies for the site you download from."
        )
        self.cookies_help.setWordWrap(True)
        self._describe(
            self.cookies_help, "About signing in",
            "Why Elisium asks for a browser or a cookies.txt file.",
        )
        form.addRow("", self.cookies_help)

        form = card("Notifications and tray")
        self.notify_check = QCheckBox("Notify when a download finishes")
        self._describe(self.notify_check, "Notify when a download finishes",
                       "Show a message when a download is done.")
        form.addRow("", self.notify_check)
        self.tray_check = QCheckBox("Keep running in the tray when closed")
        self._describe(self.tray_check, "Keep running in the tray when closed",
                       "When on, closing the window hides it to the tray and downloads carry on.")
        form.addRow("", self.tray_check)

        form = card("Appearance")
        self.appearance_combo = QComboBox()
        for label, key in (("System", "system"), ("Night", "night"), ("Day", "day")):
            self.appearance_combo.addItem(label, key)
        self._describe(self.appearance_combo, "Appearance",
                       "Follow the system light or dark setting, or always use Night or Day.")
        form.addRow(self._label("Appearance", self.appearance_combo), self.appearance_combo)
        self.motion_check = QCheckBox("Reduce motion")
        self._describe(self.motion_check, "Reduce motion",
                       "Turn off the glow breathing and the busy bar. Nothing else changes.")
        form.addRow("", self.motion_check)

        form = card("Folders and about")
        self.folder_label = _WrapLabel(str(self.queue.output_dir))
        self.folder_label.setWordWrap(True)
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._describe(self.folder_label, "Download folder",
                       "The folder where finished files are saved.")
        self.open_folder_button = QPushButton("Open")
        self._describe(self.open_folder_button, "Open download folder",
                       "Open the download folder in your file manager.")
        # The path label sits directly in the form (a wrapped label nested in a
        # box layout gets too little height at large text sizes).
        form.addRow(self._label("Download folder", self.open_folder_button), self.folder_label)
        form.addRow("", self.open_folder_button)

        self.version_label = QLabel("checking...")
        self._describe(self.version_label, "yt-dlp version",
                       "The installed version of the yt-dlp program.")
        form.addRow(self._label("yt-dlp version", self.version_label), self.version_label)
        self.update_hint = _WrapLabel(
            "If Instagram stops working, update yt-dlp (pacman -Syu / pip)"
        )
        self.update_hint.setWordWrap(True)
        self._describe(self.update_hint, "About updating yt-dlp",
                       "What to do when Instagram downloads stop working.")
        form.addRow("", self.update_hint)

        self.open_data_button = QPushButton("Open data folder")
        self._describe(self.open_data_button, "Open data folder",
                       "Open the folder that holds the history and archive.")
        form.addRow("", self.open_data_button)
        outer.addStretch(1)
        # One label column width for every card, so the fields line up.
        labels = [w for w in body.findChildren(QLabel)
                  if w.buddy() is not None]
        if labels:
            widest = max(w.sizeHint().width() for w in labels)
            for w in labels:
                w.setMinimumWidth(widest)

        for signal in (
            self.concurrency_spin.valueChanged, self.limit_check.toggled,
            self.limit_spin.valueChanged, self.limit_unit.currentIndexChanged,
            self.preset_combo.currentIndexChanged, self.cookies_combo.currentIndexChanged,
            self.notify_check.toggled,
            self.tray_check.toggled, self.appearance_combo.currentIndexChanged,
            self.motion_check.toggled,
        ):
            signal.connect(self._changed)
        self.open_folder_button.clicked.connect(self.open_download_folder)
        self.open_data_button.clicked.connect(self.open_data_folder)
        self.detect_button.clicked.connect(self.use_detected_browser)
        self.cookies_choose_button.clicked.connect(self.choose_cookies_file)
        self.cookies_clear_button.clicked.connect(self.clear_cookies_file)

        self.setTabOrder(self.concurrency_spin, self.limit_check)
        self.setTabOrder(self.limit_check, self.limit_spin)
        self.setTabOrder(self.limit_spin, self.limit_unit)
        self.setTabOrder(self.limit_unit, self.preset_combo)
        self.setTabOrder(self.preset_combo, self.detect_button)
        self.setTabOrder(self.detect_button, self.cookies_combo)
        self.setTabOrder(self.cookies_combo, self.cookies_choose_button)
        self.setTabOrder(self.cookies_choose_button, self.cookies_clear_button)
        self.setTabOrder(self.cookies_clear_button, self.notify_check)
        self.setTabOrder(self.notify_check, self.tray_check)
        self.setTabOrder(self.tray_check, self.appearance_combo)
        self.setTabOrder(self.appearance_combo, self.motion_check)
        self.setTabOrder(self.motion_check, self.open_folder_button)
        self.setTabOrder(self.open_folder_button, self.open_data_button)

    @staticmethod
    def _pad_spin(spin: QSpinBox | QDoubleSpinBox) -> None:
        """Style sheet padding does not reach a spin box's text; indent it so the
        number does not sit against the field's left edge."""
        spin.lineEdit().setTextMargins(10, 0, 0, 0)

    @staticmethod
    def _describe(widget: QWidget, name: str, description: str) -> None:
        widget.setAccessibleName(name)
        widget.setAccessibleDescription(description)

    @staticmethod
    def _label(text: str, buddy: QWidget) -> QLabel:
        label = QLabel(text)
        label.setBuddy(buddy)
        return label

    def _fit_to_font(self) -> None:
        """Give the number boxes room for their digits and arrows at any text size."""
        fm = self.fontMetrics()
        for spin, sample in ((self.concurrency_spin, "00"), (self.limit_spin, "00000.0")):
            spin.setMinimumWidth(fm.horizontalAdvance(sample) + 120)
            # The style sheet's fixed min-height must not squeeze the number field at big text.
            spin.setMinimumHeight(max(42, spin.lineEdit().minimumSizeHint().height() + 8))
        # A path label this wide makes the form wrap it under its caption when short of room.
        self.folder_label.setMinimumWidth(fm.horizontalAdvance("M") * 16)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if hasattr(self, "limit_spin") and event.type() in (
            QEvent.Type.FontChange, QEvent.Type.ApplicationFontChange
        ):
            self._fit_to_font()

    # -- state <-> controls ----------------------------------------------
    def _load_controls(self) -> None:
        s = self.settings
        self.concurrency_spin.setValue(s.concurrency)
        self.limit_check.setChecked(s.speed_limit is not None)
        if s.speed_limit:
            unit = s.speed_limit[-1] if s.speed_limit[-1] in "KMG" else "K"
            number = float(s.speed_limit[:-1] if s.speed_limit[-1] in "KMG" else s.speed_limit)
            if unit == "G":
                number, unit = number * 1024, "M"
            self.limit_spin.setValue(number)
            self.limit_unit.setCurrentIndex(0 if unit == "K" else 1)
        self.preset_combo.setCurrentIndex(max(0, self.preset_combo.findData(s.preset_id)))
        self.cookies_combo.setCurrentIndex(max(0, self.cookies_combo.findData(s.cookies_browser)))
        self.cookies_file_edit.setText(s.cookies_file or "")
        self.cookies_file_edit.setToolTip(s.cookies_file or "")
        self.notify_check.setChecked(s.notify_on_done)
        self.tray_check.setChecked(s.close_to_tray)
        self.appearance_combo.setCurrentIndex(max(0, self.appearance_combo.findData(s.appearance)))
        self.motion_check.setChecked(s.reduce_motion)
        self.limit_spin.setEnabled(self.limit_check.isChecked())
        self.limit_unit.setEnabled(self.limit_check.isChecked())
        self._update_detect_row()

    def _speed_text(self) -> str | None:
        if not self.limit_check.isChecked():
            return None
        number = self.limit_spin.value()
        text = f"{number:.0f}" if number == int(number) else f"{number:.1f}"
        return text + self.limit_unit.currentData()

    def _changed(self, *_: object) -> None:
        self.limit_spin.setEnabled(self.limit_check.isChecked())
        self.limit_unit.setEnabled(self.limit_check.isChecked())
        if self._loading:
            return
        self.settings = Settings(
            concurrency=self.concurrency_spin.value(),
            speed_limit=self._speed_text(),
            preset_id=self.preset_combo.currentData(),
            notify_on_done=self.notify_check.isChecked(),
            close_to_tray=self.tray_check.isChecked(),
            appearance=self.appearance_combo.currentData(),
            reduce_motion=self.motion_check.isChecked(),
            cookies_browser=self.cookies_combo.currentData(),
            cookies_file=self.cookies_file_edit.text().strip() or None,
        )
        if self.path is not None:
            try:
                settings_mod.save(self.settings, self.path)
            except OSError:
                pass
        settings_mod.apply(self.settings, self.queue)
        self._update_detect_row()
        self.settingsChanged.emit(self.settings)

    # -- accounts --------------------------------------------------------
    def choose_cookies_file(self) -> None:
        """Ask for a ``cookies.txt`` file and use it (never opened by us)."""
        start = self.cookies_file_edit.text().strip() or str(Path.home())
        chosen, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose cookies.txt",
            start,
            "Cookies files (cookies.txt *.txt);;All files (*)",
        )
        if chosen:
            self.cookies_file_edit.setText(chosen)
            self.cookies_file_edit.setToolTip(chosen)
            self._changed()

    def clear_cookies_file(self) -> None:
        """Stop using a ``cookies.txt`` file."""
        if self.cookies_file_edit.text():
            self.cookies_file_edit.clear()
            self.cookies_file_edit.setToolTip("")
            self._changed()

    def _start_detection(self) -> None:
        """Look for a signed-in browser off the UI thread; never blocks startup."""
        self._detector = Detector(self._detect_fn, self)
        self._detector.done.connect(self._on_detected)
        self._detector.start()

    def _on_detected(self, found: object) -> None:
        self.detected_browsers = [str(b) for b in (found or [])]  # type: ignore[union-attr]
        self._update_detect_row()

    def _update_detect_row(self) -> None:
        """Offer the detected browser only while no browser or file is configured."""
        configured = bool(self.settings.cookies_browser or self.settings.cookies_file)
        show = bool(self.detected_browsers) and not configured
        if show:
            name = browser_label(self.detected_browsers[0])
            self.detect_label.setText(f"Signed in to Instagram in {name}.")
            self.detect_button.setText(f"Use {name}")
            self._describe(
                self.detect_button, f"Use {name}",
                f"Use the cookies of {name} when a site needs a sign-in.",
            )
        self._accounts_form.setRowVisible(self.detect_row, show)

    def use_detected_browser(self) -> None:
        """Select the detected browser (same path as choosing it in the dropdown)."""
        if self.detected_browsers:
            self.use_browser(self.detected_browsers[0])

    def use_browser(self, key: str) -> None:
        """Select *key* in the dropdown: persisted and applied like any other choice."""
        index = self.cookies_combo.findData(key)
        if index < 0:
            return
        if self.cookies_combo.currentIndex() == index:
            self._changed()
        else:
            self.cookies_combo.setCurrentIndex(index)  # fires _changed

    def show_accounts(self) -> None:
        """Scroll the Accounts section into view and focus the browser dropdown.

        This is where the sign-in error's suggested action leads: the user
        picks the browser they are signed in to, or a ``cookies.txt`` file.
        """
        self._scroll.ensureWidgetVisible(self.cookies_combo, 0, 24)
        self.cookies_combo.setFocus(Qt.FocusReason.OtherFocusReason)

    # -- yt-dlp version --------------------------------------------------
    def _start_version_check(self) -> None:
        self._signal = _VersionSignal(self)
        self._signal.done.connect(self._show_version)
        signal, fn = self._signal, self._version_fn

        def work() -> None:
            try:
                result = fn()
            except Exception:  # noqa: BLE001 - any failure means "not found"
                result = None
            try:
                signal.done.emit(result)
            except RuntimeError:  # page already destroyed
                pass

        self._thread = threading.Thread(target=work, name="ytdlp-version", daemon=True)
        self._thread.start()

    def _show_version(self, version: object) -> None:
        self.version_label.setText(str(version) if version else "yt-dlp not found")

    # -- folders ---------------------------------------------------------
    def open_download_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.queue.output_dir)))

    def open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.queue.archive.path.parent)))
