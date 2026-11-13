# Brief 2C result

## Files
New: `desktop/elisium_downloader/engine/formats.py`, `ui/probe_worker.py`, `ui/thumbnail.py`, `ui/quality_dialog.py`, `ui/playlist_dialog.py`, `desktop/tests/test_formats.py`, `desktop/tests/test_ui_quality.py`, `briefs/phase2-c-quality.png`, `briefs/phase2-c-playlist.png`.
Edited: `engine/queue.py` (`add` overrides only: `format_selector`, `extra_args`, `title`; `_download` uses them), `ui/main_window.py` (Options button, playlist auto-probe, shortcuts, new `probe_fn`/`thumbnail_fetcher` kwargs), `tests/test_queue.py` (4 override tests appended).

## Command
`cd desktop && nice .venv/bin/python -m pytest -q` -> `321 passed, 1 skipped in 30.53s`

## Decisions to review
- `parse_range` lives in `engine/formats.py` (pure, named file).
- Ctrl+Return = same as Add/Enter (so a playlist link still opens the picker); Ctrl+Shift+Return = Options. They live in `MainWindow._add_shortcuts` because an existing test pins `_shortcuts` exactly.
- Dialogs start their own probe on construction; `MainWindow._run_dialog` is the single place `exec()` is called (tests replace it).
- Default probe = the queue's own `_probe_url`/`_ytdlp` (private attrs, via getattr).
- Playlist picker starts with every available entry ticked.
- Explicit empty `extra_args=()` is a real override (beats global audio args).
- Screenshots were taken offscreen with a throwaway script in the scratchpad.

## Unfinished / not verified
- Default `QNetworkAccessManager` thumbnail fetch only tested for refusing non-http URLs (no network). Real key presses for the shortcuts not tested (activated signal emitted instead).
- Nothing committed.
