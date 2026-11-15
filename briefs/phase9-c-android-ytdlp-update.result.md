# Brief 9C result - keep yt-dlp fresh on Android

## Library API found (youtubedl-android 0.18.1, javap on the Gradle-cache classes.jar)
- `YoutubeDL.getInstance().updateYoutubeDL(Context, YoutubeDL.UpdateChannel): YoutubeDL.UpdateStatus` (synchronized, throws `YoutubeDLException`).
- `YoutubeDL.UpdateChannel` is a nested sealed class with objects `STABLE` (GitHub `.../yt-dlp/releases/latest`), `NIGHTLY`, `MASTER`. Used `STABLE`.
- `YoutubeDL.UpdateStatus` is an enum: `DONE`, `ALREADY_UP_TO_DATE`. Version read with `YoutubeDL.version(context)` (same call the app already used).

## Files changed (all under android/ plus this file)
- New: `backend/UpdatePolicy.kt`, `backend/YtDlpUpdater.kt` (interface `YtDlpUpdater { fun update(): UpdateResult }`, sealed `UpdateResult`, `LibraryYtDlpUpdater`, `YtDlpUpdateService`).
- Edited: `ElisiumApp.kt` (startup auto-update after Ready, version refresh after Updated, shared service), `settings/SettingsRepository.kt` + `settings/SettingsRules.kt` (`lastYtDlpCheck`, clamped >= 0), `ui/settings/SettingsViewModel.kt` (`UpdateUi`, `canUpdate`, `updateYtDlp()`), `ui/settings/SettingsScreen.kt` (button + live-region status line in About), `ui/ElisiumViewModel.kt` (wiring, downloads-active flow), `engine/Errors.kt` (http_403 fix now "Update yt-dlp in Settings, or sign in"), `res/values/strings.xml`.
- Tests: new `backend/UpdatePolicyTest.kt`, `backend/YtDlpUpdateServiceTest.kt`, `ui/YtDlpUpdateUiTest.kt`; `ErrorsTest.kt` updated for the new 403 text; `FakeSettingsStore` got `setLastYtDlpCheck`.
- Fixed the previous agent's draft: duplicate interface method, bogus `YoutubeDL$UpdateStatus` import, suspend `update()` (brief says plain `fun`), negative `lastCheckMs` now means "never checked".

## Commands run (real results)
- `gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest` : BUILD SUCCESSFUL. Summed from the XML reports: 422 tests, 0 failures, 0 errors, 0 skipped (400 before + 22 new). (This run used `--offline`; lint/assemble ran exactly as in the brief.)
- `... :app:lintDebug` : BUILD SUCCESSFUL (lint report written; no errors failed the build).
- `... :app:assembleDebug` : BUILD SUCCESSFUL.
No OOM kill happened.

## Judgement calls
- Clock going backwards (now < last check) returns false (literal "24 h elapsed"). A manual update re-records the time and resets it.
- "Downloads active" = any queue item active or queued. "On Wi-Fi" at startup = active network is NOT_METERED, the same test the Wi-Fi-only download gate uses.
- Time is stored after every finished attempt (success or failure). A cancelled attempt records nothing.
- Auto and manual updates share one `YtDlpUpdateService` (one at a time; a second request returns null). Button is also disabled while the engine is not Ready.
- Failure reasons are one line, max 80 chars, logged as one short warning. Desktop `errors.py` still has the old 403 text (out of scope: no desktop edits).
- The settings DataStore round trip is tested through the fake store and `validated()` (DataStore needs Android); the repository's `coerceAtLeast(0)` is not run on a JVM.

## Needs a real phone
- The real `updateYoutubeDL` call (network, GitHub reachability, DONE vs ALREADY_UP_TO_DATE).
- The shown version refreshing after a real update, and downloads still working with the updated yt-dlp.
- Extra download size/time of the yt-dlp update on mobile data; startup auto-update behaviour on a cellular vs Wi-Fi network with Wi-Fi-only on and off.
- TalkBack reading of the button and the status line; button look in light and dark.
- An update started just before the user queues a download (the library call is not coordinated with the queue).
