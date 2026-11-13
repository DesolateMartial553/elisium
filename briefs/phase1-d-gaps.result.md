# Brief 1D result

Implemented by a Sonnet subagent after OpenCode hit its free usage limit

## Files changed
- desktop/elisium_downloader/engine/queue.py
- desktop/elisium_downloader/engine/runner.py
- desktop/tests/test_queue.py, desktop/tests/test_runner.py (new tests appended)
- desktop/tests/test_e2e_local.py (new, `@pytest.mark.e2e`)
- desktop/pyproject.toml (e2e marker only)
- (HANDOFF.md was already edited by OpenCode; untouched by me)

## Fixes
1. DONE. `add()` of a done/skipped item checks the file (`file_path`, else `[<id>]` scan using the YouTube key or the key learned from the probe). If gone: drops the archive entry under the archive lock (not while a download is active), resets the item and puts it back to `queued`. failed/cancelled untouched. Limitation: if a download is active at that moment the stale archive entry is kept; the later `_attempt` reconcile runs read-only too, so yt-dlp may then skip it and it ends `skipped` (safe direction).
2. DONE. `--print-to-file after_move:filepath <temp>/item-<id>.path` (OpenCode's runner part kept; its broken queue.py edit referencing `self._opts` removed). Verified with a real yt-dlp run: path file written, and progress-template JSON lines are still emitted. Queue reads the last line, deletes the file, falls back to the YouTube `[<id>]` scan.
3. DONE. Exit 0 + "has already been recorded in the archive" + no reported path -> `skipped` with ALREADY_DOWNLOADED (error also set on the item). Extra: for non-YouTube sites the archive key (`<extractor_key lower>:<id>` from the probe) is learned so the existing reconcile works for them (needed for the fresh-queue redownload e2e).
4. DONE. `stage_for_postprocessor`: MoveFiles/Metadata/FFmpegMetadata/SponsorBlock return "downloading" and the queue ignores such postprocessor events for state changes (so they never move merging/converting back or to converting). Other names stay converting; Fixup* is converting. Removed OpenCode's unused set with the `embedsport` typo.

## Tests
Command: `cd desktop && nice .venv/bin/python -m pytest -q`
    ........................................................................ [ 81%]
    .....s..........................                                         [100%]
    175 passed, 1 skipped in 17.51s

(1 skipped is the pre-existing `live` network test. The 2 e2e tests ran, not skipped.)

## Unfinished
Nothing known. Nothing committed.
