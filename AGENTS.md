# Elisium - rules for the coding agent

A yt-dlp front end for Arch Linux (PySide6/Qt6) and Android (Kotlin/Compose). You implement one brief at a time from `briefs/`. Claude audits every diff.

## Hard rules
- Read `core-spec/SPEC.md` first. It is the source of truth for queue states, dedupe, output folder and error mapping.
- Only edit files named in the brief. If you need another file, stop and say why.
- Never run `sudo`, `git push`, `rm -rf`, or install system packages. Report what is missing instead.
- Machine is 2 cores / 7.6 GB. Run builds and tests with `nice`. No Android emulator. Gradle: `--offline --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g`.
- No network calls in tests, except tests marked `@pytest.mark.live` (skipped by default).
- No analytics, telemetry, or hard-coded cookies/credentials.
- Python 3.11+, type hints, stdlib + PySide6 only for the desktop app (no new dependencies without asking).
- Write tests with the code. A brief is not done until its acceptance checks pass; paste the command output.

## Output contract
When finished, write a short `briefs/<brief>.result.md`: files changed, commands run with pass/fail, anything unfinished. Do not claim a check passed unless you ran it.

## Target desktop (corrected 2026-11-13)
The owner runs **Hyprland on Wayland** (HyDE dotfiles, waybar with a tray module, dunst for notifications, `qt6-wayland`, `qt6ct` + Kvantum for Qt theming). It is NOT KDE. Use freedesktop/XDG standards only: `org.freedesktop.Notifications`, StatusNotifierItem tray, `xdg-open`, `xdg-user-dir`. No KDE-only APIs (KNotification, KDE Wallet as a hard dependency). On Wayland an app cannot reliably raise, focus or position its own window. 

## Visual design (owner decision 2026-11-14, overrides the old "follow the Qt platform theme" rule)
Both apps use the "Afterglow" design in `design/DESIGN.md` with colours only from `design/tokens.json` (own palette, light and dark, following the system setting). Keep every accessible name, role, shortcut and live region; the redesign changes looks, not semantics. `python3 design/contrast_check.py` must stay ALL PASS. Respect reduced motion.
