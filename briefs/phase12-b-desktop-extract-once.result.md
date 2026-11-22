# Brief 12B result - desktop: extract once, copy audio when possible

Started by OpenCode (partial edits to runner.py, queue.py, presets.py; it stopped when its usage ran out, with no
tests and no result file). Reviewed and finished by Claude (2026-11-22). Not committed.

## Review of OpenCode's partial diff
- `runner.py` (`DownloadOptions.info_json`, `--load-info-json` replacing the URL) and `presets.py` were correct.
- `queue.py` was incomplete and broken: `_attempt` already called `self._download(item, info, probed_at)` but
  `_download` still took only `item` (TypeError on every download), `info_json` was never passed to the runner, and
  there was no fallback re-run. `_write_info_json` opened the file with O_TRUNC (no fresh create / symlink guard).

## Files changed
- `desktop/elisium_downloader/engine/runner.py` - `DownloadOptions.info_json: Path | None`; `build_command` adds
  `--load-info-json <file>` and drops the URL only when it is set (everything else identical).
- `desktop/elisium_downloader/engine/queue.py` - `reuse_probe: bool = True` and injectable `clock` arguments;
  `REUSE_PROBE_MAX_AGE = 300.0`; `_info_is_usable` (dict, not `_type == "playlist"`, has `formats` or `url`, probe
  under 300 s old); `_write_info_json` (fresh file, `O_EXCL|O_NOFOLLOW`, mode 0600) at `<temp>/<item id>.info.json`;
  `_download` now wraps `_download_once`: runs with the info JSON, deletes the file afterwards (finally), and re-runs
  ONCE from the URL, with no retry count and no backoff, when the info run failed before any progress line or its
  error is `http_403` / `http_410` / `format_unavailable` or its log says 410 / expired / format not available. The
  info dict lives only on the attempt (never on the item, never in history).
- `desktop/elisium_downloader/engine/presets.py` - `audio-m4a`: `bestaudio[ext=m4a]/bestaudio/best`; `audio-opus`:
  `bestaudio[acodec=opus]/bestaudio/best`; `-x --audio-format` kept; MP3, FLAC and video presets unchanged.
- Tests: `desktop/tests/test_runner.py` (2 new), `desktop/tests/test_queue.py` (11 new, 13 cases with parametrize),
  `desktop/tests/test_presets_settings.py` (1 new), `desktop/tests/test_ui_quality.py` (existing assertion updated:
  the playlist dialog's audio-m4a item now carries the new selector).

## Tests added
argv with `info_json` (flag, no URL, rest equal to the URL argv, file mode 0600, file deleted); `reuse_probe=False`
argv equals the URL argv exactly; unusable info (playlist, no formats, empty formats, non-dict, probe older than 300 s)
-> URL argv; probe just under 300 s is reused; 403 on the info run -> exactly one immediate URL run, done, no sleeps,
`attempts` still 0, info file gone; non-zero exit before any progress -> one re-run; re-run failing is final (2 runs
total); failure after progress that is not stale is not re-run; info file removed when the runner raises; both preset
selectors (and MP3/FLAC unchanged).

## Commands run
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
608 passed, 2 skipped in 477.29s (0:07:57)
```
(Pass, no failures, no flaky test seen this run; the 2 skips are the `@pytest.mark.live` tests.)
`python3 design/nightshelf/contrast_check.py` -> ALL PASS.

## Deviations / notes
- Updated one existing assertion in `test_ui_quality.py` (not named in the brief, but it pins the old m4a selector;
  the brief allows "their tests under desktop/tests/").
- A failed info-JSON run that never reached a progress line is re-run from the URL even if the error text is not
  403-like (brief item 3's "exits non-zero before the first progress line"). A re-run after a merging/converting
  state resets the item to `downloading`.
- `info_json` is passed to the runner only through `DownloadOptions`; no UI file reads `reuse_probe` yet (12C wires
  the "Faster downloads" setting to the `reuse_probe` constructor argument).
- `briefs/phase10-b1-desktop-media-engine.md` shows as untracked in git; it was not created by this brief.

## Unfinished
Nothing from the brief. Live check against a real site (that yt-dlp accepts the loaded info for each extractor) is
not in pytest; `tools/bench.py` measured it for YouTube in 12A.
