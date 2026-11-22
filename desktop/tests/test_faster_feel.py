"""Brief 12C + 12E (desktop): the "Faster downloads" setting, the rate-limit safety rail,
the instant card, the honest ETA and the "Starting..." reasons."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import pytest
from conftest import make_snapshot
from PySide6.QtGui import QFontInfo
from PySide6.QtWidgets import QLabel, QWidget
from test_queue import (
    FORMATS_PROBE,
    SUCCESS_BODY,
    URL,
    FakeHandle,
    _run_one,
    _url_argv,
    harness,  # noqa: F401  (fixture)
    wait_for,
)

from elisium_downloader.engine import queue as q
from elisium_downloader.engine.errors import ErrorInfo
from elisium_downloader.ui import model as m
from elisium_downloader.ui import settings as st
from elisium_downloader.ui import theme
from elisium_downloader.ui.main_window import MainWindow
from elisium_downloader.ui.settings_page import SettingsPage

IG = "https://www.instagram.com"
IG_REEL = f"{IG}/reel/CAbc123xyz/"
IG_TRAY = f"{IG}/stories/cafe_northfield/"
TT = "https://www.tiktok.com/@cafe/video/7123456789012345678"


# -- the setting -----------------------------------------------------------------------------
def test_faster_downloads_defaults_to_auto() -> None:
    assert st.Settings().faster_downloads == "auto"
    assert st.FASTER_DOWNLOADS == ("auto", "off")


def test_faster_downloads_off_is_kept_and_junk_falls_back_to_auto(tmp_path) -> None:
    assert st.Settings(faster_downloads="off").faster_downloads == "off"
    for junk in ("on", "", None, 3, True):
        assert st.Settings(faster_downloads=junk).faster_downloads == "auto"  # type: ignore[arg-type]
    path = tmp_path / "settings.json"
    st.save(st.Settings(faster_downloads="off"), path)
    assert st.load(path).faster_downloads == "off"


def test_an_older_settings_file_without_the_key_loads_as_auto(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"concurrency": 3, "photo_mode": "song"}), encoding="utf-8")
    loaded = st.load(path)
    assert (loaded.concurrency, loaded.photo_mode, loaded.faster_downloads) == (3, "song", "auto")


def test_the_setting_reaches_the_queue_reuse_probe(ui_queue) -> None:
    assert ui_queue.reuse_probe is True
    st.apply(st.Settings(faster_downloads="off"), ui_queue)
    assert ui_queue.reuse_probe is False
    st.apply(st.Settings(faster_downloads="auto"), ui_queue)
    assert ui_queue.reuse_probe is True


def test_off_gives_todays_exact_argv_and_auto_loads_the_info(harness) -> None:  # noqa: F811
    off = harness(probe_info=FORMATS_PROBE, body=SUCCESS_BODY)
    st.apply(st.Settings(faster_downloads="off"), off.queue)
    done = _run_one(off)
    (argv,) = off.downloads()
    assert argv == _url_argv(off, done["id"])
    assert "--load-info-json" not in argv


def test_auto_reuses_the_probe_through_the_queue(harness) -> None:  # noqa: F811
    auto = harness(probe_info=FORMATS_PROBE, body=SUCCESS_BODY)
    st.apply(st.Settings(), auto.queue)
    _run_one(auto)
    (argv,) = auto.downloads()
    assert "--load-info-json" in argv and URL not in argv


def test_settings_page_has_the_row_in_downloads(qapp, ui_queue, tmp_path) -> None:
    path = tmp_path / "cfg" / "settings.json"
    page = SettingsPage(st.Settings(), ui_queue, path, version_fn=lambda: "1")
    try:
        combo = page.faster_combo
        assert page.groups["Downloads"].isAncestorOf(combo)
        assert combo.currentData() == "auto"
        assert combo.accessibleName() == "Faster downloads"
        helper = [lab.text() for lab in page.groups["Downloads"].findChildren(QLabel)]
        assert "Auto looks each link up once. Turn off if downloads fail." in helper
        combo.setCurrentIndex(combo.findData("off"))
        assert page.settings.faster_downloads == "off"
        assert ui_queue.reuse_probe is False
        assert st.load(path).faster_downloads == "off"
    finally:
        page.deleteLater()


@pytest.mark.parametrize("scheme", ["night", "day"])
def test_the_new_row_is_readable_in_both_schemes(qapp, ui_queue, scheme) -> None:
    theme.apply(qapp, scheme)
    page = SettingsPage(st.Settings(), ui_queue, None, version_fn=lambda: "1")
    try:
        for widget in [page.faster_combo, *page.groups["Downloads"].findChildren(QWidget)]:
            widget.ensurePolished()
            if isinstance(widget, QLabel) and widget.text():
                assert QFontInfo(widget.font()).pixelSize() >= 12
        assert QFontInfo(page.faster_combo.font()).pixelSize() >= 12
    finally:
        page.deleteLater()
        theme.reset(qapp)


# -- the rate-limit safety rail --------------------------------------------------------------
def test_site_key_groups_hosts() -> None:
    assert q.site_key("https://www.youtube.com/watch?v=a") == "youtube.com"
    assert q.site_key("https://youtu.be/a") == "youtube.com"
    assert q.site_key("https://m.tiktok.com/x") == "tiktok.com"
    assert q.site_key("https://news.bbc.co.uk/x") == "bbc.co.uk"
    assert q.site_key("not a url") == ""


def test_rate_limit_errors_are_429_and_please_wait() -> None:
    assert q.is_rate_limit_error(ErrorInfo("Too many requests.", "Wait", "http_429"))
    assert q.is_rate_limit_error(ErrorInfo("Slow down.", "Wait", "rate_limited"))
    assert not q.is_rate_limit_error(ErrorInfo("Nope.", "x", "network"))
    assert not q.is_rate_limit_error(None)


def test_a_limited_site_loses_the_probe_lever_and_a_slot() -> None:
    kw = {"enabled": True, "cookies_configured": False}
    assert q.may_reuse_probe(URL, limited_sites=set(), **kw)
    assert not q.may_reuse_probe(URL, limited_sites={"youtube.com"}, **kw)
    assert q.may_reuse_probe("https://vimeo.com/1", limited_sites={"youtube.com"}, **kw)
    assert not q.may_reuse_probe(URL, limited_sites=set(), enabled=False, cookies_configured=False)
    # One download at a time for a limited site, others unaffected.
    assert q.site_slot_free("youtube.com", set(), ["youtube.com"])
    assert not q.site_slot_free("youtube.com", {"youtube.com"}, ["youtube.com"])
    assert q.site_slot_free("youtube.com", {"youtube.com"}, ["vimeo.com"])
    assert q.site_slot_free("vimeo.com", {"youtube.com"}, ["youtube.com"])


def test_signed_in_instagram_and_tiktok_and_media_items_never_get_a_lever() -> None:
    off = {"enabled": True, "limited_sites": set()}
    for url in (IG_REEL, TT):
        assert q.may_reuse_probe(url, cookies_configured=False, **off)
        assert not q.may_reuse_probe(url, cookies_configured=True, **off)
    assert q.may_reuse_probe(URL, cookies_configured=True, **off)  # signed in to YouTube is fine
    assert not q.may_reuse_probe(IG_TRAY, cookies_configured=False, **off)  # media engine


class _SlowHandle(FakeHandle):
    """A finished-after-a-moment download that counts how many run at once."""

    def __init__(self, gate: dict[str, Any], returncode: int = 0, raw_log: str = "") -> None:
        super().__init__(returncode, raw_log)
        self.gate = gate

    def wait(self, timeout: float | None = None) -> int:
        with self.gate["lock"]:
            self.gate["now"] += 1
            self.gate["peak"] = max(self.gate["peak"], self.gate["now"])
        time.sleep(0.15)
        with self.gate["lock"]:
            self.gate["now"] -= 1
        return self.returncode


def _fake_info(url, ytdlp="yt-dlp", **kw):
    return {"id": url[-6:], "title": "T", "formats": [{"format_id": "1", "url": "https://m/x"}]}


def test_first_429_stops_the_probe_lever_and_limits_the_site_to_one(harness) -> None:  # noqa: F811
    gate = {"lock": threading.Lock(), "now": 0, "peak": 0}
    seen: list[Any] = []
    calls = {"n": 0}

    def fake_run(opts, on_event):
        seen.append(opts)
        calls["n"] += 1
        if calls["n"] <= 2:  # the info run and its one re-run from the URL both get 429
            return FakeHandle(1, "ERROR: HTTP Error 429: Too Many Requests")
        return _SlowHandle(gate)

    h = harness(probe_url=_fake_info, run_download=fake_run, concurrency=2)
    first_item = h.queue.add("https://www.youtube.com/watch?v=aaaaaaaaaaa")
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    row = h.queue.item(first_item["id"])
    assert row["state"] == "failed" and row["error"]["code"] == "http_429"
    assert h.queue.rate_limited_sites() == {"youtube.com"}
    assert seen[0].info_json is not None  # the lever was on until the 429
    seen.clear()
    for tail in ("bbbbbbbbbbb", "ccccccccccc"):
        h.queue.add(f"https://www.youtube.com/watch?v={tail}")
    other = h.queue.add("https://vimeo.com/123456789")
    assert wait_for(lambda: h.queue.wait_until_idle(0.01), 15)
    assert all(o.info_json is None for o in seen if "youtube" in o.url)
    assert gate["peak"] >= 1
    states = {i["id"]: i["state"] for i in h.queue.items()}
    assert set(states.values()) == {"failed", "done"}
    assert h.queue.item(other["id"])["state"] == "done"


def test_a_limited_site_never_runs_two_downloads_together(harness) -> None:  # noqa: F811
    gate = {"lock": threading.Lock(), "now": 0, "peak": 0}
    h = harness(probe_url=_fake_info, run_download=lambda o, e: _SlowHandle(gate), concurrency=3)
    h.queue._limited_sites.add("youtube.com")
    events: list[dict] = []
    h.queue.add_listener(events.append)
    for tail in ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"):
        h.queue.add(f"https://www.youtube.com/watch?v={tail}")
    h.queue.start()
    assert h.queue.wait_until_idle(20)
    assert gate["peak"] == 1
    assert [i["state"] for i in h.queue.items()] == ["done"] * 3
    waiting = [e for e in events if e["type"] == "item" and e["item"]["wait_hint"] == "rate_limited"]
    assert waiting  # the queued rows say why they wait


def test_an_unlimited_site_still_runs_in_parallel(harness) -> None:  # noqa: F811
    gate = {"lock": threading.Lock(), "now": 0, "peak": 0}
    h = harness(probe_url=_fake_info, run_download=lambda o, e: _SlowHandle(gate), concurrency=3)
    for tail in ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"):
        h.queue.add(f"https://www.youtube.com/watch?v={tail}")
    h.queue.start()
    assert h.queue.wait_until_idle(20)
    assert gate["peak"] >= 2


def test_signed_in_instagram_item_downloads_from_the_url(harness) -> None:  # noqa: F811
    seen: list[Any] = []

    def fake_run(opts, on_event):
        seen.append(opts)
        return FakeHandle()

    h = harness(probe_url=_fake_info, run_download=fake_run)
    h.queue.set_cookies("firefox", None)
    h.queue.add(IG_REEL)
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert seen and all(o.info_json is None for o in seen)


# -- the honest ETA ---------------------------------------------------------------------------
def test_smooth_speed_is_an_exponential_moving_average() -> None:
    assert q.SPEED_EMA_ALPHA == pytest.approx(0.2)
    assert q.smooth_speed(None, 1000.0) == 1000.0
    assert q.smooth_speed(1000.0, 2000.0) == pytest.approx(1200.0)
    step = q.smooth_speed(1200.0, 600.0)
    assert step == pytest.approx(1080.0)
    # A single spike moves the average by only a fifth of the jump.
    assert q.smooth_speed(1000.0, 11000.0) == pytest.approx(3000.0)


def test_smoothed_eta() -> None:
    assert q.smoothed_eta(10_000, 4_000, 1_000) == pytest.approx(6.0)
    assert q.smoothed_eta(10_000, 10_000, 1_000) == 0.0
    assert q.smoothed_eta(None, 4_000, 1_000) is None
    assert q.smoothed_eta(10_000, 4_000, 0) is None
    assert q.smoothed_eta(10_000, None, 1_000) is None


def _event(speed: float, done: int, total: int = 100_000, eta: float = 1.0) -> dict[str, Any]:
    return {"type": "progress", "stage": "downloading", "speed": speed,
            "downloaded_bytes": done, "total_bytes": total, "eta": eta, "percent": 1.0}


def test_the_queue_ignores_the_first_two_seconds_then_smooths(harness) -> None:  # noqa: F811
    clock = {"t": 0.0}
    h = harness(probe_info=None, clock=lambda: clock["t"])
    item = h.queue._items[h.queue.add(URL)["id"]]
    on = h.queue._on_progress
    on(item, _event(1000.0, 1_000))  # t = 0: the first sample starts the warm-up
    assert item.speed == 1000.0 and item.speed_ema is None
    clock["t"] = 1.9
    on(item, _event(9000.0, 2_000))
    assert item.speed == 9000.0 and item.speed_ema is None  # shown as reported, kept out of the average
    clock["t"] = 2.0
    on(item, _event(2000.0, 10_000))
    assert item.speed_ema == pytest.approx(2000.0)  # seeded by the first sample after the warm-up
    assert item.eta == pytest.approx((100_000 - 10_000) / 2000.0)
    clock["t"] = 3.0
    on(item, _event(4000.0, 12_000))
    assert item.speed == pytest.approx(2400.0)
    assert item.eta == pytest.approx((100_000 - 12_000) / 2400.0)
    snap = h.queue.item(item.id)["progress"]
    assert snap["speed"] == pytest.approx(2400.0)


def test_a_new_file_restarts_the_average(harness) -> None:  # noqa: F811
    clock = {"t": 0.0}
    h = harness(probe_info=None, clock=lambda: clock["t"])
    item = h.queue._items[h.queue.add(URL)["id"]]
    on = h.queue._on_progress
    on(item, _event(1000.0, 5_000))
    clock["t"] = 3.0
    on(item, _event(1000.0, 9_000))
    assert item.speed_ema == pytest.approx(1000.0)
    clock["t"] = 3.5
    on(item, _event(50_000.0, 100))  # audio stream after the video: bytes start again
    assert item.speed_ema is None and item.speed == 50_000.0


def test_file_counting_items_are_not_smoothed(harness) -> None:  # noqa: F811
    h = harness(probe_info=None)
    item = h.queue._items[h.queue.add(URL)["id"]]
    h.queue._on_progress(item, {"type": "progress", "stage": "downloading", "speed": None,
                                "files_done": 1, "files_total": 3, "percent": 33.3})
    assert item.speed is None and item.speed_ema is None and item.files_done == 1


# -- carousel slides land one by one (verified; the queue relays every file) -------------------
def test_files_done_follows_each_saved_file(harness) -> None:  # noqa: F811
    h = harness(probe_info=None)
    item = h.queue._items[h.queue.add(IG_TRAY)["id"]]
    for done in (1, 2, 3):
        h.queue._on_progress(item, {"type": "progress", "stage": "downloading", "speed": None,
                                    "files_done": done, "files_total": 3, "percent": done * 33.3})
        assert h.queue.item(item.id)["progress"]["files_done"] == done


# -- "Starting..." reasons ----------------------------------------------------------------------
def test_wait_hint_picks_the_first_reason_that_applies() -> None:
    assert q.wait_hint(rate_limited=True, retrying_network=True, signed_in=True) == "rate_limited"
    assert q.wait_hint(rate_limited=False, retrying_network=True, signed_in=True) == "network"
    assert q.wait_hint(rate_limited=False, retrying_network=False, signed_in=True) == "signing_in"
    assert q.wait_hint(rate_limited=False, retrying_network=False, signed_in=False) is None


def test_stall_reason_waits_ten_seconds() -> None:
    assert m.STALL_AFTER == 10.0
    assert m.stall_reason("signing_in", 9.9) is None
    assert m.stall_reason("signing_in", 10.0) == "Signing in"
    assert m.stall_reason("network", 30) == "Waiting for the network"
    assert m.stall_reason("rate_limited", 30) == "Rate limited, waiting"
    assert m.stall_reason(None, 30) is None
    assert m.stall_reason("unheard-of", 30) is None


def test_a_row_that_has_not_started_says_why_after_ten_seconds() -> None:
    row = make_snapshot(1, "downloading", wait_hint="signing_in", quiet_since=100.0)
    assert m.describe_row(row, now=105.0).sub == "Starting"
    assert m.describe_row(row, now=111.0).sub == "Starting... Signing in"
    plain = make_snapshot(2, "downloading", quiet_since=100.0)
    assert m.describe_row(plain, now=111.0).sub == "Starting..."
    probing = make_snapshot(3, "probing", wait_hint="network", quiet_since=100.0)
    assert m.describe_row(probing, now=105.0).sub == "Looking at the link"
    assert m.describe_row(probing, now=111.0).sub == "Starting... Waiting for the network"
    queued = make_snapshot(4, "queued", wait_hint="rate_limited")
    assert m.describe_row(queued).sub == "Rate limited, waiting"
    assert m.describe_row(make_snapshot(5, "queued")).sub == "Starts next"


def test_a_row_with_progress_keeps_its_speed_text() -> None:
    row = make_snapshot(1, "downloading", wait_hint="signing_in", quiet_since=0.0,
                        progress={"speed": 4_200_000.0, "eta": 97.0, "percent": 37.0})
    assert "Starting" not in m.describe_row(row, now=500.0).sub


def test_the_model_stamps_quiet_time_only_when_something_moves(monkeypatch) -> None:
    clock = {"t": 50.0}
    monkeypatch.setattr(m.time, "monotonic", lambda: clock["t"])
    model = m.DownloadModel()
    model.upsert(make_snapshot(1, "downloading"))
    assert model.snapshot_at(0)["quiet_since"] == 50.0
    clock["t"] = 70.0
    model.upsert({**make_snapshot(1, "downloading"), "title": "Named"})  # a title only
    assert model.snapshot_at(0)["quiet_since"] == 50.0
    model.upsert(make_snapshot(1, "downloading", progress={"percent": 5.0}))
    assert model.snapshot_at(0)["quiet_since"] == 70.0


def test_descriptions_stay_plain_text_without_icons() -> None:
    for state, hint in (("downloading", "signing_in"), ("probing", "network"), ("queued", "rate_limited")):
        text = m.describe_row(make_snapshot(1, state, wait_hint=hint, quiet_since=0.0), now=99.0)
        for part in (text.sub, text.big, text.meta):
            assert all(ord(c) < 0x2190 or c == "·" for c in part), part


# -- the instant card ---------------------------------------------------------------------------
def test_host_title() -> None:
    assert m.host_title("https://www.youtube.com/watch?v=a") == "youtube.com"
    assert m.host_title("https://vimeo.com/1") == "vimeo.com"
    assert m.host_title("nonsense") == "nonsense"
    assert m.host_title(None) == ""


def test_adding_a_link_shows_its_host_at_once_and_the_probe_fills_the_title(qapp, ui_queue) -> None:
    window = MainWindow(ui_queue, version_fn=lambda: "t", tray_factory=lambda w: None)
    try:
        window.add_text("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert window.model.rowCount() == 1
        row = window.model.snapshot_at(0)
        assert m.DownloadModel.title_of(row) == "youtube.com"
        assert m.DownloadModel.spoken(row).startswith("youtube.com")
        window.model.upsert({**row, "title": "Never Gonna Give You Up", "state": "probing"})
        assert m.DownloadModel.title_of(window.model.snapshot_at(0)) == "Never Gonna Give You Up"
    finally:
        window.bridge.close()


def test_the_thumbnail_is_asked_for_as_soon_as_the_probe_names_it(harness) -> None:  # noqa: F811
    """The queue announces title and picture link before the download starts (no wait for it)."""
    order: list[str] = []

    def probe(url, ytdlp="yt-dlp", **kw):
        return {"id": "abcdefghijk", "title": "T", "thumbnail": "https://img.example/t.jpg",
                "formats": [{"format_id": "1", "url": "https://m/x"}]}

    def fake_run(opts, on_event):
        order.append("download")
        return FakeHandle()

    h = harness(probe_url=probe, run_download=fake_run)
    h.queue.add_listener(
        lambda e: order.append("thumb") if e["type"] == "item" and e["item"]["thumbnail"] else None)
    h.queue.add("https://www.youtube.com/watch?v=abcdefghijk")
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert order.index("thumb") < order.index("download")
