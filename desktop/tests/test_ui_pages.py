from __future__ import annotations

import json
import time

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMessageBox

from elisium_downloader.ui import history_page as hp
from elisium_downloader.ui import settings as st
from elisium_downloader.ui.history_page import HistoryPage
from elisium_downloader.ui.main_window import MainWindow
from elisium_downloader.ui.settings_page import SettingsPage


def pump(ms: int = 0) -> None:
    end = time.monotonic() + ms / 1000
    QCoreApplication.processEvents()
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def wait_until(pred, timeout: float = 3.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        pump()
        if pred():
            return True
        time.sleep(0.005)
    return pred()


# -- sidebar ---------------------------------------------------------------
@pytest.fixture
def window(qapp, ui_queue, tmp_path):
    win = MainWindow(ui_queue, settings_path=tmp_path / "s.json", version_fn=lambda: "2099.1.1")
    yield win
    win.bridge.close()
    win.deleteLater()


def test_sidebar_switches_pages(window) -> None:
    assert window.sidebar.accessibleName() == "Sections"
    assert [window.sidebar.item(i).text() for i in range(3)] == ["Downloads", "History", "Settings"]
    assert window.stack.currentIndex() == 0
    window.sidebar.setCurrentRow(1)
    assert window.stack.currentWidget() is window.history_page
    window.sidebar.setCurrentRow(2)
    assert window.stack.currentWidget() is window.settings_page
    window.show_section(0)
    assert window.sidebar.currentRow() == 0
    assert window.table.parentWidget() is window.stack.currentWidget()


def test_section_shortcuts_exist_and_work(window) -> None:
    assert {sc.key().toString() for sc in window._section_shortcuts} == {"Ctrl+1", "Ctrl+2", "Ctrl+3"}
    window._section_shortcuts[2].activated.emit()
    assert window.stack.currentIndex() == 2
    window._section_shortcuts[1].activated.emit()
    assert window.stack.currentIndex() == 1


# -- history page ----------------------------------------------------------
@pytest.fixture
def hist(qapp, ui_queue, tmp_path):
    h = ui_queue.history
    real = tmp_path / "real.mp4"
    real.write_text("data")
    a = h.add("https://example.com/watch/1", title="Alpha clip")
    h.update_state(a, "done", file_path=str(real))
    b = h.add("https://example.com/watch/2", title="Beta clip")
    h.update_state(b, "done", file_path=str(tmp_path / "gone.mp4"))
    c = h.add("https://other.org/3", title="Gamma")
    h.update_state(c, "failed")
    page = HistoryPage(ui_queue)
    page.ids = (a, b, c)
    page.real = real
    yield page
    page.deleteLater()


def texts(page, column: int) -> list[str]:
    m = page.model
    return [m.data(m.index(r, column)) for r in range(m.rowCount())]


def select_title(page, title: str) -> None:
    row = texts(page, 0).index(title)
    page.table.selectRow(row)


def test_history_lists_rows_and_names(hist) -> None:
    assert hist.search_edit.accessibleName() == "Search history"
    assert hist.table.accessibleName() == "History"
    assert [hist.model.headerData(i, Qt.Orientation.Horizontal) for i in range(5)] == [
        "Title", "Site", "State", "Date", "File"]
    assert sorted(texts(hist, 0)) == ["Alpha clip", "Beta clip", "Gamma"]
    assert "example.com" in texts(hist, 1)


def test_history_search_is_debounced(hist) -> None:
    hist.search_edit.setText("alpha")
    assert hist._timer.interval() == 200
    assert hist.model.rowCount() == 3  # not refreshed yet
    assert wait_until(lambda: hist.model.rowCount() == 1)
    assert texts(hist, 0) == ["Alpha clip"]
    hist.search_edit.clear()
    assert wait_until(lambda: hist.model.rowCount() == 3)


def test_history_state_words_and_file_missing(hist) -> None:
    by_title = dict(zip(texts(hist, 0), texts(hist, 2)))
    assert "Done" in by_title["Alpha clip"]
    assert by_title["Beta clip"] == hp.FILE_MISSING_TEXT and "File missing" in by_title["Beta clip"]
    assert "Failed" in by_title["Gamma"]


def test_history_buttons_follow_selection(hist) -> None:
    assert not hist.delete_button.isEnabled()
    select_title(hist, "Alpha clip")
    assert hist.open_file_button.isEnabled() and hist.delete_button.isEnabled()
    select_title(hist, "Beta clip")
    assert not hist.open_file_button.isEnabled()  # file missing
    assert hist.again_button.isEnabled()


def test_open_file_and_folder(hist, monkeypatch) -> None:
    opened = []
    monkeypatch.setattr(hp.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()))
    select_title(hist, "Alpha clip")
    hist.open_file()
    hist.open_folder()
    assert opened == [str(hist.real), str(hist.real.parent)]


def test_download_again_calls_queue(hist, ui_queue, monkeypatch) -> None:
    added = []
    monkeypatch.setattr(ui_queue, "add", lambda url: added.append(url) or {})
    select_title(hist, "Beta clip")
    hist.again_button.click()
    assert added == ["https://example.com/watch/2"]


def test_copy_link(hist) -> None:
    select_title(hist, "Gamma")
    hist.copy_button.click()
    assert QGuiApplication.clipboard().text() == "https://other.org/3"


def test_delete_entry_confirms_and_keeps_file(hist, ui_queue, monkeypatch) -> None:
    select_title(hist, "Alpha clip")
    monkeypatch.setattr(hist, "_confirm_delete", lambda: False)
    hist.delete_button.click()
    assert ui_queue.history.get(hist.ids[0]) is not None
    monkeypatch.setattr(hist, "_confirm_delete", lambda: True)
    hist.delete_button.click()
    assert ui_queue.history.get(hist.ids[0]) is None
    assert hist.real.exists()  # file untouched
    assert "Alpha clip" not in texts(hist, 0)


def test_confirm_delete_dialog_text(hist, monkeypatch) -> None:
    seen = {}

    def fake_exec(self):
        seen["text"] = self.text()
        seen["buttons"] = [b.text() for b in self.buttons()]

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    assert hist._confirm_delete() is False
    assert "file is kept" in seen["text"] and seen["buttons"] == ["Delete entry", "Cancel"]


def test_history_refreshes_on_terminal_event(hist, ui_queue) -> None:
    new = ui_queue.history.add("https://example.com/watch/9", title="Late")
    assert "Late" not in texts(hist, 0)
    hist._on_event({"type": "state", "item": {"state": "downloading"}})
    assert "Late" not in texts(hist, 0)
    hist._on_event({"type": "state", "item": {"state": "done"}})
    assert "Late" in texts(hist, 0)
    assert new


# -- settings page ---------------------------------------------------------
@pytest.fixture
def spage(qapp, ui_queue, tmp_path):
    path = tmp_path / "cfg" / "settings.json"
    page = SettingsPage(st.Settings(), ui_queue, path, version_fn=lambda: "2025.01.02")
    page.path_ = path
    yield page
    page.deleteLater()


def test_settings_page_accessibility(spage) -> None:
    for w in (spage.concurrency_spin, spage.limit_check, spage.limit_spin, spage.limit_unit,
              spage.preset_combo, spage.notify_check, spage.tray_check, spage.folder_label,
              spage.open_folder_button, spage.version_label, spage.open_data_button):
        assert w.accessibleName() and w.accessibleDescription()
    assert spage.concurrency_spin.minimum() == 1 and spage.concurrency_spin.maximum() == 5
    assert spage.preset_combo.count() == 8
    assert [spage.limit_unit.itemText(i) for i in range(2)] == ["KB/s", "MB/s"]
    from PySide6.QtWidgets import QLabel
    buddies = {lab.text(): lab.buddy() for lab in spage.findChildren(QLabel) if lab.buddy()}
    assert buddies["Parallel downloads"] is spage.concurrency_spin
    assert buddies["Default quality"] is spage.preset_combo


def test_settings_save_and_apply_live(spage, ui_queue) -> None:
    spage.concurrency_spin.setValue(4)
    assert ui_queue.concurrency == 4
    assert json.loads(spage.path_.read_text())["concurrency"] == 4
    spage.limit_check.setChecked(True)
    spage.limit_spin.setValue(3)
    assert ui_queue._limit_rate == "3M"
    spage.limit_unit.setCurrentIndex(0)
    assert ui_queue._limit_rate == "3K"
    spage.preset_combo.setCurrentIndex(spage.preset_combo.findData("audio-mp3"))
    assert ui_queue._format_selector == "bestaudio/best"
    assert ui_queue._extra_args == ("-x", "--audio-format", "mp3")
    spage.limit_check.setChecked(False)
    assert ui_queue._limit_rate is None
    spage.notify_check.setChecked(False)
    spage.tray_check.setChecked(True)
    saved = st.load(spage.path_)
    assert saved == st.Settings(4, None, "audio-mp3", False, True)


def test_settings_page_loads_existing_values(qapp, ui_queue, tmp_path) -> None:
    page = SettingsPage(st.Settings(concurrency=5, speed_limit="1.5G", preset_id="720p",
                                    close_to_tray=True), ui_queue, None, lambda: None)
    assert page.concurrency_spin.value() == 5
    assert page.limit_check.isChecked() and page.limit_spin.value() == 1536
    assert page.preset_combo.currentData() == "720p"
    assert page.tray_check.isChecked()
    page.concurrency_spin.setValue(3)  # no path: must not raise or write
    assert ui_queue.concurrency == 3


def test_ytdlp_version_label_with_fake(spage, qapp, ui_queue) -> None:
    assert wait_until(lambda: spage.version_label.text() == "2025.01.02")
    missing = SettingsPage(st.Settings(), ui_queue, None, lambda: None)
    assert wait_until(lambda: missing.version_label.text() == "yt-dlp not found")

    def boom():
        raise RuntimeError("x")

    broken = SettingsPage(st.Settings(), ui_queue, None, boom)
    assert wait_until(lambda: broken.version_label.text() == "yt-dlp not found")


def test_version_label_starts_as_checking(qapp, ui_queue) -> None:
    import threading
    gate = threading.Event()
    page = SettingsPage(st.Settings(), ui_queue, None, lambda: gate.wait(2) and "1.0")
    assert page.version_label.text() == "checking..."
    gate.set()
    assert wait_until(lambda: page.version_label.text() == "1.0")


def test_open_folders(spage, ui_queue, monkeypatch) -> None:
    from elisium_downloader.ui import settings_page as sp
    opened = []
    monkeypatch.setattr(sp.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()))
    spage.open_folder_button.click()
    spage.open_data_button.click()
    assert opened == [str(ui_queue.output_dir), str(ui_queue.archive.path.parent)]


def test_create_app_loads_and_applies_settings(qapp, tmp_path) -> None:
    from elisium_downloader.ui.app import create_app

    cfg = tmp_path / "cfg" / "settings.json"
    st.save(st.Settings(concurrency=3, speed_limit="1M", preset_id="audio-opus"), cfg)
    app, win, queue = create_app(
        [], data_path=tmp_path / "d", output_path=tmp_path / "o", temp_path=tmp_path / "t",
        settings_path=cfg, version_fn=lambda: "x",
    )
    try:
        assert queue.concurrency == 3 and queue._limit_rate == "1M"
        assert queue._extra_args == ("-x", "--audio-format", "opus")
        assert win.settings.preset_id == "audio-opus"
        assert win.settings_page.concurrency_spin.value() == 3
    finally:
        win.bridge.close()
        queue.stop(1.0)
        queue.history.close()
