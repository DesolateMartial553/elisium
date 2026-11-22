"""Brief 11C-2: the Night shelf History page, Settings page, dialogs and the leftovers."""

from __future__ import annotations

import time
import unicodedata
from datetime import date, datetime, timedelta

import pytest
from PySide6.QtCore import QCoreApplication, QPointF, Qt
from PySide6.QtGui import QFontInfo
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QLabel,
    QLineEdit,
    QWidget,
)

from elisium_downloader.ui import history_page as hp
from elisium_downloader.ui import settings as st
from elisium_downloader.ui import theme, widgets
from elisium_downloader.ui.history_page import HistoryModel, HistoryPage, day_heading
from elisium_downloader.ui.main_window import MainWindow
from elisium_downloader.ui.playlist_dialog import PlaylistDialog
from elisium_downloader.ui.quality_dialog import QualityDialog
from elisium_downloader.ui.settings_page import SettingsPage
from elisium_downloader.ui.sign_in_dialog import SignInDialog

TODAY = date(2026, 11, 22)


def pump(ms: int = 0) -> None:
    end = time.monotonic() + ms / 1000
    QCoreApplication.processEvents()
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def wait_until(pred, timeout: float = 3.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        pump()
        if pred():
            return True
        time.sleep(0.005)
    return pred()


def iso(day: date, hour: int = 12, minute: int = 0) -> str:
    return datetime(day.year, day.month, day.day, hour, minute).astimezone().isoformat(timespec="seconds")


@pytest.fixture
def styled(qapp):
    yield qapp
    theme.reset(qapp)


# -- History: grouping by day ------------------------------------------------------------
def test_day_headings_are_today_yesterday_then_dates() -> None:
    assert day_heading(TODAY, TODAY) == "Today"
    assert day_heading(TODAY - timedelta(days=1), TODAY) == "Yesterday"
    assert day_heading(date(2026, 11, 19), TODAY) == "Thursday 19 November"
    assert day_heading(date(2025, 3, 2), TODAY) == "Sunday 2 March 2025"


def _row(row_id: int, when: str, url: str = "https://www.youtube.com/watch?v=1", **kw):
    return {"id": row_id, "url": url, "title": f"Clip {row_id}", "state": "done", "file_path": None,
            "error_message": None, "created_at": when, "finished_at": when, **kw}


def test_model_marks_the_first_row_of_each_day_with_a_heading(qapp) -> None:
    model = HistoryModel()
    model.load([
        _row(5, iso(TODAY, 10, 41)), _row(4, iso(TODAY, 9, 5)),
        _row(3, iso(TODAY - timedelta(days=1), 21, 4)),
        _row(2, iso(date(2026, 11, 19), 16, 50)), _row(1, iso(date(2026, 11, 19), 9, 15)),
    ], today=TODAY)
    headings = [model.heading_at(r) for r in range(model.rowCount())]
    assert headings == ["Today", None, "Yesterday", "Thursday 19 November", None]
    assert model.row_at(0)["when_text"] == "10:41"
    assert model.heading_at(99) is None


@pytest.fixture
def hist(qapp, ui_queue, tmp_path):
    h = ui_queue.history
    real = tmp_path / "real.mp4"
    real.write_bytes(b"x" * 2048)
    now = datetime.now().astimezone()
    older = now - timedelta(days=3)
    for url, title, state, when, file in (
        ("https://www.youtube.com/watch?v=1", "Alpha clip", "done", now, str(real)),
        ("https://www.instagram.com/p/2/", "Beta post", "failed", now - timedelta(seconds=5), None),
        ("https://www.youtube.com/watch?v=3", "Gamma tune", "done", now - timedelta(days=1), str(real)),
        ("https://www.tiktok.com/@x/video/4", "Delta dance", "done", older, str(tmp_path / "gone.mp4")),
    ):
        row = h.add(url, title=title, state=state, file_path=file,
                    created_at=when.isoformat(timespec="seconds"))
        h._write("UPDATE downloads SET finished_at = ? WHERE id = ?", (when.isoformat(timespec="seconds"), row))
    page = HistoryPage(ui_queue)
    page.resize(980, 600)
    yield page
    page.deleteLater()


def titles(page) -> list[str]:
    return [page.model.row_at(r)["title"] for r in range(page.model.rowCount())]


def test_history_page_groups_newest_first_by_day(hist) -> None:
    assert titles(hist) == ["Alpha clip", "Beta post", "Gamma tune", "Delta dance"]
    assert [hist.model.heading_at(r) for r in range(4)][:3] == ["Today", None, "Yesterday"]
    assert hist.model.heading_at(3) is not None  # three days back: its own dated heading
    base = hist.delegate.row_height(hist.table.font())
    extra = hist.delegate.heading_height(hist.table.font())
    assert hist.table.rowHeight(0) == base + extra  # first row of the day holds the heading
    assert hist.table.rowHeight(1) == base
    assert hist.table.verticalHeader().defaultSectionSize() >= base


def test_history_search_narrows_the_list(hist) -> None:
    hist.search_edit.setText("gamma")
    assert wait_until(lambda: titles(hist) == ["Gamma tune"])
    assert hist.model.heading_at(0) == "Yesterday"  # headings follow the narrowed list
    hist.search_edit.setText("zzzz")
    assert wait_until(lambda: hist.model.rowCount() == 0)
    assert hist.empty_state.text == "Nothing matches"
    hist.search_edit.clear()
    assert wait_until(lambda: hist.model.rowCount() == 4)


def test_history_site_filter_narrows_the_list(hist) -> None:
    assert hist.site_button.accessibleName() == "Site filter"
    assert hist.site_button.text() == hp.ALL_SITES
    labels = [a.text() for a in hist.site_menu.actions()]
    assert labels == [hp.ALL_SITES, "Instagram", "TikTok", "YouTube"]
    next(a for a in hist.site_menu.actions() if a.text() == "YouTube").trigger()
    assert titles(hist) == ["Alpha clip", "Gamma tune"]
    assert hist.site_button.text() == "YouTube"
    hist.search_edit.setText("beta")  # the site is gone from the results: back to all sites
    assert wait_until(lambda: titles(hist) == ["Beta post"])
    assert hist.site_button.text() == hp.ALL_SITES
    hist.search_edit.clear()
    assert wait_until(lambda: hist.model.rowCount() == 4)
    hist.set_site("TikTok")
    assert titles(hist) == ["Delta dance"]
    hist.set_site(None)
    assert hist.model.rowCount() == 4


def test_history_row_has_a_word_for_each_state_and_missing_file(hist) -> None:
    by_title = {titles(hist)[r]: HistoryModel.state_text(hist.model.row_at(r)) for r in range(4)}
    assert by_title == {"Alpha clip": "Done", "Beta post": "Failed", "Gamma tune": "Done",
                        "Delta dance": "File missing"}
    assert widgets.history_tone("done") == "positive" and widgets.history_tone("failed") == "negative"
    assert widgets.history_tone("done", missing=True) == "warning"


def test_history_row_links_offer_open_folder_again_or_only_again(hist) -> None:
    kinds = {titles(hist)[r]: widgets.HistoryDelegate.link_kinds(hist.model.row_at(r)) for r in range(4)}
    assert kinds["Alpha clip"] == ["open", "folder", "again"]
    assert kinds["Beta post"] == ["again"] and kinds["Delta dance"] == ["again"]


def test_clicking_a_row_link_runs_the_action(hist, monkeypatch) -> None:
    hist.show()
    pump(50)
    opened = []
    monkeypatch.setattr(hp.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()))
    added = []
    monkeypatch.setattr(hist.queue, "add", lambda url, **kw: added.append(url) or {})
    index = hist.model.index(0, 0)
    rect = hist.table.visualRect(index)
    geo = hist.delegate.geometry(rect, hist.model.row_at(0), hist.table.font(), True)
    kind, hit = geo.links[0]
    assert kind == "open"
    QTest.mouseClick(hist.table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     hit.center().toPoint())
    assert len(opened) == 1 and opened[0].endswith("real.mp4")
    kind, hit = geo.links[2]
    assert kind == "again"
    QTest.mouseClick(hist.table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     hit.center().toPoint())
    assert added == ["https://www.youtube.com/watch?v=1"]
    assert hist.message_label.text() == "Added to the download list"
    # the title area is not a link
    assert hist._link_under(QPointF(geo.title.center())) is None
    hist.hide()


def test_history_summary_and_empty_state(qapp, ui_queue) -> None:
    page = HistoryPage(ui_queue)
    assert page.summary_label.text() == "0 saved"
    assert page.empty_state.text == "No downloads yet" and not page.empty_state.isHidden()
    page.deleteLater()


# -- no emoji anywhere --------------------------------------------------------------------
ALLOWED = set("·…−–—’‘“”")


def has_symbol(text: str) -> str | None:
    for ch in text:
        if ch in ALLOWED:
            continue
        if ord(ch) > 0xFFFF or unicodedata.category(ch) in ("So", "Cs", "Co") or 0x2190 <= ord(ch) <= 0x2BFF:
            return ch
    return None


def visible_strings(root: QWidget) -> list[str]:
    out: list[str] = []
    for widget in [root, *root.findChildren(QWidget)]:
        out += [widget.windowTitle(), widget.toolTip(), widget.accessibleName(),
                widget.accessibleDescription()]
        if isinstance(widget, (QLabel, QAbstractButton)):
            out.append(widget.text())
        if isinstance(widget, QLineEdit):
            out += [widget.text(), widget.placeholderText()]
        if isinstance(widget, QComboBox):
            out += [widget.itemText(i) for i in range(widget.count())]
    return [t for t in out if t]


def test_no_emoji_in_history_or_settings_or_main_window(qapp, ui_queue, tmp_path, hist) -> None:
    window = MainWindow(ui_queue, settings_path=tmp_path / "s.json", version_fn=lambda: "1",
                        tray_factory=lambda w: None, detect_fn=lambda: ["firefox"])
    try:
        pump(100)
        for page in (window, hist, window.settings_page):
            for text in visible_strings(page):
                assert has_symbol(text) is None, (page, text)
        # what the History rows say, to the eye and to a screen reader
        for r in range(hist.model.rowCount()):
            for column in range(5):
                for role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole,
                             Qt.ItemDataRole.ToolTipRole):
                    value = hist.model.index(r, column).data(role)
                    assert value is None or has_symbol(str(value)) is None, (r, column, value)
        for action in hist.site_menu.actions():
            assert has_symbol(action.text()) is None
    finally:
        window.bridge.close()
        window.deleteLater()


def test_no_emoji_in_the_dialogs(qapp, ui_queue, tmp_path) -> None:
    probe = lambda url: {"title": "T", "entries": [{"id": "a", "title": "One", "url": "https://y.t/a"}],
                         "formats": []}
    dialogs = [
        QualityDialog("https://y.t/a", ui_queue, probe),
        PlaylistDialog("https://y.t/p", ui_queue, probe),
        SignInDialog(detect_fn=lambda: ["firefox"]),
    ]
    for dialog in dialogs:
        wait_until(lambda: getattr(dialog, "state", "ready") != "probing")
        for text in visible_strings(dialog):
            assert has_symbol(text) is None, (type(dialog).__name__, text)
        dialog.deleteLater()


# -- Settings -----------------------------------------------------------------------------
@pytest.fixture
def spage(qapp, ui_queue, tmp_path):
    page = SettingsPage(st.Settings(), ui_queue, tmp_path / "cfg" / "settings.json",
                        version_fn=lambda: "2025.01.02")
    page.resize(940, 700)
    yield page
    page.deleteLater()


def group_of(page: SettingsPage, widget: QWidget) -> str | None:
    for heading, frame in page.groups.items():
        if frame.isAncestorOf(widget):
            return heading
    return None


def test_settings_has_the_five_groups_in_order(spage) -> None:
    assert list(spage.groups) == ["Downloads", "Photos and music", "Accounts", "Appearance", "About"]
    headings = [lab.text() for lab in spage.findChildren(QLabel) if lab.objectName() == "groupTitle"]
    assert headings == list(spage.groups)
    for text in headings:  # sentence case, no uppercase letter-spaced labels
        assert text == text.capitalize() or text[0].isupper() and text[1:].lower() == text[1:]


def test_every_prior_setting_is_still_there_in_its_group(spage) -> None:
    expected = {
        "Downloads": [spage.concurrency_spin, spage.limit_check, spage.limit_spin, spage.limit_unit,
                      spage.preset_combo],
        "Accounts": [spage.detect_button, spage.cookies_combo, spage.cookies_file_edit,
                     spage.cookies_choose_button, spage.cookies_clear_button, spage.cookies_help],
        "Appearance": [spage.notify_check, spage.tray_check, spage.appearance_combo, spage.motion_check],
        "About": [spage.folder_label, spage.open_folder_button, spage.version_label,
                  spage.update_hint, spage.open_data_button],
    }
    for heading, widgets_ in expected.items():
        for widget in widgets_:
            assert group_of(spage, widget) == heading, (heading, widget.accessibleName())
    photos = [lab.text() for lab in spage.groups["Photos and music"].findChildren(QLabel)
              if lab.objectName() == "settingName"]
    assert photos == ["Photo posts with a song", "Song length"]


def test_settings_keyboard_order_is_unchanged(spage) -> None:
    order = [spage.concurrency_spin, spage.limit_check, spage.limit_spin, spage.limit_unit,
             spage.preset_combo, spage.detect_button, spage.cookies_combo,
             spage.cookies_choose_button, spage.cookies_clear_button, spage.notify_check,
             spage.tray_check, spage.appearance_combo, spage.motion_check,
             spage.open_folder_button, spage.open_data_button]
    wanted = set(order)
    seen = []
    widget = spage.concurrency_spin
    for _ in range(200):
        if widget in wanted and widget not in seen:
            seen.append(widget)
        widget = widget.nextInFocusChain()
    assert seen == order


def test_accessible_names_and_labels_are_unchanged(spage) -> None:
    names = {w.accessibleName() for w in spage.findChildren(QWidget) if w.accessibleName()}
    before = {
        "Parallel downloads", "Limit speed", "Speed limit amount", "Speed limit unit", "Default quality",
        "Signed-in browser found", "Signed-in browser", "cookies.txt file", "Choose cookies.txt file",
        "Clear cookies.txt file", "About signing in", "Notify when a download finishes",
        "Keep running in the tray when closed", "Appearance", "Reduce motion", "Download folder",
        "Open download folder", "yt-dlp version", "About updating yt-dlp", "Open data folder",
    }
    assert before <= names, before - names
    labels = {lab.text(): lab.buddy() for lab in spage.findChildren(QLabel) if lab.buddy()}
    assert labels["Parallel downloads"] is spage.concurrency_spin
    assert labels["Default quality"] is spage.preset_combo
    assert labels["Browser"] is spage.cookies_combo
    assert labels["cookies.txt file"] is spage.cookies_choose_button
    assert labels["Notify when a download finishes"] is spage.notify_check


def test_a_switch_row_label_toggles_its_switch(spage) -> None:
    label = next(lab for lab in spage.findChildren(QLabel) if lab.text() == "Reduce motion")
    assert not spage.motion_check.isChecked()
    spage.show()
    pump(50)
    QTest.mouseClick(label, Qt.MouseButton.LeftButton)
    assert spage.motion_check.isChecked()
    assert spage.settings.reduce_motion is True
    spage.hide()


def test_settings_page_has_no_glow_text_and_reduce_motion_still_works(styled, ui_queue, tmp_path) -> None:
    window = MainWindow(ui_queue, settings_path=tmp_path / "s.json", version_fn=lambda: "1",
                        tray_factory=lambda w: None, detect_fn=lambda: [])
    try:
        page = window.settings_page
        text = page.motion_check.accessibleDescription().lower()
        assert "glow" not in text and "breath" not in text
        assert not theme.reduce_motion_enabled()
        page.motion_check.setChecked(True)
        assert theme.reduce_motion_enabled() is True  # the window applies it live
        assert st.load(tmp_path / "s.json").reduce_motion is True
    finally:
        theme.set_reduce_motion(False)
        window.bridge.close()
        window.deleteLater()


def test_settings_rows_stack_their_control_when_narrow(spage) -> None:
    spage.show()
    pump(80)
    row = next(r for r in spage.rows if r.name.text() == "cookies.txt file")
    assert not row.stacked
    spage.resize(430, 700)
    pump(120)
    assert row.stacked  # the control moved under its text instead of clipping
    assert row.control.geometry().top() > row.name.geometry().bottom() - 4
    spage.resize(940, 700)
    pump(120)
    assert not row.stacked
    spage.hide()


def test_settings_controls_use_the_control_fill_in_both_schemes(styled) -> None:
    for palette in (theme.NIGHT, theme.DAY):
        sheet = " ".join(theme.build_stylesheet(palette).split())
        want = (f"background: {palette.hex('control')}; color: {palette.hex('text')}; "
                f"placeholder-text-color: {palette.hex('muted')};")  # faint on control is under 4.5
        assert want in sheet


@pytest.mark.parametrize("palette", [theme.NIGHT, theme.DAY])
def test_control_fill_pairs_pass_contrast(palette) -> None:
    from test_theme import _contrast_module
    cc = _contrast_module()
    assert cc.ratio(palette.hex("text"), palette.hex("control")) >= 4.5
    assert cc.ratio(palette.hex("muted"), palette.hex("control")) >= 4.5  # placeholder and switch knob
    assert cc.ratio(palette.hex("faint"), palette.hex("raised")) >= 4.5   # disabled control text
    assert cc.ratio(palette.hex("onPrimary"), palette.hex("primary")) >= 4.5


# -- dialogs ------------------------------------------------------------------------------
def _quality(ui_queue):
    return QualityDialog("https://y.t/a", ui_queue, lambda url: {"title": "T", "formats": []})


def test_dialogs_are_surface_cards_on_ground_with_one_inverted_pill(styled, ui_queue) -> None:
    theme.apply(styled, "night")
    dialog = _quality(ui_queue)
    dialog.show()
    wait_until(lambda: dialog.state != "probing")
    pump(80)
    card = dialog.findChild(QWidget, "dialogCard")
    assert card is not None and card.property("card") is True
    image = dialog.grab().toImage()
    ground = image.pixelColor(3, 3).name().upper()
    inside = image.pixelColor(card.x() + 6, card.y() + card.height() // 2).name().upper()
    assert ground == theme.NIGHT.hex("ground")
    assert inside == theme.NIGHT.hex("surface")
    assert image.pixelColor(card.x() + 2, card.y() + 2).name().upper() == ground  # the rounded corner
    assert dialog.download_button.property("primary") is True
    assert dialog.cancel_button.property("quiet") is True
    assert dialog.cancel_button.property("primary") is False
    dialog.close()


def test_a_focused_cancel_does_not_turn_into_a_second_primary_pill(styled, ui_queue) -> None:
    theme.apply(styled, "night")
    dialog = _quality(ui_queue)
    dialog.show()
    wait_until(lambda: dialog.state != "probing")
    dialog.cancel_button.setFocus()
    pump(60)
    shot = dialog.cancel_button.grab().toImage()
    fill = shot.pixelColor(shot.width() // 2, 4)  # inside the pill, above the text
    assert fill.name().upper() != theme.NIGHT.hex("primary")
    assert fill.alpha() == 0 or fill.name().upper() in (theme.NIGHT.hex("surface"), theme.NIGHT.hex("ground"))
    dialog.close()


def test_dialog_styles_have_no_gradient_glow_or_shadow(styled, ui_queue, tmp_path) -> None:
    for palette in (theme.NIGHT, theme.DAY):
        sheet = theme.build_stylesheet(palette).lower()
        for banned in ("gradient", "glow", "shadow", "blur"):
            assert banned not in sheet, banned
    window = MainWindow(ui_queue, settings_path=tmp_path / "s.json", version_fn=lambda: "1",
                        tray_factory=lambda w: None)
    probe = lambda url: {"title": "T", "entries": [], "formats": []}
    dialogs = [_quality(ui_queue), PlaylistDialog("https://y.t/p", ui_queue, probe),
               SignInDialog(detect_fn=lambda: []), window.build_shortcuts_dialog()]
    try:
        for dialog in dialogs:
            for widget in [dialog, *dialog.findChildren(QWidget)]:
                sheet = widget.styleSheet().lower()
                assert "gradient" not in sheet and "shadow" not in sheet and "glow" not in sheet
                assert widget.graphicsEffect() is None  # no drop shadow or blur effect
            assert dialog.findChild(QWidget, "dialogCard") is not None
    finally:
        for dialog in dialogs:
            dialog.deleteLater()
        window.bridge.close()
        window.deleteLater()


def test_confirm_boxes_have_a_primary_and_quiet_buttons(qapp, ui_queue, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox
    page = HistoryPage(ui_queue)
    seen = {}

    def fake_exec(self):
        seen["props"] = {b.text(): (b.property("primary"), b.property("quiet")) for b in self.buttons()}
        seen["icon"] = self.icon()

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    page._confirm_delete()
    assert seen["props"] == {"Delete entry": (True, False), "Cancel": (False, True)}
    assert seen["icon"] == QMessageBox.Icon.NoIcon
    page.deleteLater()


# -- leftovers ----------------------------------------------------------------------------
def test_download_button_is_named_download(qapp, ui_queue, tmp_path) -> None:
    window = MainWindow(ui_queue, settings_path=tmp_path / "s.json", version_fn=lambda: "1",
                        tray_factory=lambda w: None)
    try:
        assert window.add_button.text() == "Download"
        assert window.add_button.accessibleName() == "Download"  # label in name
        assert window.paste_button.accessibleName() == "Paste"
        assert window.options_button.accessibleName() == "Options"
        assert window.url_edit.accessibleName() == "Video link"
    finally:
        window.bridge.close()
        window.deleteLater()


@pytest.mark.parametrize("palette_name", ["night", "day"])
def test_nothing_below_12_px_on_the_new_pages_and_dialogs(styled, ui_queue, tmp_path, palette_name) -> None:
    theme.apply(styled, palette_name)
    theme.set_base_size(styled, 11.0)  # the app's own minimum base size (14.7 px)
    page = SettingsPage(st.Settings(), ui_queue, None, version_fn=lambda: "1", detect_fn=lambda: [])
    hist = HistoryPage(ui_queue)
    ui_queue.history.add("https://www.youtube.com/watch?v=1", title="T", state="done")
    hist.refresh()
    quality = _quality(ui_queue)
    roots = [page, hist, quality, SignInDialog(detect_fn=lambda: [])]
    try:
        for root in roots:
            for widget in [root, *root.findChildren(QWidget)]:
                widget.ensurePolished()
                if isinstance(widget, (QLabel, QAbstractButton)) and widget.text():
                    assert QFontInfo(widget.font()).pixelSize() >= 12, (type(widget).__name__, widget.objectName())
        for font in widgets.QueueDelegate.row_fonts(styled.font()).values():
            assert QFontInfo(font).pixelSize() >= 12
        assert hist.delegate.heading_height(hist.table.font()) > 0
    finally:
        for root in roots:
            root.deleteLater()


def test_history_row_paints_flat_surface_and_raised_when_selected(styled, ui_queue) -> None:
    theme.apply(styled, "night")
    ui_queue.history.add("https://www.youtube.com/watch?v=1", title="Alpha", state="done")
    ui_queue.history.add("https://www.youtube.com/watch?v=2", title="Beta", state="done")
    page = HistoryPage(ui_queue)
    page.resize(900, 500)
    page.show()
    pump(80)
    page.table.selectRow(0)
    page.table.clearFocus()
    pump(60)
    image = page.table.viewport().grab().toImage()
    top = page.table.visualRect(page.model.index(0, 0))
    second = page.table.visualRect(page.model.index(1, 0))
    heading = page.delegate.heading_height(page.table.font())
    assert image.pixelColor(top.left() + 3, top.top() + heading + 40).name().upper() == theme.NIGHT.hex("raised")
    assert image.pixelColor(second.left() + 3, second.top() + 40).name().upper() == theme.NIGHT.hex("surface")
    page.hide()
    page.deleteLater()
