# phase6-c desktop polish: result

## Task 1: test_real_qt_client_round_trip segfault (ROOT CAUSE FOUND, real lifetime bug in ipc.py)

Symptom. Segfault inside `QCoreApplication.processEvents()` (in the tests' `pump_until`), ~10-30% of runs of
tests/test_ipc.py under CPU load (1 in 3 in the full suite), never when the test runs alone. test_ipc is the
first Qt test of the suite, so stale objects from other tests are not involved. faulthandler/gdb trace:
`processEvents -> sendPostedEvents -> QObject::event(DeferredDelete) -> ~QObject` crash.

Cause. Each client connection is a `_Session` (Python QObject subclass, child of `IpcServer`) that finishes with
`deleteLater()` and, like the server, was only torn down by Python garbage collection (`IpcServer` sits in
reference cycles, so `del srv` does not free it; the C++ objects linger until the cyclic GC runs, at an arbitrary
moment). A finished session therefore still had a pending `DeferredDelete` event when its server was dropped, and
the GC-driven C++ teardown of server/sessions raced with that posted event: the event was later delivered to a freed
object. A second path of the same family: a session whose socket was still connected at teardown emitted
`disconnected` from inside the session's own destructor, the slot called `deleteLater()` there, and Qt (which
removes posted events BEFORE deleting children) left a dangling event.
Reproduced deterministically outside pytest (standalone loop: open connection / serve one request, close the
server without extra pumping): crash every run before the fix, 0 of 450 iterations after it.

Fix (`desktop/elisium_downloader/ui/ipc.py`, a real bug in ipc.py; the client and the protocol are unchanged):
- `IpcServer.close()` now tears the sessions down deterministically: `_Session.dispose()` (disconnect slots, stop
  timer, abort socket) and then `shiboken6.delete(session)` (synchronous C++ delete, which also drops its posted
  events), instead of leaving that to posted events and the garbage collector. The app already calls `close()` on exit.
- `_Session` has a `_dying` flag (set from its `destroyed` signal) that every slot checks, so no `deleteLater()` is
  posted while an object is being destroyed.
- The timeout lambda became a bound method.
Regression test added to `tests/test_ipc.py`:
`test_server_teardown_with_open_connections_does_not_crash_later` (server dropped with clients still connected,
closed first and not closed first).

## Task 2: card polish (`ui/main_window.py`, `ui/widgets.py`, `ui/theme.py`, `ui/settings_page.py`)
(a) Per-card action buttons: new `CardActions` (one set of buttons on the table viewport, moved to the hovered
card, else the selected one; placed on the caption line; the delegate reserves room so the caption elides
instead of running under them). Only valid actions per state via `card_action_kinds(state)`
(pause/cancel; resume/cancel; retry; open folder), identical to the toolbar rules. Click selects that
card and triggers the window's own QAction, so toolbar, context menu and shortcuts are unchanged.
Buttons are TabFocus, in the Tab order right after the list, accessible name "<Action> <title>",
description and tooltip set, icons follow the theme. If a focused button disappears (Pause -> Resume) focus
moves to a sibling. Style `QToolButton#cardAction` lives in theme.py (tokens only).
(b) Enter animation: `EnterAnimation` in widgets.py, ONE shared `QVariantAnimation` driver with per-card start
times (fade + 8px rise, 220ms, ease-out cubic); only cards inserted after load animate; nothing is registered when
`reduce_motion()` is true (Settings switch or `ELISIUM_REDUCE_MOTION=1`).
Also: Parallel downloads / speed spin boxes now indent their text (`setTextMargins`, style sheet padding does not reach
it) and their minimum height follows the font (fixed a 200%-text clipping failure in test_ui_a11y).
Tests: `tests/test_ui_main_window.py` (valid actions per state incl. toolbar agreement, accessible names, click acts on
its own card, animation runs for new cards only, off under reduced motion via env and Settings switch);
`tests/test_ui_a11y.py` tab-order test updated (card buttons come after the list, toolbar unchanged).
Screenshots re-rendered with `tools/render_screenshots.py` (24 files in docs/screenshots/), looked at: queue
night/day/large, settings; card buttons sit cleanly on the selected card, spin box text now indented.

## Test environment note
Temp XDG dirs (+ read-only symlink of ~/.local/share/fonts). `QT_QPA_PLATFORMTHEME` must be unset: with the real
qt6ct platform theme `test_selected_row_stands_out_in_dark_and_light[light]` fails (custom wallbash palette),
unrelated to this work. Without the fonts link and with the default font, two 200%-text tests failed at baseline
(spin box min-height); the spin box fix above resolves the main-window one.

## Other test fixes made on the way
- `tests/test_queue.py::test_readding_a_done_item_after_deleting_its_file_downloads_again`: raced with the worker thread
  (row already `probing`); now accepts queued/probing/downloading (still must not be `done`).
- `test_dialogs_fit_at_200_percent` (shortcuts dialog, wrapped labels clipped in the full suite only): the dialog now pins each
  wrapped label to its height-for-width at the final width (`main_window.build_shortcuts_dialog`).

## Verification (commands run, env: temp XDG dirs, fonts symlink, QT_QPA_PLATFORMTHEME unset, nice)
- `tests/test_ipc.py` in a loop: BEFORE the fix 9/30 runs segfaulted; AFTER: 40/40 runs pass, no crash (`fails=0/40`).
- Full suite `pytest tests`: runs 4 and 5 (final code) and run 3 each `513 passed, 1 skipped`, no crash. Runs 1 and 2 were
  made while fixing (2 failed / 1 failed: the queue race and the 200% dialog, both fixed afterwards, no segfault in any run).
  Totals went 495 -> 513 passed (new tests).
- `python3 design/contrast_check.py`: ALL PASS.
- Hard-coded colours outside ui/theme.py: grep finds none (only the existing black alpha mask in widgets.py).
- Not done / caveats: the card buttons were checked in screenshots (offscreen) and by tests, not on a live Wayland session;
  hover behaviour is covered by driving `CardActions` directly, not by real pointer events.
