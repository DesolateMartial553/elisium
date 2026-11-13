# Brief 1C - yt-dlp runner + queue (run after 1B passes audit)

Read `AGENTS.md`, `core-spec/SPEC.md`, and the 1A/1B modules.

## Create
- `desktop/elisium_downloader/engine/runner.py`
  - `probe(url, ytdlp="yt-dlp") -> dict` runs `yt-dlp -J --no-download --no-playlist`-equivalent for single videos (`--flat-playlist` for playlists), returns parsed JSON. Raises `ProbeError(ErrorInfo, raw)`.
  - `build_command(opts) -> list[str]`: `-P home:<output>`, `-P temp:<tmp>`, `--download-archive`, `--no-overwrites`, `-o "%(title).150B [%(id)s].%(ext)s"`, `--continue`, `--newline`, `--progress-template` emitting JSON lines (`download:` with status/downloaded_bytes/total_bytes/speed/eta; `postprocess:` stage), `--limit-rate` when set, `-f <selector>`, `--retries 3`, `--fragment-retries 3`.
  - `run(opts, on_event) -> subprocess handle`: starts the process, parses progress JSON lines, calls `on_event(dict)`; maps stages to downloading/merging/converting; supports `terminate()` and keeps `.part`.
- `desktop/elisium_downloader/engine/queue.py`
  - `class DownloadQueue`: concurrency 1-5, states per SPEC.md, `add(url)` normalises via `urlnorm` and rejects a second item with the same dedupe identity (returns the existing item). Identity is `video_key(url)` when not None, else `normalize_url(url)` (video_key is None for non-YouTube sites, so without this fallback they would never dedupe), `pause/resume/retry/cancel(item_id)`, backoff 5s/15s/45s via an injectable `sleep` for tests, archive reconcile before download, writes to `History`, error text via `errors.explain`. Thread-based; emits events through a callback list (no Qt imports).
- `desktop/tests/test_runner.py`, `test_queue.py`
  - Use a fake yt-dlp script (small Python file written to a tmp dir) to simulate success, failure, 403, network error, slow progress. No network.
  - One optional `@pytest.mark.live` test downloading a short public video; skipped by default.

## Acceptance
`cd desktop && nice .venv/bin/python -m pytest -q` passes. Tests cover: build_command contains the dedupe flags and temp/home paths, progress parsing, stage mapping, concurrency limit honoured, duplicate add returns same item, pause keeps `.part`, resume uses `--continue`, backoff sequence 5/15/45 then failed, cancel state, archive skip gives `skipped`.

## Do not
Import PySide6, add dependencies, or run the live test unless told.

## Added after audit of 1B
- `Archive.add/remove` rewrite the whole file, and a running yt-dlp may append to it at the same time (lost update). In `queue.py` serialise every Archive call and archive reconcile behind one `threading.Lock`, and never call `archive.remove` while any item is in `downloading`/`merging`/`converting`. Add a test for this.
- Non-YouTube sites: dedupe identity falls back to `normalize_url(url)` (see above).
