#!/bin/bash
# Download the newest Hangover release for Debian 13 (trixie) on arm64.
# Hangover is Wine built for ARM computers; it runs Windows x86 programs
# by emulating only the program itself (with Box64 or FEX).
#
# Usage: fetch-hangover.sh <output-directory>
# The .deb packages end up in <output-directory>. Exits 0 even when the
# download fails, so a build can still finish without Windows support.
set -u
OUT="${1:?usage: fetch-hangover.sh <output-directory>}"
REPO=AndreRH/hangover
mkdir -p "$OUT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

asset_url=""
if json="$(curl -fsSL https://api.github.com/repos/$REPO/releases/latest 2>/dev/null)"; then
    asset_url="$(printf '%s' "$json" | grep -o '"browser_download_url": *"[^"]*"' \
        | sed 's/.*"\(https[^"]*\)"/\1/' | grep -iE 'trixie|debian13' | grep -i arm64 | head -n1)"
fi
if [ -z "$asset_url" ]; then
    # No API access: read the release page instead.
    tag="$(curl -fsSLI -o /dev/null -w '%{url_effective}' https://github.com/$REPO/releases/latest 2>/dev/null | sed 's#.*/tag/##')"
    if [ -n "$tag" ]; then
        asset_url="$(curl -fsSL "https://github.com/$REPO/releases/expanded_assets/$tag" 2>/dev/null \
            | grep -o 'href="[^"]*"' | sed 's/href="//; s/"$//' \
            | grep -iE 'trixie|debian13' | grep -i arm64 | head -n1)"
        case "$asset_url" in /*) asset_url="https://github.com$asset_url" ;; esac
    fi
fi
if [ -z "$asset_url" ]; then
    echo "fetch-hangover: could not find a Hangover download for Debian 13 arm64." >&2
    exit 0
fi

echo "fetch-hangover: downloading $asset_url"
if ! curl -fL --retry 3 -o "$TMP/hangover.archive" "$asset_url"; then
    echo "fetch-hangover: download failed." >&2
    exit 0
fi
mkdir -p "$TMP/x"
tar -xf "$TMP/hangover.archive" -C "$TMP/x" 2>/dev/null || cp "$TMP/hangover.archive" "$TMP/x/hangover.deb"
find "$TMP/x" -name '*.deb' -exec cp {} "$OUT/" \;
ls -1 "$OUT"/*.deb 2>/dev/null || echo "fetch-hangover: the download held no .deb packages." >&2
exit 0
