"""A link handed over from outside is queued by the main window on the GUI thread."""

from __future__ import annotations

import threading

import pytest
from PySide6.QtCore import QCoreApplication

from elisium_downloader.ui import ipc
from elisium_downloader.ui.main_window import MainWindow
from elisium_downloader.ui.playlist_dialog import PlaylistDialog

from test_ipc import client_call, pump_until, real_client
from test_ui_tray import FakeTray
from elisium_downloader.ui.tray import TrayController
from conftest import make_snapshot  # noqa: F401

PLAYLIST_URL = "https://www.youtube.com/playlist?list=PL123"
PLAYLIST = {"entries": [{"id": "a", "title": "A", "url": "https://example.com/v/a"}]}


@pytest.fixture
def env(qapp, ui_queue, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    class E:
        pass

    e = E()
    e.fake = FakeTray()
    e.dialogs = []
    e.threads = []

    def factory(window):
        e.tray = TrayController(window, tray=e.fake, notifier=lambda t, m: e.fake.showMessage(t, m),
                                folder_opener=lambda p: None, manage_quit_policy=False)
        return e.tray

    e.window = MainWindow(ui_queue, version_fn=lambda: "t", tray_factory=factory,
                          probe_fn=lambda url: PLAYLIST, settings_path=tmp_path / "s.json")
    e.window._run_dialog = e.dialogs.append  # never block
    original = e.window.receive_links

    def recording(urls):
        e.threads.append(threading.current_thread())
        return original(urls)

    e.server = ipc.acquire_server(recording)
    assert e.server is not None
    e.queue = ui_queue
    yield e
    e.server.close()
    for d in e.dialogs:
        d.reject()
    e.tray.shutdown()
    e.window.bridge.close()
    e.window.deleteLater()


def test_received_links_are_queued_via_add_text_path(env) -> None:
    reply = client_call(ipc.send_add, ["https://example.com/a", "https://example.com/b"])
    assert reply == {"ok": True, "added": 2, "known": 0, "ignored": 0}
    assert env.threads == [threading.main_thread()]
    assert len(env.queue.items()) == 2
    assert env.window.model.rowCount() == 2
    assert env.window.statusBar().currentMessage() == "Added 2 links"
    # default preset only: no custom selector, no output override
    for item in env.queue.items():
        assert env.queue._items[item["id"]].format_selector is None


def test_duplicate_counts_as_known(env) -> None:
    client_call(ipc.send_add, ["https://example.com/a"])
    reply = client_call(ipc.send_add, ["https://example.com/a"])
    assert reply == {"ok": True, "added": 0, "known": 1, "ignored": 0}
    assert len(env.queue.items()) == 1


def test_notification_when_enabled(env) -> None:
    client_call(ipc.send_add, ["https://example.com/a", "https://example.com/b"])
    assert env.fake.messages == [("Elisium", "Added 2 links")]
    client_call(ipc.send_add, ["https://example.com/c"])
    assert env.fake.messages[-1] == ("Elisium", "Added 1 link")


def test_no_notification_when_disabled_or_nothing_new(env) -> None:
    env.window.settings.notify_on_done = False
    client_call(ipc.send_add, ["https://example.com/a"])
    assert env.fake.messages == []
    env.window.settings.notify_on_done = True
    client_call(ipc.send_add, ["https://example.com/a"])  # already known
    assert env.fake.messages == []


def test_playlist_opens_picker_and_is_not_queued(env) -> None:
    reply = client_call(ipc.send_add, [PLAYLIST_URL, "https://example.com/v/1"])
    assert reply["ok"] is True and reply["added"] == 1 and reply["playlists"] == 1
    pump_until(lambda: len(env.dialogs) == 1)
    assert len(env.dialogs) == 1 and isinstance(env.dialogs[0], PlaylistDialog)
    assert len(env.queue.items()) == 1  # only the plain video; the playlist waits for the user


def test_window_is_never_raised_or_activated(env, monkeypatch) -> None:
    calls = []
    for name in ("raise_", "activateWindow", "showNormal", "show"):
        monkeypatch.setattr(MainWindow, name, lambda self, *a, _n=name: calls.append(_n))
    client_call(ipc.send_add, ["https://example.com/a"])
    assert calls == []


def test_real_client_process_reaches_the_window(env) -> None:
    assert real_client(["https://example.com/from-cli"])["added"] == 1
    assert env.window.statusBar().currentMessage() == "Added 1 link"
