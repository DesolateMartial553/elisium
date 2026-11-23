"""Table model for the download queue."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from elisium_downloader.engine import media as _media
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QSortFilterProxyModel,
    Qt,
)

__all__ = [
    "DownloadModel",
    "COLUMNS",
    "FILTERS",
    "FILTER_LABELS",
    "PERCENT_ROLE",
    "RowText",
    "STATE_WORD",
    "STATUS_TEXT",
    "StateFilterProxy",
    "describe_row",
    "eta_text",
    "filter_of",
    "format_bytes",
    "format_speed",
    "format_eta",
    "site_name",
    "LOOKING_UP_TITLE",
    "STALL_AFTER",
    "STALL_REASONS",
    "host_title",
    "stall_reason",
]

LOOKING_UP_TITLE = "Looking up the post..."
# Brief 12C: after this many quiet seconds a row that has not started says why.
STALL_AFTER = 10.0
STALL_REASONS = {
    "signing_in": "Signing in",
    "network": "Waiting for the network",
    "rate_limited": "Rate limited, waiting",
}

COLUMNS = ("Title", "Status", "Progress", "Speed", "ETA", "Size")
COL_TITLE, COL_STATUS, COL_PROGRESS, COL_SPEED, COL_ETA, COL_SIZE = range(6)
PERCENT_ROLE = int(Qt.ItemDataRole.UserRole) + 1

# Status is always a plain word (never an icon or emoji): the status column of the
# queue table and the History state words.
STATUS_TEXT = {
    "queued": "Queued",
    "probing": "Checking",
    "downloading": "Downloading",
    "merging": "Merging",
    "converting": "Converting",
    "paused": "Paused",
    "done": "Done",
    "failed": "Failed",
    "skipped": "Skipped",
    "cancelled": "Cancelled",
}
# Night shelf row wording: plain words, no icons (the Downloads rows draw these).
STATE_WORD = {
    "queued": "Waiting",
    "probing": "Checking",
    "downloading": "Downloading",
    "merging": "Merging",
    "converting": "Converting",
    "paused": "Paused",
    "done": "Done",
    "failed": "Failed",
    "skipped": "Skipped",
    "cancelled": "Cancelled",
}
# The count cards above the list: key -> the queue states it shows.
FILTERS = ("all", "downloading", "waiting", "failed", "done")
FILTER_LABELS = {
    "all": "All", "downloading": "Downloading", "waiting": "Waiting",
    "failed": "Failed", "done": "Done",
}
_FILTER_STATES = {
    "downloading": frozenset({"probing", "downloading", "merging", "converting"}),
    "waiting": frozenset({"queued", "paused"}),
    "failed": frozenset({"failed"}),
    "done": frozenset({"done"}),
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


def eta_text(value: float | None) -> str:
    """Time left in the Night shelf style: ``7 s``, ``1 min 37 s``, ``1 h 5 min``."""
    if value is None or value < 0:
        return ""
    total = int(round(value))
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    if minutes:
        return f"{minutes} min {seconds} s" if seconds else f"{minutes} min"
    return f"{seconds} s"


_SITES = (
    ("youtube.com", "YouTube"), ("youtu.be", "YouTube"), ("instagram.com", "Instagram"),
    ("tiktok.com", "TikTok"), ("vimeo.com", "Vimeo"), ("soundcloud.com", "SoundCloud"),
    ("twitter.com", "X"), ("x.com", "X"), ("facebook.com", "Facebook"), ("twitch.tv", "Twitch"),
)


def site_name(url: str | None) -> str:
    """A short, friendly site name for a link (``YouTube``), else the plain host."""
    host = (urlsplit(url or "").hostname or "").lower()
    for suffix, name in _SITES:
        if host == suffix or host.endswith("." + suffix):
            return name
    return host[4:] if host.startswith("www.") else host


def host_title(url: str | None) -> str:
    """The link's host (``youtube.com``) as the stand-in title of a row not looked up yet."""
    host = (urlsplit(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or (url or "")


def stall_reason(hint: str | None, silent_for: float) -> str | None:
    """The reason to show next to "Starting..." once a row was quiet for ``STALL_AFTER`` seconds."""
    if silent_for < STALL_AFTER:
        return None
    return STALL_REASONS.get(hint or "")


def _is_post_link(url: str | None) -> bool:
    """True for a link the media engine may handle (photo post, story, highlight, slideshow)."""
    return _media.classify_media_url(url).kind not in (
        _media.MediaUrlKind.UNKNOWN, _media.MediaUrlKind.REEL)


def filter_of(state: str) -> str | None:
    """The count card a state is counted under (``None``: only in All)."""
    for key, states in _FILTER_STATES.items():
        if state in states:
            return key
    return None


@dataclass(frozen=True)
class RowText:
    """Everything a Downloads row says, as plain text (the delegate only paints it)."""

    meta: str          # "YouTube · 648.5 MB"
    big: str           # "37%" or a state word ("Waiting", "Done")
    big_is_percent: bool
    sub: str           # "4.2 MB/s · 1 min 37 s left"
    tone: str          # token of the right column: muted, faint, positive, negative
    bar: str | None    # None (no bar), "hue" or "faint"
    pill: str | None   # the one fix a failed row offers ("Retry"; the window turns it into "Sign in")
    note: str          # the item's remark ("" when none)


def _size_of(row: dict[str, Any]) -> float | None:
    progress = row.get("progress") or {}
    return progress.get("total_bytes") or progress.get("downloaded_bytes")


def describe_row(row: dict[str, Any], now: float | None = None) -> RowText:
    """Texts, tones and bar kind for one queue snapshot (states as in DESIGN.md "Row states").

    *now* (``time.monotonic()``) with the model's ``quiet_since`` stamp says how long the row
    has been silent, for the "Starting..." reason (brief 12C).
    """
    state = row["state"]
    since = row.get("quiet_since")
    silent = 0.0 if since is None else max(0.0, (time.monotonic() if now is None else now) - since)
    reason = stall_reason(row.get("wait_hint"), silent)
    progress = row.get("progress") or {}
    size = format_bytes(_size_of(row))
    files_total = progress.get("files_total")
    # "YouTube · 1080p MP4 · 648.5 MB", "Instagram · 6 photos + song · 3 of 7 files"
    meta_parts = [site_name(row.get("url")), row.get("format_label") or ""]
    bulk = row.get("bulk")
    if bulk:
        # Brief 10G, "Instagram · @user · 12 of 50 posts": the count is POSTS (the files
        # inside the current post stay out of the headline).
        meta_parts.append(bulk.get("label") or "")
        done = progress.get("files_done") or 0
        if files_total:
            noun = "post" if files_total == 1 else "posts"
            meta_parts.append(f"{files_total} {noun}" if state in ("done", "skipped") else f"{done} of {files_total} posts")
    elif files_total:
        done = progress.get("files_done") or 0
        meta_parts.append(f"{files_total} files" if state in ("done", "skipped") else f"{done} of {files_total} files")
    elif size:
        meta_parts.append(size)
    meta = " · ".join(p for p in meta_parts if p)
    note = row.get("note") or ""
    percent = DownloadModel.percent_of(row)
    pct = "" if percent is None else f"{percent:.0f}%"
    if state in _RUNNING:
        bits = [t for t in (format_speed(progress.get("speed")),
                            f"{eta_text(progress.get('eta'))} left" if progress.get("eta") is not None else "")
                if t and t != " left"]
        sub = " · ".join(bits) or {"merging": "Merging", "converting": "Converting"}.get(state, "Starting")
        if not bits and state == "downloading" and silent >= STALL_AFTER:
            sub = f"Starting... {reason}" if reason else "Starting..."
        return RowText(meta, pct or STATE_WORD[state], bool(pct), sub, "muted", "hue", None, note)
    if state == "paused":
        total, got = progress.get("total_bytes"), progress.get("downloaded_bytes")
        to_go = format_bytes(total - got) if total and got is not None and total > got else ""
        sub = f"Paused · {to_go} to go" if to_go else "Paused"
        return RowText(meta, pct or "Paused", bool(pct), sub, "muted", "faint" if pct else None, None, note)
    if state == "queued":
        wait = STALL_REASONS["rate_limited"] if row.get("wait_hint") == "rate_limited" else ""
        return RowText(meta, "Waiting", False, wait or size or "Starts next", "faint", None, None, note)
    if state == "probing":
        look = f"Starting... {reason}" if reason else "Looking at the link"
        return RowText(meta, "Checking", False, look, "faint", None, None, note)
    if state == "done":
        return RowText(meta, "Done", False, "Open · Show in folder", "positive", None, None, note)
    if state == "failed":
        error = row.get("error") or {}
        return RowText(meta, "", False, error.get("message") or "Could not finish", "negative",
                       None, "Retry", note)
    if state == "skipped":
        error = row.get("error") or {}
        return RowText(meta, "Skipped", False, error.get("message") or "", "faint", None, None, note)
    return RowText(meta, STATE_WORD.get(state, state), False, "", "faint", None,
                   "Retry" if state == "cancelled" else None, note)


class StateFilterProxy(QSortFilterProxyModel):
    """The download model seen through one count card (All, Downloading, Waiting, Failed, Done).

    Never sorted, so the rows keep the queue's own order. ``snapshot_at`` and
    ``item_id_at`` take a row of THIS model, so views and delegates can use it like
    the source model.
    """

    def __init__(self, source: DownloadModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = "all"
        self.setSourceModel(source)

    @property
    def filter_key(self) -> str:
        return self._key

    def set_filter(self, key: str) -> None:
        if key not in FILTERS or key == self._key:
            return
        begin = getattr(self, "beginFilterChange", None)
        if begin is not None:
            begin()
            self._key = key
            self.endFilterChange()
        else:  # PySide6 before 6.10
            self._key = key
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, parent: QModelIndex) -> bool:  # noqa: N802
        if self._key == "all":
            return True
        row = self.sourceModel().snapshot_at(source_row)
        return row is not None and row["state"] in _FILTER_STATES[self._key]

    def snapshot_at(self, row: int) -> dict[str, Any] | None:
        source = self.mapToSource(self.index(row, 0))
        return self.sourceModel().snapshot_at(source.row()) if source.isValid() else None

    def item_id_at(self, row: int) -> int | None:
        source = self.mapToSource(self.index(row, 0))
        return self.sourceModel().item_id_at(source.row()) if source.isValid() else None


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
        fresh = dict(snapshot)
        now = time.monotonic()
        fresh["quiet_since"] = now
        if row is None:
            position = len(self._rows)
            self.beginInsertRows(QModelIndex(), position, position)
            self._rows.append(fresh)
            self._index[item_id] = position
            self.endInsertRows()
            return
        old = self._rows[row]
        if old.get("state") == fresh.get("state") and old.get("progress") == fresh.get("progress"):
            fresh["quiet_since"] = old.get("quiet_since", now)  # nothing moved: still quiet
        self._rows[row] = fresh
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
        title = row.get("title")
        if title:
            return title
        if row.get("state") in ("queued", "probing") and _is_post_link(row.get("url")):
            return LOOKING_UP_TITLE  # a photo post, story tray or slideshow: the probe names it
        if row.get("state") in ("queued", "probing"):
            return host_title(row.get("url"))  # the instant card: the probe fills in the title
        return row.get("url") or ""

    @staticmethod
    def percent_of(row: dict[str, Any]) -> float | None:
        if row["state"] == "done":
            return 100.0
        progress = row.get("progress") or {}
        percent = progress.get("percent")
        if percent is None and progress.get("files_total"):  # photo posts count files
            percent = 100.0 * (progress.get("files_done") or 0) / progress["files_total"]
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
        if row.get("bulk") and progress.get("files_total") and state not in ("done", "skipped"):
            parts.append(f"{progress.get('files_done') or 0} of {progress['files_total']} posts")
        if state == "paused" and row.get("note"):
            parts.append(row["note"])
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
