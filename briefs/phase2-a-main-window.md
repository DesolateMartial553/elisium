# Brief 2A - main window wired to the queue (PySide6 Widgets)

Read `AGENTS.md`, `core-spec/SPEC.md`, then `desktop/elisium_downloader/engine/queue.py` (public API: `add`, `pause`, `resume`, `retry`, `cancel`, `items`, `add_listener`, `start`, `stop`, `set_concurrency`; listener events `added`, `state`, `progress`, `item`) and `engine/paths.py`.

Use **QtWidgets** (not QML): Qt's accessibility bridge (AT-SPI, used by Orca) is strongest on standard widgets. PySide6 6.12 is installed in `desktop/.venv`. Never open a visible window while testing: tests run with `QT_QPA_PLATFORM=offscreen` (set it in `desktop/tests/conftest.py` before importing PySide6).

## Create (only these files)
- `desktop/elisium_downloader/ui/__init__.py`
- `desktop/elisium_downloader/ui/bridge.py` - `QueueBridge(QObject)`: registers a queue listener, and re-emits every event as a Qt signal `event(dict)` using a queued connection, because queue listeners run on worker threads while the queue lock is held and Qt widgets may only be touched on the GUI thread. The listener callback must do nothing but emit the signal (no widget access, no queue calls).
- `desktop/elisium_downloader/ui/model.py` - `DownloadModel(QAbstractTableModel)` with columns `Title`, `Status`, `Progress`, `Speed`, `ETA`, `Size`. Fed by bridge events and an initial `queue.items()` snapshot. Provide `item_id_at(row)`, `snapshot_at(row)`. Status text uses a **word plus an icon character**, never colour alone: `Queued`, `Checking`, `Downloading`, `Merging`, `Converting`, `Paused`, `Done`, `Failed`, `Skipped`, `Cancelled`. Title falls back to the URL until the probe supplies one. Format bytes, speed and ETA in plain units (`4.2 MB/s`, `1m 20s`). `Qt.AccessibleTextRole` for each row returns one full sentence, e.g. `"Big Buck Bunny, downloading, 42 percent, 4.2 megabytes per second, 1 minute left"`. For failed items the status cell tooltip is the plain-language `error.message` plus `error.fix`.
- `desktop/elisium_downloader/ui/main_window.py` - `MainWindow(QMainWindow)`:
  - URL bar: a single-line `QLineEdit` (placeholder "Paste a video link"), an **Add** button, and a **Paste** button that reads the clipboard. Pasting or entering text containing several lines or several whitespace separated URLs adds each one (ignore blank/invalid lines, show a status-bar message "Added 3 links, 1 ignored"). A link the queue returns as an already-known item shows "That video is already in the list" in the status bar instead of adding a row.
  - Queue: a `QTableView` over the model (single-row selection, no editing, stretch Title column, a progress bar drawn in the Progress column by a `QStyledItemDelegate` that ALSO draws the percent text on it).
  - Toolbar with text+icon actions **Pause**, **Resume**, **Retry**, **Cancel**, **Open folder**, enabled only when valid for the selected item's state (pause: queued/probing/downloading/merging/converting; resume: paused; retry: failed/cancelled; cancel: any non-terminal; open folder: done, opens the file's folder with `QDesktopServices`, falls back to the output dir). The same actions on a right-click context menu plus **Copy link**.
  - Shortcuts: `Ctrl+V` while the table is focused pastes and adds, `Ctrl+L` focuses the URL bar, `Space` pause/resume toggle on the selected row, `Ctrl+Q` quit, `F1` shows a small shortcut cheat-sheet dialog.
  - Status bar: summary "2 downloading, 1 queued, 5 done".
  - Accessible names and descriptions on every control (`setAccessibleName`, `setAccessibleDescription`); tab order URL bar, Paste, Add, table, toolbar. Visible focus must not be disabled. Window title "Elisium Downloader".
  - Closing the window while downloads are active asks "Downloads are running. Pause them and quit?" (Pause and quit / Keep downloading / Cancel). Keep downloading simply cancels the close for now (tray comes later).
- `desktop/elisium_downloader/ui/app.py` - `create_app(argv, *, queue=None, ...) -> (QApplication, MainWindow, DownloadQueue)` building the real `History(data_dir()/"history.sqlite")`, `Archive(data_dir()/"archive.txt")`, `DownloadQueue(history, archive, output_dir(create=True), temp_dir(create=True))` with `queue.start()`; accept an injected queue/dirs so tests never touch the real home. `run(argv)` runs the event loop and stops the queue on exit.
- `desktop/elisium_downloader/cli.py` - `main(argv=None)`: no arguments launches the GUI via `ui.app.run`. (Subcommands come later; do not add them.) This makes the console script in `pyproject.toml` work.
- `desktop/pyproject.toml` - add `dependencies = ["PySide6"]` only.
- `desktop/tests/conftest.py`, `desktop/tests/test_ui_model.py`, `test_ui_main_window.py`, `test_ui_bridge.py`

## Tests (all offscreen, no real network, no real home, no sudo)
Use the fake runner/probe injection that `DownloadQueue` already supports (see `tests/test_queue.py` for how). Cover: bridge delivers events on the GUI thread; model rows appear, update on progress, and show the right status word per state; accessible text sentence; multi-URL paste counts; duplicate message; toolbar enablement per state; closing with active downloads prompts (mock the dialog). Also one test that renders `MainWindow.grab()` to a PNG in `tmp_path` (non-empty) so a human can look at it.

## Acceptance
```
cd desktop && nice .venv/bin/python -m pytest -q     # all pass; paste the summary
QT_QPA_PLATFORM=offscreen nice .venv/bin/python -c "from elisium_downloader.ui.app import create_app; print('import ok')"
```
Then save one offscreen screenshot of a window with 4 sample items (queued, downloading 42%, done, failed) to `briefs/phase2-a-screenshot.png` using a small throwaway script you delete afterwards (put it in `/tmp/claude-1000/-home-desolate/7a401cb2-47dc-4da1-8d9c-bc19ed56873a/scratchpad/`, not in the repo).

## Do not
Touch `engine/` except for a genuine bug (say so in the result), add dependencies other than PySide6, open visible windows, run yt-dlp for real in UI tests, or commit. Write `briefs/phase2-a-main-window.result.md` (files, exact test output, anything unfinished).
