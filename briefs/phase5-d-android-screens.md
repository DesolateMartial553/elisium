# Brief 5D - Android screens (Compose)

5A-5C built the engine, the ports and the foreground service. This brief adds the real UI on top, using what exists. Read first: `AGENTS.md`, `core-spec/SPEC.md`, `briefs/phase5-c-android-backend.result.md`, `HANDOFF.md`, `android/.../MainActivity.kt`, `ElisiumApp.kt`, `engine/DownloadQueue.kt` (public API: `items`, `events`, `add`, `pause`, `resume`, `retry`, `cancel`, `QueueItem`), `engine/Presets.kt`, `service/DownloadCoordinator.kt` (`holdReason`, `pauseAll`, `cancelAll`, `serviceError`), `settings/SettingsRepository.kt`, `data/HistoryDao.kt` + `RoomHistoryStore`, `ui/theme/Theme.kt`. For behaviour and wording reference the desktop UI: `desktop/elisium_downloader/ui/main_window.py`, `history_page.py`, `settings_page.py`, `model.py`.

## Constraints
- Compose + Material 3 only (already in the build). No new heavy dependencies; `androidx.navigation:navigation-compose` is allowed only if you genuinely need it, otherwise a simple state-based screen switch with a bottom `NavigationBar` is fine. Keep Gradle runs low-memory (`nice gradle --no-daemon --max-workers=1`; a first build may be OOM-killed, retry).
- No emulator, no adb. UI is verified by compiling, lint, JVM tests of every piece of logic (view-models, formatters, mapping), and `@Preview`s that compile. Do NOT claim it looks or behaves right on a device; say plainly what is compile-only.
- **Accessibility from the start (TalkBack is a hard requirement):** every icon button has a `contentDescription`; each queue row is one merged semantics node reading "title, state, percent, speed, time left"; progress uses `progressBarRangeInfo`; state changes are announced via `liveRegion` (throttle: percent announced at 25% steps, never per tick); all touch targets >= 48dp; nothing conveyed by colour alone; support font scale 2.0 without clipping (use `heightIn`, wrap text, no fixed heights); dark and light theme both readable.
- Plain-language, non-generic copy (see `engine/Errors.kt` messages and the desktop wording). No emoji.
- Do not change `engine/` logic except for a genuine bug (say so). Do not touch `desktop/`. Do not commit or push.

## Build these (package `com.desolate.elisium.ui`)
1. **Shell**: `MainActivity` hosts a `Scaffold` with bottom navigation: **Downloads**, **History**, **Settings**. Engine state: while `Starting` show a calm "Starting the download engine..." line; on `Failed` show the message with a plain explanation (no retry button needed). Keep the share-intent handling already in `MainActivity` (the confirmation line now shows as a Snackbar with a live region).
2. **Downloads screen** (`ui/downloads/`): an "Add link" row at the top (text field + Add button; accepts pasted text with several links via `extractUrls`; paste-from-clipboard button; shows the same `shareConfirmation` wording as a Snackbar). Below, the `QueueViewModel`-driven list of `QueueItem`s: title (fall back to URL), a state label in plain words, a linear progress bar when downloading (indeterminate when no percent), "12.4 MB of 80 MB - 2.1 MB/s - 40 s left" (pure formatter functions with JVM tests, ported from the desktop `model.py` semantics), the error message and a Retry button when failed, per-row actions pause/resume/cancel/retry shown only when valid for the state (use `ACTIVE_STATES`/state names from the engine), a top-bar "Pause all / Cancel all" overflow wired to `DownloadCoordinator`, and a banner when `holdReason` is set (waiting for Wi-Fi) or `serviceError` is set. Empty state: one helpful sentence about sharing a link from any app. Cancel asks no confirmation for queued items, asks one for an active item.
3. **History screen** (`ui/history/`): search field (debounced) over `HistoryStore.search`/`recent`; rows show title, site/URL, state, date; actions: **Open** (ACTION_VIEW on the `content://` URI or file path; if `existsAt` is false show "File no longer exists" and disable), **Share** link, **Download again** (adds to queue), **Delete from history** (does not delete the file; say so in the label). Run DB calls off the main thread.
4. **Settings screen** (`ui/settings/`): preset picker (labels from `Presets`), concurrency stepper 1-5, speed limit text field with validation message via the existing `validSpeedLimit` rules, Wi-Fi-only switch, notify-when-done switch, and an About block: app version, bundled yt-dlp version (from `EngineState.Ready`), the output folder "Download/Elisium" in words. Switches are real `Switch` with the label as the clickable row (`toggleable`, `Role.Switch`).
5. **Permissions** (`ui/permissions/`): ask for `POST_NOTIFICATIONS` (API 33+) the first time the user adds a link, with a one-line reason shown first; ask for `WRITE_EXTERNAL_STORAGE` only on API 26-28 before the first download. If denied: downloads still work, show a gentle line in Settings saying notifications are off and a button opening the app's notification settings. Never block adding links on a permission. Put the decision logic (should-ask, rationale text) in pure functions with tests.
6. **Strings**: all user-visible text in `res/values/strings.xml`, none hard-coded in composables (plurals where needed).

## Tests (JVM)
Formatters (bytes, speed, eta, state labels), row-to-UI-model mapping per state, which actions are valid per state, permission decision logic, history-row mapping, settings validation messages, view-model behaviour with a fake queue/history (use the existing test fakes where possible). Existing 220 tests must still pass.

## Acceptance (paste real output)
```
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:assembleDebug
```
Lint must have **zero errors** (run it yourself; last time errors only appeared at audit). Report test counts, lint warnings briefly, APK size. Write `briefs/phase5-d-android-screens.result.md` with a section "Compile-verified only (needs the owner's phone)" and a short list of screens + TalkBack behaviour you designed but could not hear.

## Finish properly
Run all three Gradle commands to the end and fix what they report BEFORE writing the result file. Write the result file even if you are running low on budget (state what is unfinished). Do not stop silently.
