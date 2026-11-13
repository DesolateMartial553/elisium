# Brief 5B result - Kotlin engine port

## Files
Build: `android/gradle/libs.versions.toml` (coroutines 1.10.2, kotlinx-serialization-json 1.9.0, serialization plugin at Kotlin version), `android/build.gradle.kts`, `android/app/build.gradle.kts`.

Engine (`android/app/src/main/java/com/desolate/elisium/engine/`): `UrlNorm.kt`, `Errors.kt`, `Presets.kt`, `Formats.kt`, `Archive.kt`, `Ports.kt`, `ProgressParser.kt` (extra, see deviations), `DownloadQueue.kt`.

Tests (`android/app/src/test/java/com/desolate/elisium/engine/`):

| File | Tests |
|---|---|
| UrlNormTest | 12 |
| ErrorsTest | 4 |
| PresetsTest | 2 |
| FormatsTest | 14 |
| ArchiveTest | 28 |
| ProgressParserTest | 10 |
| DownloadQueueTest | 48 |
| QueueLocalFlowTest | 2 |
| SmokeTest (existing) | 1 |
| **Total** | **121** |

`TestSupport.kt` holds the fakes (FakeHistory, FakeStore, FakeBackend, FakeHandle).

## Commands run
- `:app:testDebugUnitTest` (with `--rerun-tasks`): BUILD SUCCESSFUL, 121 tests, 0 failures, 0 skipped (counts from the JUnit XML in `app/build/test-results`).
- `:app:assembleDebug`: BUILD SUCCESSFUL (36 tasks), `app-debug.apk` produced.
Both run with `JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g`. No `--offline` (first run downloaded the allowed dependencies).

## Deviations / decisions
- Test counts are not one-for-one with Python: parametrized cases are folded into one Kotlin test; extras added (parser edge cases, round-half-even, error messages, publish failure, pause-while-probing, backoff-then-success, a threaded archive-serialisation test, 50-add stress).
- `test_e2e_local.py` needs real yt-dlp/ffmpeg: `QueueLocalFlowTest` is a JVM stand-in with a directory-backed OutputStore and a fake backend that writes a real staged file and appends the real archive file.
- `test_runner.py`: only the pure progress parsing and stage mapping were ported (`ProgressParser.kt`, added so brief 5C shares one mapping). Command building and process handling are 5C.
- Settings tests in `test_presets_settings.py` (UI settings) not ported; only presets.
- Queue calls `OutputStore.publish(staged, name)` on success when the backend reports a file; null result fails the item with code `publish_failed` ("Could not save the file."). Not in Python. `_find_output` (scan of output dir) is dropped: path comes only from the backend outcome.
- `OutputStore` gained `existsAt(location)` (default true) for the "is the recorded file still there" check; `forget` is called when a deleted file is requeued.
- Skipped items get `error = Already downloaded.` on the item for both skip paths (Python only did so for the silent one); a `done` transition clears the error in history and the item (Python left a stale retry error).
- Backoff is milliseconds (`BACKOFF_MS`); `DownloadOutcome` has an extra `terminated` flag mirroring `handle.terminated`.
- Python's thread scheduler is replaced by a `schedule()` that launches workers on the injected scope; `start()`/`stop()` kept; `waitUntilIdle()` suspends on an internal idle StateFlow.
- Formatting uses BigDecimal half-even so `human_size` rounds like Python.
- Test gotcha: `advanceUntilIdle()` skips `backgroundScope` work, so tests use `runCurrent()`.
- Known minor parity gaps (unicode digits in `isdigit`/`\d`) ignored.
- Not touched: `desktop/`. Nothing committed.
