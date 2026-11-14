#!/bin/bash
# Build the Venster OS image for the Raspberry Pi 4.
#
# The result is a compressed disk image (venster-os-<date>.img.xz) that you
# write to an SD card with Raspberry Pi Imager.
#
# Requirements on the build machine (Debian or Ubuntu, run as root):
#   apt install mmdebstrap qemu-user-static binfmt-support parted \
#               dosfstools mtools e2fsprogs xz-utils python3 curl
# qemu-user-static is only needed when the build machine is not arm64.
#
# Usage: sudo ./build.sh [output-directory]
# Set KEEP_WORK=1 to keep the root file system for inspection.
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
    mountpoint -q "$ROOTFS/boot/firmware" && umount -l "$ROOTFS/boot/firmware"
    if [ -n "${KEEP_WORK:-}" ]; then
        echo "Work directory kept: $WORK"
    else
        rm -rf "$WORK"
    fi
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
# The partitions are filled straight from the directories (mkfs.ext4 -d and
# mcopy), so no loop devices or mounts are needed.
ROOT_MB=$(( $(du -sm --apparent-size "$ROOTFS" | cut -f1) * 115 / 100 + FREE_SPACE_MB ))
IMAGE="$WORK/$IMAGE_NAME.img"

truncate -s "${BOOT_SIZE_MB}M" "$WORK/boot.part"
mkfs.vfat -F 32 -n RASPIFIRM "$WORK/boot.part"
mcopy -s -i "$WORK/boot.part" "$FIRMWARE"/* ::

truncate -s "${ROOT_MB}M" "$WORK/root.part"
mkfs.ext4 -q -L RASPIROOT -O ^orphan_file -d "$ROOTFS" "$WORK/root.part"

truncate -s "$(( 4 + BOOT_SIZE_MB + ROOT_MB ))M" "$IMAGE"
parted -s "$IMAGE" mklabel msdos
parted -s "$IMAGE" mkpart primary fat32 4MiB "$(( 4 + BOOT_SIZE_MB ))MiB"
parted -s "$IMAGE" mkpart primary ext4 "$(( 4 + BOOT_SIZE_MB ))MiB" 100%
parted -s "$IMAGE" set 1 lba on
dd if="$WORK/boot.part" of="$IMAGE" bs=1M seek=4 conv=notrunc,sparse status=none
dd if="$WORK/root.part" of="$IMAGE" bs=1M seek=$(( 4 + BOOT_SIZE_MB )) conv=notrunc,sparse status=none
rm -f "$WORK/boot.part" "$WORK/root.part"

log "Compressing the image"
xz -T0 -6 -c "$IMAGE" > "$OUT_DIR/$IMAGE_NAME.img.xz"
( cd "$OUT_DIR" && sha256sum "$IMAGE_NAME.img.xz" > "$IMAGE_NAME.img.xz.sha256" )

log "Done: $OUT_DIR/$IMAGE_NAME.img.xz"
ls -lh "$OUT_DIR/$IMAGE_NAME.img.xz"
