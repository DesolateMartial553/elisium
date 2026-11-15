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


# -- brief 8A: Instagram and TikTok --------------------------------------
IG_SHORTCODE = "CabcdEFghij"
TIKTOK_ID = "7106594312292453675"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.instagram.com/p/{IG_SHORTCODE}/",
        f"https://instagram.com/p/{IG_SHORTCODE}/?igsh=abc123",
        f"https://m.instagram.com/p/{IG_SHORTCODE}/?igshid=xyz&utm_source=ig_web",
        f"https://www.instagram.com/p/{IG_SHORTCODE}/?igsh=abc&igshid=def",
    ],
)
def test_instagram_post_forms_share_one_key(url: str) -> None:
    assert video_key(url) == f"instagram:{IG_SHORTCODE}"
    assert normalize_url(url) == f"https://instagram.com/p/{IG_SHORTCODE}/"


def test_instagram_reel_and_tv_get_keys() -> None:
    for path in ("reel", "tv"):
        url = f"https://www.instagram.com/{path}/{IG_SHORTCODE}/"
        assert video_key(url) == f"instagram:{IG_SHORTCODE}"
    assert normalize_url(f"https://www.instagram.com/reel/{IG_SHORTCODE}/?igsh=x") == (
        f"https://instagram.com/reel/{IG_SHORTCODE}/"
    )


def test_instagram_img_index_is_kept() -> None:
    assert (
        normalize_url(f"https://www.instagram.com/p/{IG_SHORTCODE}/?img_index=2&igsh=x")
        == f"https://instagram.com/p/{IG_SHORTCODE}/?img_index=2"
    )


def test_instagram_story_key_needs_an_id() -> None:
    url = "https://www.instagram.com/stories/tiktok/3211234567890123456/"
    assert video_key(url) == "instagram:story:tiktok:3211234567890123456"
    assert video_key("https://www.instagram.com/stories/tiktok/") is None


@pytest.mark.parametrize(
    ("url", "normalised"),
    [
        (
            "https://www.instagram.com/stories/highlights/17912345678901234/",
            "https://instagram.com/stories/highlights/17912345678901234/",
        ),
        (
            "https://instagram.com/stories/highlights/17912345678901234",
            "https://instagram.com/stories/highlights/17912345678901234",
        ),
        (
            "https://m.instagram.com/stories/highlights/17912345678901234/?igsh=abc",
            "https://instagram.com/stories/highlights/17912345678901234/",
        ),
        (
            "https://www.instagram.com/stories/highlights/17912345678901234/"
            "?utm_source=ig_web&igshid=xyz",
            "https://instagram.com/stories/highlights/17912345678901234/",
        ),
    ],
)
def test_instagram_highlight_key(url: str, normalised: str) -> None:
    assert video_key(url) == "instagram:highlight:17912345678901234"
    # The tray still normalises like every other Instagram link.
    assert normalize_url(url) == normalised


def test_instagram_highlight_needs_a_numeric_id() -> None:
    assert video_key("https://www.instagram.com/stories/highlights/") is None
    assert video_key("https://www.instagram.com/stories/highlights/notanid/") is None


def test_instagram_profile_has_no_key() -> None:
    assert video_key("https://www.instagram.com/tiktok/") is None


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.tiktok.com/@tiktok/video/{TIKTOK_ID}",
        f"https://m.tiktok.com/@tiktok/video/{TIKTOK_ID}?is_from_webapp=1&sender_device=pc",
        f"https://www.tiktok.com/@tiktok/video/{TIKTOK_ID}?_t=8abc&_r=1"
        "&share_app_id=1340&share_link_id=x&share_item_id=y&u_code=z&timestamp=1"
        "&user_id=9&tt_from=copy&source=h5_m&lang=en&region=GB&checksum=q"
        "&refer=web&sender_web_id=w&utm_source=copy",
    ],
)
def test_tiktok_forms_share_one_key(url: str) -> None:
    assert video_key(url) == f"tiktok:{TIKTOK_ID}"
    assert normalize_url(url) == f"https://tiktok.com/@tiktok/video/{TIKTOK_ID}"


@pytest.mark.parametrize(
    ("url", "normalised"),
    [
        ("https://vm.tiktok.com/ZMabc123/", "https://vm.tiktok.com/ZMabc123/"),
        ("https://vm.tiktok.com/ZMabc123", "https://vm.tiktok.com/ZMabc123"),
        (
            "https://vm.tiktok.com/ZMabc123/?_t=1&share_app_id=1340",
            "https://vm.tiktok.com/ZMabc123/",
        ),
        (
            "https://vt.tiktok.com/ZMabc123/?is_from_webapp=1&sender_device=pc",
            "https://vt.tiktok.com/ZMabc123/",
        ),
    ],
)
def test_tiktok_short_link_keeps_one_key_without_redirects(
    url: str, normalised: str
) -> None:
    assert video_key(url) == "tiktok:short:ZMabc123"
    # Junk still goes, and the short host is never resolved to a full URL.
    assert normalize_url(url) == normalised


def test_tiktok_short_link_variants() -> None:
    assert normalize_url("https://vm.tiktok.com/ZMabc123/?_t=1&share_app_id=1340") == (
        "https://vm.tiktok.com/ZMabc123/"
    )
    assert normalize_url("https://vt.tiktok.com/ZSabc123/") == (
        "https://vt.tiktok.com/ZSabc123/"
    )
    assert video_key("https://vt.tiktok.com/ZSabc123/") == "tiktok:short:ZSabc123"
    # Two different short hosts, two different videos, two keys.
    assert video_key("https://vm.tiktok.com/ZMabc123/") != video_key(
        "https://vt.tiktok.com/ZSabc123/"
    )
    # No code, no key; a full URL is not a short link.
    assert video_key("https://vm.tiktok.com/") is None
    assert video_key(f"https://www.tiktok.com/@tiktok/video/{TIKTOK_ID}") == (
        f"tiktok:{TIKTOK_ID}"
    )



def test_youtube_behaviour_is_unchanged_next_to_the_new_sites() -> None:
    assert video_key(f"https://youtu.be/{VIDEO_ID}") == f"youtube:{VIDEO_ID}"
    assert normalize_url(f"https://youtu.be/{VIDEO_ID}") == CANONICAL
