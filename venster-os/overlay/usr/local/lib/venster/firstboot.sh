#!/bin/bash
# First boot: grow the root partition and file system to fill the SD card.
set -u
ROOT_DEV="$(findmnt -n -o SOURCE /)"
DISK="/dev/$(lsblk -no PKNAME "$ROOT_DEV")"
PART_NUM="$(cat "/sys/class/block/$(basename "$ROOT_DEV")/partition")"
growpart "$DISK" "$PART_NUM" || true
resize2fs "$ROOT_DEV" || true
mkdir -p /var/lib/venster
touch /var/lib/venster/firstboot-done
