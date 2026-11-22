# Brief 10C - Desktop screens for photo posts, carousels, stories and songs (Night shelf)

Plan: `~/.claude/plans/elisium-posts-images-music-stories.md`. Read `AGENTS.md`, `design/nightshelf/DESIGN.md`,
`briefs/phase10-b1-desktop-media-engine.result.md`, `briefs/phase10-b2-desktop-music-mix.result.md`,
`briefs/phase11-c1-desktop-nightshelf-shell.result.md`, `briefs/phase11-c2-desktop-nightshelf-pages.result.md`.
Edit only: `desktop/elisium_downloader/ui/*.py`, `desktop/elisium_downloader/engine/queue.py` and
`engine/media.py` (only for the thumbnail/format fields and the "Download again anyway" path below), history store code if
it lives in `engine/` (field additions only), tests under `desktop/tests/`, `docs/screenshots/` (regenerate the queue and
history ones through `desktop/tools/render_screenshots.py`), and write `briefs/phase10-c-desktop-multifile-screens.result.md`.
No Android, no commit/push, no sudo, no network in tests.

## Build
1. **Real thumbnail and format on rows.** Queue snapshots do not carry a thumbnail URL or a format today, so rows show a
   placeholder and "Site · size". Carry `thumbnail` (URL from the probe: yt-dlp `thumbnail`, or the first image of a media
   plan) and `format_label` (e.g. "1080p MP4", "Photos + song") from the probe into the queue snapshot (display only; never
   into history files beyond what history already stores) and use them in `describe_row` / the delegate via the existing
   `ThumbnailCache`. Meta line: "YouTube · 1080p MP4 · 648.5 MB", "Instagram · 6 photos + song · 3 of 7 files".
2. **Multi-file rows.** Show `files_done`/`files_total` ("3 of 7 files"), percent from files, and the item's `note`
   (10B-2: "Kept the full song...", "Saved the photos and the song; the video couldn't be made.") under the meta line on both
   Downloads and History rows (History must keep the note: add it to the history entry if absent, tolerant when missing from
   old files).
3. **Done rows for a post:** "Open" opens the folder for multi-file posts (the post's folder), the file for single files;
   "Show in folder" selects the first file. Label stays "Open · Show in folder".
4. **"Download again anyway".** gallery-dl's SQLite archive remembers a post even if the user deleted the files, so a re-add
   does nothing. In History's "Download again" (and when a re-added media link finishes with zero new files and the files are
   missing from the output folder) run the media engine without the archive (`--no-download-archive`-style: omit
   `--download-archive` for that run) so the files come back. Add a `force` flag on the queue add path; a normal re-add keeps
   the archive. If everything is already saved and present, show the note "Already saved" instead of silently finishing.
5. **Photos and music settings (make them real).** Replace the two read-only rows from 11C-2 with real settings stored
   like the others: "Photo posts with a song": Photos, song and video (default) / Photos and song only / Photos only;
   "Song length": Post's snippet (default) / Full song. Wire to `MediaOptions` and the mix step in `engine/mix.py`/`queue.py`
   (Photos and song only = skip the mp4; Photos only = drop the song file; Full song = skip the cut). Keep wording plain;
   tests for each combination.
6. **Add-link feedback.** When a pasted link is a photo post, story tray or slideshow, the Downloads page shows the row at
   once with the title "Looking up the post..." until the probe fills it in (no modal, no dialog).

## Tests
Row text for single video, photo post, carousel mid-download, done with note; history keeps the note and loads old entries
without it; thumbnail/format flow from the probe to the row; force re-add bypasses the archive and a normal re-add does not;
each setting combination changes the plan/argv as described; accessible names unchanged; both schemes, nothing below 12 px,
no emoji.

## Acceptance (paste real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
python3 design/nightshelf/contrast_check.py
QT_QPA_PLATFORMTHEME= nice python3 desktop/tools/render_screenshots.py
```
View the queue and history screenshots, fix differences from DESIGN.md before reporting. Write the result file even if low
on budget. Do not stop to wait on a background test run: run the full suite in the foreground with a 600000 ms timeout or
poll its log until the final summary line appears, and report only once you have that line.
