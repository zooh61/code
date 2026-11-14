#!/bin/bash
# Runs inside the new root file system during the image build.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

USER_NAME=gebruiker
USER_PASSWORD=venster

echo "--- Language, time zone and keyboard"
sed -i 's/^# *\(nl_NL.UTF-8\)/\1/; s/^# *\(en_US.UTF-8\)/\1/' /etc/locale.gen
locale-gen
update-locale LANG=nl_NL.UTF-8 LANGUAGE=nl:en
ln -sf /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime
echo Europe/Amsterdam > /etc/timezone
cat > /etc/default/keyboard <<'KBD'
XKBMODEL="pc105"
XKBLAYOUT="us"
XKBVARIANT="altgr-intl"
XKBOPTIONS=""
BACKSPACE="guess"
KBD

echo "--- Pinned taskbar programs (copied into every new user's settings)"
for pair in 2:firefox-esr.desktop 3:thunar.desktop; do
    dir="/etc/skel/.config/xfce4/panel/launcher-${pair%%:*}"
    mkdir -p "$dir"
    cp "/usr/share/applications/${pair#*:}" "$dir/"
done

echo "--- User account with automatic login"
groupadd -f autologin
groupadd -f nopasswdlogin
useradd -m -s /bin/bash -c "Gebruiker" \
    -G sudo,audio,video,render,input,plugdev,netdev,bluetooth,autologin,nopasswdlogin \
    "$USER_NAME"
echo "$USER_NAME:$USER_PASSWORD" | chpasswd
passwd -l root

echo "--- Windows-program support (Hangover = Wine for ARM)"
if ls /var/cache/venster/hangover/*.deb >/dev/null 2>&1; then
    apt-get install -y --no-install-recommends /var/cache/venster/hangover/*.deb
    /usr/local/lib/venster/configure-wine.sh
    echo "Hangover installed."
else
    echo "Hangover is not bundled; it will be installed on first use."
fi

echo "--- Default applications"
update-alternatives --set x-www-browser /usr/bin/firefox-esr || true
update-alternatives --set x-session-manager /usr/bin/xfce4-session || true
update-alternatives --set x-window-manager /usr/bin/xfwm4 || true
update-alternatives --set x-terminal-emulator /usr/bin/xfce4-terminal.wrapper || true
update-desktop-database -q /usr/share/applications || true
gtk-update-icon-cache -q -f /usr/share/icons/hicolor || true

echo "--- Services"
systemctl enable venster-firstboot.service
systemctl enable NetworkManager.service
systemctl enable lightdm.service
systemctl enable zramswap.service
systemctl set-default graphical.target
# Things a desktop Pi does not need at boot.
systemctl disable apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
systemctl mask systemd-networkd-wait-online.service NetworkManager-wait-online.service 2>/dev/null || true

echo "--- Kernel, initramfs and boot files"
update-initramfs -u -k all

echo "--- Tidy up"
apt-get clean
rm -rf /var/lib/apt/lists/*
rm -f /etc/ssh/ssh_host_* 2>/dev/null || true
: > /etc/machine-id
rm -f /var/lib/dbus/machine-id
