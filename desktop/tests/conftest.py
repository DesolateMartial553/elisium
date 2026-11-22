"""Shared test setup. Qt must run headless, so set the platform before PySide6 loads."""

from __future__ import annotations

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from elisium_downloader.engine.archive import Archive  # noqa: E402
from elisium_downloader.engine.history import History  # noqa: E402
from elisium_downloader.engine.queue import DownloadQueue  # noqa: E402


@pytest.fixture(autouse=True)
def _never_scan_real_browser_profiles(monkeypatch):
    """The app's default detector reads the real home; no test may do that."""
    from elisium_downloader.engine import browsers

    monkeypatch.setattr(browsers, "detect_default", lambda: [])


@pytest.fixture(autouse=True)
def _never_run_the_real_gallery_dl(monkeypatch):
    """No test may reach the real ``gallery-dl`` (it would go online).

    A routing slip then fails as ``gallery_dl_missing`` instead. Tests that
    need the media engine pass a fake binary to the queue explicitly.
    """
    from elisium_downloader.engine import media

    monkeypatch.setattr(media, "find_gallery_dl", lambda: None)


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["elisium-test"])
    yield app


def _fake_probe(url, ytdlp="yt-dlp", **kwargs):
    return {"id": "x", "title": "Fake title", "extractor_key": "Fake"}


@pytest.fixture
def ui_queue(tmp_path: Path):
    """A queue that is never started, so added items stay ``queued`` and nothing runs."""
    data = tmp_path / "data"
    out = tmp_path / "out"
    tmp = tmp_path / "tmp"
    for folder in (data, out, tmp):
        folder.mkdir()
    history = History(data / "history.sqlite")
    queue = DownloadQueue(
        history,
        Archive(data / "archive.txt"),
        out,
        tmp,
        sleep=lambda _s: None,
        probe_url=_fake_probe,
        run_download=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no real downloads")),
    )
    yield queue
    queue.stop(1.0)
    history.close()


def make_snapshot(item_id=1, state="queued", **over):
    snap = {
        "id": item_id,
        "record_id": item_id,
        "url": f"https://example.com/v/{item_id}",
        "identity": f"id{item_id}",
        "video_key": None,
        "state": state,
        "title": None,
        "file_path": None,
        "attempts": 0,
        "error": None,
        "progress": {
            "stage": None,
            "downloaded_bytes": None,
            "total_bytes": None,
            "speed": None,
            "eta": None,
            "percent": None,
        },
    }
    progress = over.pop("progress", None)
    snap.update(over)
    if progress:
        snap["progress"].update(progress)
    return snap
