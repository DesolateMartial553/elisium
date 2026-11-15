# Brief 9D - desktop: find the signed-in browser for the user

Read `AGENTS.md`, `core-spec/SPEC.md` ("Sign-in (cookies)"), `briefs/phase8-a-desktop-instagram-tiktok.result.md`, `briefs/phase9-a-errors-and-keys.result.md`, `design/DESIGN.md`, then `desktop/elisium_downloader/`: `ui/settings.py` (`COOKIE_BROWSERS`), `ui/settings_page.py` (Accounts card, `fetch_ytdlp_version`, `show_accounts`), `ui/main_window.py` (`SIGN_IN_CODES`, `open_accounts`, the failed-item "Sign in..." menu, how Retry works), `engine/queue.py` (`set_cookies`). Edit only under `desktop/` and write `briefs/phase9-d-desktop-browser-autodetect.result.md`. No android edits, no commit/push, no network.

## Goal
Today the user has to know which browser they are signed in to Instagram with, find Settings > Accounts, pick it, and retry. Make that automatic: detect it, offer it in one click, and retry the failed items.

## Hard privacy rules
- Detection only checks WHETHER a signed-in Instagram session exists. It may read the cookie names/hosts from a browser cookie database, never the `value`/`encrypted_value` columns, never copy the database anywhere, never write to it, and never log or store anything from it. Open it read-only (`file:<path>?mode=ro&immutable=1` URI) so a running browser is not disturbed; any error (locked, missing, corrupt) means "not detected".
- Tests must NEVER touch the real home directory or real browser profiles: build fake profile folders with small SQLite files under `tmp_path` and pass the home directory in as an argument. (OpenCode is configured not to read browser profiles; do not try to.)

## Build
1. **Detector** `engine/browsers.py`: `detect_instagram_browsers(home: Path) -> list[str]`, ordered like `COOKIE_BROWSERS`, containing a browser only when a profile's cookie DB has a cookie with host ending `instagram.com` and name `sessionid`. Linux paths (relative to `home`): Firefox `.mozilla/firefox/*/cookies.sqlite` (table `moz_cookies`, columns `host`, `name`); Chromium family `Cookies` or `Network/Cookies` under each profile dir (`Default`, `Profile *`) of `.config/google-chrome`, `.config/chromium`, `.config/BraveSoftware/Brave-Browser`, `.config/microsoft-edge`, `.config/vivaldi`, `.config/opera` (table `cookies`, columns `host_key`, `name`). Also accept the flatpak/snap Firefox and Chromium profile roots if trivial; skip them if not. Never raises.
2. **Settings page**: in the Accounts card, when no browser or file is configured and a browser is detected, show a line "Signed in to Instagram in Firefox." with a "Use Firefox" button that selects it (same code path as choosing it in the dropdown, so it is persisted and applied). Detection runs off the UI thread (or lazily on showing the page) and never blocks startup. Keep the existing dropdown and file picker unchanged. Show the yt-dlp version line there (use `fetch_ytdlp_version`) with the text "If Instagram stops working, update yt-dlp (pacman -Syu / pip)".
3. **Sign-in dialog**: the failed-item "Sign in..." entry and the status-bar hint now open a small modal dialog (`ui/sign_in_dialog.py`, Afterglow styling, keyboard operable, accessible names): explains "Sign in to Instagram in your browser, then come back and retry"; if browsers were detected, a combo + "Use this browser and retry" which sets the cookie browser (persisted like Settings does), then retries every currently failed item whose error code is in `SIGN_IN_CODES` (use the existing retry path, not a new one); a secondary "Open Settings > Accounts" button for the old behaviour; if nothing is detected, say so plainly and offer only "Open Settings > Accounts" and "Retry". Do not auto-open it; it only opens from the existing entry points.
4. Do not change `_cookie_args` / which sites get cookies. Do not add dependencies (stdlib `sqlite3`, `pathlib`, `glob` only).

## Tests (no network, no real profiles)
`test_browsers.py`: fake Firefox and Chromium profiles in `tmp_path` (with and without the `sessionid` row, a different host, a corrupt file, a missing file, a locked/empty DB), ordering, never raising, and that only `name`/`host` columns are ever selected (assert via a DB whose value column would raise if read, or by inspecting the SQL). UI tests: the Accounts hint appears/hides, "Use Firefox" persists and applies, the dialog's retry re-queues only sign-in failures, keyboard/accessible names. Keep all existing tests (570 pass, 2 skipped).

## Acceptance (paste real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= QT_QPA_PLATFORM=offscreen nice .venv/bin/python -m pytest -q
python3 ../design/contrast_check.py
```
All pass; contrast check stays ALL PASS. List "Needs the real session" items (real Firefox/Chrome DB layouts, Hyprland dialog focus). Write the result file even if low on budget.
