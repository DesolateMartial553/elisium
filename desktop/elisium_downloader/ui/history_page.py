"""The History page: search, open, download again, copy link, delete entry."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPoint,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from elisium_downloader.engine.history import TERMINAL_STATES
from elisium_downloader.engine.queue import DownloadQueue

from .bridge import QueueBridge
from .model import STATUS_TEXT

__all__ = ["HistoryModel", "HistoryPage", "FILE_MISSING_TEXT"]

FILE_MISSING_TEXT = "⚠ File missing"
COLUMNS = ("Title", "Site", "State", "Date", "File")
SEARCH_DELAY_MS = 200
ROW_LIMIT = 500


def _site(url: str) -> str:
    return urlsplit(url).netloc or url


def _date(row: dict[str, Any]) -> str:
    raw = row.get("finished_at") or row.get("created_at") or ""
    try:
        return datetime.fromisoformat(raw).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return raw


class HistoryModel(QAbstractTableModel):
    """Read-only rows from ``History``; ``file_missing`` is computed on load."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    def load(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = []
        for row in rows:
            row = dict(row)
            path = row.get("file_path")
            row["file_missing"] = bool(
                row.get("state") == "done" and path and not os.path.exists(path)
            )
            self._rows.append(row)
        self.endResetModel()

    def row_at(self, row: int) -> dict[str, Any] | None:
        return dict(self._rows[row]) if 0 <= row < len(self._rows) else None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = 0) -> Any:
        if orientation == Qt.Orientation.Horizontal and role in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.AccessibleTextRole,
        ):
            if 0 <= section < len(COLUMNS):
                return COLUMNS[section]
        return None

    @staticmethod
    def state_text(row: dict[str, Any]) -> str:
        if row.get("file_missing"):
            return FILE_MISSING_TEXT
        return STATUS_TEXT.get(row["state"], row["state"])

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return ", ".join(
                p
                for p in (
                    row.get("title") or row["url"],
                    self.state_text(row).split(" ", 1)[-1],
                    _date(row),
                )
                if p
            )
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == 0:
                return row["url"]
            if column == 4:
                return row.get("file_path")
            if column == 2 and row.get("error_message"):
                return row["error_message"]
            return None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if column == 0:
            return row.get("title") or row["url"]
        if column == 1:
            return _site(row["url"])
        if column == 2:
            return self.state_text(row)
        if column == 3:
            return _date(row)
        if column == 4:
            path = row.get("file_path")
            return Path(path).name if path else ""
        return None


class HistoryPage(QWidget):
    def __init__(
        self,
        queue: DownloadQueue,
        bridge: QueueBridge | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self.model = HistoryModel(self)
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(SEARCH_DELAY_MS)
        self._timer.timeout.connect(self.refresh)
        self.search_edit.textChanged.connect(lambda *_: self._timer.start())
        if bridge is not None:
            bridge.event.connect(self._on_event)
        self.refresh()

    # -- construction ----------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search history")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setAccessibleName("Search history")
        self.search_edit.setAccessibleDescription(
            "Type part of a title or link to filter the list of past downloads."
        )
        layout.addWidget(self.search_edit)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAccessibleName("History")
        self.table.setAccessibleDescription(
            "Past downloads with title, site, state, date and file name."
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 140), (2, 130), (3, 130), (4, 180)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.open_file_button = self._button(
            "Open file", "Open the downloaded file in your default app."
        )
        self.open_folder_button = self._button(
            "Open folder", "Open the folder that holds the downloaded file."
        )
        self.again_button = self._button(
            "Download again", "Add this link to the download list again."
        )
        self.copy_button = self._button("Copy link", "Copy the video link to the clipboard.")
        self.delete_button = self._button(
            "Delete entry",
            "Remove this row from the history. The downloaded file is not deleted.",
        )
        for button in (
            self.open_file_button, self.open_folder_button, self.again_button,
            self.copy_button, self.delete_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.message_label = QLabel()
        self.message_label.setAccessibleName("History message")
        buttons.addWidget(self.message_label)
        layout.addLayout(buttons)

        self.open_file_button.clicked.connect(self.open_file)
        self.open_folder_button.clicked.connect(self.open_folder)
        self.again_button.clicked.connect(self.download_again)
        self.copy_button.clicked.connect(self.copy_link)
        self.delete_button.clicked.connect(self.delete_entry)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_buttons())
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(lambda *_: self.open_file())
        self.setTabOrder(self.search_edit, self.table)
        self.setTabOrder(self.table, self.open_file_button)
        self.setTabOrder(self.open_file_button, self.open_folder_button)
        self.setTabOrder(self.open_folder_button, self.again_button)
        self.setTabOrder(self.again_button, self.copy_button)
        self.setTabOrder(self.copy_button, self.delete_button)
        self._update_buttons()

    @staticmethod
    def _button(text: str, description: str) -> QPushButton:
        button = QPushButton(text)
        button.setAccessibleName(text)
        button.setAccessibleDescription(description)
        return button

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        """Reload rows from the history (filtered by the search box)."""
        selected = self.selected_row()
        text = self.search_edit.text().strip()
        if text:
            rows = self.queue.history.search(text, ROW_LIMIT)
        else:
            rows = self.queue.history.recent(ROW_LIMIT)
        self.model.load(rows)
        if selected is not None:
            for row in range(self.model.rowCount()):
                if self.model.row_at(row)["id"] == selected["id"]:
                    self.table.selectRow(row)
                    break
        self._update_buttons()

    def showEvent(self, event: Any) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh()

    def _on_event(self, event: dict[str, Any]) -> None:
        item = event.get("item")
        if isinstance(item, dict) and item.get("state") in TERMINAL_STATES:
            if event.get("type") in ("state", "added"):
                self.refresh()

    def selected_row(self) -> dict[str, Any] | None:
        rows = self.table.selectionModel().selectedRows()
        return self.model.row_at(rows[0].row()) if rows else None

    def _update_buttons(self) -> None:
        row = self.selected_row()
        has_file = bool(row and row["state"] == "done" and row.get("file_path")
                        and not row["file_missing"])
        self.open_file_button.setEnabled(has_file)
        self.open_folder_button.setEnabled(has_file)
        self.again_button.setEnabled(row is not None)
        self.copy_button.setEnabled(row is not None)
        self.delete_button.setEnabled(row is not None)

    def _say(self, text: str) -> None:
        self.message_label.setText(text)

    # -- actions ---------------------------------------------------------
    def open_file(self) -> None:
        row = self.selected_row()
        if row and row.get("file_path") and not row["file_missing"] and row["state"] == "done":
            QDesktopServices.openUrl(QUrl.fromLocalFile(row["file_path"]))

    def open_folder(self) -> None:
        row = self.selected_row()
        if row and row.get("file_path") and not row["file_missing"] and row["state"] == "done":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(row["file_path"]).parent)))

    def download_again(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        try:
            self.queue.add(row["url"])
        except ValueError:
            self._say("That link cannot be downloaded")
            return
        self._say("Added to the download list")

    def copy_link(self) -> None:
        row = self.selected_row()
        if row is not None:
            QGuiApplication.clipboard().setText(row["url"])
            self._say("Link copied")

    def _confirm_delete(self) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Delete entry")
        box.setText("Remove this entry from the history? The downloaded file is kept.")
        yes = box.addButton("Delete entry", QMessageBox.ButtonRole.AcceptRole)
        no = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(no)
        box.setEscapeButton(no)
        box.exec()
        return box.clickedButton() is yes

    def delete_entry(self) -> None:
        """Delete the selected history row (never the file) after confirming."""
        row = self.selected_row()
        if row is None or not self._confirm_delete():
            return
        self.queue.history.delete(row["id"])
        self.refresh()
        self._say("Entry deleted")

    def _context_menu(self, pos: QPoint) -> None:
        index = self.table.indexAt(pos)
        if index.isValid():
            self.table.selectRow(index.row())
        menu = QMenu(self)
        for button in (
            self.open_file_button, self.open_folder_button, self.again_button,
            self.copy_button, self.delete_button,
        ):
            action = menu.addAction(button.text(), button.click)
            action.setEnabled(button.isEnabled())
        menu.exec(self.table.viewport().mapToGlobal(pos))
