from __future__ import annotations

import pytest

from elisium_downloader.engine import formats
from elisium_downloader.engine.formats import (
    FormatRow,
    human_duration,
    human_size,
    parse_range,
    playlist_entries,
    selector_for,
    summary,
)

INFO = {
    "formats": [
        {"format_id": "sb0", "ext": "mhtml", "format_note": "storyboard", "vcodec": "none",
         "acodec": "none", "height": 90, "width": 160},
        {"format_id": "139", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.5", "abr": 48.5,
         "tbr": 49, "filesize": 1_000_000},
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129.5,
         "tbr": 130, "filesize_approx": 3_500_000, "format_note": "medium"},
        {"format_id": "137", "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none",
         "width": 1920, "height": 1080, "fps": 30, "tbr": 4000, "filesize": 80_000_000},
        {"format_id": "136", "ext": "mp4", "vcodec": "avc1.4d401f", "acodec": "none",
         "width": 1280, "height": 720, "fps": 60, "vbr": 2000},
        {"format_id": "18", "ext": "mp4", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2",
         "width": 640, "height": 360, "fps": 30, "tbr": 500},
        {"format_id": "nothing", "ext": "x", "vcodec": "none", "acodec": "none"},
        {"ext": "mp4", "vcodec": "avc1", "acodec": "none", "height": 10},  # no id
    ]
}


def test_format_rows_kinds_sorting_and_skips() -> None:
    rows = formats.format_rows(INFO)
    assert [r.format_id for r in rows] == ["18", "137", "136", "140", "139"]
    by_id = {r.format_id: r for r in rows}
    assert by_id["18"].kind == "video+audio"
    assert by_id["137"].kind == "video" and by_id["137"].resolution == "1920x1080"
    assert by_id["140"].kind == "audio" and by_id["140"].resolution == "audio only"
    assert by_id["140"].note == "medium"
    assert not any(r.format_id == "sb0" or r.ext == "mhtml" for r in rows)


def test_format_rows_sizes_and_bitrate_fallbacks() -> None:
    by_id = {r.format_id: r for r in formats.format_rows(INFO)}
    assert by_id["137"].size_bytes == 80_000_000
    assert by_id["140"].size_bytes == 3_500_000  # filesize_approx
    assert by_id["136"].size_bytes is None  # missing size stays None
    assert by_id["136"].bitrate == 2000  # from vbr
    assert by_id["18"].fps == 30


def test_format_rows_tolerates_garbage() -> None:
    assert formats.format_rows({}) == []
    assert formats.format_rows({"formats": None}) == []
    assert formats.format_rows({"formats": ["x", None, 3]}) == []


def test_format_rows_without_codec_keys() -> None:
    rows = formats.format_rows(
        {"formats": [{"format_id": "a", "ext": "mp3"}, {"format_id": "b", "ext": "mp4", "height": 480}]}
    )
    kinds = {r.format_id: r.kind for r in rows}
    assert kinds == {"a": "audio", "b": "video+audio"}


@pytest.mark.parametrize(
    "video,audio,expected",
    [("137", "140", "137+140"), ("137", None, "137"), (None, "140", "140"),
     (" 18 ", "", "18"), ("", " 140", "140")],
)
def test_selector_for(video, audio, expected) -> None:
    assert selector_for(video, audio) == expected


@pytest.mark.parametrize("video,audio", [(None, None), ("", ""), ("  ", None), ("1+2", None), (None, "a b")])
def test_selector_for_errors(video, audio) -> None:
    with pytest.raises(ValueError):
        selector_for(video, audio)


def test_human_helpers() -> None:
    assert human_size(None) == "unknown"
    assert human_size(512) == "512 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"
    assert human_duration(None) == ""
    assert human_duration(65) == "1:05"
    assert human_duration(3725) == "1:02:05"


def test_summary() -> None:
    s = summary({"title": " T ", "uploader": "U", "duration": 61.4,
                 "thumbnail": "https://i/x.jpg", "webpage_url": "https://w"})
    assert (s.title, s.uploader, s.duration, s.thumbnail, s.webpage_url) == (
        "T", "U", 61, "https://i/x.jpg", "https://w")
    empty = summary({})
    assert empty.title == "Untitled video" and empty.duration is None and empty.thumbnail is None
    thumbs = summary({"channel": "C", "thumbnails": [{"url": "a"}, {"url": "b"}]})
    assert thumbs.uploader == "C" and thumbs.thumbnail == "b"


def test_playlist_entries_none_and_flat() -> None:
    info = {
        "entries": [
            {"id": "aaa", "title": "One", "url": "https://www.youtube.com/watch?v=aaa", "duration": 90},
            None,
            {"id": "ccc", "ie_key": "Youtube", "url": "ccc"},  # flat, bare id
            {"id": "ddd", "title": "[Private video]", "url": "https://www.youtube.com/watch?v=ddd"},
            {"title": "No url"},
            {"url": "https://vimeo.com/9", "ie_key": "Vimeo"},
        ]
    }
    entries = playlist_entries(info)
    assert [e.index for e in entries] == [1, 2, 3, 4, 5, 6]
    assert entries[0].available and entries[0].duration == 90 and entries[0].title == "One"
    assert not entries[1].available and entries[1].url is None
    assert entries[2].url == "https://www.youtube.com/watch?v=ccc" and entries[2].available
    assert not entries[3].available
    assert not entries[4].available
    assert entries[5].url == "https://vimeo.com/9" and entries[5].title == "https://vimeo.com/9"
    assert playlist_entries({}) == []


@pytest.mark.parametrize(
    "text,total,expected",
    [("", 10, []), ("3-5", 10, [3, 4, 5]), ("1,4,9-12", 12, [1, 4, 9, 10, 11, 12]),
     (" 2 , 2 ,1 ", 5, [1, 2]), ("7", 7, [7])],
)
def test_parse_range(text, total, expected) -> None:
    assert parse_range(text, total) == expected


@pytest.mark.parametrize("text", ["abc", "3-", "-3", "0", "1,,2", "5-3", "1-99", "1.5", "2-x"])
def test_parse_range_errors_are_plain(text) -> None:
    with pytest.raises(ValueError) as err:
        parse_range(text, 10)
    assert str(err.value) and "Traceback" not in str(err.value)


def test_formatrow_is_frozen() -> None:
    row = formats.format_rows(INFO)[0]
    assert isinstance(row, FormatRow)
    with pytest.raises(Exception):
        row.ext = "x"  # type: ignore[misc]
