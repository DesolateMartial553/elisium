# Brief 1B - archive + history (run after 1A passes audit)

Read `AGENTS.md`, `core-spec/SPEC.md`, and the 1A modules.

## Create
- `desktop/elisium_downloader/engine/archive.py`
  - `class Archive(path)`: `has(extractor, id)`, `add(extractor, id)`, `remove(extractor, id)`. File format is yt-dlp's: one `<extractor> <id>` per line (lowercase extractor). Atomic writes (temp file + rename). Tolerates a missing file and blank lines.
  - `reconcile(archive, key, output_dir) -> bool`: given a `video_key`-style key, return True only if the id is archived AND a file in `output_dir` has `[<id>]` in its name; if archived but no file exists, remove it from the archive and return False.
- `desktop/elisium_downloader/engine/history.py`
  - SQLite via stdlib. Table `downloads(id INTEGER PK, url, video_key, title, state, error_code, error_message, file_path, created_at, finished_at)`.
  - `class History(db_path)`: `add`, `update_state`, `get`, `search(text)`, `recent(limit)`, `delete`. Use parameter binding only, never string formatting.
- `desktop/tests/test_archive.py`, `test_history.py`

## Acceptance
`cd desktop && nice .venv/bin/python -m pytest -q` passes. Tests cover: archive round-trip, yt-dlp-compatible file format, reconcile removes stale ids, deleted-file case, search, and SQL-injection-safe inputs (title containing quotes).

## Do not
Touch 1A files except to fix a real bug (say so in the result file).
