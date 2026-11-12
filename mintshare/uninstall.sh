#!/usr/bin/env bash
set -e
PREFIX="${PREFIX:-$HOME/.local}"
# put the desktop's own shortcuts back exactly as they were (needs no GTK)
PYTHONPATH="$PREFIX/share/mintshare/app" /usr/bin/python3 -m mintshare.hotkeys --remove 2>/dev/null || true
mintshare quit 2>/dev/null || true
rm -rf "$PREFIX/share/mintshare" "$PREFIX/bin/mintshare" "$PREFIX/share/applications/mintshare.desktop" \
       "$HOME/.config/autostart/mintshare.desktop"
echo "MintShare removed. Settings stay in ~/.config/mintshare (delete it yourself if you want)."
