# Brief 10A result - Android media engine spike

Status: done. Route (c) - our own small Kotlin client - is the recommendation.
No commit, no push, no emulator, no `sudo`. The prototype is pure JVM (no Android APIs).

## Files changed

New, and nothing else in `android/`:

Main (`android/app/src/main/java/com/desolate/elisium/media/`):

- `MediaModels.kt` - `MediaKind`, `MediaItem`, `MusicClip`, `MediaPost`, `MediaError`, `MediaResult`, `MediaSites`
- `MediaJson.kt` - tolerant JSON accessors, `parseJsonObject`, `guessExt`
- `InstagramParser.kt` - `parseMediaInfo`, `parseStoriesTray`
- `TikTokParser.kt` - `parseItem`
- `ShortcodeId.kt` - shortcode <-> numeric media id
- `MediaUrls.kt` - `classifyMediaUrl`, `MediaUrl`, `MediaUrlKind`
- `MediaKeys.kt` - the four archive keys

Tests (`android/app/src/test/java/com/desolate/elisium/media/`):

- `InstagramParserTest.kt` (15), `TikTokParserTest.kt` (5), `ShortcodeIdTest.kt` (5),
  `MediaUrlsTest.kt` (6), `MediaKeysTest.kt` (4)

Fixtures (`android/app/src/test/resources/media/`, made-up ids, `cdn.example.com` URLs):

- `instagram_single_image.json`, `instagram_single_video.json`, `instagram_carousel_mixed.json`,
  `instagram_image_with_music.json`, `instagram_image_with_music_no_snippet.json`,
  `instagram_stories_tray.json`, `instagram_login_required.json`, `instagram_malformed.json`,
  `instagram_empty.json`, `tiktok_photo_slideshow.json`, `tiktok_video_item.json`

`core-spec/SPEC.md`, `engine/UrlNorm.kt` and every other file were read only (UrlNorm's
`normalizeUrl` / `siteKind` are called from `MediaUrls`, not edited).

## Part 1 - findings

### 1. What the bundled Python ships (youtubedl-android 0.18.1)

Inspected with `unzip -l` / `unzip -p` only; the Gradle cache was not modified.

`library-0.18.1.aar` contains `res/raw/ytdlp` (yt-dlp **2025.11.12** zipapp, 3,170,726 bytes),
`jni/<abi>/libpython.so` (loader), `jni/<abi>/libpython.zip.so` (Python + stdlib) and
`jni/<abi>/libqjs.so` (QuickJS).

From `libpython.zip.so` (arm64, 1007 entries):

- **Python 3.12** - `usr/lib/python3.12/`, `_sysconfigdata__linux_.py` has `'LDVERSION': '3.12'`.
- `site-packages` contains **only `Cryptodome` (3.6 MB) and `mutagen` (696 KB)**.
- **No `requests`, no `certifi`, no `urllib3`, no `charset_normalizer`, no `idna`** (grep of the
  full zip listing). gallery-dl's hard dependency chain is therefore missing.
- `ssl`/`http.client` and a CA bundle are present: `<packages>/python/usr/etc/tls/cert.pem`,
  handed to yt-dlp as `SSL_CERT_FILE`.
- A JavaScript runtime **is** bundled: **QuickJS**, not deno/node. `YoutubeDL` adds
  `--js-runtimes quickjs:<nativeLibraryDir>/libqjs.so` to every request.

So route (a) would need gallery-dl **plus** requests + urllib3 + certifi + charset_normalizer +
idna vendored into that zip (all pure Python, so possible), on top of the licence problem below.
Route (b) (Chaquopy) would add a second Python runtime next to this one.

### 2. How ffmpeg is invoked through the library

`com.yausername.ffmpeg.FFmpeg` has exactly two public members: `getInstance()` and
`init(Context)`. It unpacks `libffmpeg.zip.so` into
`getNoBackupFilesDir()/youtubedl-android/packages/ffmpeg`. `YoutubeDL.init(Context)` sets

- `ffmpegPath = File(applicationInfo.nativeLibraryDir, "libffmpeg.so")`,
- `LD_LIBRARY_PATH = <packages>/python/usr/lib:<packages>/ffmpeg/usr/lib:<packages>/aria2c/usr/lib`,

and appends `--ffmpeg-location <ffmpegPath>` to every yt-dlp request. `libffmpeg.so` and
`libffprobe.so` are **PIE executables** (ELF aarch64, interpreter `/system/bin/linker64`, NDK r28c,
Android 24), so 10D can run them directly:

```kotlin
ProcessBuilder(nativeLibraryDir + "/libffmpeg.so", "-y", ...)
    .apply { environment()["LD_LIBRARY_PATH"] = ldLibraryPath }
```

The app already calls `FFmpeg.getInstance().init(this@ElisiumApp)` (`ElisiumApp.kt`), so the libs
are unpacked. Bundled FFmpeg is 7.1 (libavcodec 61.19.101). The ffmpeg AAR is 141 MB across four
ABIs; the app ships `arm64-v8a` only.

### 3. Licence note

gallery-dl is **GPL-2.0-only**; Elisium is **GPL-3.0**. GPLv2-only code cannot be combined with
GPLv3 code into one work (the "or later" upgrade path does not exist for "-only"), so bundling
gallery-dl in the APK is a real conflict, not a grey area. Running the system `gallery-dl` binary
as a **separate process** on desktop is separate programs communicating at arm's length, which is
fine and needs no code from it. Route (c) avoids the issue completely: `MediaItem` / `MediaPost`
are our classes, and only public JSON **field names** (facts, not expression) are used. No
gallery-dl source was read, copied or paraphrased.

## Part 2 - Kotlin prototype

- Model: `MediaItem(kind, url, width?, height?, index 1-based, mediaId, ext)`,
  `MediaPost(site, id, owner?, takenAt? epoch seconds, caption?, items, music?)`,
  `MusicClip(url, title?, artist?, startMs?, durationMs?)`.
- `InstagramParser.parseMediaInfo`: `items[0]`, `media_type` 1/2/8, `carousel_media[]` in order,
  largest `image_versions2.candidates[]` / `video_versions[]` by pixel area, `user.username`,
  `code`, `taken_at`, `caption.text`, music from
  `music_metadata.music_info.music_asset_info` (`progressive_download_url`, `title`,
  `display_artist`) and the snippet from `music_consumption_info`
  (`highlight_start_times_in_ms[0]`, `duration_in_ms`, falling back to the asset's own times).
- `InstagramParser.parseStoriesTray`: `reels_media[]` or the `reels{}` map, each reel's `items[]`
  becomes one `MediaPost` (one queue item per story), with
  `story_music_stickers[].music_asset_info`.
- `TikTokParser.parseItem`: `imagePost.images[].imageURL.urlList[0]`, `imageWidth/imageHeight`,
  `music.playUrl/title/authorName`, `id`, `author.uniqueId`, `createTime`, `desc`; a video item is
  `NoMedia` so it stays with yt-dlp.
- `ShortcodeId`: base64-url alphabet, `BigInteger` (media ids exceed signed Long). Verified
  independently in Python: `1234567890123456789` <-> `BEiEPR96YEV`.
- `classifyMediaUrl`: POST (`/p/`, `/tv/`), REEL, STORIES_USER, STORY_ITEM, HIGHLIGHT,
  TIKTOK_PHOTO, else UNKNOWN (including profiles, `/reels/<user>/`, video links and `vm.tiktok.com`
  short links that would need a network redirect). Uses `normalizeUrl` read-only, so tracking
  parameters and `www.`/`m.` hosts behave exactly as for queue dedupe.
- `MediaKeys`: `instagram <mediaId>`, `instagram <shortcode>_mix`, `tiktok <id>_<n>`,
  `tiktok <id>_mix` (returned as `(extractor, id)` pairs for the existing `Archive`).
- Missing fields never throw: a bad slide is skipped, an unusable post is `NoMedia`, a sign-in
  wall is `LoginRequired`, anything unrecognised is `Unknown`.

## Commands run

All from `android/` with `JAVA_HOME=/usr/lib/jvm/java-21-openjdk`, `nice`, and the brief's flags.

1. `:app:testDebugUnitTest --offline` - **failed at configuration**, before compiling anything:
   `Could not resolve org.jetbrains.kotlin:kotlin-reflect:2.4.21 ... No cached version ... available
   for offline mode.` This is a hole in the local Gradle cache (Gradle 9.9.0, unrelated to this
   brief: the last build here was Gradle 9.8.2 on 2026-11-15). I ran the same task **once without
   `--offline`** so Gradle could fetch that one build-tool artifact; it then failed on a missing
   `contentOrNull` import in `TikTokParser.kt`, which I fixed. The acceptance commands below were
   then run with `--offline` exactly as written.
2. `nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest`

   ```
   > Task :app:testDebugUnitTest

   BUILD SUCCESSFUL in 1m 14s
   27 actionable tasks: 3 executed, 24 up-to-date
   ```

   Test XML totals: `tests=457 failures=0 errors=0 skipped=0` (the 35 new media tests:
   InstagramParser 15, MediaUrls 6, ShortcodeId 5, TikTokParser 5, MediaKeys 4). One earlier run
   had a failing assertion of mine (`{}` for TikTok expected `NoMedia`; the parser correctly says
   `Unknown` because there is no `id`) - the expectation was wrong, the parser was not.
3. `nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug`

   ```
   > Task :app:lintDebug

   BUILD SUCCESSFUL in 5m 22s
   28 actionable tasks: 9 executed, 19 up-to-date
   ```

   SARIF report: 12 results, **0 errors**, 12 warnings, **none in `media/`** (they are the existing
   `DownloadService` InlinedApi, `OldTargetApi`, `ChromeOsAbiSupport`, `PluralsCandidate`,
   `ObsoleteSdkInt`, `TypographyEllipsis`, two `UseKtx`, `UsableSpace`, plus one obsolete lint
   check and the manifest `extractNativeLibs` note).

## Notes / unfinished

- APK size delta for route (c): **no new dependency and no native payload** - `kotlinx-serialization-json`
  is already linked and the HTTP client would be the platform's `HttpURLConnection`. The seven new
  classes compile to 132 KB of unminified debug `.class` files (R8 in a release build shrinks that
  a lot). The current debug APK is 75,078,152 bytes (arm64 only). No `assembleDebug` was run, as it
  is not in this brief's acceptance.
- Not wired into the app yet: no network client, no UI, no download loop - by design.
- Unrelated working-tree changes appeared during this session and were left alone: `.gitignore`
  (a `.taste-skill/` line), `.taste-skill/`, `design/nightshelf/`, `AGENTS.md` (the owner's
  Night shelf design decision, which does not touch this non-UI brief) and `HANDOFF.md`. Another
  process was writing in this repo; none of those are mine.

## Recommendation

**Route (c): yes.** The bundled Python cannot run gallery-dl as shipped (no requests/certifi), and
bundling gallery-dl at all conflicts with the GPL-3.0 licence. A small Kotlin client parses the
same public JSON, adds no dependency or native payload, and the whole parse layer is already
tested offline.

What 10D still needs:

1. A network client (no new dependency): `HttpURLConnection` with the Netscape `cookies.txt` from
   `settings/CookiesFile` as a `Cookie` header, a browser User-Agent, `X-IG-App-ID` for Instagram,
   shortcode -> media id via `ShortcodeId`, then `api/v1/media/{id}/info/` (and `feed/reels_media/`
   for trays/highlights). Never log the cookie header.
2. An ffmpeg mux using `<nativeLibraryDir>/libffmpeg.so` with the library's `LD_LIBRARY_PATH`:
   `-loop 1 -t 3` per image (whole snippet for a single photo), videos joined in order, audio
   `-ss startMs/1000 -t durationMs/1000` (stream copy when possible), `libx264`/`yuv420p`/`aac`,
   `-shortest`. Archive it as `<shortcode>_mix` / `<id>_mix`.
3. MediaStore writes through the existing `storage/MediaStoreOutputStore.kt` (it takes a finished
   file; stage in app-private storage first), plus the per-slide keys from `MediaKeys`.
4. SPEC error mapping on top of `MediaError` (`no_media`, `login_required` -> `session_expired`
   when cookies are configured, `rate_limited`).

Risks found: these are private endpoints - field names and required headers can change without
notice, and heavy use can rate-limit or flag a signed-in account (10G's slow mode applies). The
music snippet shape differs between posts (`music_metadata`) and stories (`story_music_stickers`);
the parser tolerates both, but 10D should re-check against live responses before release.
