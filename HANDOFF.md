# Elisium Downloader - handoff

Plan: `~/.claude/plans/lets-start-preparing-with-snazzy-koala.md`. Spec: `core-spec/SPEC.md`. Agent rules: `AGENTS.md`.

Workflow: OpenCode implements one brief from `briefs/`; Claude audits the diff and runs the checks; if OpenCode is out of usage, a Sonnet (big) or Haiku (small) subagent takes the same brief. Record who did what below.

## Status
- Phase 0 prep: done (folder, AGENTS.md, SPEC.md, briefs 1A-1C).
- Phase 1A: DONE, audited (41 tests pass, re-run by Claude; urlnorm/errors/paths read and spot-checked). Note: xdg-user-dir returns $HOME when DOWNLOAD is unset, which would give ~/Elisium Downloader; handle in a later brief.
- Phase 1B: next (run in OpenCode by the owner).

## Log
| Brief | Implemented by | Audit | Notes |
| 1A | OpenCode (owner-run) | Claude: pass | 41 tests, no forbidden imports |
|---|---|---|---|

## Owner actions pending
- `sudo pacman -S pyside6` (needed before Phase 2).
- Confirm Android package ID (default `com.desolate.elisiumdownloader`).
