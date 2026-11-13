# Accessibility - Elisium (desktop)

## What is covered
- Every control has an accessible name (and a description where useful); status is always an icon plus a word.
- Keyboard: Tab order Link box, Paste, Add, Options, Sections list, Downloads table, toolbar. Tab leaves tables (it does not walk cells). Shortcuts: see F1 (the cheat sheet and the registered shortcuts come from one table, `SHORTCUTS` in `ui/main_window.py`).
- Progress announcements: one zero-height live label on the main window. A `QAccessibleAnnouncementEvent` (polite) is sent at 25, 50 and 75 percent, then "finished" or "failed" (with the plain-language reason), per download. Ticks in between are silent (max 4 per item).
- Not colour alone: tables, history, notifications and the playlist dialog ("Unavailable") use words.
- Contrast: an `AccessibleStyle` wrapper around the style you configured (qt6ct, Kvantum, Fusion...) outlines check boxes and radio buttons and draws a 2 px focus ring in the palette's own text colour. No colours are hard-coded, so it follows your theme.
- 200% text: sidebar, table columns, history columns and dialogs size from the font; no clipped labels, no sideways scrolling on the table pages.
- Reduced motion: `ELISIUM_REDUCE_MOTION=1` (or `=0` to force off) removes the busy bar in the Choose quality and playlist dialogs; the text "Checking the link..." stays. PySide6 6.12 has no reduced-motion style hint, so the environment variable is the only switch.
- Tray and notifications: a StatusNotifier tray icon (shown by waybar's tray module on Hyprland) with Show/Hide, Pause all, Resume all, Open download folder, Quit; do not rely on a left click, the menu always works. Notifications go through `QSystemTrayIcon.showMessage` (freedesktop notifications, e.g. dunst). If no tray exists the window simply closes as with "Keep running in the tray" off. On Wayland the app cannot reliably raise or focus its own window: Show only calls show/raise/activate.

## How it was tested (automated, headless)
`desktop/tests/test_ui_a11y.py` and `test_ui_tray.py`, run with `QT_QPA_PLATFORM=offscreen`: real `QTest.keyClick` presses (Tab order, Ctrl+L/V/1/2/3/Q, Space, F1, Ctrl+Shift+Return, Escape, Enter in the range box), the announcement throttle, status words, contrast (dark and light palettes, pixels of the rendered widgets, at least 3:1), a doubled application font, reduced motion, and the cheat sheet against the registered shortcuts. The tray uses a fake icon so nothing is shown or sent.

## Not tested
- **Orca was NOT run by the author.** The offscreen platform has no AT-SPI bus, so what a screen reader actually says is unverified. Announcement events are only checked to be sent without error.
- A real tray (waybar), real dunst notifications and clicking a notification were not tried.
- Contrast was measured with test palettes, not with your qt6ct/Kvantum theme.
- Orca key echo and global keys are limited on Wayland compositors (Hyprland), so some Orca behaviour differs from X11.

## Manual Orca checklist (Hyprland / Wayland session)
Start Orca (`orca &`, or Super+Alt+S if bound), then start `elisium`.
1. Focus lands in the link box; Orca says "Video link". Tab through Paste, Add, Options, Sections, Downloads: each is named.
2. Press Ctrl+L from the table: back in the link box.
3. Paste a link and press Enter: the row appears and the status bar says "Added 1 link".
4. In Downloads, arrow to a row: Orca reads title, status, percent, speed and time left.
5. Press Space on a running download: it pauses; press again to resume.
6. Let a download run: Orca should say 25, 50 and 75 percent once each, then "finished". (If silent, note it: announcement support in Orca on Wayland may be limited.)
7. Press F1: the shortcut list is read; Escape closes it.
8. Ctrl+Shift+Return on a link: Choose quality opens; check Quality, Advanced and Download are named; Escape closes.
9. Paste a playlist link: tick/untick with Space, type 1-3 in Range and press Enter (ticks, does not add); entries marked Unavailable are read with that word.
10. Settings: turn on "Keep running in the tray when closed", close the window, find the tray icon, use its menu (Show window). Then set text size to 200% in your Qt theme tool and reopen: nothing should be cut off.
