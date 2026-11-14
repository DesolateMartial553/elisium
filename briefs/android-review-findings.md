# Elisium Android: read-only code review (2026-11-14)

Scope: `android/app/src/main` (Kotlin, Compose, Room, DataStore, youtubedl-android 0.18.1, foreground service). Read-only: nothing edited, gradle not run. Every finding below was verified by reading the cited lines. Items I could not verify without the library or a device are in "Needs a device check" at the end, not in the ranked list. All paths are relative to `android/app/src/main/java/com/desolate/elisium/` unless noted.

## Ranked findings

### 1. CRASH: History "Download again" runs Room on the main thread
- `ui/ElisiumViewModel.kt:52` (`requeue = { url -> app.addLinks(listOf(url)) }`) and `ui/history/HistoryViewModel.kt:127-129` (`scope.launch { messageChannel.trySend(requeue(url)) }`).
- `scope` is `viewModelScope` (Main). `app.addLinks` has no `withContext`, so `queue.add()` (ElisiumApp.kt:104) runs on Main: `history.add()` is a Room insert, and `filePresent()` can do a MediaStore query. `AppDatabase` does not call `allowMainThreadQueries()`, so Room throws `IllegalStateException: Cannot access database on the main thread`. `AppQueueGateway.addLinks` (ElisiumViewModel.kt:32) does wrap in `Dispatchers.IO` and its comment explains why; the History path missed it.
- Scenario: History tab, tap "Download again" on any row, app crashes.
- Fix: `requeue = { url -> withContext(Dispatchers.IO) { app.addLinks(listOf(url)) } }`. Safer: make `ElisiumApp.addLinks` do `withContext(Dispatchers.IO)` internally so no caller can forget.

### 2. CRASH: notification "Pause all" / "Cancel all" and the Android 15 timeout call Room on the main thread
- `service/DownloadService.kt:50-51` (`coordinator?.pauseAll()` / `cancelAll()`) and `:89` (`onTimeout` -> `pauseAll()`).
- `onStartCommand` and `onTimeout` run on the main thread. `pauseAll` calls `queue.pause`, which calls `setState`, which calls `history.updateState` (Room read + update) under the queue lock. Same Room main-thread `IllegalStateException`. In `onTimeout` the crash happens before `stopNow()` is reached, so on Android 15 a dataSync timeout crashes the app, and if it did not crash the service would miss the few seconds Android gives it to stop (ANR / forced crash).
- Scenario: start a download, pull down the shade, tap "Pause all" or "Cancel all": crash. On Android 15, after the dataSync time limit: crash.
- Fix: in both places hand the work to the app scope and stop immediately. `onTimeout`: call `stopNow()` first, then `app.scope.launch { coordinator?.pauseAll() }`. `onStartCommand`: `app.scope.launch { when (action) { ... } }`. (`pauseAll` only needs to run after `startForeground`, which it already does.)

### 3. CRASH: engine init catches only `Exception`; native load failures kill the process
- `ElisiumApp.kt:55-65`.
- `YoutubeDL.init` / `FFmpeg.init` / `Aria2c.init` load native libraries and unpack python. Failures such as `UnsatisfiedLinkError`, `NoClassDefFoundError`, `ExceptionInInitializerError` are `Error`s, not `Exception`s. They are not caught, escape the `scope.launch` on `Dispatchers.IO` (no `CoroutineExceptionHandler`) and take the app down on launch with no "engine failed" banner. `app/build.gradle.kts` sets `abiFilters += "arm64-v8a"` only, so a 32-bit ARM or x86 device installs fine (or is sideloaded) and hits exactly this.
- Fix: `catch (e: CancellationException) { throw e } catch (e: Throwable) { EngineState.Failed(...) }`. Also set `_engine.value = Failed` if `createCoordinator()` throws (it already does, via the same try). Consider adding `armeabi-v7a`/`x86_64` only if the library ships them; otherwise document arm64-only.

### 4. WRONG BEHAVIOUR (fails a healthy download): quick pause -> resume marks the item failed
- `engine/DownloadQueue.kt:592-632` (post-await handling) with `pause` (:281), `resume` (:303), `stop()` (:354).
- `pause()` sets `paused` and calls `handle.cancel()`; the old worker still owns the slot and is blocked in `await()`. If `resume()` flips the state to `queued` before the old worker wakes, the worker returns `DownloadOutcome(terminated = true, exitCode = -1)`. The guard at :594 only checks `paused`/`cancelled`, so it falls through to `return explain(outcome.rawLog)` (UNKNOWN). `afterFailure` (:537) sees state `queued`, not retryable, and sets `failed`. Nothing re-runs it. Late progress lines from the dying process also hit `onProgress` (:637), which only ignores `paused`/terminal, and can push a `queued` item to `downloading`.
- Scenarios: Pause then Resume within a second; Wi-Fi-only gate flapping (`NetworkGate.setAllowed(false)` then `(true)` calls `queue.stop()` then `queue.resume()`), which is common on a real phone when moving between Wi-Fi and mobile.
- Fix: after `await()` returns, `if (outcome.terminated) return null` (only `handle.cancel()` sets `terminated`, and only the queue calls it). The worker then exits, `work()`'s `finally` releases the slot, `schedule()` picks the now-`queued` item and starts a fresh attempt. In `onProgress` also ignore events when `e.state == "queued"`.

### 5. WRONG BEHAVIOUR / DATA: single-video links with `list=` download the whole playlist
- `backend/YtDlpCommands.kt:31-53` (download args) vs `:59-60` (probe adds `--no-playlist`); `engine/DownloadQueue.kt:219` stores the original URL (`clean`), not the normalised one.
- The probe uses `--no-playlist` for a watch URL, but the download command never does. yt-dlp's default for `watch?v=ID&list=...` is to download the playlist. Sharing a video from a playlist or a YouTube Mix (`youtu.be/ID?list=RD...&si=...`) therefore queues the entire list. Only the last line of the `--print-to-file` output is used (`parsePathFile`, YtDlpCommands.kt:101), so only one file is published; the others sit in staging forever and all IDs go into the archive.
- Fix: in `buildDownloadArgs`, add `--no-playlist` when `!looksLikePlaylist(request.url)`; keep today's behaviour for real playlist URLs (and consider refusing them on Android until the queue tracks several files per item). The desktop `runner.py:build_command` has the same gap and should get the same fix.

### 6. DATA LOSS: queue is memory-only and the service is not sticky, so a process kill loses downloads and leaves History rows stuck
- `service/DownloadService.kt:57` (`START_NOT_STICKY`), `ElisiumApp.kt:76-88` (fresh empty queue on every start), `data/HistoryRules.kt:7` (rows keep `queued`/`downloading` forever).
- OEM task killers, low-memory kills, or reboot mid-download: after relaunch the Downloads tab is empty, History shows rows in `downloading`/`queued` that will never finish and have no actions, `.part` files stay in staging with nothing to resume them.
- Fix: on `createCoordinator()`, load History rows in non-terminal states and re-add them as `paused` (or `queued` if the user wants auto-resume) with their `recordId`; at minimum, mark such rows `failed` ("Interrupted, retry") once at startup so they are not stuck. The queue's `add()` creates a new history row, so re-hydration needs an `addExisting(recordId, url, state)` path.

### 7. WRONG BEHAVIOUR: staged and partial files are never cleaned up
- `engine/DownloadQueue.kt:332-344` (`cancel`), `:619` (`publish == null` keeps staged file), `backend/YoutubeDlBackend.kt:86-88`.
- Cancel keeps `<staging>/tmp/*.part` (right for pause, wrong for cancel). A failed publish keeps the finished file (fine for retry, but nothing ever expires it). Playlist leftovers (finding 5) and `.path` files from a killed process also stay. Staging lives in `filesDir`, so it counts against app storage and is invisible to the user.
- Fix: on `cancel()`, delete files in `stagingDir` that belong to the item (yt-dlp names them `<title> [<id>].*` or `*.part`; simplest is to scope each item to `staging/<processId>/` via `-P home:` and `-P temp:` and delete that directory on cancel/done/failed-terminal). Add a startup sweep of orphans older than N days.

### 8. WRONG BEHAVIOUR: free-space check uses a constant 200 MB, so a big download fails only after it finishes
- `backend/YoutubeDlBackend.kt:78-79` (`StorageSpace.requiredFreeBytes(null)`), `storage/StorageSpace.kt:16`, `storage/MediaStoreOutputStore.kt:83` (copy).
- The probe result already has `filesize`/`filesize_approx` but it is never passed down, so the "needs 2x + 50 MB" rule in `StorageSpace` never applies. Staging and Download/ share the same /data volume, so a 3 GB video on a phone with 2 GB free downloads for ages, then `copyTo` hits ENOSPC, `publishModern` returns null and the user sees "Could not save the file" with the 3 GB staged file still on disk.
- Fix: pass the probe's best size estimate into `DownloadRequest` (new field `expectedBytes`) and use `requiredFreeBytes(expectedBytes)` in `execute`. Also check `staged.length() + RESERVE` against `StorageSpace.freeBytes(...)` at the top of `publish*` and return a distinct error (not the generic "Check free storage").

### 9. WRONG BEHAVIOUR: error classification scans stdout, so a video title can trigger "Network problem" retries
- `backend/YoutubeDlBackend.kt:90-105` (log = stdout lines + stderr) feeding `engine/Errors.kt:20` (`"connection"`, `"timeout"`, `"timed out"`) and `:12` (`"private video"`).
- yt-dlp prints the title in stdout lines (`[download] Destination: <title> [id].mp4`, `[info] ...`). A video titled "Connection Lost" or "Private Video Tour" that fails for any other reason is classified `network` (retried 3 times with 5/15/45 s waits, ~65 s wasted) or "not available".
- Fix: classify from stderr (`result.stderr`) plus only the lines that start with `ERROR:`/`WARNING:`; keep stdout only for the "Details" view and the `ARCHIVED_MARKER` check.

### 10. WRONG BEHAVIOUR: a cancelled or paused item can still publish its file
- `engine/DownloadQueue.kt:610-630`.
- The state check at :592 happens before `outputStore.publish(...)`. If the user cancels during publish (a multi-GB copy takes many seconds, and `copyTo` in `MediaStoreOutputStore.kt:83` is not cancellable), the file lands in Download/Elisium, the item shows "cancelled", and History has no path. Pause during publish publishes too; the later resume then reports "Already downloaded".
- Fix: re-check `e.state in DOWNLOADING_STATES` right before publishing and after, and if the state changed after publish, either delete the published file (cancel) or record `filePath` (pause). In the copy loop, replace `copyTo` with a buffered loop that checks a cancel flag.

### 11. CRASH (rare race): `stopSelf()` can drop a start that `startForegroundService` just made
- `service/DownloadService.kt:73-85` (`main.post { if (pending) ... else stopNow() }`, `stopSelf()` without id) vs `service/DownloadCoordinator.kt:82-85` (`startService()` from an IO thread).
- Between the main-thread `pending` check and `stopSelf()` taking effect, a new item can flip `pending` to true and call `startForegroundService`. `stopSelf()` (no `startId`) stops unconditionally and discards the pending start; the app then promised a foreground service it never delivers (`ForegroundServiceDidNotStartInTimeException` after ~10 s on Android 12+), and `_pending` stays true so no new start is ever attempted.
- Fix: track `lastStartId` in `onStartCommand` and use `stopSelfResult(lastStartId)`; if it returns false, a newer start is queued and the service must stay. Also have the coordinator re-issue `startService()` when `pending` is true but the service reported a failure (`serviceError != null`) and the user adds or resumes something.

### 12. WRONG BEHAVIOUR: pasting or re-adding a failed/cancelled link does nothing
- `engine/DownloadQueue.kt:212-217`.
- A duplicate `add()` returns the existing item unchanged unless it is `done`/`skipped` with a missing file. A `failed` or `cancelled` item (or a `done` one whose file exists) just reports "Added 0 links (1 already in the list)". The spec's "Download again anyway" and "skip | replace | keep both" setting are not implemented on Android at all.
- Fix: in `add`, if the existing item is `failed`/`cancelled`, call `retry` semantics; expose an explicit `addAgain(url)` for the "Download again anyway" action (new identity suffix or remove the archive entry and file first).

### 13. WRONG BEHAVIOUR: ElisiumApp/queue exceptions from Room are not handled (disk full, DB corruption)
- `ElisiumApp.kt:104-107` (only `IllegalArgumentException` caught), `engine/DownloadQueue.kt:218,396` (history writes under the lock), `ui/ElisiumViewModel.kt:33-38` (`app.scope.launch { app.queue?.pause(id) }`).
- `history.add` / `history.updateState` can throw `SQLiteException` (full disk, which is exactly the failure mode of finding 8). In `viewModelScope` or `app.scope` (no handler) that is an app crash; inside `setState` it leaves the entry half-updated while the lock is released by the exception.
- Fix: wrap history calls in `setState` and `add` in try/catch (log, keep the in-memory state authoritative); add a `CoroutineExceptionHandler` to `ElisiumApp.scope`.

### 14. WRONG BEHAVIOUR: older Android (26-28) permission denial shows the wrong error
- `storage/MediaStoreOutputStore.kt:101-103` (`mkdirs` fails -> null), `engine/DownloadQueue.kt:46,619`.
- Denying WRITE_EXTERNAL_STORAGE (asked once, after the first link, `ui/permissions/PermissionHost.kt`) makes every finished download fail with "Could not save the file. Check free storage space", after the full download. Retry then redownloads (the archive entry is dropped by `reconcile` because the file is not in the folder).
- Fix: in `publishLegacy` check the permission first and surface a distinct `ErrorInfo` ("Allow storage access in Settings to save files"); ideally refuse to start downloads on API 26-28 until the permission is granted, or stage to app-specific external storage as a fallback.

### 15. WRONG BEHAVIOUR (low): Wi-Fi gate wording and metered Wi-Fi
- `service/DownloadCoordinator.kt:103,115`, `service/QueueSummary.kt:126`, `ui/downloads/QueueRows.kt:97-98`.
- "Wi-Fi only" is implemented as "not metered". A phone on a metered Wi-Fi (hotspot, or the user flagged it metered) or an unmetered 5G plan behaves opposite to the banner "Waiting for Wi-Fi". Offline with Wi-Fi-only on also says "Waiting for Wi-Fi".
- Fix: use `TRANSPORT_WIFI`/`TRANSPORT_ETHERNET` for the "Wi-Fi only" rule (optionally allowing metered Wi-Fi), and use different wording for "No connection" vs "Waiting for Wi-Fi".

### 16. POLISH: speed-limit field stores every typed prefix
- `ui/settings/SettingsViewModel.kt:77-82`.
- Typing "10M" stores "1" (1 byte/s), then "10", then "10M". Downloads that start in that window run at ~1 B/s (the coordinator applies each new value, `DownloadCoordinator.kt:67`). `0` is also accepted by `LIMIT_RE` (`settings/SettingsRules.kt:32`).
- Fix: debounce (e.g. 600 ms) or save on focus loss / IME Done; reject `0`.

### 17. POLISH: typed link text is lost when switching tabs
- `ui/ElisiumShell.kt:153-165` (`AnimatedContent` swaps the whole screen) with `ui/downloads/DownloadsScreen.kt:263` (`rememberSaveable` input).
- Content leaving an `AnimatedContent` is disposed and its `rememberSaveable` state is dropped (no `SaveableStateHolder`), so a half-typed or pasted link vanishes when the user glances at Settings. LazyColumn scroll position resets too.
- Fix: hoist `input` into `QueueViewModel` (it already survives rotation), or wrap each tab in `rememberSaveableStateHolder().SaveableStateProvider(tab.name)`.

### 18. POLISH (a11y): announcement live region sits inside the scrolling list
- `ui/downloads/DownloadsScreen.kt:290-299`.
- The polite live region is a LazyColumn item; when the user has scrolled down it is not composed, so TalkBack never speaks state changes ("Done", "Failed", 25% steps). It also pushes rows down when it appears/disappears.
- Fix: move the live-region Text out of the LazyColumn (e.g. in the Column above it, or as an invisible 1 dp node), and keep it always composed.

### 19. POLISH: theme flash and wrong initial theme on launch
- `MainActivity.kt:22` (`collectAsStateWithLifecycle(Settings())`).
- The first frame always uses defaults (system theme, motion on) until DataStore emits; a user with Appearance = Day on a dark system (or reduced motion on) sees one frame of the wrong theme/animations.
- Fix: read the initial value synchronously (`runBlocking { repo.current() }` in `onCreate`, it is a tiny file) or keep the splash up until the first emission.

### 20. POLISH: MediaStore duplicate-name handling
- `storage/MediaStoreOutputStore.kt:129-140,69-73`.
- (a) `findModernByName` does not see `IS_PENDING=1` rows (left behind if the process dies mid-copy) or files from a previous install (other owner), so MediaStore silently renames the new file to `name (1).ext` and dedupe layer 4 never sees it. (b) `USE_EXISTING` deletes the freshly downloaded staged file and reports success, even when the existing file is a different quality; fine while the archive blocks that case, wrong once "keep both"/"replace" exist.
- Fix: (a) query with `MediaStore.QUERY_ARG_MATCH_PENDING = MATCH_INCLUDE` (API 30+) and delete own stale pending rows at startup; (b) honour the duplicate-policy setting.

### 21. POLISH: other small items
- `ui/history/FileActions.kt:67` fallback MIME `*/*` for unknown extensions makes some viewers refuse the intent; prefer `application/octet-stream` or `ContentResolver.getType`.
- `engine/DownloadQueue.kt:32` queue never prunes `done`/`failed` items and there is no "Clear finished" action, so the Downloads list grows without bound in a long session (and `publishState()` rebuilds the full list on every progress line, `:380`; fine for 2-5 items, wasteful for 100).
- `service/DownloadService.kt:93-96` `onDestroy` does not unregister anything it started on `main` (a pending `main.post` can still run after destroy and call `stopNow()` on a dead service); use `main.removeCallbacksAndMessages(null)`.
- `service/DownloadCoordinator.kt:106` registers the network callback and never unregisters it (fine app-scoped), but it trusts `onLost(oldNetwork)` to mean "no network"; compare against the current default network id to avoid a false "offline" when a lost callback for the previous network arrives after the new one.

## Needs a device check (not verified, not counted above)
1. Progress callback: `LibraryYtDlpRunner` (`backend/YtDlpRunner.kt:45`) assumes the library calls the callback for every stdout line (so `--progress-template` JSON lines arrive). If 0.18.1 only invokes it for lines it parsed itself, the UI shows no progress and `ARCHIVED_MARKER` is never seen. First on-device test: add a download, check that percent moves and a re-add of an archived video shows "Already downloaded".
2. Argument order: confirm `YoutubeDLRequest.addCommands(args)` plus the URL produce `yt-dlp <args> <url>` and that `-P home:`/`-P temp:`/`--print-to-file` are accepted as given.
3. Process tree on pause: `destroyProcessById` terminates the python process; check ffmpeg/aria2c children do not linger and keep writing the same `.part`.
4. Doze/screen-off: no wake lock is held (manifest has no `WAKE_LOCK`); long downloads with the screen off may stall in deep sleep on some OEMs. Test a 10-minute download with the screen off, and consider a partial wake lock held while `pending`.
5. `stopSelf()` after a failed `startForeground` (DownloadService.kt:46) on Android 8-11: confirm it does not raise "did not then call startForeground".
6. `MediaStore` renames: `.opus`/`.webm` with the MIME values in `OutputNaming.kt:19-45` (MediaProvider may append a second extension when it disagrees with the MIME map).

## Checked and fine
Manifest (service `exported=false`, `dataSync` type + `FOREGROUND_SERVICE_DATA_SYNC`, `POST_NOTIFICATIONS`, `WRITE_EXTERNAL_STORAGE` capped at 28, FileProvider `exported=false` with grant, backup/extraction rules exclude everything). Channels are created before `startForeground`. Notification permission denial never blocks the service. `ForegroundServiceStartNotAllowedException` is caught (`IllegalStateException`) in both the coordinator and the service. MediaStore IS_PENDING flow is correct on API 29+, legacy path uses temp + rename. Lock order (queue lock -> archive lock) is consistent and NetworkGate -> queue lock has no reverse call. Rotation does not re-queue a share (`savedInstanceState == null` guard), `onNewIntent` is handled, and `launchMode=singleTop` matches the notification intents.
