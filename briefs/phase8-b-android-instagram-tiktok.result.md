# Brief 8B result - Instagram + TikTok videos and stories (Android)

Date: 2026-11-14. Status: done, all three acceptance checks pass. Not committed.

## Files changed

Code (`android/app/src/main/java/com/desolate/elisium/`)
- `engine/UrlNorm.kt` - Instagram drops `igsh`/`igshid` (keeps `img_index`); TikTok drops the same 17 parameters as desktop (`_t`, `_r`, `is_from_webapp`, `sender_device`, `sender_web_id`, `share_app_id`, `share_link_id`, `share_item_id`, `source`, `checksum`, `refer`, `region`, `lang`, `u_code`, `timestamp`, `user_id`, `tt_from`, plus `utm_*`); host lower-cased and `www.`/`m.` stripped. `videoKey` is now site-aware: `instagram:<shortcode>` (`/p/`, `/reel/`, `/tv/`), `instagram:story:<user>:<id>` (id only), `tiktok:<id>` (`/@user/video/<id>`); YouTube keys unchanged.
- `engine/Errors.kt` - three new rows before the existing ones: `login_required` ("Instagram needs you signed in." / fix "Import cookies in Settings > Accounts"), `rate_limited` ("Instagram is limiting requests. Wait a few minutes and try again."), `cookies_unreadable` ("Elisium could not read that cookies file. Export it again from the browser." / fix points at Settings > Accounts). Extra match needles: "netscape format cookies file", "cookies are no longer valid".
- `backend/YtDlpCommands.kt` - `buildDownloadArgs` adds `--cookies <path>` when the request has a file; `buildProbeArgs(url, cookiesFile)` does the same for probes; `isInstagramStoryTray` feeds `looksLikePlaylist` (a `/stories/<user>/` tray or `/stories/highlights/<id>` is multi-item, `/stories/<user>/<id>` is one story).
- `engine/Ports.kt` / `backend/YoutubeDlBackend.kt` - `DownloadRequest.cookiesFile: File? = null`; `DownloadBackend.probe(url, cookiesFile: File? = null)` (interface default keeps existing fakes/call sites compiling).
- `engine/DownloadQueue.kt` - `setCookiesFile(file)` stores the path; `activeCookiesFile()` returns it only while the file exists, and it is passed to every probe and download that starts afterwards. The path is held, never the contents.
- `settings/CookiesFile.kt` (new) - pure `checkCookiesFile(text)`: `Valid(count)` (Netscape header or tab-separated 7-field rows with a domain, TRUE/FALSE flag and name), `Empty` (blank or header-only), `WrongFormat` (anything else; a file starting with `<` is treated as an HTML page). BOM stripped, CRLF tolerated.
- `settings/CookieJar.kt` (new) - `CookiesStore` interface (+ `NoCookiesStore` default for previews), `CookieJar` storing `filesDir/cookies/cookies.txt`, reporting `CookiesStatus.None`/`Imported(n)` from the file itself, and `remove()` deleting file and folder. Contents are never logged.
- `ui/settings/SettingsViewModel.kt` - takes `cookies: CookiesStore = NoCookiesStore`; `importCookies(text)` / `removeCookies()`; exposes `cookies` and `cookiesRejected` (the reason an import was refused). Strings are set from resources, so no cookie text is ever held.
- `ui/settings/SettingsScreen.kt` - "Accounts" card: current status ("No cookies imported" / "Imported (N cookies)" plural), "Import cookies.txt" through `ActivityResultContracts.OpenDocument` (no storage permission) with a 4 MB read cap, "Remove" only when something is imported, refusal line for empty/wrong files, and the short how-to text ("a cookies.txt extension in a desktop browser, then copy the file to the phone"). TalkBack labels and descriptions on every control, focus rings kept; `focusAccounts` scrolls Accounts into view (instant when reduced motion), then calls `onAccountsShown`.
- `ui/downloads/QueueRows.kt` / `DownloadsScreen.kt` - `RowAction.SignIn` + `needsSignIn` column: a `failed` item whose error code is `sign_in_required`/`login_required` gets a "Sign in" button (with "Opens Settings > Accounts" description) next to "Retry".
- `ui/ElisiumShell.kt` / `ElisiumViewModel.kt` - Sign in switches to the Settings tab with `focusAccounts = true`, cleared once the section is shown.
- `ElisiumApp.kt` - one `CookieJar`, passed to the queue (`setCookiesFile`) and to the Settings view model, so an import applies to probes and downloads without a restart.

Resources
- `res/values/strings.xml` - Accounts section strings, plural `settings_accounts_imported`, `action_sign_in`/`action_sign_in_for`, refusal messages, how-to text.

Backups (unchanged, confirmed)
- `AndroidManifest.xml` already has `android:allowBackup="false"`, `dataExtractionRules` and `fullBackupContent`; `res/xml/backup_rules.xml` and `res/xml/data_extraction_rules.xml` exclude root/file/database/sharedpref/external for both cloud backup and device transfer, so `filesDir/cookies/` never leaves the phone.

Tests (JVM, no network)
- `settings/CookiesFileTest.kt` (new, 14) - valid file with header, headerless tab rows, empty/blank/header-only, HTML, JSON, wrong field count, BOM, CRLF.
- `ui/AccountsSettingsTest.kt` (new, 7) - `FakeCookiesStore`: import shows the count, refusal keeps the old status, remove clears, status survives a fresh view model.
- `engine/UrlNormTest.kt` (+Instagram/TikTok cases) - 3 post URL forms share one key, reel/tv keys, `img_index` kept, story key needs an id, profile has no key, TikTok forms share one key, `vm.tiktok.com` short link normalised, YouTube unchanged.
- `engine/ErrorsTest.kt` - the three new mappings plus code/needle checks.
- `backend/YtDlpCommandsTest.kt` - `--cookies` in download and probe argv; story tray and highlight are playlists, a story with an id is one item.
- `engine/DownloadQueueTest.kt` - cookies reach the probe and the download (fake backend records `probeCookies`); a deleted file is not passed.
- `service/ShareIntakeTest.kt` - "Look at this! https://www.instagram.com/reel/ABC/?igsh=xyz enjoy" extracts the URL; same for TikTok share text; "https://" alone is not a link.
- `ui/QueueUiTest.kt` - Sign in appears only for `failed` + sign-in error code.

## Commands run

```
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
```

```
> Task :app:testDebugUnitTest
BUILD SUCCESSFUL in 1m 3s
```

Test-results XML totals: `tests=375 failures=0 errors=0 skipped=0` (327 baseline + 48 new).

```
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug
```

```
> Task :app:lintDebug

BUILD SUCCESSFUL in 1m 45s
```

`app/build/reports/lint-results-debug.sarif`: 19 issues, **0 errors**, all 19 warnings pre-existing (dependency updates, `UseKtx`, `OldTargetApi`, `PluralsCandidate` on the percent string, etc.); none point at a file added by this brief.

```
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:assembleDebug
```

```
> Task :app:assembleDebug

BUILD SUCCESSFUL in 49s
37 actionable tasks: 3 executed, 34 up-to-date
```

## Needs a real phone

- Document picker import: tap "Import cookies.txt" in Settings > Accounts, pick a real export, and check the "Imported (N cookies)" count matches the file.
- youtubedl-android accepting `--cookies <path>`: only verified as argv here; a real Instagram download must succeed with an imported file.
- Instagram story tray: download a profile's stories and a highlight, and confirm one row per tray with the right number of items.
- Sign-in jump: a failed Instagram item must show "Sign in", and tapping it must land on Settings > Accounts with the section scrolled into view (also with reduced motion on).
- Backup exclusion: `adb shell dumpsys backup` (or a fresh install restore) should show the app's files not backed up - cannot be checked without a device.
- TalkBack labels on the new buttons/status lines; large font and dark/light Afterglow rendering of the new card.

## Unfinished / notes

- Nothing from the brief is left undone.
- Android has no browser cookie access, so only `cookies.txt` is supported (no `--cookies-from-browser`); the help text explains exporting on a desktop browser first.
- `CookieJar` is compile-verified and used by `ElisiumApp`; its storage logic is not JVM-tested (Android `Context`), matching the existing pattern for other Android-only adapters. The validation rules are tested as a pure function.
- Nothing was committed or pushed; `desktop/`, `core-spec/` and the 8A result file are still the earlier 8A working-tree changes and were not touched.
