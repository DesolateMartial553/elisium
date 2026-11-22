# Brief 10B-2 result - desktop song snippet + photo/song video

Implemented by Claude (Sonnet 5.5) because OpenCode was out of usage. Not committed, not pushed. No network. ffmpeg and
ffprobe are only ever run as separate processes, under `nice -n 10` with `-threads 2`.

## Files changed

New:
- `desktop/elisium_downloader/engine/mix.py` - `snippet_from_metadata`, `build_cut_command`, `build_mix_command`,
  `photo_seconds`, `choose_canvas`, `probe_stream` (ffprobe JSON), `MixJob` (cancellable ffmpeg runner),
  `process_staging` (find song, cut snippet, build video, notes), `find_ffmpeg` / `find_ffprobe`.
- `desktop/tests/test_mix.py` - 72 tests (fake ffmpeg / ffprobe scripts on disk, fake gallery-dl through the real queue).

Changed:
- `desktop/elisium_downloader/engine/queue.py` - `QueueItem.note` (+ `"note"` in the snapshot), `ffmpeg` / `ffprobe`
  constructor args (default: found on PATH), `_mix_post_id`, `_post_id`, `_convert_media` called in `_media_attempt` after a
  successful download and before `media.finalize`; `files_total` +1 when a mix is expected.
- `desktop/tests/conftest.py` - autouse guard: `mix.find_ffmpeg` / `find_ffprobe` return `None` so no test reaches the real
  binaries (same idea as the gallery-dl guard).
- `media.py` not edited (the brief allowed it; nothing needed changing). `media.mix_key` is used to derive the
  `<post id>_mix` file marker.

## Behaviour

- Song: exactly one audio file in the staging folder (by extension; an audio-only `.mp4` is also recognised via ffprobe).
  Several audio files (a story tray) or none: nothing happens. Snippet times are read from the song's own `.json` first,
  then every other `.json` in staging.
- Cut: `-ss S -t L -i song -c copy`, retry once with AAC 192k `.m4a`. Output `<base> song.<ext>`; only after success is
  the full download deleted. `<base>` = the song file name minus extension and the trailing `[media id] num`.
- No times: full song kept, note "Kept the full song: the post doesn't say which part it plays."
- Video `<base> [<post id>_mix].mp4`: photos (+ carousel videos in slide order, trailing `num` of the file name), each photo
  `snippet/photo count` s (min 2 s, last photo holds to the song's end), scale+pad to 1080x1920 (portrait majority, ties and
  unknowns) or 1920x1080, H.264 yuv420p 30 fps, AAC 192k, song padded/cut to the total, clips' own sound never mapped,
  no `-shortest`. Built in `<staging>/.mix-work/`, renamed into staging only when complete (a crash never leaves a half mp4
  to be moved), work folder removed afterwards.
- Item goes `downloading -> converting -> done`; `files_total` = downloads + 1 while a mix is expected; if the mp4 is not
  made (failed, or already in the output folder) `files_total` drops back by 1, so the count stays honest.
- Failure never fails the item: ffmpeg missing / mix fails -> `done` with note "Saved the photos and the song; the video
  couldn't be made." (a failed trim adds "Kept the full song: it couldn't be trimmed." first).
- `[<post id>_mix]` already in `<output>/<owner>/` (or in staging) -> no rebuild.
- Pause/cancel while converting terminates the ffmpeg run (the `MixJob` is the item's handle); a resume reruns, and an
  already-cut `... song.m4a` in staging is not cut again.

## Commands run

```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
827 passed, 2 skipped in 582.85s (0:09:42)
```
(755 existing + 72 new. The 2 skips are the existing `@pytest.mark.live` tests.)
Caveat: I changed one string in `mix.py` (the `out_range=tv` fix below) while that full run was in progress; after it I
re-ran `tests/test_mix.py tests/test_media_queue.py tests/test_media.py`: `203 passed in 17.18s`. The edit only touches a
substring the tests do not pin, but the full-suite number is strictly from the code just before that edit.

## Real local mix (no network)

Test inputs made with ffmpeg in a temp dir: `testsrc` 1080x1350 jpg, `smptebars` 1080x1920 jpg, `testsrc2` 1200x800 jpg
(portrait majority), a 10 s 440 Hz AAC tone, and a metadata JSON saying start 2000 ms / length 6000 ms
(`music_consumption_info.audio_asset_start_time_in_ms` / `overlap_duration_in_ms`). Ran `mix.process_staging` (real
ffmpeg 2-thread, nice) in 18 s:

- `<base> [CMus789rst_mix].mp4`: ffprobe -> **duration 6.000 s (video stream), format 6.012 s (AAC frame padding), 1080x1920,
  h264, yuv420p, 30 fps**, AAC audio.
- `<base> song.m4a` (stream-copied snippet): ffprobe duration 6.011 s. The 10 s original was removed.
- The first real run exposed `yuvj420p` (the jpeg's full-range flag leaked through); fixed with `out_range=tv` in the scale
  filter and re-run: now `yuvj` gone, `pix_fmt=yuv420p`.

## Deviations (and why)

1. Added `QueueItem.note` / snapshot `"note"` (brief: "set a note on the item"): the item had no such field. Not persisted in
   history; the UI needs 10C wiring to show it.
2. Mix is only attempted for a single post: Instagram `/p/`, `/tv/`, single story, TikTok `/photo/`. Story trays and
   highlights (many unrelated songs) never mix.
3. Several audio files in staging -> nothing is cut or mixed (ambiguous which song).
4. Extra note for a failed trim ("Kept the full song: it couldn't be trimmed."); brief only defined two notes.
5. Mixed carousel photo length: photos share the snippet length (`snippet / photo count`, min 2 s) and the clips add their own
   length on top; the song is padded with silence to the total (not looped).
6. Square or unprobed pictures vote for neither orientation; ties go portrait.
7. Conftest autouse ffmpeg guard (not named in the brief, but under `desktop/tests/`).
8. gallery-dl's own SQLite archive is untouched, so the mix is not "archived" there; re-add protection is the existing-file
   check from item 6 of the brief.

## Needs a live check

- Real Instagram/TikTok metadata: the snippet-time key names are guesses covering Instagram's `music_consumption_info`
  spelling plus generic shapes; whether gallery-dl `--write-metadata` includes them at all is unverified. If it does not, every
  post gets the "Kept the full song" note.
- That gallery-dl saves the song as an audio extension (or an audio-only mp4) and one song per post.
- Real HEIC/AVIF photos through ffmpeg, and a carousel with a real video (rotation, odd fps).
- The "converting" state and the note in the UI (10C).
