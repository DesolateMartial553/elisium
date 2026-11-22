# Brief 12C + 12E (desktop) - "Faster downloads" setting and faster-feeling progress

Plan: `~/.claude/plans/elisium-speed-phase12.md` (the "Safety rails" and "Perceived speed" sections).
Evidence: `briefs/phase12-a-bench.result.md`: only the extract-once lever helped (already built in 12B); `-N` gave no gain and
there is no case for aria2c, so DO NOT add aria2c, `-N`, or a per-site connection table. Read `AGENTS.md`,
`briefs/phase12-b-desktop-extract-once.result.md`, `briefs/phase10-c-desktop-multifile-screens.result.md`.
Edit only: `desktop/elisium_downloader/engine/queue.py`, `engine/runner.py` (only if needed), `engine/settings`/the settings
store, `ui/settings_page.py`, `ui/model.py`, `ui/widgets.py`, `ui/main_window.py`, tests, and write
`briefs/phase12-c-desktop-faster-setting-and-feel.result.md`. No Android, no commit/push, sudo, network, no real windows
(offscreen only), `nice` for everything.

## Build
1. **Setting "Faster downloads: Auto / Off"** (Settings > Downloads, default Auto). Auto = `reuse_probe=True` (12B). Off =
   `reuse_probe=False`, which must give today's exact argv (12B already tests the argv; add a queue-level test that the setting
   reaches `reuse_probe`). Helper text, plain: "Auto looks each link up once. Turn off if downloads fail." Stored like the
   other settings, tolerant of older settings files.
2. **Rate-limit safety rail.** On the first HTTP 429 / "please wait" for a site in a session, that site stops reusing the
   probe and drops concurrent downloads for that site to 1 for the rest of the session (pure function + test). Signed-in
   Instagram/TikTok and media-engine items never get any speed lever.
3. **Instant card (12E).** On Add, the row appears immediately with the link's host as the title ("Looking up the post..." for
   photo posts already exists) and fills in title/thumbnail when the probe returns; start fetching the thumbnail as soon as the
   probe has a URL, in parallel with the download starting (verify what the code does today; only change if it waits).
4. **Honest ETA.** Smooth speed with an exponential moving average (alpha about 0.2, ignore the first 2 s) so "time left" does
   not jump; show "Starting..." with a reason if no progress after 10 s: "Signing in", "Waiting for the network", "Rate
   limited, waiting", derived from the state the queue already has. Pure functions with tests; no new threads.
5. **Show carousel slides as they land:** for media-engine items, update `files_done` as each file is saved (verify; fix if
   it only updates at the end).

## Tests
Setting default/Off/old-file; queue gets `reuse_probe` from it; 429 downgrade per site; EMA smoothing numbers; stall reason
selection; instant-card row text; both colour schemes, nothing below 12 px, accessible names unchanged except as stated.

## Acceptance (paste real output)
```
cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
python3 design/nightshelf/contrast_check.py
```
Run the full suite ONCE at the end (7-15 min) and do not end your turn while it runs. Keep spend low: read only what you
need. Write the result file even if low on budget.
