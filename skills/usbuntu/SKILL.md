---
name: usbuntu
description: Install a complete, bootable, persistent Ubuntu desktop on a USB stick from an ISO with the usbuntu CLI (needs root). Use when the user asks to put Ubuntu onto a USB drive, to make a portable Ubuntu that keeps its files, to verify or troubleshoot such a stick, or to resume a failed install. Covers safe device selection, ISO verification, the wipe confirmation, resuming, verifying and reading /var/log/usbuntu.log.
---

# usbuntu: a full Ubuntu on a USB stick, straight from the terminal

usbuntu unpacks the ISO's own squashfs layers onto a USB stick (a 1 GiB ESP and an ext4 root), configures the system
in a chroot (GRUB, the user account), places the genuine signed shim and GRUB on the ESP with md5 verification, and
leaves a bootable, persistent Ubuntu. It is not `dd`: the result keeps files and takes updates.

Requirements: Python 3.14 or later on the host (uv fetches one if needed), root, a USB stick of 8 GiB or more, a
machine that boots UEFI, and the host tools `parted`, `mkfs.fat`, `mkfs.ext4`, `rsync`, `blkid` and `file`.

## Rules for the agent

1. **Never choose the target disk silently.** Run `usbuntu devices --json` (no root needed). It lists every disk with
   `accepted` and `refused_because`: usbuntu refuses disks that are not USB, not removable, smaller than 8 GiB, or
   that hold the running system. Read the accepted disk's device, model and size back to the user and get an explicit
   go ahead before anything destructive. When more than one disk is accepted, always pass `--device /dev/sdX`.
2. **The wipe confirmation belongs to the user.** The tool asks them to type `WIPE`. Pass `--yes` only for a run the
   user explicitly asked to be unattended.
3. **Never echo a password.** Omit `--password` and let the tool prompt on the terminal, or accept the generated
   password printed at the end. Never write it to shell history or logs.
4. **Prefix every sudo run with `PYTHONDONTWRITEBYTECODE=1`.** Root runs otherwise write bytecode caches into the
   tool's own environment, which later breaks `uv tool install --force` with permission errors.
5. **Verify the ISO first.** With the official `SHA256SUMS` beside it the tool verifies it by itself; otherwise run
   `sha256sum` on the ISO and compare with Ubuntu's published sum before the run.
6. **Read `/var/log/usbuntu.log` after any failure.** It records every command, phase message and traceback, and,
   when the chroot fails, the real `apt` error.

## Install the tool

```sh
uv tool install git+https://github.com/jpsanders/usbuntu@1.2.0
```

To update later: the same command with `--force` and the newer tag.

## Run

```sh
usbuntu devices                                     # which disks are safe targets
sudo usbuntu inspect ubuntu-26.04.1-desktop-amd64.iso   # which layers an install would copy

# 1. plan without writing anything
sudo ~/.local/bin/usbuntu install ubuntu-26.04.1-desktop-amd64.iso --device /dev/sdX --username NAME --dry-run

# 2. the real run, about twenty minutes
sudo PYTHONDONTWRITEBYTECODE=1 ~/.local/bin/usbuntu install ubuntu-26.04.1-desktop-amd64.iso \
    --device /dev/sdX --username NAME

# 3. prove the boot chain
sudo ~/.local/bin/usbuntu verify /dev/sdX
```

```text
ISO -> verify -> partition (1 GiB ESP + ext4 root) -> copy layers -> configure (hostname, locale, timezone)
    -> chroot (apt: GRUB, kernel, account) -> ESP: signed shim + GRUB, md5 verified -> done
```

`usbuntu guide` prints the full manual with every flag.

## Flags that matter

| Flag | Purpose | Default |
| --- | --- | --- |
| `--username NAME` | the account to create | required |
| `--device /dev/sdX` | pin the target disk | the one accepted disk; required when there are several |
| `--hostname NAME` | machine name of the new system | `usb-ubuntu` |
| `--password P` | starting password | generated, printed at the end |
| `--no-force-password-change` | keep the starting password | first login forces a change |
| `--flavor full\|minimal` | desktop size | `full` |
| `--language en` | language layers | `en` |
| `--remove-snap` | purge snapd (Firefox goes with it) | snap kept |
| `--packages curl,vim,git` | extra apt packages | none |
| `--with opencode` | bundled extras, repeatable: `opencode`, `claude-code`, `build-tools` | none |
| `--yes` | skip the `WIPE` prompt | asks |
| `--dry-run` | print the plan, write nothing | off |

## Running again after a failure

A completed copy is marked on the stick (`.usbuntu-install.json`) and the next run resumes from it, skipping the copy
of about 7 GB. But a failed run leaves the stick mounted, and the desktop mounts it again besides. Before the retry:

```sh
# stop the desktop's automount monitor (user scope; it returns after the next login)
systemctl --user stop gvfs-udisks2-volume-monitor.service

# unmount the failed run's leftovers, children first
sudo umount /mnt/usbuntu-install/target/dev/pts /mnt/usbuntu-install/target/run \
    /mnt/usbuntu-install/target/sys /mnt/usbuntu-install/target/proc \
    /mnt/usbuntu-install/target/dev /mnt/usbuntu-install/target/boot/efi \
    /mnt/usbuntu-install/target
```

**Missing this step is the costliest mistake available:** with the leftovers mounted, the resume probe fails and the
command starts fresh, which wipes the stick and copies everything again.

## Troubleshooting

- `wipefs ... returned status 1` or "device busy" early on: something mounted the stick again, most often the gvfs
  monitor. Stop the service, unmount by device, retry.
- `CalledProcessError` with exit status 100 from the chroot: `apt` failed. Read the printed stderr and the log.
- An error that names a missing file or a signed binary: update the tool (`uv tool install --force`), then retry.
- A good run ends with `DONE - full Ubuntu installed on ...`, and `verify` ends with `all boot checks passed`. Then
  reboot, press the firmware boot menu key (often F12) and pick the stick.

## Known good reference

The pipeline was verified end to end (a full install with `--remove-snap`, a resume over several stages, a clean
`verify`) against `ubuntu-26.04.1-desktop-amd64.iso` on a 16 GiB SanDisk Cruzer Blade.
