"""Link parsing, the socket protocol and single-instance behaviour (no network)."""

from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket

from elisium_downloader.ui import ipc


# -- parsing --------------------------------------------------------------
def test_valid_link_accepts_only_http_and_https() -> None:
    assert ipc.valid_link("https://example.com/a")
    assert ipc.valid_link("HTTP://example.com/a?x=1#y")
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "ftp://example.com/a",
                "data:text/html,hi", "example.com/a", "https://", "https:///x", "",
                "https://exa mple.com", "https://example.com/\nx", 5, None):
        assert not ipc.valid_link(bad), bad


def test_valid_link_length_limit() -> None:
    ok = "https://example.com/" + "a" * (ipc.MAX_URL_LENGTH - len("https://example.com/"))
    assert len(ok) == 2048 and ipc.valid_link(ok)
    assert not ipc.valid_link(ok + "a")


def test_split_links_counts_ignored() -> None:
    good, ignored = ipc.split_links("https://a.com/1\n file:///x  https://b.com/2\tjavascript:1")
    assert good == ["https://a.com/1", "https://b.com/2"] and ignored == 2


def test_uri_single_percent_encoded() -> None:
    link = "https://example.com/watch?v=1&t=5"
    good, ignored = ipc.links_from_elisium_uri(f"elisium://add?url={quote(link, safe='')}")
    assert good == [link] and ignored == 0


def test_uri_repeated_url_and_urls_parameter() -> None:
    uri = ("elisium://add?url=https%3A%2F%2Fa.com%2F1&url=https%3A%2F%2Fb.com%2F2"
           "&urls=" + quote("https://c.com/3\nhttps://d.com/4 https://e.com/5", safe=""))
    good, ignored = ipc.links_from_elisium_uri(uri)
    assert good == ["https://a.com/1", "https://b.com/2", "https://c.com/3",
                    "https://d.com/4", "https://e.com/5"] and ignored == 0


def test_uri_rejects_non_http_schemes() -> None:
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "ftp://x.com/a"):
        good, ignored = ipc.links_from_elisium_uri(f"elisium://add?url={quote(bad, safe='')}")
        assert good == [] and ignored == 1
    good, ignored = ipc.links_from_elisium_uri(
        "elisium://add?urls=" + quote("https://ok.com/1 file:///x", safe=""))
    assert good == ["https://ok.com/1"] and ignored == 1


def test_uri_overlong_link_is_ignored() -> None:
    long_link = "https://example.com/" + "a" * 2100
    good, ignored = ipc.links_from_elisium_uri(f"elisium://add?url={quote(long_link, safe='')}")
    assert good == [] and ignored == 1


def test_uri_unknown_action_and_empty() -> None:
    link = quote("https://a.com/1", safe="")
    assert ipc.links_from_elisium_uri(f"elisium://settings?url={link}") == ([], 0)
    assert ipc.links_from_elisium_uri(f"elisium://remove?url={link}") == ([], 0)
    assert ipc.links_from_elisium_uri("elisium://add") == ([], 0)
    assert ipc.links_from_elisium_uri("elisium://add?url=") == ([], 0)
    assert ipc.links_from_elisium_uri("https://add?url=" + link) == ([], 0)
    assert ipc.links_from_elisium_uri("elisium://[bad") == ([], 0)


def test_uri_ignores_option_parameters() -> None:
    uri = ("elisium://add?url=https%3A%2F%2Fa.com%2F1&format=bestaudio&preset=audio-mp3"
           "&output=%2Ftmp%2Fevil&args=--exec%20rm&cookies=x&settings=1&concurrency=9")
    good, ignored = ipc.links_from_elisium_uri(uri)
    assert good == ["https://a.com/1"] and ignored == 0


# -- protocol (no socket) -------------------------------------------------
def make_handler(calls):
    def handler(urls):
        calls.append(list(urls))
        return {"added": len(urls), "known": 0, "ignored": 0}

    return handler


def msg(**over) -> bytes:
    data = {"v": 1, "action": "add", "urls": ["https://a.com/1"]}
    data.update(over)
    return json.dumps(data).encode()


def test_handle_message_ok_counts() -> None:
    calls: list = []
    reply = ipc.handle_message(msg(urls=["https://a.com/1", "file:///x", "https://b.com/2"]),
                               make_handler(calls))
    assert reply == {"ok": True, "added": 2, "known": 0, "ignored": 1}
    assert calls == [["https://a.com/1", "https://b.com/2"]]


def test_handle_message_rejects_bad_input() -> None:
    calls: list = []
    h = make_handler(calls)
    for raw in (b"", b"not json", b"[1]", b'"x"', b"\xff\xfe", msg(v=2), msg(v="1"), msg(v=True),
                msg(action="remove"), msg(action="settings"), msg(urls="https://a.com"),
                msg(urls=None)):
        reply = ipc.handle_message(raw, h)
        assert reply["ok"] is False and "error" in reply, raw
    assert calls == []


def test_handle_message_limits() -> None:
    calls: list = []
    h = make_handler(calls)
    fifty = [f"https://a.com/{i}" for i in range(50)]
    assert ipc.handle_message(msg(urls=fifty), h)["added"] == 50
    too_many = ipc.handle_message(msg(urls=fifty + ["https://a.com/x"]), h)
    assert too_many == {"ok": False, "error": "too many urls"}
    huge = ipc.handle_message(b"x" * (ipc.MAX_MESSAGE_BYTES + 1), h)
    assert huge["ok"] is False
    overlong = "https://a.com/" + "a" * 2100
    reply = ipc.handle_message(msg(urls=[overlong]), h)
    assert reply == {"ok": True, "added": 0, "known": 0, "ignored": 1}
    assert len(calls) == 1  # only the 50-link message reached the handler


def test_message_cannot_carry_options() -> None:
    calls: list = []
    ipc.handle_message(msg(preset="audio-mp3", format="x", output="/tmp/evil",
                           args=["--exec", "rm"], cookies="c", settings={"a": 1}),
                       make_handler(calls))
    assert calls == [["https://a.com/1"]]  # the handler only ever receives links


def test_handler_failure_is_contained() -> None:
    def boom(urls):
        raise RuntimeError("x")

    assert ipc.handle_message(msg(), boom) == {"ok": False, "error": "internal error"}


# -- socket location ------------------------------------------------------
def test_socket_path_uses_runtime_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert ipc.socket_path() == tmp_path / "elisium.sock"


def test_socket_path_fallback_is_private_per_uid(tmp_path, monkeypatch) -> None:
    import tempfile

    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    path = ipc.socket_path()
    assert path.parent == tmp_path / f"elisium-{os.getuid()}"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    path.parent.chmod(0o777)  # too open: tightened again
    ipc.socket_path()
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_socket_path_fallback_refuses_symlink(tmp_path, monkeypatch) -> None:
    import tempfile

    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    target = tmp_path / "elsewhere"
    target.mkdir()
    (tmp_path / f"elisium-{os.getuid()}").symlink_to(target)
    with pytest.raises(OSError):
        ipc.socket_path()


# -- real socket round trips ---------------------------------------------
def pump_until(predicate, timeout=5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


def _stdlib_send(urls) -> dict:
    """Plain-socket client: it releases the GIL while waiting, so the in-process
    server (Python slots on this thread) can answer. (``ipc.send_add`` is Qt
    blocking I/O and is exercised from a separate process below.)"""
    path = ipc.socket_path()
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(5)
        sock.connect(str(path))
        sock.sendall(json.dumps({"v": 1, "action": "add", "urls": list(urls)}).encode() + b"\n")
        data = b""
        while b"\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    return json.loads(data.split(b"\n")[0])


def client_call(fn, *args, **kw):
    """Run a blocking client call in a thread while this thread pumps the server."""
    box: dict = {}

    def target():
        box["reply"] = (_stdlib_send if fn is ipc.send_add else fn)(*args, **kw)

    t = threading.Thread(target=target)
    t.start()
    pump_until(lambda: not t.is_alive())
    t.join(1)
    return box.get("reply", "no-reply")


def real_client(urls) -> dict | None:
    """The real ``ipc.send_add`` (Qt sockets) in its own process, as the CLI does."""
    code = ("import json,sys;from elisium_downloader.ui import ipc;"
            "print(json.dumps(ipc.send_add(json.loads(sys.argv[1]))))")
    root = str(Path(__file__).resolve().parents[1])
    proc = subprocess.Popen([sys.executable, "-c", code, json.dumps(list(urls))],
                            stdout=subprocess.PIPE, text=True, cwd=root,
                            env={**os.environ, "PYTHONPATH": root, "QT_QPA_PLATFORM": "offscreen"})
    pump_until(lambda: proc.poll() is not None, 20)
    return json.loads(proc.communicate(timeout=5)[0])


@pytest.fixture
def runtime(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def server(runtime):
    calls: list = []
    threads: list = []

    def handler(urls):
        calls.append(list(urls))
        threads.append(threading.current_thread())
        return {"added": len(urls) - 1 if len(urls) > 1 else len(urls),
                "known": 1 if len(urls) > 1 else 0, "ignored": 0}

    srv = ipc.acquire_server(handler, read_timeout_ms=300)
    assert srv is not None
    srv.calls, srv.threads = calls, threads
    yield srv
    srv.close()


def test_round_trip(server) -> None:
    reply = client_call(ipc.send_add, ["https://a.com/1", "https://b.com/2", "file:///x"])
    assert reply == {"ok": True, "added": 1, "known": 1, "ignored": 1}
    assert server.calls == [["https://a.com/1", "https://b.com/2"]]  # file: never reached it
    assert server.threads == [threading.main_thread()]  # runs on the GUI thread


def test_real_qt_client_round_trip(server) -> None:
    reply = real_client(["https://a.com/1", "javascript:1"])
    assert reply == {"ok": True, "added": 1, "known": 0, "ignored": 1}
    assert server.calls == [["https://a.com/1"]]


def test_empty_add_is_a_silent_no_op(server) -> None:
    assert client_call(ipc.send_add, []) == {"ok": True, "added": 0, "known": 0, "ignored": 0}
    assert server.calls == []


def raw_exchange(server, payload: bytes, wait: float = 1.0) -> dict | None:
    sock = QLocalSocket()
    sock.connectToServer(str(server.path))
    assert pump_until(lambda: sock.state() == QLocalSocket.LocalSocketState.ConnectedState)
    sock.write(payload)
    sock.flush()
    assert pump_until(lambda: sock.bytesAvailable() > 0 or
                      sock.state() == QLocalSocket.LocalSocketState.UnconnectedState, wait)
    data = bytes(sock.readAll())
    sock.abort()
    return json.loads(data.split(b"\n")[0]) if data.strip() else None


def test_malformed_json_gets_error_and_server_survives(server) -> None:
    assert raw_exchange(server, b"{not json\n") == {"ok": False, "error": "malformed message"}
    assert client_call(ipc.send_add, ["https://a.com/1"])["ok"] is True


def test_wrong_version_and_unknown_action(server) -> None:
    assert raw_exchange(server, msg(v=7) + b"\n")["error"] == "unsupported version"
    assert raw_exchange(server, msg(action="quit") + b"\n")["error"] == "unknown action"
    assert server.calls == []


def test_oversize_message_is_rejected(server) -> None:
    reply = raw_exchange(server, b"x" * (ipc.MAX_MESSAGE_BYTES + 100))
    assert reply == {"ok": False, "error": "message too large"}
    assert client_call(ipc.send_add, ["https://a.com/1"])["ok"] is True


def test_slow_client_times_out(server) -> None:
    sock = QLocalSocket()
    sock.connectToServer(str(server.path))
    assert pump_until(lambda: sock.state() == QLocalSocket.LocalSocketState.ConnectedState)
    sock.write(b'{"v": 1, "action": "add", "urls": [')  # never finished, no newline
    sock.flush()
    assert pump_until(lambda: sock.bytesAvailable() > 0, 3.0)
    assert json.loads(bytes(sock.readAll()).split(b"\n")[0]) == {"ok": False, "error": "timeout"}
    assert pump_until(lambda: sock.state() == QLocalSocket.LocalSocketState.UnconnectedState, 2.0)
    assert server.calls == []


def test_socket_permissions_are_owner_only(server) -> None:
    mode = stat.S_IMODE(server.path.stat().st_mode)
    assert mode & 0o077 == 0, oct(mode)


def test_second_instance_detects_the_first(server) -> None:
    assert ipc.acquire_server() is None


def test_stale_socket_file_is_recovered(runtime) -> None:
    path = runtime / "elisium.sock"
    dead = socket.socket(socket.AF_UNIX)
    dead.bind(str(path))
    dead.close()  # leaves the file behind, nobody listening (a crash)
    assert path.exists()
    srv = ipc.acquire_server(lambda urls: {"added": len(urls)})
    try:
        assert srv is not None
        assert client_call(ipc.send_add, ["https://a.com/1"])["added"] == 1
    finally:
        srv.close()
    assert not path.exists()  # closing removes the file


def test_send_add_without_instance_returns_none(runtime) -> None:
    assert ipc.send_add(["https://a.com/1"]) is None
    (runtime / "elisium.sock").write_text("")  # a leftover non-socket file
    assert ipc.send_add(["https://a.com/1"]) is None


def test_second_process_does_not_hijack_a_live_socket(server) -> None:
    """Qt's own listen() would replace a live socket; the start-up lock prevents it."""
    code = ("from PySide6.QtCore import QCoreApplication;a=QCoreApplication([]);"
            "from elisium_downloader.ui import ipc;print(ipc.acquire_server())")
    root = str(Path(__file__).resolve().parents[1])
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=root,
                         env={**os.environ, "PYTHONPATH": root}, timeout=30)
    assert out.stdout.strip() == "None", out.stderr
    assert client_call(ipc.send_add, ["https://a.com/1"])["ok"] is True  # original still serves


def test_send_add_leaves_room_for_the_gui_application(tmp_path) -> None:
    """The CLI probes first and may then start the GUI: the probe must not create a
    QCoreApplication (that would block the later QApplication)."""
    code = ("from PySide6.QtCore import QCoreApplication;from PySide6.QtWidgets import QApplication;"
            "from elisium_downloader.ui import ipc;"
            "assert ipc.send_add(['https://a.com/1']) is None;"
            "assert QCoreApplication.instance() is None;"
            "print(type(QApplication([])).__name__)")
    root = str(Path(__file__).resolve().parents[1])
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=root,
                         env={**os.environ, "PYTHONPATH": root, "QT_QPA_PLATFORM": "offscreen",
                              "XDG_RUNTIME_DIR": str(tmp_path)}, timeout=30)
    assert out.stdout.strip() == "QApplication", out.stderr
