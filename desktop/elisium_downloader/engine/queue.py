"""Download queue: concurrency, states, retry/backoff, archive reconcile.

Thread based and Qt free, so the UI layer subscribes with
:meth:`DownloadQueue.add_listener` and marshals events onto its own thread.
Every state is one of ``core-spec/SPEC.md``'s queue states and is written
through to :class:`~elisium_downloader.engine.history.History`.

Dedupe, per the spec:

* identity is ``video_key(url)`` (``youtube:<id>``) when the site is YouTube,
  else ``normalize_url(url)`` -- non-YouTube links would never dedupe with
  ``video_key`` alone, because it returns ``None`` for them;
* a second ``add`` of the same identity returns the existing item, unchanged;
* before downloading, the archive is reconciled against the output folder so a
  video whose file was deleted downloads again.

Archive safety (added after the 1B audit): :class:`Archive` rewrites the whole
file, and a running yt-dlp appends to the same file, so every archive call in
this module is serialised behind one lock and the archive is never rewritten
while any item is in ``downloading``/``merging``/``converting``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import media, mix, runner
from .archive import Archive, _file_exists, reconcile
from .errors import (
    GALLERY_DL_MISSING,
    ErrorInfo,
    apply_context,
    explain,
    explain_gallery,
)
from .history import History, TERMINAL_STATES
from .urlnorm import normalize_url, video_key

__all__ = [
    "ACTIVE_STATES",
    "DOWNLOADING_STATES",
    "BACKOFF",
    "RETRYABLE_CODES",
    "MAX_CONCURRENCY",
    "DEFAULT_CONCURRENCY",
    "REUSE_PROBE_MAX_AGE",
    "ALREADY_DOWNLOADED",
    "QueueItem",
    "DownloadQueue",
]

# Retry schedule from the spec: wait 5s, 15s, 45s, then give up.
BACKOFF: tuple[float, ...] = (5.0, 15.0, 45.0)
# Only these error codes are retried (the spec says "on network errors").
RETRYABLE_CODES: frozenset[str] = frozenset({"network"})
DOWNLOADING_STATES: frozenset[str] = frozenset(
    {"downloading", "merging", "converting"}
)
ACTIVE_STATES: frozenset[str] = frozenset({"probing"}) | DOWNLOADING_STATES
MAX_CONCURRENCY = 5
DEFAULT_CONCURRENCY = 2

# Brief 12B: a probe's info JSON drives the download (``--load-info-json``)
# instead of extracting the page twice. Media URLs in it expire, so it is only
# reused when the probe finished less than this many seconds before the
# download starts.
REUSE_PROBE_MAX_AGE = 300.0
# An info-JSON run that fails like this is re-run once straight from the URL.
_STALE_INFO_CODES: frozenset[str] = frozenset(
    {"http_403", "http_410", "format_unavailable"}
)
_STALE_INFO_TEXT: tuple[str, ...] = (
    "http error 410",
    "expired",
    "requested format is not available",
    "no video formats found",
    "format is not available",
)

ALREADY_DOWNLOADED = ErrorInfo(
    "Already downloaded.", "It is in the download folder", "already_downloaded"
)
_UNKNOWN = ErrorInfo("Download failed.", "See Details", "unknown")
# yt-dlp prints this and exits 0 when the archive already holds the video.
_ARCHIVE_SKIP_TEXT = "has already been recorded in the archive"


def _check_concurrency(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"concurrency must be an int, got {value!r}")
    if not 1 <= value <= MAX_CONCURRENCY:
        raise ValueError(
            f"concurrency must be between 1 and {MAX_CONCURRENCY}, got {value}"
        )
    return value


def _title_from(info: Any) -> str | None:
    if not isinstance(info, Mapping):
        return None
    title = info.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def _info_is_usable(info: Any, age: float | None) -> bool:
    """True when the probe's info dict can drive the download (brief 12B).

    *age* is how many seconds passed between the probe finishing and the
    download starting. A story tray is probed flat, so a playlist dict must
    download from its URL instead.
    """
    if not isinstance(info, dict):
        return False
    if info.get("_type") == "playlist":
        return False
    if not (info.get("formats") or info.get("url")):
        return False
    return age is not None and 0 <= age < REUSE_PROBE_MAX_AGE


def _write_info_json(path: Path, info: Mapping[str, Any]) -> bool:
    """Write *info* to *path*, readable only by the owner (mode 0600).

    The probe JSON can hold signed media URLs and request headers, so the file
    is created fresh (never through a symlink) with mode 0600 and the caller
    deletes it after the attempt. Returns False when it could not be written.
    """
    try:
        path.unlink(missing_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
    except OSError:
        return False
    try:
        stream = os.fdopen(fd, "w", encoding="utf-8")
    except OSError:
        try:
            os.close(fd)
        except OSError:
            pass
        _unlink_quietly(path)
        return False
    try:
        with stream:
            json.dump(info, stream)
    except (OSError, TypeError, ValueError):
        _unlink_quietly(path)
        return False
    return True


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _is_stale_info_failure(error: ErrorInfo, raw: str) -> bool:
    """True when a failure looks like an expired/refused media URL (brief 12B)."""
    if error.code in _STALE_INFO_CODES:
        return True
    lowered = raw.lower()
    return any(text in lowered for text in _STALE_INFO_TEXT)


class _ReadOnlyArchive:
    """Archive view that can read but never rewrite the file.

    Used while an item is downloading: yt-dlp is appending to the archive, and
    ``Archive.remove`` rewrites the whole file, which would lose that append.
    A stale entry that cannot be removed simply means the video downloads
    again -- the safe direction.
    """

    def __init__(self, archive: Archive) -> None:
        self._archive = archive

    @property
    def path(self) -> Path:
        return self._archive.path

    def has(self, extractor: str, video_id: str) -> bool:
        return self._archive.has(extractor, video_id)

    def remove(self, extractor: str, video_id: str) -> bool:  # noqa: ARG002
        return False


@dataclass
class QueueItem:
    """One queued download. Read it through :meth:`snapshot`."""

    id: int
    record_id: int
    url: str
    identity: str
    video_key: str | None = None
    state: str = "queued"
    title: str | None = None
    file_path: str | None = None
    error: ErrorInfo | None = None
    attempts: int = 0
    stage: str | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    eta: float | None = None
    percent: float | None = None
    handle: Any = None
    owned: bool = False
    # ``<extractor>:<id>`` as yt-dlp archives it, learned from the probe for
    # sites where ``video_key`` is None (not part of the snapshot).
    archive_key: str | None = None
    # Per-item overrides from the "Choose quality" dialogs; ``None`` means
    # "use the queue default" (an empty ``extra_args`` tuple is a real override).
    format_selector: str | None = None
    extra_args: tuple[str, ...] | None = None
    # Media engine (gallery-dl) items count files instead of bytes.
    files_done: int | None = None
    files_total: int | None = None
    # A short plain-language remark on a finished item (brief 10B-2), e.g.
    # "Kept the full song: ...". Not stored in the history.
    note: str | None = None

    def snapshot(self) -> dict[str, Any]:
        """A plain-dict view for the UI and for events."""
        return {
            "id": self.id,
            "record_id": self.record_id,
            "url": self.url,
            "identity": self.identity,
            "video_key": self.video_key,
            "state": self.state,
            "title": self.title,
            "file_path": self.file_path,
            "note": self.note,
            "attempts": self.attempts,
            "error": None
            if self.error is None
            else {
                "code": self.error.code,
                "message": self.error.message,
                "fix": self.error.fix,
            },
            "progress": {
                "stage": self.stage,
                "downloaded_bytes": self.downloaded_bytes,
                "total_bytes": self.total_bytes,
                "speed": self.speed,
                "eta": self.eta,
                "percent": self.percent,
                "files_done": self.files_done,
                "files_total": self.files_total,
            },
        }


class DownloadQueue:
    """A bounded, thread-based download queue.

    Events go to every listener as dicts:

    * ``{"type": "added", "item": {...}}``
    * ``{"type": "state", "id", "state", "previous", "item"}``
    * ``{"type": "progress", "id", "state", "item"}``
    * ``{"type": "item", "id", "item"}`` (title arrived, no state change)

    Listeners run on queue threads while the queue lock is held: they must be
    quick and must not block on the queue.
    """

    def __init__(
        self,
        history: History,
        archive: Archive,
        output_dir: str | os.PathLike[str],
        temp_dir: str | os.PathLike[str],
        *,
        concurrency: int = DEFAULT_CONCURRENCY,
        ytdlp: str = "yt-dlp",
        format_selector: str = runner.DEFAULT_FORMAT,
        limit_rate: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        run_download: Callable[..., Any] = runner.run,
        probe_url: Callable[..., dict[str, Any]] = runner.probe,
        reuse_probe: bool = True,
        clock: Callable[[], float] = time.monotonic,
        gallery_dl: str | None = None,
        probe_media: Callable[..., media.MediaPlan] = media.probe,
        run_media: Callable[..., Any] = media.run,
        gallery_config: str | os.PathLike[str] | None = None,
        gallery_archive: str | os.PathLike[str] | None = None,
        ffmpeg: str | None = None,
        ffprobe: str | None = None,
    ) -> None:
        self.history = history
        self.archive = archive
        self.output_dir = Path(output_dir).expanduser()
        self.temp_dir = Path(temp_dir).expanduser()
        self._ytdlp = ytdlp
        self._format_selector = format_selector
        self._limit_rate = limit_rate
        self._extra_args: tuple[str, ...] = ()
        self._cookies_browser: str | None = None
        self._cookies_file: str | None = None
        self._sleep = sleep
        self._run_download = run_download
        self._probe_url = probe_url
        self._reuse_probe = bool(reuse_probe)
        self._clock = clock
        # Brief 10B-1: photo posts, stories and slideshows go to gallery-dl.
        # ``None`` means "look it up on PATH when needed". The config lives
        # next to the temp folder (the cache dir) and gallery-dl's own archive
        # next to archive.txt (the data dir), so tests never touch real paths.
        self._gallery_dl = gallery_dl
        self._probe_media = probe_media
        self._run_media = run_media
        self._gallery_config = Path(
            gallery_config
            if gallery_config is not None
            else self.temp_dir.parent / "gallery-dl.json"
        ).expanduser()
        self._gallery_archive = Path(
            gallery_archive
            if gallery_archive is not None
            else self.archive.path.parent / "gallery-archive.sqlite3"
        ).expanduser()
        # Brief 10B-2: song snippet + photo/song video; ``None`` = look up on PATH.
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe
        self._concurrency = _check_concurrency(concurrency)

        self._items: dict[int, QueueItem] = {}
        self._order: list[int] = []
        self._by_identity: dict[str, int] = {}
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._next_id = 1

        # One lock for item state, one for the archive file. Lock order is
        # always state lock -> archive lock (see _is_archived).
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._archive_lock = threading.Lock()
        self._threads: set[threading.Thread] = set()
        self._scheduler: threading.Thread | None = None
        self._running = False

    # -- configuration ---------------------------------------------------
    @property
    def concurrency(self) -> int:
        return self._concurrency

    def set_concurrency(self, value: int) -> None:
        """Change the number of parallel downloads (1-5)."""
        checked = _check_concurrency(value)
        with self._cond:
            self._concurrency = checked
            self._cond.notify_all()

    def set_limit_rate(self, value: str | None) -> None:
        """Set ``--limit-rate`` (e.g. ``"2M"``; ``None`` for no limit).

        Applies to downloads that START after this call; running ones keep
        their old value.
        """
        with self._cond:
            self._limit_rate = value or None

    def set_format_selector(self, selector: str) -> None:
        """Set the yt-dlp ``-f`` selector for downloads that start after this call."""
        if not isinstance(selector, str) or not selector:
            raise ValueError("format selector must be a non-empty string")
        with self._cond:
            self._format_selector = selector

    def set_extra_args(self, args: Sequence[str]) -> None:
        """Set extra yt-dlp arguments for downloads that start after this call."""
        with self._cond:
            self._extra_args = tuple(str(a) for a in args)

    def set_cookies(
        self, browser: str | None, file: str | os.PathLike[str] | None
    ) -> None:
        """Set how yt-dlp signs in (``--cookies-from-browser`` / ``--cookies``).

        Applies to probes and downloads that start after this call. Only the
        browser name and the file path are kept: the app never reads, copies or
        logs the cookie contents, and they never reach history.
        """
        with self._cond:
            self._cookies_browser = str(browser) if browser else None
            self._cookies_file = None if file is None else str(file)

    def _cookies_configured(self) -> bool:
        """True when a browser or a cookies file is set (contents never read)."""
        with self._cond:
            return bool(self._cookies_browser or self._cookies_file)

    def add_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

    # -- reading ---------------------------------------------------------
    @property
    def ytdlp(self) -> str:
        """The yt-dlp executable this queue runs."""
        return self._ytdlp

    def probe(self, url: str) -> dict[str, Any]:
        """Probe *url* with the queue's own probe function and yt-dlp path.

        Uses the queue's current cookie setting, so Instagram stories can be
        probed when the user has chosen a browser. Blocks while yt-dlp runs, so
        call it from a worker thread.
        """
        with self._cond:
            browser, file = self._cookies_browser, self._cookies_file
        return self._probe_url(
            url,
            self._ytdlp,
            cookies_browser=browser,
            cookies_file=file,
        )

    def items(self) -> list[dict[str, Any]]:
        """Every item, oldest first, as snapshots."""
        with self._cond:
            return [self._items[item_id].snapshot() for item_id in self._order]

    def item(self, item_id: int) -> dict[str, Any] | None:
        with self._cond:
            found = self._items.get(item_id)
            return None if found is None else found.snapshot()

    def states(self) -> dict[int, str]:
        """``{item id: state}`` for every item (cheap UI refresh)."""
        with self._cond:
            return {item_id: item.state for item_id, item in self._items.items()}

    def active_ids(self) -> list[int]:
        with self._cond:
            return [
                item_id
                for item_id in self._order
                if self._items[item_id].state in ACTIVE_STATES
            ]

    # -- adding ----------------------------------------------------------
    def add(
        self,
        url: str,
        *,
        format_selector: str | None = None,
        extra_args: Sequence[str] | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Queue *url*; a duplicate of an existing item returns that item.

        *format_selector* and *extra_args* override the queue defaults for this
        item only; *title* is shown until the probe supplies the real one. A
        duplicate keeps its original overrides (the existing item is returned
        unchanged).

        Raises ``ValueError`` for a URL that cannot be normalised.
        """
        if not isinstance(url, str) or not url.strip():
            raise ValueError("url must be a non-empty string")
        clean = url.strip()
        normalised = normalize_url(clean)
        key = video_key(clean)
        identity = key or normalised

        with self._cond:
            existing = self._by_identity.get(identity)
            if existing is not None:
                found = self._items[existing]
                if found.state in ("done", "skipped") and not self._file_present(
                    found
                ):
                    self._requeue_missing(found)
                return found.snapshot()
            record_id = self.history.add(clean, video_key=identity, state="queued")
            item = QueueItem(
                id=self._next_id,
                record_id=record_id,
                url=clean,
                identity=identity,
                video_key=key,
                title=title.strip() if isinstance(title, str) and title.strip() else None,
                format_selector=format_selector or None,
                extra_args=None if extra_args is None else tuple(str(a) for a in extra_args),
            )
            self._next_id += 1
            self._items[item.id] = item
            self._order.append(item.id)
            self._by_identity[identity] = item.id
            snapshot = item.snapshot()
            self._cond.notify_all()
            self._emit({"type": "added", "item": snapshot})
        return snapshot

    def _file_present(self, item: QueueItem) -> bool:
        """False only when we can tell the finished file is gone.

        If the item has neither a known path nor an id to scan for, there is
        nothing to check and the existing item is kept.
        """
        key = item.video_key or item.archive_key
        if item.file_path is None and key is None:
            return True
        if item.file_path is not None and os.path.isfile(item.file_path):
            return True
        if key is not None:
            _, _, video_id = key.partition(":")
            if video_id and _file_exists(self.output_dir, video_id):
                return True
        return False

    def _requeue_missing(self, item: QueueItem) -> None:
        """Put a done/skipped item whose file was deleted back to ``queued``.

        Caller holds the state lock. The stale archive entry is dropped under
        the archive lock, and only while no download is active (yt-dlp appends
        to the archive and :meth:`Archive.remove` rewrites it). If a download
        is active the entry stays; ``_attempt`` reconciles again later.
        """
        key = item.video_key or item.archive_key
        if key is not None and not self._downloading():
            extractor, _, video_id = key.partition(":")
            if extractor and video_id:
                with self._archive_lock:
                    try:
                        self.archive.remove(extractor, video_id)
                    except (OSError, ValueError):
                        pass
        item.error = None
        item.attempts = 0
        item.file_path = None
        item.percent = None
        item.stage = None
        item.downloaded_bytes = None
        item.total_bytes = None
        item.speed = None
        item.eta = None
        self._set_state(item, "queued", clear_error=True)
        self._cond.notify_all()

    # -- user actions ----------------------------------------------------
    def pause(self, item_id: int) -> bool:
        """Pause one item. A download is terminated; ``.part`` files stay."""
        with self._cond:
            item = self._items.get(item_id)
            if item is None:
                return False
            if item.state in ACTIVE_STATES:
                handle = item.handle
                self._set_state(item, "paused")
                if handle is not None:
                    handle.terminate()
                self._cond.notify_all()
                return True
            if item.state == "queued":
                self._set_state(item, "paused")
                self._cond.notify_all()
                return True
            return False

    def resume(self, item_id: int) -> bool:
        """Queue a paused item again; the download reruns with ``--continue``."""
        with self._cond:
            item = self._items.get(item_id)
            if item is None or item.state != "paused":
                return False
            item.error = None
            item.percent = None
            self._set_state(item, "queued", clear_error=True)
            self._cond.notify_all()
            return True

    def retry(self, item_id: int) -> bool:
        """Put a failed or cancelled item back in the queue, backoff reset."""
        with self._cond:
            item = self._items.get(item_id)
            if item is None or item.state not in ("failed", "cancelled"):
                return False
            item.error = None
            item.attempts = 0
            item.percent = None
            self._set_state(item, "queued", clear_error=True)
            self._cond.notify_all()
            return True

    def cancel(self, item_id: int) -> bool:
        """Cancel one item; a running download is terminated."""
        with self._cond:
            item = self._items.get(item_id)
            if item is None or item.state in TERMINAL_STATES:
                return False
            handle = item.handle
            self._set_state(item, "cancelled", clear_error=True)
            if handle is not None:
                handle.terminate()
            self._cond.notify_all()
            return True

    # -- lifecycle -------------------------------------------------------
    def start(self) -> None:
        """Start the scheduler (idempotent)."""
        with self._cond:
            if self._running:
                return
            self._running = True
            if self._scheduler is None or not self._scheduler.is_alive():
                self._scheduler = threading.Thread(
                    target=self._schedule, name="elisium-scheduler", daemon=True
                )
                self._scheduler.start()
            self._cond.notify_all()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the scheduler and pause everything that was running."""
        deadline = time.monotonic() + max(timeout, 0.0)
        with self._cond:
            self._running = False
            handles = [
                item.handle
                for item in self._items.values()
                if item.state in ACTIVE_STATES
            ]
            for item in self._items.values():
                if item.state in ACTIVE_STATES:
                    self._set_state(item, "paused")
            self._cond.notify_all()
            threads = list(self._threads)
            scheduler = self._scheduler
        for handle in handles:
            if handle is not None:
                handle.terminate()
        for thread in ([scheduler] if scheduler is not None else []) + threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(remaining)

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        """Wait until nothing is running or waiting to run."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while True:
                if self._idle():
                    return True
                remaining = (
                    None if deadline is None else deadline - time.monotonic()
                )
                if remaining is not None and remaining <= 0:
                    return False
                self._cond.wait(remaining)

    # -- internals: state ------------------------------------------------
    def _emit(self, event: dict[str, Any]) -> None:
        for callback in list(self._listeners):
            try:
                callback(event)
            except Exception:  # a broken listener must not break the queue
                pass

    def _set_state(
        self,
        item: QueueItem,
        state: str,
        *,
        error: ErrorInfo | None = None,
        file_path: str | None = None,
        clear_error: bool = False,
    ) -> None:
        """Move *item* to *state*, write it to history, emit the event."""
        previous = item.state
        if previous == state:
            return
        item.state = state
        kwargs: dict[str, Any] = {}
        if error is not None:
            kwargs["error_code"] = error.code
            kwargs["error_message"] = error.message
        if clear_error:
            kwargs["clear_error"] = True
        if file_path is not None:
            kwargs["file_path"] = file_path
        self.history.update_state(item.record_id, state, **kwargs)
        self._emit(
            {
                "type": "state",
                "id": item.id,
                "state": state,
                "previous": previous,
                "item": item.snapshot(),
            }
        )

    def _idle(self) -> bool:
        for item in self._items.values():
            if item.owned or item.state in ACTIVE_STATES or item.state == "queued":
                return False
        return True

    def _downloading(self) -> bool:
        return any(
            item.state in DOWNLOADING_STATES for item in self._items.values()
        )

    def _owned(self) -> int:
        return sum(1 for item in self._items.values() if item.owned)

    def _next_queued(self) -> QueueItem | None:
        for item_id in self._order:
            item = self._items[item_id]
            if item.state == "queued" and not item.owned:
                return item
        return None

    # -- internals: scheduling -------------------------------------------
    def _schedule(self) -> None:
        try:
            while True:
                with self._cond:
                    while True:
                        if not self._running:
                            return
                        if self._owned() < self._concurrency:
                            item = self._next_queued()
                            if item is not None:
                                # Claim the slot before starting, so the loop
                                # cannot over-fill while the worker spins up.
                                item.owned = True
                                thread = threading.Thread(
                                    target=self._work,
                                    args=(item,),
                                    name=f"elisium-item-{item.id}",
                                    daemon=True,
                                )
                                self._threads.add(thread)
                                thread.start()
                                continue
                        self._cond.wait()
        finally:
            with self._cond:
                # Lets start() spawn a fresh scheduler after a stop().
                if self._scheduler is threading.current_thread():
                    self._scheduler = None

    def _work(self, item: QueueItem) -> None:
        try:
            self._run_item(item)
        except Exception:  # pragma: no cover - defensive
            with self._cond:
                if item.state in ACTIVE_STATES or item.state == "queued":
                    item.error = _UNKNOWN
                    self._set_state(item, "failed", error=_UNKNOWN)
        finally:
            with self._cond:
                item.owned = False
                item.handle = None
                self._threads.discard(threading.current_thread())
                self._cond.notify_all()

    def _run_item(self, item: QueueItem) -> None:
        while True:
            delay = self._attempt(item)
            if delay is None:
                return
            self._sleep(delay)
            with self._cond:
                if not self._running or item.state != "queued" or not item.owned:
                    return

    # -- internals: one attempt ------------------------------------------
    def _attempt(self, item: QueueItem) -> float | None:
        """Route, probe, reconcile, download once.

        Returns ``None`` when the item is finished with (terminal, paused or
        stopped) or the number of seconds to wait before the next attempt.

        Story trays, highlights and TikTok photo posts go straight to the media
        engine. An Instagram post (or single story) goes to yt-dlp first and,
        if yt-dlp says "no video in this post", to the media engine at once:
        no retry is counted and nothing sleeps. Everything else is yt-dlp.
        """
        with self._cond:
            if not self._running or item.state != "queued" or not item.owned:
                return None
            item.error = None
            item.percent = None
            item.downloaded_bytes = None
            item.total_bytes = None
            item.speed = None
            item.eta = None
            item.files_done = None
            item.files_total = None
            item.note = None
            self._set_state(item, "probing")

        route = media.route_for(item.url)
        if route == "media":
            error = self._media_attempt(item)
        else:
            error = self._ytdlp_attempt(item)
            if (
                route == "ytdlp_then_media"
                and error is not None
                and error.code == "no_media"
            ):
                error = self._media_fallback(item)
        if error is None:
            return None
        return self._after_failure(item, error)

    def _ytdlp_attempt(self, item: QueueItem) -> ErrorInfo | None:
        """The yt-dlp path: probe, archive reconcile, download. ``None`` = handled."""
        info: Mapping[str, Any] | None = None
        probed_at: float | None = None
        error: ErrorInfo | None = None
        try:
            info = self.probe(item.url)
            probed_at = self._clock()
        except runner.ProbeError as exc:
            # Same wording rules as a failed download: the site, not "Instagram".
            error = apply_context(exc.info, item.url, self._cookies_configured())
        except OSError:  # pragma: no cover - defensive
            error = _UNKNOWN
        else:
            self._learn_archive_key(item, info)
            title = _title_from(info)
            if title is not None:
                with self._cond:
                    item.title = title
                    self._emit(
                        {"type": "item", "id": item.id, "item": item.snapshot()}
                    )

        if error is None:
            with self._cond:
                if not self._running or item.state != "probing":
                    return None  # paused or cancelled while probing
            if self._is_archived(item):
                with self._cond:
                    if item.state == "probing":
                        self._set_state(item, "skipped", error=ALREADY_DOWNLOADED)
                return None
            with self._cond:
                if not self._running or item.state != "probing":
                    return None
                self._set_state(item, "downloading")
            error, _raw = self._download(item, info, probed_at)
        return error

    def _media_fallback(self, item: QueueItem) -> ErrorInfo | None:
        """Re-run an item the media engine's way after yt-dlp found no video."""
        with self._cond:
            if (
                not self._running
                or not item.owned
                or item.state not in ACTIVE_STATES
            ):
                return None
            item.error = None
            item.percent = None
            item.downloaded_bytes = None
            item.total_bytes = None
            item.speed = None
            item.eta = None
            if item.state != "probing":
                self._set_state(item, "probing")
        return self._media_attempt(item)

    @staticmethod
    def _learn_archive_key(item: QueueItem, info: Any) -> None:
        if item.video_key is not None or not isinstance(info, Mapping):
            return
        extractor = info.get("extractor_key") or info.get("extractor")
        video_id = info.get("id")
        if (
            isinstance(extractor, str)
            and isinstance(video_id, str)
            and extractor.strip()
            and video_id.strip()
            and not any(ch.isspace() for ch in extractor + video_id)
        ):
            item.archive_key = f"{extractor.lower()}:{video_id}"

    def _after_failure(
        self, item: QueueItem, error: ErrorInfo
    ) -> float | None:
        with self._cond:
            if (
                not self._running
                or item.state in TERMINAL_STATES
                or item.state == "paused"
            ):
                return None
            item.error = error
            if error.code in RETRYABLE_CODES and item.attempts < len(BACKOFF):
                delay = BACKOFF[item.attempts]
                item.attempts += 1
                # Back to queued while waiting, but keep the worker slot: the
                # scheduler only picks items that no worker owns.
                self._set_state(item, "queued")
                return delay
            self._set_state(item, "failed", error=error)
            return None

    def _download(
        self,
        item: QueueItem,
        info: Mapping[str, Any] | None = None,
        probed_at: float | None = None,
    ) -> tuple[ErrorInfo | None, str]:
        """Run the download for one attempt.

        Returns ``(None, raw)`` on success and on a user pause/cancel, and
        ``(ErrorInfo, raw)`` for a real failure. When the probe's *info* is
        usable the run loads it (``--load-info-json``) instead of extracting
        the page again; if that run fails the way an expired media URL does,
        one more run goes straight from the URL (no retry count, no backoff).
        """
        info_path: Path | None = None
        if self._reuse_probe:
            age = None if probed_at is None else self._clock() - probed_at
            if info is not None and _info_is_usable(info, age):
                candidate = self.temp_dir / f"{item.id}.info.json"
                try:
                    self.temp_dir.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
                if _write_info_json(candidate, info):
                    info_path = candidate
        if info_path is None:
            error, raw, _progressed = self._download_once(item, None)
            return error, raw
        try:
            error, raw, progressed = self._download_once(item, info_path)
        finally:
            _unlink_quietly(info_path)
        if error is None:
            return None, raw
        # Re-run from the URL when the info run died before any progress or
        # failed like an expired/refused media URL; anything else is final.
        if progressed and not _is_stale_info_failure(error, raw):
            return error, raw
        with self._cond:
            if not self._running or item.state not in DOWNLOADING_STATES:
                return error, raw
            if item.state != "downloading":
                self._set_state(item, "downloading")
        error, raw, _progressed = self._download_once(item, None)
        return error, raw

    def _download_once(
        self, item: QueueItem, info_path: Path | None
    ) -> tuple[ErrorInfo | None, str, bool]:
        """One yt-dlp run; the last value says whether a progress line arrived."""
        path_file = self.temp_dir / f"item-{item.id}.path"
        try:
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            path_file.unlink(missing_ok=True)
        except OSError:
            pass
        with self._cond:
            selector = item.format_selector or self._format_selector
            limit = self._limit_rate
            extra = (
                item.extra_args if item.extra_args is not None else self._extra_args
            )
            cookies_browser = self._cookies_browser
            cookies_file = self._cookies_file
        opts = runner.DownloadOptions(
            url=item.url,
            output_dir=self.output_dir,
            temp_dir=self.temp_dir,
            archive_path=self.archive.path,
            format_selector=selector,
            limit_rate=limit,
            extra_args=extra,
            ytdlp=self._ytdlp,
            path_file=path_file,
            cookies_browser=cookies_browser,
            cookies_file=cookies_file,
            info_json=info_path,
        )
        progressed = False

        def on_event(event: Any) -> None:
            nonlocal progressed
            if isinstance(event, Mapping) and event.get("type") == "progress":
                progressed = True
            self._on_progress(item, event)

        handle = self._run_download(opts, on_event)
        with self._cond:
            item.handle = handle
            stop_now = item.state in ("paused", "cancelled")
        if stop_now:
            handle.terminate()
        handle.wait()
        raw = handle.raw_log
        returncode = handle.returncode
        terminated = bool(getattr(handle, "terminated", False))

        with self._cond:
            item.handle = None
            if item.state in ("paused", "cancelled"):
                self._discard(path_file)
                return None, raw, progressed

        if returncode == 0 and not terminated:
            reported = self._read_path_file(path_file)
            self._discard(path_file)
            if reported is None and _ARCHIVE_SKIP_TEXT in raw:
                # yt-dlp exited 0 but downloaded nothing: the archive had it.
                with self._cond:
                    if item.state in DOWNLOADING_STATES:
                        item.error = ALREADY_DOWNLOADED
                        self._set_state(item, "skipped", error=ALREADY_DOWNLOADED)
                return None, raw, progressed
            path = reported or self._find_output(item)
            with self._cond:
                item.file_path = path
                item.percent = 100.0
                self._set_state(item, "done", file_path=path)
            return None, raw, progressed
        self._discard(path_file)
        return explain(raw, item.url, self._cookies_configured()), raw, progressed

    # -- internals: the media engine (gallery-dl) ------------------------
    def _media_attempt(self, item: QueueItem) -> ErrorInfo | None:
        """Probe and download *item* with gallery-dl (state is ``probing``).

        Returns ``None`` on success and on a user pause/cancel, else the
        plain-language failure. A missing gallery-dl is ``gallery_dl_missing``.
        """
        binary = self._gallery_dl or media.find_gallery_dl()
        if not binary:
            return GALLERY_DL_MISSING
        with self._cond:
            browser, cookie_file = self._cookies_browser, self._cookies_file
            limit = self._limit_rate
        has_cookies = bool(browser or cookie_file)
        try:
            config = media.write_config(self._gallery_config)
        except OSError:
            return _UNKNOWN
        try:
            plan = self._probe_media(
                item.url,
                binary,
                config_path=config,
                cookies_browser=browser,
                cookies_file=cookie_file,
            )
        except media.MediaProbeError as exc:
            return exc.info
        except OSError:
            return GALLERY_DL_MISSING

        with self._cond:
            if not self._running or item.state != "probing":
                return None  # paused or cancelled while probing
            title = plan.display_title
            if title is not None:
                item.title = title
            item.files_done = 0
            # A song plus pictures also gives one mp4: it counts as a file.
            mix_post = self._mix_post_id(item, plan)
            item.files_total = plan.total + (1 if mix_post else 0)
            self._emit({"type": "item", "id": item.id, "item": item.snapshot()})
            self._set_state(item, "downloading")

        directory = media.item_directory(self.temp_dir, item.identity)
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            return _UNKNOWN
        opts = media.MediaOptions(
            url=item.url,
            directory=directory,
            config_path=config,
            archive_path=self._gallery_archive,
            gallery_dl=str(binary),
            limit_rate=limit,
            cookies_browser=browser,
            cookies_file=cookie_file,
        )
        try:
            self._gallery_archive.parent.mkdir(parents=True, exist_ok=True)
            handle = self._run_media(
                opts,
                lambda event: self._on_progress(item, event),
                files_total=item.files_total,
            )
        except OSError:
            return GALLERY_DL_MISSING
        with self._cond:
            item.handle = handle
            stop_now = item.state in ("paused", "cancelled")
        if stop_now:
            handle.terminate()
        handle.wait()
        raw = handle.raw_log
        returncode = handle.returncode
        terminated = bool(getattr(handle, "terminated", False))

        with self._cond:
            item.handle = None
            if item.state in ("paused", "cancelled"):
                return None  # staged files stay; a resume moves them later

        owner = plan.owner or media.classify_media_url(item.url).username
        if returncode == 0 and not terminated:
            # Brief 10B-2: cut the post's song, build the photo + song video.
            if self._convert_media(item, plan, directory, owner, mix_post):
                return None  # paused or cancelled while converting
        # Move whatever finished, even after a failure: a retry then only
        # fetches the files that are still missing (the archive skips the rest).
        moved = media.finalize(directory, self.output_dir, owner)
        first = moved.first
        if returncode == 0 and not terminated:
            with self._cond:
                if item.state not in DOWNLOADING_STATES:
                    return None
                finished = list(getattr(handle, "finished", ()))
                if moved.moved or (finished and not moved.existing):
                    item.file_path = None if first is None else str(first)
                    item.percent = 100.0
                    item.files_done = (
                        item.files_total if item.files_total is not None else plan.total
                    )
                    self._set_state(item, "done", file_path=item.file_path)
                else:
                    # Nothing new: every file was skipped (archive, or a file
                    # of that name was already in the output folder).
                    item.file_path = None if first is None else str(first)
                    item.error = ALREADY_DOWNLOADED
                    self._set_state(item, "skipped", error=ALREADY_DOWNLOADED)
            return None
        if first is not None and moved.moved:
            with self._cond:
                item.file_path = str(first)
        return explain_gallery(raw, item.url, has_cookies)

    def _mix_post_id(self, item: QueueItem, plan: media.MediaPlan) -> str | None:
        """The post id for the ``[<id>_mix]`` name when a mix is expected, else ``None``.

        Expected: one post (an Instagram post / story or a TikTok photo post,
        not a story tray or highlight) with exactly one song and at least one
        picture, and ffmpeg is installed.
        """
        parsed = media.classify_media_url(item.url)
        if parsed.kind not in (
            media.MediaUrlKind.POST,
            media.MediaUrlKind.STORY_ITEM,
            media.MediaUrlKind.TIKTOK_PHOTO,
        ):
            return None
        audio = sum(1 for f in plan.files if f.is_audio)
        if audio != 1 or plan.total - audio < 1:
            return None
        if not (self._ffmpeg or mix.find_ffmpeg()):
            return None
        return self._post_id(item, plan)

    @staticmethod
    def _post_id(item: QueueItem, plan: media.MediaPlan) -> str | None:
        parsed = media.classify_media_url(item.url)
        return (
            plan.shortcode
            or plan.post_id
            or parsed.shortcode
            or parsed.tiktok_id
            or parsed.story_id
        )

    def _convert_media(
        self,
        item: QueueItem,
        plan: media.MediaPlan,
        directory: Path,
        owner: str | None,
        mix_post: str | None,
    ) -> bool:
        """Song snippet + mix video in the staging folder; ``True`` = stop (paused/cancelled).

        Never fails the item: problems become :attr:`QueueItem.note`.
        """
        post_id = mix_post or self._post_id(item, plan)
        parsed = media.classify_media_url(item.url)
        if post_id is None or parsed.kind not in (
            media.MediaUrlKind.POST,
            media.MediaUrlKind.STORY_ITEM,
            media.MediaUrlKind.TIKTOK_PHOTO,
        ):
            return False
        folder = media.safe_folder_name(owner)
        existing = self.output_dir / folder if folder else self.output_dir
        job = mix.MixJob()

        def converting() -> None:
            with self._cond:
                if item.state in DOWNLOADING_STATES:
                    item.handle = job
                    item.stage = "converting"
                    self._set_state(item, "converting")

        try:
            result = mix.process_staging(
                directory,
                post_id=post_id,
                site=plan.site or parsed.site,
                existing_dir=existing,
                ffmpeg=self._ffmpeg,
                ffprobe=self._ffprobe,
                job=job,
                on_convert=converting,
            )
        except Exception:  # an extra must never fail the download
            result = mix.MixResult(note=mix.MIX_FAILED_NOTE if mix_post else None)
        with self._cond:
            item.handle = None
            if item.state in ("paused", "cancelled"):
                return True
            item.note = result.note
            if mix_post and result.video is None and item.files_total:
                item.files_total -= 1  # the mp4 was not made (or already exists)
            elif not mix_post and result.video is not None:
                item.files_total = (item.files_total or plan.total) + 1
        return False

    @staticmethod
    def _read_path_file(path_file: Path) -> str | None:
        """Last non-empty line of yt-dlp's ``--print-to-file`` output."""
        try:
            text = path_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[-1] if lines else None

    @staticmethod
    def _discard(path_file: Path) -> None:
        try:
            path_file.unlink(missing_ok=True)
        except OSError:
            pass

    def _on_progress(self, item: QueueItem, event: Any) -> None:
        if not isinstance(event, Mapping) or event.get("type") != "progress":
            return
        stage = event.get("stage")
        with self._cond:
            if item.state in TERMINAL_STATES or item.state == "paused":
                return
            housekeeping = bool(event.get("postprocessor")) and stage == "downloading"
            if stage in runner.STAGES and item.state != stage and not housekeeping:
                self._set_state(item, str(stage))
            item.stage = stage if isinstance(stage, str) else None
            for field in (
                "downloaded_bytes",
                "total_bytes",
                "speed",
                "eta",
                "percent",
                "files_done",
                "files_total",
            ):
                value = event.get(field)
                if value is not None:
                    setattr(item, field, value)
            self._emit(
                {"type": "progress", "id": item.id, "state": item.state, "item": item.snapshot()}
            )

    # -- internals: archive + output -------------------------------------
    def _is_archived(self, item: QueueItem) -> bool:
        """True when this video is archived *and* its file is still there.

        Held under both locks: the state lock stops an item starting a
        download in the middle of an archive rewrite, and the archive lock
        serialises every archive read and write in this process.
        """
        key = item.video_key or item.archive_key
        if key is None:
            return False
        with self._lock:
            with self._archive_lock:
                archive: Archive = (
                    _ReadOnlyArchive(self.archive)
                    if self._downloading()
                    else self.archive
                )
                return reconcile(archive, key, self.output_dir)

    def _find_output(self, item: QueueItem) -> str | None:
        """Newest finished file in the output folder carrying ``[<id>]``."""
        if item.video_key is None:
            return None
        extractor, _, video_id = item.video_key.partition(":")
        if extractor != "youtube" or not video_id:
            return None
        needle = f"[{video_id}]"
        best: tuple[float, str] | None = None
        try:
            with os.scandir(self.output_dir) as entries:
                for entry in entries:
                    if needle not in entry.name:
                        continue
                    if entry.name.endswith((".part", ".ytdl", ".temp")):
                        continue
                    try:
                        if not entry.is_file():
                            continue
                        candidate = (entry.stat().st_mtime, entry.path)
                    except OSError:
                        continue
                    if best is None or candidate[0] > best[0]:
                        best = candidate
        except OSError:
            return None
        return None if best is None else best[1]
