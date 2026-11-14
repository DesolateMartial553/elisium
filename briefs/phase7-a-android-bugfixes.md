# Brief 7A - Android bug fixes from the code review

Read `briefs/android-review-findings.md` (21 ranked findings from a read-only review; each has file:line, scenario and a suggested fix), `AGENTS.md`, `core-spec/SPEC.md`. Nothing has run on a real device, so fix what can be fixed by reading and unit testing. Edit only under `android/` (code + tests) and write `briefs/phase7-a-android-bugfixes.result.md`. Do not touch `desktop/` or `design/`, do not commit or push, no emulator/adb.

For EVERY finding: re-read the cited code first; if the claim is wrong or already fine, say so in the result file instead of changing anything. Add a JVM unit test for each fix that can be tested without Android (extract pure logic where needed). Keep all 292 existing tests passing and all accessibility semantics intact.

## Must fix (in this order)
1. **Room on the main thread** (findings 1 and 2): run `ElisiumApp.addLinks` body (the `queue.add` loop) on `Dispatchers.IO` internally so no caller can hit Room on Main; in `DownloadService` handle `ACTION_PAUSE_ALL` / `ACTION_CANCEL_ALL` and `onTimeout` off the main thread (`app.scope.launch`) and for `onTimeout` call `stopNow()` FIRST so the Android 15 timeout is always honoured. Audit every other call into `DownloadQueue` from UI/service code for the same problem (queue actions, history queries, settings) and fix any that touch Room on Main.
2. **Engine init** (finding 3): catch `Throwable` (rethrow `CancellationException`) so `UnsatisfiedLinkError` etc. show the "engine failed" state instead of killing the app.
3. **Pause then quick resume marked failed** (finding 4): after `await()` return null when `outcome.terminated`, and make the state machine tolerate resume arriving before the old worker wakes; add a queue test for pause -> resume race and for the Wi-Fi hold flapping.
4. **`--no-playlist` on single-video downloads** (finding 5): add `--no-playlist` to the download argv unless the item came from the playlist picker (check how playlist items are queued in `DownloadQueue`/`Presets`/`extraArgs`: items chosen from a playlist are individual video URLs, so passing `--no-playlist` for everything the queue downloads is correct; confirm and say so). Update the argv test that mirrors the desktop semantics, and note in the result file that `desktop/elisium_downloader/engine/runner.py` has the same gap so Claude can fix it there.
5. **Stale `stopSelf()`** (finding 11): use `stopSelf(startId)` / only stop when the coordinator says nothing is pending, so a concurrent `startForegroundService` is never dropped.
6. **Cancel or pause during publish** (finding 10): do not publish (and delete the staged file) if the item was cancelled/paused while the copy was starting; test with a fake output store.
7. **Process kill recovery** (finding 6): on app start, any history row left in `queued`/`downloading`/`merging`/`converting` is marked failed with the plain message "Interrupted when the app closed. Tap Retry." (or the closest existing error wording) so History never shows stuck rows; the user can "Download again". Test with a fake history store.
8. **Staging cleanup** (finding 7): after cancel/failure/publish-failure/archived-skip delete the item's staged leftovers except `.part` files of items that are paused or failed-retryable; on app start remove orphan files in `staging/` older than 7 days. Pure helper + tests.
9. **Error classification reads stdout** (finding 9): classify from stderr / `ERROR:` lines only, not titles on stdout; test with a title containing "connection" and "private video".
10. **Re-adding a failed or cancelled link does nothing** (finding 12): make `add` of a link whose existing item is failed/cancelled/skipped retry it (or add the explicit "Download again" behaviour) and make the UI say what happened; follow SPEC dedupe rules, test.

## Also fix if straightforward (cheap, low risk)
- Finding: speed-limit field saves every typed prefix ("1", "10"): validate on a debounce / on focus loss / IME Done, not per keystroke.
- Typed link text lost on tab switch: move the `rememberSaveable` outside `AnimatedContent`.
- Metered-Wi-Fi wording and the "check free space" message shown when storage permission is denied on API 26-28 (make it say storage permission is needed and link to the permission flow).
- `main.post` not cancelled in `onDestroy`; stale `onLost` network callback; fallback MIME `*/*`.
- Room exception handling around history writes (disk full must not crash a worker).
- Free-space check (finding 8): use the probed `filesize`/`filesize_approx` when known (staging needs ~2x) with the fixed floor as fallback.

## Do NOT do
The "needs a device check" items (callback per stdout line, orphaned ffmpeg after pause, wake lock, MediaStore renaming of .opus/.webm): list them in the result file under "Needs a real phone", change nothing speculative. Skip findings that need big refactors and say which.

## Acceptance (paste real output)
```
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:assembleDebug
```
Zero lint errors. First build may be OOM-killed: retry. The result file lists, per finding number: fixed (with test name) / not a bug / deferred (why) / needs phone. Write it even if low on budget; do not stop silently.
