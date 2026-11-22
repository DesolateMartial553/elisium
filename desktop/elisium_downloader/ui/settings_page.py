"""The Settings page: grouped lists on ``surface``, one setting per row, saved immediately.

Night shelf: each group is a ``surface`` card (radius 16) with a 13/600 ``muted`` heading;
each row has its label (14/600) and helper text (13 ``faint``) on the left and its control on
the right. A row whose control no longer fits beside its text stacks the control underneath
(so 200% text never clips).
"""

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
    QFrame,
    QGridLayout,
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
        self.on_width: Callable[[int], None] | None = None  # re-arrange rows for this width
        self.viewport().installEventFilter(self)

    def _fit(self) -> None:
        page = self.widget()
        if self.on_width is not None:
            self.on_width(self.viewport().width())
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


class _ToggleLabel(QLabel):
    """A row's name that also toggles its switch when clicked (the switch has no text of its own)."""

    def __init__(self, text: str, check: QCheckBox | None = None) -> None:
        super().__init__(text)
        self._check = check
        if check is not None:
            self.setBuddy(check)

    def mouseReleaseEvent(self, event: object) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)  # type: ignore[arg-type]
        if self._check is not None and self._check.isEnabled():
            self._check.toggle()


class _SettingRow(QWidget):
    """One setting: name and helper text on the left, the control on the right.

    ``name`` may be text or a ready label. ``stack(True)`` puts the control under the text
    instead of beside it. ``rule`` draws the 1 px ``raised`` line under the row.
    """

    MIN_TEXT_EM = 20  # the text column never gets narrower than this many "M" widths

    def __init__(self, name: str | QLabel, helper: QLabel | None, controls: list[QWidget],
                 buddy: QWidget | None = None, rule: bool = True) -> None:
        super().__init__()
        self.setObjectName("settingRow")
        if isinstance(name, QLabel):
            self.name = name
        else:
            self.name = QLabel(name)
        self.name.setObjectName("settingName")
        self.name.setWordWrap(True)
        top = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        self.name.setAlignment(top)
        if buddy is not None and self.name.buddy() is None:
            self.name.setBuddy(buddy)
        self.helper = helper
        if helper is not None:
            helper.setObjectName("helper")
            helper.setWordWrap(True)
            helper.setAlignment(top)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(16, 10, 16, 10)
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.name)
        if helper is not None:
            text.addWidget(helper)
        self._grid.addLayout(text, 0, 0)
        self.control = QWidget()
        box = QHBoxLayout(self.control)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        for widget in controls:
            box.addWidget(widget, 1 if isinstance(widget, QLineEdit) else 0)
        self._grid.addWidget(self.control, 0, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._grid.setColumnStretch(0, 1)
        self.stacked = False
        self._has_controls = bool(controls)
        self.rule: QFrame | None = None
        if rule:
            self.rule = QFrame()
            self.rule.setObjectName("settingRule")
            self.rule.setFixedHeight(1)
            self._grid.addWidget(self.rule, 3, 0, 1, 2)
        if not controls:
            self.control.hide()

    def wants_stack(self, width: int) -> bool:
        """True when the control does not fit beside the text at this row *width*."""
        if not self._has_controls:
            return False
        em = self.fontMetrics().horizontalAdvance("M")
        need = self.MIN_TEXT_EM * em + self._grid.horizontalSpacing() + self.control.sizeHint().width() + 32
        return width < need

    def stack(self, stacked: bool) -> None:
        if stacked == self.stacked:
            return
        self.stacked = stacked
        self._grid.removeWidget(self.control)
        if stacked:
            self._grid.addWidget(self.control, 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
        else:
            self._grid.addWidget(self.control, 0, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


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
        outer.setContentsMargins(0, 0, 8, 0)
        outer.setSpacing(12)
        self.rows: list[_SettingRow] = []
        self.groups: dict[str, QFrame] = {}
        scroll.on_width = self._arrange

        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        def group(heading: str, rows: list[_SettingRow]) -> None:
            frame = QFrame()
            frame.setProperty("card", True)
            frame.setObjectName(f"group-{heading}")
            box = QVBoxLayout(frame)
            box.setContentsMargins(0, 8, 0, 4)
            box.setSpacing(0)
            label = QLabel(heading)
            label.setObjectName("groupTitle")
            label.setContentsMargins(16, 6, 16, 2)
            box.addWidget(label)
            for row in rows:
                box.addWidget(row)
            if rows and rows[-1].rule is not None:
                rows[-1].rule.hide()
            self.rows.extend(rows)
            self.groups[heading] = frame
            outer.addWidget(frame)

        # -- Downloads -----------------------------------------------------
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, MAX_CONCURRENCY)
        self._pad_spin(self.concurrency_spin)
        self._describe(self.concurrency_spin, "Parallel downloads",
                       "How many downloads run at the same time, from 1 to 5.")
        parallel = _SettingRow("Parallel downloads", self._helper("How many run at the same time"),
                               [self.concurrency_spin], self.concurrency_spin)

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
        speed = _SettingRow("Speed limit", self._helper("Keeps the rest of your connection free"),
                            [self.limit_check, self.limit_spin, self.limit_unit], self.limit_spin)

        self.preset_combo = QComboBox()
        for preset in PRESETS.values():
            self.preset_combo.addItem(preset.label, preset.id)
        self._describe(self.preset_combo, "Default quality",
                       "The quality used for new downloads.")
        quality = _SettingRow("Default quality", self._helper("Used for new links"),
                              [self.preset_combo], self.preset_combo)
        self.faster_combo = QComboBox()
        self.faster_combo.addItem("Auto", "auto")
        self.faster_combo.addItem("Off", "off")
        self._describe(self.faster_combo, "Faster downloads",
                       "Auto looks each link up once. Turn off if downloads fail.")
        faster = _SettingRow("Faster downloads",
                             self._helper("Auto looks each link up once. Turn off if downloads fail."),
                             [self.faster_combo], self.faster_combo)
        group("Downloads", [parallel, speed, quality, faster])

        # -- Photos and music ----------------------------------------------
        self.photo_mode_combo = QComboBox()
        for label, key in (("Photos, song and video", "video"),
                           ("Photos and song only", "song"),
                           ("Photos only", "photos")):
            self.photo_mode_combo.addItem(label, key)
        self._describe(self.photo_mode_combo, "Photo posts with a song",
                       "What to save from a photo post that has a song: the photos, the song "
                       "and a video of them together; the photos and the song; or the photos only.")
        photo_mode = _SettingRow(
            "Photo posts with a song",
            self._helper("The video needs ffmpeg; without it the photos and the song are kept"),
            [self.photo_mode_combo], self.photo_mode_combo)
        self.song_length_combo = QComboBox()
        for label, key in (("Post's snippet", "snippet"), ("Full song", "full")):
            self.song_length_combo.addItem(label, key)
        self._describe(self.song_length_combo, "Song length",
                       "Cut the song to the part the post plays, or keep the whole song.")
        song_length = _SettingRow("Song length", self._helper("Only the part the post plays, or all of it"),
                                  [self.song_length_combo], self.song_length_combo, rule=False)
        group("Photos and music", [photo_mode, song_length])

        # -- Accounts ------------------------------------------------------
        self.detect_label = _WrapLabel("")
        self.detect_label.setWordWrap(True)
        self._describe(
            self.detect_label, "Signed-in browser found",
            "A browser where Instagram looks signed in. Only the fact that you are "
            "signed in was checked, never your cookies.",
        )
        self.detect_button = QPushButton("Use")
        self.detect_button.setProperty("primary", True)
        detect = _SettingRow(self.detect_label, None, [self.detect_button])
        self.detect_row = detect
        detect.hide()
        self.cookies_combo = QComboBox()
        self.cookies_combo.addItem("Not signed in", None)
        for label, key in _COOKIE_BROWSER_LABELS:
            self.cookies_combo.addItem(label, key)
        self._describe(
            self.cookies_combo, "Signed-in browser",
            "The browser Elisium reads cookies from when a site needs a sign-in, "
            "such as Instagram stories. Choose Not signed in to turn this off.",
        )
        self.cookies_help = _WrapLabel(
            "Needed for Instagram stories and private posts. "
            "Elisium only reads cookies for the site you download from."
        )
        self.cookies_help.setWordWrap(True)
        self._describe(
            self.cookies_help, "About signing in",
            "Why Elisium asks for a browser or a cookies.txt file.",
        )
        browser = _SettingRow("Browser", self.cookies_help, [self.cookies_combo], self.cookies_combo)

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
        cookies = _SettingRow("cookies.txt file", self._helper("Optional, used instead of the browser"),
                              [self.cookies_file_edit, self.cookies_choose_button,
                               self.cookies_clear_button], self.cookies_choose_button)
        self.cookies_file_edit.setMinimumWidth(self.fontMetrics().horizontalAdvance("M") * 12)
        group("Accounts", [detect, browser, cookies])

        # -- Appearance ----------------------------------------------------
        self.notify_check = self._switch("Notify when a download finishes",
                                         "Show a message when a download is done.")
        notify = _SettingRow(_ToggleLabel("Notify when a download finishes", self.notify_check),
                             None, [self.notify_check])
        self.tray_check = self._switch("Keep running in the tray when closed",
                                       "When on, closing the window hides it to the tray and "
                                       "downloads carry on.")
        tray = _SettingRow(_ToggleLabel("Keep running in the tray when closed", self.tray_check),
                           self._helper("Downloads carry on while the window is hidden"),
                           [self.tray_check])
        self.appearance_combo = QComboBox()
        for label, key in (("System", "system"), ("Night", "night"), ("Day", "day")):
            self.appearance_combo.addItem(label, key)
        self._describe(self.appearance_combo, "Appearance",
                       "Follow the system light or dark setting, or always use Night or Day.")
        theme_row = _SettingRow("Theme", self._helper("System follows your desktop's light or dark setting"),
                                [self.appearance_combo], self.appearance_combo)
        self.motion_check = self._switch("Reduce motion",
                                         "Turn off the progress easing, the row fade-in and the "
                                         "busy bar. Nothing else changes.")
        motion = _SettingRow(_ToggleLabel("Reduce motion", self.motion_check),
                             self._helper("Changes happen instantly instead of easing"),
                             [self.motion_check], rule=False)
        group("Appearance", [notify, tray, theme_row, motion])

        # -- About ---------------------------------------------------------
        self.folder_label = _WrapLabel(str(self.queue.output_dir))
        self.folder_label.setWordWrap(True)
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._describe(self.folder_label, "Download folder",
                       "The folder where finished files are saved.")
        self.open_folder_button = QPushButton("Open")
        self._describe(self.open_folder_button, "Open download folder",
                       "Open the download folder in your file manager.")
        folder = _SettingRow("Download folder", self.folder_label, [self.open_folder_button],
                             self.open_folder_button)
        self.folder_label.setMinimumWidth(self.fontMetrics().horizontalAdvance("M") * 16)

        self.version_label = QLabel("checking...")
        self.version_label.setObjectName("settingValue")
        self._describe(self.version_label, "yt-dlp version",
                       "The installed version of the yt-dlp program.")
        self.update_hint = _WrapLabel(
            "If Instagram stops working, update yt-dlp (pacman -Syu / pip)"
        )
        self.update_hint.setWordWrap(True)
        self._describe(self.update_hint, "About updating yt-dlp",
                       "What to do when Instagram downloads stop working.")
        version = _SettingRow("yt-dlp version", self.update_hint, [self.version_label],
                              self.version_label)

        self.open_data_button = QPushButton("Open data folder")
        self._describe(self.open_data_button, "Open data folder",
                       "Open the folder that holds the history and archive.")
        data = _SettingRow("Data folder", self._helper("Holds the history and the archive"),
                           [self.open_data_button], self.open_data_button, rule=False)
        group("About", [folder, version, data])
        outer.addStretch(1)

        for signal in (
            self.concurrency_spin.valueChanged, self.limit_check.toggled,
            self.limit_spin.valueChanged, self.limit_unit.currentIndexChanged,
            self.preset_combo.currentIndexChanged, self.faster_combo.currentIndexChanged,
            self.cookies_combo.currentIndexChanged,
            self.photo_mode_combo.currentIndexChanged, self.song_length_combo.currentIndexChanged,
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
        self.setTabOrder(self.preset_combo, self.faster_combo)
        self.setTabOrder(self.faster_combo, self.photo_mode_combo)
        self.setTabOrder(self.photo_mode_combo, self.song_length_combo)
        self.setTabOrder(self.song_length_combo, self.detect_button)
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
    def _helper(text: str) -> QLabel:
        return _WrapLabel(text)

    @staticmethod
    def _value(text: str, name: str, description: str) -> QLabel:
        """A read-only value shown where a control would be (nothing to change yet)."""
        label = QLabel(text)
        label.setObjectName("settingValue")
        label.setAccessibleName(name)
        label.setAccessibleDescription(description)
        return label

    @staticmethod
    def _switch(name: str, description: str) -> QCheckBox:
        """A switch: the row's own label carries the words, so the switch has none."""
        check = QCheckBox()
        check.setAccessibleName(name)
        check.setAccessibleDescription(description)
        return check

    def _arrange(self, width: int) -> None:
        """Stack a row's control under its text when it would not fit beside it."""
        for row in self.rows:
            row.stack(row.wants_stack(width))

    def _fit_to_font(self) -> None:
        """Give the number boxes room for their digits and arrows at any text size."""
        fm = self.fontMetrics()
        for spin, sample in ((self.concurrency_spin, "00"), (self.limit_spin, "00000.0")):
            spin.setMinimumWidth(fm.horizontalAdvance(sample) + 120)
            # The style sheet's fixed min-height must not squeeze the number field at big text.
            spin.setMinimumHeight(max(42, spin.lineEdit().minimumSizeHint().height() + 8))
        self.folder_label.setMinimumWidth(fm.horizontalAdvance("M") * 16)
        self._arrange(self._scroll.viewport().width())

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
        self.faster_combo.setCurrentIndex(max(0, self.faster_combo.findData(s.faster_downloads)))
        self.photo_mode_combo.setCurrentIndex(max(0, self.photo_mode_combo.findData(s.photo_mode)))
        self.song_length_combo.setCurrentIndex(max(0, self.song_length_combo.findData(s.song_length)))
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
            photo_mode=self.photo_mode_combo.currentData(),
            song_length=self.song_length_combo.currentData(),
            faster_downloads=self.faster_combo.currentData(),
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
        self.detect_row.setVisible(show)

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
