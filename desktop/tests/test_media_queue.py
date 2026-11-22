"""Brief 10B-1: queue routing to the media engine, fallback, progress, errors."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from elisium_downloader.engine import media
from elisium_downloader.engine.archive import Archive
from elisium_downloader.engine.history import History
from elisium_downloader.engine.queue import BACKOFF, DownloadQueue
from test_media import (
    IG,
    POST,
    TIKTOK,
    TRAY,
    read_log,
    value_after,
    write_fake_gallery,
)
from test_queue import FakeHandle, SUCCESS_BODY, wait_for, write_fake

NO_VIDEO = "ERROR: [Instagram] CAbc123xyz: There is no video in this post"


@dataclass
class MediaHarness:
    queue: DownloadQueue
    history: History
    out: Path
    tmp: Path
    data: Path
    root: Path
    ytdlp_log: Path
    gdl_log: Path
    sleeps: list[float] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def ytdlp(self) -> list[list[str]]:
        return read_log(self.ytdlp_log)

    def gdl(self) -> list[list[str]]:
        return read_log(self.gdl_log)

    def gdl_probes(self) -> list[list[str]]:
        return [a for a in self.gdl() if "-j" in a]

    def gdl_downloads(self) -> list[list[str]]:
        return [a for a in self.gdl() if "-j" not in a]

    def run_one(self, url: str, timeout: float = 15) -> dict[str, Any]:
        item = self.queue.add(url)
        self.queue.start()
        assert self.queue.wait_until_idle(timeout)
        found = self.queue.item(item["id"])
        assert found is not None
        return found


@pytest.fixture
def media_harness(tmp_path: Path):
    built: list[MediaHarness] = []

    def factory(
        *,
        fixture: str | None = "instagram_story_tray.json",
        ytdlp_probe: dict | None = None,
        ytdlp_body: str = "",
        ytdlp_code: int = 0,
        ytdlp_probe_error: str | None = None,
        gallery: bool = True,
        concurrency: int = 2,
        archive_lines: list[str] | None = None,
        **gdl: Any,
    ) -> MediaHarness:
        root = tmp_path / f"h{len(built)}"  # one folder per harness
        data, out, tmp = root / "data", root / "out", root / "cache" / "tmp"
        for folder in (data, out, tmp):
            folder.mkdir(parents=True, exist_ok=True)
        ytdlp_log, gdl_log = root / "ytdlp.log", root / "gdl.log"
        script = write_fake(
            root, log=ytdlp_log, probe_info=ytdlp_probe, body=ytdlp_body, code=ytdlp_code
        )
        if ytdlp_probe_error is not None:
            # A yt-dlp whose probe prints *ytdlp_probe_error* and fails.
            script.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                f"open({str(ytdlp_log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
                f"print({ytdlp_probe_error!r}, file=sys.stderr)\n"
                "sys.exit(1)\n"
            )
        gallery_path: str | None = None
        if gallery:
            gallery_path = str(write_fake_gallery(root, log=gdl_log, fixture=fixture, **gdl))
        if archive_lines:
            (data / "gallery-archive.sqlite3").write_text("\n".join(archive_lines) + "\n")
        history = History(data / "history.sqlite")
        sleeps: list[float] = []
        queue = DownloadQueue(
            history,
            Archive(data / "archive.txt"),
            out,
            tmp,
            concurrency=concurrency,
            ytdlp=str(script),
            sleep=sleeps.append,
            gallery_dl=gallery_path,
        )
        harness = MediaHarness(queue, history, out, tmp, data, root, ytdlp_log, gdl_log, sleeps)
        queue.add_listener(harness.events.append)
        built.append(harness)
        return harness

    yield factory
    for h in built:
        h.queue.stop(1.0)
        h.history.close()


# -- routing -------------------------------------------------------------
def test_story_tray_goes_straight_to_gallery_dl(media_harness) -> None:
    h = media_harness(fixture="instagram_story_tray.json")
    item = h.run_one(TRAY)
    assert item["state"] == "done"
    assert h.ytdlp() == []  # yt-dlp is never started for a tray
    assert len(h.gdl_probes()) == 1 and len(h.gdl_downloads()) == 1
    folder = h.out / "bakery_north"
    names = sorted(p.name for p in folder.iterdir())
    assert len(names) == 3 and all(n.startswith("bakery_north ") for n in names)
    assert item["file_path"] == str(folder / names[0])
    assert item["title"] == "bakery_north 3303000000000000000"
    assert item["progress"]["percent"] == 100.0
    assert (item["progress"]["files_done"], item["progress"]["files_total"]) == (3, 3)


def test_download_argv_the_queue_builds(media_harness) -> None:
    h = media_harness(fixture="instagram_story_tray.json")
    h.queue.set_limit_rate("2M")
    h.run_one(TRAY)
    (argv,) = h.gdl_downloads()
    assert "--config-ignore" in argv
    cfg = Path(value_after(argv, "--config-json"))
    assert cfg == h.root / "cache" / "gallery-dl.json"
    assert json.loads(cfg.read_text())["extractor"]["instagram"]["audio"] is True
    stage = Path(value_after(argv, "-D"))
    assert stage.parent == h.tmp / "media"
    assert value_after(argv, "--download-archive") == str(h.data / "gallery-archive.sqlite3")
    assert "--write-metadata" in argv
    assert value_after(argv, "--limit-rate") == "2M"
    assert argv[-1] == TRAY
    # The probe and the download share one config.
    assert value_after(h.gdl_probes()[0], "--config-json") == str(cfg)
    # Metadata stays in staging, never in the output folder.
    assert sorted(p.suffix for p in stage.iterdir()) == [".json"] * 3
    assert not any(p.suffix == ".json" for p in (h.out / "bakery_north").iterdir())


def test_highlight_and_tiktok_photo_go_to_gallery_dl(media_harness) -> None:
    h = media_harness(fixture="tiktok_photo_slideshow.json")
    item = h.run_one(TIKTOK)
    assert item["state"] == "done"
    assert h.ytdlp() == []
    assert (item["progress"]["files_done"], item["progress"]["files_total"]) == (4, 4)
    assert len(list((h.out / "dancer").iterdir())) == 4
    assert item["title"] == "Three slides #fyp"
    # Slide numbers are part of every name.
    assert sorted(p.name for p in (h.out / "dancer").iterdir())[0].endswith(" 1.jpeg")

    h2 = media_harness(fixture="instagram_story_tray.json")
    done = h2.run_one(f"{IG}/stories/highlights/17912345678901234/")
    assert done["state"] == "done" and h2.ytdlp() == []


def test_video_post_stays_on_yt_dlp(media_harness) -> None:
    h = media_harness(
        ytdlp_probe={"id": "CAbc123xyz", "title": "A video post"},
        ytdlp_body="import pathlib\npathlib.Path(HOME).joinpath('post [CAbc123xyz].mp4').write_text('x')",
    )
    item = h.run_one(POST)
    assert item["state"] == "done"
    assert h.gdl() == []  # the media engine is never started
    assert len(h.ytdlp()) == 2  # probe + download


@pytest.mark.parametrize(
    "url",
    [
        f"{IG}/reel/CAbc123xyz/",
        "https://www.tiktok.com/@dancer/video/7300000000000000001",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://vimeo.com/2",
    ],
)
def test_reels_and_videos_never_touch_gallery_dl(media_harness, url: str) -> None:
    h = media_harness(ytdlp_probe={"id": "x", "title": "T"}, ytdlp_body=SUCCESS_BODY)
    item = h.run_one(url)
    assert item["state"] == "done"
    assert h.gdl() == []


def test_reel_with_no_video_does_not_fall_back(media_harness) -> None:
    h = media_harness(ytdlp_probe_error=NO_VIDEO)
    item = h.run_one(f"{IG}/reel/CAbc123xyz/")
    assert item["state"] == "failed" and item["error"]["code"] == "no_media"
    assert h.gdl() == []


# -- the /p/ no_media fallback ----------------------------------------------
def test_photo_post_falls_back_to_the_media_engine(media_harness) -> None:
    h = media_harness(fixture="instagram_single_image.json", ytdlp_probe_error=NO_VIDEO)
    item = h.run_one(POST)
    assert item["state"] == "done"
    assert len(h.ytdlp()) == 1  # only yt-dlp's probe, no second try
    assert len(h.gdl_probes()) == 1 and len(h.gdl_downloads()) == 1
    assert item["attempts"] == 0  # not counted as a retry
    assert h.sleeps == []  # and no backoff
    (saved,) = (h.out / "cafe_northfield").iterdir()
    assert saved.name == "cafe_northfield 3300000000000000001 1.jpg"
    assert item["title"] == "Fresh bread today"
    states = [e["state"] for e in h.events if e["type"] == "state" and e["id"] == item["id"]]
    assert states == ["probing", "downloading", "done"]


def test_fallback_also_fires_for_a_download_time_no_media(media_harness) -> None:
    h = media_harness(
        fixture="instagram_carousel_mixed.json",
        ytdlp_probe={"id": "CCar456uvw", "title": "Carousel"},
        ytdlp_body=f"print({NO_VIDEO!r}, file=sys.stderr)",
        ytdlp_code=1,
    )
    item = h.run_one(f"{IG}/p/CCar456uvw/")
    assert item["state"] == "done"
    assert len(h.ytdlp()) == 2  # probe + the failed download
    assert len(h.gdl_downloads()) == 1
    assert item["attempts"] == 0 and h.sleeps == []
    assert len(list((h.out / "cafe_northfield").iterdir())) == 3


def test_fallback_applies_to_tv_and_single_stories(media_harness) -> None:
    h = media_harness(fixture="instagram_story_tray.json", ytdlp_probe_error=NO_VIDEO)
    item = h.run_one(f"{IG}/stories/bakery_north/3303000000000000001/")
    assert item["state"] == "done"
    assert len(h.gdl_downloads()) == 1
    h2 = media_harness(fixture="instagram_single_image.json", ytdlp_probe_error=NO_VIDEO)
    assert h2.run_one(f"{IG}/tv/CAbc123xyz/")["state"] == "done"


def test_other_yt_dlp_errors_do_not_fall_back(media_harness) -> None:
    h = media_harness(ytdlp_probe_error="ERROR: Video unavailable")
    item = h.run_one(POST)
    assert item["state"] == "failed" and item["error"]["code"] == "video_unavailable"
    assert h.gdl() == []


def test_fallback_runs_once_and_its_failure_is_final(media_harness) -> None:
    h = media_harness(fixture="empty.json", ytdlp_probe_error=NO_VIDEO)
    item = h.run_one(POST)
    assert item["state"] == "failed"
    assert item["error"]["code"] == "no_media"
    assert len(h.ytdlp()) == 1 and len(h.gdl_probes()) == 1  # no loop
    assert h.sleeps == []


# -- gallery-dl missing ------------------------------------------------------
def test_gallery_dl_missing_fails_without_retries(media_harness) -> None:
    h = media_harness(gallery=False)  # PATH lookup is stubbed to None by conftest
    item = h.run_one(TRAY)
    assert item["state"] == "failed"
    assert item["error"]["code"] == "gallery_dl_missing"
    assert "sudo pacman -S gallery-dl" in item["error"]["message"]
    assert h.ytdlp() == [] and h.sleeps == []
    row = h.history.get(item["record_id"])
    assert row is not None and row["error_code"] == "gallery_dl_missing"


def test_missing_binary_path_is_gallery_dl_missing(media_harness) -> None:
    h = media_harness(gallery=False)
    h.queue._gallery_dl = str(h.root / "does-not-exist")
    item = h.run_one(TRAY)
    assert item["error"]["code"] == "gallery_dl_missing"


def test_photo_post_without_gallery_dl_reports_it(media_harness) -> None:
    h = media_harness(gallery=False, ytdlp_probe_error=NO_VIDEO)
    item = h.run_one(POST)
    assert item["state"] == "failed" and item["error"]["code"] == "gallery_dl_missing"


def test_the_queue_finds_gallery_dl_on_path(media_harness, monkeypatch) -> None:
    h = media_harness(gallery=False, fixture="instagram_story_tray.json")
    script = write_fake_gallery(h.root, log=h.gdl_log, fixture="instagram_story_tray.json")
    monkeypatch.setattr(media, "find_gallery_dl", lambda: str(script))
    assert h.run_one(TRAY)["state"] == "done"


# -- progress ---------------------------------------------------------------
def test_progress_events_carry_files_done_and_total(media_harness) -> None:
    h = media_harness(fixture="instagram_carousel_mixed.json")
    h.run_one(f"{IG}/stories/cafe_northfield/")
    progress = [e for e in h.events if e["type"] == "progress"]
    done = [e["item"]["progress"]["files_done"] for e in progress]
    assert done == [1, 2, 3]
    assert [e["item"]["progress"]["percent"] for e in progress] == [33.3, 66.7, 100.0]
    assert {e["item"]["progress"]["files_total"] for e in progress} == {3}
    # The total is known before the first file finishes (from the probe).
    items = [e for e in h.events if e["type"] == "item"]
    assert items and items[0]["item"]["progress"]["files_total"] == 3


def test_snapshot_has_files_keys_for_every_item(media_harness) -> None:
    h = media_harness(ytdlp_probe={"id": "x", "title": "T"}, ytdlp_body=SUCCESS_BODY)
    item = h.queue.add("https://vimeo.com/2")
    assert item["progress"]["files_done"] is None and item["progress"]["files_total"] is None


# -- no duplicates / resume --------------------------------------------------
def test_archived_slides_are_skipped_and_the_rest_fetched(media_harness) -> None:
    h = media_harness(
        fixture="instagram_carousel_mixed.json",
        archive_lines=["instagram:3301000000000000001:1"],
    )
    item = h.run_one(f"{IG}/stories/cafe_northfield/")
    assert item["state"] == "done"
    assert len(list((h.out / "cafe_northfield").iterdir())) == 2  # only the missing slides
    assert (item["progress"]["files_done"], item["progress"]["files_total"]) == (3, 3)


def test_everything_already_archived_is_skipped(media_harness) -> None:
    h = media_harness(
        fixture="instagram_carousel_mixed.json",
        archive_lines=[
            "instagram:3301000000000000001:1",
            "instagram:3301000000000000002:2",
            "instagram:3301000000000000003:3",
        ],
    )
    item = h.run_one(f"{IG}/stories/cafe_northfield/")
    assert item["state"] == "skipped"
    assert item["error"]["code"] == "already_downloaded"
    assert not (h.out / "cafe_northfield").exists()


def test_existing_output_file_is_never_overwritten(media_harness) -> None:
    h = media_harness(fixture="instagram_single_image.json")
    folder = h.out / "cafe_northfield"
    folder.mkdir()
    name = "cafe_northfield 3300000000000000001 1.jpg"
    (folder / name).write_text("mine")
    item = h.run_one(f"{IG}/stories/cafe_northfield/")
    assert (folder / name).read_text() == "mine"
    assert [p.name for p in folder.iterdir()] == [name]  # no "(1)" copy
    assert item["state"] == "skipped"
    assert item["file_path"] == str(folder / name)


def test_done_item_whose_file_is_present_stays_done(media_harness) -> None:
    h = media_harness(fixture="instagram_story_tray.json")
    item = h.run_one(TRAY)
    again = h.queue.add(TRAY)
    assert again["id"] == item["id"] and again["state"] == "done"


# -- cookies ------------------------------------------------------------------
def test_cookies_reach_probe_and_download_and_never_history(media_harness) -> None:
    h = media_harness(fixture="instagram_story_tray.json")
    h.queue.set_cookies("firefox", "/secret/cookies.txt")
    item = h.run_one(TRAY)
    for argv in (h.gdl_probes()[0], h.gdl_downloads()[0]):
        assert value_after(argv, "--cookies-from-browser") == "firefox"
        assert "--cookies" not in argv  # the browser wins
    assert "/secret/cookies.txt" not in json.dumps(h.history.get(item["record_id"]) or {})

    h2 = media_harness(fixture="instagram_story_tray.json")
    h2.queue.set_cookies(None, "/c.txt")
    h2.run_one(TRAY)
    assert value_after(h2.gdl_downloads()[0], "--cookies") == "/c.txt"


# -- errors ---------------------------------------------------------------------
def test_login_wall_on_probe_is_a_sign_in_message(media_harness) -> None:
    h = media_harness(
        probe_stdout="[]",
        probe_stderr="[instagram][error] HttpError: '401 Unauthorized'\n[instagram][warning] Redirected to login page",
        probe_code=4,
    )
    item = h.run_one(TRAY)
    assert item["state"] == "failed" and item["error"]["code"] == "login_required"
    assert h.gdl_downloads() == []


def test_login_wall_with_cookies_is_an_expired_session(media_harness) -> None:
    h = media_harness(
        probe_stdout="[]",
        probe_stderr="[instagram][error] HttpError: '401 Unauthorized'",
        probe_code=4,
    )
    h.queue.set_cookies("firefox", None)
    assert h.run_one(TRAY)["error"]["code"] == "session_expired"


def test_download_time_failures_are_explained(media_harness) -> None:
    h = media_harness(
        fixture="instagram_story_tray.json",
        download_stderr="[instagram][error] HttpError: '429 Too Many Requests'\n",
        download_code=4,
    )
    item = h.run_one(TRAY)
    assert item["state"] == "failed" and item["error"]["code"] == "rate_limited"
    assert h.sleeps == []  # a rate limit is not retried


def test_private_account_and_story_expired(media_harness) -> None:
    h = media_harness(probe_stdout="", probe_stderr="This account is private", probe_code=1)
    assert h.run_one(TRAY)["error"]["code"] == "private_account"
    h2 = media_harness(fixture="empty.json")
    assert h2.run_one(TRAY)["error"]["code"] == "story_expired"
    h3 = media_harness(
        ytdlp_probe_error=NO_VIDEO,
        probe_stdout="",
        probe_stderr="[instagram][error] HttpError: '404 Not Found'",
        probe_code=1,
    )
    assert h3.run_one(f"{IG}/stories/bakery_north/3303000000000000001/")["error"]["code"] == "story_expired"


def test_a_failed_run_still_moves_what_finished(media_harness) -> None:
    h = media_harness(
        fixture="instagram_story_tray.json",
        download_stderr="[instagram][error] something broke\n",
        download_code=1,
    )
    item = h.run_one(TRAY)
    assert item["state"] == "failed"
    # The three files were fetched before the error: they are in the output folder
    # now, so the retry only has to fetch what is missing.
    assert len(list((h.out / "bakery_north").iterdir())) == 3
    assert item["file_path"] is not None and Path(item["file_path"]).is_file()


def test_network_errors_retry_with_the_usual_backoff(media_harness) -> None:
    h = media_harness(
        fixture="instagram_story_tray.json",
        download_stderr="[downloader.http][error] Connection reset by peer\n",
        download_code=1,
    )
    item = h.run_one(TRAY, timeout=20)
    assert item["state"] == "failed" and item["error"]["code"] == "network"
    assert h.sleeps == list(BACKOFF)
    assert item["attempts"] == len(BACKOFF)


# -- pause / cancel ------------------------------------------------------------
def test_pause_stops_gallery_dl_and_keeps_staged_files(media_harness) -> None:
    h = media_harness(fixture="instagram_story_tray.json", sleep_after_first=30)
    item = h.queue.add(TRAY)
    h.queue.start()
    assert wait_for(
        lambda: (h.queue.item(item["id"]) or {}).get("progress", {}).get("files_done") == 1
    )
    assert h.queue.pause(item["id"])
    assert h.queue.wait_until_idle(10)
    assert h.queue.item(item["id"])["state"] == "paused"
    assert not (h.out / "bakery_north").exists()  # nothing moved yet
    stage = media.item_directory(h.tmp, item["identity"])
    assert any(p.suffix != ".json" for p in stage.iterdir())  # the finished slide is kept


def test_resume_moves_files_that_finished_before_the_pause(media_harness) -> None:
    h = media_harness(fixture="instagram_story_tray.json", sleep_after_first=30)
    item = h.queue.add(TRAY)
    h.queue.start()
    assert wait_for(
        lambda: (h.queue.item(item["id"]) or {}).get("progress", {}).get("files_done") == 1
    )
    h.queue.pause(item["id"])
    assert h.queue.wait_until_idle(10)
    # Swap in a fake that finishes quickly, then resume.
    fast = write_fake_gallery(
        h.root, log=h.gdl_log, fixture="instagram_story_tray.json", name="fast-gdl"
    )
    h.queue._gallery_dl = str(fast)
    assert h.queue.resume(item["id"])
    assert h.queue.wait_until_idle(15)
    assert h.queue.item(item["id"])["state"] == "done"
    assert len(list((h.out / "bakery_north").iterdir())) == 3  # slide 1 from staging + 2 new


def test_cancel_terminates_the_process(media_harness) -> None:
    h = media_harness(fixture="instagram_story_tray.json", sleep_after_first=30)
    item = h.queue.add(TRAY)
    h.queue.start()
    assert wait_for(
        lambda: (h.queue.item(item["id"]) or {}).get("progress", {}).get("files_done") == 1
    )
    assert h.queue.cancel(item["id"])
    assert h.queue.wait_until_idle(10)
    assert h.queue.item(item["id"])["state"] == "cancelled"


# -- injected engine -------------------------------------------------------------
def test_run_media_and_probe_media_are_injectable(tmp_path: Path) -> None:
    data, out, tmp = tmp_path / "data", tmp_path / "out", tmp_path / "cache" / "tmp"
    for folder in (data, out, tmp):
        folder.mkdir(parents=True)
    history = History(data / "history.sqlite")
    seen: dict[str, Any] = {}

    def fake_probe(url, binary, **kw):
        seen["probe"] = (url, binary, kw)
        return media.MediaPlan(site="instagram", files=(media.PlannedFile("image", "1", 1, "jpg"),), owner="u")

    def fake_run(opts, on_event, *, files_total=None):
        seen["run"] = (opts, files_total)
        return FakeHandle()

    queue = DownloadQueue(
        history,
        Archive(data / "archive.txt"),
        out,
        tmp,
        sleep=lambda _s: None,
        gallery_dl="/fake/gallery-dl",
        probe_media=fake_probe,
        run_media=fake_run,
    )
    try:
        item = queue.add(TRAY)
        queue.start()
        assert queue.wait_until_idle(10)
        assert queue.item(item["id"])["state"] == "skipped"  # FakeHandle printed nothing
        assert seen["probe"][1] == "/fake/gallery-dl"
        assert seen["run"][1] == 1
        assert seen["run"][0].gallery_dl == "/fake/gallery-dl"
    finally:
        queue.stop(1.0)
        history.close()


def test_worker_threads_are_released_after_a_run(media_harness) -> None:
    h = media_harness(fixture="instagram_story_tray.json")
    h.run_one(TRAY)
    assert wait_for(lambda: not h.queue._threads)
