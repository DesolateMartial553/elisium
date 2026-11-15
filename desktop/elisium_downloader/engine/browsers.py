"""Find which browser holds a signed-in Instagram session.

Privacy rules (binding, see briefs/phase9-d):
- Only *whether* a ``sessionid`` cookie for instagram.com exists is checked.
- Only the cookie name and host columns are ever read. A SQLite authorizer
  denies every other column, so even a coding mistake cannot read a value.
- The database is opened read-only with the ``immutable`` URI flag (a running
  browser is not disturbed), is never copied or written, and nothing from it is
  logged or stored.
- Any error (missing, locked, corrupt, wrong schema) means "not detected".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

__all__ = ["BROWSER_ORDER", "detect_default", "detect_instagram_browsers"]

# Same order as ``ui.settings.COOKIE_BROWSERS`` (a test keeps them in step).
BROWSER_ORDER: tuple[str, ...] = (
    "firefox", "chrome", "chromium", "brave", "edge", "vivaldi", "opera",
)

_FIREFOX_ROOTS = (
    ".mozilla/firefox",
    ".var/app/org.mozilla.firefox/.mozilla/firefox",
    "snap/firefox/common/.mozilla/firefox",
)
_CHROMIUM_ROOTS: dict[str, tuple[str, ...]] = {
    "chrome": (".config/google-chrome", ".var/app/com.google.Chrome/config/google-chrome"),
    "chromium": (
        ".config/chromium",
        ".var/app/org.chromium.Chromium/config/chromium",
        "snap/chromium/common/chromium",
    ),
    "brave": (
        ".config/BraveSoftware/Brave-Browser",
        ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser",
    ),
    "edge": (".config/microsoft-edge", ".var/app/com.microsoft.Edge/config/microsoft-edge"),
    "vivaldi": (".config/vivaldi",),
    "opera": (".config/opera",),
}

_MAX_PROFILES = 50  # sanity cap per browser

# Columns the authorizer lets a query touch. Nothing else can be read.
_ALLOWED_COLUMNS = frozenset({"", "name", "host", "host_key"})
_FIREFOX_SQL = "SELECT name, host FROM moz_cookies WHERE name = 'sessionid'"
_CHROMIUM_SQL = "SELECT name, host_key FROM cookies WHERE name = 'sessionid'"


def _authorizer(action: int, arg1: str | None, arg2: str | None, *_: object) -> int:
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        return sqlite3.SQLITE_OK if (arg2 or "") in _ALLOWED_COLUMNS else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _is_instagram_host(host: object) -> bool:
    if not isinstance(host, str):
        return False
    host = host.strip().lower().lstrip(".")
    return host == "instagram.com" or host.endswith(".instagram.com")


def _has_session(db: Path, sql: str) -> bool:
    """True when *db* has an instagram.com ``sessionid`` cookie. Never raises."""
    conn: sqlite3.Connection | None = None
    try:
        if not db.is_file():
            return False
        conn = sqlite3.connect(f"{db.as_uri()}?mode=ro&immutable=1", uri=True, timeout=0.2)
        conn.set_authorizer(_authorizer)
        return any(_is_instagram_host(host) for _name, host in conn.execute(sql))
    except Exception:  # noqa: BLE001 - locked/missing/corrupt/odd schema: "not detected"
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def _firefox(home: Path) -> bool:
    for root in _FIREFOX_ROOTS:
        try:
            profiles = sorted((home / root).glob("*"))[:_MAX_PROFILES]
        except OSError:
            continue
        if any(_has_session(p / "cookies.sqlite", _FIREFOX_SQL) for p in profiles):
            return True
    return False


def _chromium(home: Path, roots: tuple[str, ...]) -> bool:
    for root in roots:
        base = home / root
        try:
            profiles = [
                p for p in sorted(base.iterdir())
                if p.name == "Default" or p.name.startswith("Profile ")
            ][:_MAX_PROFILES]
        except OSError:
            continue
        for profile in profiles:
            for rel in ("Network/Cookies", "Cookies"):
                if _has_session(profile / rel, _CHROMIUM_SQL):
                    return True
    return False


def detect_instagram_browsers(home: Path) -> list[str]:
    """Browsers (ordered like ``COOKIE_BROWSERS``) with a signed-in Instagram session.

    *home* is passed in so tests never touch the real home directory.
    Never raises.
    """
    found: list[str] = []
    try:
        home = Path(home)
        for name in BROWSER_ORDER:
            try:
                hit = _firefox(home) if name == "firefox" else _chromium(home, _CHROMIUM_ROOTS[name])
            except Exception:  # noqa: BLE001
                hit = False
            if hit:
                found.append(name)
    except Exception:  # noqa: BLE001
        return []
    return found


def detect_default() -> list[str]:
    """Detect using the real home directory (the app's default; tests replace it)."""
    try:
        return detect_instagram_browsers(Path.home())
    except Exception:  # noqa: BLE001
        return []
