"""Turn raw yt-dlp output into a plain-language error.

The table is the one in ``core-spec/SPEC.md``: case-insensitive substring
match, first match wins, fallback is "Download failed.".

Two rows name Instagram because that is where they come from. :func:`explain`
takes the item's URL and whether a cookie source is configured, so the same
raw text gets the right wording for other sites and an expired Instagram
session is reported as such (brief 9A). Both arguments are optional: calling
``explain(raw)`` keeps the old behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .urlnorm import site_kind

__all__ = [
    "ErrorInfo",
    "GALLERY_DL_MISSING",
    "NO_MEDIA_FILES",
    "PRIVATE_ACCOUNT",
    "STORY_EXPIRED",
    "apply_context",
    "explain",
    "explain_gallery",
]


@dataclass(frozen=True)
class ErrorInfo:
    """A user-facing explanation of a failed download."""

    message: str
    fix: str
    code: str


_FALLBACK = ErrorInfo("Download failed.", "See Details", "unknown")

# Instagram wording (used when there is no URL to judge, or it is Instagram).
_IG_SIGNED_IN = ErrorInfo(
    "Instagram needs you signed in.",
    "Choose a browser in Settings > Accounts",
    "login_required",
)
# The site wants a sign-in but is not Instagram: same code, no site name.
_SIGNED_IN = ErrorInfo(
    "The site wants you to be signed in.",
    _IG_SIGNED_IN.fix,
    "login_required",
)
_IG_RATE = ErrorInfo(
    "Instagram is limiting requests. Wait a few minutes and try again.",
    "Wait a few minutes and try again",
    "rate_limited",
)
_RATE_LIMITED = ErrorInfo(
    "The site is limiting requests. Wait a few minutes and try again.",
    _IG_RATE.fix,
    "rate_limited",
)
# A cookie source is configured and Instagram still asked for a sign-in: it
# is the saved session that has gone stale, not the link.
_SESSION_EXPIRED = ErrorInfo(
    "Your Instagram sign-in has expired.",
    "Choose your browser again in Settings > Accounts",
    "session_expired",
)

# Order matters: first match wins (same order as the spec table).
_TABLE: tuple[tuple[tuple[str, ...], ErrorInfo], ...] = (
    (
        ("sign in to confirm", "not a bot"),
        ErrorInfo(
            "The site wants you to be signed in.",
            "Import cookies",
            "sign_in_required",
        ),
    ),
    (
        # Instagram stories and private posts print this without cookies.
        (
            "you need to log in to access this content",
            "log in to view this content",
            "you must be logged in to view",
            "instagram needs you signed in",
        ),
        _IG_SIGNED_IN,
    ),
    (
        # Instagram's own pacing message, not a plain HTTP 429.
        (
            "please wait a few minutes",
            "instagram is limiting",
            "request limit reached",
        ),
        _IG_RATE,
    ),
    (
        # A post with no video: yt-dlp's own wording (extractor/instagram.py,
        # "raise_no_formats" and the empty Polaris response).
        (
            "there is no video in this post",
            "instagram sent an empty media response",
        ),
        ErrorInfo(
            "This post has no video to download.",
            "Check the link",
            "no_media",
        ),
    ),
    (
        # yt-dlp could not open the browser's cookie store.
        (
            "could not find cookies database",
            "failed to decrypt",
            "could not copy chrome cookie database",
            "could not find firefox cookies database",
        ),
        ErrorInfo(
            "Elisium could not read that browser's cookies. "
            "Close the browser or pick another.",
            "Close the browser, or choose another browser in Settings",
            "cookies_unreadable",
        ),
    ),
    (
        ("video unavailable", "private video"),
        ErrorInfo(
            "This video is not available.", "Check the link", "video_unavailable"
        ),
    ),
    (
        ("requested format is not available",),
        ErrorInfo(
            "That quality isn't offered for this video.",
            "Pick another format",
            "format_unavailable",
        ),
    ),
    (
        ("http error 401",),
        ErrorInfo(
            "The site refused to let Elisium in.",
            "Sign in, then try again",
            "http_401",
        ),
    ),
    (
        ("http error 403",),
        ErrorInfo(
            "The site refused the download.",
            "Update yt-dlp, or import cookies",
            "http_403",
        ),
    ),
    (
        ("http error 429",),
        ErrorInfo("Too many requests.", "Wait, lower concurrency", "http_429"),
    ),
    (
        ("unable to download", "timed out", "timeout", "connection"),
        ErrorInfo(
            "Network problem.",
            "Retry (auto-retry already ran)",
            "network",
        ),
    ),
    (
        ("ffmpeg not found", "ffmpeg is not installed"),
        ErrorInfo("ffmpeg is missing.", "Install ffmpeg", "ffmpeg_missing"),
    ),
)


# -- gallery-dl (the photo/story engine, brief 10B-1) -------------------------
GALLERY_DL_MISSING = ErrorInfo(
    "Photo downloads need gallery-dl. Install it: sudo pacman -S gallery-dl",
    "Install gallery-dl",
    "gallery_dl_missing",
)
STORY_EXPIRED = ErrorInfo(
    "This story has expired. Stories last 24 hours.",
    "Check the link",
    "story_expired",
)
PRIVATE_ACCOUNT = ErrorInfo(
    "This account is private. Follow it in your browser, then sign in here.",
    "Follow the account in your browser, then sign in in Settings > Accounts",
    "private_account",
)
# gallery-dl ran and found nothing it could save (no error text to go on).
NO_MEDIA_FILES = ErrorInfo(
    "There are no photos or videos to download here.",
    "Check the link",
    "no_media",
)

# gallery-dl's own wording. Needles are deliberately narrow ("404 not found",
# never a bare "not found") so they cannot catch rows of the yt-dlp table such
# as "ffmpeg not found". First match wins; checked before the yt-dlp table.
_GALLERY_TABLE: tuple[tuple[tuple[str, ...], ErrorInfo], ...] = (
    (("gallery-dl is missing",), GALLERY_DL_MISSING),
    (
        (
            "private account",
            "account is private",
            "user is private",
            "profile is private",
        ),
        PRIVATE_ACCOUNT,
    ),
    (
        (
            "story has expired",
            "stories have expired",
            "story expired",
            "story is no longer available",
        ),
        STORY_EXPIRED,
    ),
    (
        (
            "redirected to login",
            "login required",
            "authrequired",
            "authentication required",
            "requires authentication",
            "401 unauthorized",
            "you need to log in",
        ),
        _IG_SIGNED_IN,
    ),
    (
        (
            "429 too many requests",
            "http error 429",
            "rate limit",
            "please wait a few minutes",
        ),
        _IG_RATE,
    ),
    (
        ("404 not found", "http error 404", "notfounderror"),
        ErrorInfo(
            "This video is not available.", "Check the link", "video_unavailable"
        ),
    ),
)


def _instagram_only(url: str | None) -> bool:
    """True when a message may name Instagram: no URL, or an Instagram URL."""
    if url is None:
        return True
    if not isinstance(url, str) or not url.strip():
        return True
    return site_kind(url) == "instagram"


def apply_context(
    info: ErrorInfo, url: str | None = None, hasCookies: bool = False
) -> ErrorInfo:
    """Adjust *info* for the item's site and cookie state.

    * ``login_required`` / ``rate_limited`` on a non-Instagram URL use the
      generic wording (other sites are not Instagram).
    * ``login_required`` on Instagram with cookies configured is an expired
      session, not a missing sign-in.

    ``hasCookies`` keeps its camelCase spelling so both platforms use the same
    argument name. Everything else is returned unchanged.
    """
    if info.code == "login_required":
        if _instagram_only(url):
            return _SESSION_EXPIRED if hasCookies else info
        return _SIGNED_IN
    if info.code == "rate_limited":
        return info if _instagram_only(url) else _RATE_LIMITED
    return info


def explain(
    raw_log: str, url: str | None = None, hasCookies: bool = False
) -> ErrorInfo:
    """Map *raw_log* to an :class:`ErrorInfo` (never raises for plain text)."""
    text = (raw_log or "").lower()
    for needles, info in _TABLE:
        if any(needle in text for needle in needles):
            return apply_context(info, url, hasCookies)
    return _FALLBACK


def explain_gallery(
    raw_log: str, url: str | None = None, hasCookies: bool = False
) -> ErrorInfo:
    """Map gallery-dl output to an :class:`ErrorInfo` (never raises).

    gallery-dl's own wording is tried first, then the yt-dlp table (its
    "connection" / "timed out" rows still apply). The same context rules as
    :func:`explain` apply: a login wall with cookies configured is an expired
    session, and a non-Instagram site never names Instagram. A 404 on a single
    story link means the story is gone (stories last 24 hours).
    """
    text = (raw_log or "").lower()
    for needles, info in _GALLERY_TABLE:
        if any(needle in text for needle in needles):
            if info.code == "video_unavailable" and _is_story_item(url):
                return STORY_EXPIRED
            return apply_context(info, url, hasCookies)
    return explain(raw_log, url, hasCookies)


def _is_story_item(url: str | None) -> bool:
    """True for ``instagram.com/stories/<user>/<numeric id>``."""
    if not isinstance(url, str) or site_kind(url) != "instagram":
        return False
    try:
        segments = [s for s in urlsplit(url).path.split("/") if s]
    except ValueError:
        return False
    return (
        len(segments) >= 3
        and segments[0] == "stories"
        and segments[1] != "highlights"
        and segments[2].isdigit()
    )
