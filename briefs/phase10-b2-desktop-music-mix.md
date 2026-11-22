# Brief 10B-2 - Desktop: song snippet and the photo + song video

Plan: `~/.claude/plans/elisium-posts-images-music-stories.md`, section "Owner decisions" (music = BOTH: keep the photos +
the song file, AND make an mp4; song = ONLY the post's snippet). Read `AGENTS.md`, `core-spec/SPEC.md`,
`briefs/phase10-b1-desktop-media-engine.result.md` (the engine this builds on) and `desktop/elisium_downloader/engine/media.py`.
Edit only: new `desktop/elisium_downloader/engine/mix.py`, `desktop/elisium_downloader/engine/media.py` and
`desktop/elisium_downloader/engine/queue.py` (only to call the mix step after a media download), tests under
`desktop/tests/`, and write `briefs/phase10-b2-desktop-music-mix.result.md`. No UI, no Android, no commit/push, no sudo,
no network in tests. ffmpeg is a system dependency already (yt-dlp uses it); find it with `shutil.which("ffmpeg")`.

## Build (runs after the media files are downloaded, still in the item's staging folder, before the move to output)
1. **Find the post's song.** From the `--write-metadata` JSON files in staging, find the audio file and its snippet times.
   Read the start and length tolerantly from what the metadata holds (e.g. an `audio_timestamps`-style list, or
   start/duration fields in ms or s); write a small pure function `snippet_from_metadata(meta) -> (start_s, length_s) | None`
   with tests for each shape you support and for missing data. If no song file: skip all of this.
2. **Cut the snippet** with ffmpeg into `<base> song.<ext>` in staging: `-ss <start> -t <length> -i <song> -c copy`;
   if stream copy fails (non-zero exit), retry once re-encoding to AAC 192k m4a. If no snippet times: keep the full song and
   set a note on the item ("Kept the full song: the post doesn't say which part it plays."). The original full download is
   then removed from staging (only the snippet, or the full song when there are no times, goes to the output).
3. **Build the video** `<base> [<post id>_mix].mp4` (archive key `mix_key(site, post_id)` from media.py):
   - photos only (single image or carousel of images): each photo shown for `snippet length / photo count` seconds
     (minimum 2 s each; if the song is shorter the last photo holds until the song ends), scaled and padded to 1080x1920 for
     portrait-majority posts or 1920x1080 for landscape-majority, black bars, H.264 yuv420p, 30 fps, AAC audio,
     `-shortest` off so the video lasts the song.
   - carousel with videos inside: photos as above, videos played in slide order at their own length (scaled/padded the
     same), the song as the soundtrack over the whole thing, trimmed to the total length; the videos' own sound is dropped.
   - no song (a carousel without music): do NOT build a video; the photos/videos are the result.
   Use an ffmpeg concat/filter_complex argv built by a pure function `build_mix_command(...) -> list[str]` (tested
   without running ffmpeg). Run it with `nice`, low thread count (`-threads 2`), into staging, then it moves to output with
   the other files.
4. **Progress:** the item shows the state "converting" (existing state) while cutting/mixing; files_total includes the
   mix file (+1) and the snippet replaces the song (no change), so the count stays honest.
5. **Failure:** if ffmpeg is missing or the mix fails, the photos and song are still saved; the item ends `done` with a
   note "Saved the photos and the song; the video couldn't be made." (never fail the whole item for the extra video).
6. **No duplicate on re-add:** skip building when `[<post id>_mix]` already exists in the output folder.

## Tests (offline; a fake ffmpeg on PATH that records argv and writes the output file, like the fake yt-dlp tests)
snippet_from_metadata shapes; cut argv (copy, then the re-encode retry); mix argv for 1 photo, 3 photos, mixed carousel,
portrait vs landscape choice, the 2-second minimum; no-song -> no video; ffmpeg missing -> done with note; existing mix
skipped; files_total +1. Keep all existing tests passing.

## Acceptance (paste real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
```
Also run ONE real local mix (no network): make 3 test images and a 10 s tone with ffmpeg in a temp dir
(`ffmpeg -f lavfi -i testsrc=...` / `sine=...`), run your mix function on them, and report the output's duration and
resolution from `ffprobe`. Write the result file even if low on budget.
