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
