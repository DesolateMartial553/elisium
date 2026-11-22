# Brief 10A - Android media engine spike (photos, carousels, music, stories, TikTok slideshows)

Plan: `~/.claude/plans/elisium-posts-images-music-stories.md` (read it). Read `AGENTS.md` and `core-spec/SPEC.md` first.
Edit only under `android/app/src/main/java/com/desolate/elisium/media/` (new package),
`android/app/src/test/java/com/desolate/elisium/media/` (new), `android/app/src/test/resources/media/` (new fixtures),
and write `briefs/phase10-a-android-media-spike.result.md`. No other files. No commit, no push, no emulator, no network
calls at all (not even in tests), no sudo.

## Why
yt-dlp cannot save images. Desktop will use the system `gallery-dl` binary as a separate process. On Android, bundling
gallery-dl is a licence problem (gallery-dl is GPL-2.0-only, Elisium is GPL-3.0), so the expected Android route is
**our own small Kotlin client**. This spike proves (or disproves) that route offline. Do NOT copy or paraphrase any
gallery-dl code. Public JSON field names are facts and may be used.

## Part 1 - findings (write them in the result file)
1. Inspect the youtubedl-android 0.18.1 AARs in the gradle cache
   (`~/.gradle/caches/modules-2/files-2.1/io.github.junkfood02.youtubedl-android/`, library/common/ffmpeg/aria2c):
   list what the bundled Python ships (is `requests`/`certifi` present? which Python version?), and whether a JavaScript
   runtime (deno/node/quickjs) is bundled. Use `unzip -l` / reading only; do not modify the cache.
2. Note how ffmpeg is invoked through the library (class/method names) so 10D can build the photo+music mp4 with it.
3. A short licence note: why route (c) (own Kotlin client) avoids the GPL-2.0-only issue.

## Part 2 - Kotlin prototype (pure JVM, no Android APIs, so it carries into 10D)
Package `com.desolate.elisium.media`:
- `MediaItem` (kind = IMAGE | VIDEO | AUDIO, url, width?, height?, index (1-based slide number), mediaId, ext guess),
  `MediaPost` (site, shortcode/id, owner username, takenAt, caption?, items: List<MediaItem>, music: MusicClip?),
  `MusicClip` (url, title?, artist?, startMs?, durationMs?).
- `InstagramParser`: parse a media-info JSON object (the shape `api/v1/media/{id}/info/` returns: `items[0]` with
  `media_type` 1=image 2=video 8=carousel, `carousel_media[]`, `image_versions2.candidates[]` (pick the largest),
  `video_versions[]` (pick the largest), `user.username`, `code`, `taken_at`, `caption.text`, and music from
  `music_metadata.music_info.music_asset_info` (`progressive_download_url`, `title`, `display_artist`, `id`) plus
  `music_metadata.music_info.music_consumption_info` / asset `highlight_start_times_in_ms` and `duration_in_ms` for
  the snippet when present). Also parse a stories tray (`reels_media[]` / `reels{}` -> `items[]`, including
  `story_music_stickers[].music_asset_info`).
- `TikTokParser`: parse a TikTok item JSON with `imagePost.images[].imageURL.urlList[]`, `imageWidth/imageHeight`,
  `music.playUrl`, `music.title`, `music.authorName`, `id`, `author.uniqueId`, `createTime`, `desc`.
- `ShortcodeId`: Instagram shortcode <-> numeric media id conversion (base64-url alphabet), with tests.
- `MediaUrls`: classify an input URL into post / reel / stories-user / story-item / highlight / tiktok-photo / unknown
  (reuse nothing from engine/UrlNorm.kt by editing it; you may call it read-only).
- Archive keys: `instagram <mediaId>` per slide, `instagram <shortcode>_mix` for the built mp4,
  `tiktok <id>_<n>` per photo, `tiktok <id>_mix`.
- Missing fields never crash: return a typed error (`NoMedia`, `LoginRequired`, `Unknown`).

## Tests (JVM, offline)
Hand-written fixture JSON files under `src/test/resources/media/` (made-up ids and example.com/cdn URLs, no real
account data): single image, single video, carousel mixed (3 slides: image, video, image), image with music
(with and without snippet times), stories tray with a music sticker, TikTok photo slideshow with music, malformed
and empty responses. Plus ShortcodeId round-trips and MediaUrls classification. Keep all existing tests passing.

## Acceptance (paste real output)
```
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug
```
First build may be OOM-killed; retry once. End the result file with a recommendation: route (c) yes/no, what 10D still
needs (network client with cookies.txt, ffmpeg mux, MediaStore writes), and any risk found. Write the result file even if
you run low on budget.
