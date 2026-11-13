"""Tray icon, tray menu, close-to-tray and desktop notifications (all with fakes)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from elisium_downloader.ui import settings as st
from elisium_downloader.ui.main_window import MainWindow
from elisium_downloader.ui.tray import STILL_RUNNING_TEXT, TrayController

from conftest import make_snapshot


class FakeTray(QObject):
    """Stands in for QSystemTrayIcon: records calls, shows nothing."""

    activated = Signal(object)
    messageClicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.visible = False
        self.tooltip = ""
        self.icon = None
        self.menu = None
        self.messages: list[tuple[str, str]] = []

    def setIcon(self, icon) -> None:
        self.icon = icon

    def setToolTip(self, text: str) -> None:
        self.tooltip = text

    def setContextMenu(self, menu) -> None:
        self.menu = menu

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False

    def showMessage(self, title, message, icon=None, msecs=0) -> None:
        self.messages.append((title, message))


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class Env:
    pass


@pytest.fixture
def env(qapp, ui_queue, tmp_path):
    e = Env()
    e.fake = FakeTray()
    e.clock = Clock()
    e.opened: list[Path] = []
    e.quits: list[bool] = []

    def factory(window):
        e.controller = TrayController(
            window,
            tray=e.fake,
            folder_opener=e.opened.append,
            clock=e.clock,
            quit_fn=lambda: e.quits.append(True),
        )
        return e.controller

    e.window = MainWindow(ui_queue, settings_path=tmp_path / "s.json",
                          version_fn=lambda: "t", tray_factory=factory)
    e.queue = ui_queue
    yield e
    e.controller.shutdown()  # restores the app's quit policy
    e.window.bridge.close()
    e.window.deleteLater()


def state_event(snapshot):
    return {"type": "state", "item": snapshot}


def test_default_window_has_no_tray_under_offscreen(qapp, ui_queue) -> None:
    win = MainWindow(ui_queue, version_fn=lambda: "t")
    try:
        assert win.tray is None  # tray_wanted() is False on the offscreen platform
    finally:
        win.bridge.close()


def test_tray_setup_menu_and_tooltip(env) -> None:
    c = env.controller
    assert env.fake.visible and env.fake.icon is not None and not env.fake.icon.isNull()
    assert [a.text() for a in c.menu.actions() if not a.isSeparator()] == [
        "Show window", "Pause all", "Resume all", "Open download folder", "Quit",
    ]
    assert env.fake.tooltip == "No downloads" == env.window.summary_label.text()
    env.window.add_text("https://a.com/1 https://b.com/2")
    assert env.fake.tooltip == env.window.summary_label.text() == "2 queued"


def test_left_click_toggles_window(env) -> None:
    w = env.window
    w.show()
    assert w.isVisible()
    env.fake.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    assert not w.isVisible()
    assert env.controller.toggle_action.text() == "Show window"
    env.fake.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    assert w.isVisible()
    env.fake.activated.emit(QSystemTrayIcon.ActivationReason.Context)  # right click: ignored
    assert w.isVisible()
    w.hide()


def test_menu_pause_all_resume_all(env) -> None:
    env.window.add_text("https://a.com/1 https://b.com/2")
    env.controller.pause_all_action.trigger()
    assert {i["state"] for i in env.queue.items()} == {"paused"}
    env.controller.resume_all_action.trigger()
    assert {i["state"] for i in env.queue.items()} == {"queued"}


def test_menu_open_folder_and_quit(env) -> None:
    env.controller.open_folder_action.trigger()
    assert env.opened == [env.queue.output_dir]
    env.controller.quit_action.trigger()
    assert env.quits == [True] and not env.fake.visible


def test_quit_with_running_download_asks_first(env, monkeypatch) -> None:
    item = env.queue.add("https://a.com/1")
    with env.queue._cond:
        env.queue._items[item["id"]].state = "downloading"
    asked = []
    monkeypatch.setattr(env.window, "_confirm_close", lambda: asked.append(1) or "keep")
    env.controller.quit_action.trigger()
    assert asked == [1] and env.quits == [] and env.fake.visible
    monkeypatch.setattr(env.window, "_confirm_close", lambda: "pause")
    env.controller.quit_action.trigger()
    assert env.quits == [True]
    assert env.queue.item(item["id"])["state"] == "paused"


def test_ctrl_q_really_quits_even_when_close_to_tray(env) -> None:
    env.window.settings = st.Settings(close_to_tray=True)
    env.window.quit_app()
    assert env.quits == [True]


def test_close_to_tray_hides_and_keeps_downloading(env, monkeypatch) -> None:
    env.window.settings = st.Settings(close_to_tray=True)
    item = env.queue.add("https://a.com/1")
    with env.queue._cond:
        env.queue._items[item["id"]].state = "downloading"
    monkeypatch.setattr(env.window, "_confirm_close", lambda: pytest.fail("must not ask"))
    env.window.show()
    assert env.window.close() is False
    assert not env.window.isVisible()
    assert env.queue.item(item["id"])["state"] == "downloading"
    assert env.fake.messages == [("Elisium", STILL_RUNNING_TEXT)]
    assert env.quits == []
    # Second time: no repeat of the hint.
    env.window.show()
    env.window.close()
    assert len(env.fake.messages) == 1


def test_close_without_close_to_tray_keeps_the_prompt(env, monkeypatch) -> None:
    env.window.settings = st.Settings(close_to_tray=False)
    item = env.queue.add("https://a.com/1")
    with env.queue._cond:
        env.queue._items[item["id"]].state = "downloading"
    asked = []
    monkeypatch.setattr(env.window, "_confirm_close", lambda: asked.append(1) or "keep")
    env.window.close()
    assert asked == [1] and env.fake.messages == []


def test_settings_toggle_takes_effect_immediately(env) -> None:
    page = env.window.settings_page
    page.tray_check.setChecked(True)
    assert env.window.settings.close_to_tray is True
    env.window.show()
    env.window.close()
    assert not env.window.isVisible()


def test_close_to_tray_without_a_tray_closes_normally(qapp, ui_queue) -> None:
    win = MainWindow(ui_queue, settings=st.Settings(close_to_tray=True),
                     version_fn=lambda: "t", tray_factory=lambda w: None)
    assert win.tray is None
    assert win.close() is True
    win.bridge.close()


# -- notifications ---------------------------------------------------------
def done(item_id, **over):
    return state_event(make_snapshot(item_id, "done", title=f"Clip {item_id}", **over))


def test_done_notification_when_window_not_focused(env) -> None:
    env.window._on_event(done(1))
    assert env.fake.messages == [("Download finished", "Clip 1")]


def test_failed_notification_uses_plain_error_message(env) -> None:
    error = {"code": "http_403", "message": "The site refused the download.", "fix": "x"}
    env.window._on_event(state_event(make_snapshot(1, "failed", title="Bad", error=error)))
    title, message = env.fake.messages[0]
    assert title == "Download failed"
    assert "Bad" in message and "The site refused the download." in message


def test_no_notification_when_focused_or_disabled(env, monkeypatch) -> None:
    monkeypatch.setattr(env.window, "isActiveWindow", lambda: True)
    env.window._on_event(done(1))
    assert env.fake.messages == []
    monkeypatch.undo()
    env.window.settings = st.Settings(notify_on_done=False)
    env.window._on_event(done(2))
    assert env.fake.messages == []


def test_same_state_event_twice_notifies_once_and_retry_notifies_again(env) -> None:
    env.window._on_event(done(1))
    env.clock.now += 5
    env.window._on_event(done(1))
    assert len(env.fake.messages) == 1
    env.window._on_event(state_event(make_snapshot(1, "queued")))
    env.clock.now += 5
    env.window._on_event(done(1))
    assert len(env.fake.messages) == 2


def test_notifications_are_batched_to_one_per_second(env) -> None:
    env.window._on_event(done(1))
    env.clock.now += 0.2
    env.window._on_event(done(2))
    env.window._on_event(done(3))
    assert len(env.fake.messages) == 1  # held back
    assert env.controller._timer.isActive()
    env.clock.now += 1.0
    env.controller.flush()  # what the timer does
    assert env.fake.messages[1] == ("Downloads finished", "2 downloads finished")
    assert len(env.fake.messages) == 2
    env.clock.now += 0.1
    error = {"code": "x", "message": "Network problem.", "fix": ""}
    env.window._on_event(state_event(make_snapshot(4, "failed", title="Z", error=error)))
    env.window._on_event(done(5))
    env.clock.now += 2
    env.controller.flush()
    assert env.fake.messages[2] == (
        "Downloads finished or failed", "1 download finished, 1 download failed"
    )


def test_never_two_notifications_within_a_second(env) -> None:
    for n in range(1, 8):
        env.clock.now += 0.1
        env.window._on_event(done(n))
    env.controller.flush()
    # Everything after the first message was merged into one more message.
    assert len(env.fake.messages) <= 2
    assert env.fake.messages[-1][1] == "6 downloads finished"


def test_clicking_the_notification_opens_the_files_folder(env, tmp_path) -> None:
    folder = tmp_path / "videos"
    folder.mkdir()
    env.window._on_event(done(1, file_path=str(folder / "a.mp4")))
    env.fake.messageClicked.emit()
    assert env.opened == [folder]


def test_click_with_no_file_path_opens_output_folder(env) -> None:
    env.window._on_event(done(1))
    env.fake.messageClicked.emit()
    assert env.opened == [env.queue.output_dir]


def test_injected_notifier_replaces_the_balloon(qapp, ui_queue) -> None:
    got = []
    fake = FakeTray()
    win = MainWindow(
        ui_queue, version_fn=lambda: "t",
        tray_factory=lambda w: TrayController(
            w, tray=fake, notifier=lambda t, m: got.append((t, m)),
            quit_fn=lambda: None, manage_quit_policy=False),
    )
    win._on_event(done(1))
    assert got == [("Download finished", "Clip 1")] and fake.messages == []
    win.bridge.close()


def test_tray_restores_quit_policy_on_shutdown(qapp, ui_queue) -> None:
    before = QApplication.quitOnLastWindowClosed()
    win = MainWindow(ui_queue, version_fn=lambda: "t",
                     tray_factory=lambda w: TrayController(w, tray=FakeTray(),
                                                           quit_fn=lambda: None))
    assert QApplication.quitOnLastWindowClosed() is False
    win.tray.shutdown()
    assert QApplication.quitOnLastWindowClosed() is before
    win.bridge.close()
