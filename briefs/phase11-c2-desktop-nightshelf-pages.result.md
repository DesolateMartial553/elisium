# Brief 11C-2 result - desktop Night shelf: History, Settings, dialogs, leftovers

Status: DONE (finished and verified by Claude after the agent stopped).

## Done
- History page: day groups (Today / Yesterday / dated), pill search, site filter menu, Night shelf rows, state as a coloured word, painted Open / Show in folder / Download again links, emoji removed (STATUS_TEXT plain words, "File missing").
- Settings page: five grouped surface lists (Downloads, Photos and music, Accounts, Appearance, About), one setting per row, control fill, switches, "glow" text removed.
- Dialogs: surface card (radius 16) on ground, one inverted primary pill, quiet secondary buttons, no gradient/glow/shadow. QMessageBox icons removed.
- Leftovers: Download button accessible name "Download"; render_screenshots.py runs directly (forces offscreen); selected-row tone contrast centralised (state_text_colour) and tested.
- Docs text: README.md, desktop/ACCESSIBILITY.md.
- Tests: updated pinned tests, new desktop/tests/test_nightshelf_pages.py.

## Checks actually run
- Targeted: test_nightshelf_pages.py + test_ui_a11y.py = 75 passed; test_theme/test_ui_model/test_ui_pages/test_ui_quality = 180 passed.
- Full `cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q`: `904 passed, 2 skipped in 878.95s` (EXIT 0). `python3 design/nightshelf/contrast_check.py`: ALL PASS. `python3 desktop/tools/render_screenshots.py` (no wrapper): wrote all 24 PNGs into `docs/screenshots/` (queue, empty, history, settings, choose-quality, playlist; night/day, normal/large). Claude viewed history-night, settings-night, choose-quality-day.
- contrast_check.py: not re-run after changes. render_screenshots.py: ran into a scratch dir only (all 24 files written, viewed night/day history, settings, dialogs); NOT written to docs/screenshots.

## Notes
- First renderer run used the real Wayland session (script did not force offscreen) and briefly opened windows on the desktop; fixed.
- Photos and music rows are read-only text (no such setting exists yet).
- Selected-row thumbnail placeholder blends into the raised fill.
