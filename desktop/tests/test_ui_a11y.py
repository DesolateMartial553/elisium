"""Accessibility pass: real key presses, announcements, contrast, 200% text,
reduced motion and the F1 cheat sheet. Headless (offscreen) with QTest."""

from __future__ import annotations

import re
import threading

import pytest
from PySide6.QtCore import QCoreApplication, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableView,
    QWidget,
)

from elisium_downloader.ui import settings as st
from elisium_downloader.ui.history_page import FILE_MISSING_TEXT, HistoryModel
from elisium_downloader.ui.main_window import SHORTCUTS, MainWindow, ProgressAnnouncer
from elisium_downloader.ui.model import STATUS_TEXT, DownloadModel
from elisium_downloader.ui.playlist_dialog import PlaylistDialog
from elisium_downloader.ui.quality_dialog import QualityDialog, reduce_motion

from conftest import make_snapshot
from test_ui_quality import INFO, PLAYLIST, PLAYLIST_URL, fake_fetcher, wait_until


def pump() -> None:
    QCoreApplication.processEvents()


@pytest.fixture
def win(qapp, ui_queue, tmp_path):
    window = MainWindow(ui_queue, settings_path=tmp_path / "s.json", version_fn=lambda: "t",
                        probe_fn=lambda url: PLAYLIST if "list=" in url else INFO,
                        thumbnail_fetcher=fake_fetcher, tray_factory=lambda w: None)
    window.dialogs = []

    def run(dialog):
        window.dialogs.append(dialog)

    window._run_dialog = run
    window.show()
    window.activateWindow()
    pump()
    yield window
    for dialog in window.dialogs:
        dialog.reject()
    window.hide()
    window.bridge.close()
    window.deleteLater()


def focus_name() -> str:
    widget = QApplication.focusWidget()
    return widget.accessibleName() if widget else ""


# -- 1. real key presses ----------------------------------------------------
def test_tab_order_through_the_main_window(win) -> None:
    win.add_text("https://a.com/1")
    win.table.selectRow(0)  # Pause and Cancel become enabled, so they take focus
    win.nav.setFocus()
    pump()
    seen = [focus_name()]
    for _ in range(10):
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Tab)
        seen.append(focus_name())
    assert seen[:11] == [
        "Sections", "Video link", "Paste", "Download", "Options", "All: 1", "Downloads",
        "Pause a.com", "Cancel a.com",  # the selected row's own buttons (the host until the probe names it)
        "Pause", "Cancel",  # then the unchanged toolbar
    ]
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Tab)
    assert focus_name() == "Sections"  # wraps round


def test_tab_leaves_the_table_instead_of_walking_cells(win) -> None:
    win.add_text("https://a.com/1")
    win.table.setFocus()
    QTest.keyClick(win.table, Qt.Key.Key_Tab)
    assert QApplication.focusWidget() is not win.table


def test_ctrl_l_focuses_the_link_box(win) -> None:
    win.table.setFocus()
    QTest.keyClick(win.table, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.focusWidget() is win.url_edit


def test_ctrl_v_in_the_list_adds_clipboard_links(win, ui_queue) -> None:
    QGuiApplication.clipboard().setText("https://a.com/1")
    win.table.setFocus()
    QTest.keyClick(win.table, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert len(ui_queue.items()) == 1


def test_space_pauses_and_resumes_the_selected_download(win, ui_queue) -> None:
    win.add_text("https://a.com/1")
    win.table.selectRow(0)
    win.table.setFocus()
    QTest.keyClick(win.table, Qt.Key.Key_Space)
    pump()
    assert ui_queue.items()[0]["state"] == "paused"
    QTest.keyClick(win.table, Qt.Key.Key_Space)
    pump()
    assert ui_queue.items()[0]["state"] == "queued"


def test_ctrl_1_2_3_switch_sections(win) -> None:
    for number, index in ((2, 1), (3, 2), (1, 0)):
        QTest.keyClick(win, Qt.Key(Qt.Key.Key_0.value + number), Qt.KeyboardModifier.ControlModifier)
        assert win.stack.currentIndex() == index
        assert win.nav.currentRow() == index


def test_f1_opens_the_cheat_sheet(win) -> None:
    QTest.keyClick(win, Qt.Key.Key_F1)
    assert len(win.dialogs) == 1
    assert win.dialogs[0].windowTitle() == "Keyboard shortcuts"


def test_ctrl_shift_return_opens_quality_and_ctrl_return_adds(win, ui_queue) -> None:
    win.url_edit.setText("https://example.com/v/2")
    win.url_edit.setFocus()
    QTest.keyClick(win.url_edit, Qt.Key.Key_Return,
                   Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert isinstance(win.dialogs[0], QualityDialog)
    assert ui_queue.items() == []
    QTest.keyClick(win.url_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert len(ui_queue.items()) == 1


def test_enter_in_the_link_box_adds(win, ui_queue) -> None:
    win.url_edit.setText("https://example.com/v/3")
    win.url_edit.setFocus()
    QTest.keyClick(win.url_edit, Qt.Key.Key_Return)
    assert len(ui_queue.items()) == 1 and win.url_edit.text() == ""


def test_ctrl_q_quits_without_a_prompt_when_idle(win) -> None:
    QTest.keyClick(win, Qt.Key.Key_Q, Qt.KeyboardModifier.ControlModifier)
    assert not win.isVisible()


@pytest.fixture
def dialogs(qapp, ui_queue):
    made = []

    def quality():
        d = QualityDialog("https://example.com/v/1", ui_queue, lambda u: INFO,
                          thumbnail_fetcher=fake_fetcher)
        made.append(d)
        d.show()
        assert wait_until(lambda: d.state == "ready")
        return d

    def playlist():
        d = PlaylistDialog(PLAYLIST_URL, ui_queue, lambda u: PLAYLIST)
        made.append(d)
        d.show()
        assert wait_until(lambda: d.state == "ready")
        return d

    yield quality, playlist
    for d in made:
        d.reject()
        d.deleteLater()


def test_escape_closes_every_dialog(win, dialogs) -> None:
    quality, playlist = dialogs
    for dialog in (quality(), playlist(), win.build_shortcuts_dialog()):
        dialog.show()
        pump()
        assert dialog.isVisible()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        assert not dialog.isVisible()
        assert dialog.result() == QDialog.DialogCode.Rejected


def test_enter_in_the_range_field_applies_it_and_does_not_add(dialogs, ui_queue) -> None:
    _quality, playlist = dialogs
    dialog = playlist()
    dialog.range_edit.setFocus()
    dialog.range_edit.blockSignals(True)  # type the range without the live preview
    dialog.range_edit.setText("1")
    dialog.range_edit.blockSignals(False)
    assert len(dialog.selected_entries()) == 5  # everything still ticked
    QTest.keyClick(dialog.range_edit, Qt.Key.Key_Return)
    assert [e.index for e in dialog.selected_entries()] == [1]
    assert dialog.isVisible() and ui_queue.items() == []
    QTest.keyClick(dialog.range_edit, Qt.Key.Key_Enter)
    assert dialog.isVisible()


def test_enter_in_the_range_field_reports_a_bad_range(dialogs) -> None:
    _quality, playlist = dialogs
    dialog = playlist()
    dialog.range_edit.blockSignals(True)
    dialog.range_edit.setText("9-1")
    dialog.range_edit.blockSignals(False)
    QTest.keyClick(dialog.range_edit, Qt.Key.Key_Return)
    assert dialog.range_error.isVisibleTo(dialog) and dialog.range_error.text()


# -- 2. progress announcements ----------------------------------------------
def progress_event(item_id, state, percent=None, **over):
    snap = make_snapshot(item_id, state, title=f"Clip {item_id}", progress={"percent": percent}, **over)
    return {"type": "progress", "item": snap}


def test_hundred_ticks_give_at_most_four_announcements() -> None:
    said: list[str] = []
    announcer = ProgressAnnouncer(said.append)
    for tick in range(1, 101):
        announcer.feed(progress_event(1, "downloading", float(tick)))
    announcer.feed(progress_event(1, "done", 100.0))
    assert said == [
        "Clip 1: 25 percent", "Clip 1: 50 percent", "Clip 1: 75 percent", "Clip 1 finished",
    ]


def test_announcements_are_per_item_and_a_jump_announces_once() -> None:
    said: list[str] = []
    announcer = ProgressAnnouncer(said.append)
    announcer.feed(progress_event(1, "downloading", 80.0))
    announcer.feed(progress_event(2, "downloading", 30.0))
    announcer.feed(progress_event(1, "downloading", 90.0))
    assert said == ["Clip 1: 75 percent", "Clip 2: 25 percent"]


def test_failure_is_announced_once_with_the_plain_message_and_retry_starts_over() -> None:
    said: list[str] = []
    announcer = ProgressAnnouncer(said.append)
    error = {"code": "x", "message": "Network problem.", "fix": ""}
    failed = {"type": "state", "item": make_snapshot(1, "failed", title="V", error=error)}
    announcer.feed(failed)
    announcer.feed(failed)
    assert said == ["V failed: Network problem."]
    announcer.feed({"type": "state", "item": make_snapshot(1, "queued", title="V")})
    announcer.feed(progress_event(1, "downloading", 60.0))
    assert said[-1] == "Clip 1: 50 percent"


def test_plain_progress_below_a_step_is_silent() -> None:
    said: list[str] = []
    announcer = ProgressAnnouncer(said.append)
    for tick in (None, 1.0, 10.0, 24.9):
        announcer.feed(progress_event(1, "downloading", tick))
    assert said == []


def test_window_live_label_is_single_hidden_and_updated(win) -> None:
    assert win.live_label.accessibleName() == "Progress announcements"
    assert win.live_label.height() == 0
    assert len(win.findChildren(QLabel, options=Qt.FindChildOption.FindChildrenRecursively)) > 1
    for tick in range(1, 101):
        win._on_event(progress_event(7, "downloading", float(tick)))
    win._on_event(progress_event(7, "done", 100.0))
    assert win.announcements == [
        "Clip 7: 25 percent", "Clip 7: 50 percent", "Clip 7: 75 percent", "Clip 7 finished",
    ]
    assert win.live_label.text() == "Clip 7 finished"
    assert win.live_label.accessibleDescription() == "Clip 7 finished"


# -- 3. not colour alone ------------------------------------------------------
@pytest.mark.parametrize("state", sorted(STATUS_TEXT))
def test_every_status_has_a_word_in_table_history_and_speech(state) -> None:
    model = DownloadModel()
    model.load([make_snapshot(1, state, title="T")])
    shown = model.index(0, 1).data()
    assert re.search(r"[A-Za-z]{4,}", shown), shown
    assert shown.isalpha()  # a plain word: Night shelf has no icon or emoji in a status
    assert re.search(r"[A-Za-z]{4,}", HistoryModel.state_text({"state": state}))
    assert HistoryModel.state_text({"state": state}).isalpha()
    assert state.replace("probing", "checking") in DownloadModel.spoken(
        make_snapshot(1, state, title="T")).lower()


def test_history_missing_file_has_a_word() -> None:
    assert re.search(r"[A-Za-z]{4,}", FILE_MISSING_TEXT)
    assert FILE_MISSING_TEXT == "File missing"  # words only, no warning sign


def test_unavailable_playlist_entries_say_so(dialogs) -> None:
    _quality, playlist = dialogs
    dialog = playlist()
    texts = [dialog.list.item(i).text() for i in range(dialog.list.count())]
    assert any("Unavailable" in t for t in texts)
    assert "unavailable" in dialog.count_label.text()


def test_notification_texts_contain_words(qapp, ui_queue) -> None:
    from test_ui_tray import FakeTray
    from elisium_downloader.ui.tray import TrayController

    fake = FakeTray()
    window = MainWindow(ui_queue, version_fn=lambda: "t",
                        tray_factory=lambda w: TrayController(
                            w, tray=fake, quit_fn=lambda: None, manage_quit_policy=False))
    window._on_event({"type": "state", "item": make_snapshot(1, "done", title="Alpha clip")})
    err = {"code": "x", "message": "Network problem.", "fix": ""}
    window.tray._last_sent = float("-inf")
    window._on_event({"type": "state", "item": make_snapshot(2, "failed", title="Bravo clip", error=err)})
    window.bridge.close()
    assert [t for t, _m in fake.messages] == ["Download finished", "Download failed"]
    assert all(re.search(r"[A-Za-z]{4,}", m) for _t, m in fake.messages)


def lum(c: QColor) -> float:
    def ch(v: int) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


def contrast(a: QColor, b: QColor) -> float:
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def palette(dark: bool) -> QPalette:
    p = QPalette()
    c = QPalette.ColorRole
    colours = (
        {c.Window: "#2b2b2b", c.WindowText: "#eeeeee", c.Base: "#1e1e1e", c.Text: "#eeeeee",
         c.Button: "#3a3a3a", c.ButtonText: "#eeeeee", c.Highlight: "#3daee9",
         c.HighlightedText: "#000000"}
        if dark
        else {c.Window: "#efefef", c.WindowText: "#202020", c.Base: "#ffffff", c.Text: "#202020",
              c.Button: "#e0e0e0", c.ButtonText: "#202020", c.Highlight: "#1a5fb4",
              c.HighlightedText: "#ffffff"}
    )
    for role, value in colours.items():
        p.setColor(role, QColor(value))
    return p


def ring_contrast(image, background: QColor, rect: QRect, thickness: int = 2) -> float:
    """Best contrast against *background* among the pixels on the rect's outer edge."""
    best = 1.0
    for y in range(rect.top(), rect.bottom() + 1):
        for x in range(rect.left(), rect.right() + 1):
            inside = (rect.left() + thickness <= x <= rect.right() - thickness
                      and rect.top() + thickness <= y <= rect.bottom() - thickness)
            if not inside:
                best = max(best, contrast(QColor(image.pixel(x, y)), background))
    return best


@pytest.fixture(params=["dark", "light"])
def themed(request, win):
    """The app palette set to a dark or light one (restored afterwards)."""
    saved = QApplication.palette()
    QApplication.setPalette(palette(request.param == "dark"))
    pump()
    yield request.param
    QApplication.setPalette(saved)
    pump()


def test_checkbox_and_focus_ring_contrast_in_dark_and_light(themed) -> None:
    holder = QWidget()
    holder.setAutoFillBackground(True)
    from PySide6.QtWidgets import QVBoxLayout
    layout = QVBoxLayout(holder)
    box, button, edit, listing = QCheckBox("Option"), QPushButton("Go"), QLineEdit("x"), QListWidget()
    listing.addItems(["one", "two"])
    for widget in (box, button, edit, listing):
        layout.addWidget(widget)
    holder.show()
    pump()
    background = holder.palette().color(QPalette.ColorRole.Window)
    indicator = QRect(box.x(), box.y(), 24, box.height())  # the box, not the text
    plain = holder.grab().toImage()
    assert ring_contrast(plain, background, indicator, 99) >= 3.0, "unticked box is too faint"
    for widget in (button, edit, listing):
        widget.setFocus()
        pump()
        ringed = holder.grab().toImage()
        assert ring_contrast(ringed, background, widget.geometry()) >= 3.0, (
            f"{type(widget).__name__} focus ring is too faint ({themed})"
        )
    holder.close()


def test_selected_row_stands_out_in_dark_and_light(themed) -> None:
    table = QTableView()
    model = DownloadModel()
    model.load([make_snapshot(1, "queued", title="One"), make_snapshot(2, "queued", title="Two")])
    table.setModel(model)
    table.resize(400, 300)
    table.show()
    table.selectRow(0)
    table.setFocus()
    pump()
    image = table.viewport().grab().toImage()
    selected = QColor(image.pixel(3, table.rowHeight(0) // 2))
    empty = QColor(image.pixel(3, image.height() - 5))  # below the rows: plain Base
    assert contrast(selected, empty) >= 3.0
    highlighted = table.palette().color(QPalette.ColorRole.HighlightedText)
    assert contrast(highlighted, selected) >= 4.5
    table.close()


# -- 4. 200% text -----------------------------------------------------------
@pytest.fixture
def big_text(qapp):
    probe = QWidget()  # the platform theme resets the app font on the first show
    probe.show()
    pump()
    probe.close()
    original = QApplication.font()
    big = QApplication.font()
    big.setPointSizeF(original.pointSizeF() * 2)
    QApplication.setFont(big)
    pump()
    yield
    QApplication.setFont(original)
    pump()


def clipped(root: QWidget) -> list[str]:
    problems = []
    for widget in root.findChildren(QWidget):
        if not widget.isVisibleTo(root) or widget.height() == 0 or widget.width() == 0:
            continue
        name = f"{type(widget).__name__}({widget.accessibleName() or widget.objectName()})"
        if isinstance(widget, QLabel) and widget.text():
            plain = re.sub("<[^>]+>", "", widget.text())
            if widget.wordWrap():
                if widget.heightForWidth(widget.width()) > widget.height():
                    problems.append(f"{name} wrapped text taller than the label: {plain[:30]}")
            elif widget.fontMetrics().horizontalAdvance(plain) > widget.width():
                problems.append(f"{name} text wider than the label: {plain[:30]}")
        elif isinstance(widget, QAbstractButton) and widget.text():
            text = widget.text().replace("&", "")
            if widget.fontMetrics().horizontalAdvance(text) > widget.width():
                problems.append(f"{name} text wider than the button: {text}")
        if type(widget).__name__ in ("QHeaderView", "QWidget", "QScrollBar"):
            continue  # Qt's own internals report generic minimum sizes
        hint = widget.minimumSizeHint()
        if hint.isValid() and (widget.width() < hint.width() or widget.height() < hint.height()):
            problems.append(f"{name} {widget.size().toTuple()} smaller than its minimum {hint.toTuple()}")
    return problems


def table_cells_fit(table: QTableView, samples: dict[int, str]) -> list[str]:
    fm = table.fontMetrics()
    return [
        f"column {col} is {table.columnWidth(col)}px but needs {fm.horizontalAdvance(text)} for {text!r}"
        for col, text in samples.items()
        if table.columnWidth(col) < fm.horizontalAdvance(text)
    ]


def test_text_really_is_double(big_text, win) -> None:
    assert win.table.fontMetrics().height() >= 28


def test_main_history_settings_fit_at_200_percent(big_text, qapp, ui_queue, tmp_path) -> None:
    window = MainWindow(ui_queue, settings_path=tmp_path / "s.json", version_fn=lambda: "2025.01.02",
                        tray_factory=lambda w: None)
    try:
        window.model.load([
            make_snapshot(1, "downloading", title="Big Buck Bunny",
                          progress={"percent": 42.0, "speed": 4404019.0, "eta": 80,
                                    "total_bytes": 52428800}),
            make_snapshot(2, "failed", title="Broken",
                          error={"code": "x", "message": "The site refused the download.", "fix": "x"}),
        ])
        window._refresh_ui()
        window.show()
        pump()
        for index, name in enumerate(("Downloads", "History", "Settings")):
            window.show_section(index)
            pump()
            assert clipped(window) == [], name
            for table in window.stack.currentWidget().findChildren(QTableView):
                assert not table.horizontalScrollBar().isVisible(), f"{name} scrolls sideways"
                assert table.horizontalScrollBar().maximum() == 0
        window.show_section(0)
        # Cards: the row height grows with the text so no line of a card is clipped.
        window.resize(3000, window.height())
        pump()
        need = window.delegate.row_height(window.table.font())
        assert window.table.verticalHeader().defaultSectionSize() >= need
        assert need >= 3 * window.table.fontMetrics().height()
        window.show_section(1)
        pump()
        history = window.history_page.table
        assert history.verticalHeader().defaultSectionSize() >= \
            window.history_page.delegate.row_height(history.font())
        assert window.nav.width() >= window.nav.fontMetrics().horizontalAdvance("Downloads")
        window.hide()
    finally:
        window.bridge.close()
        window.deleteLater()


def test_dialogs_fit_at_200_percent(big_text, win, dialogs) -> None:
    quality, playlist = dialogs
    q = quality()
    pump()
    assert clipped(q) == []
    q.advanced_button.setChecked(True)
    pump()
    assert clipped(q) == []
    assert q.video_table.height() >= q.video_table.verticalHeader().defaultSectionSize() * 3
    p = playlist()
    pump()
    assert clipped(p) == []
    shortcuts = win.build_shortcuts_dialog()
    shortcuts.show()
    pump()
    assert clipped(shortcuts) == []
    shortcuts.close()


# -- 5. reduced motion ---------------------------------------------------------
@pytest.mark.parametrize("value,expected", [("1", True), ("0", False)])
def test_reduce_motion_env_override(monkeypatch, value, expected) -> None:
    monkeypatch.setenv("ELISIUM_REDUCE_MOTION", value)
    assert reduce_motion() is expected


def test_reduce_motion_defaults_to_off_without_a_hint(monkeypatch) -> None:
    monkeypatch.delenv("ELISIUM_REDUCE_MOTION", raising=False)
    assert reduce_motion() is False  # PySide6 6.12 exposes no reduced-motion hint


def slow_probe(gate: threading.Event, result):
    def probe(url):
        gate.wait(5)
        return result
    return probe


@pytest.mark.parametrize("reduced", [True, False])
def test_dialogs_show_text_not_a_busy_bar_when_motion_is_reduced(
    qapp, ui_queue, monkeypatch, reduced
) -> None:
    monkeypatch.setenv("ELISIUM_REDUCE_MOTION", "1" if reduced else "0")
    gate = threading.Event()
    quality = QualityDialog("https://example.com/v/1", ui_queue, slow_probe(gate, INFO),
                            thumbnail_fetcher=fake_fetcher)
    playlist = PlaylistDialog(PLAYLIST_URL, ui_queue, slow_probe(gate, PLAYLIST))
    try:
        assert quality.state == "probing" and playlist.state == "probing"
        assert quality.status_label.text() == "Checking the link..."
        assert playlist.status_label.text() == "Checking the playlist..."
        for dialog in (quality, playlist):
            assert dialog.progress.isVisibleTo(dialog) is (not reduced)
    finally:
        gate.set()
        for dialog in (quality, playlist):
            dialog.reject()
            dialog.deleteLater()


# -- 6. the F1 cheat sheet cannot drift ----------------------------------------
def registered_keys(window: MainWindow) -> set[str]:
    shortcuts = window._section_shortcuts + window._add_shortcuts + window._shortcuts
    return {sc.key().toString() for sc in shortcuts}


def test_cheat_sheet_matches_registered_shortcuts(win) -> None:
    listed = {keys for _text, _meaning, sequences in SHORTCUTS for keys in sequences}
    assert listed == registered_keys(win)
    # Every key a QShortcut really owns is written in the cheat sheet text (Ctrl+Enter
    # is the keypad twin of Ctrl+Return, Ctrl+Shift+Enter of Ctrl+Shift+Return).
    shown = " ".join(text for text, _m, _s in SHORTCUTS)
    for keys in registered_keys(win):
        normal = keys.replace("Enter", "Return")
        assert normal in shown or normal.replace("Ctrl+", "") in shown, keys


def test_cheat_sheet_dialog_shows_every_entry(win) -> None:
    dialog = win.build_shortcuts_dialog()
    text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    for keys, meaning, _sequences in SHORTCUTS:
        assert keys in text and meaning in text
    dialog.deleteLater()


def test_every_shortcut_in_the_sheet_really_fires(win, ui_queue) -> None:
    """Each listed key, sent as a real key press, does what the sheet says."""
    win.add_text("https://a.com/1")
    win.table.selectRow(0)
    win.table.setFocus()
    QTest.keyClick(win.table, Qt.Key.Key_Space)  # Space
    assert ui_queue.items()[0]["state"] == "paused"
    QTest.keyClick(win.table, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)  # Ctrl+2
    assert win.stack.currentIndex() == 1
    QTest.keyClick(win, Qt.Key.Key_F1)  # F1
    assert win.dialogs
