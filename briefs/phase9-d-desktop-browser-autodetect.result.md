# Result: Brief 9D - desktop browser auto-detect

## Files changed (all under desktop/ plus this file)
- NEW `desktop/elisium_downloader/engine/browsers.py` - `detect_instagram_browsers(home)`, `detect_default()`, `BROWSER_ORDER`.
- NEW `desktop/elisium_downloader/ui/sign_in_dialog.py` - `SignInDialog`, `Detector` (worker-thread helper), `browser_label`.
- EDIT `desktop/elisium_downloader/ui/settings_page.py` - Accounts hint row ("Signed in to Instagram in Firefox." + "Use Firefox"), `use_browser`, `use_detected_browser`, `detected_browsers`, `detect_fn` kwarg, yt-dlp update hint label.
- EDIT `desktop/elisium_downloader/ui/main_window.py` - `detect_fn` kwarg, `open_sign_in_dialog`, `retry_sign_in_failures`, status-bar "Sign in..." button (shown only while a sign-in-coded failed item exists), context-menu "Sign in..." now opens the dialog. `open_accounts` unchanged.
- EDIT `desktop/tests/conftest.py` - autouse fixture replaces `browsers.detect_default` with `[]` so no test can scan the real home.
- NEW `desktop/tests/test_browsers.py` (13 tests), EDIT `desktop/tests/test_ui_pages.py` (+9 tests).

## Commands run (real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= QT_QPA_PLATFORM=offscreen nice .venv/bin/python -m pytest -q
592 passed, 2 skipped in 307.57s (0:05:07)
python3 ../design/contrast_check.py
... ALL PASS 0
```
(Baseline was 570 passed, 2 skipped; +22 new tests.)

## Privacy implementation
- Query selects only `name, host` (Firefox) / `name, host_key` (Chromium) with `WHERE name='sessionid'`; the host match (== instagram.com or ends with .instagram.com) is done in Python.
- Defence in depth: a SQLite authorizer denies reading any column other than name/host/host_key (and denies all writes). Tests check this with a spy on the authorizer and by showing `SELECT value` is denied.
- Opened with `file:<path>?mode=ro&immutable=1`, 0.2 s timeout; nothing copied, written, logged or stored; every exception returns "not detected". Test confirms file bytes/dir listing unchanged and that a DB held under EXCLUSIVE lock is still read.
- Tests only use fake profiles under tmp_path with `home` passed in. I never opened any real browser profile.

## Judgement calls
- Layering: `engine/browsers.py` keeps its own `BROWSER_ORDER` (engine must not import ui); a test asserts it equals `COOKIE_BROWSERS`.
- Flatpak/snap roots included (Firefox: org.mozilla.firefox, snap firefox; Chrome, Chromium, Brave, Edge flatpak/snap Chromium) since they are just extra path prefixes.
- If several browsers are detected the Accounts hint offers the first in COOKIE_BROWSERS order; the dialog lists all.
- Detection runs once on a daemon thread when the Settings page is built (never blocks startup). The dialog reuses that result when it exists, otherwise detects on its own thread.
- "Status-bar hint": the existing status message text is unchanged; I added a flat "Sign in..." button in the status bar that appears while any failed item has a SIGN_IN_CODES error, and opens the dialog. The dialog never opens by itself.
- "Use this browser and retry" goes through `SettingsPage.use_browser` (combo change -> `_changed` -> saved + `queue.set_cookies`), then `retry_sign_in_failures` calls `queue.retry` for failed items whose code is in SIGN_IN_CODES. The no-detection "Retry" button retries without changing settings.
- Dialog opens with `QDialog.open()` (window-modal, non-blocking) so tests and the event loop are not blocked.
- Hint row hides once a browser or cookies file is configured, and reappears if the user goes back to "Not signed in".

## Needs the real session
- Real Firefox and Chrome/Brave/etc. cookie DB layouts: only fake schemas tested. Chromium has used `Cookies` and `Network/Cookies`; both are tried. Newer Chrome may differ.
- `immutable=1` ignores the WAL file: a session cookie written very recently (Firefox uses WAL) may not be seen until the browser checkpoints or closes. Mandated by the brief; if detection misses a fresh sign-in this is the likely cause.
- Browsers with Chrome app-bound/keyring encryption: only presence of the row is checked, but yt-dlp itself decrypting them is outside this brief.
- Hyprland dialog behaviour (focus on open, modal stacking, whether `setFocus` on the default button takes effect on Wayland).
- Visual check of the Afterglow styling of the new dialog, status-bar button and Accounts row (global stylesheet covers QDialog/QPushButton and `primary`; not looked at on screen; contrast check does not cover them specifically).
- Whether the real default detection finds the user's actual profile (default uses `Path.home()`; never exercised in tests by design).
