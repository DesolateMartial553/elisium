# Elisium - handoff

Plan: `~/.claude/plans/lets-start-preparing-with-snazzy-koala.md`. Spec: `core-spec/SPEC.md`. Agent rules: `AGENTS.md`.

Workflow: OpenCode implements one brief from `briefs/`; Claude audits the diff and runs the checks; if OpenCode is out of usage, a Sonnet (big) or Haiku (small) subagent takes the same brief. Record who did what below.

## Status
- Phase 0 prep: done (folder, AGENTS.md, SPEC.md, briefs 1A-1C).
- Phase 1A: DONE, audited (41 tests pass, re-run by Claude; urlnorm/errors/paths read and spot-checked). Note: xdg-user-dir returns $HOME when DOWNLOAD is unset, which would give ~/Elisium; handle in a later brief.
- Phase 1B: DONE, audited (107 tests pass; archive/history read). Concern moved to 1C: archive lost-update race with yt-dlp appends.
- Phase 1C: DONE, audited (161 pass; real-yt-dlp end-to-end run OK: 3 URL forms -> 1 item, 1 file, empty temp, archive written, restart makes no copy). Gaps -> brief 1D: same-session re-add after delete, file_path for non-YouTube, silent archive skip reported as done, "converting" shown for MoveFiles.
- Phase 1D: DONE, audited by Claude (175 pass, 1 skipped; own real-yt-dlp e2e run OK: file_path set for non-YouTube, restart => skipped, no "converting" for plain downloads). OpenCode hit its free usage limit mid-task; finished by a Sonnet subagent (user-approved fallback). ENGINE COMPLETE.
- Phase 2A: DONE (main window, queue table, toolbar, shortcuts, a11y names; 223 tests). Built by a Sonnet subagent (OpenCode out of free usage); Claude fixed the progress delegate (selection gap, invisible percent). Not yet covered: real key-press tests, 25%-step screen-reader announcements.
- Phase 2B: DONE (sidebar, History page, Settings page, presets, queue setters; 252 tests). OpenCode hit its free limit again after presets.py; Sonnet subagent finished. Audited: real home untouched, screenshots reviewed.
- Phase 2C: DONE (Options button, Choose-quality dialog with exact-format table, playlist picker with ranges; 321 tests). Sonnet subagent. Review notes: default probe uses queue._probe_url/_ytdlp via getattr (make public in 2D); unticked checkboxes faint on dark offscreen theme (check under Breeze).
- Phase 2D: DONE (tray, notifications via freedesktop, a11y pass, public queue.probe; 391 tests). Sonnet subagent, corrected mid-task for Hyprland. NOT verified: Orca, real tray/dunst, owner theme contrast.
- Real-session smoke test DONE 2026-11-13: app runs natively on Wayland (not XWayland), window opens, themed by HyDE, no errors. Found + fixed narrow-tile clipping (low-priority columns now hide). Not yet tried: a real download from the GUI, real tray in waybar, dunst notification.
- RENAMED 2026-11-13 (user): app is now "Elisium" (no "Downloader"): window title, command `elisium`, app_id `elisium`, data ~/.local/share/elisium, cache ~/.cache/elisium, output ~/Downloads/Elisium. Python package stays elisium_downloader, repo folder stays elisium-downloader. Launcher (user space): ~/.local/bin/elisium (dev wrapper), ~/.local/share/applications/elisium.desktop, icon elisium.svg; copies in desktop/packaging/.
- ANDROID 5A DONE 2026-11-13: android/ scaffold builds debug APK (72 MB, arm64-v8a only, package com.desolate.elisium, AGP 9.5.1, Kotlin 2.4.21, compileSdk 37, youtubedl-android 0.18.1). Build: JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --no-daemon --max-workers=1 :app:assembleDebug (first build OOM-killed once; retry works). UNVERIFIED on a device: engine start. Copy at ~/Downloads/Elisium-debug-0.1.0.apk. (allowBackup=false done in phase 8B.)
- ANDROID 5B DONE: Kotlin engine port (UrlNorm, Errors, Presets, Formats, Archive, ProgressParser, DownloadQueue + Ports interfaces) 121 JVM tests pass (audited: rerun by Claude). Sonnet subagent. Deviations accepted: queue calls OutputStore.publish (publish_failed error), existsAt added, skipped carries "Already downloaded.".
- ANDROID 5C DONE 2026-11-14: backend, MediaStore output, Room history, DataStore settings, dataSync foreground service, Wi-Fi gate, share intake. Sonnet subagent, cut off before verifying; Claude fixed 4 issues (see briefs/phase5-c-android-backend.result.md). 220 JVM tests, lint clean, debug APK builds. Device behaviour UNVERIFIED.
- ANDROID 5D DONE 2026-11-14: Compose shell (Downloads/History/Settings), permissions, FileProvider for Open; Sonnet subagent. Claude reran: 273 JVM tests pass, lint 0 errors, APK 73.9 MB. Look, TalkBack, and all behaviour UNVERIFIED on a device (see briefs/phase5-d-android-screens.result.md).
- DESKTOP 3A DONE 2026-11-14: single instance (QLocalServer, flock-guarded), `elisium add URL|-`, `elisium://add?url=` handler, http/https-only validation, default preset only. Sonnet subagent; Claude reran 446 tests pass, read ipc.py validation. Real browser click / Hyprland / dunst UNVERIFIED.
- SCOPE (owner, 2026-11-14): for the owner and friends only, apps only. No browser extension, no store listings, no large-scale distribution polish.
- REDESIGN 2026-11-14 "Afterglow" (design/DESIGN.md, tokens.json): Android 1399e31 (292 tests, lint 0 errors), desktop (495 tests, screenshots in docs/screenshots). Not done: per-card action buttons, card enter animation (desktop). Known: tests/test_ipc.py::test_real_qt_client_round_trip segfaults ~1 in 3 full runs (pre-existing). Visuals on real devices UNVERIFIED.
- 2026-11-14 later: Android code review (briefs/android-review-findings.md) -> 7A fixes (327 tests): Room-off-main-thread crashes, pause/resume race, --no-playlist, stale History rows, staging cleanup. Desktop: ipc.py teardown crash fixed at root (was GC vs pending deleteLater), per-card action buttons + enter animation, --no-playlist in runner (514 tests). GPL-3.0 licence, PKGBUILD (untested: needs python-build/installer). Run desktop tests with QT_QPA_PLATFORMTHEME unset (qt6ct wallbash palette breaks one light-theme test). Deferred: queue rehydrate after process kill, explicit "Download again anyway", metered/no-connection wording.
- Next: Android phone test of Elisium-debug-0.2.0.apk, then 5E (a11y fixes + signed release APK for friends); desktop: Arch install package (PKGBUILD or simple install script) so friends can install it, 5E a11y + signed release; desktop Phase 3 (elisium:// handler, CLI add, browser ext), Phase 4 packaging, Phase 5 Android.

## Log
| Brief | Implemented by | Audit | Notes |
| 1A | OpenCode (owner-run) | Claude: pass | 41 tests, no forbidden imports |
| 1B | OpenCode (Claude-launched, no --auto) | Claude: pass | 107 tests total |
| 1C | OpenCode (Claude-launched) | Claude: pass + e2e | 161 tests; pyproject marker added (accepted) |
| 1D | OpenCode (partial, hit limit) then Sonnet subagent | Claude: pass + e2e | 175 tests; engine complete |
| 2A | Sonnet subagent | Claude: pass + fix | 223 tests; screenshot reviewed |
| 2B | OpenCode (presets.py only, then limit) + Sonnet subagent | Claude: pass | 252 tests; screenshots reviewed |
| 2C | Sonnet subagent | Claude: pass | 321 tests; screenshots reviewed |
| 2D | Sonnet subagent | Claude: pass | 391 tests; Orca/tray/dunst untested |
| 3A | Sonnet subagent | Claude: pass (446 tests, e2e by agent in temp XDG) | handler registration done by Claude |
| 5D | Sonnet subagent | Claude: pass (reran all 3 gradle tasks) | 273 JVM tests, lint 0 errors; device untested |
| 5C | Sonnet subagent (cut off) | Claude: pass after 4 fixes | 220 JVM tests, lint clean, APK builds; device untested |
| 9A | OpenCode (Claude-launched) | Claude: pass (desktop 570 pass/2 skip rerun; Android 382 tests 0 failures, lint OK; diff read) | Instagram error rows (session_expired, http_401, no_media), site-aware wording, highlight + TikTok short dedupe keys. SPEC.md table not yet updated (step 5). |
| 9B | OpenCode (Claude-launched) | Claude: pass (Android 400 tests 0 failures, lint OK, APK builds; login code read) | In-app Instagram WebView sign-in -> cookies.txt via existing CookieJar; Advanced section keeps picker. WebView behaviour UNVERIFIED on a phone. |
| 9C | OpenCode (hit free limit, wrote seam/policy draft) then Sonnet subagent | Claude: pass (Android 422 tests 0 failures, lint OK, APK builds; updater/policy/startup read) | Android yt-dlp auto-update (24 h, Wi-Fi gate, idle only) + Settings button. Real update call UNVERIFIED on a phone. |
| 9D | Sonnet subagent (OpenCode out of free usage) | Claude: pass (desktop full suite rerun, contrast ALL PASS; browsers.py privacy review) | Desktop: read-only detector for a signed-in Instagram browser, Accounts hint, Sign-in dialog with retry. Real Firefox/Chrome DB layouts + Hyprland dialog UNVERIFIED. |
| 10A | OpenCode (Claude-launched, finished without hitting its limit) | Claude: pass (Android 457 tests 0 failures, lint 0 errors, rerun by Claude; parser code read, no network/logging in media/) | Route (c) own Kotlin client recommended; bundled Python lacks requests/certifi; QuickJS is bundled; ffmpeg runnable via ProcessBuilder; library yt-dlp is 2025.11.12 (auto-update covers it). |
| 12B (desktop) | OpenCode (hit free limit mid-task, left queue.py broken) then Sonnet subagent | Claude: pass (608 passed / 2 skipped rerun by Claude; diff read: info JSON 0600 O_EXCL, deleted after attempt, one URL re-run on stale/early failure) | Extract once via --load-info-json; audio-m4a/opus prefer native streams. reuse_probe flag not yet wired to a setting (12C). Android 12B still to do. |
| 10B-1 | Sonnet subagent (OpenCode out of free usage) | Claude: pass (755 passed / 2 skipped rerun by Claude; live gallery-dl check on a public image confirmed the -j message shape and stdout path / "# path" lines) | Desktop gallery-dl engine: routing, /p/ no_media fallback, files_done/total, new errors. Instagram/TikTok field names still assumed: live check needs owner links + sign-in OK. Known: gallery-dl archive not reconciled with deleted files (handle in 10C). |
| 10B-2 | Sonnet subagent (resumed once after a session end) | Claude: pass (827 passed / 2 skipped rerun by Claude after the agent's mid-run edit; agent's real local mix: 1080x1920 h264 yuv420p 30 fps, 6.0 s = snippet) | Song cut to the post's snippet, photo + song mp4 per single post; notes when the full song is kept or the video fails. Snippet key names in real gallery-dl metadata still need a live check. |
|---|---|---|---|

## Owner actions pending
- `sudo pacman -S pyside6` (needed before Phase 2).
- Confirm Android package ID (default `com.desolate.elisiumdownloader`).

## Phases 10-12 (started 2026-11-22, branch `phase10-12`)
Plans: `~/.claude/plans/elisium-posts-images-music-stories.md` (10), `elisium-redesign-phase11.md` (11), `elisium-speed-phase12.md` (12).
Order: W1 10A (OpenCode) || 11A (Claude mockups) -> W2 12A bench (no build running) + owner picks direction -> 11B
-> W3 12B, 10B (needs `sudo pacman -S gallery-dl`), 11C, 10C -> W4 10D, 11D, 10E -> W5 10G, 12C/12D (after aria2 answer), 12E
-> W6 12F, 10F + 11E docs, release only on owner yes. One heavy job at a time (2 cores).
