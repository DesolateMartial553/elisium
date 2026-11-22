# Brief 11C-1 - Desktop restyle to Night shelf: theme, shell and Downloads screen

Read `AGENTS.md`, then `design/nightshelf/DESIGN.md` and `design/nightshelf/tokens.json` (the target, owner-approved for
desktop and phone), then look at the approved mockups' source: `.taste-skill/mock/pub/index.html` section "A" and
`.taste-skill/mock/pub/screens.html` (HTML only as a picture of the target; build it with Qt widgets/QSS/QPainter).
Edit only: `desktop/elisium_downloader/ui/theme.py`, `ui/widgets.py`, `ui/main_window.py`, `ui/thumbnail.py`, `ui/model.py`
(display fields only), `ui/app.py` (font/theme loading only), the tests that pin the old look
(`desktop/tests/test_theme.py`, `test_ui_quality.py`, `test_ui_a11y.py` and any other test that asserts Afterglow
colours, the gradient, the sidebar or Inter: UPDATE them to Night shelf, never delete coverage), `docs/screenshots/`
(regenerate), and write `briefs/phase11-c1-desktop-nightshelf-shell.result.md`. Do NOT touch History, Settings or the
dialogs' layouts (11C-2), the engine, Android, or `design/` (except reading). No commit/push, no sudo, no network.

## Build
1. **Theme from `design/nightshelf/tokens.json`** (read at runtime like today's tokens.json, dark + light, follow the system
   scheme, the existing System/Night/Day override keeps working). Remove every gradient, glow, breathing animation and
   violet value from theme.py/widgets.py (`Breath`, `_glow_gradient`, `paint_glow_bar` glow parts, gradient wordmark).
   No `QGraphicsDropShadowEffect` on anything at rest.
2. **Font:** load `ui/fonts/HankenGrotesk-{Regular,SemiBold,Bold}.ttf` (already in the folder, OFL text next to them)
   instead of Inter; delete the Inter TTFs and `OFL-Inter.txt` from `ui/fonts/` and from package-data if listed. Hanken's
   digits are already equal width, so numbers stay steady. Sizes per DESIGN.md (title 20, row title 15/600, figure 24/600,
   body 14, meta 13, small 12; nothing below 12).
3. **Shell: top bar, no sidebar.** 48 px bar on the ground colour, no border: the mark (three stacked rounded bars, the
   shortest in `hue`, drawn with QPainter) + "Elisium" 18/700, then text links Downloads / History / Settings (14/600,
   `faint`, active `text`, no pill behind it; keyboard focusable, same shortcuts as today's sidebar), and on the right the
   link field (pill, 36 px, `surface`) + the Download button (inverted pill: white on black at night, black on white by day).
   The current sidebar's pages stay as pages in a QStackedWidget; only navigation moves to the bar.
4. **Count cards = filters** above the list: All, Downloading, Waiting (queued + paused), Failed, Done; 5 equal cards,
   61 px, `surface`, radius 14, 13 px label over a 16/600 count, the selected one with a 1.5 px `hue` outline. Clicking
   filters the list (a QSortFilterProxyModel on state). Zero prints as 0. Keyboard: arrow keys move between cards.
5. **Download row** (rewrite `QueueDelegate`): 80 px, `surface`, radius 16, 8 px gap; thumbnail 112 x 63 radius 10 from
   `thumbnail.py` (placeholder: a `raised` block with the site name in `faint`, never an icon); title 15/600 one line elided;
   meta line 13 `faint` ("YouTube · 1080p MP4 · 648.5 MB", or with files_done/files_total "Instagram · 6 photos + song ·
   3 of 7 files"); 4 px bar `hue` on `track`; right column percent 24/600 over "4.2 MB/s · 1 min 37 s left" 12 `muted`.
   States exactly as DESIGN.md "Row states" (Paused bar `faint`; Waiting; Failed reason in `negative` + one inverted pill
   with the fix; Done in `positive` + Open · Show in folder). Show the item's `note` (from 10B-2) under the meta line when set.
   Keep the per-card action buttons and every accessible name/role/shortcut the current rows have.
6. **Motion:** 120-200 ms ease-out; a new row fades in with a 6 px rise; progress eases; no loops. "Reduce motion" = instant.
7. **Empty state:** "Paste a link from YouTube, Instagram, TikTok…" in the list area with the mark, no clip-art.
8. **Tray/app icon:** the same mark on a black rounded square (QPainter), replacing the glow icon.

## Tests and checks
Update the Afterglow-pinning tests to the new tokens/look; add tests: tokens loaded for both schemes, no gradient brushes
used by the delegates (assert the painter calls or the palette), filter cards filter the model, row state text for each
state, note shown, font family is Hanken Grotesk, nothing below 12 px. `python3 design/nightshelf/contrast_check.py` ALL PASS.
Regenerate `docs/screenshots/queue-*.png` and `empty-*.png` (night + day, normal + large) with the existing offscreen
screenshot script/test.

## Acceptance (paste real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
python3 design/nightshelf/contrast_check.py
```
List the screenshot files you regenerated. Write the result file even if low on budget.
