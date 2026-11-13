from __future__ import annotations

import threading

from PySide6.QtCore import QCoreApplication

from elisium_downloader.ui.bridge import QueueBridge


def test_events_arrive_on_gui_thread(qapp, ui_queue) -> None:
    bridge = QueueBridge(ui_queue)
    received: list[tuple[dict, threading.Thread]] = []
    bridge.event.connect(lambda ev: received.append((ev, threading.current_thread())))

    worker = threading.Thread(target=lambda: ui_queue.add("https://example.com/a"))
    worker.start()
    worker.join()
    # Queued: nothing is delivered until the GUI thread runs its event loop.
    assert received == []
    QCoreApplication.processEvents()
    assert len(received) == 1
    event, thread = received[0]
    assert thread is threading.main_thread()
    assert event["type"] == "added"
    assert event["item"]["url"] == "https://example.com/a"
    assert event["item"]["error"] is None
    assert event["item"]["progress"]["percent"] is None
    bridge.close()


def test_close_stops_listening(qapp, ui_queue) -> None:
    bridge = QueueBridge(ui_queue)
    got: list[dict] = []
    bridge.event.connect(got.append)
    bridge.close()
    ui_queue.add("https://example.com/b")
    QCoreApplication.processEvents()
    assert got == []
