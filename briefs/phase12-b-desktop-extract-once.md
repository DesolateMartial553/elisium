# Brief 12B (desktop) - extract once, and copy audio instead of converting

Plan: `~/.claude/plans/elisium-speed-phase12.md` (read the "Extract once" and "No needless re-encoding" items) and
`briefs/phase12-a-bench.result.md` for the measured numbers. Read `AGENTS.md` and `core-spec/SPEC.md` first.
Edit only `desktop/elisium_downloader/engine/runner.py`, `desktop/elisium_downloader/engine/queue.py`,
`desktop/elisium_downloader/engine/presets.py`, their tests under `desktop/tests/`, and write
`briefs/phase12-b-desktop-extract-once.result.md`. No UI files, no Android, no commit/push, no sudo, no network in tests.

## Why
Today every item runs yt-dlp twice: `queue._attempt` probes with `-J`, then `_download` runs a second yt-dlp that
extracts the same page again. On a 19-second YouTube clip the measured total fell from ~14 s to ~6 s when the
download reused the probe's info JSON (`--load-info-json`). Short clips (reels, TikToks, Shorts) are most of what
the owner downloads, so this is the biggest felt speed-up.

## Build
1. **Reuse the probe.** In `_attempt`, keep the probe's info dict on the attempt (not on the persisted item; never in
   history). In `_download`, when the info is usable, write it to a file in the item's temp dir
   (`<temp>/<item id>.info.json`, mode 0600) and build the argv with `--load-info-json <file>` and WITHOUT the URL.
   Add this as an explicit `DownloadOptions.info_json: Path | None` field in `runner.py`; `build_command` puts
   `--load-info-json` and drops `opts.url` only when it is set. Everything else in the argv stays identical
   (archive, `--no-overwrites`, output template, home/temp split, `--continue`, progress templates, retries, `-f`,
   `--no-playlist`, `--print-to-file`, cookies, extra args).
2. **Usable** means: a dict, not `_type == "playlist"` (story trays are probed flat and must download from the URL),
   has `formats` or `url`, and the probe finished less than 300 s before the download starts.
3. **Fallback.** If a download that used `--load-info-json` fails with an error whose code is `http_403`, `http_410`,
   `expired`/unavailable-format style text, or yt-dlp exits non-zero before the first progress line, run ONE more
   attempt immediately from the URL (no info JSON), without counting it as a retry and without a backoff delay.
   Delete the info file after the attempt either way. Pause/cancel behaviour is unchanged.
4. **Off switch.** A module constant / queue argument `reuse_probe: bool = True`, so the later "Faster downloads: Off"
   setting (12C) can turn it off. With it False the argv must be byte-for-byte today's argv (test it).
5. **Audio presets copy when possible.** In `presets.py`: `audio-m4a` format selector `bestaudio[ext=m4a]/bestaudio/best`,
   `audio-opus` `bestaudio[acodec=opus]/bestaudio/best`; keep `-x --audio-format ...` so the result type is the same.
   MP3 and FLAC unchanged (they must encode). Video presets unchanged.

## Tests (offline, fake yt-dlp / injected probe as the existing tests do)
- argv with `info_json` set: has `--load-info-json <path>`, no URL, everything else equal to the URL argv.
- argv with `reuse_probe=False`: identical to the current argv for the same options.
- unusable info (playlist type, missing formats, older than 300 s) -> URL argv.
- fallback: first run with info JSON fails with 403 -> exactly one immediate URL run, success marks done; attempts
  counter unchanged; info file removed.
- presets: the two new selectors.
- Keep every existing test passing (QT_QPA_PLATFORMTHEME unset).

## Acceptance (paste real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
```
Write the result file even if low on budget.
