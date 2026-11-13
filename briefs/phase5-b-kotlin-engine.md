# Brief 5B - Kotlin engine port (pure logic, JVM-tested, no UI)

Port the finished, audited **Python engine** to Kotlin so the Android app behaves exactly like the Arch app. The Python code and its tests are the source of truth for behaviour:
`desktop/elisium_downloader/engine/{urlnorm,errors,presets,formats,archive,runner,queue}.py` and `desktop/tests/test_{urlnorm,errors,presets_settings,formats,archive,runner,queue,e2e_local}.py`. Read `AGENTS.md` and `core-spec/SPEC.md` first. Do the port faithfully, case by case; do not redesign. Where Android genuinely differs, follow "Android adaptations" below.

All code goes under `android/app/src/main/java/com/desolate/elisium/engine/` (package `com.desolate.elisium.engine`) with tests in `android/app/src/test/java/com/desolate/elisium/engine/`. Everything in this brief must run as plain **JVM unit tests** (`:app:testDebugUnitTest`) - no Android classes (`Context`, `Uri`, `Log`, `org.json`) in the engine files, no emulator, no network, no real yt-dlp. Use `java.io.File`/`java.nio` for files and `kotlinx.serialization.json` for JSON.

## Dependencies you may add (to `gradle/libs.versions.toml` + `app/build.gradle.kts`)
`org.jetbrains.kotlinx:kotlinx-coroutines-core`, `kotlinx-coroutines-test` (test), `org.jetbrains.kotlinx:kotlinx-serialization-json` with the `org.jetbrains.kotlin.plugin.serialization` plugin (same version as Kotlin). Stable versions only. Nothing else.

## Part 1 - pure modules (port + tests)
1. `UrlNorm.kt`: `normalizeUrl(url)`, `videoKey(url)` (`"youtube:<ID>"` or null), `IllegalArgumentException` for bad input. Same rules and the same test cases as `test_urlnorm.py` (youtu.be / watch / shorts / embed / live / m. / music., tracking params, `t`/`start`, playlist keeps `list`, other sites strip `utm_*` and fragment). Do not use `java.net.URI` quirks that differ; hand-parse the query like the Python does.
2. `Errors.kt`: `explain(rawLog): ErrorInfo(message, fix, code)` with the exact table and order of `errors.py` / SPEC.md.
3. `Presets.kt`: the preset list exactly as `presets.py` (ids, labels, selectors, extra args), `get(id)` with `best` fallback.
4. `Formats.kt`: `formatRows(info: JsonObject)`, `selectorFor(videoId, audioId)`, `humanSize`, `humanDuration`, `summary(info)`, `playlistEntries(info)`, `parseRange(text, max)` exactly like `formats.py` and its tests.
5. `Archive.kt`: yt-dlp-compatible archive file (`<extractor> <id>` lines), atomic write (temp file + `Files.move` ATOMIC_MOVE with replace), `has/add/remove`, tolerant reading. Use a `ReentrantLock` inside the class so one process cannot interleave read-modify-write.

## Part 2 - queue (coroutines) behind interfaces
Define these interfaces in `engine/Ports.kt` (the Android implementations come in brief 5C; here you write fakes in the tests):
- `DownloadBackend`: `suspend fun probe(url: String): ProbeResult` (returns the parsed `-J` JsonObject or throws `ProbeFailure(raw: String)`), and `fun start(request: DownloadRequest, onProgress: (Progress) -> Unit): DownloadHandle` where `DownloadHandle` has `suspend fun await(): DownloadOutcome` (exit code, raw log, final file path or null, `alreadyArchived: Boolean`) and `fun cancel()`. `DownloadRequest` carries url, format selector, extra args, limit rate, archive file path, a **staging dir** (where yt-dlp writes), and a process id string.
- `OutputStore`: `fun existsFor(extractorKey: String, videoId: String): Boolean` (is a finished file for this video already in the final location?), `suspend fun publish(stagedFile: File, displayName: String): PublishedFile?` (moves the finished file to its final place; returns null on failure; later implemented with MediaStore), `fun forget(...)`.
- `HistoryStore`: `add`, `updateState`, `get`, `search`, `recent`, `delete` with the same fields as `history.py`; the tests use an in-memory fake (Room comes in 5C).
- `Clock`/`Delay` injection: the queue takes a `delay: suspend (Long) -> Unit` and a `CoroutineScope`/`CoroutineDispatcher` so tests control time with `runTest`.

`DownloadQueue.kt` ports `queue.py` behaviour exactly: states `queued, probing, downloading, merging, converting, paused, done, failed, skipped, cancelled`; concurrency 1-5 (setter validates); `add(url, formatSelector?, extraArgs?, title?)` with dedupe identity = `videoKey` else `normalizeUrl` and duplicate-add returns the existing item; re-adding a `done`/`skipped` item whose file is gone requeues it (use `OutputStore.existsFor`); pause (cancels the handle, keeps staged `.part` files so resume continues), resume, retry, cancel; network errors retry after 5s/15s/45s then fail (code `network` only); archive skip -> `skipped` with the "Already downloaded." info; stage mapping (merger -> merging, MoveFiles/Metadata/FFmpegMetadata/SponsorBlock ignored, other post-processors -> converting); `file_path` comes from the backend outcome; `alreadyArchived` + no file -> `skipped`; archive lock + never rewrite the archive file while an item is downloading (read-only view), exactly like the Python. Expose `val items: StateFlow<List<QueueItem>>` and `val events: SharedFlow<QueueEvent>` (added / state / progress) instead of listeners. A public `suspend fun probe(url)` and `ytdlp` info are NOT needed here.

## Tests (JUnit 4 + coroutines-test; port the Python cases one for one)
Every test file in the Python list above has a Kotlin counterpart with the same cases (names may be translated to backtick sentences). For the queue, use the fake `DownloadBackend`/`OutputStore`/`HistoryStore` to cover: concurrency limit, duplicate add, URL forms collapsing to one item, pause/resume/retry/cancel, backoff 5/15/45 then failed (virtual time), archive skip, deleted-file re-add, per-item overrides, non-retryable error fails immediately, stage mapping, the archive-lock rule, and a stress case of 50 adds with concurrency 3 finishing every item exactly once.

## Android adaptations (only these)
- Final location is abstracted by `OutputStore`; there is no `output_dir` string. `Archive` and staging dir are plain `File`s given by the caller.
- No Qt/UI listeners: use the `StateFlow`/`SharedFlow` above.
- Do not implement any Android-specific class here (`MediaStore`, `Service`, Room, `YoutubeDLRequest`): that is brief 5C.

## Acceptance (paste real output)
```
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:assembleDebug
```
Report the number of tests per file and the total. The APK must still build.

## Do not
Touch `desktop/`, add other dependencies, add permissions, use Android classes in `engine/`, start an emulator, use adb, commit or push. If memory runs out (the Gradle daemon vanishing), stop other work and retry; do not raise memory limits above the values in `gradle.properties` without saying so. Write `briefs/phase5-b-kotlin-engine.result.md` with files, per-file test counts, exact output, deviations.
