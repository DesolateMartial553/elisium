# Brief 10D result - Android media engine

Status: implemented and all JVM tests pass. Not committed, not pushed, no emulator, no sudo. Own Kotlin client only
(no gallery-dl on Android). Implemented by Claude (Sonnet 5.5) as a subagent.

## Acceptance (real output)

`android/` has no `gradlew`, so the Gradle in the brief's command was run as the system `gradle` (same flags, same as 10A):

```
cd android && JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --offline --no-daemon --max-workers=1 \
  -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest --rerun-tasks

> Task :app:testDebugUnitTest
BUILD SUCCESSFUL in 2m 45s
27 actionable tasks: 27 executed
```
Test XML totals: `tests=575 skipped=0 failures=0 errors=0` (457 before this brief + 118 new). `lintDebug` and `assembleDebug` were
not run (not in this brief's acceptance).

## What was built

New, `media/` (pure Kotlin, JVM-tested):
- `MediaPorts.kt` - `CancelToken` (flag + closers: `disconnect()` / `Process.destroy()` run on cancel), `MediaFailure`,
  `MediaFetchException`, ports `MediaFetcher`, `FileDownloader`, `FfmpegSession`, and `MediaEngine`.
- `MediaHttp.kt` - `HttpTransport` + `UrlConnectionTransport` (`HttpURLConnection`, no new dependency, Range resume),
  Netscape cookie header per host (`cookieHeader`, `cookieValue`).
- `MediaClient.kt` - `HttpMediaFetcher` (Instagram `media/{id}/info/` via `ShortcodeId`, `users/web_profile_info/` +
  `feed/reels_media/` for trays, `reel_ids=highlight:<id>` for highlights, TikTok page `__UNIVERSAL_DATA_FOR_REHYDRATION__`),
  feeds the 10A parsers; `HttpFileDownloader` (`.part` then rename). The cookie header is built per request, never kept,
  logged or put in an exception.
- `MediaErrors.kt` + `engine/Errors.kt` - `mediaErrorInfo`; new `STORY_EXPIRED`, `PRIVATE_ACCOUNT`, `NO_MEDIA_FILES` with the
  exact desktop `errors.py` words.
- `MediaNaming.kt` - desktop names, `safeFolderName`, markers. `MediaMix.kt` - `photoSeconds`, `chooseCanvas`,
  `parseProbeJson`, `buildCutCommand`, `buildMixCommand` (port of desktop `mix.py`, `out_range=tv`, `Locale.ROOT` numbers).
  `MediaConverter.kt` - `convertStaging` (port of `process_staging`, same notes and order). `MediaModes.kt` - `PhotoMode`,
  `SongLength`, `MediaRoute`, `routeFor`. `MediaKeys.song` added.

New elsewhere: `engine/MediaRunner.kt` (one attempt: fetch, plan, skip by archive, download, convert, publish, archive),
`backend/ProcessFfmpegSession.kt` (`nativeLibraryDir/libffmpeg.so` + `libffprobe.so`, `LD_LIBRARY_PATH` from
`noBackupFilesDir/youtubedl-android/packages/{python,ffmpeg,aria2c}/usr/lib`), `data/Migrations.kt`.

Changed:
- `engine/DownloadQueue.kt` - routing in `attempt`, `runMediaAttempt`, `/p/` fallback, `add(..., force)`, setters
  (`setMediaEngine`, `setPhotoMode`, `setSongLength`), new `QueueItem` fields `thumbnail`, `formatLabel`, `filesDone`,
  `filesTotal`, `note` (trailing, defaulted). Media keys live in `media-archive.txt` beside `archive.txt` (yt-dlp appends to
  the other file; a rewrite of it by us could drop its lines).
- `engine/Ports.kt` - `OutputStore.publish(staged, name, subfolder)` and `existsInFolder(subfolder, marker)` with defaults
  (flat); `HistoryStore.updateExtras`; `HistoryRecord.note/filesTotal`.
- `engine/StagingCleanup.kt` - `mediaDirFor` (`staging/media/<sha1(identity)[:16]>`), `deleteDirectory`, and `sweepOrphans` now
  also sweeps those folders (cancel and failure delete them).
- `data/` - `HistoryEntity` (+`note`, `files_total`), `HistoryDao.updateExtras`, `RoomHistoryStore`, `AppDatabase` version 2 with
  `MIGRATION_1_2`. KSP exported `app/schemas/.../2.json`.
- `settings/` - `Settings.photoMode/songLength`, `SettingsRepository` keys + setters (`SettingsStore` setters have default bodies).
- `service/DownloadCoordinator.kt` - builds the `MediaEngine`, applies both settings to the queue.

## Behaviour (mirrors desktop 10B/10C)

- Routing (`routeFor`): reels, videos, YouTube, everything else stay on yt-dlp unchanged. Story trays, highlights, TikTok
  `/photo/` go to the media engine only. Instagram `/p/`, `/tv/` and a single `/stories/<user>/<id>/` try yt-dlp first; on a
  `no_media` error (at probe or at download) the same attempt re-runs once on the media engine, no retry counted, and later
  retries go straight to the media engine. The media engine's own `no_media` is final (no loop back).
- Download into `staging/media/<hash>/`; progress = `files_done / files_total` (a built mp4 counts as one file, removed from the
  total if it was not made); pause/cancel/resume like other items; finished staged files are skipped on resume; archived and
  still in the output folder are skipped, archived but gone are dropped from the archive and fetched again.
- Output: `<owner> <date> <shortcode> [<media id>] <n>.<ext>` (TikTok `<owner> <id> [<id>_<n>] <n>.<ext>`), published to the
  owner subfolder through the new store seam; an existing name is skipped, never renamed or overwritten.
- Song: snippet cut with `-ss -t -c copy`, AAC re-encode retry; video `<base> [<post>_mix].mp4` with desktop canvas, durations,
  2 s minimum, `out_range=tv`. ffmpeg missing or failing never fails the item (done + same note text as desktop).
- Settings: photos+song+video (default) / photos+song / photos only (song not even downloaded); snippet (default) / full song.
- "Download again anyway": `queue.add(url, force = true)` ignores the media archive for that run; nothing missing -> `skipped`
  with `already_downloaded` and note "Already saved" (decided from per-file pre-checks, not from `publish()`).
- History rows get `note` and `files_total`.
- yt-dlp items also get `thumbnail` (probe `thumbnail`, else the last of `thumbnails`, http/https only) and `format_label`
  ("1080p MP4", "MP3 audio") like desktop 10C (`engine/ProbeDisplay.kt`); they are display only and never reach history.

## Tests (118 new, all JVM/offline, fake HTTP/ffmpeg/store)

`MediaMixTest` 12 (all desktop pure argv/canvas/probe cases; `snippet_from_metadata` and `find_existing_mix` are not ported: the parser supplies the snippet times and `existsInFolder` replaces the second), `MediaNamingTest` 9, `MediaConverterTest` 16 (notes, retry, settings combos, cancel,
mixed carousel, no ffprobe), `MediaClientTest` 22 (fixtures, every HTTP status, cookies, private, TikTok, downloads),
`MediaErrorsTest` 10 (every mapping), `MediaQueueTest` 39 (routing table per URL kind, `/p/` fallback both paths, no loop,
progress counts, archive skip on re-add, missing-file refetch, force, every error code, 5/15/45 backoff, all 6 photo-mode x song-length combinations, ffmpeg missing (and a re-add without ffmpeg fetches nothing), yt-dlp thumbnail/kind line, tray, pause/resume, cancel cleanup, session never in error/history), `MigrationTest` 5
(schema 1 -> 2 diff, migration SQL, old rows, Room store extras; no `room-testing` dependency, so no real SQLite run),
`PhotoSettingsTest` 3, `ProbeDisplayTest` 2. `FakeHistory` (TestSupport.kt) gained `updateExtras`.

## Deviations and things left for the owner/Claude

1. **Owner subfolder is wired through a seam but not yet real on a device.** The brief did not allow editing `storage/`, and
   `MediaStoreOutputStore` still writes flat into `Download/Elisium/`. Needed change in `storage/MediaStoreOutputStore.kt`
   (+ `OutputNaming.kt` if wanted): override `publish(stagedFile, displayName, subfolder)` and `existsInFolder(subfolder,
   videoId)` using `RELATIVE_PATH + safeFolderName(subfolder) + "/"` in `publishModern`, `findModernByName`, `existingByIdModern`
   and `legacyDir()` (API 26-28). Until then the files are flat and the dedupe checks still work (they look for `[marker]`).
2. **Wiring is in `DownloadCoordinator.start()`** (it has a Context), so `ElisiumApp.kt` is untouched.
3. **Single `/stories/<user>/<id>/` is yt-dlp-first** (desktop's actual rule, deviation 2 of 10B-1), not media-only as one line of
   this brief reads; the media engine handles it on `no_media` and our client also does video stories.
4. **Song file name** is `<base> song [<post>_song].<ext>` (desktop: `<base> song.<ext>`), so the "already saved" check can use a
   `[marker]` like every other file. The staged whole track is `<base> full [<post>_song].<ext>`. Archive key `<site> <post>_song`
   added to `MediaKeys`.
5. **Trays** (several unrelated songs): each song is kept whole, nothing is cut or mixed (desktop does the same for a tray).
6. Mix is only for a single post; a missing video rebuilds from re-fetched photos/song (saved copies are not duplicated).
7. Used `gradle`, not `./gradlew` (none in `android/`). ffmpeg's `libx264` is present in the bundled AAR (checked `libx264.so` and
   `--enable-libx264` in `libffmpeg.so`).
8. Display-only: `thumbnail`/`format_label` are not persisted. Only `note` and `files_total` go to history, as in desktop.
9. The media client now reads `cookies.txt` in-process to build the `Cookie`/`X-CSRFToken` headers (the brief requires it). This
   contradicts the comments in `Ports.kt` and `settings/CookieJar.kt` ("only the path is ever given") and SPEC's "never reads or
   copies the cookie contents" wording: 10F should update them. The values are never logged or put in an error, note or history row
   (tested).
10. UI is untouched (10E): the new snapshot/history/settings fields are data only; `SettingsStore` setters for the two new
   settings exist but no screen calls them yet.

## Needs a live check

- yt-dlp's real `no_media` text on a real photo post at probe time: the whole `/p/` fallback keys on it (`There is no video in
  this post` / `Instagram sent an empty media response`).
- A mixed photo + video carousel on `/p/`: yt-dlp may succeed with only the videos and silently skip the photos (no fallback runs).
- TikTok image CDN may need a `Referer`; `HttpFileDownloader` sends only `User-Agent` and `Accept`.

- Real Instagram JSON and headers: `X-IG-App-ID` value, `api/v1/media/{id}/info/` on `www.instagram.com` with a WebView-captured
  session, the shortcode -> media id route for `/tv/`, and the user lookup (`web_profile_info`) for story trays; `reel_ids=
  highlight:<id>`; whether 400/403 carry `login_required` as assumed; 404 vs private-account behaviour for posts.
- TikTok page parsing (`__UNIVERSAL_DATA_FOR_REHYDRATION__` -> `webapp.video-detail.itemInfo.itemStruct`), `statusCode` 10222
  meaning private, and that image URLs download without cookies.
- Signed-in stories and highlights end to end; music snippet field names for posts vs stories (`music_consumption_info`);
  whether the snippet `duration_in_ms` is the snippet or the whole track.
- ffmpeg on a device: running `libffmpeg.so` / `libffprobe.so` as a child process with the `LD_LIBRARY_PATH` above, `libx264`
  encode speed on the phone, HEIC/AVIF photo input, rotated or odd-fps carousel clips.
- Blocking HTTP reads are interrupted through `disconnect()` on pause/cancel; confirm on a slow connection.
- Rate limits / account flags from repeated requests (10G slow mode is not part of this brief).
