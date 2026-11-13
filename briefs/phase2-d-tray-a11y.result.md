# Brief 2D result

## Test run
`cd desktop && nice .venv/bin/python -m pytest -q` -> `391 passed, 1 skipped in 23.49s` (321 existing tests plus new ones; the skip is the pre-existing live test).

## Files
Created: `desktop/elisium_downloader/ui/tray.py`, `desktop/tests/test_ui_tray.py`, `desktop/tests/test_ui_a11y.py`, `desktop/ACCESSIBILITY.md`, `briefs/phase2-d-large-text.png` (main window at 200% text, from a throwaway script in the scratchpad).
Edited: `engine/queue.py` (public `probe(url)` and `ytdlp` property), `ui/main_window.py`, `ui/quality_dialog.py`, `ui/playlist_dialog.py`, tests `test_queue.py`, `test_ui_main_window.py` (new tests only).
Edited beyond the named files (needed for part 3, please review): `ui/history_page.py` (columns sized from the font, no sideways scroll, Tab leaves the table), `ui/settings_page.py` (download-folder row restructured because a wrapped label inside a box layout was clipped at large text; the tray checkbox description said "no effect yet", now accurate).

## What was done
1. `MainWindow` now uses `queue.probe` / `queue.ytdlp`.
2. Tray: `TrayController` (menu Show/Hide, Pause all, Resume all, Open download folder, Quit; tooltip = status summary; left click toggles). close_to_tray hides the window and shows "Elisium Downloader is still running here" once per run; Ctrl+Q and tray Quit really quit (and prompt if downloads run). Notifications for done/failed when notify_on_done is on and the window is not active, max one per second (batched "N downloads finished"), failed ones use the plain error message, clicking opens the file's folder. Injectable tray, notifier, folder opener, clock and quit function. The real tray is only built when `tray_wanted()` (not on the offscreen/minimal platforms) because `isSystemTrayAvailable()` is True offscreen. DBus notifier skipped (showMessage only). No tray: close behaves as before.
3. Accessibility: tab order fixed (sidebar added; tables no longer swallow Tab); announcer with live label and `QAccessibleAnnouncementEvent`; `AccessibleStyle` wrapper (check box outline, focus ring in palette text colour); font-driven sizes for 200%; `ELISIUM_REDUCE_MOTION`; Enter in the playlist range box applies the range instead of pressing Add; F1 cheat sheet built from the same table as the registered shortcuts.

## Unverified / caveats
- Orca was NOT run. No AT-SPI in offscreen; announcements are only checked to be sent without error.
- Real tray, dunst and notification clicks were not tried. Wayland raise/focus is not promised.
- The reduce-motion switch is the env var only; PySide6 6.12 has no reduced-motion style hint.
- Contrast was checked with test dark/light palettes on the machine's qt6ct-wrapped style, not the owner's real theme. Installing the `AccessibleStyle` replaces the application style object at MainWindow start (idempotent; palette unchanged in my check) - worth a look in a real session.
- 200% layout: main window grows to about 1200 px wide at 200%. Long titles are elided in the Title column (tooltip has the full text).
- Offscreen tests call `show()` on windows (no real display involved).
