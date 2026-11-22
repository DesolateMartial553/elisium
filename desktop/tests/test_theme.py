"""Night shelf theme: tokens, contrast, schemes, flat progress, rows, count cards, motion, settings."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontInfo, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from elisium_downloader.ui import settings as st
from elisium_downloader.ui import theme, widgets
from elisium_downloader.ui.main_window import SIGN_IN_CODES, MainWindow
from elisium_downloader.ui.model import (
    FILTERS,
    STATE_WORD,
    StateFilterProxy,
    DownloadModel,
    describe_row,
    eta_text,
    site_name,
)

from conftest import make_snapshot

DESIGN = Path(__file__).resolve().parents[2] / "design" / "nightshelf"
UI = Path(__file__).resolve().parents[1] / "elisium_downloader" / "ui"


def _contrast_module():
    spec = importlib.util.spec_from_file_location("contrast_check_mod", DESIGN / "contrast_check.py")
    mod = importlib.util.module_from_spec(spec)
    import sys
    argv, sys.argv = sys.argv, ["x"]
    try:
        with pytest.raises(SystemExit):
            spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


@pytest.fixture
def styled(qapp):
    yield qapp
    theme.reset(qapp)


@pytest.fixture
def window(qapp, ui_queue):
    win = MainWindow(ui_queue, version_fn=lambda: "t", tray_factory=lambda w: None)
    yield win
    win.bridge.close()
    win.deleteLater()


def test_tokens_equal_nightshelf_tokens_json() -> None:
    data = json.loads((DESIGN / "tokens.json").read_text())
    assert theme.TOKENS["dark"] == data["dark"]
    assert theme.TOKENS["light"] == data["light"]
    assert theme.RADIUS == data["radius"]
    assert dict(theme.SPACE) == data["space"]
    assert theme.MOTION["fastMs"] == data["motion"]["fastMs"]
    assert theme.MOTION["baseMs"] == data["motion"]["baseMs"]
    for key, value in data["size"].items():
        assert theme.SIZE[key] == (tuple(value) if isinstance(value, list) else value), key
    assert theme.TYPE["family"] == data["type"]["family"]
    assert theme.TYPE["minimum"] == data["type"]["minimum"]


def test_nightshelf_contrast_check_prints_all_pass() -> None:
    import subprocess
    import sys
    out = subprocess.run([sys.executable, str(DESIGN / "contrast_check.py")],
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0 and out.stdout.strip().endswith("ALL PASS")


@pytest.mark.parametrize("palette", [theme.NIGHT, theme.DAY])
def test_stylesheet_colour_pairs_meet_contrast(palette) -> None:
    cc = _contrast_module()
    by_hex = {v.upper(): k for k, v in palette.tokens.items()}
    sheet = theme.build_stylesheet(palette)
    checked = 0
    for block in re.findall(r"\{([^{}]*)\}", sheet):
        decl = dict(
            (a.strip(), b.strip().upper())
            for a, _, b in (d.partition(":") for d in block.split(";") if ":" in d)
        )
        pairs = []
        fg = decl.get("color")
        bg = decl.get("background") or decl.get("background-color")
        if fg in by_hex:
            backgrounds = [bg] if bg in by_hex else [palette.hex(k).upper() for k in ("ground", "surface", "raised")]
            pairs += [(fg, b) for b in backgrounds]
        sel_fg, sel_bg = decl.get("selection-color"), decl.get("selection-background-color")
        if sel_fg in by_hex and sel_bg in by_hex:
            pairs.append((sel_fg, sel_bg))
        for f, b in pairs:
            assert cc.ratio(f, b) >= 4.5, (by_hex[f], by_hex[b], cc.ratio(f, b))
            checked += 1
    assert checked > 20


@pytest.mark.parametrize("palette", [theme.NIGHT, theme.DAY])
@pytest.mark.parametrize("state", sorted(widgets._CHIP_KEY))
def test_state_chips_are_readable(palette, state) -> None:
    cc = _contrast_module()
    bg, fg = widgets.chip_colours(state, palette)
    assert cc.ratio(fg.name(), bg.name()) >= 4.5


@pytest.mark.parametrize("palette", [theme.NIGHT, theme.DAY])
@pytest.mark.parametrize("tone", ["muted", "faint", "positive", "negative", "text"])
def test_row_text_tones_are_readable_on_surface_and_raised(palette, tone) -> None:
    cc = _contrast_module()
    assert cc.ratio(palette.hex(tone), palette.hex("surface")) >= 4.5
    # a selected row is lifted to raised; a tone that is too faint there falls back to text
    shown = widgets.legible_colour(palette, tone, "raised")
    assert cc.ratio(shown.name(), palette.hex("raised")) >= 4.5


def test_resolve_scheme() -> None:
    S = Qt.ColorScheme
    assert theme.resolve_scheme("night", S.Light) is theme.NIGHT
    assert theme.resolve_scheme("day", S.Dark) is theme.DAY
    assert theme.resolve_scheme("system", S.Light) is theme.DAY
    assert theme.resolve_scheme("system", S.Dark) is theme.NIGHT
    assert theme.resolve_scheme("system", S.Unknown) is theme.NIGHT
    assert theme.resolve_scheme("bogus", S.Unknown) is theme.NIGHT


@pytest.mark.parametrize("setting,palette", [("night", theme.NIGHT), ("day", theme.DAY)])
def test_app_starts_in_both_schemes(styled, ui_queue, tmp_path, setting, palette) -> None:
    theme.apply(styled, setting)
    assert theme.current() is palette
    assert styled.palette().color(styled.palette().ColorRole.Window).name().upper() == palette.hex("ground")
    window = MainWindow(ui_queue, settings=st.Settings(appearance=setting),
                        version_fn=lambda: "t", tray_factory=lambda w: None)
    window.show()
    QApplication.processEvents()
    assert window.grab().width() > 100
    window.bridge.close()


def test_system_override_keeps_working(styled) -> None:
    for setting, palette in (("night", theme.NIGHT), ("day", theme.DAY)):
        theme.apply(styled, setting)
        assert theme.current() is palette
    assert theme.apply(styled, "nonsense") is theme.resolve_scheme("system")


# -- font, sizes, flatness ---------------------------------------------------------
def test_font_family_is_hanken_grotesk(styled) -> None:
    assert theme.FAMILY == "Hanken Grotesk"
    assert theme.load_fonts()
    assert "Hanken Grotesk" in QFontDatabase.families()
    assert not list((UI / "fonts").glob("Inter*")) and not (UI / "fonts" / "OFL-Inter.txt").exists()
    assert (UI / "fonts" / "OFL-HankenGrotesk.txt").exists()
    theme.apply(styled, "night")
    assert styled.font().family() == "Hanken Grotesk"
    assert 'font-family: "Hanken Grotesk"' in theme.build_stylesheet(theme.NIGHT)
    assert QFontInfo(widgets.QueueDelegate.row_fonts(styled.font())["title"]).family() == "Hanken Grotesk"


def test_nothing_below_12_px(styled) -> None:
    for palette in (theme.NIGHT, theme.DAY):
        sheet = theme.build_stylesheet(palette)
        for size in re.findall(r"font-size:\s*([\d.]+)px", sheet):
            assert float(size) >= 12, size
        for em in re.findall(r"font-size:\s*([\d.]+)em", sheet):
            assert float(em) * theme.TYPE["body"] >= 12, em  # em of the 14 px body size
    for font in widgets.QueueDelegate.row_fonts(styled.font()).values():
        assert QFontInfo(font).pixelSize() >= 12
    assert min(theme.TYPE[k] for k in ("title", "rowTitle", "figure", "body", "meta", "small")) >= 12


def test_no_gradients_glows_breathing_or_shadows_in_the_code() -> None:
    banned = re.compile(r"QLinearGradient|QRadialGradient|QConicalGradient|qlineargradient|"
                        r"qradialgradient|DropShadow|glow[A-C]\b|Breath|HorizonHeader")
    for name in ("theme.py", "widgets.py", "main_window.py", "thumbnail.py", "model.py"):
        assert not banned.search((UI / name).read_text()), name
    for palette in (theme.NIGHT, theme.DAY):
        sheet = theme.build_stylesheet(palette).lower()
        assert "gradient" not in sheet and "shadow" not in sheet
        violet = {"#B388FF", "#C4A1FF", "#6B3FD4", "#7C4DFF"}
        assert not violet & {v.upper() for v in re.findall(r"#[0-9a-fA-F]{6}", sheet)}


@pytest.mark.parametrize("state", ["queued", "downloading", "paused", "done", "failed"])
@pytest.mark.parametrize("percent", [0.0, 37.0, 100.0])
def test_flat_progress_bar_paints(state, percent) -> None:
    image = QImage(220, 40, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    widgets.paint_bar(painter, QRectF(10, 16, 200, 4), percent / 100.0, "hue", theme.NIGHT)
    painter.end()
    assert any(image.pixelColor(x, 18).alpha() for x in range(10, 210, 5))


def test_bar_is_flat_hue_on_track_and_faint_when_paused() -> None:
    def pixel(fill, x):
        image = QImage(220, 40, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.black)
        painter = QPainter(image)
        widgets.paint_bar(painter, QRectF(10, 16, 200, 4), 0.5, fill, theme.NIGHT)
        painter.end()
        return image.pixelColor(x, 18).name().upper()
    filled = {pixel("hue", x) for x in range(25, 100, 7)}
    assert filled == {theme.NIGHT.hex("hue")}  # one flat colour, no gradient or glow
    assert pixel("hue", 180) == theme.NIGHT.hex("track")
    assert pixel("faint", 50) == theme.NIGHT.hex("faint")


def test_a_painted_row_uses_only_flat_colours(window) -> None:
    window.model.load([make_snapshot(1, "downloading", title="Clip",
                                     progress={"percent": 60.0, "speed": 1e6, "eta": 5})])
    window._refresh_ui()
    window.resize(900, 520)
    window.show()
    QApplication.processEvents()
    theme.set_reduce_motion(True)
    try:
        image = window.table.viewport().grab().toImage()
    finally:
        theme.set_reduce_motion(False)
    geo = window.delegate.geometry(window.table.visualRect(window.proxy.index(0, 0)),
                                   window.model.snapshot_at(0), window.table.font())
    y = int(geo.bar.center().y())
    x0 = int(geo.bar.left() + 6)
    inside = {image.pixelColor(x, y).name().upper() for x in range(x0, int(geo.bar.left() + geo.bar.width() * 0.5), 9)}
    assert inside == {theme.current().hex("hue")}


def test_delegate_height_grows_with_font_scale(qapp) -> None:
    d = widgets.QueueDelegate()
    small = QFont(qapp.font())
    big = QFont(small)
    big.setPointSizeF(small.pointSizeF() * 2)
    assert d.row_height(big) > d.row_height(small) * 1.5
    assert d.row_height(small) >= theme.SIZE["rowHeight"]  # 80 px row plus the 8 px gap
    h = widgets.HistoryDelegate()
    assert h.row_height(big) > h.row_height(small) * 1.5


# -- motion ---------------------------------------------------------------------------
def test_progress_eases_and_is_instant_with_reduced_motion(qapp, monkeypatch) -> None:
    monkeypatch.delenv("ELISIUM_REDUCE_MOTION", raising=False)
    ease = widgets.ProgressEase()
    theme.set_reduce_motion(False)
    assert ease.value_for(1, 10.0) == 10.0  # the first value is drawn as it is
    midway = ease.value_for(1, 50.0)
    assert 10.0 <= midway < 50.0 and ease.active
    ease.stop()
    theme.set_reduce_motion(True)
    try:
        assert ease.value_for(2, 5.0) == 5.0 and ease.value_for(2, 80.0) == 80.0
    finally:
        theme.set_reduce_motion(False)


def test_one_animation_serves_all_rows(qapp) -> None:
    assert widgets.progress_ease() is widgets.progress_ease()
    assert widgets.enter_animation() is widgets.enter_animation()
    assert widgets.EnterAnimation.RISE_PX == 6.0 and widgets.EnterAnimation.DURATION_MS == 200
    for anim in (widgets.enter_animation(), widgets.progress_ease()):
        assert anim.loopCount() == 1  # nothing loops, nothing breathes


# -- count cards = filters ----------------------------------------------------------------
def _states_window(window):
    states = ["downloading", "merging", "queued", "paused", "queued", "failed", "done", "done", "cancelled"]
    window.model.load([make_snapshot(i + 1, state, title=f"T{i + 1}") for i, state in enumerate(states)])
    window._refresh_ui()
    return window


def test_count_cards_show_the_counts_and_zero_prints_as_0(window) -> None:
    assert [window.cards.cards[k].count for k in FILTERS] == [0, 0, 0, 0, 0]
    _states_window(window)
    assert {k: window.cards.cards[k].count for k in FILTERS} == {
        "all": 9, "downloading": 2, "waiting": 3, "failed": 1, "done": 2}
    assert window.cards.cards["failed"].accessibleName() == "Failed: 1"
    window.model.load([])
    window._refresh_ui()
    assert window.cards.cards["done"].accessibleName() == "Done: 0"


def test_count_cards_filter_the_list(window) -> None:
    _states_window(window)
    expected = {"all": 9, "downloading": 2, "waiting": 3, "failed": 1, "done": 2}
    for key, rows in expected.items():
        window.cards.cards[key].click()
        assert window.proxy.filter_key == key
        assert window.proxy.rowCount() == rows, key
    window.cards.cards["waiting"].click()
    assert {window.proxy.snapshot_at(r)["state"] for r in range(window.proxy.rowCount())} == {"queued", "paused"}
    # a row picked in the filtered list is the right download, and the source is untouched
    window.table.selectRow(2)
    assert window.selected_snapshot()["id"] == 5 and window.model.rowCount() == 9
    window.cards.cards["all"].click()
    assert window.proxy.rowCount() == 9


def test_arrow_keys_move_between_the_cards(window) -> None:
    window.show()
    window.cards.cards["all"].setFocus()
    QApplication.processEvents()
    QTest.keyClick(window.cards.cards["all"], Qt.Key.Key_Right)
    assert window.cards.current_key() == "downloading"
    assert window.proxy.filter_key == "downloading"
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Right)
    assert window.cards.current_key() == "waiting"
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Left)
    assert window.cards.current_key() == "downloading"
    window.hide()


def test_filtered_empty_list_says_why(window) -> None:
    _states_window(window)
    window.model.load([make_snapshot(1, "done", title="Only")])
    window._refresh_ui()
    window.cards.cards["failed"].click()
    assert window.proxy.rowCount() == 0 and window.empty_state.text == "No failed downloads right now"
    window.cards.cards["all"].click()
    window.model.load([])
    window._refresh_ui()
    assert window.empty_state.text.startswith("Paste a link from YouTube, Instagram, TikTok")


def test_state_filter_proxy_keeps_queue_order(qapp) -> None:
    model = DownloadModel()
    model.load([make_snapshot(i, s) for i, s in ((1, "done"), (2, "failed"), (3, "done"))])
    proxy = StateFilterProxy(model)
    proxy.set_filter("done")
    assert [proxy.item_id_at(r) for r in range(proxy.rowCount())] == [1, 3]
    model.upsert(make_snapshot(2, "done"))  # a state change re-filters live
    assert [proxy.item_id_at(r) for r in range(proxy.rowCount())] == [1, 2, 3]
    proxy.set_filter("nonsense")
    assert proxy.filter_key == "done"


# -- row text per state ------------------------------------------------------------------------
YT = "https://www.youtube.com/watch?v=a"
IG = "https://www.instagram.com/p/b/"


def test_site_names_and_times() -> None:
    assert site_name(YT) == "YouTube" and site_name(IG) == "Instagram"
    assert site_name("https://vm.tiktok.com/x") == "TikTok" and site_name("https://www.example.org/a") == "example.org"
    assert eta_text(7) == "7 s" and eta_text(97) == "1 min 37 s" and eta_text(3900) == "1 h 5 min"


def test_row_text_for_each_state() -> None:
    mib = 1024 * 1024
    running = describe_row(make_snapshot(1, "downloading", url=YT, progress={
        "percent": 37.0, "speed": 4.2 * mib, "eta": 97, "total_bytes": 648.5 * mib}))
    assert (running.meta, running.big, running.big_is_percent, running.sub, running.bar) == (
        "YouTube · 648.5 MB", "37%", True, "4.2 MB/s · 1 min 37 s left", "hue")
    photos = describe_row(make_snapshot(2, "downloading", url=IG, progress={
        "percent": 43.0, "speed": 1.9 * mib, "eta": 7, "files_done": 3, "files_total": 7}))
    assert photos.meta == "Instagram · 3 of 7 files" and photos.sub == "1.9 MB/s · 7 s left"
    paused = describe_row(make_snapshot(3, "paused", url=YT, progress={
        "percent": 54.0, "total_bytes": 295.6 * mib, "downloaded_bytes": 159.6 * mib}))
    assert paused.big == "54%" and paused.sub == "Paused · 136.0 MB to go" and paused.bar == "faint"
    waiting = describe_row(make_snapshot(4, "queued", url=YT))
    assert (waiting.big, waiting.sub, waiting.tone, waiting.bar) == ("Waiting", "Starts next", "faint", None)
    sized = describe_row(make_snapshot(5, "queued", url=YT, progress={"total_bytes": 1.24 * 1024 * mib}))
    assert sized.sub == "1.2 GB"
    failed = describe_row(make_snapshot(6, "failed", url=IG, error={
        "code": "session_expired", "message": "Instagram sign-in has expired", "fix": "Sign in"}))
    assert failed.sub == "Instagram sign-in has expired" and failed.tone == "negative" and failed.pill == "Retry"
    done = describe_row(make_snapshot(7, "done", url=YT, progress={"total_bytes": 14.2 * mib}))
    assert (done.big, done.sub, done.tone, done.meta) == ("Done", "Open · Show in folder", "positive", "YouTube · 14.2 MB")
    multi = describe_row(make_snapshot(8, "done", url=IG, progress={"files_done": 7, "files_total": 7}))
    assert multi.meta == "Instagram · 7 files"
    for state in STATE_WORD:  # every state has words, none has an icon character
        text = describe_row(make_snapshot(9, state, url=YT, error={"code": "x", "message": "m", "fix": ""}
                                           if state in ("failed", "skipped") else None))
        assert STATE_WORD[state].isalpha() and (text.big or text.sub)


def test_the_note_is_shown_under_the_meta_line(window) -> None:
    note = "Kept the full song: the video would have been cut short"
    snap = make_snapshot(1, "done", title="Clip", url=IG, note=note)
    assert describe_row(snap).note == note and describe_row(make_snapshot(2, "done")).note == ""
    window.model.load([snap])
    window._refresh_ui()
    rect = window.table.visualRect(window.proxy.index(0, 0))
    with_note = window.delegate.geometry(rect, snap, window.table.font())
    without = window.delegate.geometry(rect, dict(snap, note=None), window.table.font())
    assert with_note.note is not None and without.note is None
    assert with_note.note.top() >= with_note.meta.bottom()
    assert with_note.card.height() == without.card.height()


def test_failed_row_offers_one_pill_sign_in_or_retry(window) -> None:
    sign_in = make_snapshot(1, "failed", title="A", url=IG, error={
        "code": "session_expired", "message": "Instagram sign-in has expired", "fix": "Sign in"})
    plain = make_snapshot(2, "failed", title="B", url=YT, error={
        "code": "network", "message": "Network problem.", "fix": "Retry"})
    assert window.delegate.pill_text(sign_in) == "Sign in" and window.delegate.pill_text(plain) == "Retry"
    assert window.delegate.pill_text(make_snapshot(3, "done")) is None
    assert SIGN_IN_CODES == window.delegate.sign_in_codes
    window.model.load([sign_in, plain])
    window._refresh_ui()
    window.show()
    window.table.selectRow(0)
    QApplication.processEvents()
    button = window.card_actions.buttons["retry"]
    assert button.text() == "Sign in" and button.accessibleName() == "Sign in A"
    opened = []
    window.open_sign_in_dialog = lambda: opened.append(True)  # type: ignore[method-assign]
    button.click()
    assert opened == [True]
    window.table.selectRow(1)
    QApplication.processEvents()
    assert button.text() == "Retry" and button.accessibleName() == "Retry B"
    window.hide()


def test_done_row_has_open_and_show_in_folder_links(window) -> None:
    window.model.load([make_snapshot(1, "done", title="Clip", url=YT)])
    window._refresh_ui()
    window.show()
    window.table.selectRow(0)
    QApplication.processEvents()
    buttons = window.card_actions.buttons
    assert buttons["launch"].text() == "Open" and buttons["open"].text() == "Show in folder"
    assert buttons["launch"].accessibleName() == "Open Clip"
    assert buttons["open"].accessibleName() == "Open folder Clip"
    window.hide()


def test_placeholder_thumbnail_is_a_raised_block_with_the_site_name(qapp) -> None:
    from elisium_downloader.ui.thumbnail import row_placeholder
    theme.reset(qapp)
    pixmap = row_placeholder("YouTube", 112, 63, 1.0)
    image = pixmap.toImage()
    assert (pixmap.width(), pixmap.height()) == (112, 63)
    assert image.pixelColor(4, 31).name().upper() == theme.NIGHT.hex("raised")
    assert image.pixelColor(0, 0).alpha() == 0  # rounded corner, not a square block
    lit = {image.pixelColor(x, y).name().upper() for x in range(112) for y in range(63)}
    assert theme.NIGHT.hex("faint") in lit  # the site name is drawn in faint


def test_the_mark_and_the_icon_are_drawn_without_gradients(qapp) -> None:
    image = widgets.app_icon().pixmap(128, 128).toImage()
    assert image.pixelColor(1, 1).alpha() == 0  # a rounded square, not a full square
    assert image.pixelColor(64, 8).name().upper() == theme.NIGHT.hex("ground")  # on black
    assert image.pixelColor(45, 87).name().upper() == theme.NIGHT.hex("hue")  # shortest bar in hue
    first = image.pixelColor(60, 41)  # the longest bar: text at 35%, one flat value
    assert abs(first.red() - 89) <= 2 and first.red() == first.green() == first.blue()
    assert image.pixelColor(30, 41) == image.pixelColor(70, 41)  # flat along the bar


def test_queue_cards_keep_model_and_names(qapp, ui_queue) -> None:
    window = MainWindow(ui_queue, version_fn=lambda: "t", tray_factory=lambda w: None)
    window.model.load([make_snapshot(1, "downloading", title="Clip",
                                     progress={"percent": 37.0, "speed": 1e6, "eta": 5})])
    window._refresh_ui()
    assert window.table.accessibleName() == "Downloads"
    assert "37 percent" in window.model.index(0, 0).data(Qt.ItemDataRole.AccessibleTextRole)
    assert "37 percent" in window.proxy.index(0, 0).data(Qt.ItemDataRole.AccessibleTextRole)
    assert not window.empty_state.isVisibleTo(window)
    window.model.load([])
    window._refresh_ui()
    assert window.empty_state.isVisibleTo(window) or not window.isVisible()
    window.bridge.close()


# -- settings -------------------------------------------------------------------
def test_settings_defaults_and_old_files(tmp_path) -> None:
    s = st.Settings()
    assert s.appearance == "system" and s.reduce_motion is False
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"concurrency": 3, "notify_on_done": False}))
    loaded = st.load(old)
    assert loaded.concurrency == 3 and loaded.appearance == "system" and loaded.reduce_motion is False


def test_settings_round_trip_and_validation(tmp_path) -> None:
    path = tmp_path / "s.json"
    st.save(st.Settings(appearance="day", reduce_motion=True), path)
    back = st.load(path)
    assert back.appearance == "day" and back.reduce_motion is True
    path.write_text(json.dumps({"appearance": "neon", "reduce_motion": "yes"}))
    bad = st.load(path)
    assert bad.appearance == "system" and bad.reduce_motion is False


def test_settings_page_exposes_appearance_and_motion(qapp, ui_queue, tmp_path) -> None:
    from elisium_downloader.ui.settings_page import SettingsPage
    page = SettingsPage(st.Settings(), ui_queue, tmp_path / "s.json", lambda: "t")
    assert page.appearance_combo.accessibleName() == "Appearance"
    assert page.motion_check.accessibleName() == "Reduce motion"
    page.appearance_combo.setCurrentIndex(page.appearance_combo.findData("night"))
    page.motion_check.setChecked(True)
    saved = st.load(tmp_path / "s.json")
    assert saved.appearance == "night" and saved.reduce_motion is True
