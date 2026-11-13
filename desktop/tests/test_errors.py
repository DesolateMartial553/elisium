from __future__ import annotations

import pytest

from elisium_downloader.engine.errors import ErrorInfo, explain


@pytest.mark.parametrize(
    ("raw_log", "message", "fix"),
    [
        ("ERROR: Sign in to confirm you're not a bot", "The site wants you to be signed in.", "Import cookies"),
        ("ERROR: Video unavailable", "This video is not available.", "Check the link"),
        ("ERROR: Private video. Sign in", "This video is not available.", "Check the link"),
        (
            "ERROR: Requested format is not available",
            "That quality isn't offered for this video.",
            "Pick another format",
        ),
        ("ERROR: unable to download video data: HTTP Error 403: Forbidden", "The site refused the download.", "Update yt-dlp, or import cookies"),
        ("ERROR: HTTP Error 429: Too Many Requests", "Too many requests.", "Wait, lower concurrency"),
        ("ERROR: Unable to download webpage: timed out", "Network problem.", "Retry (auto-retry already ran)"),
        ("ERROR: ffmpeg not found. Please install or provide the path", "ffmpeg is missing.", "Install ffmpeg"),
        ("something completely unexpected", "Download failed.", "See Details"),
    ],
)
def test_error_table(raw_log: str, message: str, fix: str) -> None:
    info = explain(raw_log)
    assert isinstance(info, ErrorInfo)
    assert info.message == message
    assert info.fix == fix
    assert info.code


def test_matching_is_case_insensitive() -> None:
    assert explain("sign IN to CONFIRM").message == "The site wants you to be signed in."
    assert explain("PRIVATE VIDEO").message == "This video is not available."


def test_first_match_wins() -> None:
    # A 403 wrapped in "unable to download" must map to the 403 row, not network.
    info = explain("ERROR: unable to download video data: HTTP Error 403: Forbidden")
    assert info.code == "http_403"


def test_empty_log_falls_back() -> None:
    assert explain("").message == "Download failed."
