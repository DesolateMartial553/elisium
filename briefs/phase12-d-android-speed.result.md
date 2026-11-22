# Brief 12D result - Android speed (extract once, "Faster downloads", locks, feel, aria2c removed)

Implemented by a Sonnet subagent (2026-11-22). Not committed, not pushed, no emulator, no sudo. **Nothing here was run on a device.**

## Acceptance (real output)
```
cd android && JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest :app:assembleDebug
BUILD SUCCESSFUL in 1m 45s
45 actionable tasks: 11 executed, 34 up-to-date
EXIT 0
```
Test XML totals: `tests=640 skipped=0 failures=0 errors=0` (600 before this brief).
The acceptance command was run twice: the first run (after a targeted run of the new tests, which passed) failed 1 test,
`QueueUiTest.titleFallsBackToUrlAndBlankCounts`, an old assertion that a queued card's title is the URL (the instant card now
shows the host). Test-only fix, then the whole command was re-run: the output above.

## What was built
1. **Extract once (12B).** `engine/FasterDownloads.kt` (new, pure): `infoIsUsable` (object, not `playlist`/`multi_video`, has `formats`
   or `url`, probe under 300 s), `mayReuseProbe`, `shouldRerunFromUrl`, `writeInfoJson`. `DownloadQueue` keeps the probe's
   info for the attempt only (never on the item or in history), writes it to `staging/tmp/item-<id>.info.json` (old file/link
   removed, `CREATE_NEW`, owner-only 0600) and passes `DownloadRequest.infoJson`. `buildDownloadArgs` appends
   `--load-info-json <file>` and `runnerUrlFor` gives the runner an empty URL; `LibraryYtDlpRunner` maps "no URL" to an empty
   `YoutubeDLRequest(List)` (that constructor exists in youtubedl-android 0.18.1, checked with `javap`). Failure of the info run
   before the first progress line, or `http_403`/`http_410`/`format_unavailable` (or "HTTP Error 410", "expired", "format is not
   available" in the log): ONE immediate re-run from the link, no `attempts` increment, no `delay`, paused/cancelled re-checked,
   state put back to `downloading`; the file is deleted in a `finally`. Off (or any unusable probe) gives the same argv as before
   (test). Media-engine items return before the probe, so they never reach it; signed-in Instagram/TikTok and a rate-limited
   site never reuse it either (mirrors desktop `may_reuse_probe`).
2. **Audio presets copy:** M4A `bestaudio[ext=m4a]/bestaudio/best`, Opus `bestaudio[acodec=opus]/bestaudio/best` (`-x --audio-format`
   kept). Pins in `PresetsTest.kt` (the brief named `YtDlpCommandsTest.kt`, which pinned no audio selector).
3. **Setting "Faster downloads: Auto / Off"** (default Auto): `Settings.fasterDownloads` + `FasterDownloads` enum (junk/missing
   stored value -> Auto), DataStore key, `SettingsViewModel`, a Settings > Downloads row (two choice rows, helper "Auto looks
   each link up once. Turn off if downloads fail.", same words as desktop), wired in `DownloadCoordinator` to
   `queue.setReuseProbe`. **429 rail:** the first `http_429`/`rate_limited` for a site in a session (recorded in `afterFailure`, so
   media failures count too) stops probe reuse for that site and lets only ONE of its items run at a time (`schedule()` now
   skips a blocked item instead of stopping; other sites go on). Pure `siteKey`, `siteSlotFree`, `isRateLimitCode` + tests.
4. **Locks.** `service/DownloadLocks.kt` (pure `shouldHoldLocks` = any item probing/downloading/merging/converting, and
   `DownloadLocks` acquire/release bookkeeping behind a `HeldLock` interface), `service/AndroidHeldLocks.kt` (partial `WakeLock`
   with a 6 h safety timeout, `WifiLock` `WIFI_MODE_FULL_HIGH_PERF`, `@Suppress("DEPRECATION")`). `DownloadService` follows
   `queue.items`, holds both while a download runs, releases on idle (pending false), when the foreground start fails,
   in `stopNow` (error/timeout) and in `onDestroy`. **Manifest: added only `WAKE_LOCK`** (the merged manifest had none; `WifiLock`
   needs `WAKE_LOCK`, not `CHANGE_WIFI_STATE`, so that one was NOT added).
5. **aria2c removed.** `implementation(libs.youtubedl.aria2c)` removed from `app/build.gradle.kts`; `Aria2c` import + init removed from
   `ElisiumApp.kt`; `aria2c` dropped from the `LD_LIBRARY_PATH` list in `backend/ProcessFfmpegSession.kt`. Build and all tests pass;
   Elisium never passed `--downloader`/`--external-downloader` (test pins it). The now-unused `youtubedl-aria2c` line in
   `android/gradle/libs.versions.toml` was left (outside the allowed files, harmless).
6. **Feel (12E).**
   - Instant card: `queueTitle` shows the link host (`youtube.com`) while queued/probing; failed rows still show the URL; the
     "Looking up the post..." title is unchanged.
   - Thumbnail alongside the probe: **verified, no change needed**. The queue emits `ItemUpdated` with the picture as soon as the probe
     returns, before the download starts; `Thumbnail` (10E loader) fetches on that update. New test pins the order.
   - Smoothed ETA: `SpeedSmoother` (EMA alpha 0.2, first 2 s of a file as reported and kept out of the average, restart when the byte
     count drops); applied in `DownloadQueue.onProgress` with an injectable `clock` (default wall clock). Media-engine items untouched.
   - "Starting..." with a reason after 10 quiet seconds: queue stamps `QueueItem.quietSince` on state/progress change and computes
     `waitHint` (rate_limited > network retry > signing_in for IG/TikTok with cookies); `QueueRowModel.startingSince/stallReason`;
     pure `stallSide`/`sideAt`; the Compose row ticks once a second only while that row is starting (a `LaunchedEffect`, no ticker in
     the view model). Words: "Signing in", "Waiting for Wi-Fi" (from the Wi-Fi hold, shown on queued rows at once), "Waiting for the
     network", "Rate limited, waiting" (queued rows of a limited site also show it at once).
   - Carousel `files_done` per file: **verified, no change needed** (`MediaQueueTest` lines ~329-333 already pin `ProgressChanged` per file).
   - All content descriptions and the "N percent" TalkBack text are unchanged (row spoken text is title/state/percent/speed/eta/error/note as before).
7. **MediaStore copy speed:** both staging -> public-folder copies in `storage/MediaStoreOutputStore.kt` used `copyTo` with the 8 KiB default;
   now 1 MiB (`COPY_BUFFER_BYTES`). Not measurable without a device.

## Files changed
`android/app/build.gradle.kts`, `android/app/src/main/AndroidManifest.xml` (WAKE_LOCK), under `.../com/desolate/elisium/`:
`ElisiumApp.kt`, `engine/{FasterDownloads(new),DownloadQueue,Ports,Presets}.kt`, `backend/{YtDlpCommands,YoutubeDlBackend,YtDlpRunner,ProcessFfmpegSession}.kt`,
`service/{DownloadLocks(new),AndroidHeldLocks(new),DownloadService,DownloadCoordinator}.kt`, `settings/{SettingsRules,SettingsRepository}.kt`,
`ui/settings/{SettingsViewModel,SettingsScreen}.kt`, `ui/downloads/{QueueRows,QueueViewModel,DownloadsScreen}.kt`, `storage/MediaStoreOutputStore.kt`
(outside the brief's folder list but named by item 7).
Tests (`android/app/src/test/.../`): new `engine/FasterDownloadsTest` (10), `engine/FasterQueueTest` (13), `ui/FasterFeelTest` (9), `service/DownloadLocksTest` (4);
extended `backend/YtDlpCommandsTest`, `backend/YoutubeDlBackendTest`, `settings/SettingsRulesTest`, `engine/PresetsTest`;
updated pins `ui/NightShelfQueueTest` (queued reel -> `instagram.com`), `ui/QueueUiTest` (queued title -> host), `ui/HistoryAndSettingsTest` (`FakeSettingsStore` setter).
Deviation: strings are Kotlin constants under `ui/` (not `res/values/strings.xml`, which is not on the edit list).

## APK size (debug, arm64 only)
Before (from the previous brief's build): file 74,306,505 B, compressed entries total 74,219,648 B, includes `libaria2c.so` (1,032,430 B deflated) and
`libaria2c.zip.so` (4,246,281 B). After: file on disk 74,306,357 B, but that is an incremental repackage that left 5,259,945 B of unreclaimed holes
where the removed entries were; compressed entries total **68,960,080 B (-5,259,568 B, about -7.1%)**, uncompressed 100,303,994 -> 93,512,033 B.
A clean build would give a file of about 69.05 MB (not built: one heavy job only). Removed module: `aria2c-0.18.1.aar` (arm64 part only is packaged because of `abiFilters`).

## Not verified on a device
- The locks: that Android grants both, that `WIFI_MODE_FULL_HIGH_PERF` does anything (deprecated, ignored on recent Android; kept because the brief asked for it), that they are released on idle/error/destroy in the real service.
- The speed effect of extract-once and of the 1 MiB copy buffer; that yt-dlp inside youtubedl-android accepts `--load-info-json` with an empty URL list for each site (desktop 12A measured it for YouTube only); that `YoutubeDL.execute` accepts a request with no URL.
- Every changed screen (Settings row, "Starting..." text, host titles); no Compose UI test exists in the project.
- The rate-limit rail against a real 429; the APK size on a clean build.

## Notes
- The queue's attempt timeline: a 429 on an info run before any progress is re-run once from the link by the 12B rule; the site is marked when the final failure is returned (same as desktop).
- `youtubedl-aria2c` still sits in `android/gradle/libs.versions.toml` (unused).
