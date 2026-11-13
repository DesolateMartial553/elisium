"""End to end: the real yt-dlp against a video served from 127.0.0.1.

Needs ``yt-dlp`` and ``ffmpeg`` on PATH (skips otherwise). No internet.
"""

from __future__ import annotations

import functools
import http.server
import shutil
import socketserver
import subprocess
import threading
from pathlib import Path

import pytest

from elisium_downloader.engine.archive import Archive
from elisium_downloader.engine.history import History
from elisium_downloader.engine.queue import DownloadQueue

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("yt-dlp") is None or shutil.which("ffmpeg") is None,
        reason="yt-dlp and ffmpeg are required",
    ),
]


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: D401
        pass


@pytest.fixture
def url(tmp_path: Path):
    srv_dir = tmp_path / "srv"
    srv_dir.mkdir()
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
            "-f", "lavfi", "-i", "sine=duration=2",
            "-shortest", "-pix_fmt", "yuv420p",
            str(srv_dir / "clip.mp4"),
        ],
        check=True,
        timeout=60,
    )
    server = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(srv_dir))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/clip.mp4"
    finally:
        server.shutdown()
        server.server_close()


class Env:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.out = base / "out"
        self.tmp = base / "cache" / "tmp"
        self.archive = Archive(base / "archive.txt")
        self.history = History(base / "history.sqlite")
        self.queues: list[DownloadQueue] = []

    def queue(self) -> DownloadQueue:
        q = DownloadQueue(self.history, self.archive, self.out, self.tmp)
        q.start()
        self.queues.append(q)
        return q

    def finished_files(self) -> list[Path]:
        return sorted(self.out.glob("*")) if self.out.exists() else []

    def close(self) -> None:
        for q in self.queues:
            q.stop(2.0)
        self.history.close()


@pytest.fixture
def env(tmp_path: Path):
    e = Env(tmp_path / "env")
    try:
        yield e
    finally:
        e.close()


def run_one(q: DownloadQueue, link: str) -> dict:
    item = q.add(link)
    assert q.wait_until_idle(90)
    return q.item(item["id"])


def test_local_download_end_to_end(env: Env, url: str) -> None:
    q = env.queue()
    ids = {q.add(url)["id"], q.add(url)["id"], q.add(url + "?utm_source=x")["id"]}
    assert len(ids) == 1
    assert q.wait_until_idle(90)

    (item,) = q.items()
    assert item["state"] == "done", item
    assert item["file_path"] is not None and Path(item["file_path"]).is_file()
    assert Path(item["file_path"]).parent == env.out
    assert len(env.finished_files()) == 1
    assert not list(env.out.glob("*.part"))
    assert not list(env.tmp.glob("*")) if env.tmp.exists() else True
    assert env.archive.has("generic", "clip")
    assert env.history.get(item["record_id"])["file_path"] == item["file_path"]

    # Fresh queue, same URL: archived and the file is there -> skipped.
    q2 = env.queue()
    again = run_one(q2, url)
    assert again["state"] == "skipped", again
    assert len(env.finished_files()) == 1


def test_redownload_after_deleting_the_file(env: Env, url: str) -> None:
    q = env.queue()
    first = run_one(q, url)
    assert first["state"] == "done", first
    Path(first["file_path"]).unlink()

    # Same queue: add() notices the missing file and queues it again.
    assert q.add(url)["state"] == "queued"
    assert q.wait_until_idle(90)
    second = q.item(first["id"])
    assert second["state"] == "done", second
    assert Path(second["file_path"]).is_file()
    assert len(env.finished_files()) == 1

    # Fresh queue: the archive is reconciled from the probe's id.
    Path(second["file_path"]).unlink()
    q2 = env.queue()
    third = run_one(q2, url)
    assert third["state"] == "done", third
    assert Path(third["file_path"]).is_file()
    assert len(env.finished_files()) == 1
