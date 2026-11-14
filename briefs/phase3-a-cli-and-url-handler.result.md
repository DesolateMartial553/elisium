# Result - Brief 3A: single instance, `elisium add`, `elisium://` handler

Status: implemented; pytest and the isolated end-to-end run both completed.

## Files changed (all under `desktop/`)
- NEW `elisium_downloader/ui/ipc.py` - link validation, `elisium://` parsing, socket path, JSON protocol (`handle_message`), `IpcServer` (QLocalServer), `acquire_server`, `send_add` (QLocalSocket client).
- `elisium_downloader/cli.py` - argparse: no args (GUI), `add URL...`, `add -`, `elisium://add?...`, `--version`, `--help`; injectable `launcher`/`sender`/streams for tests.
- `elisium_downloader/ui/app.py` - `run()` takes the single-instance lock, hands links to a running instance instead of opening a second window/queue, wires `window.receive_links`, closes the server on exit.
- `elisium_downloader/ui/main_window.py` - `add_text` split into `_queue_links` / `_report_added` (behaviour unchanged); new `receive_links(urls)` (default preset only, playlist links go to the picker one at a time via `QTimer.singleShot`, never queued; no `raise_`/`activateWindow`).
- `elisium_downloader/ui/tray.py` - `notify_added(count)`: "Elisium" / "Added N links" if `notify_on_done` is on.
- `packaging/elisium.desktop` - `Exec=elisium %u`, `MimeType=x-scheme-handler/elisium;` (`desktop-file-validate` passes). Dev launcher already forwards `"$@"`, unchanged.
- NEW tests: `tests/test_ipc.py`, `tests/test_cli.py`, `tests/test_ui_receive.py`.
- Docs: no `desktop/README` exists and `ACCESSIBILITY.md` is not relevant, so docs skipped (the `--help` text documents the commands).

## Commands run
- `cd desktop && QT_QPA_PLATFORM=offscreen nice .venv/bin/python -m pytest -q` -> PASS: `446 passed, 1 skipped in 24.97s` (the 391 old tests untouched and passing; the skip is the existing live/e2e marker one).
- `desktop-file-validate packaging/elisium.desktop` -> PASS.
- Isolated end-to-end (temp `HOME`, `XDG_RUNTIME_DIR` (0700), `XDG_DATA/CONFIG/CACHE_HOME`, `XDG_DOWNLOAD_DIR`, offscreen), real GUI start-up through `elisium_downloader.cli.main` with a small harness in the scratchpad that only logs `receive_links` and turns SIGTERM into quit:
  - app up, socket `srw-------` (owner only) + lock file.
  - `elisium add http://127.0.0.1:9/a` -> `Sent 1 link to Elisium`, exit 0; app log: `RECEIVED on MainThread [...a] -> {'added': 1,...} | status bar: 'Added 1 link' | rows: 1`.
  - `elisium "elisium://add?url=http%3A%2F%2F127.0.0.1%3A9%2Fb"` -> `Sent 1 link to Elisium`, exit 0; received as above (rows: 2).
  - `printf '...c ...d\nfile:///etc/passwd\n' | elisium add -` -> `Sent 2 links to Elisium (1 ignored)`, exit 0 (rows: 4).
  - `elisium add file:///x` -> exit 1; `elisium` with no args while running -> exit 0, no output, no second window or queue.
  - SIGTERM -> app exit 0, socket file removed; history db in the temp dir has the 4 rows; real `~/.local/share/elisium`, `~/Downloads/Elisium`, `~/.config/elisium` listing identical before/after.
  - No-instance path: `elisium add http://127.0.0.1:9/first` started the GUI and printed `Started Elisium and added 1 link`; a second `elisium add` while it ran printed `Sent 1 link to Elisium` and the first instance received it.

## Deviations / decisions to audit
- Test URLs were `http://127.0.0.1:9/...` instead of example.com so no real network download starts (no fake-runner env var exists). The queue was live, so yt-dlp ran against the refused loopback port only.
- **Qt `listen()` silently replaces a live socket** when `UserAccessOption` is set (found in testing: a second process hijacked the first). So `acquire_server` first takes an `flock` on `elisium.sock.lock` (dies with the process; no stale-lock problem), then probes with a connect, then removes a stale socket file, then listens. The lock file stays in `$XDG_RUNTIME_DIR` (0600, empty).
- `send_add` must not create a `QCoreApplication` (it blocks the later `QApplication` when the CLI falls through to starting the GUI; found in e2e, now has a regression test).
- Reply has one extra key, `"playlists": n`, only when playlist links were handed over. The three specified keys are unchanged.
- Errors (no valid link, refused message) go to stderr; outcomes go to stdout. Links over 50 are sent as chunks of 50. `elisium add` blocks the terminal when it has to start the GUI (like any GUI app). Qt options such as `-platform` on the command line are now a usage error (exit 2).
- If a start-up race loses the lock to a still-starting instance, `run()` retries sending for up to 3 s, then exits 1 with a message.
- Notification wording: title "Elisium", text "Added 2 links". It only fires when a tray controller exists (not offscreen) and `notify_on_done` is on.
- Playlist picker: opens after the reply is sent (so the CLI does not wait on a modal dialog); several playlist links open one after another.
- In-process tests use a stdlib socket client in a thread (Qt blocking calls hold the GIL and would deadlock the in-process server); the real `send_add` is tested from a separate process.

## Unverified
- A real browser click on an `elisium://` link and `xdg-mime`/handler registration (nothing installed or registered, as instructed).
- Real Hyprland behaviour (no raise/focus is asserted by test only: `raise_`, `activateWindow`, `showNormal`, `show` are patched and shown not called on receive).
- Real tray icon and dunst notification; only a fake tray records `("Elisium", "Added 2 links")`.
- The real PlaylistDialog modal flow was not driven (`_run_dialog` is replaced in tests); only that the picker is requested and nothing is queued.
- Harness note: a plain SIGTERM to the GUI while downloads are active triggers the existing "quit while downloading?" confirm dialog (existing behaviour, not changed); the clean-stop runs above had no active download at that moment.
