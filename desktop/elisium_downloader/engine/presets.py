"""Format presets for yt-dlp quality selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

__all__ = ["DEFAULT_ID", "Preset", "PRESETS", "get"]

DEFAULT_ID = "best"


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    format_selector: str
    extra_args: tuple[str, ...] = ()


_PRESET_LIST: list[Preset] = [
    Preset("best", "Best quality", "bestvideo*+bestaudio/best"),
    Preset("1080p", "1080p", "bestvideo*[height<=1080]+bestaudio/best[height<=1080]"),
    Preset("720p", "720p", "bestvideo*[height<=720]+bestaudio/best[height<=720]"),
    Preset("audio-mp3", "Audio only (MP3)", "bestaudio/best", ("-x", "--audio-format", "mp3")),
    # Prefer a stream already in the target codec so ffmpeg copies instead of
    # re-encoding (brief 12B); the ``-x --audio-format`` result is unchanged.
    Preset(
        "audio-m4a",
        "Audio only (M4A)",
        "bestaudio[ext=m4a]/bestaudio/best",
        ("-x", "--audio-format", "m4a"),
    ),
    Preset(
        "audio-opus",
        "Audio only (Opus)",
        "bestaudio[acodec=opus]/bestaudio/best",
        ("-x", "--audio-format", "opus"),
    ),
    Preset("audio-flac", "Audio only (FLAC)", "bestaudio/best", ("-x", "--audio-format", "flac")),
    Preset("smallest", "Smallest file", "wv*+wa/w"),
]

PRESETS: dict[str, Preset] = {p.id: p for p in _PRESET_LIST}


def get(preset_id: str | None) -> Preset:
    """Return the Preset for *preset_id*, falling back to ``best`` if unknown."""
    if preset_id and preset_id in PRESETS:
        return PRESETS[preset_id]
    return PRESETS[DEFAULT_ID]
