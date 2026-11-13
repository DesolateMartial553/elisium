# Brief 1A - pure modules (no yt-dlp, no network, no GUI)

Read `AGENTS.md` and `core-spec/SPEC.md` first.

## Create (only these files)
- `desktop/pyproject.toml` - package `elisium_downloader`, Python >=3.11, pytest as dev dependency, console script `elisium-downloader = elisium_downloader.cli:main` (cli can be added later; do not create it now).
- `desktop/elisium_downloader/__init__.py` (version `0.1.0`), `desktop/elisium_downloader/engine/__init__.py`
- `desktop/elisium_downloader/engine/urlnorm.py`
  - `normalize_url(url: str) -> str` and `video_key(url: str) -> str | None`
  - YouTube: `youtu.be/ID`, `youtube.com/watch?v=ID`, `m.youtube.com`, `music.youtube.com`, `/shorts/ID`, `/embed/ID`, `/live/ID` all normalise to `https://www.youtube.com/watch?v=ID`; drop `si`, `feature`, `pp`, `utm_*`, `list`/`index` only when it is a single-video link (keep `list` for `/playlist` URLs); keep `t`/`start` only if it is a start time.
  - Other sites: lowercase scheme/host, strip fragment and `utm_*`, keep the rest.
  - `video_key` returns `"youtube:<ID>"` for YouTube, else `None`.
  - Invalid input (empty, no host) raises `ValueError`.
- `desktop/elisium_downloader/engine/errors.py`
  - `explain(raw_log: str) -> ErrorInfo` (dataclass: `message`, `fix`, `code`) implementing the table in SPEC.md, case-insensitive substring match, first match wins, fallback "Download failed."
- `desktop/elisium_downloader/engine/paths.py`
  - `output_dir()`, `temp_dir()`, `config_dir()`, `data_dir()`, `cache_dir()` per SPEC.md. Output uses `xdg-user-dir DOWNLOAD` via `subprocess` if available else `~/Downloads`, then appends `Elisium Downloader`. Every function accepts an optional `env`/`home` override for tests. Functions create the directory only when called with `create=True`.
- `desktop/tests/test_urlnorm.py`, `test_errors.py`, `test_paths.py`

## Acceptance checks (paste output in the result file)
```
cd desktop && nice .venv/bin/python -m pytest -q
```
Tests must cover: youtu.be vs watch?v= vs shorts give the same key; tracking params stripped; playlist URL keeps `list`; every row in the error table; paths use overrides and never touch the real home in tests.

## Do not
Add dependencies, call the network, import PySide6, or edit outside the files above.
