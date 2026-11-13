from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from elisium_downloader.engine.history import TERMINAL_STATES, History

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
COLUMNS = [
    "id",
    "url",
    "video_key",
    "title",
    "state",
    "error_code",
    "error_message",
    "file_path",
    "created_at",
    "finished_at",
]


@pytest.fixture()
def history(tmp_path: Path) -> History:
    db = History(tmp_path / "history.sqlite")
    try:
        yield db
    finally:
        db.close()


# -- schema -------------------------------------------------------------
def test_schema_matches_the_spec(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite"
    History(path).close()
    with sqlite3.connect(path) as conn:
        rows = conn.execute("PRAGMA table_info(downloads)").fetchall()
    assert [row[1] for row in rows] == COLUMNS


def test_database_file_and_parent_directory_are_created(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "deeper" / "history.sqlite"
    db = History(path)
    db.close()
    assert path.is_file()


def test_rows_persist_across_reopening(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite"
    first = History(path)
    record_id = first.add(URL, video_key="youtube:dQw4w9WgXcQ", title="Never Gonna")
    first.close()

    second = History(path)
    try:
        row = second.get(record_id)
        assert row is not None
        assert row["title"] == "Never Gonna"
    finally:
        second.close()


# -- add / get ----------------------------------------------------------
def test_add_and_get_round_trip(history: History) -> None:
    record_id = history.add(
        URL, video_key="youtube:dQw4w9WgXcQ", title="Never Gonna Give You Up"
    )
    row = history.get(record_id)
    assert row is not None
    assert row["id"] == record_id
    assert row["url"] == URL
    assert row["video_key"] == "youtube:dQw4w9WgXcQ"
    assert row["title"] == "Never Gonna Give You Up"
    assert row["state"] == "queued"
    assert row["error_code"] is None
    assert row["error_message"] is None
    assert row["file_path"] is None
    assert row["finished_at"] is None
    assert row["created_at"]


def test_get_unknown_id_returns_none(history: History) -> None:
    assert history.get(999) is None


def test_added_quietly_row_gets_an_id(history: History) -> None:
    first = history.add(URL)
    second = history.add(URL)
    assert second > first


def test_add_blank_url_raises(history: History) -> None:
    with pytest.raises(ValueError):
        history.add("   ")


def test_unknown_state_raises(history: History) -> None:
    with pytest.raises(ValueError):
        history.add(URL, state="downlaoding")
    record_id = history.add(URL)
    with pytest.raises(ValueError):
        history.update_state(record_id, "nonsense")
    assert history.get(record_id)["state"] == "queued"


# -- state transitions --------------------------------------------------
def test_update_state_walks_the_queue(history: History) -> None:
    record_id = history.add(URL)
    for state in ("probing", "downloading", "merging", "converting", "done"):
        assert history.update_state(record_id, state) is True
        row = history.get(record_id)
        assert row["state"] == state
        if state in TERMINAL_STATES:
            assert row["finished_at"]
        else:
            assert row["finished_at"] is None


def test_finished_at_is_stamped_only_once(history: History) -> None:
    record_id = history.add(URL)
    history.update_state(record_id, "done")
    stamp = history.get(record_id)["finished_at"]
    history.update_state(record_id, "done")
    assert history.get(record_id)["finished_at"] == stamp


def test_update_state_unknown_id_returns_false(history: History) -> None:
    assert history.update_state(999, "done") is False


def test_update_state_records_error_and_file_path(history: History) -> None:
    record_id = history.add(URL)
    history.update_state(
        record_id,
        "failed",
        error_code="http_429",
        error_message="Too many requests.",
    )
    row = history.get(record_id)
    assert row["state"] == "failed"
    assert row["error_code"] == "http_429"
    assert row["error_message"] == "Too many requests."
    assert row["finished_at"]

    history.update_state(record_id, "queued")
    row = history.get(record_id)
    assert row["finished_at"] is None
    # Unspecified fields are left alone.
    assert row["error_code"] == "http_429"

    history.update_state(
        record_id, "done", file_path="/home/user/Downloads/x.mp4", clear_error=True
    )
    row = history.get(record_id)
    assert row["file_path"] == "/home/user/Downloads/x.mp4"
    assert row["error_code"] is None
    assert row["error_message"] is None


def test_paused_is_not_terminal(history: History) -> None:
    record_id = history.add(URL)
    history.update_state(record_id, "paused")
    assert history.get(record_id)["finished_at"] is None


# -- search -------------------------------------------------------------
def test_search_matches_title_url_and_video_key(history: History) -> None:
    title_id = history.add(URL, title="Lo-fi beats to relax to")
    url_id = history.add("https://vimeo.com/12345", title="Something else")
    key_id = history.add(
        "https://example.com/x", video_key="youtube:AbCdEf", title="Third"
    )

    assert [row["id"] for row in history.search("lo-fi")] == [title_id]
    assert [row["id"] for row in history.search("vimeo")] == [url_id]
    assert [row["id"] for row in history.search("abcdef")] == [key_id]


def test_search_is_case_insensitive(history: History) -> None:
    record_id = history.add(URL, title="Never Gonna Give You Up")
    assert [row["id"] for row in history.search("NEVER gonna")] == [record_id]


def test_search_blank_text_returns_nothing(history: History) -> None:
    history.add(URL, title="Anything")
    assert history.search("") == []
    assert history.search("   ") == []


def test_search_returns_newest_first_and_respects_limit(history: History) -> None:
    ids = [history.add(URL, title=f"clip {index}") for index in range(5)]
    found = history.search("clip")
    assert [row["id"] for row in found] == list(reversed(ids))
    assert [row["id"] for row in history.search("clip", limit=2)] == [
        ids[4],
        ids[3],
    ]
    assert history.search("clip", limit=0) == []


# -- injection and wildcard safety --------------------------------------
def test_title_with_quotes_round_trips(history: History) -> None:
    nasty = "Robert'); DROP TABLE downloads;--"
    record_id = history.add(URL, title=nasty)
    assert history.get(record_id)["title"] == nasty
    assert [row["id"] for row in history.search("Robert")] == [record_id]
    # The table is still there and still works.
    assert history.recent(limit=1)[0]["id"] == record_id
    assert history.delete(record_id) is True


@pytest.mark.parametrize(
    "query",
    [
        "' OR 1=1 --",
        '" OR "1"="1',
        "'; DELETE FROM downloads; --",
        "%' OR '%'='",
    ],
)
def test_injection_style_searches_match_nothing(
    history: History, query: str
) -> None:
    record_id = history.add(URL, title="Never Gonna Give You Up")
    assert history.search(query) == []
    assert history.recent(limit=10)[0]["id"] == record_id


def test_percent_and_underscore_are_literal_in_search(history: History) -> None:
    percent_id = history.add(URL, title="100% honest review")
    other_id = history.add(URL, title="100x honest review")
    underscore_id = history.add(URL, title="file_name here")
    space_id = history.add(URL, title="file name here")

    assert [row["id"] for row in history.search("100%")] == [percent_id]
    assert [row["id"] for row in history.search("file_name")] == [underscore_id]
    assert sorted(row["id"] for row in history.search("honest")) == sorted(
        [percent_id, other_id]
    )
    assert space_id == history.recent(limit=1)[0]["id"]


def test_backslash_is_literal_in_search(history: History) -> None:
    backslash_id = history.add(URL, title=r"C:\Videos\clip")
    history.add(URL, title="C:Videosclip")
    assert [row["id"] for row in history.search("\\")] == [backslash_id]


# -- recent / delete ----------------------------------------------------
def test_recent_returns_newest_first(history: History) -> None:
    ids = [history.add(URL, title=f"item {index}") for index in range(3)]
    assert [row["id"] for row in history.recent(10)] == list(reversed(ids))
    assert [row["id"] for row in history.recent(2)] == [ids[2], ids[1]]
    assert history.recent(0) == []


def test_recent_default_limit_does_not_explode(history: History) -> None:
    for index in range(60):
        history.add(URL, title=f"item {index}")
    assert len(history.recent()) == 50


def test_delete(history: History) -> None:
    record_id = history.add(URL, title="Gone")
    assert history.delete(record_id) is True
    assert history.get(record_id) is None
    assert history.delete(record_id) is False


def test_in_memory_database_works() -> None:
    db = History(":memory:")
    try:
        record_id = db.add(URL, title="Memory only")
        assert db.get(record_id)["title"] == "Memory only"
    finally:
        db.close()
