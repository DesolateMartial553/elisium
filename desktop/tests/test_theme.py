"""Afterglow theme: tokens, contrast, schemes, glow progress, cards, reduced motion, settings."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from elisium_downloader.ui import settings as st
from elisium_downloader.ui import theme, widgets
from elisium_downloader.ui.main_window import MainWindow

from conftest import make_snapshot

DESIGN = Path(__file__).resolve().parents[2] / "design"


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


def test_tokens_equal_design_tokens_json() -> None:
    data = json.loads((DESIGN / "tokens.json").read_text())
    assert theme.TOKENS["dark"] == data["dark"]
    assert theme.TOKENS["light"] == data["light"]
    assert theme.RADIUS == data["radius"]
    assert list(theme.SPACE) == data["space"]
    assert theme.MOTION["fastMs"] == data["motion"]["fastMs"]


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
            backgrounds = [bg] if bg in by_hex else [palette.hex(k).upper() for k in ("bg", "surface", "raised")]
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
    assert styled.palette().color(styled.palette().ColorRole.Window).name().upper() == palette.hex("bg")
    window = MainWindow(ui_queue, settings=st.Settings(appearance=setting),
                        version_fn=lambda: "t", tray_factory=lambda w: None)
    window.show()
    QApplication.processEvents()
    assert window.grab().width() > 100
    window.bridge.close()


@pytest.mark.parametrize("state", ["queued", "downloading", "paused", "done", "failed"])
@pytest.mark.parametrize("percent", [0.0, 37.0, 100.0])
def test_glow_progress_paints(state, percent) -> None:
    image = QImage(220, 40, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    widgets.paint_glow_bar(painter, QRectF(10, 12, 200, 12), percent, state, theme.NIGHT, 0.7)
    painter.end()
    assert any(image.pixelColor(x, 18).alpha() for x in range(10, 210, 5))
    w = widgets.GlowProgress()
    w.resize(200, 20)
    w.set_progress(percent, state)
    assert w.grab().width() == 200
    assert w.accessibleDescription() == f"{percent:.0f} percent"


def test_done_and_failed_use_semantic_colours() -> None:
    def centre(state, percent):
        image = QImage(220, 40, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        widgets.paint_glow_bar(p, QRectF(10, 12, 200, 12), percent, state, theme.NIGHT)
        p.end()
        return image.pixelColor(30, 18).name().upper()
    assert centre("done", 100.0) == theme.NIGHT.hex("success")
    assert centre("failed", 50.0) == theme.NIGHT.hex("error")


def test_delegate_height_grows_with_font_scale(qapp) -> None:
    d = widgets.QueueDelegate()
    small = QFont(qapp.font())
    big = QFont(small)
    big.setPointSizeF(small.pointSizeF() * 2)
    assert d.row_height(big) > d.row_height(small) * 1.5
    h = widgets.HistoryDelegate()
    assert h.row_height(big) > h.row_height(small) * 1.5


def test_reduced_motion_stops_the_shared_animation(qapp, monkeypatch) -> None:
    monkeypatch.delenv("ELISIUM_REDUCE_MOTION", raising=False)
    anim = widgets.breath()
    theme.set_reduce_motion(False)
    anim.set_active(True)
    assert anim.state() == anim.State.Running
    theme.set_reduce_motion(True)
    assert anim.state() != anim.State.Running
    anim.set_active(True)
    assert anim.state() != anim.State.Running and anim.phase() == 0.5
    theme.set_reduce_motion(False)
    anim.set_active(False)
    assert anim.state() != anim.State.Running


def test_one_animation_serves_all_rows(qapp) -> None:
    assert widgets.breath() is widgets.breath()


def test_queue_cards_keep_model_and_names(qapp, ui_queue) -> None:
    window = MainWindow(ui_queue, version_fn=lambda: "t", tray_factory=lambda w: None)
    window.model.load([make_snapshot(1, "downloading", title="Clip",
                                     progress={"percent": 37.0, "speed": 1e6, "eta": 5})])
    window._refresh_ui()
    assert window.table.accessibleName() == "Downloads"
    assert "37 percent" in window.model.index(0, 0).data(Qt.ItemDataRole.AccessibleTextRole)
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
