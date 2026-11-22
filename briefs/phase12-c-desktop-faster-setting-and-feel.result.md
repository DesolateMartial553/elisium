# Brief 12C + 12E (desktop) result - "Faster downloads" setting and faster-feeling progress

Implemented by a Sonnet subagent (2026-11-22). Not committed. No aria2c, no `-N`, no per-site connection table.

## Files changed
- `desktop/elisium_downloader/ui/settings.py` - `Settings.faster_downloads` ("auto" default | "off"), `FASTER_DOWNLOADS`,
  validated (junk or a missing key from an older file -> "auto"); `apply()` calls `queue.set_reuse_probe(value == "auto")`.
- `desktop/elisium_downloader/ui/settings_page.py` - Settings > Downloads row "Faster downloads" (Auto / Off combo, helper
  "Auto looks each link up once. Turn off if downloads fail.", accessible name and description set, tab order after
  Default quality, saved like the other settings).
- `desktop/elisium_downloader/engine/queue.py`:
  - `set_reuse_probe()` / `reuse_probe` property; `_download` asks the pure `may_reuse_probe()` (off, media-engine link,
    rate-limited site, or signed-in Instagram/TikTok -> never loads the info JSON; Off gives today's exact argv).
  - Rate-limit rail: pure `site_key`, `is_rate_limit_error` (codes `http_429`, `rate_limited` = 429 / "please wait"),
    `site_slot_free`. `_after_failure` records the site on its first 429; from then on that site never reuses the probe
    and `_next_queued` lets only one download per limited site run at a time (other sites unaffected). Waiting rows get
    `wait_hint = "rate_limited"` and an `item` event.
  - Honest ETA: pure `smooth_speed` (EMA, alpha 0.2), `smoothed_eta`, constants `SPEED_EMA_ALPHA`, `SPEED_EMA_WARMUP` (2 s).
    `_smooth` (called from `_on_progress`, using the injectable clock): first 2 s of a file shown as reported and kept out
    of the average, then EMA speed and ETA = remaining / smoothed speed; a byte count that drops (next stream) restarts
    it; file-counting (media engine) items untouched. No new thread.
  - `wait_hint` (pure) + `QueueItem.wait_hint`, now in the snapshot: "rate_limited" > "network" (retry after a network
    error) > "signing_in" (cookies set on Instagram/TikTok) > none.
- `desktop/elisium_downloader/ui/model.py` - `host_title()` (instant card: a queued/probing row with no title shows the
  link's host, e.g. `youtube.com`; failed rows still show the URL; photo-post "Looking up the post..." unchanged),
  `stall_reason()`, `STALL_AFTER = 10`, `STALL_REASONS` ("Signing in", "Waiting for the network", "Rate limited, waiting"),
  `describe_row(row, now=None)` shows "Starting... <reason>" after 10 quiet seconds (downloading with no progress, or
  probing), a queued rate-limited row says "Rate limited, waiting"; the model stamps `quiet_since` only when state or
  progress changes.
- `desktop/elisium_downloader/ui/main_window.py` - a 1 s `QTimer` repaints the table while any row is queued, probing or
  downloading, so the reason appears without a new event (no thread).
- `engine/runner.py` untouched; no Android file touched.

## Verified, no change needed
- Thumbnail (item 3): the queue emits an `item` event with the picture link as soon as the probe returns, before the
  download starts; the delegate's `ThumbnailCache` fetches on that repaint, in parallel. Test added (order: thumbnail
  event before the download).
- Carousel slides (item 5): `MediaProcess` emits `files_done` per saved file and the queue relays it
  (`test_media_queue.py::test_progress_events_carry_files_done_and_total` already pins 1, 2, 3); new test also covers it.

## Tests
- New `desktop/tests/test_faster_feel.py` (32 cases): setting default/Off/old file/junk/round-trip; setting reaches
  `queue.reuse_probe`; Off argv equals today's, Auto loads the info; Settings row, helper, accessible name, both colour
  schemes, nothing below 12 px; 429 downgrade per site (probe lever off, one at a time, other sites still parallel,
  hint event); signed-in Instagram/TikTok and media items never get the lever; EMA numbers (1000/2000 -> 1200, 1080,
  spike 1000/11000 -> 3000); 2 s warm-up, seeding, a new file restarts the average; file-counting items not smoothed;
  stall reason selection and the 10 s threshold; row texts; model quiet stamp; host title; instant card in the window.
- Updated existing tests: `test_presets_settings.py` (fake queues gain `set_reuse_probe`, expected call list gains
  `("rp", True)`); `test_multifile_screens.py` (non-post links now show the host, not the URL, while queued; failed rows
  still show the URL). Also `test_ui_a11y.py` and `test_ui_model.py` (one assertion each, see above). Accessible names otherwise unchanged; the only change is the queued row's title (and so its Pause/Cancel button names) showing the host.

## Commands run
```
cd desktop && QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q tests/test_faster_feel.py tests/test_presets_settings.py tests/test_multifile_screens.py
86 passed in 7.02s
```
Full suite (run once, whole):
```
cd desktop && QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
FAILED tests/test_ui_a11y.py::test_tab_order_through_the_main_window
FAILED tests/test_ui_model.py::test_rows_title_fallback_and_update
2 failed, 979 passed, 2 skipped in 817.33s (0:13:37)
```
Both failures were old assertions pinning the URL as a queued row's title / the row buttons' accessible name
("Pause https://a.com/1"); the instant card (item 3) now shows the host, so they became "example.com" and
"Pause a.com" / "Cancel a.com". Updated those two assertions (tests only) and re-ran the three affected files:
```
pytest -q tests/test_ui_a11y.py tests/test_ui_model.py tests/test_faster_feel.py
94 passed in 9.76s
```
The full suite was NOT re-run after this two-line test edit (one full run only, per the brief).
```
cd /home/desolate/Work-Projects/elisium-downloader && python3 design/nightshelf/contrast_check.py
... ALL PASS
```

## Notes
- Re-run quirk worth knowing: a 429 on an info-JSON run before any progress is re-run once from the URL by the 12B logic;
  the rail marks the site when the final failure is returned.
- `python3 design/nightshelf/contrast_check.py` lives at the repo root `design/`, not under `desktop/` (the brief's `cd desktop`
  line would not find it); run from the repo root.
