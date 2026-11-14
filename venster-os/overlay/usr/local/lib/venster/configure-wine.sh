#!/bin/bash
# Venster OS: system-wide Wine settings after Hangover is installed.
# Box64 (wowbox64) is the fastest emulator for 32-bit programs on a Pi 4.
if [ -n "$(find /usr/lib /usr/local/lib /opt -name wowbox64.dll -print -quit 2>/dev/null)" ]; then
    sed -i '/^HODLL=/d' /etc/environment
    echo "HODLL=wowbox64.dll" >> /etc/environment
fi
