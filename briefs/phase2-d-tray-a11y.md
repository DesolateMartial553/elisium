# Brief 2D - tray, notifications, accessibility pass, cleanup

Read `AGENTS.md`, `core-spec/SPEC.md` (Accessibility section), `ui/main_window.py`, `ui/model.py`, `ui/settings.py`, `ui/quality_dialog.py`, `ui/playlist_dialog.py`, `engine/queue.py`. Headless tests only (`QT_QPA_PLATFORM=offscreen`); no visible windows, no real network, never touch the real home.

## Part 1 - cleanup
- `engine/queue.py`: add a public `probe(url) -> dict` method (wraps the injected `probe_url` with the queue's `ytdlp`) and a public `ytdlp` property. `ui/main_window.py` must use these instead of `getattr(queue, "_probe_url")`/`_ytdlp`. Tests for both.

## Part 2 - tray and notifications
- `ui/tray.py` `TrayController(QObject)`: a `QSystemTrayIcon` (skip gracefully when `QSystemTrayIcon.isSystemTrayAvailable()` is false), menu: Show/Hide window, Pause all, Resume all, Open download folder, Quit. Tooltip = the status-bar summary. Left click toggles the window.
- Settings wiring: **Keep running in the tray when closed** (already stored as `close_to_tray`): when on and a tray exists, closing the window hides it and keeps downloading; when off, the existing close prompt behaviour stays. First time it hides, show a tray message "Elisium Downloader is still running here".
- Notifications: when an item finishes (done/failed) and `notify_on_done` is on and the window is not focused, show a desktop notification (`QSystemTrayIcon.showMessage`; also try KDE's `org.freedesktop.Notifications` over `QtDBus` only if you can do it cleanly with an injectable notifier, otherwise skip). Failed items use the plain-language `error.message`. Clicking the notification opens the file's folder. No more than one notification per second (batch "3 downloads finished").
- Injectable notifier/tray so tests never show real notifications.

## Part 3 - accessibility pass (SPEC.md rules)
1. **Real key presses.** Using `QTest.keyClick`, cover: Tab order through URL bar, Paste, Add, Options, sidebar, table, toolbar; `Ctrl+L`, `Ctrl+V`, `Space` pause/resume, `Ctrl+1/2/3`, `F1`, `Ctrl+Shift+Return`; Escape closes dialogs; Enter in the playlist range field applies it. Fix any broken path you find.
2. **Progress announcements.** A single hidden/zero-height accessible live label on the main window; update its text only at coarse steps (25/50/75 percent, then "finished" or "failed") per item, never every tick, using `QAccessible` announcement events if available in PySide6 6.12 (`QAccessibleAnnouncementEvent`), else a polite live-region-style text change with `QAccessibleEvent`. Test the throttling: 100 progress ticks give at most 4 announcements per item.
3. **Not colour alone**: assert every status in the downloads table, history page and notifications has a word, and in dialogs unavailable entries have the word "Unavailable". Ensure checkboxes, focus rings and selected rows remain visible with a dark and a light `QPalette` (render with both, check unticked checkbox and focused widget pixel contrast against the background is at least 3:1; fix by forcing the style's checkbox/focus drawing or palette roles if not).
4. **200% text scale**: set the application font to double the default size, show the main window, history, settings, both dialogs at their default size; assert no widget's text is clipped (use `fontMetrics().horizontalAdvance` against the widget width for labels/buttons, and size hints) and no horizontal scrollbar is forced on the table pages. Fix layouts (minimum sizes, wrapping, stretch) where it fails.
5. **Reduced motion**: respect `QStyleHints`/an `ELISIUM_REDUCE_MOTION=1` env override: no animated progress (indeterminate busy bar in the quality dialog becomes static text "Checking the link...").
6. **Cheat sheet (F1)** lists every shortcut that exists; test that it matches the registered shortcuts so the two cannot drift.
7. Write `desktop/ACCESSIBILITY.md`: what is covered, how it was tested (offscreen + QTest), and a short **manual Orca checklist** for the owner to run on a real KDE session (start `orca`, 10 steps), because Orca itself cannot run headless. State clearly that Orca testing has NOT been done by you.

## Tests
New `tests/test_ui_tray.py`, `tests/test_ui_a11y.py`; update others only where required. Screenshot `grab()` of the main window at 200% scale to `briefs/phase2-d-large-text.png` via a throwaway script in the scratchpad dir (not the repo).

## Acceptance
```
cd desktop && nice .venv/bin/python -m pytest -q     # all pass, paste the summary line
```

## Do not
Add dependencies beyond stdlib + PySide6, change finished engine behaviour other than the public `probe`/`ytdlp`, call real notifications or the network in tests, claim Orca was tested, or commit. Write `briefs/phase2-d-tray-a11y.result.md`.
