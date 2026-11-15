"""Browser sign-in detection. Only fake profiles under tmp_path; never the real home."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from elisium_downloader.engine import browsers
from elisium_downloader.engine.browsers import BROWSER_ORDER, detect_instagram_browsers
from elisium_downloader.ui.settings import COOKIE_BROWSERS


def firefox_db(path: Path, rows: list[tuple[str, str]], value: str = "SECRET") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE moz_cookies (id INTEGER PRIMARY KEY, host TEXT, name TEXT, value TEXT)")
    con.executemany(
        "INSERT INTO moz_cookies (host, name, value) VALUES (?, ?, ?)",
        [(h, n, value) for h, n in rows],
    )
    con.commit()
    con.close()


def chromium_db(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT, encrypted_value BLOB)"
    )
    con.executemany(
        "INSERT INTO cookies VALUES (?, ?, 'SECRET', x'0102')", rows
    )
    con.commit()
    con.close()


SESSION = [(".instagram.com", "sessionid"), (".instagram.com", "csrftoken")]


def test_order_matches_settings() -> None:
    assert BROWSER_ORDER == COOKIE_BROWSERS


def test_nothing_found_in_empty_home(tmp_path: Path) -> None:
    assert detect_instagram_browsers(tmp_path) == []
    assert detect_instagram_browsers(tmp_path / "does-not-exist") == []


def test_firefox_detected(tmp_path: Path) -> None:
    firefox_db(tmp_path / ".mozilla/firefox/abc.default/cookies.sqlite", SESSION)
    assert detect_instagram_browsers(tmp_path) == ["firefox"]


def test_firefox_second_profile_and_flatpak(tmp_path: Path) -> None:
    firefox_db(tmp_path / ".mozilla/firefox/a.default/cookies.sqlite", [(".example.com", "x")])
    firefox_db(
        tmp_path / ".var/app/org.mozilla.firefox/.mozilla/firefox/b.default/cookies.sqlite",
        SESSION,
    )
    assert detect_instagram_browsers(tmp_path) == ["firefox"]


def test_chromium_family_and_profile_layouts(tmp_path: Path) -> None:
    chromium_db(tmp_path / ".config/google-chrome/Default/Cookies", SESSION)
    chromium_db(tmp_path / ".config/chromium/Profile 2/Network/Cookies", SESSION)
    chromium_db(tmp_path / ".config/BraveSoftware/Brave-Browser/Default/Network/Cookies", SESSION)
    chromium_db(tmp_path / ".config/microsoft-edge/Default/Cookies", SESSION)
    chromium_db(tmp_path / ".config/vivaldi/Default/Cookies", SESSION)
    chromium_db(tmp_path / ".config/opera/Default/Cookies", SESSION)
    assert detect_instagram_browsers(tmp_path) == [
        "chrome", "chromium", "brave", "edge", "vivaldi", "opera",
    ]


def test_ordered_like_cookie_browsers(tmp_path: Path) -> None:
    chromium_db(tmp_path / ".config/opera/Default/Cookies", SESSION)
    chromium_db(tmp_path / ".config/google-chrome/Default/Cookies", SESSION)
    firefox_db(tmp_path / ".mozilla/firefox/x/cookies.sqlite", SESSION)
    found = detect_instagram_browsers(tmp_path)
    assert found == ["firefox", "chrome", "opera"]
    assert found == [b for b in COOKIE_BROWSERS if b in found]


def test_requires_sessionid_and_instagram_host(tmp_path: Path) -> None:
    firefox_db(tmp_path / ".mozilla/firefox/a/cookies.sqlite", [(".instagram.com", "csrftoken")])
    chromium_db(tmp_path / ".config/google-chrome/Default/Cookies", [(".example.com", "sessionid")])
    chromium_db(tmp_path / ".config/chromium/Default/Cookies", [(".notinstagram.com", "sessionid")])
    chromium_db(tmp_path / ".config/vivaldi/Default/Cookies", [("www.instagram.com", "sessionid")])
    assert detect_instagram_browsers(tmp_path) == ["vivaldi"]


def test_bad_files_are_not_detected_and_never_raise(tmp_path: Path) -> None:
    corrupt = tmp_path / ".mozilla/firefox/a/cookies.sqlite"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_bytes(b"this is not a database" * 50)
    empty = tmp_path / ".config/google-chrome/Default/Cookies"
    empty.parent.mkdir(parents=True)
    empty.write_bytes(b"")  # empty file: no tables
    (tmp_path / ".config/chromium/Default").mkdir(parents=True)  # profile with no DB
    wrong = tmp_path / ".config/vivaldi/Default/Cookies"
    wrong.parent.mkdir(parents=True)
    con = sqlite3.connect(wrong)
    con.execute("CREATE TABLE other (a TEXT)")
    con.commit()
    con.close()
    (tmp_path / ".config/opera/Default/Cookies").mkdir(parents=True)  # a directory, not a file
    assert detect_instagram_browsers(tmp_path) == []


def test_locked_database_is_still_read_without_blocking(tmp_path: Path) -> None:
    db = tmp_path / ".mozilla/firefox/a/cookies.sqlite"
    firefox_db(db, SESSION)
    holder = sqlite3.connect(db, isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")  # a running browser holding the file
    try:
        assert detect_instagram_browsers(tmp_path) == ["firefox"]
    finally:
        holder.execute("ROLLBACK")
        holder.close()


def test_never_raises_on_odd_input() -> None:
    assert detect_instagram_browsers(Path("/definitely/not/here")) == []
    assert detect_instagram_browsers(None) == []  # type: ignore[arg-type]


def test_only_name_and_host_columns_are_read(tmp_path: Path, monkeypatch) -> None:
    firefox_db(tmp_path / ".mozilla/firefox/a/cookies.sqlite", SESSION)
    chromium_db(tmp_path / ".config/google-chrome/Default/Cookies", SESSION)
    read: set[str] = set()
    real_connect = sqlite3.connect

    class Spy:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self._c = conn

        def set_authorizer(self, cb) -> None:
            def wrapped(action, a1, a2, *rest):
                result = cb(action, a1, a2, *rest)
                if action == sqlite3.SQLITE_READ and result == sqlite3.SQLITE_OK:
                    read.add(a2)
                return result

            self._c.set_authorizer(wrapped)

        def __getattr__(self, name):
            return getattr(self._c, name)

    monkeypatch.setattr(browsers.sqlite3, "connect", lambda *a, **k: Spy(real_connect(*a, **k)))
    assert detect_instagram_browsers(tmp_path) == ["firefox", "chrome"]
    assert read and read <= {"", "name", "host", "host_key"}
    assert not read & {"value", "encrypted_value"}


def test_authorizer_denies_value_columns(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite"
    firefox_db(db, SESSION)
    conn = sqlite3.connect(f"{db.as_uri()}?mode=ro&immutable=1", uri=True)
    conn.set_authorizer(browsers._authorizer)
    try:
        conn.execute("SELECT value FROM moz_cookies").fetchall()
    except sqlite3.DatabaseError:
        denied = True
    else:
        denied = False
    finally:
        conn.close()
    assert denied


def test_detection_does_not_modify_or_copy_the_database(tmp_path: Path) -> None:
    db = tmp_path / ".mozilla/firefox/a/cookies.sqlite"
    firefox_db(db, SESSION)
    before = db.read_bytes()
    before_files = sorted(p.name for p in db.parent.iterdir())
    detect_instagram_browsers(tmp_path)
    assert db.read_bytes() == before
    assert sorted(p.name for p in db.parent.iterdir()) == before_files
