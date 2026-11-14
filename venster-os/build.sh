#!/bin/bash
# Build the Venster OS image for the Raspberry Pi 4.
#
# The result is a compressed disk image (venster-os-<date>.img.xz) that you
# write to an SD card with Raspberry Pi Imager.
#
# Requirements on the build machine (Debian or Ubuntu, run as root):
#   apt install mmdebstrap qemu-user-static binfmt-support parted \
#               dosfstools e2fsprogs xz-utils python3 curl rsync
# qemu-user-static is only needed when the build machine is not arm64.
#
# Usage: sudo ./build.sh [output-directory]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$(realpath -m "${1:-$HERE/out}")"
WORK="$(mktemp -d "${TMPDIR:-/var/tmp}/venster-build.XXXXXX")"
ROOTFS="$WORK/rootfs"
FIRMWARE="$WORK/firmware"
SUITE=trixie
MIRROR="${MIRROR:-https://deb.debian.org/debian}"
IMAGE_NAME="venster-os-$(date +%Y%m%d)"
BOOT_SIZE_MB=512
FREE_SPACE_MB=600    # room left on the root partition before first-boot growth

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

cleanup() {
    set +e
    for mountpoint in "$WORK/mnt/boot/firmware" "$WORK/mnt" "$ROOTFS/boot/firmware"; do
        mountpoint -q "$mountpoint" && umount -l "$mountpoint"
    done
    [ -n "${LOOP:-}" ] && losetup -d "$LOOP"
    rm -rf "$WORK"
}
trap cleanup EXIT

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this script as root (sudo ./build.sh)." >&2
    exit 1
fi

mkdir -p "$OUT_DIR" "$FIRMWARE"

log "Generating the Venster window theme"
python3 "$HERE/tools/make-xfwm4-theme.py" "$WORK/theme/Venster"

log "Downloading Windows-program support (Hangover)"
"$HERE/tools/fetch-hangover.sh" "$WORK/hangover"

PACKAGES="$(grep -v '^\s*#' "$HERE/packages.txt" | xargs | tr ' ' ',')"

log "Building the Debian $SUITE (arm64) root file system"
# The firmware partition is prepared in a separate directory that is
# bind-mounted at /boot/firmware, so the raspi-firmware package fills it.
mmdebstrap \
    --architectures=arm64 \
    --variant=apt \
    --components="main contrib non-free non-free-firmware" \
    --include="$PACKAGES" \
    --setup-hook='mkdir -p "$1/boot/firmware" "$1/etc/default"' \
    --setup-hook="mount --bind '$FIRMWARE' \"\$1/boot/firmware\"" \
    --customize-hook="cp -a '$HERE/overlay/.' \"\$1/\"" \
    --customize-hook="mkdir -p \"\$1/usr/share/themes\" && cp -a '$WORK/theme/Venster' \"\$1/usr/share/themes/\"" \
    --customize-hook="mkdir -p \"\$1/var/cache/venster/hangover\" && cp -a '$WORK/hangover/.' \"\$1/var/cache/venster/hangover/\"" \
    --customize-hook="python3 '$HERE/tools/patch-xfce-defaults.py' \"\$1\"" \
    --customize-hook='chroot "$1" /bin/bash /usr/local/lib/venster/setup-in-chroot.sh' \
    --customize-hook='rm -rf "$1/var/cache/venster"' \
    --customize-hook='umount "$1/boot/firmware"' \
    "$SUITE" "$ROOTFS" "$MIRROR"

for required in config.txt cmdline.txt start4.elf bcm2711-rpi-4-b.dtb; do
    if [ ! -e "$FIRMWARE/$required" ]; then
        echo "The firmware partition is missing $required; the build failed." >&2
        exit 1
    fi
done

log "Creating the disk image"
ROOT_MB=$(( $(du -sm --apparent-size "$ROOTFS" | cut -f1) * 115 / 100 + FREE_SPACE_MB ))
IMAGE="$WORK/$IMAGE_NAME.img"
truncate -s "$(( BOOT_SIZE_MB + ROOT_MB + 4 ))M" "$IMAGE"
parted -s "$IMAGE" mklabel msdos
parted -s "$IMAGE" mkpart primary fat32 4MiB "$(( BOOT_SIZE_MB + 4 ))MiB"
parted -s "$IMAGE" mkpart primary ext4 "$(( BOOT_SIZE_MB + 4 ))MiB" 100%
parted -s "$IMAGE" set 1 lba on

LOOP="$(losetup --show -f -P "$IMAGE")"
# Some build machines do not create the partition devices automatically.
if [ ! -e "${LOOP}p1" ]; then
    partx -a "$LOOP" || true
fi
mkfs.vfat -F 32 -n RASPIFIRM "${LOOP}p1"
mkfs.ext4 -q -L RASPIROOT -O ^orphan_file "${LOOP}p2"

mkdir -p "$WORK/mnt"
mount "${LOOP}p2" "$WORK/mnt"
rsync -aHAX --numeric-ids "$ROOTFS/" "$WORK/mnt/"
mkdir -p "$WORK/mnt/boot/firmware"
mount "${LOOP}p1" "$WORK/mnt/boot/firmware"
cp -r "$FIRMWARE/." "$WORK/mnt/boot/firmware/"
sync
umount "$WORK/mnt/boot/firmware"
umount "$WORK/mnt"
losetup -d "$LOOP"
LOOP=""

log "Compressing the image"
xz -T0 -6 -c "$IMAGE" > "$OUT_DIR/$IMAGE_NAME.img.xz"
( cd "$OUT_DIR" && sha256sum "$IMAGE_NAME.img.xz" > "$IMAGE_NAME.img.xz.sha256" )

log "Done: $OUT_DIR/$IMAGE_NAME.img.xz"
ls -lh "$OUT_DIR/$IMAGE_NAME.img.xz"
