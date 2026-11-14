# Brief 5D result - Android screens (Compose)

## Commands run (all to completion, `JAVA_HOME=/usr/lib/jvm/java-21-openjdk`, `nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g`)
- `:app:testDebugUnitTest` -> BUILD SUCCESSFUL. 273 tests, 0 failures, 0 skipped (220 existing + 53 new).
- `:app:lintDebug` -> BUILD SUCCESSFUL, **0 errors, 18 warnings** (dependency/version nags: GradleDependency x4, NewerVersionAvailable x3, UseKtx x3, OldTargetApi, ObsoleteSdkInt, ObsoleteLintCustomCheck, ChromeOsAbiSupport, InlinedApi (POST_NOTIFICATIONS constant, guarded by SDK_INT), PluralsCandidate, TypographyEllipsis (the "Starting the download engine..." copy), UsableSpace).
- `:app:assembleDebug` -> BUILD SUCCESSFUL. APK `android/app/build/outputs/apk/debug/app-debug.apk` = 73.9 MB (73,882,316 bytes; dominated by bundled yt-dlp/ffmpeg/aria2c).
- No emulator, no adb, no commit/push, `desktop/` untouched.

## Files (all under `android/` except this file)
New, package `com.desolate.elisium.ui`:
- `Formatters.kt` (bytes/speed/eta/progress line/site/date, ported from desktop `model.py`), `StateLabels.kt`, `ElisiumViewModel.kt` (holds the three screen models + `AppQueueGateway`), `ElisiumShell.kt` (Scaffold, bottom NavigationBar, top-bar Pause all / Cancel all menu, engine status line, Snackbar host).
- `downloads/`: `QueueRows.kt` (row mapping, valid actions, banner rule, spoken sentence, 25%-step announcer), `QueueViewModel.kt`, `DownloadsScreen.kt`.
- `history/`: `HistoryRows.kt`, `HistoryViewModel.kt` (debounced search, IO dispatcher), `HistoryScreen.kt`, `FileActions.kt` (open / share intents).
- `settings/`: `SettingsViewModel.kt`, `SettingsScreen.kt`.
- `permissions/`: `PermissionRules.kt` (pure), `PermissionHost.kt`.
Edited: `MainActivity.kt` (now hosts the shell; share intent still handled, confirmation is a Snackbar), `ElisiumApp.kt` (exposes `history`, `outputStore`, `settingsRepository`, queue uses the same instances), `settings/SettingsRepository.kt` (new `SettingsStore` interface, so the view-model is testable), `res/values/strings.xml` (all UI text), `AndroidManifest.xml` (FileProvider for opening files at plain paths on API 26-28), `res/xml/file_paths.xml`, `app/build.gradle.kts` + `gradle/libs.versions.toml` (two BOM-managed deps: `material-icons-core`, `ui-tooling-preview`; no navigation library, tab switch is saved state).
Tests: `ui/FormattersTest`, `ui/QueueUiTest`, `ui/QueueViewModelTest`, `ui/HistoryAndSettingsTest`, `ui/PermissionRulesTest`.

## What the JVM tests cover
Formatters (bytes, speed, eta, spoken eta/speed, progress line, site, date), state label coverage, row mapping per state, valid actions per state, cancel-confirmation rule, banner rule, announcer (state changes, 25% steps only, no repeat after a dip), spoken-row ordering, queue view-model (rows, banner, multi-link paste, no-link text, confirm/dismiss cancel, cancel all, announcement) against a fake gateway, history row mapping (file Available/Missing/None), history view-model (recent, debounced search, delete keeps file, download again, reload) against the existing `FakeHistory`/`FakeStore`, settings view-model (stepper bounds, speed-limit validation, persisted switches/preset), permission decision logic.

## Notes and decisions
- Room refuses main-thread access and queue actions write history, so `AppQueueGateway` runs adds and pause/resume/retry/cancel on the app IO scope; History runs on `Dispatchers.IO`. No change to `engine/` logic.
- "Cancel all" also asks for confirmation (the brief only specified per-item); one extra dialog.
- Permission prompts come after the links are queued (adding is never blocked). Consequence on API 26-28: if the user says no to storage, the first publish can fail and the row shows the engine error; this path is untested.
- Formatter words (units, "per second", "left") live in `Formatters.kt` rather than strings.xml because the brief wants pure JVM-tested formatters; all other UI text is in strings.xml. A pluralised string was not needed.
- `HistoryViewModelTest` runs on `UnconfinedTestDispatcher`; the same tests with `StandardTestDispatcher` saw an empty list for reasons I did not chase (test-scheduler ordering with `backgroundScope`/`flowOn`). The production code is not changed by that.
- `@Preview`s exist for a queue row (normal and font scale 2.0), a history row and the settings screen; they compile, they were not rendered.

## Compile-verified only (needs the owner's phone)
Nothing below has run on a device or emulator.
- Layout and look: spacing, dark/light readability (dynamic colour on Android 12+), font scale 2.0 without clipping (built with `heightIn`, wrapping text and `FlowRow`, never fixed heights, but not seen), bottom bar, top-bar menu.
- Add link: paste-from-clipboard (`LocalClipboard`), keyboard Done action, share intent to Snackbar.
- Real queue behaviour through the UI: progress ticks, pause/resume/cancel/retry, Wi-Fi banner, service-error banner, Cancel-all and the confirm dialogs.
- History: Open (content URI and FileProvider path), Share link chooser, "File no longer exists" state, Download again.
- Settings: DataStore persistence, notification-off notice and the button to the app's notification settings (re-checked on resume), About block.
- Permission dialogs and the system prompts (POST_NOTIFICATIONS on 33+, WRITE_EXTERNAL_STORAGE on 26-28).

## TalkBack behaviour designed but not heard
- Each queue row's text block is one node: "title, state, percent, speed, time left" (plus the error and fix for failed rows), with `progressBarRangeInfo` when the percent is known. Pause/Resume/Cancel/Retry buttons stay separate focus stops, each described with the title ("Pause <title>"). I rely on Compose keeping them separate from the row text because the text block is its own merged node; unverified.
- Progress is not a live region per tick. A polite live-region line under the add box announces state changes ("<title>: Done.", failures with the engine message) and percent only at 25, 50, 75. The Snackbar carries the add confirmation and open/share problems. Banners and the engine status line are polite live regions.
- History row text is one node ("title, site, state, date, File no longer exists"); each button carries the title in its description; Open is disabled, not hidden, when the file is missing. Settings switches are whole-row `toggleable` with `Role.Switch`, presets are `Role.RadioButton` rows, the concurrency stepper has "Fewer/More downloads at the same time" descriptions and a live-region value.
- All touch targets use `heightIn(min = 48.dp)` or Material defaults; state is always a word, never colour alone. Possible double reading of the percent when TalkBack combines the description with the range info is untested.

## Unfinished
Nothing known. Not done by design: no navigation library, no tests of Composables themselves.
