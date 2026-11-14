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
- ANDROID 5A DONE 2026-11-13: android/ scaffold builds debug APK (72 MB, arm64-v8a only, package com.desolate.elisium, AGP 9.5.1, Kotlin 2.4.21, compileSdk 37, youtubedl-android 0.18.1). Build: JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --no-daemon --max-workers=1 :app:assembleDebug (first build OOM-killed once; retry works). UNVERIFIED on a device: engine start. Copy at ~/Downloads/Elisium-debug-0.1.0.apk. TODO: allowBackup=false before release (cookies).
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
|---|---|---|---|

## Owner actions pending
- `sudo pacman -S pyside6` (needed before Phase 2).
- Confirm Android package ID (default `com.desolate.elisiumdownloader`).
