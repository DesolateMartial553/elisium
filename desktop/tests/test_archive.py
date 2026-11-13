from __future__ import annotations

import os
from pathlib import Path

import pytest

from elisium_downloader.engine.archive import Archive, reconcile

VIDEO_ID = "dQw4w9WgXcQ"


def make_archive(tmp_path: Path) -> Archive:
    return Archive(tmp_path / "archive.txt")


# -- round trip ---------------------------------------------------------
def test_add_has_remove_round_trip(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    assert archive.has("youtube", VIDEO_ID) is False

    assert archive.add("youtube", VIDEO_ID) is True
    assert archive.has("youtube", VIDEO_ID) is True

    assert archive.remove("youtube", VIDEO_ID) is True
    assert archive.has("youtube", VIDEO_ID) is False
    assert archive.remove("youtube", VIDEO_ID) is False


def test_entries_survive_a_new_instance(tmp_path: Path) -> None:
    make_archive(tmp_path).add("youtube", VIDEO_ID)
    assert Archive(tmp_path / "archive.txt").has("youtube", VIDEO_ID)


def test_add_is_idempotent_and_writes_one_line(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    assert archive.add("youtube", VIDEO_ID) is True
    assert archive.add("youtube", VIDEO_ID) is False
    text = archive.path.read_text(encoding="utf-8")
    assert text == f"youtube {VIDEO_ID}\n"


def test_other_entries_are_kept(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    archive.add("youtube", "aaa")
    archive.add("vimeo", "12345")
    archive.add("youtube", "bbb")

    assert archive.remove("vimeo", "12345") is True
    assert archive.path.read_text(encoding="utf-8") == "youtube aaa\nyoutube bbb\n"


# -- yt-dlp compatible file format --------------------------------------
def test_file_format_matches_yt_dlp(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    archive.add("YouTube", "AbC_-123")
    archive.add("vimeo", "98765")
    assert archive.path.read_bytes() == b"youtube AbC_-123\nvimeo 98765\n"


def test_extractor_is_lowercased_on_read_and_write(tmp_path: Path) -> None:
    path = tmp_path / "archive.txt"
    path.write_text("YouTube abc123\n", encoding="utf-8")
    archive = Archive(path)
    assert archive.has("YouTube", "abc123") is True
    assert archive.has("youtube", "abc123") is True

    archive.add("VIMEO", "xyz")
    assert path.read_text(encoding="utf-8") == "youtube abc123\nvimeo xyz\n"


def test_yt_dlp_style_file_is_read_as_is(tmp_path: Path) -> None:
    path = tmp_path / "archive.txt"
    path.write_text(
        "youtube dQw4w9WgXcQ\n"
        "vimeo 12345\n"
        "soundcloud 99/track-name\n",
        encoding="utf-8",
    )
    archive = Archive(path)
    assert archive.has("youtube", VIDEO_ID) is True
    assert archive.has("vimeo", "12345") is True
    assert archive.has("soundcloud", "99/track-name") is True
    assert archive.has("youtube", "12345") is False


# -- tolerance ----------------------------------------------------------
def test_missing_file_is_tolerated_and_not_created(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    assert archive.has("youtube", VIDEO_ID) is False
    assert archive.remove("youtube", VIDEO_ID) is False
    assert not archive.path.exists()


def test_blank_and_malformed_lines_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "archive.txt"
    path.write_text(
        "\n"
        "   \n"
        "youtube dQw4w9WgXcQ\n"
        "\n"
        "onlyonefield\n"
        "too many fields here\n"
        "# yt-dlp does not write comments, but do not choke on one\n"
        "vimeo 12345\n"
        "youtube dQw4w9WgXcQ\n",
        encoding="utf-8",
    )
    archive = Archive(path)
    assert archive.has("youtube", VIDEO_ID) is True
    assert archive.has("vimeo", "12345") is True
    assert archive.has("onlyonefield", "anything") is False

    archive.add("youtube", "new")
    assert path.read_text(encoding="utf-8") == (
        "youtube dQw4w9WgXcQ\n" "vimeo 12345\n" "youtube new\n"
    )


def test_crlf_file_is_tolerated(tmp_path: Path) -> None:
    path = tmp_path / "archive.txt"
    path.write_bytes(b"youtube dQw4w9WgXcQ\r\nvimeo 12345\r\n")
    archive = Archive(path)
    assert archive.has("youtube", VIDEO_ID) is True
    assert archive.has("vimeo", "12345") is True


def test_absolute_path_and_str_path_both_work(tmp_path: Path) -> None:
    path = tmp_path / "archive.txt"
    Archive(str(path)).add("youtube", VIDEO_ID)
    assert Archive(path).has("youtube", VIDEO_ID) is True


@pytest.mark.parametrize(
    "extractor, video_id",
    [("", "abc"), ("youtube", ""), ("  ", "abc"), ("youtube", "   ")],
)
def test_empty_fields_raise(tmp_path: Path, extractor: str, video_id: str) -> None:
    archive = make_archive(tmp_path)
    with pytest.raises(ValueError):
        archive.add(extractor, video_id)


def test_fields_with_whitespace_raise(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    with pytest.raises(ValueError):
        archive.add("you tube", VIDEO_ID)
    with pytest.raises(ValueError):
        archive.add("youtube", "abc 123")


def test_missing_parent_directory_is_created(tmp_path: Path) -> None:
    archive = Archive(tmp_path / "nested" / "deeper" / "archive.txt")
    assert archive.add("youtube", VIDEO_ID) is True
    assert archive.has("youtube", VIDEO_ID) is True


# -- atomic writes ------------------------------------------------------
def test_write_leaves_no_temp_files_behind(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    archive.add("youtube", "aaa")
    archive.add("youtube", "bbb")
    archive.remove("youtube", "aaa")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["archive.txt"]


def test_failed_replace_keeps_the_old_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = make_archive(tmp_path)
    archive.add("youtube", "aaa")
    before = archive.path.read_bytes()

    def boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        archive.add("youtube", "bbb")

    assert archive.path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["archive.txt"]


# -- reconcile ----------------------------------------------------------
def test_reconcile_true_when_archived_and_file_exists(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    archive.add("youtube", VIDEO_ID)
    (out / f"Some video [{VIDEO_ID}].mp4").write_bytes(b"data")

    assert reconcile(archive, f"youtube:{VIDEO_ID}", out) is True
    assert archive.has("youtube", VIDEO_ID) is True


@pytest.mark.parametrize(
    "filename",
    [
        f"Some video [{VIDEO_ID}].mp4",
        f"Some video [{VIDEO_ID}].webm",
        f"Audio [{VIDEO_ID}].mp3",
        f"  [{VIDEO_ID}]  ",
    ],
)
def test_reconcile_accepts_any_extension(tmp_path: Path, filename: str) -> None:
    archive = make_archive(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    archive.add("youtube", VIDEO_ID)
    (out / filename).write_bytes(b"data")
    assert reconcile(archive, f"youtube:{VIDEO_ID}", out) is True


def test_reconcile_removes_stale_id_when_no_file(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    archive.add("youtube", VIDEO_ID)
    archive.add("vimeo", "12345")

    assert reconcile(archive, f"youtube:{VIDEO_ID}", out) is False
    assert archive.has("youtube", VIDEO_ID) is False
    # Unrelated entries are untouched.
    assert archive.has("vimeo", "12345") is True


def test_reconcile_deleted_file_case(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    archive.add("youtube", VIDEO_ID)
    file = out / f"Some video [{VIDEO_ID}].mp4"
    file.write_bytes(b"data")
    assert reconcile(archive, f"youtube:{VIDEO_ID}", out) is True

    file.unlink()
    assert reconcile(archive, f"youtube:{VIDEO_ID}", out) is False
    assert archive.has("youtube", VIDEO_ID) is False


def test_reconcile_false_when_not_archived(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / f"Some video [{VIDEO_ID}].mp4").write_bytes(b"data")

    assert reconcile(archive, f"youtube:{VIDEO_ID}", out) is False
    assert not archive.path.exists()


def test_reconcile_ignores_a_loose_id_in_another_name(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    archive.add("youtube", VIDEO_ID)
    (out / f"Some video [x{VIDEO_ID}].mp4").write_bytes(b"data")
    (out / f"Some video {VIDEO_ID}.mp4").write_bytes(b"data")

    assert reconcile(archive, f"youtube:{VIDEO_ID}", out) is False


def test_reconcile_ignores_directories_and_part_files_are_not_enough(
    tmp_path: Path,
) -> None:
    archive = make_archive(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    archive.add("youtube", VIDEO_ID)
    (out / f"Some video [{VIDEO_ID}].mp4.part").write_bytes(b"partial")

    assert reconcile(archive, f"youtube:{VIDEO_ID}", out) is False


def test_reconcile_ignores_a_directory_named_like_the_file(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    archive.add("youtube", VIDEO_ID)
    (out / f"Some video [{VIDEO_ID}]").mkdir()

    assert reconcile(archive, f"youtube:{VIDEO_ID}", out) is False


def test_reconcile_missing_output_dir_removes_the_id(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    archive.add("youtube", VIDEO_ID)
    assert reconcile(archive, f"youtube:{VIDEO_ID}", tmp_path / "nope") is False
    assert archive.has("youtube", VIDEO_ID) is False


@pytest.mark.parametrize("key", ["", "   ", "youtube", ":abc", "youtube:", "nocolon"])
def test_reconcile_malformed_key_is_false(tmp_path: Path, key: str) -> None:
    archive = make_archive(tmp_path)
    archive.add("youtube", VIDEO_ID)
    assert reconcile(archive, key, tmp_path) is False
    assert archive.has("youtube", VIDEO_ID) is True


def test_reconcile_accepts_a_pathlib_output_dir(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    archive.add("youtube", VIDEO_ID)
    (out / f"Some video [{VIDEO_ID}].mp4").write_bytes(b"data")
    assert reconcile(archive, f"youtube:{VIDEO_ID}", str(out)) is True
