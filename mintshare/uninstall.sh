#!/usr/bin/env bash
set -e
PREFIX="${PREFIX:-$HOME/.local}"
mintshare quit 2>/dev/null || true
rm -rf "$PREFIX/share/mintshare" "$PREFIX/bin/mintshare" "$PREFIX/share/applications/mintshare.desktop" \
       "$HOME/.config/autostart/mintshare.desktop"
echo "MintShare removed. Settings stay in ~/.config/mintshare (delete it yourself if you want)."
