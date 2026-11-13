"""Pure helpers that turn a yt-dlp ``-J`` dict into rows for the UI.

Nothing here runs yt-dlp or touches Qt; every function takes plain dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

__all__ = [
    "FormatRow",
    "VideoSummary",
    "PlaylistEntry",
    "format_rows",
    "selector_for",
    "human_size",
    "human_duration",
    "summary",
    "playlist_entries",
    "parse_range",
]

KIND_BOTH = "video+audio"
KIND_VIDEO = "video"
KIND_AUDIO = "audio"
_KIND_RANK = {KIND_BOTH: 0, KIND_VIDEO: 1, KIND_AUDIO: 2}
_AUDIO_EXTS = frozenset({"m4a", "mp3", "opus", "ogg", "oga", "flac", "wav", "aac", "weba"})
_UNAVAILABLE_TITLES = frozenset({"[private video]", "[deleted video]", "[unavailable]"})
_UNAVAILABLE_AVAILABILITY = frozenset({"private", "needs_auth"})
_BAD_ID_CHARS = frozenset("+/,()[]\"'")


@dataclass(frozen=True)
class FormatRow:
    format_id: str
    ext: str
    resolution: str
    fps: float | None
    vcodec: str
    acodec: str
    bitrate: float | None
    size_bytes: int | None
    note: str
    kind: str
    height: int | None = None


@dataclass(frozen=True)
class VideoSummary:
    title: str
    uploader: str
    duration: int | None
    thumbnail: str | None
    webpage_url: str | None


@dataclass(frozen=True)
class PlaylistEntry:
    index: int
    id: str | None
    title: str
    url: str | None
    duration: int | None
    available: bool


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value == value else None  # drop NaN


def _int(value: Any) -> int | None:
    number = _num(value)
    return None if number is None else int(number)


def _codec(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _kind(fmt: Mapping[str, Any]) -> str | None:
    """The kind of *fmt*, or ``None`` when it is neither video nor audio."""
    vcodec = _codec(fmt.get("vcodec"))
    acodec = _codec(fmt.get("acodec"))
    has_video = vcodec not in ("none",)
    has_audio = acodec not in ("none",)
    if not vcodec and not acodec:
        # Generic extractors often give neither: infer from size/extension.
        if fmt.get("height") or fmt.get("width"):
            return KIND_BOTH
        if str(fmt.get("ext") or "").lower() in _AUDIO_EXTS:
            return KIND_AUDIO
        return KIND_BOTH
    if not vcodec:
        has_video = bool(fmt.get("height") or fmt.get("width"))
    if not acodec:
        has_audio = vcodec == "none"
    if has_video and has_audio:
        return KIND_BOTH
    if has_video:
        return KIND_VIDEO
    if has_audio:
        return KIND_AUDIO
    return None


def _is_storyboard(fmt: Mapping[str, Any]) -> bool:
    ext = str(fmt.get("ext") or "").lower()
    note = str(fmt.get("format_note") or "").lower()
    protocol = str(fmt.get("protocol") or "").lower()
    return ext == "mhtml" or "storyboard" in note or protocol == "mhtml"


def format_rows(info: Mapping[str, Any]) -> list[FormatRow]:
    """Rows for every downloadable format in *info*, best first.

    Order: video with audio, video only, audio only; inside a group by height,
    frame rate and bitrate, highest first. Storyboards (``mhtml``) are skipped.
    """
    formats = info.get("formats") if isinstance(info, Mapping) else None
    if not isinstance(formats, list):
        return []
    rows: list[FormatRow] = []
    for fmt in formats:
        if not isinstance(fmt, Mapping) or _is_storyboard(fmt):
            continue
        format_id = fmt.get("format_id")
        if format_id is None or not str(format_id).strip():
            continue
        kind = _kind(fmt)
        if kind is None:
            continue
        height = _int(fmt.get("height"))
        width = _int(fmt.get("width"))
        if kind == KIND_AUDIO:
            resolution = "audio only"
        elif width and height:
            resolution = f"{width}x{height}"
        elif height:
            resolution = f"{height}p"
        else:
            resolution = "unknown"
        bitrate = _num(fmt.get("tbr"))
        if bitrate is None:
            vbr, abr = _num(fmt.get("vbr")), _num(fmt.get("abr"))
            if vbr is not None or abr is not None:
                bitrate = (vbr or 0.0) + (abr or 0.0)
        size = _int(fmt.get("filesize"))
        if size is None:
            size = _int(fmt.get("filesize_approx"))
        rows.append(
            FormatRow(
                format_id=str(format_id).strip(),
                ext=str(fmt.get("ext") or ""),
                resolution=resolution,
                fps=_num(fmt.get("fps")),
                vcodec=_codec(fmt.get("vcodec")) or ("none" if kind == KIND_AUDIO else ""),
                acodec=_codec(fmt.get("acodec")) or ("none" if kind == KIND_VIDEO else ""),
                bitrate=bitrate,
                size_bytes=size,
                note=str(fmt.get("format_note") or fmt.get("format") or ""),
                kind=kind,
                height=height,
            )
        )
    rows.sort(
        key=lambda r: (
            _KIND_RANK[r.kind],
            -(r.height or 0),
            -(r.fps or 0.0),
            -(r.bitrate or 0.0),
        )
    )
    return rows


def _clean_id(value: str | None, what: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if any(ch.isspace() or ch in _BAD_ID_CHARS for ch in text):
        raise ValueError(f"invalid {what} format id: {value!r}")
    return text


def selector_for(video_id: str | None, audio_id: str | None) -> str:
    """The yt-dlp ``-f`` selector for the chosen formats.

    ``"137+140"`` (video + audio), ``"137"`` (video, or video with audio inside)
    or ``"140"`` (audio only). Raises ``ValueError`` when both are empty.
    """
    video = _clean_id(video_id, "video")
    audio = _clean_id(audio_id, "audio")
    if video and audio:
        return f"{video}+{audio}"
    if video:
        return video
    if audio:
        return audio
    raise ValueError("choose a video or an audio format")


def human_size(size_bytes: int | float | None) -> str:
    """``1.5 MB`` style size; ``unknown`` when not known."""
    if size_bytes is None or isinstance(size_bytes, bool) or size_bytes < 0:
        return "unknown"
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"  # pragma: no cover


def human_duration(seconds: int | float | None) -> str:
    """``3:05`` or ``1:02:03``; empty string when not known."""
    if seconds is None or isinstance(seconds, bool) or seconds < 0:
        return ""
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def summary(info: Mapping[str, Any]) -> VideoSummary:
    """Title, uploader, duration (seconds), thumbnail URL and page URL."""
    thumbnail = _text(info.get("thumbnail")) or None
    if thumbnail is None:
        thumbs = info.get("thumbnails")
        if isinstance(thumbs, list):
            for thumb in reversed(thumbs):
                if isinstance(thumb, Mapping) and _text(thumb.get("url")):
                    thumbnail = _text(thumb.get("url"))
                    break
    return VideoSummary(
        title=_text(info.get("title")) or "Untitled video",
        uploader=_text(info.get("uploader")) or _text(info.get("channel")) or "",
        duration=_int(info.get("duration")),
        thumbnail=thumbnail,
        webpage_url=_text(info.get("webpage_url")) or _text(info.get("original_url")) or None,
    )


def _entry_url(entry: Mapping[str, Any]) -> str | None:
    for key in ("webpage_url", "url"):
        value = _text(entry.get(key))
        if value.lower().startswith(("http://", "https://")):
            return value
    video_id = _text(entry.get("id")) or _text(entry.get("url"))
    ie_key = str(entry.get("ie_key") or entry.get("extractor_key") or "").lower()
    if video_id and ie_key.startswith("youtube") and "/" not in video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return None


def playlist_entries(info: Mapping[str, Any]) -> list[PlaylistEntry]:
    """One entry per playlist position (1-based), unavailable ones flagged.

    ``None`` entries (yt-dlp's hole for a deleted/private video) keep their
    position so a range such as ``3-15`` matches the playlist's own numbering.
    """
    entries = info.get("entries") if isinstance(info, Mapping) else None
    if entries is None:
        return []
    result: list[PlaylistEntry] = []
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, Mapping):
            result.append(PlaylistEntry(position, None, f"Video {position}", None, None, False))
            continue
        url = _entry_url(entry)
        title = _text(entry.get("title")) or _text(entry.get("id")) or url or f"Video {position}"
        gone = (
            title.lower() in _UNAVAILABLE_TITLES
            or str(entry.get("availability") or "").lower() in _UNAVAILABLE_AVAILABILITY
        )
        result.append(
            PlaylistEntry(
                index=position,
                id=_text(entry.get("id")) or None,
                title=title,
                url=url,
                duration=_int(entry.get("duration")),
                available=url is not None and not gone,
            )
        )
    return result


def parse_range(text: str, total: int) -> list[int]:
    """Parse ``3-15`` / ``1,4,9-12`` into sorted unique 1-based numbers.

    Blank text gives ``[]``. Raises ``ValueError`` with a plain-language
    message (shown to the user as is) for anything it cannot use.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    example = "Use numbers like 3-15 or 1,4,9-12."
    numbers: set[int] = set()
    for part in cleaned.replace(" ", "").split(","):
        if not part:
            raise ValueError(f"There is an extra comma. {example}")
        low_text, dash, high_text = part.partition("-")
        if not low_text.isdigit() or (dash and not high_text.isdigit()):
            raise ValueError(f"\"{part}\" is not a number or a range. {example}")
        low = int(low_text)
        high = int(high_text) if dash else low
        if low < 1 or high < 1:
            raise ValueError("Numbers start at 1.")
        if low > high:
            raise ValueError(f"\"{part}\" runs backwards; write it as {high}-{low}.")
        if high > total:
            noun = "video" if total == 1 else "videos"
            raise ValueError(f"{high} is past the end; this playlist has {total} {noun}.")
        numbers.update(range(low, high + 1))
    return sorted(numbers)
