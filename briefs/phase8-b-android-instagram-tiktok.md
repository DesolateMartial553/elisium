# Brief 8B - Instagram + TikTok videos and stories (Android)

Read `AGENTS.md`, `core-spec/SPEC.md`, `briefs/phase8-a-desktop-instagram-tiktok.result.md` (the desktop version: mirror its behaviour, URL rules and error wording exactly), then the Kotlin engine under `android/app/src/main/java/com/desolate/elisium/` (UrlNorm, Errors, DownloadQueue, backend, Settings screen). Edit only under `android/` and write `briefs/phase8-b-android-instagram-tiktok.result.md`. No desktop/design edits, no commit/push, no emulator/adb.

## Build
1. **Cookies import** (no browser access on Android): Settings > Accounts > "Import cookies.txt" using the system document picker (`ActivityResultContracts.OpenDocument`, no storage permission). Validate it looks like a Netscape cookie file (header line or tab-separated 7-field rows), copy into app-private `filesDir/cookies/cookies.txt`, show "Imported (N cookies)" and a "Remove" button. Never log contents. Confirm `android:allowBackup="false"` (and `dataExtractionRules`/`fullBackupContent` exclude it) so cookies never leave the device in backups.
2. **Engine**: pass `--cookies <path>` in the youtubedl-android request for downloads and probes when the file exists.
3. **Stories/highlights as multi-item**, **UrlNorm** rules, **video_key**, and **Errors** wording: port 1:1 from the desktop brief (items 3, 4, 5), including the sign-in error action jumping to Settings > Accounts.
4. Share intake: Instagram/TikTok share-sheet text often contains extra words around the URL; make sure the first http(s) URL is extracted (test it).
5. Short help text under the import button: how to export (a cookies.txt browser extension on desktop, then copy to the phone). Keep Afterglow, TalkBack labels, reduced motion.

## Tests (JVM, no network)
UrlNorm cases mirroring desktop; classification of story/highlight URLs; error mapping; cookies validation pure function (valid, empty, wrong format, HTML file); settings store; share-text URL extraction. Keep all 327 existing tests.

## Acceptance (paste real output)
```
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:assembleDebug
```
Zero lint errors; first build may be OOM-killed, retry. List "Needs a real phone" items. Write the result file even if low on budget.
