# Brief 10G result - desktop bulk saves (whole profile, tabs, Saved, TikTok profile) in slow mode

Implemented by Claude (Sonnet 5.5). Not committed, not pushed. No network: gallery-dl is only ever a fake script in tests, no real
Instagram/TikTok account was touched. Offscreen Qt only. Nothing from gallery-dl is imported; it still runs as a separate process.

**Android: not built, on purpose.** Bulk saves need a paginating Kotlin client that cannot be checked without a device and a real
account, and a bad pull can get a signed-in account flagged. SPEC.md says so.

## Acceptance (real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
1071 passed, 2 skipped in 856.64s (0:14:16)        (EXIT 0; the 2 skips are the existing @live tests)

python3 design/contrast_check.py
... ALL PASS
```
1071 = 981 existing + 90 new (`tests/test_bulk_saves.py`). Run once at the end, as the brief asked.
Tests cover: the URL table (odd cases, reserved paths, single posts), the 4-10 s config with no concurrency keys, count probe cap
(`--post-range 1-<cap+1>`, defensive cut), picker returning the chosen posts, a fake 429 stopping the run with the note and the resume
skipping saved posts, warning shown once, cap clamp 1-200, both colour schemes with nothing below 12 px, accessible names.

## Files changed
- `desktop/elisium_downloader/engine/media.py` - `classify_bulk_url` / `BulkUrl` / `BulkKind`, `route_for` -> `"bulk"`, bulk config
  (`config_dict(bulk=True)`, `write_config(..., bulk=True)`: `sleep-request` = `[4.0, 10.0]` at extractor/instagram/tiktok level, nothing
  about concurrency), bulk probe (`build_bulk_probe_command`: `-s -j --post-range 1-<cap+1>`, `probe_bulk`, `parse_bulk`, `BulkPost`,
  `listing_info`), `bulk_key`.
- `desktop/elisium_downloader/engine/queue.py` - `add_bulk` (one item, one slot), `probe()` dispatches bulk links to the count probe,
  `_bulk_attempt` / `_bulk_post` (one gallery-dl process per post, randomised 4-10 s pause between posts, finalize per post to
  `<output>/<owner>/`, per-post song/mix handling via `mix.process_staging`), stop-on-slow-down, serial rule against other signed-in
  Instagram/TikTok items, `bulk_max_posts` (clamp 1-200, default 50), `bulk-saved.txt` record next to `gallery-archive.sqlite3`.
- `desktop/elisium_downloader/engine/errors.py` - `is_slow_down`, `bulk_stop_note`.
- `desktop/elisium_downloader/ui/settings.py`, `settings_page.py` - `bulk_max_posts` (spin box "Most posts per bulk save" in the Downloads
  group), `bulk_warning_seen`.
- `desktop/elisium_downloader/ui/playlist_dialog.py` - bulk mode of the existing picker (Newest-N box, range, cap clamp, no quality row,
  plain post wording) and `BulkWarningDialog` (Start = primary pill, Cancel = quiet, accessible names, keyboard).
- `desktop/elisium_downloader/ui/main_window.py` - bulk links open the picker (also via `elisium add` / IPC), one-time warning
  (`_confirm_bulk_start`, `_run_warning`), flag saved in settings.
- `desktop/elisium_downloader/ui/model.py` - row meta "Instagram · @user · 12 of 50 posts", spoken text.
- `core-spec/SPEC.md` - new section "Bulk saves" (new rows only).
- `desktop/tests/test_bulk_saves.py` (new, 90 tests).

## How it works
1. Link -> picker (probe lists up to cap+1 posts, slow mode applied) -> warning once -> `queue.add_bulk(url, posts)`.
2. The item runs `probing -> downloading`; each post is its own gallery-dl run (`-D <staging per post>`, default archive), so the
   headline is posts: `files_done`/`files_total` = posts, the per-file count inside a post never reaches the row.
3. First 429 / "please wait" / rate limit / `challenge_required` / login wall mid-run (cookies set or posts already saved) ends the run:
   state `paused`, note "Instagram asked us to slow down. Saved N posts. Try again later." (TikTok for TikTok), site added to the
   rate-limited set. Finished posts are already moved. Re-adding the link or Resume continues; posts saved earlier are skipped without a
   request (`bulk-saved.txt`). A login wall with nothing saved and no cookies is the plain `login_required` failure instead.
4. A post that fails for another reason is skipped (item ends `done` with a note); three in a row fail the item.
5. Cancel/pause keep finished posts; nothing is deleted; existing file names are never overwritten.

## Deviations
1. `classify_media_url` is unchanged (its existing test table says profile = UNKNOWN); bulk links are classified by the new
   `classify_bulk_url`, and `route_for` returns `"bulk"` for them. Existing tests stay unchanged.
2. Settings: the cap row sits in the existing "Downloads" group (an existing test pins the group list).
3. `settings.apply` calls `set_bulk_max_posts` only when the queue has it (older test doubles).
4. Bulk runs use their own config `gallery-dl-bulk.json` so the ordinary media config stays as it was.
5. The "skip without requesting" record is Elisium's own `bulk-saved.txt` (gallery-dl's archive still needs a request per post). It
   means a bulk re-run does not re-fetch a post whose files you deleted; delete that file to reset.
6. Photo-with-song posts inside a bulk run still get the song cut / mp4 per the photo settings, but without the "converting" state.

## Needs a live check
- Real `gallery-dl -j --post-range 1-N` listing output for an Instagram profile, `/reels/`, `/tagged/`, `/saved/`, a Saved collection and
  a TikTok profile: field names (`post_shortcode`, `shortcode`, `username`, `date`, `description`, TikTok `id`/`author.uniqueId`), whether
  `--post-range` counts posts as assumed, and the `/p/<code>/` and `/@user/video/<id>` links the post URLs are built from.
- Real rate-limit and challenge wording (the needles in `errors._SLOW_DOWN_NEEDLES` are guessed) and the exit code.
- Signed-in Saved (cookies from a browser), including collection URL shape.
- That `sleep-request` as a list `[4, 10]` is accepted by this gallery-dl version (1.32.20 installed).
