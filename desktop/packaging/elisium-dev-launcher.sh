#!/bin/sh
# Developer launcher: runs Elisium from the project's venv.
# The packaged version (PKGBUILD) installs a normal `elisium` command instead.
ROOT="$HOME/Work-Projects/elisium-downloader/desktop"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-wayland;xcb}"
exec "$ROOT/.venv/bin/python" -c "import sys; sys.path.insert(0, '$ROOT'); from elisium_downloader.cli import main; sys.exit(main())" "$@"
