#!/usr/bin/env bash
# MintShare installer for Linux Mint / Ubuntu / Debian (user install, no root needed for the app itself).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
DEPS=(python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-xapp-1.0 python3-pil python3-requests python3-qrcode
      python3-xlib ffmpeg xdotool xclip tesseract-ocr zbar-tools)
OPTIONAL=(python3-paramiko tesseract-ocr-nld gir1.2-ayatanaappindicator3-0.1)

usage() { cat <<U
Usage: ./install.sh [--dry-run] [--no-deps] [-y]
  --dry-run  show exactly which apt packages and files would be touched, change nothing
  --no-deps  do not run apt (you installed the dependencies yourself)
  -y         do not ask for confirmation
U
}
ASSUME_YES=0; DRY=0; NODEPS=0
for a in "$@"; do case "$a" in
  --dry-run) DRY=1;; --no-deps) NODEPS=1;; -y) ASSUME_YES=1;; -h|--help) usage; exit 0;;
  *) echo "Unknown option $a"; usage; exit 1;; esac; done

echo "MintShare will:"
echo "  1. install these apt packages (only the ones you do not have yet): ${DEPS[*]}"
echo "  2. copy its own files to $PREFIX/share/mintshare, $PREFIX/bin/mintshare and a menu entry"
echo "It will NOT change any desktop shortcut now. Shortcuts are only touched if you later run"
echo "'mintshare --apply-hotkeys' (preview first with 'mintshare --show-hotkey-changes'; undo with"
echo "'mintshare --remove-hotkeys' or ./uninstall.sh)."
if [[ $DRY -eq 1 ]]; then
  echo; echo "==> apt simulation (nothing is installed):"
  apt-get install -s "${DEPS[@]}" | grep -E '^(Inst|Conf|[0-9]+ upgraded)' | head -60 || true
  exit 0
fi
if [[ $ASSUME_YES -eq 0 ]]; then read -r -p "Continue? [y/N] " ans; [[ "$ans" =~ ^[yYjJ] ]] || { echo "Cancelled."; exit 1; }; fi

if [[ $NODEPS -eq 1 ]]; then :; else
  echo "==> Installing dependencies with apt (asks for your password)…"
  sudo apt-get update -qq
  sudo apt-get install -y "${DEPS[@]}"
  for p in "${OPTIONAL[@]}"; do sudo apt-get install -y "$p" 2>/dev/null || echo "   (optional package $p not available, skipped)"; done
fi

echo "==> Installing MintShare into $PREFIX"
DEST="$PREFIX/share/mintshare/app"
rm -rf "$DEST"; mkdir -p "$DEST" "$PREFIX/bin" "$PREFIX/share/applications"
cp -r "$HERE/mintshare" "$DEST/"
install -m755 "$HERE/bin/mintshare" "$DEST/mintshare-launcher"
ln -sf "$DEST/mintshare-launcher" "$PREFIX/bin/mintshare"
install -m644 "$HERE/data/mintshare.desktop" "$PREFIX/share/applications/mintshare.desktop"
update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) echo "NOTE: add $PREFIX/bin to your PATH (log out and in again on Linux Mint usually does it)";; esac

echo
echo "Done. Start MintShare from the menu or run:  mintshare"
echo "Set up the hotkeys (Print, Ctrl+Print, …) with:  mintshare --apply-hotkeys"
