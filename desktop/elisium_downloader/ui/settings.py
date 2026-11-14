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
from elisium_downloader.engine.queue import DEFAULT_CONCURRENCY, MAX_CONCURRENCY, DownloadQueue

__all__ = ["Settings", "apply", "default_path", "load", "save", "valid_speed_limit"]

_LIMIT_RE = re.compile(r"^\d+(\.\d+)?[KMG]?$")


def valid_speed_limit(value: object) -> str | None:
    """Return *value* if it is a valid ``--limit-rate`` string, else ``None``."""
    if isinstance(value, str) and _LIMIT_RE.match(value.strip()):
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


