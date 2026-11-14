# Brief 3A - single instance, `elisium add`, and the `elisium://` link handler

Goal: other programs (a terminal, a browser, a script, a future browser extension) can hand links to the running Elisium. Read `AGENTS.md` (Hyprland/Wayland rules apply: no raising or focusing the window), `core-spec/SPEC.md`, `desktop/elisium_downloader/cli.py`, `ui/app.py`, `ui/main_window.py` (`add_text`, `extract_urls`), `ui/tray.py`, `packaging/elisium.desktop`.

## Behaviour to build
1. **Single instance.** Starting the GUI when Elisium is already running must not open a second window or a second queue. Use `QLocalServer` / `QLocalSocket` (PySide6 only, no new dependencies). Server name is per user: put the socket under `$XDG_RUNTIME_DIR` (fall back to a per-uid name in the temp dir); never a fixed world-writable path. Handle a stale socket file left by a crash (a failed connect means remove it and become the server). Create the socket with owner-only permissions.
2. **Command line** (`cli.py`, stdlib `argparse`):
   - `elisium` with no arguments: launch the GUI as today (if already running: just tell the user nothing; do not error; exit 0 after asking the running instance to show a notification-free no-op - Wayland cannot raise the window).
   - `elisium add URL [URL ...]` and `elisium add -` (read links from stdin, one or many per line): send the links to the running instance; if none is running, start the GUI and add them once it is up. Print one plain line per outcome to stdout ("Sent 2 links to Elisium", "Started Elisium and added 1 link"); exit 0 on success, 1 if no valid link, 2 on usage error.
   - `elisium elisium://add?url=<percent-encoded URL>`: the same as `add URL` (this is how the desktop environment calls the handler). Also accept repeated `url=` parameters and a `urls=` parameter holding several links separated by whitespace or newlines (percent-encoded).
   - `elisium --version` and `--help`.
3. **Protocol messages** between client and running instance: one JSON object per connection, `{"v": 1, "action": "add", "urls": [...]}`, reply `{"ok": true, "added": n, "known": n, "ignored": n}`. Size limit (64 KiB) and a read timeout; reject anything malformed without crashing. Only the action `add` exists.
4. **Security rules (important - links arrive from untrusted pages).** Accept only `http` and `https` URLs, max 2048 chars each, max 50 per message. An `elisium://` URL may ONLY queue links with the default preset; it must never accept parameters that change format, output path, extra yt-dlp args, cookies or the settings. Unknown actions and parameters are ignored. Playlist/channel links are NOT expanded silently: they follow the existing playlist-picker path (the picker opens in the running window, which is a user-visible confirmation). Add a unit test per rule.
5. **Running-instance side** (`ui/`): a small `ipc.py` (server + client + parsing) and a hook in `app.py` so received links call `MainWindow.add_text(...)` on the GUI thread, and the user is told: status-bar message (already produced by `add_text`) plus a tray/desktop notification "Elisium: added 2 links" via the existing notification code, if notifications are enabled in settings. Never call `raise_`/`activateWindow`.
6. **Desktop entry.** Update `packaging/elisium.desktop`: `Exec=elisium %u`, `MimeType=x-scheme-handler/elisium;`, keep everything else. Do NOT install anything into `$HOME`; Claude installs the user copy and registers the handler after the audit. Also update `packaging/elisium-dev-launcher.sh` only if it needs to forward arguments (it already uses `"$@"`).
7. **Docs.** Add a short "Command line and links" section to `desktop/README` if one exists, otherwise to `desktop/ACCESSIBILITY.md` only if relevant; otherwise skip docs and mention it in the result file.

## Tests (no network, no real yt-dlp, no real home)
- URL/`elisium://` parsing: valid, percent-encoded, repeated `url=`, `urls=`, non-http schemes (`file:`, `javascript:`, `ftp:`), overlong, too many, unknown action, empty.
- IPC round trip in-process using a temporary `XDG_RUNTIME_DIR` (client sends, server callback receives; reply counts correct); malformed JSON, oversize, wrong version, slow client timeout.
- Stale socket recovery; socket permissions are owner-only.
- `cli.main` for `add`, stdin form, `--version`, bad usage exit codes, "no running instance -> starts GUI path" (inject a fake launcher; do not open a window).
- Main window integration: a received message adds items through `add_text` on the GUI thread (use the existing offscreen test setup); a playlist link opens the picker path and does not queue.
- Existing 391 tests must still pass.

## Acceptance (paste real output)
```
cd desktop
QT_QPA_PLATFORM=offscreen nice .venv/bin/python -m pytest -q
```
Then, in an **isolated environment** (temporary `XDG_RUNTIME_DIR`, `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` pointing into a temp dir, `QT_QPA_PLATFORM=offscreen`), run the real thing end to end once: start the app in the background, run `elisium add https://example.com/a` with the CLI, show that the running instance received it, then `elisium "elisium://add?url=https%3A%2F%2Fexample.com%2Fb"`, then stop it. The queue must not start a real network download (inject or set a fake runner via an environment variable only if one already exists; otherwise point at an unroutable `127.0.0.1` URL). Paste what happened. Do not touch the real `~/.local/share/elisium`.

## Do not
Run `sudo`, install anything into the real home, register the handler, push or commit, touch `android/`, add dependencies, call `raise_`/`activateWindow`. Write `briefs/phase3-a-cli-and-url-handler.result.md` (files changed, commands with pass/fail, what is unverified: real browser click on an `elisium://` link, real Hyprland behaviour, real tray/dunst notification).

## Finish properly
Run everything to the end before writing the result file. Write it even if running low on budget; state what is unfinished.
