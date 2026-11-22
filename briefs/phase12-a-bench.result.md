# Brief 12A result - desktop speed benchmark (Claude, 2026-11-22)

Tool: `tools/bench.py` (not in pytest; needs the network). It runs the app's real probe + `build_command` per URL,
fresh temp folder and archive per run, configs alternated per round. Preset 720p, 2 rounds, medians.
Machine: 2 cores; yt-dlp 2026.10.26 with deno. Line speed seen: about 7-10 MB/s (60-80 Mbit/s) on YouTube.


| URL | config | start s | (probe s) | transfer s | post s | total s | MB | MB/s | failures |
|---|---|---|---|---|---|---|---|---|---|
| https://www.youtube.com/watch?v=jNQXAC9IVRw | base | 12.4 | 6.6 | 0.4 | 0.5 | 13.3 | 0.5 | 1.42 | 0 |
| https://www.youtube.com/watch?v=jNQXAC9IVRw | once | 7.2 | 6.1 | 0.3 | 0.3 | 7.9 | 0.5 | 1.57 | 0 |
| https://www.youtube.com/watch?v=jNQXAC9IVRw | n4 | 9.2 | 4.4 | 0.6 | 0.2 | 10.0 | 0.5 | 0.85 | 0 |
| https://www.youtube.com/watch?v=jNQXAC9IVRw | once_n4 | 5.3 | 4.3 | 0.6 | 0.2 | 6.1 | 0.5 | 0.85 | 0 |
| https://www.youtube.com/watch?v=aqz-KE-bpKQ | base | 9.9 | 5.1 | 16.8 | 2.1 | 28.8 | 102.2 | 6.92 | 0 |
| https://www.youtube.com/watch?v=aqz-KE-bpKQ | once | 10.3 | 8.8 | 12.6 | 2.9 | 25.8 | 102.2 | 8.81 | 0 |
| https://www.youtube.com/watch?v=aqz-KE-bpKQ | n4 | 19.3 | 11.9 | 11.8 | 1.1 | 32.1 | 102.2 | 10.19 | 0 |
| https://www.youtube.com/watch?v=aqz-KE-bpKQ | once_n4 | 7.7 | 6.5 | 15.6 | 2.1 | 25.3 | 102.2 | 6.56 | 1 |
| https://vimeo.com/76979871 | base | - | - | - | - | - | - | - | 2 |
| https://vimeo.com/76979871 | once | - | - | - | - | - | - | - | 2 |
| https://vimeo.com/76979871 | n4 | - | - | - | - | - | - | - | 2 |
| https://vimeo.com/76979871 | once_n4 | - | - | - | - | - | - | - | 2 |

Failures: Vimeo's probe failed in every config ("Download failed. [unknown]": the extractor needs sign-in or is
broken right now), so there is no HLS/DASH number yet. One `once_n4` run of the long video got
`HTTP Error 403: Forbidden` on the media URL from the reused info JSON: the 12B fallback (one immediate re-run from
the URL) is required, not optional.

## What the numbers say
- **Extract once wins on short clips.** 19 s clip: 13.3 s -> 7.9 s total (base -> once). Nearly all of a short clip's
  time is start-up (two page extractions), not transfer. Reels, TikToks and Shorts behave like this. -> ship in 12B.
- **Long videos already run near line speed.** 10-minute video, 102 MB: transfer 12-17 s at 7-10 MB/s in every
  config; total 25-32 s. Extract once saves a few seconds of start-up; `-N 4` shows no reliable gain on YouTube
  (plain https formats, as expected; spread between runs is larger than the difference).
- **No case for aria2c yet.** Transfer is already close to the line speed seen; only a faster line would show a gain.
  Ask the owner before installing it; test again only if they report slow long downloads.
- **Next measurements:** Instagram reel and TikTok links (need owner-approved public links), and an HLS site once one
  that works without sign-in is found.
