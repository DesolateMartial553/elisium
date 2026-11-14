"""Single instance and link hand-over: a per-user local socket, JSON messages.

Untrusted pages can reach this through ``elisium://`` links, so the rules are
strict: only ``http``/``https`` links, a size and count limit, and the only
action is ``add`` (the default preset, never any option from the message).
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import shiboken6
from PySide6.QtCore import QCoreApplication, QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

__all__ = [
    "IpcServer",
    "MAX_MESSAGE_BYTES",
    "MAX_URL_LENGTH",
    "MAX_URLS",
    "acquire_server",
    "handle_message",
    "links_from_elisium_uri",
    "send_add",
    "socket_path",
    "split_links",
    "valid_link",
]

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 64 * 1024
MAX_URL_LENGTH = 2048
MAX_URLS = 50
READ_TIMEOUT_MS = 3000
SOCKET_FILE = "elisium.sock"
URI_SCHEME = "elisium"

_BAD_CHARS = re.compile(r"[\s\x00-\x1f\x7f]")

Handler = Callable[[list[str]], dict[str, int]]


# -- link parsing ---------------------------------------------------------
def valid_link(value: object) -> bool:
    """True for one ``http``/``https`` URL of at most 2048 characters."""
    if not isinstance(value, str) or not value or len(value) > MAX_URL_LENGTH:
        return False
    if _BAD_CHARS.search(value):
        return False
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        return False
    return parts.scheme.lower() in ("http", "https") and bool(host)


def split_links(text: str) -> tuple[list[str], int]:
    """Split *text* on whitespace; return (valid links, ignored count)."""
    good: list[str] = []
    ignored = 0
    for token in text.split():
        if valid_link(token):
            good.append(token)
        else:
            ignored += 1
    return good, ignored


def links_from_elisium_uri(uri: str) -> tuple[list[str], int]:
    """Links carried by ``elisium://add?url=...`` (``url=`` repeated, ``urls=``).

    Only the action ``add`` is understood and only the ``url``/``urls``
    parameters are read; everything else (format, path, args...) is ignored.
    Returns (valid links, ignored count).
    """
    try:
        parts = urlsplit(uri.strip())
    except ValueError:
        return [], 0
    if parts.scheme.lower() != URI_SCHEME or parts.netloc.lower() != "add":
        return [], 0
    try:
        query = parse_qs(parts.query, keep_blank_values=False, max_num_fields=500)
    except ValueError:
        return [], 0
    good: list[str] = []
    ignored = 0
    for value in query.get("url", []):
        value = value.strip()
        if valid_link(value):
            good.append(value)
        else:
            ignored += 1
    for value in query.get("urls", []):
        found, bad = split_links(value)
        good.extend(found)
        ignored += bad
    return good, ignored


# -- socket location ------------------------------------------------------
def socket_path() -> Path:
    """Per-user socket path: ``$XDG_RUNTIME_DIR/elisium.sock``.

    Without a runtime dir, a private ``elisium-<uid>`` folder in the temp dir
    (created 0700; refused if it is a symlink or belongs to someone else).
    Raises ``OSError`` when no safe place exists.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.isabs(runtime) and os.path.isdir(runtime):
        return Path(runtime) / SOCKET_FILE
    uid = os.getuid()
    folder = Path(tempfile.gettempdir()) / f"elisium-{uid}"
    try:
        folder.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = folder.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid:
        raise OSError(f"{folder} is not a private folder of this user")
    if stat.S_IMODE(info.st_mode) & 0o077:
        folder.chmod(0o700)
    return folder / SOCKET_FILE


# -- protocol -------------------------------------------------------------
def _error(text: str) -> dict[str, Any]:
    return {"ok": False, "error": text}


def handle_message(raw: bytes, handler: Handler) -> dict[str, Any]:
    """Validate one request and run *handler*; always returns a reply dict."""
    if len(raw) > MAX_MESSAGE_BYTES:
        return _error("message too large")
    try:
        message = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _error("malformed message")
    if not isinstance(message, dict):
        return _error("malformed message")
    if message.get("v") != PROTOCOL_VERSION or isinstance(message.get("v"), bool):
        return _error("unsupported version")
    if message.get("action") != "add":
        return _error("unknown action")
    urls = message.get("urls")
    if not isinstance(urls, list):
        return _error("urls must be a list")
    if len(urls) > MAX_URLS:
        return _error("too many urls")
    good = [u for u in urls if valid_link(u)]
    invalid = len(urls) - len(good)
    counts = {"added": 0, "known": 0, "ignored": 0}
    if good:
        try:
            result = handler(good)
        except Exception:  # never let a bad message take the app down
            return _error("internal error")
        for key in ("added", "known", "ignored"):
            value = result.get(key, 0)
            counts[key] = value if isinstance(value, int) else 0
        if isinstance(result.get("playlists"), int) and result["playlists"]:
            counts["playlists"] = result["playlists"]
    counts["ignored"] += invalid
    return {"ok": True, **counts}


class _Session(QObject):
    """One client connection: read until newline/EOF, answer once, close."""

    def __init__(self, sock: QLocalSocket, handler: Handler, timeout_ms: int,
                 parent: QObject) -> None:
        super().__init__(parent)
        self._sock = sock
        self._handler = handler
        self._buffer = bytearray()
        self._done = False
        # While this object is being destroyed Qt still lets its child socket emit
        # ``disconnected``; ``deleteLater`` from that slot would post an event for an
        # object that is already gone (Qt removes posted events *before* it deletes the
        # children), and the next event-loop pass would crash. ``destroyed`` fires first,
        # so it flips a flag the slots check. (A plain list: no reference to ``self``.)
        self._dying = dying = [False]
        self.destroyed.connect(lambda *_: dying.__setitem__(0, True))
        sock.setParent(self)
        sock.readyRead.connect(self._on_ready)
        sock.disconnected.connect(self._on_disconnected)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._timer.start(timeout_ms)
        if sock.bytesAvailable():
            self._on_ready()

    def dispose(self) -> None:
        """Drop the connection without answering (server shutdown)."""
        self._dying[0] = True
        self._done = True
        self._timer.stop()
        self._sock.disconnected.disconnect(self._on_disconnected)
        self._sock.readyRead.disconnect(self._on_ready)
        self._sock.abort()

    def _on_ready(self) -> None:
        if self._done or self._dying[0]:
            return
        # Never buffer more than the limit (+1 byte to detect overflow).
        room = MAX_MESSAGE_BYTES + 1 - len(self._buffer)
        self._buffer += bytes(self._sock.read(max(room, 0)))
        if len(self._buffer) > MAX_MESSAGE_BYTES:
            self._finish(_error("message too large"))
        elif b"\n" in self._buffer:
            line = bytes(self._buffer).split(b"\n", 1)[0]
            self._finish(handle_message(line, self._handler))

    def _on_disconnected(self) -> None:
        if self._dying[0]:
            return
        if not self._done:
            self._on_ready()
        if not self._done and self._buffer:
            self._finish(handle_message(bytes(self._buffer), self._handler))
        self.deleteLater()

    def _on_timeout(self) -> None:
        self._finish(_error("timeout"))

    def _finish(self, reply: dict[str, Any]) -> None:
        if self._done or self._dying[0]:
            return
        self._done = True
        self._timer.stop()
        if self._sock.state() == QLocalSocket.LocalSocketState.ConnectedState:
            self._sock.write(json.dumps(reply).encode("utf-8") + b"\n")
            self._sock.flush()
            self._sock.disconnectFromServer()
        else:
            self.deleteLater()


class IpcServer(QObject):
    """Listens on the per-user socket and passes links to ``handler``.

    The handler runs on the thread that owns this object (the GUI thread).
    """

    def __init__(self, server: QLocalServer, path: Path, handler: Handler | None = None,
                 *, read_timeout_ms: int = READ_TIMEOUT_MS) -> None:
        super().__init__()
        self.path = path
        self._lock_fd: int | None = None
        self.read_timeout_ms = read_timeout_ms
        self._handler: Handler = handler or (lambda urls: {"added": 0, "known": 0, "ignored": len(urls)})
        self._server = server
        server.setParent(self)
        server.newConnection.connect(self._on_connection)

    def set_handler(self, handler: Handler) -> None:
        self._handler = handler

    def _call(self, urls: list[str]) -> dict[str, int]:
        return self._handler(urls)

    def _on_connection(self) -> None:
        while (sock := self._server.nextPendingConnection()) is not None:
            _Session(sock, self._call, self.read_timeout_ms, self)

    def close(self) -> None:
        self._server.close()  # also removes the socket file
        for session in self.findChildren(_Session):  # connections still open
            session.dispose()
            shiboken6.delete(session)  # now, not via a posted event or the garbage collector
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None


def _connect(path: Path, timeout_ms: int) -> QLocalSocket | None:
    sock = QLocalSocket()
    sock.connectToServer(str(path))
    if sock.waitForConnected(timeout_ms):
        return sock
    sock.abort()
    return None


def _new_server(path: Path) -> QLocalServer | None:
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    return server if server.listen(str(path)) else None


def _lock(path: Path) -> int | None:
    """Take the start-up lock beside the socket; ``None`` if another instance has it.

    The lock dies with its process, so a crash never leaves it stuck. (Qt's
    ``listen`` would silently replace a live socket, so it is not enough alone.)
    """
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(str(path) + ".lock", flags, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def acquire_server(handler: Handler | None = None, *, path: Path | None = None,
                   read_timeout_ms: int = READ_TIMEOUT_MS) -> IpcServer | None:
    """Become the single instance, or return ``None`` if one is already running.

    A socket file left behind by a crash (the lock is free and nobody answers)
    is removed first. Raises ``OSError`` when there is no safe socket location.
    """
    path = path or socket_path()
    fd = _lock(path)
    if fd is None:
        return None
    probe = _connect(path, 500)
    if probe is not None:  # something answers although the lock was free
        probe.abort()
        os.close(fd)
        return None
    QLocalServer.removeServer(str(path))  # stale file from a crash
    server = _new_server(path)
    if server is None:
        os.close(fd)
        raise OSError(f"cannot listen on {path}")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    ipc = IpcServer(server, path, handler, read_timeout_ms=read_timeout_ms)
    ipc._lock_fd = fd
    return ipc


def send_add(urls: Iterable[str], *, path: Path | None = None, connect_ms: int = 1000,
             reply_ms: int = 8000) -> dict[str, Any] | None:
    """Send links to the running instance.

    Returns its reply, or ``None`` when no instance answers on the socket.
    A running instance that gives no usable reply yields ``{"ok": False, ...}``.
    """
    try:
        path = path or socket_path()
    except OSError:
        return None
    sock = _connect(path, connect_ms)
    if sock is None:
        return None
    request = {"v": PROTOCOL_VERSION, "action": "add", "urls": list(urls)}
    sock.write(json.dumps(request).encode("utf-8") + b"\n")
    sock.flush()
    buffer = bytearray()
    while b"\n" not in buffer and len(buffer) <= MAX_MESSAGE_BYTES:
        if not sock.waitForReadyRead(reply_ms):
            break
        buffer += bytes(sock.readAll())
    buffer += bytes(sock.readAll())
    sock.abort()
    try:
        reply = json.loads(bytes(buffer).split(b"\n", 1)[0].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _error("no usable reply")
    return reply if isinstance(reply, dict) else _error("no usable reply")

