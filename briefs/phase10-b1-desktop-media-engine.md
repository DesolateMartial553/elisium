# Brief 10B-1 - Desktop media engine: photo posts, carousels, stories, TikTok photo slideshows

Plan: `~/.claude/plans/elisium-posts-images-music-stories.md` (read it whole). Read `AGENTS.md`, `core-spec/SPEC.md`,
and the Android spike `briefs/phase10-a-android-media-spike.result.md` (same URL kinds and archive keys; mirror them).
Edit only: new `desktop/elisium_downloader/engine/media.py`, `desktop/elisium_downloader/engine/queue.py`,
`desktop/elisium_downloader/engine/errors.py`, `desktop/elisium_downloader/engine/urlnorm.py` (only to add a pure
classifier if needed), `desktop/packaging/PKGBUILD` (or wherever the PKGBUILD lives), `install-desktop.sh`, new/changed
tests under `desktop/tests/` (fixtures under `desktop/tests/fixtures/media/`), and write
`briefs/phase10-b1-desktop-media-engine.result.md`. No UI files (10C does the screens), no Android, no commit/push,
no sudo, no network in tests (live checks only under `@pytest.mark.live`, skipped by default).

## Context
yt-dlp cannot save images, so photo posts fail today with "This post has no video to download". The owner installed
the Arch package `gallery-dl` (1.32.20, GPL-2.0-only). Elisium (GPL-3.0) only **runs it as a separate process**,
the same way it runs yt-dlp. Never import gallery_dl or copy its code.

## Build
1. **`media.py`: a gallery-dl runner**, shaped like `runner.py` (explicit paths, argv builder, tested with a fake binary):
   - `find_gallery_dl()` -> path or None (`shutil.which("gallery-dl")`).
   - A per-run config JSON written to the cache dir (`~/.cache/elisium/gallery-dl.json`, mode 0600) and passed with
     `--config-ignore --config-json <file>` so the user's own gallery-dl config never changes Elisium's behaviour.
     It turns on `extractor.instagram.audio: true` (song files for photo posts and story stickers) and keeps videos on;
     TikTok photos/audio on (their defaults).
   - Probe: `gallery-dl --config-ignore --config-json <cfg> -s -j <url>` (simulate, dump JSON) -> parse into a list of
     planned files (kind image|video|audio, media id, slide number, ext) + post metadata (owner, shortcode/id, date,
     title/caption first line). This gives the file total for progress before downloading.
   - Download into the item's temp dir with `-D <temp>/<item id>` and a filename format that always contains the media
     id, e.g. Instagram `{username} {date:%Y-%m-%d} {shortcode} [{media_id}] {num}.{extension}`, TikTok
     `{author[uniqueId]} {id} [{id}_{num}] {num}.{extension}` (verify the field names against a `-j` dump you save as a
     fixture; adjust and document if they differ). Then move finished files to `~/Downloads/Elisium/<owner>/`
     (create it) with no overwrite: an existing name is skipped, never renamed to "(1)".
   - Dedupe: `--download-archive ~/.local/share/elisium/gallery-archive.sqlite3` (gallery-dl's own archive, separate
     from yt-dlp's archive.txt), so re-adding a carousel fetches only the missing slides.
   - Progress: count files as gallery-dl reports them (each finished file path is printed on stdout; a skipped one is
     printed with a leading `# `). Emit the same progress event shape the queue already uses, with
     `files_done`, `files_total` added (percent = files_done / files_total).
   - Cookies: the existing settings, `--cookies <file>` or `--cookies-from-browser <name>` (browser wins), never logged.
   - Pause/cancel: terminate the process like the yt-dlp runner; a restart resumes thanks to the archive.
2. **Routing in `queue.py`.** Classify each URL (port the Android `MediaUrls` rules: Instagram `/p/` and `/tv/` posts,
   `/stories/<user>/`, `/stories/<user>/<id>/`, `/stories/highlights/<id>/`, TikTok `/@user/photo/<id>`):
   - Reels and video links stay on yt-dlp exactly as today (the 12B extract-once path included).
   - Instagram story trays, highlights and TikTok `/photo/` go to the media engine.
   - Instagram `/p/` posts: try yt-dlp first (a video post works today); if it fails with the `no_media` code
     ("no video in this post"), retry once immediately with the media engine, not counted as a retry.
   - If gallery-dl is missing, the item fails with a new `gallery_dl_missing` error.
3. **Errors** (`errors.py`, plain words, same style as SPEC's table): map gallery-dl output to existing codes where they
   fit (login-required / "Redirected to login" -> sign-in rows incl. session_expired when cookies are set; HTTP 429 ->
   rate limit; 404 / "not found" -> unavailable), plus new rows: `gallery_dl_missing` ("Photo downloads need gallery-dl.
   Install it: sudo pacman -S gallery-dl"), `story_expired` ("This story has expired. Stories last 24 hours."),
   `private_account` ("This account is private. Follow it in your browser, then sign in here."). Add tests for each.
4. **Packaging:** add `gallery-dl` to the PKGBUILD `depends`; `install-desktop.sh` prints a one-line hint when
   `gallery-dl` is not on PATH (it must not install anything).

Music snippet cutting and the photo + song mp4 are **10B-2**, not this brief: here the song is just saved as the file
gallery-dl gives (keep its metadata JSON in the temp dir for 10B-2: pass `--write-metadata` and leave the .json files in
temp, never in the output folder).

## Tests (offline)
Fake `gallery-dl` script on PATH in tests (like the fake yt-dlp ones) that replays fixture `-j` JSON and prints file
lines. Cover: argv (config-ignore, config-json, -D, -f, archive, cookies variants), probe parsing for single image,
carousel mixed, image + music, story tray, TikTok slideshow, empty / login-required output; routing table for each URL
kind; the `/p/` no_media -> media engine fallback; files_done/files_total progress; move-to-output with no overwrite;
gallery_dl_missing; error mapping rows. Keep all existing tests passing.

## Acceptance (paste real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
```
List what still needs a real signed-in run (story trays, private posts) under "Needs a live check". Write the result file
even if low on budget.
