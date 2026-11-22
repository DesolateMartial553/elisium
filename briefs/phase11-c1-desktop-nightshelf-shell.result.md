# Brief 11C-1 result - desktop Night shelf: theme, shell and Downloads screen

Implemented by Claude (OpenCode was out of usage). Not committed.

## Acceptance (real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
855 passed, 2 skipped in 365.19s (0:06:05)

python3 design/nightshelf/contrast_check.py
... ALL PASS
```

## Files changed
- `desktop/elisium_downloader/ui/theme.py` - Night shelf tokens (hand-copied, equality-tested), flat QSS, Hanken Grotesk, no gradients/glow/shadow/violet; QSS font sizes in `em` so 200% text still scales.
- `desktop/elisium_downloader/ui/widgets.py` - rewritten: `draw_mark`/`app_icon` (mark on black rounded square), `BrandMark`, `CountCard(s)`, new `QueueDelegate` (80 px row, thumb 112x63, 4 px flat bar, right column) with `geometry()`, `EnterAnimation` (200 ms, 6 px rise), `ProgressEase`, flat `paint_bar`, restyled `HistoryDelegate` (look only), `EmptyState` (mark + sentence). Removed `Breath`, glow gradients, `HorizonHeader`, `GlowProgress`, `caption_parts`.
- `desktop/elisium_downloader/ui/main_window.py` - 48 px top bar (no sidebar), `nav` list (replaces `sidebar`, still named "Sections"), count cards + `StateFilterProxy`, `CardActions` reworked (icon buttons, inverted pill on failed rows, "Open" / "Show in folder" links on done rows), new `launch_action`, 1 px rule under the bar once the list scrolls.
- `desktop/elisium_downloader/ui/model.py` - `STATE_WORD`, `FILTERS`, `describe_row`, `site_name`, `eta_text`, `StateFilterProxy`; `percent_of` falls back to files_done/files_total.
- `desktop/elisium_downloader/ui/thumbnail.py` - `row_placeholder` (raised block + site name in faint), `ThumbnailCache`, tokens renamed.
- `desktop/elisium_downloader/ui/fonts/` - Inter TTFs and `OFL-Inter.txt` deleted (package-data glob `ui/fonts/*` unchanged and still right).
- Tests updated/added: `tests/test_theme.py` (rewritten head: tokens both schemes, contrast, Hanken family, nothing below 12 px, no gradient/glow/shadow in code and stylesheet, flat bar pixels, count cards filter, arrow keys, row text per state, note, pill Sign in/Retry, done links, placeholder, icon), `test_ui_main_window.py`, `test_ui_a11y.py` (tab order now Sections, Video link, Paste, Add, Options, card, Downloads, row buttons, toolbar), `test_ui_pages.py` (`sidebar` -> `nav`).
- `docs/screenshots/queue-{night,day}{,-large}.png` and `empty-{night,day}{,-large}.png` regenerated (8 files).

## Deviations and notes
- `desktop/tools/render_screenshots.py` was NOT edited (not in the brief's list) but it breaks on the new tokens (`thumb_bytes()` uses `glowA`/`glowC`). I ran it through a scratchpad wrapper (`.../scratchpad/shots_wrapper.py`) that swaps in a flat thumbnail, Night shelf sample rows (incl. a 3-of-7 photo post, sign-in failure, a note) and per-link fake thumbnails. The script needs a 3-line fix before it is run directly again (11C-2 or a follow-up).
- Tokens are hand-copied and equality-tested against `design/nightshelf/tokens.json`, not read at runtime: `design/` is not packaged (same as Afterglow today).
- Queue snapshots carry no thumbnail URL and no format, so rows show the placeholder block and "Site · size" (or "Site · N of M files"), not "1080p MP4". `ThumbnailCache` already loads a `thumbnail` field if the engine ever adds one (the screenshots use that). Engine untouched.
- `STATUS_TEXT` (emoji) is kept for the History page (11C-2) and its test; the Downloads rows use new emoji-free `STATE_WORD`.
- The Download button's accessible name stays "Add" (AGENTS.md: keep every name) though its visible text is "Download"; consider renaming to "Download" for label-in-name in 11C-2. Paste and Options... remain as real quiet buttons in the top bar (not in the mockup).
- The Pause/Resume/Retry/Cancel/Open folder toolbar is kept (names/tab order) but restyled quiet and moved below the list.
- Done rows got a new card-only "Open" button (opens the file, `launch_action`); `card_action_kinds("done")` is now `["launch", "open"]`.
- Selected row = `raised` fill; where a tone is under 4.5:1 there (day `positive`) text falls back to `text`. History chips use `ground` pills.
- `settings_page.py:294` still says "glow breathing"; `README.md`/`ACCESSIBILITY.md` still mention Inter/Afterglow (not in scope).
- Not regenerated (11C-2): history/settings/choose-quality/playlist screenshots; they already pick up the new theme via QSS.
