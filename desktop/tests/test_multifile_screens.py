"""Brief 10C: desktop rows and settings for photo posts, carousels, stories and songs."""

from __future__ import annotations

import json
import sqlite3
import time
import unicodedata
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QRectF, Qt
from PySide6.QtGui import QFontInfo, QImage, QPainter
from PySide6.QtWidgets import QStyleOptionViewItem

from conftest import make_snapshot
from elisium_downloader.engine import media, queue as queue_mod
from elisium_downloader.engine.archive import Archive
from elisium_downloader.engine.history import History
from elisium_downloader.engine.queue import (
    ALREADY_SAVED_NOTE,
    DownloadQueue,
    _format_label_from,
    _thumbnail_from,
)
from elisium_downloader.ui import history_page as hp
from elisium_downloader.ui import settings as st
from elisium_downloader.ui import theme, widgets
from elisium_downloader.ui.history_page import HistoryPage
from elisium_downloader.ui.main_window import MainWindow
from elisium_downloader.ui.model import LOOKING_UP_TITLE, DownloadModel, describe_row
from elisium_downloader.ui.settings_page import SettingsPage
from test_media import IG, TIKTOK, TRAY, read_log, value_after
from test_media_queue import media_harness  # noqa: F401  (fixture)
from test_mix import POST, music_post, mix_harness  # noqa: F401  (fixture)
from test_queue import FakeHandle, wait_for

PHOTO_POST = f"{IG}/p/CAbc123xyz/"
CAROUSEL = f"{IG}/stories/cafe_northfield/"
NOTE_FULL = "Kept the full song: the post doesn't say which part it plays."
NOTE_VIDEO = "Saved the photos and the song; the video couldn't be made."


def pump(ms: int = 0) -> None:
    end = time.monotonic() + ms / 1000
    QCoreApplication.processEvents()
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


# -- row text ----------------------------------------------------------------
def test_row_text_for_a_single_video() -> None:
    row = make_snapshot(1, "downloading", title="Walk", url="https://www.youtube.com/watch?v=a",
                        format_label="1080p MP4",
                        progress={"percent": 37.0, "total_bytes": 680_000_000, "speed": 4_404_019.0,
                                  "eta": 97})
    text = describe_row(row)
    assert text.meta == "YouTube · 1080p MP4 · 648.5 MB"
    assert text.big == "37%" and text.note == ""


def test_row_text_for_a_photo_post() -> None:
    row = make_snapshot(2, "queued", url=PHOTO_POST, format_label="6 photos + song")
    assert describe_row(row).meta == "Instagram · 6 photos + song"


def test_row_text_for_a_carousel_mid_download() -> None:
    row = make_snapshot(3, "downloading", title="Monument Hill", url=PHOTO_POST,
                        format_label="6 photos + song",
                        progress={"files_done": 3, "files_total": 7, "speed": 2_000_000.0, "eta": 7})
    text = describe_row(row)
    assert text.meta == "Instagram · 6 photos + song · 3 of 7 files"
    assert text.big == "43%" and text.big_is_percent  # the percent comes from the files


def test_row_text_for_a_done_post_with_a_note() -> None:
    row = make_snapshot(4, "done", title="Monument Hill", url=PHOTO_POST, note=NOTE_FULL,
                        format_label="6 photos + song", progress={"files_done": 7, "files_total": 7})
    text = describe_row(row)
    assert text.meta == "Instagram · 6 photos + song · 7 files"
    assert text.note == NOTE_FULL and text.sub == "Open · Show in folder"


def test_a_skipped_post_says_how_many_files_not_zero_of_n() -> None:
    row = make_snapshot(6, "skipped", title="Dawn", url=PHOTO_POST, note=ALREADY_SAVED_NOTE,
                        format_label="3 photos", progress={"files_done": 0, "files_total": 3})
    assert describe_row(row).meta == "Instagram · 3 photos · 3 files"


def test_row_without_a_format_label_is_unchanged() -> None:
    row = make_snapshot(5, "queued", url="https://www.youtube.com/watch?v=a",
                        progress={"total_bytes": 1_331_439_861})
    assert describe_row(row).meta == "YouTube · 1.2 GB"


@pytest.mark.parametrize("url", [PHOTO_POST, CAROUSEL, f"{IG}/stories/highlights/17912345678901234/",
                                 TIKTOK])
def test_a_post_link_says_looking_up_until_the_probe_names_it(url) -> None:
    for state in ("queued", "probing"):
        assert DownloadModel.title_of(make_snapshot(1, state, url=url)) == LOOKING_UP_TITLE
    assert LOOKING_UP_TITLE == "Looking up the post..."
    assert DownloadModel.title_of(make_snapshot(1, "downloading", url=url, title="Café")) == "Café"
    assert DownloadModel.spoken(make_snapshot(1, "probing", url=url)).startswith(LOOKING_UP_TITLE)


def test_other_links_show_the_host_as_title_until_the_probe_names_them() -> None:
    for url, host in (("https://www.youtube.com/watch?v=a", "youtube.com"),
                      (f"{IG}/reel/CAbc123xyz/", "instagram.com")):
        assert DownloadModel.title_of(make_snapshot(1, "queued", url=url)) == host
        assert DownloadModel.title_of(make_snapshot(1, "failed", url=url)) == url


def test_adding_a_post_link_shows_the_row_at_once(qapp, ui_queue) -> None:
    window = MainWindow(ui_queue, version_fn=lambda: "t", tray_factory=lambda w: None)
    try:
        window.add_text(PHOTO_POST)
        assert window.model.rowCount() == 1
        assert DownloadModel.title_of(window.model.snapshot_at(0)) == LOOKING_UP_TITLE
        assert not window.findChildren(type(window))  # no extra window or dialog
    finally:
        window.bridge.close()
        window.deleteLater()


# -- thumbnail and format flow from the probe to the row ---------------------------
def test_thumbnail_and_format_helpers() -> None:
    assert _thumbnail_from({"thumbnail": "https://i.example/t.jpg"}) == "https://i.example/t.jpg"
    assert _thumbnail_from({"thumbnails": [{"url": "https://i.example/a.jpg"},
                                           {"url": "https://i.example/b.jpg"}]}) == "https://i.example/b.jpg"
    assert _thumbnail_from({"thumbnail": "file:///etc/passwd"}) is None
    assert _thumbnail_from(None) is None
    assert _format_label_from({"height": 1080, "ext": "mp4"}, ()) == "1080p MP4"
    assert _format_label_from({"ext": "webm"}, ()) == "WEBM"
    assert _format_label_from({"height": 1080, "ext": "mp4"}, ("-x", "--audio-format", "mp3")) == "MP3 audio"
    assert _format_label_from({}, ()) is None


def test_ytdlp_probe_reaches_the_snapshot_and_not_the_history(tmp_path: Path) -> None:
    data, out, tmp = tmp_path / "data", tmp_path / "out", tmp_path / "tmp"
    for folder in (data, out, tmp):
        folder.mkdir()
    history = History(data / "history.sqlite")
    info = {"id": "abc", "title": "Walk", "extractor_key": "Youtube", "formats": [{}], "url": "u",
            "thumbnail": "https://i.example/t.jpg", "height": 1080, "ext": "mp4"}
    queue = DownloadQueue(history, Archive(data / "archive.txt"), out, tmp, sleep=lambda _s: None,
                          probe_url=lambda *a, **k: info,
                          run_download=lambda *a, **k: FakeHandle(0))
    try:
        item = queue.add("https://www.youtube.com/watch?v=abc")
        queue.start()
        assert queue.wait_until_idle(10)
        row = queue.item(item["id"])
        assert row["thumbnail"] == "https://i.example/t.jpg"
        assert row["format_label"] == "1080p MP4"
        assert "thumbnail" not in history.get(item["record_id"])
        assert describe_row(row).meta.startswith("YouTube · 1080p MP4")
    finally:
        queue.stop(1.0)
        history.close()


def test_media_probe_reaches_the_snapshot(media_harness) -> None:  # noqa: F811
    h = media_harness(fixture="instagram_carousel_mixed.json")
    item = h.run_one(CAROUSEL)
    assert item["thumbnail"] == "https://cdn.example.com/3301000000000000001.jpg?sig=abc"
    assert item["format_label"] == "2 photos + 1 video"
    assert "thumbnail" not in h.history.get(item["record_id"])


def test_plan_labels_and_cover() -> None:
    f = media.PlannedFile
    plan = media.MediaPlan("instagram", (f("image", "1", 1, "jpg"), f("audio", "2", 2, "m4a")))
    assert plan.format_label == "1 photo + song"
    assert media.MediaPlan("instagram", ()).format_label is None
    video_only = media.parse_probe(json.dumps([
        [2, {"category": "instagram", "username": "u", "thumbnail": "https://i.example/c.jpg"}],
        [3, "https://cdn.example.com/v.mp4", {"category": "instagram", "media_id": "1", "num": 1,
                                              "extension": "mp4", "username": "u"}]]))
    assert video_only.thumbnail == "https://i.example/c.jpg"


# -- the note reaches History -------------------------------------------------------
def test_history_keeps_the_note_and_the_file_count(mix_harness) -> None:  # noqa: F811
    h = mix_harness(with_ffmpeg=False)
    item = h.run_one()
    assert item["note"] == NOTE_VIDEO or NOTE_VIDEO in item["note"]
    row = h.history.get(item["record_id"])
    assert row["note"] == item["note"] and row["files_total"] == 3


def test_a_retry_clears_the_old_note_in_the_history(mix_harness) -> None:  # noqa: F811
    h = mix_harness(with_ffmpeg=False)
    item = h.run_one()
    assert h.history.get(item["record_id"])["note"]
    h.queue._set_state(h.queue._items[item["id"]], "queued", clear_error=True)
    h.queue._items[item["id"]].note = None
    h.queue._set_state(h.queue._items[item["id"]], "probing")
    assert h.history.get(item["record_id"])["note"] is None


def test_history_page_shows_the_note_and_old_entries_load(qapp, ui_queue) -> None:
    h = ui_queue.history
    a = h.add("https://www.instagram.com/p/AAA/", title="With note", state="done", note=NOTE_FULL,
              files_total=7)
    b = h.add("https://www.youtube.com/watch?v=b", title="Old entry", state="done")
    h._conn.execute("UPDATE downloads SET note = NULL, files_total = NULL WHERE id = ?", (b,))
    page = HistoryPage(ui_queue)
    page.resize(980, 600)
    try:
        rows = {page.model.row_at(r)["title"]: page.model.row_at(r) for r in range(page.model.rowCount())}
        assert rows["With note"]["note"] == NOTE_FULL and rows["Old entry"].get("note") is None
        geo = page.delegate.geometry(QRectF(0, 0, 900, page.delegate.row_height(page.table.font())),
                                     rows["With note"], page.table.font())
        assert geo.note is not None and geo.card.contains(geo.note)
        assert page.delegate.geometry(QRectF(0, 0, 900, 90), rows["Old entry"], page.table.font()).note is None
        page.show()
        pump(50)
        image = page.grab()  # paints both rows without error
        assert not image.isNull()
    finally:
        page.deleteLater()


# -- Open / Show in folder ---------------------------------------------------------
def test_open_finished_file_for_one_file_folder_for_a_post(tmp_path, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(widgets.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    folder = tmp_path / "owner"
    folder.mkdir()
    first = folder / "a [1] 1.jpg"
    first.write_text("x")
    widgets.open_finished(str(first), None, tmp_path)
    widgets.open_finished(str(first), 1, tmp_path)
    widgets.open_finished(str(first), 7, tmp_path)
    widgets.open_finished(str(folder / "gone.jpg"), 7, tmp_path)
    widgets.open_finished(None, 7, tmp_path)
    assert opened == [str(first), str(first), str(folder), str(folder), str(tmp_path)]


def test_show_finished_selects_the_first_file_else_opens_the_folder(tmp_path, monkeypatch) -> None:
    opened, selected = [], []
    monkeypatch.setattr(widgets.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    first = tmp_path / "a [1] 1.jpg"
    first.write_text("x")
    monkeypatch.setattr(widgets, "_show_item", lambda path: selected.append(str(path)) or True)
    widgets.show_finished(str(first), tmp_path)
    assert selected == [str(first)] and opened == []
    monkeypatch.setattr(widgets, "_show_item", lambda path: False)  # no file manager on the bus
    widgets.show_finished(str(first), tmp_path)
    assert opened == [str(tmp_path)]


def test_window_open_buttons_follow_the_row(qapp, ui_queue, tmp_path, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(widgets.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    shown: list[str] = []
    monkeypatch.setattr(widgets, "_show_item", lambda path: shown.append(str(path)) or True)
    folder = tmp_path / "out" / "owner"
    folder.mkdir(parents=True)
    first = folder / "o [1] 1.jpg"
    first.write_text("x")
    window = MainWindow(ui_queue, version_fn=lambda: "t", tray_factory=lambda w: None)
    try:
        window.model.load([make_snapshot(1, "done", title="Post", url=PHOTO_POST, file_path=str(first),
                                         progress={"files_done": 7, "files_total": 7})])
        window.table.selectRow(0)
        window.launch_action.trigger()  # "Open" on a post: its folder
        window.open_action.trigger()  # "Show in folder": the first file selected
        assert opened == [str(folder)] and shown == [str(first)]
        window.model.load([make_snapshot(1, "done", title="Clip", file_path=str(first))])
        window.table.selectRow(0)
        window.launch_action.trigger()  # one file: the file itself
        assert opened[-1] == str(first)
    finally:
        window.bridge.close()
        window.deleteLater()


def test_history_open_follows_the_file_count(qapp, ui_queue, tmp_path, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(widgets.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    folder = tmp_path / "owner"
    folder.mkdir()
    first = folder / "o [1] 1.jpg"
    first.write_text("x")
    ui_queue.history.add(PHOTO_POST, title="Post", state="done", file_path=str(first), files_total=7)
    page = HistoryPage(ui_queue)
    try:
        page.table.selectRow(0)
        page.open_file()
        assert opened == [str(folder)]
    finally:
        page.deleteLater()


# -- "Download again anyway" ---------------------------------------------------------
def test_force_re_add_bypasses_the_archive_and_a_normal_one_does_not(media_harness) -> None:  # noqa: F811
    h = media_harness(fixture="instagram_carousel_mixed.json", bracket_ids=True)
    item = h.run_one(CAROUSEL)
    assert item["state"] == "done"
    assert "--download-archive" in h.gdl_downloads()[0]
    # a normal re-add of a finished item whose files are there does nothing
    again = h.queue.add(CAROUSEL)
    assert again["id"] == item["id"] and h.queue.item(item["id"])["state"] == "done"
    assert len(h.gdl_downloads()) == 1
    # "Download again anyway": a new run, without the archive
    h.queue.add(CAROUSEL, force=True)
    assert h.queue.wait_until_idle(15)
    runs = h.gdl_downloads()
    assert len(runs) == 2 and "--download-archive" not in runs[1]
    row = h.queue.item(item["id"])
    # every file is in the folder already: "Already saved" instead of a silent finish
    assert row["state"] == "skipped" and row["note"] == ALREADY_SAVED_NOTE
    assert h.history.get(item["record_id"])["note"] == ALREADY_SAVED_NOTE


def test_force_brings_back_deleted_files(media_harness) -> None:  # noqa: F811
    h = media_harness(fixture="instagram_carousel_mixed.json", bracket_ids=True)
    item = h.run_one(CAROUSEL)
    folder = h.out / "cafe_northfield"
    for path in folder.iterdir():
        path.unlink()
    h.queue.add(CAROUSEL, force=True)
    assert h.queue.wait_until_idle(15)
    row = h.queue.item(item["id"])
    assert row["state"] == "done" and row["note"] is None
    assert len(list(folder.iterdir())) == 3
    assert "--download-archive" not in h.gdl_downloads()[-1]


def test_force_on_a_fresh_queue_runs_without_the_archive(media_harness) -> None:  # noqa: F811
    h = media_harness(fixture="instagram_carousel_mixed.json")
    h.queue.add(CAROUSEL, force=True)
    h.queue.start()
    assert h.queue.wait_until_idle(15)
    assert all("--download-archive" not in run for run in h.gdl_downloads())


def test_force_is_ignored_for_a_plain_video_link(media_harness) -> None:  # noqa: F811
    h = media_harness(fixture="instagram_carousel_mixed.json")
    snap = h.queue.add("https://www.youtube.com/watch?v=abcdefghijk", force=True)
    assert h.queue._items[snap["id"]].force is False


def test_the_media_archive_flag_is_the_only_difference(tmp_path) -> None:
    base = dict(url=PHOTO_POST, directory=tmp_path / "d", config_path=tmp_path / "c.json",
                archive_path=tmp_path / "a.sqlite3")
    with_archive = media.build_command(media.MediaOptions(**base))
    without = media.build_command(media.MediaOptions(**base, use_archive=False))
    assert "--download-archive" in with_archive and "--download-archive" not in without
    assert [a for a in with_archive if a not in ("--download-archive", str(tmp_path / "a.sqlite3"))] == without


def test_history_download_again_forces(qapp, ui_queue, monkeypatch) -> None:
    ui_queue.history.add(PHOTO_POST, title="Post", state="done")
    page = HistoryPage(ui_queue)
    seen: list[tuple] = []
    monkeypatch.setattr(ui_queue, "add", lambda url, **kw: seen.append((url, kw)) or {})
    try:
        page.table.selectRow(0)
        page.download_again()
        assert seen == [(PHOTO_POST, {"force": True})]
    finally:
        page.deleteLater()


# -- the Photos and music settings ---------------------------------------------------
def names(h) -> list[str]:
    return h.owner_files()


@pytest.mark.parametrize(
    ("mode", "length", "photos_song_video", "ffmpeg_calls", "files_total"),
    [
        ("video", "snippet", ("jpg", "jpg", "song", "mix"), 2, 4),
        ("video", "full", ("jpg", "jpg", "full", "mix"), 1, 4),
        ("song", "snippet", ("jpg", "jpg", "song"), 1, 3),
        ("song", "full", ("jpg", "jpg", "full"), 0, 3),
        ("photos", "snippet", ("jpg", "jpg"), 0, 2),
        ("photos", "full", ("jpg", "jpg"), 0, 2),
    ],
)
def test_each_setting_combination_changes_what_is_made(
    mix_harness, mode, length, photos_song_video, ffmpeg_calls, files_total  # noqa: F811
) -> None:
    h = mix_harness()
    h.queue.set_photo_mode(mode)
    h.queue.set_song_length(length)
    item = h.run_one()
    assert item["state"] == "done" and item["note"] is None
    found = names(h)
    kinds = [
        "mix" if n.endswith("_mix].mp4") else "song" if n.endswith(" song.m4a")
        else "full" if n.endswith("99 3.m4a") else "jpg"
        for n in found
    ]
    assert sorted(kinds) == sorted(photos_song_video)
    calls = h.ffmpeg_calls()
    assert len(calls) == ffmpeg_calls
    assert item["progress"]["files_total"] == files_total
    assert item["progress"]["files_done"] == files_total and item["progress"]["percent"] == 100.0
    if length == "full" and ffmpeg_calls:
        assert all("-filter_complex" in c for c in calls)  # only the mix, no cut
    if mode == "song" and length == "snippet":
        assert "-filter_complex" not in calls[0] and "-c" in calls[0]  # only the cut
    if mode != "video":
        assert "converting" not in h.states() or ffmpeg_calls


def test_photos_only_needs_no_ffmpeg_and_no_note(mix_harness) -> None:  # noqa: F811
    h = mix_harness(with_ffmpeg=False)
    h.queue.set_photo_mode("photos")
    item = h.run_one()
    assert item["state"] == "done" and item["note"] is None
    assert len(names(h)) == 2 and not any(n.endswith(".m4a") for n in names(h))


def test_photos_and_song_without_ffmpeg_keeps_the_full_song_without_a_video_note(mix_harness) -> None:  # noqa: F811
    h = mix_harness(with_ffmpeg=False)
    h.queue.set_photo_mode("song")
    item = h.run_one()
    assert item["state"] == "done"
    assert NOTE_VIDEO not in (item["note"] or "")  # no video was asked for
    assert len(names(h)) == 3


def test_setting_values_are_checked() -> None:
    queue = DownloadQueue.__new__(DownloadQueue)
    import threading

    queue._lock = threading.RLock()
    queue._cond = threading.Condition(queue._lock)
    with pytest.raises(ValueError):
        queue.set_photo_mode("everything")
    with pytest.raises(ValueError):
        queue.set_song_length("long")
    assert queue_mod.PHOTO_MODES == ("video", "song", "photos")
    assert queue_mod.SONG_LENGTHS == ("snippet", "full")


def test_settings_defaults_validation_and_old_files(tmp_path) -> None:
    assert (st.Settings().photo_mode, st.Settings().song_length) == ("video", "snippet")
    bad = st.Settings(photo_mode="x", song_length=3)
    assert (bad.photo_mode, bad.song_length) == ("video", "snippet")
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"concurrency": 3}))  # a file from before brief 10C
    loaded = st.load(path)
    assert (loaded.photo_mode, loaded.song_length) == ("video", "snippet")
    st.save(st.Settings(photo_mode="photos", song_length="full"), path)
    again = st.load(path)
    assert (again.photo_mode, again.song_length) == ("photos", "full")


def test_settings_page_has_real_photo_and_song_controls(qapp, ui_queue, tmp_path) -> None:
    path = tmp_path / "cfg" / "settings.json"
    page = SettingsPage(st.Settings(), ui_queue, path, version_fn=lambda: "1")
    try:
        for combo, name in ((page.photo_mode_combo, "Photo posts with a song"),
                            (page.song_length_combo, "Song length")):
            assert combo.accessibleName() == name and combo.accessibleDescription()
        assert [page.photo_mode_combo.itemText(i) for i in range(3)] == [
            "Photos, song and video", "Photos and song only", "Photos only"]
        assert [page.song_length_combo.itemText(i) for i in range(2)] == ["Post's snippet", "Full song"]
        assert page.groups["Photos and music"].isAncestorOf(page.photo_mode_combo)
        page.photo_mode_combo.setCurrentIndex(2)
        page.song_length_combo.setCurrentIndex(1)
        saved = json.loads(path.read_text())
        assert (saved["photo_mode"], saved["song_length"]) == ("photos", "full")
        assert (ui_queue._photo_mode, ui_queue._song_length) == ("photos", "full")
    finally:
        page.deleteLater()


# -- looks: both schemes, nothing under 12 px, no emoji --------------------------------
ROWS = [
    make_snapshot(1, "downloading", title="Walk", url="https://www.youtube.com/watch?v=a",
                  format_label="1080p MP4", progress={"percent": 37.0, "total_bytes": 680_000_000}),
    make_snapshot(2, "downloading", title="Monument Hill", url=PHOTO_POST,
                  format_label="6 photos + song", progress={"files_done": 3, "files_total": 7}),
    make_snapshot(3, "done", title="Dawn", url=PHOTO_POST, note=NOTE_FULL, format_label="6 photos + song",
                  progress={"files_done": 7, "files_total": 7}),
    make_snapshot(4, "probing", url=CAROUSEL),
]


@pytest.mark.parametrize("scheme", ["night", "day"])
def test_rows_paint_in_both_schemes_without_small_text_or_emoji(qapp, scheme) -> None:
    theme.apply(qapp, scheme)
    try:
        delegate = widgets.QueueDelegate()
        fonts = delegate.row_fonts(qapp.font())
        assert all(f.pixelSize() >= 12 for f in fonts.values())
        model = DownloadModel()
        model.load(ROWS)
        for r, row in enumerate(ROWS):
            text = describe_row(row)
            for part in (text.meta, text.big, text.sub, text.note, DownloadModel.title_of(row)):
                assert not any(unicodedata.category(c) in ("So", "Cs", "Co") or ord(c) > 0xFFFF
                               for c in part), part
            image = QImage(900, 100, QImage.Format.Format_ARGB32)
            image.fill(0)
            painter = QPainter(image)
            option = QStyleOptionViewItem()
            option.rect = image.rect()
            option.font = qapp.font()
            delegate.paint(painter, option, model.index(r, 0))
            painter.end()
            geo = delegate.geometry(image.rect(), row, qapp.font())
            if text.note:
                assert geo.note is not None and geo.card.contains(geo.note)
            assert geo.card.contains(geo.meta)
    finally:
        theme.reset(qapp)
