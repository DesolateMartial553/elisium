# Brief 2C - "Choose quality" dialog and playlist picker

Read `AGENTS.md`, `core-spec/SPEC.md`, `engine/runner.py` (`probe`, `ProbeError`), `engine/queue.py`, `engine/presets.py`, `ui/main_window.py`, `ui/settings.py`. Tests are headless (`QT_QPA_PLATFORM=offscreen`); never open a visible window, never use the real network (inject fakes), never touch the real home.

## Behaviour (UX rules)
- Plain **Add** stays instant: it queues the link with the default preset, no dialog. (Speed matters.)
- A new **Options...** button next to Add probes the link on a worker thread and opens the *Choose quality* dialog for one video.
- If **Add** is used on a link that looks like a playlist/channel (`runner._looks_like_playlist`), the app probes it automatically and opens the *Playlist* dialog, because queueing it blindly would download an unknown number of videos.

## Part 1 - engine (no Qt)
- `engine/formats.py`: `format_rows(info: dict) -> list[FormatRow]` from a probe `-J` dict (`formats` list). `FormatRow` has `format_id`, `ext`, `resolution` ("1920x1080" or "audio only"), `fps`, `vcodec`, `acodec`, `bitrate`, `size_bytes` (filesize or filesize_approx, may be None), `note`, `kind` (`video+audio` | `video` | `audio`). Sort best first. Skip storyboard/`mhtml` formats. `selector_for(video_id, audio_id) -> str` builds `"137+140"`, `"137"` (video with audio inside), or `"140"` (audio only); raise `ValueError` for empty input. `human_size(n)` and `human_duration(seconds)` helpers. `summary(info) -> VideoSummary` (title, uploader, duration seconds, thumbnail url, webpage url).
- `engine/formats.py`: `playlist_entries(info) -> list[PlaylistEntry]` (index, id, title, url, duration, availability flag); handle `entries` containing `None` (unavailable) and flat entries with only `url`/`ie_key`. Pure functions; test with hand-written dicts, no yt-dlp.
- `engine/queue.py` (add only): `add(url, *, format_selector=None, extra_args=None, title=None)`: per-item overrides stored on the item and used by `_download` instead of the queue defaults; a duplicate `add` still returns the existing item unchanged. Tests for overrides in `tests/test_queue.py`.

## Part 2 - UI
- `ui/probe_worker.py`: `ProbeWorker(QObject)` runs a `probe` callable on a `QThread`, emits `finished(dict)` or `failed(ErrorInfo, raw)`; injectable probe function; never blocks the GUI; can be cancelled by closing the dialog.
- `ui/thumbnail.py`: `ThumbnailLoader` fetches an image URL with `QNetworkAccessManager` (injectable fetcher for tests), scales to 240 px wide, shows a neutral placeholder on failure. No disk cache.
- `ui/quality_dialog.py` `QualityDialog(QDialog)`: thumbnail + title + uploader + duration; a **Quality** combo of the presets; an **Advanced: choose exact formats** expander with a `QTableView` of `format_rows` (video table and audio table or one table with a Kind column) and live text showing the resulting selector (e.g. "Video 1080p mp4 + audio 128 kbps"); buttons **Download** and **Cancel**. While probing shows "Checking the link..." with an indeterminate bar; on failure shows the plain-language `ErrorInfo` message + fix with a **Show details** area for the raw log and a **Retry** button. Returns `(format_selector, extra_args)` via a method; `Download` calls `queue.add(url, format_selector=..., extra_args=...)`.
- `ui/playlist_dialog.py` `PlaylistDialog(QDialog)`: list with check boxes and title/duration, **Select all**, **Select none**, a range field (`3-15`, `1,4,9-12`, validated with a plain-language error), a count label ("12 of 40 selected"), unavailable entries shown disabled with the word "Unavailable", and a quality combo. **Add selected** queues each chosen entry's own URL (not the playlist URL) with the chosen preset, using the existing dedupe.
- Wire both into `MainWindow` (Options button; auto-probe on playlist links), keeping `Ctrl+Return` = Options-less quick add and adding `Ctrl+Shift+Return` = Options. Accessible names/descriptions and tab order for every control; the dialogs are keyboard-complete and announce probing/failed state through an accessible live label (`setAccessibleDescription` update).

## Tests (headless, fakes only)
formats parsing (video+audio, video-only, audio-only, storyboard skipped, missing sizes), `selector_for` combinations and errors, playlist entries with `None` and flat entries, range parser, queue per-item overrides, worker success/failure with a fake probe, dialogs: placeholder then filled, error state shows message and Retry, selecting an exact format changes the returned selector, playlist select all/none/range and "Add selected" calls the queue once per chosen entry with its own URL, Add on a playlist link opens the playlist dialog (fake probe), plain Add on a single link never opens a dialog or probes. Save one offscreen `grab()` of each dialog to `briefs/phase2-c-quality.png` and `briefs/phase2-c-playlist.png` using a throwaway script kept in the scratchpad dir, not the repo.

## Acceptance
```
cd desktop && nice .venv/bin/python -m pytest -q     # all pass, paste the summary line
```

## Do not
Add dependencies beyond stdlib + PySide6, change finished engine behaviour other than the `add` overrides, run the real yt-dlp or touch the internet in tests, or commit. Write `briefs/phase2-c-choose-quality.result.md`.
