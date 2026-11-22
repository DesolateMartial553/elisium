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
        (
            "ERROR: You need to log in to access this content. "
            "Use --cookies-from-browser or --cookies",
            "Instagram needs you signed in.",
            "Choose a browser in Settings > Accounts",
        ),
        (
            "ERROR: Please wait a few minutes before you try again.",
            "Instagram is limiting requests. Wait a few minutes and try again.",
            "Wait a few minutes and try again",
        ),
        (
            "ERROR: could not find firefox cookies database in "
            "/home/x/.mozilla/firefox",
            "Elisium could not read that browser's cookies. "
            "Close the browser or pick another.",
            "Close the browser, or choose another browser in Settings",
        ),
        (
            "ERROR: Failed to decrypt cookie for chrome",
            "Elisium could not read that browser's cookies. "
            "Close the browser or pick another.",
            "Close the browser, or choose another browser in Settings",
        ),
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


def test_new_site_codes() -> None:
    assert explain("You need to log in to access this content").code == "login_required"
    assert explain("Please wait a few minutes before you try again").code == "rate_limited"
    assert explain("could not find firefox cookies database").code == "cookies_unreadable"
    assert explain("Failed to decrypt cookie").code == "cookies_unreadable"
    # The old rows keep their codes.
    assert explain("Sign in to confirm you're not a bot").code == "sign_in_required"
    assert explain("HTTP Error 429").code == "http_429"


def test_empty_log_falls_back() -> None:
    assert explain("").message == "Download failed."


# -- brief 9A: context-aware explain ------------------------------------
IG_POST = "https://www.instagram.com/p/CabcdEFghij/"
YT_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
LOGIN_RAW = "ERROR: You need to log in to access this content. Use --cookies-from-browser or --cookies"


def test_http_401_row() -> None:
    info = explain("ERROR: unable to download video data: HTTP Error 401: Unauthorized")
    assert info.code == "http_401"
    assert info.message == "The site refused to let Elisium in."
    assert info.fix == "Sign in, then try again"
    # 401 does not swallow 403 or 429.
    assert explain("ERROR: HTTP Error 403: Forbidden").code == "http_403"
    assert explain("ERROR: HTTP Error 429: Too Many Requests").code == "http_429"


@pytest.mark.parametrize(
    "raw_log",
    [
        # raise_no_formats('There is no video in this post', expected=True)
        "ERROR: [Instagram] CabcdEFghij: There is no video in this post",
        # the empty Polaris response, verbatim from extractor/instagram.py
        "ERROR: Instagram sent an empty media response. Check if this post is "
        "accessible in your browser without being logged-in. If it is not, then "
        "use --cookies-from-browser or --cookies for the authentication.",
    ],
)
def test_no_media_row(raw_log: str) -> None:
    info = explain(raw_log)
    assert info.code == "no_media"
    assert info.message == "This post has no video to download."
    assert info.fix == "Check the link"


def test_no_media_does_not_shadow_login_required() -> None:
    # The empty-response message mentions cookies but is not a sign-in failure.
    info = explain(
        "ERROR: Instagram sent an empty media response. ... use --cookies-from-browser",
        IG_POST,
        True,
    )
    assert info.code == "no_media"
    assert explain(LOGIN_RAW, IG_POST, True).code == "session_expired"


def test_login_required_is_generic_for_other_sites() -> None:
    info = explain(LOGIN_RAW, YT_URL)
    assert info.code == "login_required"
    assert info.message == "The site wants you to be signed in."
    assert info.fix == "Choose a browser in Settings > Accounts"
    # An Instagram URL, and no URL at all, keep the Instagram wording.
    assert explain(LOGIN_RAW, IG_POST).message == "Instagram needs you signed in."
    assert explain(LOGIN_RAW).message == "Instagram needs you signed in."
    assert explain(LOGIN_RAW, None).message == "Instagram needs you signed in."


def test_rate_limited_is_generic_for_other_sites() -> None:
    raw = "ERROR: Please wait a few minutes before you try again."
    other = explain(raw, YT_URL)
    assert other.code == "rate_limited"
    assert other.message == (
        "The site is limiting requests. Wait a few minutes and try again."
    )
    assert other.fix == "Wait a few minutes and try again"
    assert explain(raw, IG_POST).message == (
        "Instagram is limiting requests. Wait a few minutes and try again."
    )
    assert explain(raw).message == (
        "Instagram is limiting requests. Wait a few minutes and try again."
    )


def test_expired_session_only_with_cookies_on_instagram() -> None:
    expired = explain(LOGIN_RAW, IG_POST, True)
    assert expired.code == "session_expired"
    assert expired.message == "Your Instagram sign-in has expired."
    assert expired.fix == "Choose your browser again in Settings > Accounts"
    # No cookies configured: it is still a plain "sign in" failure.
    assert explain(LOGIN_RAW, IG_POST, False).code == "login_required"
    assert explain(LOGIN_RAW, IG_POST).code == "login_required"
    # No URL: an Instagram-only row, so cookies still mean an expired session.
    assert explain(LOGIN_RAW, hasCookies=True).code == "session_expired"
    # Another site never gets "your Instagram sign-in has expired".
    other = explain(LOGIN_RAW, YT_URL, True)
    assert other.code == "login_required"
    assert "Instagram" not in other.message


@pytest.mark.parametrize("raw_log", [LOGIN_RAW, "HTTP Error 401", "HTTP Error 403", ""])
def test_default_arguments_keep_the_old_behaviour(raw_log: str) -> None:
    assert explain(raw_log) == explain(raw_log, None, False)
    assert explain(raw_log) == explain(raw_log, url=None, hasCookies=False)



# -- brief 10B-1: gallery-dl wording and the new rows ------------------------
from elisium_downloader.engine.errors import (  # noqa: E402
    GALLERY_DL_MISSING,
    NO_MEDIA_FILES,
    PRIVATE_ACCOUNT,
    STORY_EXPIRED,
    explain_gallery,
)

GDL_IG = "https://www.instagram.com/p/CAbc123xyz/"
GDL_STORY = "https://www.instagram.com/stories/someone/3303000000000000001/"
GDL_TRAY = "https://www.instagram.com/stories/someone/"
GDL_TT = "https://www.tiktok.com/@dancer/photo/7300000000000000001"


def test_new_rows_use_the_owners_wording() -> None:
    assert GALLERY_DL_MISSING.code == "gallery_dl_missing"
    assert GALLERY_DL_MISSING.message == (
        "Photo downloads need gallery-dl. Install it: sudo pacman -S gallery-dl"
    )
    assert STORY_EXPIRED.code == "story_expired"
    assert STORY_EXPIRED.message == "This story has expired. Stories last 24 hours."
    assert PRIVATE_ACCOUNT.code == "private_account"
    assert PRIVATE_ACCOUNT.message == (
        "This account is private. Follow it in your browser, then sign in here."
    )
    assert NO_MEDIA_FILES.code == "no_media"


def test_gallery_dl_missing_text_maps_to_the_row() -> None:
    assert explain_gallery("gallery-dl is missing") == GALLERY_DL_MISSING


@pytest.mark.parametrize(
    "raw",
    [
        "[instagram][warning] Redirected to login page",
        "[instagram][error] HttpError: '401 Unauthorized' for 'https://x'",
        "[instagram][error] AuthRequired: 'authenticated cookies'",
        "login required",
    ],
)
def test_gallery_login_walls_are_sign_in_rows(raw: str) -> None:
    info = explain_gallery(raw, GDL_IG, False)
    assert info.code == "login_required"
    assert info.message == "Instagram needs you signed in."
    # A configured cookie source means the saved session is the problem.
    assert explain_gallery(raw, GDL_IG, True).code == "session_expired"
    # Another site never names Instagram.
    other = explain_gallery(raw, GDL_TT, False)
    assert other.code == "login_required" and "Instagram" not in other.message
    assert explain_gallery(raw, GDL_TT, True).code == "login_required"


def test_gallery_rate_limit_rows() -> None:
    raw = "[instagram][error] HttpError: '429 Too Many Requests' for 'https://x'"
    ig = explain_gallery(raw, GDL_IG)
    assert ig.code == "rate_limited" and "Instagram" in ig.message
    other = explain_gallery(raw, GDL_TT)
    assert other.code == "rate_limited" and "Instagram" not in other.message
    assert explain_gallery("rate limit exceeded", GDL_IG).code == "rate_limited"


def test_gallery_not_found_is_unavailable_except_for_a_story() -> None:
    raw = "[instagram][error] HttpError: '404 Not Found' for 'https://x'"
    assert explain_gallery(raw, GDL_IG).code == "video_unavailable"
    assert explain_gallery(raw, GDL_TT).code == "video_unavailable"
    assert explain_gallery(raw, GDL_STORY) == STORY_EXPIRED
    # A tray URL is not "one story": a 404 there is still just unavailable.
    assert explain_gallery(raw, GDL_TRAY).code == "video_unavailable"


@pytest.mark.parametrize(
    "raw",
    [
        "[instagram][error] This account is private",
        "AuthorizationError: private account",
        "user is private",
    ],
)
def test_gallery_private_account(raw: str) -> None:
    assert explain_gallery(raw, GDL_IG, True) == PRIVATE_ACCOUNT
    assert explain_gallery(raw, GDL_IG, False) == PRIVATE_ACCOUNT


@pytest.mark.parametrize(
    "raw", ["this story has expired", "The stories have expired", "story expired"]
)
def test_gallery_story_expired(raw: str) -> None:
    assert explain_gallery(raw, GDL_TRAY) == STORY_EXPIRED


def test_gallery_falls_back_to_the_yt_dlp_table() -> None:
    assert explain_gallery("[downloader.http][error] Connection reset by peer").code == "network"
    assert explain_gallery("something odd").code == "unknown"
    assert explain_gallery("").code == "unknown"
    # Narrow needles: a bare "not found" never shadows the ffmpeg row.
    assert explain_gallery("ERROR: ffmpeg not found").code == "ffmpeg_missing"
    assert explain_gallery("ERROR: Video unavailable").code == "video_unavailable"


def test_explain_itself_is_unchanged_for_gallery_text() -> None:
    # The yt-dlp table does not learn gallery-dl wording (the queue picks the
    # right explainer per engine).
    assert explain("[instagram][error] This account is private").code == "unknown"
