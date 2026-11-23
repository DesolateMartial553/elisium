# Brief 10G (desktop only) - bulk saves: whole profile, tabs, Saved, TikTok profile, in slow mode

Plan: `~/.claude/plans/elisium-posts-images-music-stories.md`, section "Brief 10G". Android bulk saves are deliberately NOT
built (they need a paginating Kotlin client that cannot be checked without a device and a real account, and a bad pull can
get a signed-in account flagged): say so in the result file. Read `AGENTS.md`, `core-spec/SPEC.md`,
`briefs/phase10-b1-desktop-media-engine.result.md`, `briefs/phase10-c-desktop-multifile-screens.result.md`,
`desktop/elisium_downloader/engine/media.py` and `queue.py`. Never import gallery_dl or read its source; run it only as a
separate process, like the engine already does.
Edit only: `desktop/elisium_downloader/engine/media.py`, `engine/queue.py`, `engine/errors.py`, `ui/settings*.py`,
`ui/main_window.py`, `ui/model.py`, the existing playlist dialog `ui/playlist_dialog.py`, tests, `core-spec/SPEC.md` (new rows
only), and write `briefs/phase10-g-desktop-bulk-saves.result.md`. No Android, no commit/push/sudo, no network in tests, no
real windows (offscreen), `nice`.

## Build
1. **Classify bulk URLs** in `classify_media_url`/`route_for`: Instagram profile (`/<user>/`), `/<user>/reels/`,
   `/<user>/tagged/`, `/<user>/saved/`, `/<user>/saved/<collection>/`, TikTok profile `/@user`. Single-post rules stay as they
   are (a profile must never be mistaken for a post and vice versa; test the table including odd cases like trailing slashes,
   query strings, `/stories/`, `/p/`, reserved paths such as `/explore/` and `/accounts/`).
2. **Count probe, then the picker.** A bulk probe lists posts without downloading (gallery-dl simulate/dump, with the
   request sleep below applied and a hard cap on how many entries it reads: the run cap + 1). Show the existing playlist
   dialog with the posts (title/date, count) and "newest N" / ranges / all, preselected newest 50, never more than the cap.
3. **Slow mode, always on for bulk** (not configurable off): pass gallery-dl's request sleep so requests are randomised 4-10 s
   apart (`sleep-request` as a range in the generated config), concurrency for the item is 1 post at a time, bulk items take
   one queue slot, and they never run in parallel with another signed-in Instagram/TikTok item. Cap per run: setting "Most
   posts per bulk save" (default 50, max 200, stored like other settings).
4. **Stop on the first rate limit**: any HTTP 429 / "please wait" / login-challenge text ends the run cleanly (state "paused"
   with the plain note "Instagram asked us to slow down. Saved N posts. Try again later.") keeping everything saved; a re-add
   resumes via the archive and skips saved posts without requesting them where gallery-dl's archive allows.
5. **One-time warning** before the first bulk run, a dialog with plain text ("Instagram may slow down or flag accounts that
   download a lot at once. Elisium saves one post at a time, slowly, and stops if Instagram asks it to slow down.") with
   "Start" (inverted pill) and "Cancel"; the "seen" flag is stored in settings. Nightshelf style, accessible names, keyboard.
6. **Progress/UX:** the row shows "Instagram · @user · 12 of 50 posts" using `files_done`/`files_total` semantics per post
   (keep the existing per-file count inside the current post out of the headline), the note shows the stop reason, and
   "Retry" resumes. Output folder per owner as today.
7. **Never lose data:** cancel/pause keeps finished posts; nothing is deleted.

## Tests (fake gallery-dl script on PATH like the existing media tests)
URL classification table; count probe respects the cap; picker returns the chosen posts; the generated config contains the
4-10 s sleep and nothing that raises concurrency; a fake 429 stops the run, keeps the saved posts, sets the note and the
resume re-add skips them; warning shown once then not again; cap setting clamps 1-200; both colour schemes, nothing below
12 px; accessible names; existing tests unchanged.

## Acceptance (paste real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
python3 design/contrast_check.py
```
Run the full suite ONCE at the end (7-15 min) and do not end your turn while it runs; report only with its final line.
List under "Needs a live check": real gallery-dl profile listing output, real rate-limit text, signed-in Saved. Keep spend
low. Write the result file even if low on budget.
