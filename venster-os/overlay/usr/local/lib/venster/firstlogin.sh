#!/bin/bash
# Venster OS: runs at every login; does the one-time setup the first time.
set -u
MARKER="$HOME/.config/venster/firstlogin-done"
WALLPAPER=/usr/share/backgrounds/venster/venster.svg

set_wallpaper() {
    # Set the wallpaper on every connected screen (screen names differ per
    # monitor and cable, so they are read at login).
    local monitor
    for monitor in $(xrandr --listactivemonitors 2>/dev/null | awk 'NR>1 {print $NF}') \
                   $(xfconf-query -c xfce4-desktop -l 2>/dev/null | sed -n 's#^/backdrop/screen0/monitor\([^/]*\)/.*#\1#p' | sort -u); do
        local base="/backdrop/screen0/monitor$monitor/workspace0"
        xfconf-query -c xfce4-desktop -p "$base/last-image" -n -t string -s "$WALLPAPER"
        xfconf-query -c xfce4-desktop -p "$base/image-style" -n -t int -s 5
    done
}

desktop_shortcut() {
    # Copy a menu item to the desktop and mark it as trusted.
    local source="$1" desktop target
    desktop="$(xdg-user-dir DESKTOP)"
    target="$desktop/$(basename "$source")"
    [ -e "$source" ] || return 0
    mkdir -p "$desktop"
    cp "$source" "$target"
    chmod +x "$target"
    gio set -t string "$target" metadata::xfce-exe-checksum "$(sha256sum "$target" | cut -d' ' -f1)" 2>/dev/null || true
}

if [ ! -e "$MARKER" ]; then
    xdg-user-dirs-update
    sleep 3   # give the desktop a moment to start
    set_wallpaper
    desktop_shortcut /usr/share/applications/firefox-esr.desktop
    desktop_shortcut /usr/share/applications/venster-windows-programma-installeren.desktop
    desktop_shortcut /usr/share/applications/xfce-settings-manager.desktop
    mkdir -p "$(dirname "$MARKER")"
    touch "$MARKER"
    notify-send -i venster-start "Welkom bij Venster OS" \
        "Klik op Start (linksonder) voor alle programma's. Windows-programma's (.exe/.msi) opent u met een dubbelklik." || true

    # Prepare the Windows environment in the background, so the first
    # Windows program starts faster.
    if command -v wine >/dev/null 2>&1 && [ ! -d "$HOME/.wine" ]; then
        [ -f /etc/environment ] && . /etc/environment && export HODLL 2>/dev/null
        nice -n 10 wineboot -i >/dev/null 2>&1 &
    fi
fi
