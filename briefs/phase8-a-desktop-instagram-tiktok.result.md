# Brief 8A result - Instagram + TikTok videos and stories (desktop)

Date: 2026-11-14. Status: done, all acceptance checks pass.

## Files changed

Code (`desktop/elisium_downloader/`)
- `engine/runner.py` - `DownloadOptions.cookies_browser` / `cookies_file`; shared `_cookie_args()` used by `build_command` (`--cookies-from-browser <name>`, else `--cookies <path>`, browser wins) and by `probe()`; `probe()` gains the same two keyword arguments (stories can be probed); `_looks_like_playlist` now treats `instagram.com/stories/<user>/` and `instagram.com/stories/highlights/<id>/` as playlists, while `/stories/<user>/<id>` stays one item.
- `engine/urlnorm.py` - Instagram drops `igsh`/`igshid` (keeps `img_index`); TikTok drops `_t`, `_r`, `is_from_webapp`, `sender_device`, `sender_web_id`, `share_app_id`, `share_link_id`, `share_item_id`, `source`, `checksum`, `refer`, `region`, `lang`, `u_code`, `timestamp`, `user_id`, `tt_from` (plus `utm_*`). Host is lower-cased and `www.`/`m.` stripped for both sites. `video_key` returns `instagram:<shortcode>` (`/p/`, `/reel/`, `/tv/`), `instagram:story:<user>:<id>` (id present only) and `tiktok:<id>` (`/@user/video/<id>`). YouTube behaviour unchanged (`_host_kind` keeps `music.` handling).
- `engine/errors.py` - three new rows before the existing ones: `login_required` ("Instagram needs you signed in." / "Choose a browser in Settings > Accounts"), `rate_limited` ("Instagram is limiting requests. Wait a few minutes and try again."), `cookies_unreadable` ("Elisium could not read that browser's cookies. Close the browser or pick another."). Everything else keeps the SPEC mapping.
- `engine/queue.py` - `set_cookies(browser, file)` (applies to probes and downloads that start later); `probe()` and `_attempt()` pass the current choice to the probe; `_download()` puts it on `DownloadOptions`. Only the browser name / file path are held; nothing cookie-related is read, copied or written to history.
- `ui/settings.py` - `COOKIE_BROWSERS`, `valid_cookie_browser`, `valid_cookies_file`; `Settings.cookies_browser` / `cookies_file` (default `None`, invalid values fall back to `None`); `load()` of an old file without the fields still works; `apply()` calls `queue.set_cookies(...)`.
- `ui/settings_page.py` - new "Accounts" card: browser dropdown ("Not signed in", Firefox, Chrome, Chromium, Brave, Microsoft Edge, Vivaldi, Opera), read-only `cookies.txt` field with "Choose..." / "Clear", and the one-line help text from the brief. Accessible name + description on every control, label buddies, tab order inserted after Default quality, `_changed()` saves and applies live. `show_accounts()` scrolls the section into view and focuses the dropdown.
- `ui/main_window.py` - `open_accounts()` (Settings page + `show_accounts()`), a status-bar hint when a failed item carries `sign_in_required` / `login_required`, and a "Sign in..." context-menu entry for those items: the sign-in error action now actually lands on Accounts.

Spec
- `core-spec/SPEC.md` - error table rows for the three new messages and a short "Sign-in (cookies)" section.

Tests (all new cases, no network; one `@pytest.mark.live` for TikTok)
- `tests/test_presets_settings.py` - cookie round trip, old settings file, validation, `apply()` pushes the choice.
- `tests/test_runner.py` - argv for none / browser / file / both; story tray and highlight classified as playlists; story-with-id and TikTok video not; probe gets the cookie flags; `test_live_tiktok_public_video_probe` (skipped unless `ELISIUM_LIVE_TESTS=1`).
- `tests/test_urlnorm.py` - 3 Instagram post URL forms share one key, reel/tv keys, `img_index` kept, story key needs an id, profile has no key, 3 TikTok forms share one key and one normalised URL, `vm.tiktok.com` short link loses junk but has no key, YouTube unchanged.
- `tests/test_errors.py` - the four new plain-language mappings plus code checks.
- `tests/test_queue.py` - cookies reach the probe and the download argv (browser and file), reset clears them, the path never appears in the history row.
- `tests/test_ui_pages.py` - Accounts dropdown saves + persists, file chooser and Clear, saved choice loads into the page, `show_accounts()` focuses the dropdown, a `login_required` failure points at Accounts and `open_accounts()` lands there.

## Commands run

```
cd desktop
env -u QT_QPA_PLATFORMTHEME QT_QPA_PLATFORM=offscreen nice .venv/bin/python -I -m pytest -q
...
549 passed, 2 skipped in 287.16s (0:04:47)
```
The two skips are the live tests (the existing YouTube one and the new TikTok one). Baseline before this brief was 514 passed + 1 skipped; 36 tests were added.

```
python3 ../design/contrast_check.py | tail -3
ok   light glowB    on bg        3.76 (need 3.0)
ok   light glowC    on bg        4.18 (need 3.0)
ALL PASS 0
```

Note on the acceptance command: `python -I -m pytest` only works when the package is importable without the working directory. The venv copy was not installed, so I ran `nice .venv/bin/pip install -e . --no-build-isolation --no-deps` once (local venv only, `*.egg-info/` is gitignored, no repo files added) and then the exact command above passed. The first full run before that install used `-m pytest` without `-I` and also passed (`549 passed, 2 skipped`); the only failures in the first run were the seven existing queue/settings tests whose injected fake probes did not yet accept the new cookie keyword - those fakes were updated.

## Unfinished / notes

- Nothing from the brief is left undone. The Chinese-wall items I did not add: no browser extension, no password storage, no login dialog, no new dependencies, no network in tests.
- `_looks_like_playlist` also still returns False for `/stories/highlights/` with no id (it is a tray only with an id, matching the brief).
- Highlights URLs have no `video_key` (the brief only defines keys for `/stories/<user>/<id>`), so their dedupe falls back to the normalised URL - intentional.
- `engine/urlnorm.py` still contains the pre-existing unused `_VIDEO_ONLY_DROP` constant; left untouched to keep the diff to this brief.
- Not committed or pushed.
