# Brief 10C result - desktop screens for photo posts, carousels, stories and songs

Implemented by Claude (Sonnet 5.5). Not committed, not pushed. No network, no real windows (offscreen only).

## Acceptance (real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
949 passed, 2 skipped in 667.84s (0:11:07)        (EXIT 0; 2 skips = existing @live tests)

python3 design/nightshelf/contrast_check.py
... ALL PASS

QT_QPA_PLATFORMTHEME= nice python3 <scratch wrapper around desktop/tools/render_screenshots.py>
wrote all 24 PNGs (queue/empty/history/settings/choose-quality/playlist, night/day, normal/large) into docs/screenshots/
```
The wrapper (`.../scratchpad/shots10c.py`, not in the repo) imports the real renderer unchanged and only patches its sample
data (format labels, a note on a done post, a "Looking up the post..." row, history notes), because `render_screenshots.py`
is not in this brief's edit list. Viewed once: queue-night, queue-day-large, history-night, settings-night, plus a scratch
render of a done row with a note and a skipped "Already saved" row. No differences from DESIGN.md found.

## What was built
1. Thumbnail + format: queue items/snapshots carry `thumbnail` and `format_label` (display only, never in history).
   yt-dlp probe: `thumbnail`/`thumbnails[-1]` (http(s) only) and "1080p MP4" / "MP3 audio". gallery-dl plan: first image
   URL (else a cover field) and "6 photos + song". `describe_row` meta: "YouTube · 1080p MP4 · 648.5 MB",
   "Instagram · 6 photos + song · 3 of 7 files". The row delegate already loaded `thumbnail` through `ThumbnailCache`.
2. Multi-file rows: files_done/total, percent from files, and the item's note under the meta on Downloads AND History rows.
   History gained `note` and `files_total` columns (added on open to old files, tolerant when missing; the schema test now
   expects the spec columns plus these two).
3. Open / Show in folder: "Open" opens the file for one file and the post's folder for multi-file posts; "Show in folder"
   selects the first file through `org.freedesktop.FileManager1.ShowItems` (QtDBus) and falls back to opening the folder.
   Same helpers (`widgets.open_finished`, `show_finished`) for Downloads and History.
4. "Download again anyway": `queue.add(url, force=True)` (History's "Download again" uses it); `MediaOptions.use_archive=False`
   omits `--download-archive`. Normal re-add keeps the archive. Automatic: if a media run finishes with nothing new, nothing
   staged and the files are not in the output folder, it re-runs once without the archive. If everything is present the item
   is skipped with note "Already saved". Force is ignored for plain yt-dlp links.
5. Settings: `photo_mode` (Photos, song and video / Photos and song only / Photos only) and `song_length` (Post's snippet /
   Full song) are real combos stored in settings.json, pushed by `settings.apply` to `queue.set_photo_mode/set_song_length`,
   and honoured by `mix.process_staging(make_video, keep_song, cut_song)`. Photos only deletes the song; Full song skips the
   cut (no note); Photos and song only builds no mp4. `files_total` is adjusted for each case.
6. Add-link feedback: a queued/probing photo post, story tray, highlight or slideshow shows "Looking up the post..." as its
   title (`DownloadModel.title_of`, also used by the delegate and screen-reader text) until the probe names it. No dialog.

## Files changed
engine: `media.py` (thumbnail, format_label, use_archive, staged_files, all_present), `mix.py` (3 flags), `queue.py`,
`history.py`. ui: `model.py`, `widgets.py`, `main_window.py`, `history_page.py`, `settings.py`, `settings_page.py`.
tests: new `tests/test_multifile_screens.py` (42 tests); updated `conftest.py` (autouse guard so no test talks to the real
file manager), `test_history.py`, `test_media.py` (fake gallery-dl: archive optional, `bracket_ids`), `test_media_queue.py`
(the old "archived -> skipped" test is now "archived and present -> skipped + Already saved" plus "archived, deleted -> comes
back without the archive"), `test_presets_settings.py`, `test_ui_pages.py`, `test_nightshelf_pages.py` (fake `add` takes
`force`). `docs/screenshots/*` regenerated (all 24).

## Notes / not verified live
- Needs a real run: whether real gallery-dl's `-j` message URL for an image is a usable thumbnail without cookies; real
  file-manager D-Bus selection (tests stub it); real `[media id]` naming for the "files present" check (it uses `[id]` in file
  names, the song is excluded because its name changes when cut).
- `render_screenshots.py` itself was not edited (see wrapper note above); its own sample rows have no format labels or notes.
- History "Open" on posts older than this change has no `files_total`, so it opens the file as before.
