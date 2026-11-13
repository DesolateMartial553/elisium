"""Table model for the download queue."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt

__all__ = [
    "DownloadModel",
    "COLUMNS",
    "PERCENT_ROLE",
    "STATUS_TEXT",
    "format_bytes",
    "format_speed",
    "format_eta",
]

COLUMNS = ("Title", "Status", "Progress", "Speed", "ETA", "Size")
COL_TITLE, COL_STATUS, COL_PROGRESS, COL_SPEED, COL_ETA, COL_SIZE = range(6)
PERCENT_ROLE = int(Qt.ItemDataRole.UserRole) + 1

# A word plus an icon character: status is never conveyed by colour alone.
STATUS_TEXT = {
    "queued": "⏳ Queued",
    "probing": "\U0001f50d Checking",
    "downloading": "⬇ Downloading",
    "merging": "⚙ Merging",
    "converting": "⟳ Converting",
    "paused": "⏸ Paused",
    "done": "✔ Done",
    "failed": "✖ Failed",
    "skipped": "⏭ Skipped",
    "cancelled": "⊘ Cancelled",
}
_WORD = {
    "queued": "queued",
    "probing": "checking",
    "downloading": "downloading",
    "merging": "merging",
    "converting": "converting",
    "paused": "paused",
    "done": "done",
    "failed": "failed",
    "skipped": "skipped",
    "cancelled": "cancelled",
}
_RUNNING = ("downloading", "merging", "converting")
_UNITS = ("B", "KB", "MB", "GB", "TB")
_UNIT_WORDS = ("bytes", "kilobytes", "megabytes", "gigabytes", "terabytes")


def _scale(value: float) -> tuple[float, int]:
    size = float(value)
    unit = 0
    while size >= 1024 and unit < len(_UNITS) - 1:
        size /= 1024
        unit += 1
    return size, unit


def _number(size: float, unit: int) -> str:
    return f"{size:.0f}" if unit == 0 else f"{size:.1f}"


def format_bytes(value: float | None) -> str:
    if value is None or value < 0:
        return ""
    size, unit = _scale(value)
    return f"{_number(size, unit)} {_UNITS[unit]}"


def format_speed(value: float | None) -> str:
    if value is None or value <= 0:
        return ""
    return f"{format_bytes(value)}/s"


def _speed_words(value: float) -> str:
    size, unit = _scale(value)
    return f"{_number(size, unit)} {_UNIT_WORDS[unit]} per second"


def format_eta(value: float | None) -> str:
    if value is None or value < 0:
        return ""
    total = int(round(value))
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    if minutes:
        return f"{minutes}m {seconds}s" if seconds else f"{minutes}m"
    return f"{seconds}s"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _eta_words(value: float) -> str:
    total = int(round(value))
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(_plural(hours, "hour"))
    if minutes:
        parts.append(_plural(minutes, "minute"))
    if seconds or not parts:
        if not hours:
            parts.append(_plural(seconds, "second"))
    return " ".join(parts) + " left"


class DownloadModel(QAbstractTableModel):
    """Rows are queue-item snapshots; fed by bridge events."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._index: dict[int, int] = {}

    # -- feeding ---------------------------------------------------------
    def load(self, items: list[dict[str, Any]]) -> None:
        """Replace everything with a ``queue.items()`` snapshot."""
        self.beginResetModel()
        self._rows = [dict(item) for item in items]
        self._index = {row["id"]: n for n, row in enumerate(self._rows)}
        self.endResetModel()

    def has_item(self, item_id: int) -> bool:
        return item_id in self._index

    def upsert(self, snapshot: dict[str, Any]) -> None:
        """Add the item, or replace the row it already has."""
        item_id = snapshot["id"]
        row = self._index.get(item_id)
        if row is None:
            position = len(self._rows)
            self.beginInsertRows(QModelIndex(), position, position)
            self._rows.append(dict(snapshot))
            self._index[item_id] = position
            self.endInsertRows()
            return
        self._rows[row] = dict(snapshot)
        self.dataChanged.emit(
            self.index(row, 0), self.index(row, len(COLUMNS) - 1)
        )

    def handle_event(self, event: dict[str, Any]) -> None:
        """Apply a queue event (``added``/``state``/``progress``/``item``)."""
        item = event.get("item")
        if isinstance(item, dict) and "id" in item:
            self.upsert(item)

    # -- reading ---------------------------------------------------------
    def item_id_at(self, row: int) -> int | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]["id"]
        return None

    def snapshot_at(self, row: int) -> dict[str, Any] | None:
        if 0 <= row < len(self._rows):
            return dict(self._rows[row])
        return None

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

    # -- cell helpers ----------------------------------------------------
    @staticmethod
    def title_of(row: dict[str, Any]) -> str:
        return row.get("title") or row.get("url") or ""

    @staticmethod
    def percent_of(row: dict[str, Any]) -> float | None:
        if row["state"] == "done":
            return 100.0
        percent = (row.get("progress") or {}).get("percent")
        return None if percent is None else float(percent)

    @staticmethod
    def spoken(row: dict[str, Any]) -> str:
        """One full sentence describing the row, for screen readers."""
        state = row["state"]
        parts = [DownloadModel.title_of(row), _WORD.get(state, state)]
        progress = row.get("progress") or {}
        if state in _RUNNING:
            percent = DownloadModel.percent_of(row)
            if percent is not None:
                parts.append(f"{percent:.0f} percent")
            if progress.get("speed"):
                parts.append(_speed_words(progress["speed"]))
            if progress.get("eta") is not None:
                parts.append(_eta_words(progress["eta"]))
        elif state == "paused":
            percent = DownloadModel.percent_of(row)
            if percent is not None:
                parts.append(f"{percent:.0f} percent")
        elif state in ("failed", "skipped") and row.get("error"):
            error = row["error"]
            parts.append(f"{error['message']} {error['fix']}".strip())
        return ", ".join(parts)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        column = index.column()
        state = row["state"]
        progress = row.get("progress") or {}
        running = state in _RUNNING

        if role == Qt.ItemDataRole.AccessibleTextRole:
            return self.spoken(row)
        if role == PERCENT_ROLE:
            return self.percent_of(row)
        if role == Qt.ItemDataRole.TextAlignmentRole and column >= COL_SPEED:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == COL_TITLE:
                return row.get("url")
            if column == COL_STATUS and row.get("error"):
                error = row["error"]
                return f"{error['message']} {error['fix']}".strip()
            return None
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if column == COL_TITLE:
            return self.title_of(row)
        if column == COL_STATUS:
            return STATUS_TEXT.get(state, state)
        if column == COL_PROGRESS:
            percent = self.percent_of(row)
            return "" if percent is None else f"{percent:.0f}%"
        if column == COL_SPEED:
            return format_speed(progress.get("speed")) if running else ""
        if column == COL_ETA:
            return format_eta(progress.get("eta")) if running else ""
        if column == COL_SIZE:
            return format_bytes(progress.get("total_bytes") or progress.get("downloaded_bytes"))
        return None
