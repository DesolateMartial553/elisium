# Brief 2B - quality presets, settings, history page, sidebar

Read `AGENTS.md`, `core-spec/SPEC.md`, `engine/queue.py`, `engine/history.py`, `engine/paths.py`, `ui/main_window.py`, `ui/model.py`. Tests are headless (`QT_QPA_PLATFORM=offscreen`, already set in `tests/conftest.py`); never open a visible window, never touch the real home, never use the network.

## Part 1 - engine bits (no Qt)
- `desktop/elisium_downloader/engine/presets.py`: `PRESETS` ordered dict, each `Preset(id, label, format_selector, extra_args)`:
  `best` "Best quality" `bestvideo*+bestaudio/best`; `1080p` `bestvideo*[height<=1080]+bestaudio/best[height<=1080]`; `720p` same with 720; `audio-mp3` "Audio only (MP3)" `bestaudio/best` + `-x --audio-format mp3`; `audio-m4a`, `audio-opus`, `audio-flac` likewise; `smallest` "Smallest file" `wv*+wa/w`. Helpers `get(id)` (unknown id -> `best`), `DEFAULT_ID = "best"`.
- `engine/queue.py` (add only): `set_limit_rate(value: str | None)`, `set_format_selector(selector: str)`, `set_extra_args(args: Sequence[str])`, applied to downloads that START after the call (document this); the queue passes `extra_args` into `DownloadOptions`. Add tests in `tests/test_queue.py`.
- `desktop/elisium_downloader/ui/settings.py`: `Settings` dataclass (`concurrency=2`, `speed_limit: str|None=None` e.g. `"2M"`, `preset_id="best"`, `notify_on_done=True`, `close_to_tray=False`) with validation (concurrency 1-5; speed limit matches `^\d+(\.\d+)?[KMG]?$` or None; unknown preset -> default), `load(path)`/`save(path)` as JSON, atomic write (temp file + `os.replace`), a corrupt or missing file gives defaults without raising, unknown keys ignored. Default path `config_dir()/"settings.json"`; every function takes a path so tests never touch the real home. `apply(settings, queue)` pushes concurrency, limit, preset format + extra args into the queue.

## Part 2 - UI
- Restructure `MainWindow` into a **sidebar + stacked pages**: a `QListWidget` sidebar (Downloads, History, Settings; accessible name "Sections", arrow keys switch, `Ctrl+1/2/3`) and a `QStackedWidget`. The existing downloads view becomes the first page unchanged in behaviour. Keep every existing test passing (update tests only where the layout change forces it).
- `ui/history_page.py` `HistoryPage(QWidget)`: search `QLineEdit` (accessible name "Search history", debounce 200 ms) + `QTableView` showing Title, Site/URL, State (word + icon like the downloads table), Date, File. If a done item's `file_path` no longer exists show the status text "File missing" (word, not just colour). Buttons and context menu: **Open file**, **Open folder**, **Download again** (calls `queue.add(url)`; the engine already handles deleted-file re-download), **Copy link**, **Delete entry** (confirm first; only deletes the history row, never the file). Refresh when the page is shown and when a queue item reaches a terminal state.
- `ui/settings_page.py` `SettingsPage(QWidget)`: form with **Parallel downloads** (spin box 1-5), **Speed limit** (checkbox "Limit speed" + number + unit combo KB/s, MB/s), **Default quality** (combo from `PRESETS`), **Notify when a download finishes** (checkbox), **Keep running in the tray when closed** (checkbox, stored only; wired in a later brief), read-only **Download folder** label with an **Open** button, **yt-dlp version** label filled from `yt-dlp --version` on a worker thread (shows "checking..." then the version, or "yt-dlp not found" in plain words; injectable for tests), and **Open data folder**. Changes save immediately and `apply()` to the queue. Every control has an accessible name and description; labels are tied to inputs with `setBuddy`.
- `ui/app.py`: load settings at start, apply them, pass them to the window; use an injectable settings path in `create_app`.

## Tests (headless)
presets table and unknown-id fallback; settings validation, round-trip, corrupt file, atomic write; `apply` calls the queue setters; queue setters affect the next started download (fake runner); sidebar switches pages and shortcuts exist; history page search, "File missing", delete only removes the row (file stays), Download again calls the queue; settings page writes the file and applies live; yt-dlp version label with an injected fake. One offscreen `grab()` of the History page and of the Settings page saved to `briefs/phase2-b-history.png` and `briefs/phase2-b-settings.png` via a throwaway script kept in the scratchpad dir, not the repo.

## Acceptance
```
cd desktop && nice .venv/bin/python -m pytest -q     # all pass, paste the summary line
```

## Do not
Add dependencies, import anything outside stdlib + PySide6, touch `engine/` beyond the additions above, commit, or run the real yt-dlp except `yt-dlp --version` (and not at all inside tests). Write `briefs/phase2-b-history-settings.result.md`.
