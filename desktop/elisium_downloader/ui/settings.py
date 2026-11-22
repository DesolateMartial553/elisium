"""User settings: validation, JSON load/save, and pushing them into the queue."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from elisium_downloader.engine import paths
from elisium_downloader.engine.presets import DEFAULT_ID, PRESETS, get
from elisium_downloader.engine.queue import (
    DEFAULT_CONCURRENCY,
    MAX_CONCURRENCY,
    PHOTO_MODES,
    SONG_LENGTHS,
    DownloadQueue,
)

__all__ = [
    "COOKIE_BROWSERS",
    "Settings",
    "apply",
    "default_path",
    "load",
    "save",
    "valid_cookie_browser",
    "valid_cookies_file",
    "valid_speed_limit",
]

_LIMIT_RE = re.compile(r"^\d+(\.\d+)?[KMG]?$")

# Browsers yt-dlp can read cookies from (``--cookies-from-browser``). The order
# is the order of the Settings dropdown.
COOKIE_BROWSERS: tuple[str, ...] = (
    "firefox",
    "chrome",
    "chromium",
    "brave",
    "edge",
    "vivaldi",
    "opera",
)


def valid_speed_limit(value: object) -> str | None:
    """Return *value* if it is a valid ``--limit-rate`` string, else ``None``."""
    if isinstance(value, str) and _LIMIT_RE.match(value.strip()):
        return value.strip()
    return None


def valid_cookie_browser(value: object) -> str | None:
    """Return *value* as a lower-case browser name, or ``None`` ("not signed in")."""
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in COOKIE_BROWSERS:
            return lowered
    return None


def valid_cookies_file(value: object) -> str | None:
    """Return *value* if it is a usable cookies.txt path, else ``None``."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


@dataclass
class Settings:
    concurrency: int = DEFAULT_CONCURRENCY
    speed_limit: str | None = None
    preset_id: str = DEFAULT_ID
    notify_on_done: bool = True
    close_to_tray: bool = False
    appearance: str = "system"  # "system" | "night" | "day"
    reduce_motion: bool = False
    # Instagram stories/private posts need a signed-in session; yt-dlp can read
    # the cookies of a browser the user is already signed in to, or a
    # cookies.txt file. Browser wins when both are set.
    cookies_browser: str | None = None
    cookies_file: str | None = None
    # Photos and music (brief 10C): "video" = photos, song and video; "song" =
    # photos and song only; "photos" = photos only. "snippet" = the part the
    # post plays; "full" = the whole song.
    photo_mode: str = "video"
    song_length: str = "snippet"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Replace every invalid field with its default."""
        c = self.concurrency
        if isinstance(c, bool) or not isinstance(c, int) or not 1 <= c <= MAX_CONCURRENCY:
            self.concurrency = DEFAULT_CONCURRENCY
        self.speed_limit = valid_speed_limit(self.speed_limit)
        if self.preset_id not in PRESETS:
            self.preset_id = DEFAULT_ID
        if not isinstance(self.notify_on_done, bool):
            self.notify_on_done = True
        if not isinstance(self.close_to_tray, bool):
            self.close_to_tray = False
        if self.appearance not in ("system", "night", "day"):
            self.appearance = "system"
        if not isinstance(self.reduce_motion, bool):
            self.reduce_motion = False
        self.cookies_browser = valid_cookie_browser(self.cookies_browser)
        self.cookies_file = valid_cookies_file(self.cookies_file)
        if self.photo_mode not in PHOTO_MODES:
            self.photo_mode = "video"
        if self.song_length not in SONG_LENGTHS:
            self.song_length = "snippet"


def default_path() -> Path:
    return paths.config_dir() / "settings.json"


def load(path: str | os.PathLike[str]) -> Settings:
    """Read settings; a missing or corrupt file gives defaults, never raises."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in data.items() if k in known})


def save(settings: Settings, path: str | os.PathLike[str]) -> None:
    """Write settings atomically (temp file in the same folder, then replace)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(asdict(settings), handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def apply(settings: Settings, queue: DownloadQueue) -> None:
    """Push the queue-related settings into *queue* (affects downloads that start later)."""
    preset = get(settings.preset_id)
    queue.set_concurrency(settings.concurrency)
    queue.set_limit_rate(settings.speed_limit)
    queue.set_format_selector(preset.format_selector)
    queue.set_extra_args(preset.extra_args)
    queue.set_cookies(settings.cookies_browser, settings.cookies_file)
    queue.set_photo_mode(settings.photo_mode)
    queue.set_song_length(settings.song_length)


