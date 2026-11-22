"""The History page: grouped by day, search, a site filter, open, download again, copy link, delete.

Night shelf: rows have the anatomy of a download row (thumbnail placeholder, title, meta, no
bar); the state is a coloured word, never an icon; the day heading sits above the first row of
each day. One model row per entry: the headings are painted, so selection and row numbers stay
the model's own.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QPointF,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QActionGroup, QDesktopServices, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
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

from . import theme
from .bridge import QueueBridge
from .model import STATUS_TEXT, format_bytes, site_name
from .widgets import EmptyState, HistoryDelegate, RowHeightKeeper, make_primary, make_quiet

__all__ = ["HistoryModel", "HistoryPage", "FILE_MISSING_TEXT", "ALL_SITES", "day_heading"]

FILE_MISSING_TEXT = "File missing"
ALL_SITES = "All sites"
COLUMNS = ("Title", "Site", "State", "Date", "File")
SEARCH_DELAY_MS = 200
ROW_LIMIT = 500


def _site(url: str) -> str:
    return site_name(url) or url


def _when(row: dict[str, Any]) -> datetime | None:
    """When the entry finished (else was added), in local time; ``None`` if unreadable."""
    raw = row.get("finished_at") or row.get("created_at") or ""
    try:
        return datetime.fromisoformat(raw).astimezone()
    except ValueError:
        return None


def _date(row: dict[str, Any]) -> str:
    when = _when(row)
    return when.strftime("%Y-%m-%d %H:%M") if when else (row.get("finished_at") or "")


def day_heading(day: date, today: date) -> str:
    """The heading over a day's rows: Today, Yesterday, or ``Thursday 19 November``."""
    gap = (today - day).days
    if gap == 0:
        return "Today"
    if gap == 1:
        return "Yesterday"
    text = f"{day.strftime('%A')} {day.day} {day.strftime('%B')}"
    return text if day.year == today.year else f"{text} {day.year}"


class HistoryModel(QAbstractTableModel):
    """Read-only rows from ``History``; ``file_missing`` is computed on load."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._headings: list[str | None] = []

    def load(self, rows: list[dict[str, Any]], today: date | None = None) -> None:
        """Replace the rows (newest first). *today* is only passed by tests."""
        today = today or datetime.now().astimezone().date()
        self.beginResetModel()
        self._rows = []
        self._headings = []
        previous: date | None = None
        for row in rows:
            row = dict(row)
            path = row.get("file_path")
            exists = bool(path) and os.path.exists(path)
            row["file_missing"] = bool(row.get("state") == "done" and path and not exists)
            row["site"] = _site(row["url"])
            size = 0
            if exists:
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
            row["size_bytes"] = size
            row["size_text"] = format_bytes(size) if size else ""
            when = _when(row)
            row["when_text"] = when.strftime("%H:%M") if when else ""
            day = when.date() if when else None
            heading = None
            if day is not None and day != previous:
                heading = day_heading(day, today)
                previous = day
            elif day is None and not self._rows:
                heading = "Earlier"
            self._rows.append(row)
            self._headings.append(heading)
        self.endResetModel()

    def heading_at(self, row: int) -> str | None:
        """The day heading painted above this row (first row of a day), else ``None``."""
        return self._headings[row] if 0 <= row < len(self._headings) else None

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
                    self.state_text(row),
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


def _sort_key(row: dict[str, Any]) -> tuple[float, int]:
    when = _when(row)
    return (when.timestamp() if when else 0.0, int(row.get("id") or 0))


class _HistoryHeights(RowHeightKeeper):
    """The row-height keeper that also re-applies each row's own height (day headings)."""

    def __init__(self, view: Any, delegate: Any, page: Any) -> None:
        super().__init__(view, delegate)
        self._page = page
        self.update()

    def update(self) -> None:
        super().update()
        page = getattr(self, "_page", None)
        if page is not None:
            page._apply_heights()


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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(int(theme.SPACE["gap"]))
        head = QHBoxLayout()
        title = QLabel("History")
        title.setObjectName("pageTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.summary_label = QLabel()
        self.summary_label.setProperty("muted", True)
        self.summary_label.setAccessibleName("History summary")
        head.addWidget(self.summary_label)
        layout.addLayout(head)

        tools = QHBoxLayout()
        tools.setSpacing(int(theme.SPACE["gap"]))
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchField")
        self.search_edit.setPlaceholderText("Search titles and links")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setAccessibleName("Search history")
        self.search_edit.setAccessibleDescription(
            "Type part of a title or link to filter the list of past downloads."
        )
        tools.addWidget(self.search_edit, 1)
        # The site filter is a quiet text menu: the words say which site, no coloured chip.
        self.site_button = QPushButton(ALL_SITES)
        self.site_button.setProperty("quiet", True)
        self.site_button.setProperty("menu", True)
        self.site_button.setAccessibleName("Site filter")
        self.site_button.setAccessibleDescription(
            "Show downloads from one site only, or from all sites."
        )
        self.site_menu = QMenu(self.site_button)
        self.site_button.setMenu(self.site_menu)
        tools.addWidget(self.site_button)
        layout.addLayout(tools)
        self._site: str | None = None  # None: all sites
        self._sites: list[str] = []

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
        self.table.setTabKeyNavigation(False)
        self.table.setObjectName("cards")
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Cards: one delegate paints the whole row into column 0; the other
        # columns stay in the model (names, tests, screen readers) but are hidden.
        self.delegate = HistoryDelegate(self.table)
        self.table.setItemDelegateForColumn(0, self.delegate)
        self.row_heights = _HistoryHeights(self.table, self.delegate, self)
        self.table.horizontalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        for column in range(1, len(COLUMNS)):
            self.table.setColumnHidden(column, True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setMouseTracking(True)
        self.table.viewport().installEventFilter(self)
        self.empty_state = EmptyState(self.table.viewport(), "No downloads yet")
        self.empty_state.setAccessibleName("Empty history")
        self._fit_to_font()
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
        self.setTabOrder(self.search_edit, self.site_button)
        self.setTabOrder(self.site_button, self.table)
        self.setTabOrder(self.table, self.open_file_button)
        self.setTabOrder(self.open_file_button, self.open_folder_button)
        self.setTabOrder(self.open_folder_button, self.again_button)
        self.setTabOrder(self.again_button, self.copy_button)
        self.setTabOrder(self.copy_button, self.delete_button)
        self._update_buttons()

    def _fit_to_font(self) -> None:
        """Size the cards from the text size, so 200% text never clips."""
        self.row_heights.update()
        fm = QFontMetrics(self.font())
        self.table.setMinimumWidth(fm.horizontalAdvance("M") * 22)

    def _apply_heights(self) -> None:
        """Each row is one normal row high; the first row of a day also holds its heading."""
        base = self.delegate.row_height(self.table.font())
        extra = self.delegate.heading_height(self.table.font())
        for row in range(self.model.rowCount()):
            self.table.setRowHeight(row, base + (extra if self.model.heading_at(row) else 0))

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if hasattr(self, "table") and event.type() in (
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
        ):
            self._fit_to_font()

    @staticmethod
    def _button(text: str, description: str) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("quiet", True)
        button.setAccessibleName(text)
        button.setAccessibleDescription(description)
        return button

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        """Reload rows from the history (search box and site filter applied), newest first."""
        selected = self.selected_row()
        text = self.search_edit.text().strip()
        if text:
            rows = self.queue.history.search(text, ROW_LIMIT)
        else:
            rows = self.queue.history.recent(ROW_LIMIT)
        rows = sorted(rows, key=_sort_key, reverse=True)
        self._set_sites(sorted({_site(r["url"]) for r in rows}, key=str.lower))
        if self._site is not None:
            rows = [r for r in rows if _site(r["url"]) == self._site]
        self.model.load(rows)
        self._apply_heights()
        self._update_summary()
        if selected is not None:
            for row in range(self.model.rowCount()):
                if self.model.row_at(row)["id"] == selected["id"]:
                    self.table.selectRow(row)
                    break
        self._update_buttons()

    def _set_sites(self, sites: list[str]) -> None:
        """Rebuild the site menu from the sites in the current results."""
        self._sites = sites
        if self._site is not None and self._site not in sites:
            self._site = None
        self.site_menu.clear()
        group = QActionGroup(self.site_menu)
        group.setExclusive(True)
        for label, value in [(ALL_SITES, None)] + [(name, name) for name in sites]:
            action = self.site_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(value == self._site)
            action.triggered.connect(lambda _checked=False, v=value: self.set_site(v))
            group.addAction(action)
        self.site_button.setText(self._site or ALL_SITES)

    def set_site(self, site: str | None) -> None:
        """Show only *site* (``None``: all sites) and reload."""
        if site != self._site:
            self._site = site
            self.refresh()

    def _update_summary(self) -> None:
        count = self.model.rowCount()
        total = sum(self.model.row_at(r)["size_bytes"] for r in range(count))
        text = f"{count} saved" + (f" · {format_bytes(total)}" if total else "")
        self.summary_label.setText(text)
        empty = count == 0
        self.empty_state.setVisible(empty)
        searching = bool(self.search_edit.text().strip()) or self._site is not None
        self.empty_state.text = "Nothing matches" if searching else "No downloads yet"
        self.empty_state.setAccessibleDescription(self.empty_state.text)
        self.empty_state.update()

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

    # -- the links painted in each row ---------------------------------------
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.table.viewport():
            kind = event.type()
            if kind in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
                hit = self._link_under(event.position())
                if kind == QEvent.Type.MouseMove:
                    self._hover(hit)
                elif hit is not None and event.button() == Qt.MouseButton.LeftButton:
                    self.activate_link(*hit)
                    return True
            elif kind == QEvent.Type.Leave:
                self._hover(None)
        return super().eventFilter(watched, event)

    def _link_under(self, pos: QPointF) -> tuple[int, str] | None:
        """``(model row, link kind)`` under *pos* (viewport coordinates), or ``None``."""
        index = self.table.indexAt(pos.toPoint())
        if not index.isValid():
            return None
        row = self.model.row_at(index.row())
        kind = self.delegate.link_at(
            self.table.visualRect(self.model.index(index.row(), 0)), row, self.table.font(),
            bool(self.model.heading_at(index.row())), pos,
        )
        return (index.row(), kind) if kind else None

    def _hover(self, hit: tuple[int, str] | None) -> None:
        row = self.model.row_at(hit[0]) if hit else None
        wanted = (row["id"], hit[1]) if row and hit else None
        if wanted != self.delegate.hover:
            self.delegate.hover = wanted
            self.table.viewport().setCursor(
                Qt.CursorShape.PointingHandCursor if wanted else Qt.CursorShape.ArrowCursor
            )
            self.table.viewport().update()

    def activate_link(self, row: int, kind: str) -> None:
        """Run a row link ("open", "folder", "again") for model row *row*."""
        self.table.selectRow(row)
        {"open": self.open_file, "folder": self.open_folder, "again": self.download_again}[kind]()

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
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.setWindowTitle("Delete entry")
        box.setText("Remove this entry from the history? The downloaded file is kept.")
        yes = box.addButton("Delete entry", QMessageBox.ButtonRole.AcceptRole)
        no = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        make_primary(yes)
        make_quiet(no)
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
