# Brief 9A result - better Instagram errors + dedupe keys (desktop + Android)

Date: 2026-11-15. Status: done, all acceptance checks pass.

## Files changed

Desktop (`desktop/elisium_downloader/`)
- `engine/errors.py` - `explain(raw_log, url=None, hasCookies=False)`; new public `apply_context(info, url=None, hasCookies=False)` holds the site/cookie logic so the probe path can reuse it without re-parsing a log. Rows:
  - `login_required`: Instagram wording when there is no URL or the URL is Instagram, otherwise "The site wants you to be signed in." with the same code and the same fix text.
  - `rate_limited`: same split, "The site is limiting requests. Wait a few minutes and try again." for other sites.
  - `login_required` + cookies + Instagram (or no URL) -> `session_expired`, "Your Instagram sign-in has expired." / "Choose your browser again in Settings > Accounts".
  - New `no_media` row ("This post has no video to download." / "Check the link"), placed after the two site rows and before `cookies_unreadable`; it cannot shadow them.
  - New `http_401` row ("The site refused to let Elisium in." / "Sign in, then try again"), placed immediately before `http_403`; 403 and 429 keep their rows and order. Every other row is untouched.
- `engine/urlnorm.py` - new public `site_kind(url)` (`"instagram"` / `"tiktok"` / `None`, never raises) reusing the existing `_site_kind` host rules; `instagram:highlight:<id>` for `/stories/highlights/<digits>/`; `tiktok:short:<code>` for `vm.tiktok.com` / `vt.tiktok.com` (`_TIKTOK_SHORT_HOSTS`), never resolved over the network. Highlight tray classification (`runner._looks_like_playlist`) untouched.
- `engine/queue.py` - only the error-mapping sites: `_cookies_configured()` helper (browser or cookies file set, reads nothing); the probe failure now goes through `apply_context(exc.info, item.url, ...)` and the download failure through `explain(raw, item.url, ...)`. Advice about `--cookies*` for every site is unchanged.
- `ui/main_window.py` - `SIGN_IN_CODES` now `{sign_in_required, login_required, session_expired, http_401}`.

Android (`android/app/src/main/java/com/desolate/elisium/`)
- `engine/Errors.kt` - port of the above: `explain(rawLog, url = null, hasCookies = false)`, `applyContext(info, url = null, hasCookies = false)`, the generic/Instagram wording pair, `session_expired` (fix "Sign in again in Settings > Accounts"), `no_media`, `http_401`, same order.
- `engine/UrlNorm.kt` - mirror of the Python: `siteKind(url)`, highlight key, `tiktok:short:<code>`; the private host classifier was renamed `siteKindOfHost` so it cannot be confused with the URL helper.
- `engine/DownloadQueue.kt` - only the `explain` call sites: probe failure `explain(f.errorText, e.url, activeCookiesFile() != null)`, download failure `explain(outcome.errorLog, e.url, cookies != null)`.
- `ui/downloads/QueueRows.kt` - `SIGN_IN_CODES` adds `session_expired` and `http_401` (this also feeds `validActions`, so those rows show "Sign in" too).

Tests (no network)
- `desktop/tests/test_errors.py` - 401 row (and 403/429 unchanged), both `no_media` needles with the full real message, `no_media` does not shadow `login_required`, generic vs Instagram wording for `login_required` and `rate_limited`, `session_expired` only with cookies on Instagram/no URL, other sites never get it, default arguments identical to `explain(raw, None, False)`.
- `desktop/tests/test_urlnorm.py` - highlight keys (trailing slash, no slash, `m.` host, `igsh`/`igshid`/`utm_*` variants), numeric-id guard; TikTok short keys (trailing slash, tracking parameters, both short hosts, no code, full URL unaffected).
- `desktop/tests/test_ui_main_window.py` - `SIGN_IN_CODES` set.
- `android/.../engine/ErrorsTest.kt` - the same cases, plus the Android fix texts.
- `android/.../engine/UrlNormTest.kt` - highlight and short-link key families.
- `android/.../ui/QueueUiTest.kt` - `session_expired` and `http_401` get the Sign in action.

## Needles for `no_media`

Read-only from the installed yt-dlp (2026.10.26), `extractor/instagram.py`:
- line 530: `self.raise_no_formats('There is no video in this post', expected=True)` -> needle `there is no video in this post`
- line 522: `raise ExtractorError('Instagram sent an empty media response. Check if this post is accessible in your browser without being logged-in. ...')` -> needle `instagram sent an empty media response`

Nothing invented; both are the exact lower-cased strings yt-dlp prints.

## Conflict in the brief (please read)

Point 5 asks for `instagram:highlight:<id>` and `tiktok:short:<code>` keys, but also "existing tests must pass untouched". Four existing assertions asserted the opposite (`video_key(highlight) is None`, `video_key(vm.tiktok.com/ZMabc123) is None`), so they could not all survive. I implemented the keys (the numbered requirement) and changed only those assertions:
- `desktop/tests/test_urlnorm.py`: the highlight `is None` line moved into the new `test_instagram_highlight_needs_a_numeric_id`, and `test_tiktok_short_link_has_no_key_but_loses_junk` is now `test_tiktok_short_link_keeps_one_key_without_redirects`.
- `android/.../UrlNormTest.kt`: same two lines, same reason.

No other assertion, key or normalised URL changed. If the keys were meant to wait, revert those two pairs and drop the two key families.

Two smaller judgement calls: `hasCookies` keeps the brief's camelCase spelling in Python so both platforms use the same argument name; and the probe path needed `apply_context` rather than a fresh `explain(...)` because `ProbeError` already carries a classified `ErrorInfo` (a missing yt-dlp binary would otherwise degrade to "Download failed.").

## Commands run

```
cd desktop
QT_QPA_PLATFORMTHEME= QT_QPA_PLATFORM=offscreen nice .venv/bin/python -m pytest -q
...
570 passed, 2 skipped in 260.88s (0:04:20)
```
The 2 skips are the live tests (`@pytest.mark.live`). Baseline before this brief was 549 passed + 2 skipped; 21 tests were added. `python3 -m pytest` from the system interpreter has no pytest, so the project venv is used (same as phase 8A).

```
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
```
First run: `382 tests completed, 1 failed` - my own new highlight test asserted a trailing slash on a URL that had none. Fixed the test, re-ran:
```
> Task :app:testDebugUnitTest
BUILD SUCCESSFUL in 49s
```
Test-results XML totals: `tests=382 skipped=0 failures=0 errors=0` (375 baseline + 7 new).

```
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug
...
> Task :app:lintDebug
BUILD SUCCESSFUL in 3m 11s
```
`app/build/reports/lint-results-debug.sarif`: 19 issues, 0 errors, all warnings; none in `Errors.kt`, `UrlNorm.kt`, `DownloadQueue.kt` or `QueueRows.kt`.

No emulator, no adb, no network in tests, no `sudo`, nothing committed or pushed.

## Unfinished / notes

- `core-spec/SPEC.md` is not in the brief's file list, so its error table still shows the old Instagram-only rows; the new `session_expired`, `http_401` and `no_media` rows are not listed there yet. Worth a follow-up brief.
- `design/contrast_check.py` was not re-run: no colours, layout or motion changed in this brief.
