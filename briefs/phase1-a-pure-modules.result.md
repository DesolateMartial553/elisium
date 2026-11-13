# Brief 1A result - pure modules

Status: done.

## Files created
- `desktop/pyproject.toml` - package `elisium_downloader`, `requires-python >=3.11`, pytest under `[project.optional-dependencies] dev`, console script `elisium-downloader = elisium_downloader.cli:main` (target intentionally not created yet), pytest `testpaths`.
- `desktop/elisium_downloader/__init__.py` - `__version__ = "0.1.0"`.
- `desktop/elisium_downloader/engine/__init__.py` - package marker.
- `desktop/elisium_downloader/engine/urlnorm.py` - `normalize_url`, `video_key`.
- `desktop/elisium_downloader/engine/errors.py` - `ErrorInfo` dataclass + `explain`.
- `desktop/elisium_downloader/engine/paths.py` - `output_dir`, `temp_dir`, `config_dir`, `data_dir`, `cache_dir`.
- `desktop/tests/test_urlnorm.py`
- `desktop/tests/test_errors.py`
- `desktop/tests/test_paths.py`

No other files touched. No dependencies added, no network, no PySide6 import.

## Behaviour notes
- YouTube: `youtu.be`, `watch?v=`, `m.`, `music.`, `/shorts/`, `/embed/`, `/live/`, `/v/` all collapse to `https://www.youtube.com/watch?v=ID`. `si`/`feature`/`pp`/`utm_*` dropped; `list`/`index` dropped on single-video links; a `/playlist` URL keeps `list` (and `index`). `t`/`start` kept only when numeric or `1h2m3s` form, normalised to `t=` so the same start time dedupes.
- Other sites: scheme/host lowercased, fragment and `utm_*` stripped, everything else (including `si`/`feature`/`pp`) kept.
- `video_key` returns `youtube:<ID>` or `None`; empty / no-host / non-http(s) input raises `ValueError` in both functions.
- Errors follow the SPEC table order (first match wins, case-insensitive), fallback `Download failed.` / `See Details` / code `unknown`.
- Paths: `create=False` by default, never creates anything. Passing an `env` override makes the call hermetic: `xdg-user-dir` is not run, only an explicit `XDG_DOWNLOAD_DIR` is used (supports `$HOME/...`), else `<home>/Downloads`. Without `env`, `xdg-user-dir DOWNLOAD` is tried first, then `XDG_DOWNLOAD_DIR`, then `~/Downloads`. All XDG base dirs honoured.

## Commands run
```
cd desktop && nice .venv/bin/python -m pytest -q
.........................................                                [100%]
41 passed in 0.09s
```
PASS (41 tests).

Also spot-checked real (no-override) path resolution once with a short script; observed:
```
output_dir  = /home/desolate/Downloads/Elisium Downloader
temp_dir    = /home/desolate/.cache/elisium-downloader/tmp
config_dir  = /home/desolate/.config/elisium-downloader
data_dir    = /home/desolate/.local/share/elisium-downloader
cache_dir   = /home/desolate/.cache/elisium-downloader
```
Confirmed none of those directories were created by the call (`ls` returned "No such file or directory" for all five).

## Unfinished / follow-ups
- `elisium_downloader.cli:main` does not exist yet (per brief); installing the console script will fail until a later brief adds it.
- Package was not `pip install`ed; tests run from `desktop/` with the existing venv.
