"""URL normalisation and dedupe keys.

Rules come from ``core-spec/SPEC.md`` (layer 3 of the dedupe plan):

* every YouTube video URL form collapses to one canonical watch URL;
* tracking parameters are dropped;
* a playlist URL keeps its ``list`` parameter;
* other sites keep everything except the fragment and ``utm_*`` parameters.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = ["normalize_url", "video_key"]

_YOUTUBE_HOSTS = {"youtube.com", "youtube-nocookie.com"}
_SHORT_HOST = "youtu.be"
_VIDEO_PATH_PREFIXES = ("shorts", "embed", "live", "v")
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_TIME_RE = re.compile(r"^(?:\d+h)?(?:\d+m)?(?:\d+s)?$")

# Dropped on every site / every YouTube URL.
_TRACKING_PARAMS = {"si", "feature", "pp"}
# Dropped only when the URL points at a single video (not a playlist).
_VIDEO_ONLY_DROP = {"list", "index"}


def _split(url: str):
    if not isinstance(url, str):
        raise ValueError("URL must be a string")
    raw = url.strip()
    if not raw:
        raise ValueError("URL is empty")
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parts.scheme or '(none)'}")
    if not parts.hostname:
        raise ValueError(f"URL has no host: {url!r}")
    return parts


def _is_start_time(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    if value.isdigit():
        return True
    return bool(_TIME_RE.fullmatch(value)) and any(ch.isdigit() for ch in value)


def _host_kind(host: str) -> str | None:
    """Return ``"short"``, ``"full"`` for YouTube hosts, else ``None``."""
    h = host.lower().rstrip(".")
    for prefix in ("www.", "m.", "music."):
        if h.startswith(prefix):
            h = h[len(prefix) :]
    if h == _SHORT_HOST:
        return "short"
    if h in _YOUTUBE_HOSTS:
        return "full"
    return None


def _video_id(parts, kind: str) -> str | None:
    segments = [seg for seg in parts.path.split("/") if seg]

    if kind == "short":
        candidate = segments[0] if segments else None
    else:
        candidate = None
        if segments and segments[0] in _VIDEO_PATH_PREFIXES and len(segments) > 1:
            candidate = segments[1]
        elif segments and segments[0] == "watch":
            candidate = dict(parse_qsl(parts.query)).get("v")

    if candidate and _VIDEO_ID_RE.fullmatch(candidate):
        return candidate
    return None


def _start_time(query: str) -> str | None:
    for name, value in parse_qsl(query, keep_blank_values=True):
        if name in ("t", "start") and _is_start_time(value):
            return value.strip()
    return None


def _canonical_video(video_id: str, query: str) -> str:
    params: list[tuple[str, str]] = [("v", video_id)]
    start = _start_time(query)
    if start is not None:
        params.append(("t", start))
    return urlunsplit(("https", "www.youtube.com", "/watch", urlencode(params), ""))


def _filter_query(query: str, drop: set[str]) -> str:
    kept = [
        (name, value)
        for name, value in parse_qsl(query, keep_blank_values=True)
        if name not in drop and not name.startswith("utm_")
    ]
    return urlencode(kept)


def _normalise_youtube(parts, kind: str) -> str:
    video_id = _video_id(parts, kind)
    if video_id is not None:
        return _canonical_video(video_id, parts.query)

    segments = [seg for seg in parts.path.split("/") if seg]
    if segments and segments[0] == "playlist":
        # A playlist link keeps its list (and index) parameter.
        query = _filter_query(parts.query, _TRACKING_PARAMS)
        return urlunsplit(("https", "www.youtube.com", "/playlist", query, ""))

    path = parts.path or "/"
    query = _filter_query(parts.query, _TRACKING_PARAMS)
    return urlunsplit(("https", "www.youtube.com", path, query, ""))


def normalize_url(url: str) -> str:
    """Return the canonical form of *url* used for queue dedupe.

    Raises ``ValueError`` for empty input or input without a host.
    """
    parts = _split(url)
    host = (parts.hostname or "").lower()
    kind = _host_kind(host)
    if kind is not None:
        return _normalise_youtube(parts, kind)

    scheme = parts.scheme.lower()
    netloc = host
    is_default_port = (scheme == "http" and parts.port == 80) or (
        scheme == "https" and parts.port == 443
    )
    if parts.port is not None and not is_default_port:
        netloc = f"{host}:{parts.port}"
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo += f":{parts.password}"
        netloc = f"{userinfo}@{netloc}"

    query = _filter_query(parts.query, set())
    return urlunsplit((scheme, netloc, parts.path, query, ""))


def video_key(url: str) -> str | None:
    """Return ``"youtube:<ID>"`` for a YouTube video, else ``None``."""
    parts = _split(url)
    kind = _host_kind((parts.hostname or "").lower())
    if kind is None:
        return None
    video_id = _video_id(parts, kind)
    if video_id is None:
        return None
    return f"youtube:{video_id}"
