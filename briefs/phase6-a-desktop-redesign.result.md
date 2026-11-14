# Brief 6A result: desktop "Afterglow" redesign

## Commands run (real output)
- `cd desktop && QT_QPA_PLATFORM=offscreen nice .venv/bin/python -m pytest -q` -> **495 passed, 1 skipped** (was 446 + 1; 49 new tests in `tests/test_theme.py`). Run with temp XDG dirs (read-only symlinks to the real gtk/qt6ct/fontconfig config so the default font matches the real desktop).
- `python3 ../design/contrast_check.py | tail -1` -> `ALL PASS 0`
- `QT_QPA_PLATFORM=offscreen nice .venv/bin/python tools/render_screenshots.py` -> 24 PNGs in `docs/screenshots/` (queue, empty, history, settings, choose-quality, playlist; night and day; normal and `-large` = 1.5x text). Old queue/history/settings/choose-quality/playlist PNGs deleted.
- Hard-coded colour grep (`#rrggbb`, `QColor("...")` outside `ui/theme.py`): no hits.

## Files
New: `ui/theme.py` (tokens, Palette, resolve_scheme, build_stylesheet, apply, Inter loading, QPalette, live system-scheme switch, generated switch/check/chevron images), `ui/widgets.py` (glow bar + GlowProgress widget, shared Breath QVariantAnimation, QueueDelegate/HistoryDelegate cards, state chips, HorizonHeader, EmptyState, painted toolbar icons and app icon, RowHeightKeeper), `tools/render_screenshots.py`, `tests/test_theme.py`.
Edited: `ui/main_window.py` (header, cards, toolbar moved into Downloads page, empty overlay, breathing, theme hooks; ProgressDelegate and the column hiding logic removed), `ui/history_page.py`, `ui/settings_page.py` (cards, Appearance combo System/Night/Day, Reduce motion switch, scroll area), `ui/settings.py` (`appearance`, `reduce_motion`; old files load), `ui/quality_dialog.py` / `ui/playlist_dialog.py` (margins, primary button, reduce_motion also honours the setting), `ui/thumbnail.py` (themed rounded placeholder), `ui/app.py` (applies theme + window icon), `packaging/elisium.svg` (new icon, valid, checked at 16/64/256), `tests/test_ui_a11y.py` and `tests/test_ui_main_window.py` (two tests that asserted old column visuals now assert card behaviour; no accessible-name/role/shortcut assertion weakened).

## What changed after looking at the screenshots
Fonts were silently DejaVu (the platform theme resets the app and per-class fonts on first show): fixed with per-class Inter, a fontChanged re-apply and a QSS font-family. Selection painted a lilac block behind cards (cards table now transparent). Sidebar had a stray accent frame (QSS `:focus::item` rule leaked onto the frame). Card rows were clipped at large text (row height now follows the font). Spin boxes squeezed/overlapping text, label columns misaligned, dialogs had no margins, "Select all" looked like the default button, header band was muddy brown (opacity lowered), stylesheet resets the palette (palette now set after the stylesheet).

## Deviations / notes
- Per-card action buttons not added (toolbar actions and shortcuts unchanged and still act on the selected card). Card enter animation (fade + rise) not implemented; only the breathing glow, which stops with Reduce motion / `ELISIUM_REDUCE_MOTION=1`.
- Selected card border is 1.6px gradient plus a 2px accent focus ring when the list has keyboard focus.
- State chips are tinted on `surface` (10%) because success on `raised` fails 4.5:1 in Day; checked in tests for all states, both schemes.
- Queue/history keep the 6/5-column models, only column 0 is visible (a card); the other columns are hidden, so names and accessible text are unchanged.
- Flaky pre-existing segfault in `tests/test_ipc.py::test_real_qt_client_round_trip` (crashes ~1 in 3 full runs, passes alone and on rerun); not touched.
- Tests need the normal desktop font config: with a bare temp XDG_CONFIG_HOME Qt falls back to DejaVu 12 pt and a stock QSpinBox trips the existing 200% clipping test.

## Unverified
Real Hyprland/Wayland rendering, real HyDE/qt6ct/Kvantum interaction (offscreen with symlinked qt6ct config only), live system dark/light switching, Orca, real tray menu look, breathing animation motion (only still frames seen).
