# Brief 10D - Android media engine: photo posts, carousels, stories, TikTok slideshows, song, mix video

Plan: `~/.claude/plans/elisium-posts-images-music-stories.md` (read the Android and "Owner decisions" parts). Read `AGENTS.md`,
`core-spec/SPEC.md`, `briefs/phase10-a-android-media-spike.result.md` (the design and the parsers already written: use them),
and, as the behaviour to mirror 1:1, the desktop results `briefs/phase10-b1-desktop-media-engine.result.md`,
`briefs/phase10-b2-desktop-music-mix.result.md`, `briefs/phase10-c-desktop-multifile-screens.result.md`.
Edit only under `android/app/src/main/java/com/desolate/elisium/` (`media/`, `engine/`, `service/`, `backend/`, `settings/`,
`data/` additions), their tests under `android/app/src/test/`, and write `briefs/phase10-d-android-media-engine.result.md`.
No UI files (10E), no desktop, no commit/push, no sudo. Do NOT bundle or call gallery-dl on Android (licence): our own Kotlin
client only. No emulator. Gradle: `nice ./gradlew --offline --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest`
(one Gradle job at a time; it is slow, run it in the foreground with a long timeout and report only after its final line).

## Build (mirror the desktop behaviour and wording)
1. **HTTP client for Instagram/TikTok** (OkHttp or `HttpURLConnection`, whatever the project already depends on; no new
   dependency without saying so): fetch the post JSON with the stored session cookies (never logged), feed the 10A parsers,
   return a `MediaPost` (items with kind/url/ext/id/slide, music clip with snippet start/length, owner, id, date, title).
   Map failures to the same error codes as desktop (login required / session_expired / rate limit / unavailable /
   `story_expired` / `private_account`, plus `no_media`), same plain-words text as SPEC and desktop `errors.py`.
2. **Routing** in `DownloadQueue`: reels/videos stay on yt-dlp exactly as today; `/stories/...`, highlights and TikTok
   `/photo/` go to the media engine; Instagram `/p/` tries yt-dlp first and on `no_media` retries once with the media engine
   (not counted as a retry). Port the desktop's rules, including the archive keys (`MediaKeys.kt`) and "existing name is
   skipped, never renamed".
3. **Download** each file into the item's staging folder with the existing downloader utilities (progress = files_done /
   files_total, pause/cancel/resume like other items, resumes skip finished files by archive key), then move to the output
   folder under an owner subfolder with the desktop's naming (`<owner> <date> <shortcode> [<media id>] <n>.<ext>`).
4. **Song snippet and mix video via ffmpeg** run as a process from `nativeLibraryDir/libffmpeg.so` with `LD_LIBRARY_PATH`
   (see the 10A result, part 1.2): cut the snippet (`-ss -t -c copy`, AAC re-encode retry), build `<base> [<id>_mix].mp4` with
   the same canvas/duration/min-2-s/`out_range=tv` rules as desktop `mix.py` (port its pure functions and their test cases),
   respecting the settings below. ffmpeg missing or failing never fails the item: done with the same note text as desktop.
5. **Settings** (data layer only, UI is 10E): "photo posts with a song" (photos+song+video default / photos+song / photos only),
   "song length" (snippet default / full), stored like the other settings; wired to the plan.
6. **Force re-add** ("Download again anyway"): a queue add flag that ignores the media archive for that run, like desktop;
   "Already saved" note when nothing is missing.
7. **Snapshot fields** the UI will read in 10E: `thumbnail`, `format_label`, `files_done`, `files_total`, `note`; history
   gets `note` and `files_total` columns with a Room migration (add and test it) tolerant of old rows.

## Tests (JVM, offline, fixtures from 10A; fake HTTP client)
Routing table per URL kind; `/p/` no_media fallback; progress counts; archive skip on re-add; force re-add; every error
mapping; snippet/mix argv pure functions (all desktop cases); each setting combination; ffmpeg missing -> done with note;
Room migration test if the project has migration tests (otherwise a schema/version test); all existing tests still pass.

## Acceptance (paste real output)
```
cd android && nice ./gradlew --offline --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
```
List under "Needs a live check": real Instagram/TikTok JSON shapes, signed-in stories, ffmpeg on a device. Write the result
file even if low on budget. Do not end your turn while a Gradle run is going.
