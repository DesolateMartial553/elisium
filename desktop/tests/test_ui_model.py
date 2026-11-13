from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from elisium_downloader.ui.model import (
    COLUMNS,
    PERCENT_ROLE,
    DownloadModel,
    format_bytes,
    format_eta,
    format_speed,
)

from conftest import make_snapshot


def cell(model, row, col, role=Qt.ItemDataRole.DisplayRole):
    return model.data(model.index(row, col), role)


def test_columns() -> None:
    assert COLUMNS == ("Title", "Status", "Progress", "Speed", "ETA", "Size")


def test_formatters() -> None:
    assert format_speed(4.2 * 1024 * 1024) == "4.2 MB/s"
    assert format_eta(80) == "1m 20s"
    assert format_eta(60) == "1m"
    assert format_eta(45) == "45s"
    assert format_eta(3700) == "1h 1m"
    assert format_bytes(1536) == "1.5 KB"
    assert format_bytes(10) == "10 B"
    assert format_bytes(None) == ""
    assert format_speed(None) == ""


def test_rows_title_fallback_and_update(qapp) -> None:
    model = DownloadModel()
    model.load([make_snapshot(1)])
    assert model.rowCount() == 1
    assert cell(model, 0, 0) == "https://example.com/v/1"  # URL until probe gives a title
    model.handle_event({"type": "item", "id": 1, "item": make_snapshot(1, title="Big Buck Bunny")})
    assert cell(model, 0, 0) == "Big Buck Bunny"
    model.handle_event({"type": "added", "item": make_snapshot(2)})
    assert model.rowCount() == 2
    assert model.item_id_at(1) == 2
    assert model.snapshot_at(0)["title"] == "Big Buck Bunny"
    assert model.item_id_at(5) is None and model.snapshot_at(-1) is None
    # Re-adding the same id does not create a duplicate row.
    model.upsert(make_snapshot(2))
    assert model.rowCount() == 2


@pytest.mark.parametrize(
    "state,word",
    [
        ("queued", "Queued"), ("probing", "Checking"), ("downloading", "Downloading"),
        ("merging", "Merging"), ("converting", "Converting"), ("paused", "Paused"),
        ("done", "Done"), ("failed", "Failed"), ("skipped", "Skipped"),
        ("cancelled", "Cancelled"),
    ],
)
def test_status_word_and_icon(qapp, state, word) -> None:
    model = DownloadModel()
    model.load([make_snapshot(1, state)])
    text = cell(model, 0, 1)
    assert text.endswith(word)
    assert len(text) > len(word)  # an icon character precedes the word


def test_progress_columns_and_sentence(qapp) -> None:
    model = DownloadModel()
    snap = make_snapshot(
        1,
        "downloading",
        title="Big Buck Bunny",
        progress={
            "percent": 42.0, "speed": 4.2 * 1024 * 1024, "eta": 60,
            "total_bytes": 50 * 1024 * 1024,
        },
    )
    model.load([snap])
    assert cell(model, 0, 2) == "42%"
    assert cell(model, 0, 2, PERCENT_ROLE) == 42.0
    assert cell(model, 0, 3) == "4.2 MB/s"
    assert cell(model, 0, 4) == "1m"
    assert cell(model, 0, 5) == "50.0 MB"
    for col in range(len(COLUMNS)):
        assert (
            cell(model, 0, col, Qt.ItemDataRole.AccessibleTextRole)
            == "Big Buck Bunny, downloading, 42 percent, 4.2 megabytes per second, 1 minute left"
        )


def test_done_is_100_percent_and_blank_speed(qapp) -> None:
    model = DownloadModel()
    model.load([make_snapshot(1, "done", title="T", progress={"speed": 5.0, "eta": 3})])
    assert cell(model, 0, 2) == "100%"
    assert cell(model, 0, 3) == "" and cell(model, 0, 4) == ""
    assert cell(model, 0, 1, Qt.ItemDataRole.AccessibleTextRole) == "T, done"


def test_failed_tooltip_has_message_and_fix(qapp) -> None:
    model = DownloadModel()
    error = {"code": "http_403", "message": "The site refused the download.",
             "fix": "Update yt-dlp, or import cookies"}
    model.load([make_snapshot(1, "failed", title="T", error=error)])
    tip = cell(model, 0, 1, Qt.ItemDataRole.ToolTipRole)
    assert "The site refused the download." in tip
    assert "Update yt-dlp, or import cookies" in tip
    assert cell(model, 0, 1, Qt.ItemDataRole.AccessibleTextRole).startswith("T, failed")
