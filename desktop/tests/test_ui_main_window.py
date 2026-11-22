from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QCoreApplication, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMessageBox

from elisium_downloader.ui import main_window as mw
from elisium_downloader.ui.app import create_app
from elisium_downloader.ui.main_window import MainWindow, extract_urls

from conftest import make_snapshot


@pytest.fixture
def window(qapp, ui_queue):
    win = MainWindow(ui_queue, version_fn=lambda: "test")
    yield win
    win.bridge.close()
    win.deleteLater()


def pump() -> None:
    QCoreApplication.processEvents()


def test_title_and_accessible_names(window) -> None:
    assert window.windowTitle() == "Elisium"
    assert window.url_edit.placeholderText() == "Paste a link from YouTube, Instagram, TikTok…"
    for widget in (window.url_edit, window.paste_button, window.add_button, window.table, window.toolbar):
        assert widget.accessibleName()
    for action in (window.pause_action, window.resume_action, window.retry_action,
                   window.cancel_action, window.open_action):
        button = window.toolbar.widgetForAction(action)
        assert button.accessibleName() == action.text()
        assert button.accessibleDescription()
        assert not action.icon().isNull()


def test_extract_urls() -> None:
    urls, ignored = extract_urls("https://a.com/1\n\nnot a link http://b.com/2 ftp://x")
    assert urls == ["https://a.com/1", "http://b.com/2"]
    assert ignored == 4  # "not", "a", "link", "ftp://x"


def test_multi_url_paste_counts(window, ui_queue) -> None:
    window.add_text("https://a.com/1\nhttps://b.com/2 https://c.com/3\ngarbage")
    pump()
    assert window.statusBar().currentMessage() == "Added 3 links, 1 ignored"
    assert window.model.rowCount() == 3
    assert len(ui_queue.items()) == 3
    assert "3 queued" in window.summary_label.text()


def test_paste_button_reads_clipboard(window) -> None:
    QGuiApplication.clipboard().setText("https://a.com/1")
    window.paste_button.click()
    pump()
    assert window.statusBar().currentMessage() == "Added 1 link"
    assert window.model.rowCount() == 1


def test_add_button_and_enter_clear_box(window) -> None:
    window.url_edit.setText("https://a.com/1")
    window.add_button.click()
    assert window.url_edit.text() == ""
    assert window.model.rowCount() == 1


def test_duplicate_message(window) -> None:
    window.add_text("https://a.com/1")
    window.add_text("https://a.com/1")
    pump()
    assert window.statusBar().currentMessage() == "That video is already in the list"
    assert window.model.rowCount() == 1


def select(window, row: int) -> None:
    window.table.selectRow(row)


@pytest.mark.parametrize(
    "state,enabled",
    [
        ("queued", {"pause", "cancel"}),
        ("probing", {"pause", "cancel"}),
        ("downloading", {"pause", "cancel"}),
        ("merging", {"pause", "cancel"}),
        ("converting", {"pause", "cancel"}),
        ("paused", {"resume", "cancel"}),
        ("failed", {"retry"}),
        ("cancelled", {"retry"}),
        ("done", {"open"}),
        ("skipped", set()),
    ],
)
def test_toolbar_enablement(window, state, enabled) -> None:
    window.model.load([make_snapshot(1, state)])
    select(window, 0)
    actual = {
        name
        for name, action in (
            ("pause", window.pause_action), ("resume", window.resume_action),
            ("retry", window.retry_action), ("cancel", window.cancel_action),
            ("open", window.open_action),
        )
        if action.isEnabled()
    }
    assert actual == enabled


def test_no_selection_disables_everything(window) -> None:
    window.model.load([make_snapshot(1, "queued")])
    window.table.clearSelection()
    window._update_actions()
    for action in (window.pause_action, window.resume_action, window.retry_action,
                   window.cancel_action, window.open_action, window.copy_action):
        assert not action.isEnabled()


def test_pause_resume_through_ui_and_bridge(window, ui_queue) -> None:
    window.add_text("https://a.com/1")
    select(window, 0)
    window.pause_action.trigger()
    pump()
    assert window.model.snapshot_at(0)["state"] == "paused"
    assert window.resume_action.isEnabled() and not window.pause_action.isEnabled()
    window.toggle_pause_resume()  # Space: paused -> queued
    pump()
    assert window.model.snapshot_at(0)["state"] == "queued"
    window.toggle_pause_resume()
    pump()
    assert window.model.snapshot_at(0)["state"] == "paused"
    window.cancel_action.trigger()
    pump()
    assert window.model.snapshot_at(0)["state"] == "cancelled"
    assert window.retry_action.isEnabled()
    window.retry_action.trigger()
    pump()
    assert window.model.snapshot_at(0)["state"] == "queued"


def test_open_folder_uses_file_parent_or_output_dir(window, ui_queue, tmp_path, monkeypatch) -> None:
    opened: list[QUrl] = []
    monkeypatch.setattr(mw.QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    folder = tmp_path / "videos"
    folder.mkdir()
    window.model.load([make_snapshot(1, "done", file_path=str(folder / "a.mp4"))])
    select(window, 0)
    window.open_action.trigger()
    assert opened[-1].toLocalFile() == str(folder)
    window.model.load([make_snapshot(1, "done", file_path=str(tmp_path / "gone" / "a.mp4"))])
    select(window, 0)
    window.open_action.trigger()
    assert opened[-1].toLocalFile() == str(ui_queue.output_dir)


def test_copy_link(window) -> None:
    window.add_text("https://a.com/1")
    select(window, 0)
    window.copy_action.trigger()
    assert QGuiApplication.clipboard().text() == "https://a.com/1"


def test_summary_text(window) -> None:
    states = ["downloading", "downloading", "queued", "done", "done", "done", "done", "done"]
    window.model.load([make_snapshot(n + 1, s) for n, s in enumerate(states)])
    window._refresh_ui()
    assert window.summary_label.text() == "2 downloading, 1 queued, 5 done"


def test_close_without_active_downloads_accepts(window, monkeypatch) -> None:
    monkeypatch.setattr(window, "_confirm_close", lambda: pytest.fail("should not ask"))
    assert window.close() is True


@pytest.mark.parametrize("choice,closes", [("pause", True), ("keep", False), ("cancel", False)])
def test_close_with_active_downloads_prompts(window, ui_queue, monkeypatch, choice, closes) -> None:
    item = ui_queue.add("https://a.com/1")
    # Force an active state without running the engine.
    with ui_queue._cond:
        ui_queue._items[item["id"]].state = "downloading"
    asked: list[bool] = []
    monkeypatch.setattr(window, "_confirm_close", lambda: asked.append(True) or choice)
    assert window.close() is closes
    assert asked == [True]
    state = ui_queue.item(item["id"])["state"]
    assert state == ("paused" if choice == "pause" else "downloading")


def test_confirm_dialog_buttons(window, monkeypatch) -> None:
    captured: dict = {}

    def fake_exec(self):
        captured["text"] = self.text()
        captured["buttons"] = [b.text() for b in self.buttons()]
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    assert window._confirm_close() == "cancel"  # no button clicked
    assert captured["text"] == "Downloads are running. Pause them and quit?"
    assert captured["buttons"] == ["Pause and quit", "Keep downloading", "Cancel"]


def test_tab_order_and_shortcuts(window) -> None:
    assert window.focusPolicy() is not None
    assert window.url_edit.focusPolicy().name in ("StrongFocus", "WheelFocus")
    keys = {sc.key().toString() for sc in window._shortcuts}
    assert keys == {"Ctrl+V", "Ctrl+L", "Space", "Ctrl+Q", "F1"}
    window.focus_url_bar()  # must not raise offscreen


def test_create_app_with_injected_queue(qapp, ui_queue) -> None:
    app, win, queue = create_app([], queue=ui_queue, version_fn=lambda: "test")
    assert queue is ui_queue and win.queue is ui_queue
    assert app is qapp
    win.bridge.close()


def test_create_app_builds_in_injected_dirs(qapp, tmp_path) -> None:
    app, win, queue = create_app(
        [],
        data_path=tmp_path / "d",
        output_path=tmp_path / "o",
        temp_path=tmp_path / "t",
        settings_path=tmp_path / "cfg" / "settings.json",
        version_fn=lambda: "test",
    )
    try:
        assert (tmp_path / "d" / "history.sqlite").exists()
        assert queue.output_dir == tmp_path / "o"
    finally:
        win.bridge.close()
        queue.stop(1.0)
        queue.history.close()


def test_grab_screenshot(window, tmp_path) -> None:
    window.model.load(
        [
            make_snapshot(1, "queued", title="Queued clip"),
            make_snapshot(2, "downloading", title="Big Buck Bunny",
                          progress={"percent": 42.0, "speed": 4404019.0, "eta": 80,
                                    "total_bytes": 52428800}),
            make_snapshot(3, "done", title="Finished clip", progress={"total_bytes": 1048576}),
            make_snapshot(4, "failed", title="Broken clip",
                          error={"code": "http_403", "message": "The site refused the download.",
                                 "fix": "Update yt-dlp, or import cookies"}),
        ]
    )
    window._refresh_ui()
    window.resize(900, 420)
    pixmap = window.grab()
    out = tmp_path / "window.png"
    assert pixmap.save(str(out))
    assert out.stat().st_size > 1000


def test_default_probe_goes_through_the_queues_public_probe(window, ui_queue) -> None:
    assert window._default_probe("https://a.com/1") == {
        "id": "x", "title": "Fake title", "extractor_key": "Fake"}
    assert ui_queue.ytdlp == "yt-dlp"


def test_the_table_keeps_one_visible_column(window) -> None:
    # the table keeps one visible column (the row); the rest stay in the model
    assert not window.table.isColumnHidden(0)
    assert window.table.isColumnHidden(1)


# -- card action buttons and enter animation --------------------------------
from PySide6.QtWidgets import QApplication  # noqa: E402

from elisium_downloader.ui import theme  # noqa: E402
from elisium_downloader.ui.main_window import card_action_kinds  # noqa: E402
from elisium_downloader.ui.widgets import enter_animation  # noqa: E402


@pytest.mark.parametrize("state,kinds", [
    ("queued", ["pause", "cancel"]),
    ("probing", ["pause", "cancel"]),
    ("downloading", ["pause", "cancel"]),
    ("merging", ["pause", "cancel"]),
    ("paused", ["resume", "cancel"]),
    ("failed", ["retry"]),
    ("cancelled", ["retry"]),
    ("done", ["launch", "open"]),
    ("skipped", []),
])
def test_card_action_kinds_per_state(state, kinds, window) -> None:
    assert card_action_kinds(state) == kinds
    window.model.load([make_snapshot(1, state, title="T")])
    window.table.selectRow(0)
    pump()
    assert window.card_actions.visible_kinds() == kinds
    # they agree with the toolbar's enabled state ("launch" opens the file and is card-only)
    enabled = [k for k, a in (("pause", window.pause_action), ("resume", window.resume_action),
                              ("retry", window.retry_action), ("cancel", window.cancel_action),
                              ("open", window.open_action)) if a.isEnabled()]
    assert [k for k in window.card_actions.visible_kinds() if k != "launch"] == enabled


def test_card_buttons_have_accessible_names_with_the_title(window) -> None:
    window.model.load([make_snapshot(1, "downloading", title="Big Buck Bunny")])
    window.table.selectRow(0)
    pump()
    buttons = window.card_actions.buttons
    assert buttons["pause"].accessibleName() == "Pause Big Buck Bunny"
    assert buttons["cancel"].accessibleName() == "Cancel Big Buck Bunny"
    assert buttons["pause"].focusPolicy() & Qt.FocusPolicy.TabFocus
    assert not buttons["pause"].icon().isNull()
    assert buttons["pause"].accessibleDescription()


def test_card_button_runs_the_window_action_on_its_own_card(window, ui_queue) -> None:
    window.resize(900, 700)
    window.show()
    window.add_text("https://a.com/1 https://b.com/2")
    pump()
    window.table.selectRow(0)
    pump()
    calls = []
    window.queue.cancel = lambda item_id: calls.append(item_id)  # type: ignore[method-assign]
    window.card_actions._hover_row = 1  # pointer over the second card
    window.card_actions.refresh()
    assert window.card_actions.card_row() == 1
    window.card_actions.buttons["cancel"].click()
    assert calls == [window.model.item_id_at(1)]
    assert window.table.selectionModel().selectedRows()[0].row() == 1


def test_card_buttons_hidden_without_a_card(window) -> None:
    window.model.load([])
    pump()
    assert window.card_actions.visible_kinds() == []
    assert window.delegate.actions_row_id is None


def test_card_enter_animation_runs_once_for_new_cards_only(window, monkeypatch) -> None:
    monkeypatch.setenv("ELISIUM_REDUCE_MOTION", "0")
    anim = enter_animation()
    anim._starts.clear()
    window.model.load([make_snapshot(1, "queued", title="Old")])  # a reload: no animation
    assert not anim.active
    window.model.upsert(make_snapshot(2, "queued", title="New"))
    assert anim.active and anim.state() == anim.State.Running
    assert 0.0 <= anim.progress(2) < 1.0 and anim.progress(1) == 1.0
    anim._starts[2] -= 1.0  # 220ms are long gone
    assert anim.progress(2) == 1.0 and not anim.active
    anim.stop()


def test_card_enter_animation_is_off_with_reduced_motion(window, monkeypatch) -> None:
    monkeypatch.setenv("ELISIUM_REDUCE_MOTION", "1")
    anim = enter_animation()
    anim._starts.clear()
    window.model.upsert(make_snapshot(3, "queued", title="New"))
    assert not anim.active and anim.progress(3) == 1.0


def test_card_enter_animation_off_with_the_settings_switch(window, monkeypatch) -> None:
    monkeypatch.delenv("ELISIUM_REDUCE_MOTION", raising=False)
    theme.set_reduce_motion(True)
    try:
        anim = enter_animation()
        anim._starts.clear()
        window.model.upsert(make_snapshot(4, "queued", title="New"))
        assert not anim.active
    finally:
        theme.set_reduce_motion(False)


def test_toolbar_and_shortcuts_still_work_with_card_buttons(window) -> None:
    window.model.load([make_snapshot(1, "paused", title="T")])
    window.table.selectRow(0)
    pump()
    assert window.resume_action.isEnabled() and not window.pause_action.isEnabled()


def test_sign_in_codes_cover_expired_session_and_401() -> None:
    # Brief 9A: these two failures are fixed in Settings > Accounts too.
    assert mw.SIGN_IN_CODES == frozenset(
        {"sign_in_required", "login_required", "session_expired", "http_401"}
    )
