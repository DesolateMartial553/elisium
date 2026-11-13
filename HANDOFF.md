# Elisium Downloader - handoff

Plan: `~/.claude/plans/lets-start-preparing-with-snazzy-koala.md`. Spec: `core-spec/SPEC.md`. Agent rules: `AGENTS.md`.

Workflow: OpenCode implements one brief from `briefs/`; Claude audits the diff and runs the checks; if OpenCode is out of usage, a Sonnet (big) or Haiku (small) subagent takes the same brief. Record who did what below.

## Status
- Phase 0 prep: done (folder, AGENTS.md, SPEC.md, briefs 1A-1C).
- Phase 1A: DONE, audited (41 tests pass, re-run by Claude; urlnorm/errors/paths read and spot-checked). Note: xdg-user-dir returns $HOME when DOWNLOAD is unset, which would give ~/Elisium Downloader; handle in a later brief.
- Phase 1B: DONE, audited (107 tests pass; archive/history read). Concern moved to 1C: archive lost-update race with yt-dlp appends.
- Phase 1C: DONE, audited (161 pass; real-yt-dlp end-to-end run OK: 3 URL forms -> 1 item, 1 file, empty temp, archive written, restart makes no copy). Gaps -> brief 1D: same-session re-add after delete, file_path for non-YouTube, silent archive skip reported as done, "converting" shown for MoveFiles.
- Phase 1D: DONE, audited by Claude (175 pass, 1 skipped; own real-yt-dlp e2e run OK: file_path set for non-YouTube, restart => skipped, no "converting" for plain downloads). OpenCode hit its free usage limit mid-task; finished by a Sonnet subagent (user-approved fallback). ENGINE COMPLETE.
- Next: Phase 2 (PySide6 UI). PySide6 6.12.0 is installed (pacman package is `pyside6`, not python-pyside6).

## Log
| Brief | Implemented by | Audit | Notes |
| 1A | OpenCode (owner-run) | Claude: pass | 41 tests, no forbidden imports |
| 1B | OpenCode (Claude-launched, no --auto) | Claude: pass | 107 tests total |
| 1C | OpenCode (Claude-launched) | Claude: pass + e2e | 161 tests; pyproject marker added (accepted) |
| 1D | OpenCode (partial, hit limit) then Sonnet subagent | Claude: pass + e2e | 175 tests; engine complete |
|---|---|---|---|

## Owner actions pending
- `sudo pacman -S pyside6` (needed before Phase 2).
- Confirm Android package ID (default `com.desolate.elisiumdownloader`).
