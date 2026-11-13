# Brief 1B result - archive + history

Status: done.

## Files created
- `desktop/elisium_downloader/engine/archive.py` - `Archive` (`has`/`add`/`remove`) + `reconcile`.
- `desktop/elisium_downloader/engine/history.py` - `History` (`add`, `update_state`, `get`, `search`, `recent`, `delete`), `STATES`, `TERMINAL_STATES`.
- `desktop/tests/test_archive.py` - 38 tests.
- `desktop/tests/test_history.py` - 28 tests.

No 1A file was touched (`git status` shows only the four new files). No new dependencies, no PySide6 import, no network.

## Behaviour notes

### archive.py
- File format is yt-dlp's `--download-archive`: `<extractor> <id>` per line, extractor lowercased, `\n` separated, trailing newline. Verified byte-exact: `b"youtube dQw4w9WgXcQ\nvimeo 12345\n"`.
- Reads tolerate: missing file, blank/whitespace lines, CRLF, lines with more or fewer than 2 fields, duplicate lines. Unparsable lines are ignored and dropped on the next write.
- Every call re-reads the file (never trusts an in-memory set), because yt-dlp appends to the same file during a download.
- Writes are atomic: `NamedTemporaryFile` in the same directory, `flush` + `fsync`, then `os.replace`. On any failure the temp file is unlinked and the old archive is left intact (tested by patching `os.replace` to raise).
- `add` returns `False` when the entry is already present (no rewrite, no duplicate line). `remove` returns `False` and does not create the file when the entry is absent. Parent directories are created on write.
- Empty or whitespace-containing extractor/id raise `ValueError`.
- `reconcile(archive, "youtube:<id>", output_dir)`: `True` only when the id is archived **and** a real file whose name contains `[<id>]` is in `output_dir` (top level, non-recursive). Otherwise `False`, and if the id is archived but no file exists it is removed from the archive so the video downloads again. Missing/unreadable output dir counts as "no file".
- Two judgement calls worth a look in audit: (a) a bare `VIDEO_ID` in a filename without brackets does not count, only `[<id>]`; (b) files ending `.part`, `.ytdl`, `.temp` are ignored so a leftover partial in the output folder can never be mistaken for a finished download (staging belongs in the cache temp dir per SPEC).
- A malformed key (no `:`, empty side) returns `False` and leaves the archive alone.

### history.py
- Stdlib `sqlite3` only. Table is exactly `downloads(id INTEGER PRIMARY KEY, url, video_key, title, state, error_code, error_message, file_path, created_at, finished_at)` - asserted column-by-column against `PRAGMA table_info`.
- One shared connection (`check_same_thread=False`) guarded by an `RLock`, so a UI thread and a download-worker thread can both use it. `close()` plus context-manager support. `:memory:` works.
- Every value is a bound parameter. No user text is ever formatted into SQL; the only f-string is the `UPDATE ... SET` list, built from a fixed set of column names.
- `LIKE` searches escape `%`, `_` and `\` with `ESCAPE '\'`, so `search("100%")` matches the literal text `100%` and nothing else; a title containing `'` or `Robert'); DROP TABLE downloads;--` round-trips and searches normally.
- `search(text)` matches `url`, `video_key` or `title` (case-insensitive for ASCII), newest first, default `limit=200`; blank text returns `[]`. `recent(limit=50)` is newest first. Both return plain dicts; `get` returns `None` when missing.
- `add` validates `url` is non-empty and `state` is one of the SPEC states; returns the new row id.
- `update_state(id, state, *, error_code, error_message, file_path, clear_error=False)` returns `False` for an unknown id. `None` leaves a column unchanged; `clear_error=True` nulls the two error columns. `finished_at` is stamped once on a terminal state (`done`/`failed`/`skipped`/`cancelled`) and cleared when the item goes back to an active state, so `failed -> queued -> done` gives a fresh stamp.
- Unknown states raise `ValueError` (typo guard, states come from `core-spec/SPEC.md`).

## Commands run
```
cd desktop && nice .venv/bin/python -m pytest -q
........................................................................ [ 67%]
...................................                                      [100%]
107 passed in 0.28s
```
PASS (107 tests: 41 pre-existing from 1A + 66 new).

```
cd desktop && nice .venv/bin/python -m pytest -q tests/test_archive.py tests/test_history.py
66 passed in 0.18s
```
PASS.

Also ran a throwaway script against real files in `/tmp/opencode/brief1b` (not part of the suite) to eyeball bytes and rows:
```
bytes: b'youtube dQw4w9WgXcQ\nvimeo 12345\n'
reconcile with file: True
reconcile after delete: False
archive now: vimeo 12345
search 100%: [1]        search injection: []        recent: [1]
schema: ['id','url','video_key','title','state','error_code','error_message','file_path','created_at','finished_at']
```

## Unfinished / follow-ups
- Nothing blocked. `reconcile` is not yet called from a runner or UI - that belongs to a later brief.
- `History` has no migration/version table yet; the first schema change will need one.
- No cleanup job for old history rows (retention) - not in this brief.
