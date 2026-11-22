#!/bin/sh
# Install Elisium for the current user (no sudo). Re-run to update.
# Needs: python, pyside6, yt-dlp, ffmpeg  (Arch: sudo pacman -S pyside6 yt-dlp ffmpeg)
# Optional: gallery-dl (photo posts, carousels, stories, TikTok slideshows)
set -eu

SRC="$(cd "$(dirname "$0")" && pwd)/desktop"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/elisium/app"
BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

missing=""
python3 -c "import PySide6" 2>/dev/null || missing="$missing pyside6"
command -v yt-dlp >/dev/null 2>&1 || missing="$missing yt-dlp"
command -v ffmpeg >/dev/null 2>&1 || missing="$missing ffmpeg"
if [ -n "$missing" ]; then
    echo "Missing:$missing"
    echo "On Arch, run: sudo pacman -S$missing"
    exit 1
fi

# Photo posts, carousels, stories and TikTok slideshows need gallery-dl. It is
# optional (videos work without it), so only hint, never install or fail.
command -v gallery-dl >/dev/null 2>&1 || echo "Tip: for photo posts, carousels and stories, install gallery-dl (Arch: sudo pacman -S gallery-dl)"

mkdir -p "$PREFIX" "$BIN" "$APPS" "$ICONS" "${XDG_CONFIG_HOME:-$HOME/.config}"
rm -rf "$PREFIX/elisium_downloader"
cp -r "$SRC/elisium_downloader" "$PREFIX/"
find "$PREFIX" -name __pycache__ -type d -prune -exec rm -rf {} +

cat > "$BIN/elisium" <<EOF
#!/bin/sh
export QT_QPA_PLATFORM="\${QT_QPA_PLATFORM:-wayland;xcb}"
exec python3 -I -c "import sys; sys.path.insert(0, '$PREFIX'); from elisium_downloader.cli import main; sys.exit(main())" "\$@"
EOF
chmod +x "$BIN/elisium"

cp "$SRC/packaging/elisium.desktop" "$APPS/elisium.desktop"
cp "$SRC/packaging/elisium.svg" "$ICONS/elisium.svg"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" || true
command -v xdg-mime >/dev/null 2>&1 && xdg-mime default elisium.desktop x-scheme-handler/elisium || true

echo "Installed. Run: elisium   (make sure $BIN is in your PATH)"
