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

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from . import runner
from .archive import Archive, reconcile
from .errors import ErrorInfo, explain
from .history import History, TERMINAL_STATES
from .urlnorm import normalize_url, video_key

__all__ = [
    "ACTIVE_STATES",
    "DOWNLOADING_STATES",
    "BACKOFF",
    "RETRYABLE_CODES",
    "MAX_CONCURRENCY",
    "DEFAULT_CONCURRENCY",
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

ALREADY_DOWNLOADED = ErrorInfo(
    "Already downloaded.", "It is in the download folder", "already_downloaded"
)
_UNKNOWN = ErrorInfo("Download failed.", "See Details", "unknown")


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
    ) -> None:
        self.history = history
        self.archive = archive
        self.output_dir = Path(output_dir).expanduser()
        self.temp_dir = Path(temp_dir).expanduser()
        self._ytdlp = ytdlp
        self._format_selector = format_selector
        self._limit_rate = limit_rate
        self._sleep = sleep
        self._run_download = run_download
        self._probe_url = probe_url
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
    def add(self, url: str) -> dict[str, Any]:
        """Queue *url*; a duplicate of an existing item returns that item.

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
                return self._items[existing].snapshot()
            record_id = self.history.add(clean, video_key=identity, state="queued")
            item = QueueItem(
                id=self._next_id,
                record_id=record_id,
                url=clean,
                identity=identity,
                video_key=key,
            )
            self._next_id += 1
            self._items[item.id] = item
            self._order.append(item.id)
            self._by_identity[identity] = item.id
            snapshot = item.snapshot()
            self._cond.notify_all()
            self._emit({"type": "added", "item": snapshot})
        return snapshot

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
        """Probe, reconcile, download once.

        Returns ``None`` when the item is finished with (terminal, paused or
        stopped) or the number of seconds to wait before the next attempt.
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
            self._set_state(item, "probing")

        info: Mapping[str, Any] | None = None
        error: ErrorInfo | None = None
        try:
            info = self._probe_url(item.url, self._ytdlp)
        except runner.ProbeError as exc:
            error = exc.info
        except OSError:  # pragma: no cover - defensive
            error = _UNKNOWN
        else:
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
            error, _raw = self._download(item)

        if error is None:
            return None
        return self._after_failure(item, error)
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

    def _download(self, item: QueueItem) -> tuple[ErrorInfo | None, str]:
        """Run one yt-dlp download.

        Returns ``(None, raw)`` on success and on a user pause/cancel, and
        ``(ErrorInfo, raw)`` for a real failure.
        """
        opts = runner.DownloadOptions(
            url=item.url,
            output_dir=self.output_dir,
            temp_dir=self.temp_dir,
            archive_path=self.archive.path,
            format_selector=self._format_selector,
            limit_rate=self._limit_rate,
            ytdlp=self._ytdlp,
        )
        handle = self._run_download(
            opts, lambda event: self._on_progress(item, event)
        )
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
                return None, raw

        if returncode == 0 and not terminated:
            path = self._find_output(item)
            with self._cond:
                item.file_path = path
                item.percent = 100.0
                self._set_state(item, "done", file_path=path)
            return None, raw
        return explain(raw), raw

    def _on_progress(self, item: QueueItem, event: Any) -> None:
        if not isinstance(event, Mapping) or event.get("type") != "progress":
            return
        stage = event.get("stage")
        with self._cond:
            if item.state in TERMINAL_STATES or item.state == "paused":
                return
            if stage in runner.STAGES and item.state != stage:
                self._set_state(item, str(stage))
            item.stage = stage if isinstance(stage, str) else None
            for field in ("downloaded_bytes", "total_bytes", "speed", "eta", "percent"):
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
        if item.video_key is None:
            return False
        with self._lock:
            with self._archive_lock:
                archive: Archive = (
                    _ReadOnlyArchive(self.archive)
                    if self._downloading()
                    else self.archive
                )
                return reconcile(archive, item.video_key, self.output_dir)

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
