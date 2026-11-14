"""The "Choose quality" dialog for one video."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QEvent, QModelIndex, Qt, Signal
from PySide6.QtGui import QGuiApplication, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from elisium_downloader.engine import formats
from elisium_downloader.engine.errors import ErrorInfo
from elisium_downloader.engine.formats import FormatRow
from elisium_downloader.engine.presets import PRESETS, Preset, get
from elisium_downloader.engine.queue import DownloadQueue

from . import theme
from .probe_worker import ProbeWorker
from .thumbnail import ThumbnailLoader, placeholder_pixmap

__all__ = ["QualityDialog", "describe_selection", "dialog_scale", "font_scale", "reduce_motion"]

_COLUMNS = ("Resolution", "FPS", "Type", "Codec", "Bitrate", "Size", "Note")
_NONE_VIDEO = "No video (audio only)"
_NONE_AUDIO = "No separate audio"
ROW_ROLE = Qt.ItemDataRole.UserRole + 1
_REFERENCE_LINE_HEIGHT = 16  # fontMetrics().height() of the default 10 pt UI font


def reduce_motion() -> bool:
    """True when the user wants no animation.

    ``ELISIUM_REDUCE_MOTION=1`` forces it on and ``=0`` off. Otherwise the Settings
    switch "Reduce motion" counts, and a Qt that
    exposes a reduced-motion style hint is honoured (PySide6 6.12 has none).
    """
    override = os.environ.get("ELISIUM_REDUCE_MOTION", "").strip()
    if override in ("1", "0"):
        return override == "1"
    if theme.reduce_motion_enabled():  # the Settings switch "Reduce motion"
        return True
    hints = QGuiApplication.styleHints()
    return bool(getattr(hints, "reducedMotion", lambda: False)())


def dialog_scale(widget: QWidget) -> float:
    """Dialogs grow with the text, but less than 1:1 (their images do not scale)."""
    return 1 + (font_scale(widget) - 1) * 0.6


def font_scale(widget: QWidget) -> float:
    """How much bigger than the default 10 pt the widget's text is (1.0 or more)."""
    return max(1.0, widget.fontMetrics().height() / _REFERENCE_LINE_HEIGHT)


def _quality_word(row: FormatRow) -> str:
    if row.kind == "audio":
        return f"{round(row.bitrate)} kbps" if row.bitrate else row.ext
    return row.resolution


def describe_selection(video: FormatRow | None, audio: FormatRow | None) -> str:
    """Plain text for the chosen formats, e.g. ``Video 1080p mp4 + audio 128 kbps``."""
    parts = []
    if video is not None:
        text = f"Video {video.height}p {video.ext}" if video.height else f"Video {video.ext}"
        if video.kind == "video+audio":
            text += " (with sound)"
        parts.append(text)
    if audio is not None and not (video is not None and video.kind == "video+audio"):
        word = f"audio {_quality_word(audio)}"
        parts.append(word if parts else word.capitalize())
    if not parts:
        return ""
    text = " + ".join(parts)
    if video is not None and video.kind == "video" and audio is None:
        text += " (no sound)"
    return text


def _row_cells(row: FormatRow | None, label: str) -> list[QStandardItem]:
    if row is None:
        cells = [QStandardItem(label)] + [QStandardItem("") for _ in _COLUMNS[1:]]
    else:
        codec = row.vcodec if row.kind != "audio" else row.acodec
        if row.kind == "video+audio" and row.acodec and row.acodec != "none":
            codec = f"{row.vcodec} / {row.acodec}"
        cells = [
            QStandardItem(f"{row.resolution} {row.ext}".strip()),
            QStandardItem("" if row.fps is None else f"{row.fps:g}"),
            QStandardItem(row.kind),
            QStandardItem(codec),
            QStandardItem("" if row.bitrate is None else f"{row.bitrate:.0f} kbps"),
            QStandardItem(formats.human_size(row.size_bytes)),
            QStandardItem(row.note),
        ]
    for cell in cells:
        cell.setEditable(False)
    cells[0].setData(row, ROW_ROLE)
    return cells


class QualityDialog(QDialog):
    """Probe *url*, then let the user pick a preset or exact formats.

    ``itemsAdded`` carries ``[(snapshot, is_new)]`` after **Download** queued
    the link. ``probe`` is called as ``probe(url)`` on a worker thread.
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
        thumbnail_fetcher: Callable[..., None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.url = url
        self.queue = queue
        self._info: dict[str, Any] | None = None
        self._summary: formats.VideoSummary | None = None
        self._state = "idle"
        self.setWindowTitle("Choose quality")
        self.setAccessibleName("Choose quality")
        self._fit_to_font()

        self.worker = ProbeWorker(probe, self)
        self.worker.finished.connect(self._on_probed)
        self.worker.failed.connect(self._on_failed)
        self.thumbnails = ThumbnailLoader(thumbnail_fetcher, self)
        self.thumbnails.changed.connect(self._show_thumbnail)

        self._build(list(presets) if presets else list(PRESETS.values()), default_preset_id)
        self._fit_to_font()
        self.start_probe()

    # -- construction ----------------------------------------------------
    def _build(self, presets: list[Preset], default_id: str | None) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(18)
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setPixmap(placeholder_pixmap("Loading..."))
        self.thumbnail_label.setAccessibleName("Video preview")
        self.thumbnail_label.setAccessibleDescription("Thumbnail of the video.")
        self.thumbnail_label.setFixedSize(240, 135)
        info = QVBoxLayout()
        self.title_label = QLabel(self.url)
        self.title_label.setWordWrap(True)
        self.title_label.setAccessibleName("Video title")
        bold = self.title_label.font()
        bold.setBold(True)
        self.title_label.setFont(bold)
        self.uploader_label = QLabel("")
        self.uploader_label.setAccessibleName("Uploader")
        self.duration_label = QLabel("")
        self.duration_label.setAccessibleName("Length")
        info.addWidget(self.title_label)
        info.addWidget(self.uploader_label)
        info.addWidget(self.duration_label)
        info.addStretch(1)
        top.addWidget(self.thumbnail_label)
        top.addLayout(info, 1)
        root.addLayout(top)

        # Status line doubles as the accessible live region.
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Status")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
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
        self.details_text.setMaximumHeight(110)
        self.details_text.setAccessibleName("Error details")
        self.details_text.setHidden(True)
        self.details_button.toggled.connect(self._toggle_details)
        for widget in (self.status_label, self.progress, self.fix_label,
                       self.details_button, self.details_text):
            root.addWidget(widget)

        row = QHBoxLayout()
        label = QLabel("Quality")
        self.quality_combo = QComboBox()
        self.quality_combo.setAccessibleName("Quality")
        self.quality_combo.setAccessibleDescription("Pick a ready-made quality.")
        label.setBuddy(self.quality_combo)
        for preset in presets:
            self.quality_combo.addItem(preset.label, preset.id)
        index = self.quality_combo.findData(get(default_id).id if default_id else "best")
        self.quality_combo.setCurrentIndex(max(index, 0))
        row.addWidget(label)
        row.addWidget(self.quality_combo, 1)
        root.addLayout(row)

        self.advanced_button = QToolButton()
        self.advanced_button.setText("Advanced: choose exact formats")
        self.advanced_button.setCheckable(True)
        self.advanced_button.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_button.setAccessibleName("Advanced: choose exact formats")
        self.advanced_button.setAccessibleDescription(
            "Show every video and audio format so you can pick exactly one of each."
        )
        self.advanced_button.setEnabled(False)
        root.addWidget(self.advanced_button)

        self.advanced_box = QWidget()
        adv = QVBoxLayout(self.advanced_box)
        adv.setContentsMargins(0, 0, 0, 0)
        self.video_table, self.video_model = self._make_table(
            "Video formats", "Pick the picture. Formats marked video+audio already include sound."
        )
        self.audio_table, self.audio_model = self._make_table(
            "Audio formats", "Pick the sound to add to a picture-only format."
        )
        adv.addWidget(QLabel("Video"))
        adv.addWidget(self.video_table)
        adv.addWidget(QLabel("Audio"))
        adv.addWidget(self.audio_table)
        self.advanced_box.setHidden(True)
        root.addWidget(self.advanced_box)
        self.advanced_button.toggled.connect(self._toggle_advanced)

        self.selection_label = QLabel()
        self.selection_label.setWordWrap(True)
        self.selection_label.setAccessibleName("Chosen quality")
        root.addWidget(self.selection_label)

        self.buttons = QDialogButtonBox()
        self.retry_button = QPushButton("Retry")
        self.retry_button.setAccessibleName("Retry")
        self.retry_button.setAccessibleDescription("Check the link again.")
        self.buttons.addButton(self.retry_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.download_button = QPushButton("Download")
        self.download_button.setAccessibleName("Download")
        self.download_button.setAccessibleDescription("Add this video to the download list.")
        self.download_button.setDefault(True)
        self.download_button.setProperty("primary", True)
        self.buttons.addButton(self.download_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setAccessibleName("Cancel")
        self.cancel_button.setAccessibleDescription("Close without adding anything.")
        self.buttons.addButton(self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole)
        root.addWidget(self.buttons)

        self.retry_button.clicked.connect(self.start_probe)
        self.download_button.clicked.connect(self._download)
        self.cancel_button.clicked.connect(self.reject)
        self.quality_combo.currentIndexChanged.connect(self._update_selection_text)

        for first, second in zip(
            (self.quality_combo, self.advanced_button, self.video_table, self.audio_table,
             self.details_button, self.retry_button, self.download_button),
            (self.advanced_button, self.video_table, self.audio_table,
             self.details_button, self.retry_button, self.download_button,
             self.cancel_button),
            strict=True,
        ):
            QWidget.setTabOrder(first, second)

    def _make_table(self, name: str, description: str) -> tuple[QTableView, QStandardItemModel]:
        model = QStandardItemModel(0, len(_COLUMNS), self)
        model.setHorizontalHeaderLabels(list(_COLUMNS))
        table = QTableView()
        table.setModel(model)
        table.setAccessibleName(name)
        table.setAccessibleDescription(description)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setTabKeyNavigation(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.selectionModel().selectionChanged.connect(lambda *_: self._update_selection_text())
        return table, model

    # -- text size -------------------------------------------------------
    def _fit_to_font(self) -> None:
        """Size the dialog and its format tables from the text size (200% safe)."""
        self.setMinimumWidth(round(560 * dialog_scale(self)))
        for table in (getattr(self, "video_table", None), getattr(self, "audio_table", None)):
            if table is None:
                continue
            header = table.horizontalHeader().sizeHint().height()
            row = table.verticalHeader().defaultSectionSize()
            frame = 2 * table.frameWidth()
            table.setMinimumHeight(header + 3 * row + frame)
            table.setMaximumHeight(header + 6 * row + frame)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._fit_to_font()

    # -- state -----------------------------------------------------------
    @property
    def state(self) -> str:
        """``probing``, ``ready`` or ``failed``."""
        return self._state

    def _set_state(self, state: str, text: str, description: str | None = None) -> None:
        self._state = state
        self.status_label.setText(text)
        # Screen readers read the description when it changes: this is the live label.
        self.status_label.setAccessibleDescription(description or text)
        probing = state == "probing"
        failed = state == "failed"
        ready = state == "ready"
        # Reduced motion: no busy bar, the status text alone says "Checking...".
        self.progress.setVisible(probing and not reduce_motion())
        self.retry_button.setVisible(failed)
        self.fix_label.setVisible(failed)
        self.details_button.setVisible(failed)
        if not failed:
            self.details_text.setHidden(True)
            self.details_button.setChecked(False)
        self.download_button.setEnabled(ready)
        self.quality_combo.setEnabled(ready)
        self.advanced_button.setEnabled(ready and self.video_model.rowCount() > 0)
        if not ready:
            self.advanced_button.setChecked(False)
        self._update_selection_text()

    def start_probe(self) -> None:
        self._info = None
        self._summary = None
        self.thumbnails.cancel()
        self._set_state("probing", "Checking the link...")
        self.worker.start(self.url)

    def _on_probed(self, info: dict) -> None:
        self._info = info
        self._summary = formats.summary(info)
        s = self._summary
        self.title_label.setText(s.title)
        self.uploader_label.setText(s.uploader)
        duration = formats.human_duration(s.duration)
        self.duration_label.setText(f"Length {duration}" if duration else "")
        self._fill_tables(formats.format_rows(info))
        self.thumbnail_label.setPixmap(placeholder_pixmap("Loading..."))
        self.thumbnails.load(s.thumbnail)
        if not s.thumbnail:
            self.thumbnail_label.setPixmap(placeholder_pixmap())
        self._set_state("ready", "Ready. Choose a quality, then press Download.")

    def _on_failed(self, info: ErrorInfo, raw: str) -> None:
        self.fix_label.setText(f"What to do: {info.fix}")
        self.details_text.setPlainText(raw)
        self.thumbnail_label.setPixmap(placeholder_pixmap())
        self._set_state("failed", info.message, f"{info.message} {info.fix}.")

    def _toggle_details(self, shown: bool) -> None:
        self.details_text.setHidden(not shown)
        self.details_button.setArrowType(
            Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow
        )
        self.details_button.setText("Hide details" if shown else "Show details")

    def _show_thumbnail(self, pixmap: Any) -> None:
        self.thumbnail_label.setPixmap(pixmap)

    # -- advanced tables -------------------------------------------------
    def _fill_tables(self, rows: list[FormatRow]) -> None:
        for model in (self.video_model, self.audio_model):
            model.removeRows(0, model.rowCount())
        videos = [r for r in rows if r.kind != "audio"]
        audios = [r for r in rows if r.kind == "audio"]
        if videos:
            self.video_model.appendRow(_row_cells(None, _NONE_VIDEO))
        for r in videos:
            self.video_model.appendRow(_row_cells(r, ""))
        if audios:
            self.audio_model.appendRow(_row_cells(None, _NONE_AUDIO))
        for r in audios:
            self.audio_model.appendRow(_row_cells(r, ""))
        self.video_table.resizeColumnsToContents()
        self.audio_table.resizeColumnsToContents()

    def _toggle_advanced(self, shown: bool) -> None:
        self.advanced_box.setHidden(not shown)
        self.advanced_button.setArrowType(
            Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow
        )
        if shown:
            self._preselect()
        self.adjustSize()
        self._update_selection_text()

    def _preselect(self) -> None:
        """Start from the best video (and best audio if it has none inside)."""
        if not self.video_table.selectionModel().hasSelection() and self.video_model.rowCount() > 1:
            self.video_table.selectRow(1)
        video = self._selected_row(self.video_table)
        if (
            not self.audio_table.selectionModel().hasSelection()
            and self.audio_model.rowCount() > 1
            and (video is None or video.kind == "video")
        ):
            self.audio_table.selectRow(1)

    @staticmethod
    def _selected_row(table: QTableView) -> FormatRow | None:
        rows = table.selectionModel().selectedRows()
        if not rows:
            return None
        index: QModelIndex = rows[0]
        return table.model().item(index.row(), 0).data(ROW_ROLE)

    # -- result ----------------------------------------------------------
    def selected_preset(self) -> Preset:
        return get(self.quality_combo.currentData())

    def exact_selection(self) -> tuple[FormatRow | None, FormatRow | None]:
        """The (video, audio) rows chosen in the advanced tables."""
        if not self.advanced_button.isChecked():
            return None, None
        return self._selected_row(self.video_table), self._selected_row(self.audio_table)

    def result_selection(self) -> tuple[str, tuple[str, ...]]:
        """``(format_selector, extra_args)`` for the current choice."""
        video, audio = self.exact_selection()
        if video is not None or audio is not None:
            if video is not None and video.kind == "video+audio":
                audio = None
            return (
                formats.selector_for(video.format_id if video else None,
                                     audio.format_id if audio else None),
                (),
            )
        preset = self.selected_preset()
        return preset.format_selector, tuple(preset.extra_args)

    def _update_selection_text(self) -> None:
        if self._state != "ready":
            self.selection_label.setText("")
            return
        video, audio = self.exact_selection()
        if video is not None or audio is not None:
            if video is not None and video.kind == "video+audio":
                audio = None
            text = f"You will get: {describe_selection(video, audio)}"
        else:
            text = f"You will get: {self.selected_preset().label}"
            if self.advanced_button.isChecked():
                text += " (no exact formats chosen)"
        self.selection_label.setText(text)
        self.selection_label.setAccessibleDescription(text)

    # -- actions ---------------------------------------------------------
    def _download(self) -> None:
        if self._state != "ready":
            return
        selector, extra = self.result_selection()
        existing = {item["id"] for item in self.queue.items()}
        title = self._summary.title if self._summary else None
        try:
            snapshot = self.queue.add(
                self.url, format_selector=selector, extra_args=extra, title=title
            )
        except ValueError as exc:
            self._set_state("failed", "That link cannot be added.", str(exc))
            self.fix_label.setText("What to do: Check the link")
            self.details_text.setPlainText(str(exc))
            return
        self.itemsAdded.emit([(snapshot, snapshot["id"] not in existing)])
        self.accept()

    def done(self, result: int) -> None:
        self.worker.cancel()
        self.thumbnails.cancel()
        super().done(result)
