# Brief 10B-1 result - desktop media engine (gallery-dl)

Implemented by Claude (Sonnet 5.5) because OpenCode was out of usage. Not committed, not pushed. No network calls were
made: gallery-dl's `--help`, man page and `/usr/share/doc/gallery-dl` (configuration.rst, formatting.md) were read, its
Python source was not. Nothing imports gallery_dl; it only ever runs as a separate process.

## Files changed

New:
- `desktop/elisium_downloader/engine/media.py` - URL classifier + routing, per-run config, argv builders, `-j` probe
  parser, `MediaProcess` (file counting), `finalize` (no-overwrite move), `find_gallery_dl`.
- `desktop/tests/test_media.py` (95 tests), `desktop/tests/test_media_queue.py` (36 tests).
- `desktop/tests/fixtures/media/` - `instagram_single_image.json`, `instagram_single_image.jsonl`,
  `instagram_carousel_mixed.json`, `instagram_image_with_music.json`, `instagram_story_tray.json`,
  `tiktok_photo_slideshow.json`, `empty.json`, `login_required.txt`, `README.txt`. All hand-made (see "Needs a live check").

Changed:
- `desktop/elisium_downloader/engine/queue.py` - routing, media attempt, `/p/` fallback, `files_done` / `files_total`.
- `desktop/elisium_downloader/engine/errors.py` - `explain_gallery`, `GALLERY_DL_MISSING`, `STORY_EXPIRED`,
  `PRIVATE_ACCOUNT`, `NO_MEDIA_FILES`.
- `desktop/tests/test_errors.py` (16 new test cases appended), `desktop/tests/conftest.py` (autouse guard: `media.find_gallery_dl`
  returns `None`, so no test can reach the real `/usr/bin/gallery-dl`).
- `packaging/arch/PKGBUILD` (`depends += 'gallery-dl'`), `install-desktop.sh` (one-line hint, never installs, never exits 1).

Not touched: `urlnorm.py` (the classifier lives in `media.py` and calls `normalize_url` / `site_kind` read-only),
`runner.py`, any UI file, Android, `SPEC.md`.

## How it works

- **Routing** (`media.route_for`, used at the top of `DownloadQueue._attempt`, before any yt-dlp probe):
  - `media` (gallery-dl only): Instagram `/stories/<user>/`, `/stories/highlights/<id>/`, TikTok `/@user/photo/<id>`.
  - `ytdlp_then_media`: Instagram `/p/<code>`, `/tv/<code>`, and a single `/stories/<user>/<id>/`. yt-dlp first; if it fails
    with the `no_media` code (at probe time or at download time) the same attempt re-runs once on the media engine.
    No retry is counted and nothing sleeps. The state goes `probing -> downloading -> done` when yt-dlp's probe
    reports `no_media`, and `downloading -> probing -> downloading -> done` when it is the download that reports it.
  - `ytdlp` (unchanged, 12B extract-once path included): reels, `/reel/`, TikTok videos, YouTube, everything else.
- **Probe**: `gallery-dl --config-ignore --config-json <cache>/gallery-dl.json --no-input -s -j [cookies] <url>`. Gives the
  planned files (kind by extension, media id, slide number) and owner / shortcode / date / caption first line, so the card
  has `files_total` and a title before the first file lands.
- **Download**: `... --no-input -D <temp>/media/<hash> -f <format> --download-archive <data>/gallery-archive.sqlite3
  --write-metadata [--limit-rate] [cookies] <url>`. Formats: Instagram
  `{username} {date:%Y-%m-%d} {post_shortcode|shortcode|post_id} [{media_id|id}] {num}.{extension}`, TikTok
  `{author[uniqueId]} {id} [{id}_{num}] {num}.{extension}`.
- **Config** (mode 0600, written atomically each attempt): `extractor.instagram.audio: true`, `videos: true`, TikTok
  `photos/audio/videos: true`, and a pinned `output` block (`mode: pipe`, `skip: true`, `shorten: false`, `progress: false`)
  so the stdout format the counter reads does not depend on auto-detection.
- **Progress**: `MediaProcess` (a `runner.DownloadProcess` subclass) counts printed file paths under the staging folder;
  a `# `-prefixed path (skipped) counts too. Events have the yt-dlp shape plus `files_done` / `files_total`;
  `percent = files_done / files_total * 100` (0-100, like the yt-dlp events). Queue snapshots carry
  `progress.files_done` / `progress.files_total` (null for yt-dlp items).
- **Output**: after the process exits the staging folder is scanned (not stdout) and media files are moved to
  `<output>/<owner>/`. `os.link` + unlink (copy with `O_EXCL` across filesystems): an existing name is skipped and the staged
  duplicate dropped, never renamed. `.json` metadata, `.part` files stay in staging for brief 10B-2. The owner folder name is
  sanitised (`/`, `\`, control characters, leading dots, `..`); no owner puts files in the output root. Files that finished
  before a failure, pause or restart are moved too, so a retry only fetches what is missing.
- **Result states**: something new moved -> `done` (`file_path` = first moved file, `percent` 100); everything skipped
  (archive or name already in the output folder) -> `skipped` with `already_downloaded`; non-zero exit -> `failed` through
  `explain_gallery` (network errors retry with the usual 5/15/45 s backoff, others do not).
- **Errors**: `explain_gallery` checks gallery-dl wording first, then the yt-dlp table. New codes `gallery_dl_missing`,
  `story_expired`, `private_account` (messages exactly as in the brief), plus `NO_MEDIA_FILES` (code `no_media`) for an empty
  non-story result. Login wall -> `login_required` / `session_expired` (cookies set) / generic wording off Instagram;
  `429 Too Many Requests` -> `rate_limited`; `404 Not Found` -> `video_unavailable`, or `story_expired` for a single story URL;
  an empty story tray / story item with no error text -> `story_expired`.

## Commands run

```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
755 passed, 2 skipped in 703.86s (0:11:43)
```

(608 existing + 147 new = 755; 95 in test_media.py, 36 in test_media_queue.py, 16 in test_errors.py. `sh -n install-desktop.sh` -> OK. The two skips are the existing `@pytest.mark.live` tests.)

## Deviations (and why)

1. **Staging folder is `<temp>/media/<sha1(identity)[:16]>`, not `<temp>/<item id>`.** Item ids restart at 1 every launch,
   so after a crash a different post could inherit a stale folder and its leftover files would be moved into the wrong
   owner's folder. The identity hash is stable for one link, so a restart resumes in the same folder. Leftover `.json`
   metadata stays there for 10B-2.
2. **Single `/stories/<user>/<id>/` is `ytdlp_then_media`** (like `/p/`), not media-only: a video story works on yt-dlp today
   and the `no_media` fallback fixes photo stories. The brief only listed trays, highlights and `/photo/` as media-only.
3. **`/tv/<code>` also gets the `no_media` fallback** (the brief names `/p/`; `/tv/` is the same post type in the Android rules).
4. **gallery-dl keeps its default archive IDs.** I did not set `archive-format` to mirror the Android keys
   (`instagram <media_id>`, `tiktok <id>_<n>`): with an unverified field name every slide would get the key `None` and slides
   2..N would be silently skipped. `media.archive_key()` / `media.mix_key()` give the Android-shaped keys for 10B-2 and the UI.
5. **No reconcile for gallery-dl's SQLite archive.** SPEC's "file deleted -> drop the id from the archive and download again"
   works for `archive.txt` only; Elisium cannot edit gallery-dl's archive rows without knowing its key format, so a deleted
   photo is not re-fetched by re-adding the post (delete `gallery-archive.sqlite3` to reset). The "Download again anyway"
   action therefore just skips again for media items (gallery-dl's archive wins); 10C needs to know. Not covered by a test.
6. **Extra flags**: `--no-input` (never prompt for a password) and `--limit-rate` (the SPEC speed-limit setting reaches
   gallery-dl too; same flag name and unit syntax).
7. **`queue.py` constructor gained** `gallery_dl`, `probe_media`, `run_media`, `gallery_config`, `gallery_archive` (all
   optional). Defaults work with no arguments: gallery-dl is looked up on PATH when needed, the config goes to
   `<temp_dir parent>/gallery-dl.json` (= `~/.cache/elisium/gallery-dl.json` in the app) and the archive to
   `<archive.txt folder>/gallery-archive.sqlite3` (= `~/.local/share/elisium/`). The UI needs no change.
8. **Public `DownloadQueue.probe()` is unchanged** (yt-dlp, flat for trays), because the playlist picker uses it. The UI still
   opens a story tray in the picker, and each picked story becomes a single story item (so 2. covers it). Sending a whole tray
   to the media engine as one card from the UI is a 10C decision; adding a tray URL straight to `DownloadQueue.add` does
   it (covered by tests). I did not check how `cli.py` hands URLs over.
9. **Changed `tests/conftest.py`** (not named in the brief; it is under `desktop/tests/`): an autouse guard stubs
   `find_gallery_dl` to `None` so no test can run the real binary.
10. SPEC.md's error table was not edited (not in the file list). Rows to add in 10F: `gallery_dl_missing`, `story_expired`,
    `private_account`, and the gallery-dl wording for login / 429 / 404.

## Needs a live check

No `-j` dump could be made offline, so **every field below is an assumption** written into hand-made fixtures. A real run
(ideally one public photo post, one carousel, one photo-with-music post, one signed-in story tray, one TikTok slideshow)
must confirm each:

1. **`-j` output shape**: a JSON array of messages, `[2, {post metadata}]` and `[3, "<url>", {file metadata}]`. The parser also
   accepts JSON Lines and ignores unknown message types, but the real shape is unverified (also whether `-s` skips the archive).
2. **Instagram fields**: `category`, `username`, `post_shortcode`, `shortcode`, `post_id`, `media_id`, `num`, `count`,
   `extension`, `date` (string `YYYY-MM-DD HH:MM:SS`), `description`. Check the filename renders no literal `None`
   for posts, carousels, stories and highlights (`{post_shortcode|shortcode|post_id}`, `{media_id|id}`).
3. **TikTok fields**: `id`, `author.uniqueId`, `desc`, `num`, `extension`, `date`, `category`. Check `{author[uniqueId]}` and that
   `[{id}_{num}]` is unique for every slide and the sound file.
4. **Audio**: with `extractor.instagram.audio: true`, does a photo post / story music sticker yield an `m4a`-like file, with
   which extension and `media_id`/`num`? The parser classifies audio by extension (`m4a mp3 aac opus ogg wav flac`); if
   gallery-dl names it `mp4` it is counted as a video. Check the song file does not collide with a photo's filename.
5. **stdout in `pipe` mode**: one full path per finished file, `# <path>` for a skipped one, nothing else starting with the
   staging path. `MediaProcess` counts only lines that start with the `-D` folder.
6. **Error wording** (matched by substring, all guessed from memory of gallery-dl's log style): `Redirected to login page`,
   `401 Unauthorized`, `AuthRequired`, `429 Too Many Requests`, `404 Not Found`, a private-account message, a story-expired
   message. Confirm each on a real failure; fix the needles in `errors._GALLERY_TABLE` if they differ. Also confirm that an
   expired or missing story gives an empty result (the empty-probe-on-a-story-URL rule maps that to `story_expired`).
7. **Exit codes on partial failure** (a probe that exits non-zero but still lists files is treated as a usable plan).
8. **Real signed-in runs**: story tray, highlights, private posts (`private_account` vs the login wall), `--cookies-from-browser`
   for each supported browser name and `--cookies <file>`; and that `--limit-rate 2M` is accepted.
9. **yt-dlp's `no_media` text on real photo posts / photo stories** at probe time (the fallback keys on the existing
   `no_media` code, which matches yt-dlp's "There is no video in this post").
10. **Re-adding a carousel** fetches only the missing slides with the default gallery-dl archive IDs, and the SQLite archive
    is created under `~/.local/share/elisium/`.
