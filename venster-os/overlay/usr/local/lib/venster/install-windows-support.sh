#!/bin/bash
# Venster OS: download and install Hangover (Wine for ARM). Run as root.
set -e
echo "Windows-ondersteuning (Hangover) wordt gedownload en geïnstalleerd..."
TMP="$(mktemp -d)"
/usr/local/lib/venster/fetch-hangover.sh "$TMP"
if ! ls "$TMP"/*.deb >/dev/null 2>&1; then
    echo "Downloaden is mislukt. Controleer de internetverbinding en probeer opnieuw."
    exit 1
fi
apt-get update
apt-get install -y --no-install-recommends "$TMP"/*.deb
/usr/local/lib/venster/configure-wine.sh
rm -rf "$TMP"
echo
echo "Klaar! U kunt dit venster sluiten en het programma opnieuw openen."
