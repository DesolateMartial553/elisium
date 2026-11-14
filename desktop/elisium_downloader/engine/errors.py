"""Turn raw yt-dlp output into a plain-language error.

The table is the one in ``core-spec/SPEC.md``: case-insensitive substring
match, first match wins, fallback is "Download failed.".
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ErrorInfo", "explain"]


@dataclass(frozen=True)
class ErrorInfo:
    """A user-facing explanation of a failed download."""

    message: str
    fix: str
    code: str


_FALLBACK = ErrorInfo("Download failed.", "See Details", "unknown")

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
        ErrorInfo(
            "Instagram needs you signed in.",
            "Choose a browser in Settings > Accounts",
            "login_required",
        ),
    ),
    (
        # Instagram's own pacing message, not a plain HTTP 429.
        (
            "please wait a few minutes",
            "instagram is limiting",
            "request limit reached",
        ),
        ErrorInfo(
            "Instagram is limiting requests. Wait a few minutes and try again.",
            "Wait a few minutes and try again",
            "rate_limited",
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


def explain(raw_log: str) -> ErrorInfo:
    """Map *raw_log* to an :class:`ErrorInfo` (never raises for plain text)."""
    text = (raw_log or "").lower()
    for needles, info in _TABLE:
        if any(needle in text for needle in needles):
            return info
    return _FALLBACK
