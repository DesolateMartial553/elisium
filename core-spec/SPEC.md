# Elisium - core spec (both apps follow this)

## Queue item states
`queued -> probing -> downloading -> merging -> converting -> done`
Terminal states: `done`, `failed`, `skipped`, `cancelled`. Also `paused` (resumable). Stages merging/converting are shown separately from downloading. `converting` is also the stage in which a photo post's photos and its song are turned into one video (see Photo posts).

## Queue rules
- Concurrency 1-5 (default 2). Extra items wait as `queued`.
- Pause kills the yt-dlp process but keeps `.part` files; resume reruns with `--continue`.
- Retry with backoff on network errors: wait 5s, 15s, 45s, then `failed`.
- Settings: speed limit (`--limit-rate`), schedule window (hold items outside it).
- Progress comes from `--progress-template` JSON lines. Never scrape text output.

## No duplicates (4 layers)
1. `--download-archive <data>/archive.txt` (video id).
2. Filename template `%(title).150B [%(id)s].%(ext)s` plus `--no-overwrites`.
3. URL normaliser: same video from `youtu.be/ID`, `youtube.com/watch?v=ID`, `/shorts/ID`, `m.` host, with or without tracking params (`si`, `utm_*`, `feature`, `t` kept only if a start time) is ONE queue item. Unknown sites: strip fragments and `utm_*`, keep the rest.
4. Android only: query MediaStore for an existing name before insert (see Android phase).
- Reconcile: before skipping because of the archive, check the file still exists in the output folder. If it was deleted, remove that id from the archive and download again.
- Photo posts, carousels, stories and TikTok slideshows have their own archive, one key per file. Desktop: gallery-dl's SQLite archive `~/.local/share/elisium/gallery-archive.sqlite3` (gallery-dl's own ids; Elisium cannot reconcile it with deleted files, so "Download again anyway" re-runs without it). Android: `media-archive.txt` beside `archive.txt`, keys `instagram <media id>`, `tiktok <id>_<n>`, song `<site> <post>_song`, mix `<site> <post>_mix`. The built mp4 is marked `[<post id>_mix]` in its file name; if that name is already in the owner's folder it is not rebuilt.
- Same video, different quality: default skip with a "Download again anyway" action. Setting: skip | replace | keep both. Force re-add: "Download again anyway" (History's "Download again") adds the link again past the archive. For photo posts the app first checks the owner's folder: if every file is already there the item is `skipped` with the note "Already saved".

## Output location
- Desktop: final files go to `~/Downloads/Elisium/` (use `xdg-user-dir DOWNLOAD`, fall back to `~/Downloads`). yt-dlp flags: `-P home:<that>` and `-P temp:<cache>/tmp`, so the output folder holds only finished files, never `.part`.
- Android: stage in app-private storage, move finished file to `Download/Elisium/` via MediaStore.
- Photo posts, carousels, stories and slideshows go to one folder per owner: `<output>/<owner>/` (desktop) and `Download/Elisium/<owner>/` (Android). The owner name is sanitised (no `/`, `\`, control characters, leading dots or `..`); with no owner the files go in the output root. An existing name is skipped, never renamed or overwritten. Files that finished before a failure, pause or restart are kept, so a retry fetches only what is missing.

## Data locations (desktop)
- Config `~/.config/elisium/`, data `~/.local/share/elisium/` (history.sqlite, archive.txt), cache `~/.cache/elisium/`.

## Format presets
Best video, 1080p, 720p, Audio only (mp3, m4a, opus, flac), Smallest file. Default selector `bestvideo*+bestaudio/best`.

## Sign-in (cookies)
Some sites need a signed-in session (Instagram stories, private posts, some reels). Settings > Accounts offers one browser (`--cookies-from-browser firefox|chrome|chromium|brave|edge|vivaldi|opera`, default off) or an optional `cookies.txt` file; the browser wins when both are set. The app never asks for a password, never copies the cookie contents anywhere, and keeps only the browser name / file path in settings - never in history. yt-dlp and gallery-dl are handed the file path (or the browser name). The one exception: the Android media client reads `cookies.txt` in-process, only to build its request headers; it never logs or stores the contents. Instagram story trays (`/stories/<user>/`, `/stories/highlights/<id>/`) are playlists; a story URL with its own id is one item.

**Android sign-in (phase 9):** no browser cookies exist on a phone, so Settings > Accounts has "Sign in to Instagram": a WebView on Instagram's own login page. The app never sees the password; it only watches its cookie store, and once a `sessionid` cookie appears it writes a Netscape `cookies.txt` (`.instagram.com`, one-year expiry) into app-private storage, then wipes the WebView's cookies, storage and cache. Navigation is limited to https on instagram.com / facebook.com / fbcdn.net. "Sign out" deletes the file. Importing a `cookies.txt` stays as an Advanced fallback. Cookies are never in backups.

**Desktop sign-in (phase 9):** Elisium looks (read-only, names and hosts only, never values) for a browser that already holds an Instagram `sessionid` and offers it in one click; a failed item's "Sign in..." opens a dialog that picks it and retries the items that failed for a sign-in reason. Cookie flags are still passed for every site (the YouTube "not a bot" fix needs them).

**yt-dlp updates (Android):** at most once per 24 h at startup, only when no download is active and the Wi-Fi-only gate allows it, plus an "Update yt-dlp" button in Settings. The time of every attempt is stored so a failing update is not retried on every launch.

## Plain-language errors (raw log kept under Details)
| yt-dlp text contains | Message | Suggested fix |
|---|---|---|
| `Sign in to confirm` / `not a bot` | The site wants you to be signed in. | Import cookies |
| `Video unavailable` / `Private video` | This video is not available. | Check the link |
| `Requested format is not available` | That quality isn't offered for this video. | Pick another format |
| `HTTP Error 403` | The site refused the download. | Update yt-dlp, or import cookies |
| `HTTP Error 429` | Too many requests. | Wait, lower concurrency |
| `Unable to download` / timeout / connection | Network problem. | Retry (auto-retry already ran) |
| `ffmpeg` not found | ffmpeg is missing. | Install ffmpeg |
| Instagram `You need to log in to access this content` (stories, private posts) | Instagram needs you signed in. | Choose a browser in Settings > Accounts |
| Instagram `Please wait a few minutes` | Instagram is limiting requests. Wait a few minutes and try again. | Wait a few minutes and try again |
| Instagram `There is no video in this post` / `Instagram sent an empty media response` | This post has no video to download. | Check the link |
| `HTTP Error 401` | The site refused to let Elisium in. | Sign in, then try again |
| Instagram login-required text while cookies ARE configured | Your Instagram sign-in has expired. | Sign in again (Android: Settings > Accounts; desktop: choose your browser again) |
| `could not find ... cookies database` / `Failed to decrypt` | Elisium could not read that browser's cookies. Close the browser or pick another. | Close the browser, or choose another browser in Settings |
| anything else | Download failed. | See Details |

The Instagram rows name Instagram only for Instagram URLs (or when no URL is known); for any other site the same codes use "The site wants you to be signed in." / "The site is limiting requests. Wait a few minutes and try again.". Android's `http_403` fix is "Update yt-dlp in Settings, or sign in".

## Photo posts, carousels, stories, TikTok slideshows (phase 10)
Routing by URL (`media.route_for` on desktop, the same rules in the Kotlin media client on Android):
| URL | Engine |
|---|---|
| Instagram `/stories/<user>/` (tray), `/stories/highlights/<id>/`, TikTok `/@user/photo/<id>` | media engine only (gallery-dl on desktop, own Kotlin client on Android) |
| Instagram `/p/<code>`, `/tv/<code>`, a single `/stories/<user>/<id>/` | yt-dlp first; if it fails with `no_media` (at probe or at download time) the same attempt re-runs once on the media engine; no retry is counted and nothing waits |
| reels, TikTok videos, YouTube, everything else | yt-dlp, unchanged |

A post is one card. While the link is being looked up the card says "Looking up the post...". Snapshots carry `files_done` / `files_total` (null for plain yt-dlp items); `percent = files_done / files_total * 100`. A carousel counts per saved file. Also on the snapshot: `thumbnail` (http/https only, display only, never in history), `format_label` (for example "1080p MP4", "MP3 audio", "6 photos + song") and `note` (one plain sentence, stored in history together with `files_total`).

**Song and photos+song video** (single posts only: `/p/`, `/tv/`, one story, one TikTok `/photo/`; never a tray or highlight, and nothing when the post holds several audio files). The song is cut to the snippet the post plays (start and length from the post's metadata); the video is H.264 yuv420p 30 fps with AAC audio, 1080x1920 (portrait majority) or 1920x1080, each photo shown for `snippet / photo count` (at least 2 s), carousel videos kept in slide order with the song replacing their own sound. The item goes `downloading -> converting -> done`; `files_total` includes the video while one is expected. Making the video never fails the item. Notes: "Kept the full song: the post doesn't say which part it plays." / "Kept the full song: it couldn't be trimmed." / "Saved the photos and the song; the video couldn't be made." / "Already saved".
Settings > Photos and music (both apps): *Photos, song and video* (default) | *Photos and song only* | *Photos only*, and *Post's snippet* (default) | *Full song*.

New error codes (desktop wording; Android uses the same codes except `gallery_dl_missing`, which it has no use for, and keeps its own wording where it differs):
| Code | When | Message | Suggested fix |
|---|---|---|---|
| `gallery_dl_missing` | gallery-dl not on PATH (desktop) | Photo downloads need gallery-dl. Install it: sudo pacman -S gallery-dl | Install gallery-dl |
| `story_expired` | story gone, empty story tray, or 404 on a single story link | This story has expired. Stories last 24 hours. | Check the link |
| `private_account` | private-account text from the engine | This account is private. Follow it in your browser, then sign in here. | Follow the account in your browser, then sign in in Settings > Accounts |
| `no_media` (fallback) | the media engine ran and found nothing to save | There are no photos or videos to download here. | Check the link |
Login wall -> `login_required` (or `session_expired` when cookies are configured); `429` -> `rate_limited`; `404` -> `video_unavailable`.

## Faster downloads (phase 12)
- Settings > Downloads > "Faster downloads": **Auto** (default) | **Off**. Auto looks a link up once and reuses that lookup for the download (`--load-info-json`; if the reused media address has gone stale, one immediate re-run from the link). Off gives the plain command (look up again at download time). Never reused for media-engine links or signed-in Instagram/TikTok.
- Audio presets copy the native stream when the site offers one (m4a, opus) instead of re-encoding.
- 429 rail: after the first `429` / "please wait" from a site, that site no longer reuses the lookup and runs one download at a time; other sites are unaffected. Waiting rows show "Rate limited, waiting".
- Feel: a queued link shows its host as the title straight away; speed is smoothed (exponential average, ignoring the first 2 s of a file) so the time left does not jump; a download with no progress for 10 s says "Starting... <reason>" ("Signing in", "Waiting for the network", "Rate limited, waiting").
- No aria2c, no multi-connection flags: measured no gain on long videos (see `briefs/phase12-a-bench.result.md`).

## Accessibility (every UI)
Every control has an accessible name; status is never colour-only (icon + text); full keyboard path; text scales to 200%; reduced-motion respected; progress announced at coarse steps (25% or completion).
