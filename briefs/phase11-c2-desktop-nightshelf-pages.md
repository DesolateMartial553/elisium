# Brief 11C-2 - Desktop restyle to Night shelf: History, Settings, dialogs, leftovers

Read `AGENTS.md`, `design/nightshelf/DESIGN.md`, `design/nightshelf/tokens.json`, then
`briefs/phase11-c1-desktop-nightshelf-shell.result.md` (what 11C-1 built: theme.py, widgets.py, top bar, count cards,
QueueDelegate, `describe_row`, `ThumbnailCache`). The owner-approved picture of History and Settings is
`.taste-skill/mock/pub/screens.html` (HTML only as a picture; build with Qt widgets/QSS/QPainter) and
https://claude.ai/artifact/KpTfdZAD13xd6qPYApJM8F.
Edit only: `desktop/elisium_downloader/ui/*.py` (history page, settings_page.py, dialogs: choose quality, playlist, sign-in,
options, about; theme.py/widgets.py/model.py as needed), `desktop/tools/render_screenshots.py` (fix it), the tests that pin
the old look, `docs/screenshots/` (regenerate), `desktop/README.md`/`ACCESSIBILITY.md`/`README.md` mentions of Inter and
Afterglow (text only), and write `briefs/phase11-c2-desktop-nightshelf-pages.result.md`. Do NOT touch the engine, Android,
`design/`, or the Downloads page layout (done in 11C-1) except for the two fixes under "Leftovers". No commit/push, sudo, network.

## Build
1. **History page** per screens.html: grouped by day (Today / Yesterday / date headings, 13 `faint`), search field (pill,
   `surface`), site filter (quiet text menu, not a coloured chip), rows with the same anatomy as download rows (thumbnail
   placeholder, title 15/600, meta 13 `faint`, no progress bar), actions "Open", "Show in folder", "Download again" as quiet
   text links, the status as a WORD in colour (Done `positive`, Failed `negative`), never emoji. Remove `STATUS_TEXT` emoji
   and update the test that pins it. Selected row = `raised`.
2. **Settings page** per screens.html: grouped lists on `surface` (radius 16), one setting per row (label 14/600 left,
   control right, helper text 13 `faint` under the label), group headings 13/600 `muted` sentence case (no uppercase
   letter-spaced). Groups: Downloads, Photos and music, Accounts, Appearance, About. Keep every existing setting, its
   accessible name and its keyboard order. Switches/checkboxes/combos: flat, `control` fill, focus ring 2 px `focus`.
   Remove the "glow breathing" text (`settings_page.py` ~line 294); "Reduce motion" keeps working.
3. **Dialogs** (choose quality, playlist picker, sign-in, options, about, errors): `surface` on `ground`, radius 16, a soft
   shadow is allowed ONLY on the dialog itself (it floats), inverted primary pill, quiet secondary text button, no gradients.
4. **Leftovers from 11C-1:** (a) rename the Download button's accessible name to "Download" (it shows "Download";
   update tests/a11y names and any shortcut docs); (b) fix `desktop/tools/render_screenshots.py` so it runs directly with
   the Night shelf tokens (it crashes on removed `glowA`/`glowC`): flat thumbnails, Night shelf sample rows, so nobody needs
   a wrapper; (c) the selected-row `positive` text contrast in day mode is under 4.5:1: choose colours so every state text
   passes against its row fill in both schemes (extend `contrast_check.py` pairs ONLY by adding pairs, in `design/` is
   read-only for you: instead assert it in a test using the tokens).
5. Docs text: replace Inter / Afterglow mentions in README.md, ACCESSIBILITY.md; no new claims.

## Tests and checks
Update pinned tests; add: History grouping by day, search and site filter narrow the list, no emoji in any visible string
(scan the page widgets), Settings groups present with all prior controls reachable, dialogs have no gradient/glow, accessible
names unchanged except Download, nothing below 12 px, both schemes.

## Acceptance (paste real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
python3 design/nightshelf/contrast_check.py
python3 desktop/tools/render_screenshots.py   # must run with no wrapper
```
List the screenshot files regenerated (history-*, settings-*, choose-quality-*, playlist-* in night, day, large). View them
against the mockups and fix differences before reporting. Write the result file even if low on budget.
