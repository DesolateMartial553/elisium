# Elisium - core spec (both apps follow this)

## Queue item states
`queued -> probing -> downloading -> merging -> converting -> done`
Terminal states: `done`, `failed`, `skipped`, `cancelled`. Also `paused` (resumable). Stages merging/converting are shown separately from downloading.

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
- Same video, different quality: default skip with a "Download again anyway" action. Setting: skip | replace | keep both.

## Output location
- Desktop: final files go to `~/Downloads/Elisium/` (use `xdg-user-dir DOWNLOAD`, fall back to `~/Downloads`). yt-dlp flags: `-P home:<that>` and `-P temp:<cache>/tmp`, so the output folder holds only finished files, never `.part`.
- Android: stage in app-private storage, move finished file to `Download/Elisium/` via MediaStore.

## Data locations (desktop)
- Config `~/.config/elisium/`, data `~/.local/share/elisium/` (history.sqlite, archive.txt), cache `~/.cache/elisium/`.

## Format presets
Best video, 1080p, 720p, Audio only (mp3, m4a, opus, flac), Smallest file. Default selector `bestvideo*+bestaudio/best`.

## Sign-in (cookies)
Some sites need a signed-in session (Instagram stories, private posts, some reels). Settings > Accounts offers one browser (`--cookies-from-browser firefox|chrome|chromium|brave|edge|vivaldi|opera`, default off) or an optional `cookies.txt` file; the browser wins when both are set. The app never asks for a password, never reads or copies the cookie contents, and keeps only the browser name / file path in settings - never in history. Instagram story trays (`/stories/<user>/`, `/stories/highlights/<id>/`) are playlists; a story URL with its own id is one item.

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
| `could not find ... cookies database` / `Failed to decrypt` | Elisium could not read that browser's cookies. Close the browser or pick another. | Close the browser, or choose another browser in Settings |
| anything else | Download failed. | See Details |

## Accessibility (every UI)
Every control has an accessible name; status is never colour-only (icon + text); full keyboard path; text scales to 200%; reduced-motion respected; progress announced at coarse steps (25% or completion).
