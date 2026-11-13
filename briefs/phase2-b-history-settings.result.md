# Brief 2B result

Implemented by the fallback implementer (OpenCode had only written presets.py).

## Files
- engine/presets.py: reviewed against the brief, correct, kept unchanged.
- engine/queue.py: added `set_limit_rate`, `set_format_selector`, `set_extra_args` (apply to downloads that START afterwards; documented); `_download` snapshots them under the lock and passes `extra_args` to `DownloadOptions`.
- ui/settings.py, ui/settings_page.py, ui/history_page.py (new).
- ui/main_window.py: sidebar (QListWidget "Sections") + QStackedWidget, Ctrl+1/2/3, toolbar shown only on Downloads; new keyword args `settings`, `settings_path`, `version_fn`; status-bar message when a download finishes and notify is on.
- ui/app.py: `settings_path` and `version_fn` params; loads and applies settings (injected queue with no path: defaults, nothing on disk).
- Tests: new tests/test_presets_settings.py, tests/test_ui_pages.py; added setter tests to tests/test_queue.py; tests/test_ui_main_window.py changed only to inject `version_fn` and `settings_path` (so no real yt-dlp or home access).
- Screenshots: briefs/phase2-b-history.png, briefs/phase2-b-settings.png (script in scratchpad, not the repo).

## Check
`cd desktop && nice .venv/bin/python -m pytest -q` -> `252 passed, 1 skipped in 19.64s`

## Notes / unfinished
- `close_to_tray` is stored only. `notify_on_done` shows a status-bar message only (no desktop notification).
- Speed limit above 999 KB/MB etc. is allowed up to 100000; a stored "G" value shows as MB/s x1024.
- Download folder row in the Settings screenshot is a temp path (throwaway script).
