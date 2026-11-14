from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from elisium_downloader.engine.archive import Archive
from elisium_downloader.engine.history import History
from elisium_downloader.engine.queue import (
    BACKOFF,
    DownloadQueue,
)

VIDEO_ID = "dQw4w9WgXcQ"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
VIDEO_ID_2 = "BaW_jenozKc"
URL_2 = f"https://www.youtube.com/watch?v={VIDEO_ID_2}"


# -- fake yt-dlp ---------------------------------------------------------
def write_fake(
    tmp_path: Path,
    *,
    log: Path,
    probe_info: dict | None = None,
    body: str = "",
    code: int = 0,
    name: str = "fake-yt-dlp",
) -> Path:
    """A fake yt-dlp: logs argv, answers ``-J`` with *probe_info*, then runs *body*."""
    lines = [
        "#!/usr/bin/env python3",
        "import json, pathlib, sys, time",
        "argv = sys.argv[1:]",
        "def _opt(prefix):",
        "    for arg in argv:",
        "        if arg.startswith(prefix):",
        "            return arg.split(':', 1)[1]",
        "    return ''",
        "HOME = _opt('home:')",
        "TEMP = _opt('temp:')",
        f"with open({str(log)!r}, 'a', encoding='utf-8') as fh:",
        "    fh.write(json.dumps(argv) + '\\n')",
        "if '-J' in argv:",
    ]
    if probe_info is None:
        lines += [
            "    print('ERROR: Video unavailable', file=sys.stderr)",
            "    sys.exit(1)",
        ]
    else:
        lines += [f"    print(json.dumps({probe_info!r}))", "    sys.exit(0)"]
    if body:
        lines += body.splitlines()
    lines.append(f"sys.exit({code})")
    script = tmp_path / name
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def progress(obj: dict) -> str:
    return "print('[download] ' + json.dumps(" + repr(obj) + "), flush=True)"


SUCCESS_BODY = "\n".join(
    [
        "pathlib.Path(HOME).joinpath('Video [dQw4w9WgXcQ].mp4').write_text('done')",
        progress(
            {
                "status": "downloading",
                "downloaded_bytes": 5,
                "total_bytes": 10,
                "speed": 1.0,
                "eta": 5,
            }
        ),
        progress({"status": "finished", "downloaded_bytes": 10, "total_bytes": 10}),
    ]
)


class FakeHandle:
    """Stands in for a runner.DownloadProcess."""

    def __init__(self, returncode: int = 0, raw_log: str = "") -> None:
        self.returncode = returncode
        self.raw_log = raw_log
        self.terminated = False

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True


# -- harness -------------------------------------------------------------
@dataclass
class Harness:
    queue: DownloadQueue
    history: History
    archive: Archive
    out: Path
    tmp: Path
    log: Path
    sleeps: list[float] = field(default_factory=list)

    def invocation_log(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [
            json.loads(line)
            for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def probes(self) -> list[list[str]]:
        return [argv for argv in self.invocation_log() if "-J" in argv]

    def downloads(self) -> list[list[str]]:
        return [argv for argv in self.invocation_log() if "-J" not in argv]

    def row(self, item: dict[str, Any]) -> dict[str, Any] | None:
        return self.history.get(item["record_id"])


_DEFAULT_PROBE: dict[str, Any] = {"id": VIDEO_ID, "title": "Video title"}


def make_harness(
    tmp_path: Path,
    *,
    body: str = "",
    probe_info: dict | None = _DEFAULT_PROBE,
    code: int = 0,
    concurrency: int = 2,
    **queue_kwargs: Any,
) -> Harness:
    data = tmp_path / "data"
    out = tmp_path / "out"
    tmp = tmp_path / "tmp"
    for folder in (data, out, tmp):
        folder.mkdir(exist_ok=True)
    log = tmp_path / "argv.log"
    script = write_fake(
        tmp_path,
        log=log,
        probe_info=probe_info,
        body=body,
        code=code,
    )
    history = History(data / "history.sqlite")
    archive = queue_kwargs.pop("archive", None) or Archive(data / "archive.txt")
    sleeps: list[float] = []
    queue = DownloadQueue(
        history,
        archive,
        out,
        tmp,
        concurrency=concurrency,
        ytdlp=str(script),
        sleep=sleeps.append,
        **queue_kwargs,
    )
    return Harness(queue, history, archive, out, tmp, log, sleeps)


@pytest.fixture
def harness(tmp_path: Path):
    created: list[Harness] = []

    def factory(**kwargs: Any) -> Harness:
        built = make_harness(tmp_path, **kwargs)
        created.append(built)
        return built

    yield factory
    for built in created:
        built.queue.stop(1.0)
        built.history.close()


def wait_for(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# -- add + dedupe --------------------------------------------------------
def test_add_queues_one_item(harness) -> None:
    h = harness()
    item = h.queue.add(URL)
    assert item["state"] == "queued"
    assert item["identity"] == f"youtube:{VIDEO_ID}"
    assert h.row(item)["state"] == "queued"


def test_duplicate_add_returns_the_same_item(harness) -> None:
    h = harness()
    first = h.queue.add(URL)
    second = h.queue.add(
        f"https://youtu.be/{VIDEO_ID}?si=tracking&t=30"
    )
    assert first["id"] == second["id"]
    assert len(h.queue.items()) == 1
    assert len(h.history.recent()) == 1


def test_non_youtube_sites_dedupe_by_normalized_url(harness) -> None:
    h = harness()
    first = h.queue.add("https://vimeo.com/12345?utm_source=x#t=1")
    second = h.queue.add("https://vimeo.com/12345")
    assert first["id"] == second["id"]
    assert first["identity"] == "https://vimeo.com/12345"
    assert first["video_key"] is None


def test_add_rejects_a_bad_url(harness) -> None:
    h = harness()
    with pytest.raises(ValueError):
        h.queue.add("not a url")
    assert h.queue.items() == []


# -- happy path ----------------------------------------------------------
def test_success_downloads_marks_done_and_stores_the_file(harness) -> None:
    h = harness(body=SUCCESS_BODY)
    item = h.queue.add(URL)
    h.queue.start()
    assert h.queue.wait_until_idle(15)

    done = h.queue.item(item["id"])
    assert done["state"] == "done"
    assert done["title"] == "Video title"
    assert done["file_path"] == str(h.out / "Video [dQw4w9WgXcQ].mp4")
    assert done["progress"]["percent"] == 100.0
    row = h.row(item)
    assert row["state"] == "done"
    assert row["file_path"] == done["file_path"]
    assert row["finished_at"] is not None


def test_download_command_contains_the_dedupe_flags(harness) -> None:
    h = harness(body=SUCCESS_BODY)
    h.queue.add(URL)
    h.queue.start()
    assert h.queue.wait_until_idle(15)

    downloads = h.downloads()
    assert len(downloads) == 1
    argv = downloads[0]
    assert f"home:{h.out}" in argv
    assert f"temp:{h.tmp}" in argv
    assert argv[argv.index("--download-archive") + 1] == str(h.archive.path)
    assert "--no-overwrites" in argv
    assert "--continue" in argv
    assert "%(title).150B [%(id)s].%(ext)s" in argv


def test_stages_go_downloading_merging_converting_then_done(harness) -> None:
    body = "\n".join(
        [
            progress(
                {"status": "downloading", "downloaded_bytes": 1, "total_bytes": 2}
            ),
            progress({"status": "started", "postprocessor": "Merger"}),
            progress({"status": "started", "postprocessor": "ExtractAudio"}),
            "pathlib.Path(HOME).joinpath('Video [dQw4w9WgXcQ].mp3').write_text('x')",
        ]
    )
    h = harness(body=body)
    item = h.queue.add(URL)
    seen: list[str] = []
    h.queue.add_listener(
        lambda event: seen.append(event["state"])
        if event["type"] == "state"
        else None
    )
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(item["id"])["state"] == "done"
    for stage in ("downloading", "merging", "converting", "done"):
        assert stage in seen


# -- failures ------------------------------------------------------------
def test_403_fails_with_plain_language_text_and_no_retry(harness) -> None:
    body = "print('ERROR: unable to download video data: HTTP Error 403: Forbidden', file=sys.stderr)"
    h = harness(body=body, code=1)
    item = h.queue.add(URL)
    h.queue.start()
    assert h.queue.wait_until_idle(15)

    failed = h.queue.item(item["id"])
    assert failed["state"] == "failed"
    assert failed["error"]["code"] == "http_403"
    assert failed["error"]["message"] == "The site refused the download."
    assert h.sleeps == []
    assert len(h.downloads()) == 1
    assert h.row(item)["error_code"] == "http_403"


def test_network_error_backs_off_5_15_45_then_fails(harness) -> None:
    body = "print('ERROR: unable to download video data: Connection reset by peer', file=sys.stderr)"
    h = harness(body=body, code=1)
    item = h.queue.add(URL)
    h.queue.start()
    assert h.queue.wait_until_idle(20)

    assert h.sleeps == list(BACKOFF)
    assert h.queue.item(item["id"])["state"] == "failed"
    assert h.queue.item(item["id"])["error"]["code"] == "network"
    assert len(h.downloads()) == 4  # first try + three retries


def test_probe_failure_is_reported(harness) -> None:
    h = harness(probe_info=None)
    item = h.queue.add(URL)
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    failed = h.queue.item(item["id"])
    assert failed["state"] == "failed"
    assert failed["error"]["code"] == "video_unavailable"
    assert h.downloads() == []


# -- pause / resume / cancel / retry -------------------------------------
def test_pause_keeps_the_part_file_and_resume_runs_continue(harness) -> None:
    body = "\n".join(
        [
            "part = pathlib.Path(TEMP) / 'Video [dQw4w9WgXcQ].f137.mp4.part'",
            "part.write_text('half')",
            progress(
                {
                    "status": "downloading",
                    "downloaded_bytes": 5,
                    "total_bytes": 10,
                }
            ),
            "release = pathlib.Path(TEMP) / 'release'",
            "while not release.exists():",
            "    time.sleep(0.02)",
            "pathlib.Path(HOME).joinpath('Video [dQw4w9WgXcQ].mp4').write_text('done')",
        ]
    )
    h = harness(body=body)
    item = h.queue.add(URL)
    part = h.tmp / "Video [dQw4w9WgXcQ].f137.mp4.part"
    h.queue.start()

    assert wait_for(lambda: part.exists())
    assert h.queue.pause(item["id"]) is True
    assert h.queue.item(item["id"])["state"] == "paused"
    assert part.exists()  # pause never deletes the .part file
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(item["id"])["state"] == "paused"

    (h.tmp / "release").write_text("go")
    assert h.queue.resume(item["id"]) is True
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(item["id"])["state"] == "done"

    downloads = h.downloads()
    assert len(downloads) == 2
    assert all("--continue" in argv for argv in downloads)


def test_pause_of_a_queued_item(harness) -> None:
    h = harness(body=SUCCESS_BODY, concurrency=1)
    first = h.queue.add(URL)
    second = h.queue.add("https://youtu.be/zzzzzzzzzzz")
    assert h.queue.pause(second["id"]) is True
    assert h.queue.item(second["id"])["state"] == "paused"
    assert h.queue.pause(first["id"]) is True  # still queued, not started


def test_cancel_terminates_a_running_download(harness) -> None:
    body = "\n".join(
        [
            "pathlib.Path(TEMP).joinpath('started').write_text('1')",
            "time.sleep(30)",
        ]
    )
    h = harness(body=body)
    item = h.queue.add(URL)
    h.queue.start()
    assert wait_for(lambda: (h.tmp / "started").exists())

    assert h.queue.cancel(item["id"]) is True
    assert h.queue.item(item["id"])["state"] == "cancelled"
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(item["id"])["state"] == "cancelled"
    assert h.row(item)["state"] == "cancelled"
    assert h.sleeps == []


def test_cancel_a_queued_item(harness) -> None:
    h = harness(body=SUCCESS_BODY)
    item = h.queue.add(URL)
    assert h.queue.cancel(item["id"]) is True
    assert h.queue.item(item["id"])["state"] == "cancelled"
    assert h.queue.cancel(item["id"]) is False  # already terminal


def test_retry_after_failure_clears_the_error(harness) -> None:
    body = "print('ERROR: Video unavailable', file=sys.stderr)"
    h = harness(body=body, code=1)
    item = h.queue.add(URL)
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(item["id"])["state"] == "failed"

    h.queue.stop(1.0)  # so the retry is not picked up while we assert
    assert h.queue.retry(item["id"]) is True
    after = h.queue.item(item["id"])
    assert after["state"] == "queued"
    assert after["error"] is None
    assert after["attempts"] == 0
    assert h.row(item)["error_code"] is None

    h.queue.start()
    assert h.queue.wait_until_idle(15)


def test_actions_on_unknown_items_return_false(harness) -> None:
    h = harness()
    assert h.queue.pause(999) is False
    assert h.queue.resume(999) is False
    assert h.queue.retry(999) is False
    assert h.queue.cancel(999) is False
    assert h.queue.item(999) is None


# -- concurrency ---------------------------------------------------------
def test_concurrency_limit_is_honoured(harness) -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_run(opts, on_event):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return FakeHandle()

    h = harness(
        concurrency=2,
        probe_url=lambda url, ytdlp="yt-dlp", **kw: {"title": "T"},
        run_download=fake_run,
    )
    for index in range(6):
        h.queue.add(f"https://vimeo.com/{index}")
    h.queue.start()
    assert h.queue.wait_until_idle(15)

    assert peak == 2
    assert {item["state"] for item in h.queue.items()} == {"done"}


def test_concurrency_must_be_between_1_and_5(harness) -> None:
    for bad in (0, 6, -1):
        with pytest.raises(ValueError):
            harness(concurrency=bad)
    h = harness()
    with pytest.raises(ValueError):
        h.queue.set_concurrency(9)


def test_set_concurrency_is_used(harness) -> None:
    h = harness(concurrency=1)
    h.queue.set_concurrency(3)
    assert h.queue.concurrency == 3


# -- archive -------------------------------------------------------------
def test_archive_skip_gives_skipped(harness) -> None:
    h = harness(body=SUCCESS_BODY)
    h.archive.add("youtube", VIDEO_ID)
    (h.out / f"Old video [{VIDEO_ID}].mp4").write_text("old")

    item = h.queue.add(URL)
    h.queue.start()
    assert h.queue.wait_until_idle(15)

    assert h.queue.item(item["id"])["state"] == "skipped"
    assert h.row(item)["state"] == "skipped"
    assert h.downloads() == []


def test_archive_entry_without_a_file_downloads_again(harness) -> None:
    h = harness(body=SUCCESS_BODY)
    h.archive.add("youtube", VIDEO_ID)

    item = h.queue.add(URL)
    h.queue.start()
    assert h.queue.wait_until_idle(15)

    assert h.queue.item(item["id"])["state"] == "done"
    assert len(h.downloads()) == 1
    assert not h.archive.has("youtube", VIDEO_ID)  # stale entry was removed


def test_archive_is_not_rewritten_while_an_item_downloads(harness, tmp_path) -> None:
    body = "\n".join(
        [
            "pathlib.Path(TEMP).joinpath('started').write_text('1')",
            "release = pathlib.Path(TEMP) / 'release'",
            "while not release.exists():",
            "    time.sleep(0.02)",
            "pathlib.Path(HOME).joinpath('Video [' + 'x' * 4 + '].mp4').write_text('x')",
        ]
    )
    removed: list[tuple[str, str]] = []

    class SpyArchive(Archive):
        def remove(self, extractor: str, video_id: str) -> bool:
            removed.append((extractor, video_id))
            return super().remove(extractor, video_id)

    spy = SpyArchive(tmp_path / "data" / "spy-archive.txt")
    spy.add("youtube", "STALEID")
    h = harness(body=body, archive=spy)

    busy = h.queue.add(URL_2)  # starts, then blocks on the release file
    h.queue.start()
    assert wait_for(lambda: (h.tmp / "started").exists())

    stale = h.queue.add("https://youtu.be/STALEID")  # archived, file missing
    assert wait_for(lambda: h.queue.item(stale["id"])["state"] != "queued")
    assert h.queue.wait_until_idle(0.5) is False  # busy item still running
    assert removed == []  # the archive was never rewritten while busy
    assert spy.has("youtube", "STALEID")

    (h.tmp / "release").write_text("go")
    assert h.queue.wait_until_idle(15)
    # Read-only reconcile meant "not archived", so it downloaded instead.
    assert h.queue.item(stale["id"])["state"] == "done"
    assert spy.has("youtube", "STALEID") is True
    assert busy["id"] != stale["id"]

    # Now the queue is idle: the stale entry is removed as usual.
    spy.add("youtube", "STALEID2")
    third = h.queue.add("https://youtu.be/STALEID2")
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(third["id"])["state"] == "done"
    assert removed == [("youtube", "STALEID2")]
    assert spy.has("youtube", "STALEID2") is False


def test_archive_calls_are_serialised(harness, tmp_path) -> None:
    class OverlapArchive(Archive):
        def __init__(self, path: Path) -> None:
            super().__init__(path)
            self._busy = threading.Lock()
            self.overlaps = 0

        def _enter(self) -> None:
            if not self._busy.acquire(blocking=False):
                self.overlaps += 1
                self._busy.acquire()
            time.sleep(0.002)

        def _exit(self) -> None:
            self._busy.release()

        def has(self, extractor: str, video_id: str) -> bool:
            self._enter()
            try:
                return super().has(extractor, video_id)
            finally:
                self._exit()

        def remove(self, extractor: str, video_id: str) -> bool:
            self._enter()
            try:
                return super().remove(extractor, video_id)
            finally:
                self._exit()

    h = harness(concurrency=4, archive=OverlapArchive(tmp_path / "shared-archive.txt"))
    shared = h.archive

    for index in range(4):
        h.queue.add(f"https://youtu.be/id{index}")
    h.queue.start()
    assert h.queue.wait_until_idle(20)

    assert shared.overlaps == 0


# -- misc ----------------------------------------------------------------
def test_events_are_emitted_to_every_listener(harness) -> None:
    h = harness(body=SUCCESS_BODY)
    seen_one: list[str] = []
    seen_two: list[str] = []
    h.queue.add_listener(lambda event: seen_one.append(event["type"]))
    h.queue.add_listener(lambda event: seen_two.append(event["type"]))

    h.queue.add(URL)
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert "added" in seen_one and "state" in seen_one
    assert seen_one == seen_two


def test_a_broken_listener_does_not_break_the_queue(harness) -> None:
    def explode(event):
        raise RuntimeError("boom")

    h = harness(body=SUCCESS_BODY)
    h.queue.add_listener(explode)
    item = h.queue.add(URL)
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(item["id"])["state"] == "done"


def test_snapshots_are_plain_dicts(harness) -> None:
    h = harness()
    h.queue.add(URL)
    snapshot = h.queue.items()[0]
    json.dumps(snapshot)  # must be JSON-serialisable for the UI layer
    assert set(snapshot) >= {"id", "url", "state", "progress", "error"}


def test_stop_pauses_running_items(harness) -> None:
    body = "\n".join(
        [
            "pathlib.Path(TEMP).joinpath('started').write_text('1')",
            "time.sleep(30)",
        ]
    )
    h = harness(body=body)
    item = h.queue.add(URL)
    h.queue.start()
    assert wait_for(lambda: (h.tmp / "started").exists())

    h.queue.stop(2.0)
    assert h.queue.item(item["id"])["state"] == "paused"


# -- brief 1D ------------------------------------------------------------
PATH_BODY = "\n".join(
    [
        "pathlib.Path(HOME).joinpath('Weird name.mp4').write_text('x')",
        "pf = argv[argv.index('--print-to-file') + 2]",
        "pathlib.Path(pf).write_text(str(pathlib.Path(HOME) / 'Weird name.mp4') + '\\n')",
    ]
)
SKIP_BODY = (
    "print('[generic] clip: has already been recorded in the archive', flush=True)"
)


def test_reported_path_file_becomes_the_item_file_path(harness) -> None:
    h = harness(body=PATH_BODY)
    item = h.queue.add("https://example.com/clip.mp4")
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    done = h.queue.item(item["id"])
    assert done["state"] == "done"
    assert done["file_path"] == str(h.out / "Weird name.mp4")
    assert h.row(item)["file_path"] == done["file_path"]
    assert list(h.tmp.glob("*.path")) == []
    assert "--print-to-file" in h.downloads()[0]


def test_silent_archive_skip_is_reported_as_skipped(harness) -> None:
    h = harness(body=SKIP_BODY)
    item = h.queue.add("https://example.com/clip.mp4")
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    got = h.queue.item(item["id"])
    assert got["state"] == "skipped"
    assert got["error"]["code"] == "already_downloaded"
    assert h.row(item)["state"] == "skipped"


def test_archive_skip_text_with_a_new_file_is_still_done(harness) -> None:
    h = harness(body=SKIP_BODY + "\n" + PATH_BODY)
    item = h.queue.add("https://example.com/clip.mp4")
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(item["id"])["state"] == "done"


def test_plain_download_never_shows_converting(harness) -> None:
    body = "\n".join(
        [
            progress({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 2}),
            progress({"status": "started", "postprocessor": "MoveFiles"}),
            progress({"status": "started", "postprocessor": "Metadata"}),
            SUCCESS_BODY,
        ]
    )
    h = harness(body=body)
    h.queue.add(URL)
    seen: list[str] = []
    h.queue.add_listener(
        lambda event: seen.append(event["state"])
        if event["type"] == "state"
        else None
    )
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert "converting" not in seen
    assert "merging" not in seen
    assert seen[-1] == "done"


def _finish(h: Harness, url: str) -> dict:
    item = h.queue.add(url)
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    return h.queue.item(item["id"])


def test_readding_a_done_item_with_its_file_changes_nothing(harness) -> None:
    h = harness(body=SUCCESS_BODY)
    first = _finish(h, URL)
    assert first["state"] == "done"
    again = h.queue.add(URL)
    assert again["id"] == first["id"]
    assert again["state"] == "done"
    assert len(h.downloads()) == 1


def test_readding_a_done_item_after_deleting_its_file_downloads_again(harness) -> None:
    h = harness(body=SUCCESS_BODY)
    first = _finish(h, URL)
    h.archive.add("youtube", VIDEO_ID)
    Path(first["file_path"]).unlink()

    again = h.queue.add(URL)
    assert again["id"] == first["id"]
    assert again["state"] == "queued"
    assert again["error"] is None
    assert again["file_path"] is None
    assert not h.archive.has("youtube", VIDEO_ID)
    # the worker may already have picked it up, so "queued" is not stable; it must not still be "done"
    assert h.row(first)["state"] in ("queued", "probing", "downloading")

    assert h.queue.wait_until_idle(15)
    final = h.queue.item(first["id"])
    assert final["state"] == "done"
    assert len(h.downloads()) == 2


def test_readding_a_skipped_item_with_a_missing_file_downloads_again(harness) -> None:
    h = harness(body=SUCCESS_BODY)
    h.archive.add("youtube", VIDEO_ID)
    kept = h.out / f"Old [{VIDEO_ID}].mp4"
    kept.write_text("old")
    first = _finish(h, URL)
    assert first["state"] == "skipped"
    assert h.queue.add(URL)["state"] == "skipped"  # file still there

    kept.unlink()
    assert h.queue.add(URL)["state"] == "queued"
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(first["id"])["state"] == "done"


def test_readding_a_failed_item_leaves_it_alone(harness) -> None:
    h = harness(body="print('ERROR: HTTP Error 403: Forbidden')", code=1)
    first = _finish(h, URL)
    assert first["state"] == "failed"
    assert h.queue.add(URL)["state"] == "failed"


def test_non_youtube_archive_key_comes_from_the_probe(harness) -> None:
    info = {"id": "clip", "title": "t", "extractor_key": "Generic"}
    h = harness(body=SUCCESS_BODY, probe_info=info)
    h.archive.add("generic", "clip")  # stale: no file in the output folder
    item = h.queue.add("https://example.com/clip.mp4")
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(item["id"])["state"] == "done"
    assert not h.archive.has("generic", "clip")


# -- runtime setters (apply to downloads that start afterwards) -----------
def test_setters_apply_to_next_started_download(harness) -> None:
    seen: list = []

    def fake_run(opts, on_event):
        seen.append(opts)
        return FakeHandle()

    h = harness(probe_url=lambda url, ytdlp="yt-dlp", **kw: {"title": "T"}, run_download=fake_run)
    h.queue.set_limit_rate("2M")
    h.queue.set_format_selector("wv*+wa/w")
    h.queue.set_extra_args(["-x", "--audio-format", "mp3"])
    h.queue.add("https://vimeo.com/1")
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert seen[0].limit_rate == "2M"
    assert seen[0].format_selector == "wv*+wa/w"
    assert tuple(seen[0].extra_args) == ("-x", "--audio-format", "mp3")

    h.queue.set_limit_rate(None)
    h.queue.set_extra_args([])
    h.queue.add("https://vimeo.com/2")
    assert h.queue.wait_until_idle(15)
    assert seen[1].limit_rate is None
    assert tuple(seen[1].extra_args) == ()


def test_set_format_selector_rejects_empty(harness) -> None:
    with pytest.raises(ValueError):
        harness().queue.set_format_selector("")


# -- brief 8A: cookies ----------------------------------------------------
def test_cookies_reach_the_probe_and_the_download(harness) -> None:
    h = harness(body=SUCCESS_BODY)
    h.queue.set_cookies("firefox", "/tmp/cookies.txt")
    item = h.queue.add("https://www.instagram.com/stories/tiktok/3211234567890123456/")
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(item["id"])["state"] == "done"

    probe_argv = h.probes()[0]
    assert probe_argv[probe_argv.index("--cookies-from-browser") + 1] == "firefox"
    assert "--cookies" not in probe_argv
    download_argv = h.downloads()[0]
    assert download_argv[download_argv.index("--cookies-from-browser") + 1] == "firefox"
    # The cookie file path never reaches history.
    assert "/tmp/cookies.txt" not in json.dumps(h.row(item) or {})


def test_cookies_file_flag_and_reset(harness) -> None:
    h = harness(body=SUCCESS_BODY)
    h.queue.set_cookies(None, "/tmp/cookies.txt")
    h.queue.add("https://www.tiktok.com/@tiktok/video/7106594312292453675")
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    probe_argv = h.probes()[0]
    assert probe_argv[probe_argv.index("--cookies") + 1] == "/tmp/cookies.txt"
    assert "--cookies-from-browser" not in probe_argv

    h.queue.set_cookies(None, None)
    h.queue.add("https://vimeo.com/2")
    assert h.queue.wait_until_idle(15)
    last = h.probes()[-1]
    assert "--cookies" not in last and "--cookies-from-browser" not in last


# -- per-item overrides (brief 2C) ----------------------------------------
def _recording_harness(harness, seen: list):
    def fake_run(opts, on_event):
        seen.append(opts)
        return FakeHandle()

    return harness(probe_url=lambda url, ytdlp="yt-dlp", **kw: {"title": "Probed"}, run_download=fake_run)


def test_item_overrides_beat_queue_defaults(harness) -> None:
    seen: list = []
    h = _recording_harness(harness, seen)
    h.queue.set_format_selector("best")
    h.queue.set_extra_args(["-x"])
    h.queue.add(
        "https://vimeo.com/1",
        format_selector="137+140",
        extra_args=["--remux-video", "mp4"],
        title="Shown first",
    )
    h.queue.add("https://vimeo.com/2")  # no overrides: queue defaults
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    by_url = {o.url: o for o in seen}
    assert by_url["https://vimeo.com/1"].format_selector == "137+140"
    assert tuple(by_url["https://vimeo.com/1"].extra_args) == ("--remux-video", "mp4")
    assert by_url["https://vimeo.com/2"].format_selector == "best"
    assert tuple(by_url["https://vimeo.com/2"].extra_args) == ("-x",)


def test_empty_extra_args_override_still_wins(harness) -> None:
    seen: list = []
    h = _recording_harness(harness, seen)
    h.queue.set_extra_args(["-x", "--audio-format", "mp3"])
    h.queue.add("https://vimeo.com/1", format_selector="22", extra_args=())
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert tuple(seen[0].extra_args) == ()


def test_title_override_is_shown_before_the_probe(harness) -> None:
    h = harness()
    item = h.queue.add("https://vimeo.com/1", title="  Chosen title ")
    assert item["title"] == "Chosen title"


def test_duplicate_add_keeps_original_overrides(harness) -> None:
    seen: list = []
    h = _recording_harness(harness, seen)
    first = h.queue.add("https://vimeo.com/1", format_selector="137+140")
    again = h.queue.add("https://vimeo.com/1", format_selector="18", extra_args=["-x"])
    assert again == first
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert len(seen) == 1 and seen[0].format_selector == "137+140"
    assert tuple(seen[0].extra_args) == ()


# -- public probe / ytdlp --------------------------------------------------
def test_public_probe_uses_injected_probe_and_ytdlp(harness) -> None:
    calls: list[tuple[str, str]] = []

    def fake_probe(url, ytdlp="yt-dlp", **kw):
        calls.append((url, ytdlp))
        return {"title": "Probed"}

    h = harness(probe_url=fake_probe)
    assert h.queue.probe("https://vimeo.com/1") == {"title": "Probed"}
    assert calls == [("https://vimeo.com/1", h.queue.ytdlp)]


def test_ytdlp_property_is_the_configured_path(harness) -> None:
    h = harness()
    assert isinstance(h.queue.ytdlp, str) and h.queue.ytdlp
