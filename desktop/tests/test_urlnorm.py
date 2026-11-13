from __future__ import annotations

import pytest

from elisium_downloader.engine.urlnorm import normalize_url, video_key

VIDEO_ID = "dQw4w9WgXcQ"
CANONICAL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


@pytest.mark.parametrize(
    "url",
    [
        f"https://youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"http://youtube.com/watch?v={VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://music.youtube.com/watch?v={VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?si=tracking123",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&feature=share&pp=abc",
    ],
)
def test_all_youtube_forms_normalise_and_share_one_key(url: str) -> None:
    assert normalize_url(url) == CANONICAL
    assert video_key(url) == f"youtube:{VIDEO_ID}"


def test_tracking_params_are_stripped_from_a_single_video() -> None:
    url = (
        f"https://www.youtube.com/watch?v={VIDEO_ID}"
        "&si=abc&feature=share&pp=xyz&utm_source=newsletter&utm_medium=email"
        "&list=PL123&index=4"
    )
    assert normalize_url(url) == CANONICAL


def test_start_time_is_kept_in_normalised_form() -> None:
    assert normalize_url(f"https://youtu.be/{VIDEO_ID}?t=90") == f"{CANONICAL}&t=90"
    assert (
        normalize_url(f"https://www.youtube.com/watch?v={VIDEO_ID}&t=1m30s")
        == f"{CANONICAL}&t=1m30s"
    )
    assert (
        normalize_url(f"https://www.youtube.com/watch?v={VIDEO_ID}&start=45")
        == f"{CANONICAL}&t=45"
    )


def test_non_time_t_is_dropped() -> None:
    assert normalize_url(f"https://youtu.be/{VIDEO_ID}?t=notatime") == CANONICAL


def test_playlist_url_keeps_list() -> None:
    assert (
        normalize_url("https://www.youtube.com/playlist?list=PL123&si=abc&utm_source=x")
        == "https://www.youtube.com/playlist?list=PL123"
    )
    assert (
        normalize_url("https://www.youtube.com/playlist?list=PL123&index=2")
        == "https://www.youtube.com/playlist?list=PL123&index=2"
    )


def test_playlist_link_has_no_video_key() -> None:
    assert video_key("https://www.youtube.com/playlist?list=PL123") is None


def test_other_sites_lowercase_scheme_and_host_and_strip_fragment_and_utm() -> None:
    assert (
        normalize_url("HTTPS://Example.COM/Some/Path?utm_source=x&a=1&b=2#section")
        == "https://example.com/Some/Path?a=1&b=2"
    )


def test_other_sites_have_no_video_key() -> None:
    assert video_key("https://vimeo.com/12345") is None


def test_other_sites_only_drop_utm_params() -> None:
    assert (
        normalize_url("https://example.com/watch?si=keep&feature=keep&utm_source=x")
        == "https://example.com/watch?si=keep&feature=keep"
    )


@pytest.mark.parametrize("url", ["", "   ", "not a url", "https://", "ftp://example.com/x"])
def test_invalid_input_raises_value_error(url: str) -> None:
    with pytest.raises(ValueError):
        normalize_url(url)
    with pytest.raises(ValueError):
        video_key(url)
