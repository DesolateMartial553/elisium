# Brief 9C - keep yt-dlp fresh on Android

Read `AGENTS.md`, `core-spec/SPEC.md`, `briefs/phase9-b-android-webview-login.result.md`, then under `android/app/src/main/java/com/desolate/elisium/`: `ElisiumApp.kt` (engine init, `EngineState`), `backend/YtDlpRunner.kt`, `settings/` (`SettingsRepository`, the Wi-Fi-only setting), `ui/settings/SettingsScreen.kt` + `SettingsViewModel.kt`, `service/` (how the queue reports active downloads). Edit only under `android/` and write `briefs/phase9-c-android-ytdlp-update.result.md`. No desktop edits, no commit/push, no emulator/adb, no network in tests, no new dependencies.

## Goal
youtubedl-android 0.18.1 ships a fixed yt-dlp and the app never updates it, but Instagram/TikTok extractors break every few weeks. Add a safe, throttled self-update plus a manual button.

## Build
1. **Seam** in `backend/YtDlpUpdater.kt`: `interface YtDlpUpdater { fun update(): UpdateResult }` with a sealed `UpdateResult` (`Updated(version)`, `AlreadyUpToDate(version)`, `Failed(reason)`). `LibraryYtDlpUpdater` calls the library's `YoutubeDL.getInstance().updateYoutubeDL(context, <stable channel>)`; confirm the exact method, channel enum and status type by inspecting the youtubedl-android 0.18.1 jar/sources in the Gradle cache (read-only) and say what you found in the result file. It must catch every `Throwable` except cancellation and map it to `Failed` (no network, library error), never crash the app, never log more than a short reason.
2. **Policy** (pure, JVM-tested) in `backend/UpdatePolicy.kt`: `shouldAutoUpdate(nowMs, lastCheckMs, wifiOnly, onWifi, downloadsActive)`: true only when at least 24 h have passed since the last check, no download is active, and (`!wifiOnly || onWifi`). `lastCheckMs` is stored through the existing settings store (a new long, default 0, never negative). Record the time after every attempt, success or failure, so a failing update is not retried on every launch.
3. **Startup**: in `ElisiumApp` after the engine is `Ready`, run the auto-update once on the app scope off the main thread when the policy allows. After `Updated`, refresh the version shown in `EngineState.Ready`/Settings. A failure is silent (a short log line only).
4. **Settings UI**: in the About/engine area of Settings, show the yt-dlp version and an "Update yt-dlp" button (always allowed, disabled while an update runs or a download is active; with a short status line: "Updated to X", "Already up to date (X)", "Update failed: <reason>, try again later"). TalkBack labels and Afterglow styling as elsewhere; strings in `strings.xml`.
5. Update the `http_403` Android fix text only if it does not already point at the new button: "Update yt-dlp in Settings, or sign in".

## Tests (JVM, no network)
`UpdatePolicyTest` (24 h boundary exactly, never-checked 0, wifi-only on/off cell, downloads active, clock going backwards), a fake `YtDlpUpdater` driving the ViewModel states (idle, running, updated, up to date, failed, button disabled while active), the settings round trip of the new timestamp. Keep all existing tests passing.

## Acceptance (paste real output)
```
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:assembleDebug
```
Zero lint errors; first build may be OOM-killed, retry. List "Needs a real phone" items (the real update call, version refresh, the extra download size). Write the result file even if low on budget.
