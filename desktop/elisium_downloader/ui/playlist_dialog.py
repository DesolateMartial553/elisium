"""The playlist picker: choose which videos of a playlist or channel to queue."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QToolButton,
    QWidget,
)

from elisium_downloader.engine import formats
from elisium_downloader.engine.errors import ErrorInfo
from elisium_downloader.engine.formats import PlaylistEntry
from elisium_downloader.engine.presets import PRESETS, Preset, get
from elisium_downloader.engine.queue import DownloadQueue

from .probe_worker import ProbeWorker
from .quality_dialog import dialog_scale, reduce_motion
from .widgets import dialog_card, make_primary, make_quiet

__all__ = ["PlaylistDialog"]

ENTRY_ROLE = Qt.ItemDataRole.UserRole + 1


class PlaylistDialog(QDialog):
    """Probe a playlist link, then queue the ticked videos one by one.

    Each chosen video is queued by its *own* URL (never the playlist URL) with
    the chosen preset. ``itemsAdded`` carries ``[(snapshot, is_new)]``.
    """

    itemsAdded = Signal(list)

    def __init__(
        self,
        url: str,
        queue: DownloadQueue,
        probe: Callable[[str], dict[str, Any]],
        *,
        presets: Sequence[Preset] | None = None,
        default_preset_id: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.url = url
        self.queue = queue
        self._entries: list[PlaylistEntry] = []
        self._state = "idle"
        self._updating = False
        self.added_count = 0
        self.known_count = 0
        self.setWindowTitle("Choose videos from a playlist")
        self.setAccessibleName("Playlist")
        self._fit_to_font()

        self.worker = ProbeWorker(probe, self)
        self.worker.finished.connect(self._on_probed)
        self.worker.failed.connect(self._on_failed)

        self._build(list(presets) if presets else list(PRESETS.values()), default_preset_id)
        self.start_probe()

    # -- construction ----------------------------------------------------
    def _build(self, presets: list[Preset], default_id: str | None) -> None:
        root = dialog_card(self)
        root.setSpacing(12)
        self.title_label = QLabel("Playlist")
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setWordWrap(True)
        self.title_label.setAccessibleName("Playlist title")
        root.addWidget(self.title_label)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Status")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setAccessibleName("Checking the link")
        self.fix_label = QLabel()
        self.fix_label.setWordWrap(True)
        self.fix_label.setAccessibleName("Suggested fix")
        self.details_button = QToolButton()
        self.details_button.setText("Show details")
        self.details_button.setCheckable(True)
        self.details_button.setArrowType(Qt.ArrowType.RightArrow)
        self.details_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.details_button.setAccessibleName("Show details")
        self.details_button.setAccessibleDescription("Show the raw yt-dlp output for this error.")
        self.details_text = QPlainTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(90)
        self.details_text.setAccessibleName("Error details")
        self.details_text.setHidden(True)
        self.details_button.toggled.connect(self._toggle_details)
        for widget in (self.status_label, self.progress, self.fix_label,
                       self.details_button, self.details_text):
            root.addWidget(widget)

        tools = QHBoxLayout()
        self.select_all_button = QPushButton("Select all")
        self.select_all_button.setAccessibleName("Select all")
        self.select_all_button.setAccessibleDescription("Tick every available video.")
        self.select_none_button = QPushButton("Select none")
        self.select_none_button.setAccessibleName("Select none")
        self.select_none_button.setAccessibleDescription("Untick every video.")
        range_label = QLabel("Range")
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("for example 3-15 or 1,4,9-12")
        self.range_edit.setAccessibleName("Range")
        self.range_edit.setAccessibleDescription(
            "Type video numbers such as 3-15 or 1,4,9-12 to tick exactly those videos."
        )
        range_label.setBuddy(self.range_edit)
        make_quiet(self.select_all_button)
        make_quiet(self.select_none_button)
        self.select_all_button.setAutoDefault(False)
        self.select_none_button.setAutoDefault(False)
        tools.setSpacing(8)
        tools.addWidget(self.select_all_button)
        tools.addWidget(self.select_none_button)
        tools.addWidget(range_label)
        tools.addWidget(self.range_edit, 1)
        root.addLayout(tools)
        self.range_error = QLabel()
        self.range_error.setWordWrap(True)
        self.range_error.setAccessibleName("Range problem")
        self.range_error.setVisible(False)
        root.addWidget(self.range_error)

        self.list = QListWidget()
        self.list.setObjectName("entries")
        self.list.setAccessibleName("Videos in the playlist")
        self.list.setAccessibleDescription(
            "Use the arrow keys to move and Space to tick or untick a video."
        )
        root.addWidget(self.list, 1)

        self.count_label = QLabel("0 of 0 selected")
        self.count_label.setAccessibleName("Selected count")
        root.addWidget(self.count_label)

        row = QHBoxLayout()
        label = QLabel("Quality")
        self.quality_combo = QComboBox()
        self.quality_combo.setAccessibleName("Quality")
        self.quality_combo.setAccessibleDescription("Quality used for every chosen video.")
        label.setBuddy(self.quality_combo)
        for preset in presets:
            self.quality_combo.addItem(preset.label, preset.id)
        index = self.quality_combo.findData(get(default_id).id if default_id else "best")
        self.quality_combo.setCurrentIndex(max(index, 0))
        row.addWidget(label)
        row.addWidget(self.quality_combo, 1)
        root.addLayout(row)

        self.buttons = QDialogButtonBox()
        self.retry_button = QPushButton("Retry")
        self.retry_button.setAccessibleName("Retry")
        self.retry_button.setAccessibleDescription("Check the link again.")
        make_quiet(self.retry_button)
        self.buttons.addButton(self.retry_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.add_button = QPushButton("Add selected")
        self.add_button.setAccessibleName("Add selected")
        self.add_button.setAccessibleDescription("Add the ticked videos to the download list.")
        self.add_button.setDefault(True)
        make_primary(self.add_button)
        self.buttons.addButton(self.add_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setAccessibleName("Cancel")
        self.cancel_button.setAccessibleDescription("Close without adding anything.")
        make_quiet(self.cancel_button)
        self.buttons.addButton(self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole)
        root.addWidget(self.buttons)

        self.select_all_button.clicked.connect(self.select_all)
        self.select_none_button.clicked.connect(self.select_none)
        self.range_edit.textChanged.connect(self._range_changed)
        self.range_edit.installEventFilter(self)
        self.list.itemChanged.connect(lambda *_: self._update_count())
        self.retry_button.clicked.connect(self.start_probe)
        self.add_button.clicked.connect(self._add_selected)
        self.cancel_button.clicked.connect(self.reject)

        chain = (self.select_all_button, self.select_none_button, self.range_edit,
                 self.list, self.quality_combo, self.details_button, self.retry_button,
                 self.add_button, self.cancel_button)
        for first, second in zip(chain, chain[1:]):
            QWidget.setTabOrder(first, second)

    # -- text size and keys ----------------------------------------------
    def _fit_to_font(self) -> None:
        scale = dialog_scale(self)
        self.setMinimumSize(round(560 * scale), round(460 * scale))

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._fit_to_font()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        """Enter in the range box applies the range; it must not press Add selected."""
        if (
            watched is self.range_edit
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        ):
            self._range_changed(self.range_edit.text())
            return True
        return super().eventFilter(watched, event)

    # -- state -----------------------------------------------------------
    @property
    def state(self) -> str:
        """``probing``, ``ready`` or ``failed``."""
        return self._state

    def _set_state(self, state: str, text: str, description: str | None = None) -> None:
        self._state = state
        self.status_label.setText(text)
        self.status_label.setAccessibleDescription(description or text)
        failed = state == "failed"
        ready = state == "ready"
        # Reduced motion: no busy bar, the status text alone says "Checking...".
        self.progress.setVisible(state == "probing" and not reduce_motion())
        self.retry_button.setVisible(failed)
        self.fix_label.setVisible(failed)
        self.details_button.setVisible(failed)
        if not failed:
            self.details_text.setHidden(True)
            self.details_button.setChecked(False)
        for widget in (self.select_all_button, self.select_none_button, self.range_edit,
                       self.list, self.quality_combo):
            widget.setEnabled(ready)
        self._update_count()

    def start_probe(self) -> None:
        self._entries = []
        self.list.clear()
        self.range_edit.clear()
        self._set_state("probing", "Checking the playlist...")
        self.worker.start(self.url)

    def _on_probed(self, info: dict) -> None:
        self._entries = formats.playlist_entries(info)
        title = info.get("title")
        self.title_label.setText(title.strip() if isinstance(title, str) and title.strip() else "Playlist")
        if not self._entries:
            self._set_state("failed", "No videos were found in this link.",
                            "No videos were found in this link. Check the link.")
            self.fix_label.setText("What to do: Check the link")
            self.details_text.setPlainText("The playlist came back empty.")
            return
        self._updating = True
        for entry in self._entries:
            self.list.addItem(self._make_item(entry))
        self._updating = False
        # Everything available starts ticked: the common wish is "all of them".
        self.select_all()
        available = sum(e.available for e in self._entries)
        self._set_state("ready", f"Found {len(self._entries)} videos ({available} available). "
                                 "Tick the ones you want.")

    def _on_failed(self, info: ErrorInfo, raw: str) -> None:
        self.fix_label.setText(f"What to do: {info.fix}")
        self.details_text.setPlainText(raw)
        self._set_state("failed", info.message, f"{info.message} {info.fix}.")

    def _toggle_details(self, shown: bool) -> None:
        self.details_text.setHidden(not shown)
        self.details_button.setArrowType(
            Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow
        )
        self.details_button.setText("Hide details" if shown else "Show details")

    def _make_item(self, entry: PlaylistEntry) -> QListWidgetItem:
        duration = formats.human_duration(entry.duration)
        text = f"{entry.index}. {entry.title}"
        if duration:
            text += f"  ({duration})"
        item = QListWidgetItem()
        item.setData(ENTRY_ROLE, entry)
        if entry.available:
            item.setText(text)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                          | Qt.ItemFlag.ItemIsSelectable)
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setText(f"{text}  - Unavailable")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
        return item

    # -- selection -------------------------------------------------------
    def _items(self) -> list[QListWidgetItem]:
        return [self.list.item(i) for i in range(self.list.count())]

    def _set_checked(self, wanted: set[int] | None) -> None:
        """Tick the available entries whose index is in *wanted* (None = all)."""
        self._updating = True
        for item in self._items():
            entry: PlaylistEntry = item.data(ENTRY_ROLE)
            if not entry.available:
                continue
            on = wanted is None or entry.index in wanted
            item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self._updating = False
        self._update_count()

    def select_all(self) -> None:
        self._set_checked(None)

    def select_none(self) -> None:
        self._set_checked(set())

    def _range_changed(self, text: str) -> None:
        if not text.strip():
            self._show_range_error("")
            return
        try:
            numbers = formats.parse_range(text, len(self._entries))
        except ValueError as exc:
            self._show_range_error(str(exc))
            return
        self._show_range_error("")
        self._set_checked(set(numbers))

    def _show_range_error(self, message: str) -> None:
        self.range_error.setText(message)
        self.range_error.setVisible(bool(message))
        self.range_edit.setAccessibleDescription(
            message or "Type video numbers such as 3-15 or 1,4,9-12 to tick exactly those videos."
        )

    def selected_entries(self) -> list[PlaylistEntry]:
        chosen = []
        for item in self._items():
            entry: PlaylistEntry = item.data(ENTRY_ROLE)
            if entry.available and item.checkState() == Qt.CheckState.Checked:
                chosen.append(entry)
        return chosen

    def _update_count(self) -> None:
        if self._updating:
            return
        available = sum(e.available for e in self._entries)
        chosen = len(self.selected_entries())
        text = f"{chosen} of {available} selected"
        missing = len(self._entries) - available
        if missing:
            text += f" ({missing} unavailable)"
        self.count_label.setText(text)
        self.count_label.setAccessibleDescription(text)
        self.add_button.setEnabled(self._state == "ready" and chosen > 0)

    def selected_preset(self) -> Preset:
        return get(self.quality_combo.currentData())

    # -- actions ---------------------------------------------------------
    def _add_selected(self) -> None:
        if self._state != "ready":
            return
        preset = self.selected_preset()
        results: list[tuple[dict[str, Any], bool]] = []
        for entry in self.selected_entries():
            if entry.url is None:
                continue
            existing = {item["id"] for item in self.queue.items()}
            try:
                snapshot = self.queue.add(
                    entry.url,
                    format_selector=preset.format_selector,
                    extra_args=preset.extra_args,
                    title=entry.title,
                )
            except ValueError:
                continue
            results.append((snapshot, snapshot["id"] not in existing))
        self.added_count = sum(1 for _, new in results if new)
        self.known_count = len(results) - self.added_count
        self.itemsAdded.emit(results)
        self.accept()

    def done(self, result: int) -> None:
        self.worker.cancel()
        super().done(result)
