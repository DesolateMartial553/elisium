# Brief 8A - Instagram + TikTok videos and stories (desktop)

Read `AGENTS.md`, `core-spec/SPEC.md`, then `desktop/elisium_downloader/engine/{runner,urlnorm,errors,queue}.py` and `ui/{settings,settings_page,bridge}.py`. Edit only under `desktop/` (code + tests) and write `briefs/phase8-a-desktop-instagram-tiktok.result.md`. Do not touch `android/` or `design/`, do not commit or push.

## Verified facts (Claude ran yt-dlp 2026.10.26 on this machine)
- TikTok public video: extracts fine with no login (a harmless "impersonation" warning is printed).
- Instagram stories (`instagram.com/stories/<user>/`): fails with "You need to log in to access this content. Use --cookies-from-browser or --cookies". Posts/reels often need login too. So the one missing feature is **cookies**. The app has none today (only the "Import cookies" hint text in `errors.py`).
- Browsers on the machine: Firefox, Google Chrome.

## Build
1. **Cookie settings** (`ui/settings.py`, validated, persisted, backwards compatible with old settings files): `cookies_browser: str | None` (one of `firefox, chrome, chromium, brave, edge, vivaldi, opera`, else None) and `cookies_file: str | None` (path). Browser wins if both set. Default both None (off).
2. **Runner/probe** (`engine/runner.py`): `DownloadOptions` gets `cookies_browser` / `cookies_file`; `build_command` adds `--cookies-from-browser <name>` or `--cookies <file>`; `probe()` takes the same so stories can be probed. The queue passes the current settings through (`apply(settings, queue)`). Never log cookie file contents; do not copy the file; do not store anything in history.
3. **Stories and highlights as multi-item**: `_looks_like_playlist` (and the playlist picker path) must treat `instagram.com/stories/<user>/` (no numeric id) and `instagram.com/stories/highlights/<id>/` as playlists so the whole story tray is listed and each item is queued. A story URL WITH a numeric id stays a single item.
4. **urlnorm** (`engine/urlnorm.py`): for `instagram.com` drop `igsh`, `igshid`, `img_index`-free tracking only (keep `img_index`); for `tiktok.com` / `vm.tiktok.com` / `vt.tiktok.com` drop `_t`, `_r`, `is_from_webapp`, `sender_device`, `sender_web_id`, `share_app_id`, `share_link_id`, `share_item_id`, `source`, `checksum`, `refer`, `region`, `lang`, `u_code`, `timestamp`, `user_id`, `tt_from`, `utm_*`. Lowercase host, strip `www.`/`m.` for those two sites. `video_key` returns `instagram:<shortcode>` for `/p/`, `/reel/`, `/tv/` URLs and `tiktok:<id>` for `/@user/video/<id>`; stories get `instagram:story:<user>:<id>` when an id is present. Existing YouTube behaviour unchanged.
5. **Errors** (`engine/errors.py`): for Instagram/TikTok add plain-English messages: login required -> "Instagram needs you signed in. Choose a browser in Settings > Accounts." (action opens Settings); rate-limit / "Please wait a few minutes" -> "Instagram is limiting requests. Wait a few minutes and try again."; cookies unreadable (`could not find ... cookies database`, `Failed to decrypt`) -> "Elisium could not read that browser's cookies. Close the browser or pick another." Keep the existing SPEC mapping for everything else; update `core-spec/SPEC.md` error table accordingly (you may edit that one file).
6. **Settings page** (`ui/settings_page.py`): new "Accounts" section: a browser dropdown ("Not signed in", Firefox, Chrome, ...), an optional "cookies.txt file" chooser, and one line of help text: "Needed for Instagram stories and private posts. Elisium only reads cookies for the site you download from." Keep Afterglow tokens, accessible names, keyboard order, reduced motion. The "sign-in" error action jumps to this section.

## Do NOT
Add a browser extension, store passwords, ask for a login, or add dependencies. No network in tests.

## Tests (write with the code; no network)
Settings round trip + old file loads; `build_command` argv for browser / file / none / both; story and highlight URLs classified as playlist, story-with-id and TikTok video not; urlnorm cases for share-link junk on both sites (same video via 3 URL forms -> one key); error mapping cases; settings page widget test (dropdown saves, accessible names present). Add one `@pytest.mark.live` test (skipped by default) for the public TikTok URL `https://www.tiktok.com/@tiktok/video/7106594312292453675`.

## Acceptance (paste real output)
```
cd desktop
env -u QT_QPA_PLATFORMTHEME QT_QPA_PLATFORM=offscreen nice python -I -m pytest -q
python3 ../design/contrast_check.py
```
Existing 514 tests must still pass. Result file: files changed, command output, anything unfinished. Write it even if low on budget.
