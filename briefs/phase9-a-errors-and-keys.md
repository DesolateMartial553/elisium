# Brief 9A - better Instagram errors + dedupe keys (desktop + Android)

Read `AGENTS.md`, `core-spec/SPEC.md` ("Sign-in (cookies)" and the error table), `briefs/phase8-a-desktop-instagram-tiktok.result.md` and `briefs/phase8-b-android-instagram-tiktok.result.md`. Edit only the files listed below (plus their tests) and write `briefs/phase9-a-errors-and-keys.result.md`. No commit/push, no emulator/adb, no network in tests.

Goal: when Instagram fails, tell the user the real reason and the right fix, and stop hard-coding "Instagram" into messages for other sites. Keep desktop and Android behaviour identical (same codes, same wording except the platform-specific fix text that already differs).

## Files
Desktop: `desktop/elisium_downloader/engine/errors.py`, `engine/urlnorm.py`, `engine/queue.py` (only the places that call `explain`), `ui/main_window.py` (`SIGN_IN_CODES`), tests under `desktop/tests/`.
Android (`android/app/src/main/java/com/desolate/elisium/`): `engine/Errors.kt`, `engine/UrlNorm.kt`, `engine/DownloadQueue.kt` (only the `explain` call sites), `ui/downloads/QueueRows.kt` (`needsSignIn`), tests under `android/app/src/test/`.

## Build
1. **Context-aware `explain`.** Add optional arguments to `explain` on both platforms: the item's URL (`url: str | None = None`) and whether cookies are currently configured (`hasCookies: bool = False`). Existing callers and every existing test keep working with the defaults. Update the queue call sites to pass the item URL and whether a browser or cookies file is set (desktop `_cookies_browser`/`_cookies_file`, Android `activeCookiesFile`).
2. **Instagram wording only for Instagram URLs.** The `login_required` and `rate_limited` rows currently say "Instagram" even for other sites. When a URL is given and it is not an Instagram URL (use the existing host classification in urlnorm), use the generic wording "The site wants you to be signed in." / "The site is limiting requests. Wait a few minutes and try again." with the same codes. With no URL given, keep today's text.
3. **New rows** (first match wins; place them where they cannot shadow the existing rows, and keep the existing order otherwise):
   - `http error 401` -> code `http_401`, "The site refused to let Elisium in.", fix "Sign in, then try again".
   - Empty or media-less Instagram posts -> code `no_media`, "This post has no video to download.", fix "Check the link". Needles must come from real yt-dlp output: grep the installed yt-dlp source (`python3 -c "import yt_dlp,os;print(os.path.dirname(yt_dlp.__file__))"` then read `extractor/instagram.py`, read-only) and use the exact `raise ExtractorError`/`raise_login_required` strings you find, lower-cased. List the strings you used in the result file. Do not invent needles; if the source has none for this case, skip the row and say so.
   - **Expired session:** when the login-required needles match, `hasCookies` is true and the URL is Instagram (or no URL given), return code `session_expired`, "Your Instagram sign-in has expired.", fix "Sign in again" (Android: "Sign in again in Settings > Accounts"; desktop: "Choose your browser again in Settings > Accounts"). Without cookies it stays `login_required`.
4. **Sign-in action.** Add `session_expired` and `http_401` to the codes that show the "Sign in" action (desktop `SIGN_IN_CODES` in `ui/main_window.py`; Android `needsSignIn` in `QueueRows.kt`).
5. **Dedupe keys.** In `urlnorm.py` / `UrlNorm.kt` (mirror exactly):
   - Instagram highlights `/stories/highlights/<digits>/` -> `video_key` `instagram:highlight:<id>`. Do not change how highlights are classified as trays.
   - TikTok short links `vm.tiktok.com/<code>/` and `vt.tiktok.com/<code>/` -> `video_key` `tiktok:short:<code>`. Do not follow redirects (no network).
   - All existing keys and normalisation stay byte-identical; existing tests must pass untouched.

Do NOT change which sites receive `--cookies-from-browser` / `--cookies`: they stay passed for every site, because the YouTube "not a bot" error tells users to import cookies.

## Tests (no network)
Desktop and JVM: each new row (needle -> code/text), the non-Instagram wording for `login_required` and `rate_limited`, `session_expired` vs `login_required` by `hasCookies`, default-argument behaviour unchanged, the sign-in action sets, and the two new key families including a tracking-parameter variant and a trailing-slash variant.

## Acceptance (paste real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
cd ../android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug
```
All existing tests still pass (desktop 514+, Android 375+), zero lint errors; first Gradle run may be OOM-killed, retry. Write the result file even if you run low on budget.
