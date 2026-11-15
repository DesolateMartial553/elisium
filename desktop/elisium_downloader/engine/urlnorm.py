"""URL normalisation and dedupe keys.

Rules come from ``core-spec/SPEC.md`` (layer 3 of the dedupe plan):

* every YouTube video URL form collapses to one canonical watch URL;
* tracking parameters are dropped;
* a playlist URL keeps its ``list`` parameter;
* Instagram and TikTok links lose their share-link junk, so the same video
  from the app, the mobile site and the web site is one queue item;
* other sites keep everything except the fragment and ``utm_*`` parameters.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = ["normalize_url", "site_kind", "video_key"]

_YOUTUBE_HOSTS = {"youtube.com", "youtube-nocookie.com"}
_SHORT_HOST = "youtu.be"
_VIDEO_PATH_PREFIXES = ("shorts", "embed", "live", "v")
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_TIME_RE = re.compile(r"^(?:\d+h)?(?:\d+m)?(?:\d+s)?$")

_INSTAGRAM_HOST = "instagram.com"
# The short hosts are their own domain, so they are matched before the suffix.
_TIKTOK_HOSTS = {"tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
# Share links: the code alone identifies one video (never resolved, no network).
_TIKTOK_SHORT_HOSTS = {"vm.tiktok.com", "vt.tiktok.com"}

# Dropped on every site / every YouTube URL.
_TRACKING_PARAMS = {"si", "feature", "pp"}
# Dropped only when the URL points at a single video (not a playlist).
_VIDEO_ONLY_DROP = {"list", "index"}

# Share-link parameters added by the Instagram app / web share sheet.
# ``img_index`` is deliberately kept: it selects one image of a carousel post.
_INSTAGRAM_DROP = {"igsh", "igshid"}
# Share-link parameters added by the TikTok app and web share sheet.
_TIKTOK_DROP = {
    "_t",
    "_r",
    "is_from_webapp",
    "sender_device",
    "sender_web_id",
    "share_app_id",
    "share_link_id",
    "share_item_id",
    "source",
    "checksum",
    "refer",
    "region",
    "lang",
    "u_code",
    "timestamp",
    "user_id",
    "tt_from",
}

# Instagram post paths that carry a shortcode, per the brief.
_INSTAGRAM_POST_PREFIXES = ("p", "reel", "tv")


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


def _bare_host(host: str) -> str:
    """Lower-case *host* without a leading ``www.`` or ``m.``."""
    h = host.lower().rstrip(".")
    for prefix in ("www.", "m."):
        if h.startswith(prefix):
            h = h[len(prefix) :]
    return h


def _site_kind(host: str) -> str | None:
    """``"instagram"`` / ``"tiktok"`` for those sites, else ``None``."""
    h = _bare_host(host)
    if h == _INSTAGRAM_HOST:
        return "instagram"
    if h in _TIKTOK_HOSTS:
        return "tiktok"
    return None


def _is_start_time(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    if value.isdigit():
        return True
    return bool(_TIME_RE.fullmatch(value)) and any(ch.isdigit() for ch in value)


def _host_kind(host: str) -> str | None:
    """Return ``"short"``, ``"full"`` for YouTube hosts, else ``None``."""
    h = _bare_host(host)
    for prefix in ("music.",):
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


def _normalise_site(parts, site: str) -> str:
    """Instagram/TikTok: lower-case host without ``www.``/``m.``, junk dropped."""
    drop = _INSTAGRAM_DROP if site == "instagram" else _TIKTOK_DROP
    query = _filter_query(parts.query, drop)
    return urlunsplit(
        (parts.scheme.lower(), _bare_host(parts.hostname or ""), parts.path, query, "")
    )


def _instagram_key(parts) -> str | None:
    segments = [seg for seg in parts.path.split("/") if seg]
    if len(segments) >= 2 and segments[0] in _INSTAGRAM_POST_PREFIXES:
        shortcode = segments[1]
        if _VIDEO_ID_RE.fullmatch(shortcode):
            return f"instagram:{shortcode}"
        return None
    if len(segments) >= 3 and segments[0] == "stories" and segments[1] == "highlights":
        # One highlight (the tray itself is classified elsewhere, unchanged).
        highlight_id = segments[2]
        if highlight_id.isdigit():
            return f"instagram:highlight:{highlight_id}"
        return None
    if (
        len(segments) >= 3
        and segments[0] == "stories"
        and segments[1] != "highlights"
        and segments[2].isdigit()
    ):
        # One story (a story tray has no id and is queued item by item).
        return f"instagram:story:{segments[1]}:{segments[2]}"
    return None


def _tiktok_key(parts, host: str) -> str | None:
    segments = [seg for seg in parts.path.split("/") if seg]
    if _bare_host(host) in _TIKTOK_SHORT_HOSTS:
        # Short links are never resolved (no network): the code is the identity.
        if segments and _VIDEO_ID_RE.fullmatch(segments[0]):
            return f"tiktok:short:{segments[0]}"
        return None
    if len(segments) >= 3 and segments[0].startswith("@") and segments[1] == "video":
        video_id = segments[2]
        if video_id.isdigit():
            return f"tiktok:{video_id}"
    return None


def normalize_url(url: str) -> str:
    """Return the canonical form of *url* used for queue dedupe.

    Raises ``ValueError`` for empty input or input without a host.
    """
    parts = _split(url)
    host = (parts.hostname or "").lower()
    kind = _host_kind(host)
    if kind is not None:
        return _normalise_youtube(parts, kind)
    site = _site_kind(host)
    if site is not None:
        return _normalise_site(parts, site)

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


def site_kind(url: str) -> str | None:
    """``"instagram"`` / ``"tiktok"`` for a URL on those sites, else ``None``.

    Never raises: an unparseable URL has no known site. Same host rules as
    :func:`normalize_url`, so callers can pick wording per site.
    """
    try:
        parts = _split(url)
    except (ValueError, TypeError):
        return None
    return _site_kind(parts.hostname or "")


def video_key(url: str) -> str | None:
    """Return ``"youtube:<ID>"``, ``"instagram:..."``, ``"tiktok:<id>"`` or ``None``."""
    parts = _split(url)
    host = (parts.hostname or "").lower()
    kind = _host_kind(host)
    if kind is not None:
        video_id = _video_id(parts, kind)
        if video_id is None:
            return None
        return f"youtube:{video_id}"
    site = _site_kind(host)
    if site == "instagram":
        return _instagram_key(parts)
    if site == "tiktok":
        return _tiktok_key(parts, host)
    return None
