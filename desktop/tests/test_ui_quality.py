"""Probe worker, thumbnail loader, Choose quality and Playlist dialogs, window wiring."""

from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtCore import QBuffer, QCoreApplication, QIODevice, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QDialog

from elisium_downloader.engine.errors import ErrorInfo
from elisium_downloader.engine.presets import PRESETS
from elisium_downloader.engine.runner import ProbeError
from elisium_downloader.ui.main_window import MainWindow
from elisium_downloader.ui.playlist_dialog import PlaylistDialog
from elisium_downloader.ui.probe_worker import ProbeWorker
from elisium_downloader.ui.quality_dialog import QualityDialog
from elisium_downloader.ui.thumbnail import THUMB_WIDTH, ThumbnailLoader

INFO = {
    "title": "A fine video",
    "uploader": "Some Channel",
    "duration": 125,
    "thumbnail": "https://img.example/t.jpg",
    "formats": [
        {"format_id": "sb0", "ext": "mhtml", "vcodec": "none", "acodec": "none"},
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128,
         "tbr": 128, "filesize": 3_000_000},
        {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "width": 1920,
         "height": 1080, "fps": 30, "tbr": 4000, "filesize": 80_000_000},
        {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "width": 640,
         "height": 360, "fps": 30, "tbr": 500},
    ],
}
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PL123"
PLAYLIST = {
    "title": "My list",
    "entries": [
        {"id": f"v{n:02d}", "title": f"Video {n}", "url": f"https://www.youtube.com/watch?v=v{n:02d}",
         "duration": 60 * n}
        for n in range(1, 6)
    ][:2]
    + [None]
    + [
        {"id": f"v{n:02d}", "title": f"Video {n}", "url": f"https://www.youtube.com/watch?v=v{n:02d}"}
        for n in range(4, 7)
    ],
}


def wait_until(predicate, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    QCoreApplication.processEvents()
    return predicate()


def png_bytes(width: int = 480, height: int = 270) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#3366cc"))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def good_probe(url):
    return INFO


def fake_fetcher(url, callback):
    callback(png_bytes())


# -- probe worker ---------------------------------------------------------
def test_worker_success_runs_off_the_gui_thread(qapp) -> None:
    seen = {}

    def probe(url):
        seen["thread"] = threading.current_thread()
        seen["url"] = url
        return {"title": "ok"}

    worker = ProbeWorker(probe)
    results = []
    worker.finished.connect(results.append)
    worker.start("https://x/1")
    assert wait_until(lambda: results)
    assert results == [{"title": "ok"}]
    assert seen["url"] == "https://x/1"
    assert seen["thread"] is not threading.main_thread()


def test_worker_failure_carries_error_and_raw(qapp) -> None:
    info = ErrorInfo("This video is not available.", "Check the link", "video_unavailable")

    def probe(url):
        raise ProbeError(info, "ERROR: Video unavailable")

    worker = ProbeWorker(probe)
    failures = []
    worker.failed.connect(lambda i, raw: failures.append((i, raw)))
    worker.start("https://x/1")
    assert wait_until(lambda: failures)
    assert failures == [(info, "ERROR: Video unavailable")]


def test_worker_unexpected_exception_becomes_plain_failure(qapp) -> None:
    def probe(url):
        raise RuntimeError("boom")

    worker = ProbeWorker(probe)
    failures = []
    worker.failed.connect(lambda i, raw: failures.append((i, raw)))
    worker.start("u")
    assert wait_until(lambda: failures)
    assert failures[0][0].message == "Download failed." and failures[0][1] == "boom"


def test_worker_cancel_drops_late_result(qapp) -> None:
    gate = threading.Event()
    done = threading.Event()

    def probe(url):
        gate.wait(5)
        done.set()
        return {"late": True}

    worker = ProbeWorker(probe)
    results = []
    worker.finished.connect(results.append)
    worker.start("u")
    worker.cancel()
    gate.set()
    assert done.wait(5)
    wait_until(lambda: False, 0.2)
    assert results == []


# -- thumbnails -----------------------------------------------------------
def test_thumbnail_placeholder_then_scaled_image(qapp) -> None:
    pending = []
    loader = ThumbnailLoader(lambda url, cb: pending.append(cb))
    assert not loader.pixmap.isNull() and not loader.loaded
    changed = []
    loader.changed.connect(changed.append)
    loader.load("https://img.example/t.jpg")
    assert not loader.loaded
    pending[0](png_bytes(480, 270))
    assert loader.loaded and loader.pixmap.width() == THUMB_WIDTH
    assert loader.pixmap.height() == 135 and len(changed) == 1


@pytest.mark.parametrize("data", [None, b"not an image"])
def test_thumbnail_failure_keeps_a_placeholder(qapp, data) -> None:
    loader = ThumbnailLoader(lambda url, cb: cb(data))
    loader.load("https://img.example/t.jpg")
    assert not loader.loaded and not loader.pixmap.isNull()


def test_thumbnail_stale_result_is_ignored(qapp) -> None:
    pending = []
    loader = ThumbnailLoader(lambda url, cb: pending.append(cb))
    loader.load("a")
    loader.cancel()
    pending[0](png_bytes())
    assert not loader.loaded


def test_thumbnail_real_fetcher_refuses_non_http(qapp) -> None:
    loader = ThumbnailLoader()  # default Qt fetcher; file:// never touches the network
    loader.load("file:///etc/passwd")
    assert not loader.loaded


# -- Choose quality dialog ------------------------------------------------
@pytest.fixture
def make_quality(qapp, ui_queue):
    made = []

    def factory(probe=good_probe, **kw):
        dialog = QualityDialog("https://example.com/v/1", ui_queue, probe,
                               thumbnail_fetcher=kw.pop("fetcher", fake_fetcher), **kw)
        made.append(dialog)
        return dialog

    yield factory
    for dialog in made:
        dialog.reject()
        dialog.deleteLater()


def test_quality_dialog_placeholder_then_filled(make_quality) -> None:
    gate = threading.Event()

    def slow(url):
        gate.wait(5)
        return INFO

    dialog = make_quality(probe=slow)
    assert dialog.state == "probing"
    assert dialog.status_label.text() == "Checking the link..."
    assert dialog.status_label.accessibleDescription() == "Checking the link..."
    assert not dialog.progress.isHidden() and dialog.progress.maximum() == 0
    assert not dialog.download_button.isEnabled()
    assert not dialog.thumbnail_label.pixmap().isNull()  # placeholder
    gate.set()
    assert wait_until(lambda: dialog.state == "ready")
    assert dialog.title_label.text() == "A fine video"
    assert dialog.uploader_label.text() == "Some Channel"
    assert "2:05" in dialog.duration_label.text()
    assert dialog.progress.isHidden() and dialog.download_button.isEnabled()
    assert dialog.thumbnails.loaded
    assert dialog.thumbnail_label.pixmap().width() == THUMB_WIDTH
    assert dialog.quality_combo.count() == len(PRESETS)
    # storyboard skipped: 2 video rows + "no video", 1 audio row + "no audio"
    assert dialog.video_model.rowCount() == 3 and dialog.audio_model.rowCount() == 2


def test_quality_dialog_error_state_and_retry(make_quality) -> None:
    info = ErrorInfo("The site wants you to be signed in.", "Import cookies", "sign_in_required")
    calls = []

    def probe(url):
        calls.append(url)
        if len(calls) == 1:
            raise ProbeError(info, "ERROR: Sign in to confirm you're not a bot")
        return INFO

    dialog = make_quality(probe=probe)
    assert wait_until(lambda: dialog.state == "failed")
    assert dialog.status_label.text() == info.message
    assert "Import cookies" in dialog.fix_label.text()
    assert "Import cookies" in dialog.status_label.accessibleDescription()
    assert not dialog.retry_button.isHidden()
    assert not dialog.download_button.isEnabled()
    assert dialog.details_text.isHidden()
    dialog.details_button.click()
    assert not dialog.details_text.isHidden()
    assert "Sign in to confirm" in dialog.details_text.toPlainText()
    dialog.retry_button.click()
    assert dialog.state == "probing"
    assert wait_until(lambda: dialog.state == "ready")
    assert dialog.retry_button.isHidden() and len(calls) == 2


def test_quality_dialog_preset_selection(make_quality) -> None:
    dialog = make_quality()
    assert wait_until(lambda: dialog.state == "ready")
    dialog.quality_combo.setCurrentIndex(dialog.quality_combo.findData("audio-mp3"))
    assert dialog.result_selection() == ("bestaudio/best", ("-x", "--audio-format", "mp3"))
    assert "Audio only (MP3)" in dialog.selection_label.text()


def test_quality_dialog_default_preset_comes_from_settings(make_quality) -> None:
    dialog = make_quality(default_preset_id="720p")
    assert dialog.quality_combo.currentData() == "720p"


def test_exact_format_changes_the_selector(make_quality) -> None:
    dialog = make_quality()
    assert wait_until(lambda: dialog.state == "ready")
    assert dialog.advanced_box.isHidden()
    dialog.advanced_button.click()
    assert not dialog.advanced_box.isHidden()
    # best video (18 has sound, sorted first) is preselected
    assert dialog.result_selection() == ("18", ())
    # pick the video-only 1080p row and the audio row
    dialog.video_table.selectRow(2)
    dialog.audio_table.selectRow(1)
    assert dialog.result_selection() == ("137+140", ())
    assert dialog.selection_label.text() == "You will get: Video 1080p mp4 + audio 128 kbps"
    # picture only
    dialog.audio_table.selectRow(0)
    assert dialog.result_selection() == ("137", ())
    assert "no sound" in dialog.selection_label.text()
    # audio only
    dialog.video_table.selectRow(0)
    dialog.audio_table.selectRow(1)
    assert dialog.result_selection() == ("140", ())
    # closing the expander goes back to the preset
    dialog.advanced_button.click()
    assert dialog.result_selection()[0] == PRESETS["best"].format_selector


def test_download_calls_queue_add_with_choice(make_quality, ui_queue) -> None:
    dialog = make_quality()
    assert wait_until(lambda: dialog.state == "ready")
    got = []
    dialog.itemsAdded.connect(got.append)
    dialog.quality_combo.setCurrentIndex(dialog.quality_combo.findData("720p"))
    dialog.download_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    items = ui_queue.items()
    assert len(items) == 1 and items[0]["url"] == "https://example.com/v/1"
    assert items[0]["title"] == "A fine video"
    internal = ui_queue._items[items[0]["id"]]
    assert internal.format_selector == PRESETS["720p"].format_selector
    assert internal.extra_args == ()
    assert got and got[0][0][1] is True


def test_cancel_adds_nothing_and_drops_probe(make_quality, ui_queue) -> None:
    gate = threading.Event()
    dialog = make_quality(probe=lambda url: (gate.wait(5), INFO)[1])
    dialog.cancel_button.click()
    gate.set()
    wait_until(lambda: False, 0.1)
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert ui_queue.items() == []


def test_quality_dialog_accessibility(make_quality) -> None:
    dialog = make_quality()
    assert wait_until(lambda: dialog.state == "ready")
    for w in (dialog.quality_combo, dialog.advanced_button, dialog.video_table, dialog.audio_table,
              dialog.download_button, dialog.cancel_button, dialog.retry_button,
              dialog.status_label, dialog.thumbnail_label, dialog.details_button):
        assert w.accessibleName(), w
    assert dialog.focusPolicy() is not None


# -- Playlist dialog ------------------------------------------------------
@pytest.fixture
def make_playlist(qapp, ui_queue):
    made = []

    def factory(probe=lambda url: PLAYLIST, **kw):
        dialog = PlaylistDialog(PLAYLIST_URL, ui_queue, probe, **kw)
        made.append(dialog)
        return dialog

    yield factory
    for dialog in made:
        dialog.reject()
        dialog.deleteLater()


def test_playlist_dialog_lists_entries_and_unavailable(make_playlist) -> None:
    dialog = make_playlist()
    assert dialog.state == "probing" and dialog.status_label.text() == "Checking the playlist..."
    assert wait_until(lambda: dialog.state == "ready")
    assert dialog.list.count() == 6
    gone = dialog.list.item(2)
    assert "Unavailable" in gone.text()
    assert not (gone.flags() & Qt.ItemFlag.ItemIsEnabled)
    assert "(1:00)" in dialog.list.item(0).text()
    assert dialog.count_label.text() == "5 of 5 selected (1 unavailable)"


def test_playlist_select_all_none_and_count(make_playlist) -> None:
    dialog = make_playlist()
    assert wait_until(lambda: dialog.state == "ready")
    dialog.select_none_button.click()
    assert dialog.count_label.text().startswith("0 of 5 selected")
    assert not dialog.add_button.isEnabled()
    dialog.select_all_button.click()
    assert dialog.count_label.text().startswith("5 of 5 selected")
    assert dialog.add_button.isEnabled()
    dialog.list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.count_label.text().startswith("4 of 5 selected")


def test_playlist_range_field(make_playlist) -> None:
    dialog = make_playlist()
    assert wait_until(lambda: dialog.state == "ready")
    dialog.range_edit.setText("1,4-5")
    assert [e.index for e in dialog.selected_entries()] == [1, 4, 5]
    assert dialog.range_error.isHidden()
    dialog.range_edit.setText("3")  # entry 3 is unavailable: nothing ticked
    assert dialog.selected_entries() == []
    dialog.range_edit.setText("2-")
    assert not dialog.range_error.isHidden() and "2-" in dialog.range_error.text()
    assert dialog.range_edit.accessibleDescription() == dialog.range_error.text()
    dialog.range_edit.setText("1-99")
    assert "past the end" in dialog.range_error.text()
    dialog.range_edit.setText("")
    assert dialog.range_error.isHidden()


def test_add_selected_queues_each_entry_with_its_own_url(make_playlist, ui_queue) -> None:
    dialog = make_playlist()
    assert wait_until(lambda: dialog.state == "ready")
    added = []
    dialog.itemsAdded.connect(added.append)
    dialog.range_edit.setText("1-2,5")
    dialog.quality_combo.setCurrentIndex(dialog.quality_combo.findData("audio-m4a"))
    dialog.add_button.click()
    urls = sorted(i["url"] for i in ui_queue.items())
    assert urls == [
        "https://www.youtube.com/watch?v=v01",
        "https://www.youtube.com/watch?v=v02",
        "https://www.youtube.com/watch?v=v05",
    ]
    assert PLAYLIST_URL not in urls
    for item in ui_queue.items():
        internal = ui_queue._items[item["id"]]
        assert internal.format_selector == "bestaudio[ext=m4a]/bestaudio/best"
        assert internal.extra_args == ("-x", "--audio-format", "m4a")
    assert dialog.added_count == 3 and dialog.known_count == 0
    assert len(added[0]) == 3 and dialog.result() == QDialog.DialogCode.Accepted


def test_add_selected_uses_existing_dedupe(make_playlist, ui_queue) -> None:
    ui_queue.add("https://www.youtube.com/watch?v=v01")
    dialog = make_playlist()
    assert wait_until(lambda: dialog.state == "ready")
    dialog.range_edit.setText("1-2")
    dialog.add_button.click()
    assert len(ui_queue.items()) == 2
    assert dialog.added_count == 1 and dialog.known_count == 1


def test_playlist_error_state_and_retry(make_playlist) -> None:
    info = ErrorInfo("Network problem.", "Retry (auto-retry already ran)", "network")
    calls = []

    def probe(url):
        calls.append(1)
        if len(calls) == 1:
            raise ProbeError(info, "ERROR: Unable to download webpage")
        return PLAYLIST

    dialog = make_playlist(probe=probe)
    assert wait_until(lambda: dialog.state == "failed")
    assert dialog.status_label.text() == "Network problem."
    assert not dialog.retry_button.isHidden() and not dialog.add_button.isEnabled()
    assert "Unable to download" in dialog.details_text.toPlainText()
    dialog.retry_button.click()
    assert wait_until(lambda: dialog.state == "ready")
    assert dialog.list.count() == 6


def test_playlist_empty_is_a_failure(make_playlist) -> None:
    dialog = make_playlist(probe=lambda url: {"entries": []})
    assert wait_until(lambda: dialog.state == "failed")
    assert "No videos" in dialog.status_label.text()


def test_playlist_accessibility(make_playlist) -> None:
    dialog = make_playlist()
    assert wait_until(lambda: dialog.state == "ready")
    for w in (dialog.list, dialog.range_edit, dialog.select_all_button, dialog.select_none_button,
              dialog.quality_combo, dialog.add_button, dialog.cancel_button, dialog.count_label,
              dialog.status_label):
        assert w.accessibleName(), w


# -- MainWindow wiring ----------------------------------------------------
@pytest.fixture
def win(qapp, ui_queue):
    probes = []

    def probe(url):
        probes.append(url)
        return PLAYLIST if "list=" in url else INFO

    window = MainWindow(ui_queue, version_fn=lambda: "t", probe_fn=probe, thumbnail_fetcher=fake_fetcher)
    window.probes = probes
    window.dialogs = []

    def run(dialog):
        window.dialogs.append(dialog)
        assert wait_until(lambda: dialog.state in ("ready", "failed"))

    window._run_dialog = run
    yield window
    for dialog in window.dialogs:
        dialog.reject()
    window.bridge.close()
    window.deleteLater()


def test_plain_add_never_probes_or_opens_a_dialog(win, ui_queue) -> None:
    win.url_edit.setText("https://example.com/v/1")
    win.add_button.click()
    wait_until(lambda: False, 0.1)
    assert win.dialogs == [] and win.probes == []
    assert len(ui_queue.items()) == 1
    assert ui_queue._items[ui_queue.items()[0]["id"]].format_selector is None


def test_add_on_playlist_link_opens_playlist_dialog(win, ui_queue) -> None:
    win.url_edit.setText(PLAYLIST_URL)
    win.add_button.click()
    assert len(win.dialogs) == 1 and isinstance(win.dialogs[0], PlaylistDialog)
    assert win.probes == [PLAYLIST_URL]
    assert ui_queue.items() == []  # nothing queued blindly


def test_paste_of_playlist_link_also_opens_picker(win, ui_queue) -> None:
    win.add_text(f"https://example.com/v/1 {PLAYLIST_URL}")
    assert len(ui_queue.items()) == 1
    assert len(win.dialogs) == 1 and isinstance(win.dialogs[0], PlaylistDialog)


def test_options_button_opens_quality_dialog_and_download_updates_window(win, ui_queue) -> None:
    assert win.options_button.accessibleName() and win.options_button.text() == "Options..."
    win.url_edit.setText("https://example.com/v/9")
    win.options_button.click()
    dialog = win.dialogs[0]
    assert isinstance(dialog, QualityDialog) and win.probes == ["https://example.com/v/9"]
    assert ui_queue.items() == []
    dialog.download_button.click()
    assert len(ui_queue.items()) == 1
    assert win.model.rowCount() == 1
    assert win.url_edit.text() == ""
    assert win.statusBar().currentMessage() == "Added 1 link"


def test_options_on_playlist_link_and_bad_input(win) -> None:
    win.open_options()
    assert win.statusBar().currentMessage() == "Paste a video link first"
    win.url_edit.setText("two https://a.com/1 https://b.com/2")
    win.open_options()
    assert "one link" in win.statusBar().currentMessage()
    win.url_edit.setText(PLAYLIST_URL)
    win.open_options()
    assert isinstance(win.dialogs[0], PlaylistDialog)


def test_playlist_add_selected_updates_window(win, ui_queue) -> None:
    win.add_text(PLAYLIST_URL)
    dialog = win.dialogs[0]
    dialog.range_edit.setText("1-2")
    dialog.add_button.click()
    assert win.model.rowCount() == 2
    assert win.statusBar().currentMessage() == "Added 2 links"


def test_shortcuts_exist(win) -> None:
    keys = {sc.key().toString() for sc in win._add_shortcuts}
    assert {"Ctrl+Return", "Ctrl+Shift+Return"} <= keys
    assert win.options_button.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_shortcuts_trigger_add_and_options(win, ui_queue) -> None:
    quick = next(s for s in win._add_shortcuts if s.key().toString() == "Ctrl+Return")
    opts = next(s for s in win._add_shortcuts if s.key().toString() == "Ctrl+Shift+Return")
    win.url_edit.setText("https://example.com/v/1")
    quick.activated.emit()
    assert win.dialogs == [] and len(ui_queue.items()) == 1
    win.url_edit.setText("https://example.com/v/2")
    opts.activated.emit()
    assert isinstance(win.dialogs[0], QualityDialog)
