# Brief 1C result - yt-dlp runner + queue

Status: done.

## Files created
- `desktop/elisium_downloader/engine/runner.py` - `probe()`, `build_command()`, `run()`, `DownloadProcess`, progress parsing, `DownloadOptions` dataclass.
- `desktop/elisium_downloader/engine/queue.py` - `DownloadQueue` with concurrency 1-5, states per SPEC, `add/pause/resume/retry/cancel`, backoff 5/15/45s, archive reconcile, `History` integration, thread-based event emission (no Qt).
- `desktop/tests/test_runner.py` - 28 tests (27 passing, 1 `@pytest.mark.live` skipped by default).
- `desktop/tests/test_queue.py` - 27 tests.

## Files modified
- `desktop/pyproject.toml` - added `markers` section for the `live` mark.

## Acceptance checks
```
cd desktop && nice .venv/bin/python -m pytest -q
161 passed, 1 skipped in 3.65s
```
Coverage per brief:
- `build_command` contains `--download-archive`, `--no-overwrites`, `-P home:`, `-P temp:`, `--continue`, `--newline`, both `--progress-template` lines, `-f`, `--retries 3`, `--fragment-retries 3` PASS.
- Progress parsing maps JSON lines to events with `downloaded_bytes`, `total_bytes`, `speed`, `eta`, `percent`, and stages `downloading`/`merging`/`converting` PASS.
- Stage mapping: download->downloading, Merger->merging, other post-processors->converting PASS.
- Concurrency limit honoured PASS.
- Duplicate `add` returns same item via `video_key` for YouTube, `normalize_url` fallback for other sites PASS.
- Pause keeps `.part` file; resume reruns with `--continue` PASS.
- Backoff sequence 5/15/45s then `failed` PASS.
- Cancel sets state `cancelled` and terminates process PASS.
- Archive skip gives `skipped` state PASS.
- Archive calls serialised behind `threading.Lock`; `archive.remove` never called while any item is in `downloading`/`merging`/`converting` PASS.

## Non-functional requirements
- No PySide6 imports, no new dependencies, no network in unit tests, Python 3.11+, type hints throughout.
- Live test marked `@pytest.mark.live` and skipped unless `ELISIUM_LIVE_TESTS=1`.

## Unfinished / follow-ups
- UI layer (Phase 2) will subscribe to `DownloadQueue.add_listener` and marshal events onto Qt thread.
- Format selector UI and settings persistence not in this brief.
