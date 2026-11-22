# Brief 12D (+12B Android, 12E Android) - Android: extract once, "Faster downloads", locks, feel

Plan: `~/.claude/plans/elisium-speed-phase12.md`. Evidence: `briefs/phase12-a-bench.result.md`: only extract-once helped; `-N`
gave no gain; no case for aria2c. Read `AGENTS.md`, `briefs/phase12-b-desktop-extract-once.result.md` and
`briefs/phase12-c-desktop-faster-setting-and-feel.result.md` (the behaviour to mirror), `briefs/phase11-d-android-nightshelf-and-10e-screens.result.md`.
Edit only under `android/app/src/main/java/com/desolate/elisium/` (`engine/`, `backend/`, `service/`, `settings/`, `ui/`),
`android/app/build.gradle*` (only to remove the aria2c module, see 5), `ElisiumApp.kt` (only to drop aria2c init),
tests under `android/app/src/test/`, and write `briefs/phase12-d-android-speed.result.md`. No desktop, no commit/push/sudo,
no emulator. Gradle: `JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --offline --no-daemon --max-workers=1
-Dorg.gradle.jvmargs=-Xmx1g ...`; one job at a time.

## Build
1. **Extract once (12B Android).** In `DownloadQueue`, keep the probe's info JSON for the attempt (never in history), write it
   to the item's temp dir (private, no world access) and have `YtDlpCommands` pass `--load-info-json <file>` without the URL
   when usable: a JSON object, not a playlist/tray, has `formats` or `url`, probe younger than 300 s; one immediate URL
   re-run (not a retry, no backoff) on 403/410/format-unavailable or a failure before the first progress line; delete the file
   after. With reuse off, the argv must equal today's (test). Media-engine items never use it.
2. **Audio presets copy** exactly like desktop: M4A `bestaudio[ext=m4a]/bestaudio/best`, Opus
   `bestaudio[acodec=opus]/bestaudio/best` (keep `-x --audio-format`); update the argument pins in `YtDlpCommandsTest.kt`.
3. **Setting "Faster downloads: Auto / Off"** (data + a row in Settings > Downloads, default Auto, plain helper text as
   desktop), wired to reuse. First 429 for a site in a session: that site stops reusing the probe and runs 1 at a time for the
   session (pure function + test).
4. **Locks.** While at least one download is running: a high-performance Wi-Fi lock and a partial wake lock held by the
   foreground service, released as soon as it goes idle, on error, and on service destroy (test the pure acquire/release
   decision; the lock objects behind a small interface). Do not add permissions beyond WAKE_LOCK/CHANGE_WIFI_STATE
   if already declared; if a new manifest permission is needed, say so in the result and add only that.
5. **aria2c: remove it.** The benchmark found no case for it. Remove the aria2c module dependency and its init so the APK
   shrinks; keep everything compiling. If removal breaks the build offline or at runtime wiring, revert that part and say
   exactly why instead of leaving it broken.
6. **Feel (12E).** Same as desktop: instant card with the host as title, thumbnail fetched alongside the probe (the 10E
   loader), smoothed ETA (EMA alpha about 0.2, ignore the first 2 s), "Starting..." with a reason after 10 s of no progress
   ("Signing in", "Waiting for Wi-Fi", "Rate limited, waiting"), carousel `files_done` updating per file. Pure functions with
   JVM tests; keep every content description and the "N percent" TalkBack text.
7. **MediaStore copy speed:** inspect the staging -> MediaStore copy; if it uses a small buffer, use a 1 MiB buffer. No
   measuring possible without a device: say so.

## Acceptance (paste real output)
```
cd android && JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest :app:assembleDebug
```
List "Not verified on a device": locks, the speed effect, the APK size change (report the debug APK sizes before and after if
you can build both cheaply; otherwise the size of the removed module). Write the result file even if low on budget. Keep
spend low and do not end your turn while Gradle is running.
