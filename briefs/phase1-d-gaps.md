# Brief 1D - close the gaps found when auditing 1C

Read `AGENTS.md` and `core-spec/SPEC.md`. Found by running the real yt-dlp against a local video (no internet): the queue works end to end, but four things are wrong. You may edit `engine/queue.py`, `engine/runner.py` and their tests, plus the one new test file below.

## Fixes

1. **Re-adding a finished item in the same session never re-downloads.** `DownloadQueue.add()` returns the existing item for the same identity even if that item is `done`/`skipped` and the user has since deleted the file. Fix: if the existing item is `done` or `skipped`, check that its file still exists in `output_dir` (use `file_path` if known, else the `[<id>]` scan for YouTube); if the file is gone, put the item back to `queued` (clear error, reset progress, drop the stale archive entry through the archive lock, never while a download is active) and return it. If the file is there, return the existing item unchanged. `failed`/`cancelled` items stay as they are (the user retries them).

2. **Non-YouTube downloads have `file_path = None`.** `_find_output` only works for YouTube ids. Make the runner report the real final path for every site. Preferred: `--print-to-file after_move:filepath <temp>/<item>.path` (does not imply `--quiet` or `--simulate`; verify that with a real run), read after exit. If that does not work, find another way and explain in the result file. The path must be set on the item and written to history. Keep the YouTube scan only as a fallback.

3. **yt-dlp silently skipping is reported as `done`.** When the video is already in the archive, yt-dlp exits 0 with "has already been recorded in the archive" and downloads nothing; the queue then says `done`. Detect that line in the raw log (and that no new file/`after_move` path was produced) and set `skipped` with `ALREADY_DOWNLOADED` instead.

4. **Plain downloads show a "converting" stage.** `stage_for_postprocessor` maps every non-merger post-processor to `converting`, so a simple mp4 shows `converting` for `MoveFiles`. Map housekeeping processors (`MoveFiles`, `Metadata`, `EmbedThumbnail` is still converting, `FFmpegMetadata`, `SponsorBlock`, `ModifyChapters` is converting) sensibly: `MoveFiles` and `Metadata`/`FFmpegMetadata` must NOT change the state away from `downloading`; real conversion (`ExtractAudio`, `VideoConvertor`, `VideoRemuxer`, `EmbedSubtitle`, `EmbedThumbnail`, `ModifyChapters`) stays `converting`.

## New test file
`desktop/tests/test_e2e_local.py`, marked `@pytest.mark.e2e` (register the marker in `pyproject.toml`). It needs only `yt-dlp` and `ffmpeg` on PATH and skips otherwise. It generates a 2-second test video with ffmpeg (`-f lavfi -i testsrc=duration=2:size=160x120:rate=10 -f lavfi -i sine=duration=2 -shortest -pix_fmt yuv420p`), serves it from `http.server` on 127.0.0.1, then with the REAL yt-dlp checks: one queue item for the same URL added three ways (plain, repeated, `?utm_source=x`); exactly one finished file in the output folder; no `.part` files in the output folder; temp dir empty after success; archive contains `generic clip`; `file_path` is set and exists; a fresh queue adding the same URL again ends `skipped` and creates no second file; after deleting the file, adding the URL again in the SAME queue downloads it again (fix 1) and in a fresh queue too (archive reconcile or yt-dlp re-download - make sure the archive is cleaned so it is not silently skipped for non-YouTube sites; if reconcile cannot cover non-YouTube ids, extend it using `file_path` from history).

## Acceptance
```
cd desktop && nice .venv/bin/python -m pytest -q          # all pass, e2e included
```
Paste the output. Also add unit tests for fixes 1, 3 and 4 with the fake yt-dlp.

## Do not
Import PySide6, add dependencies, touch 1A/1B modules except for a real bug (say so), or contact the internet.
