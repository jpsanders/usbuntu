---
name: usbuntu
description: >
  Install a complete, bootable Ubuntu desktop on a USB stick from an ISO with the usbuntu CLI (needs
  root). Use when the user asks to put Ubuntu onto a USB drive, to verify or troubleshoot such an
  install, or to resume a failed one. Covers safe device selection, ISO verification, the wipe
  confirmation, resume handling, verification, and reading /var/log/usbuntu.log.
---

# usbuntu — full Ubuntu on a USB stick, straight from the terminal

usbuntu unpacks the ISO's own squashfs layers onto a USB stick (1 GiB ESP + ext4 root), configures the
system in a chroot (GRUB, user account), places the genuine signed shim and GRUB on the ESP with md5
verification, and leaves a bootable, persistent Ubuntu. It is not `dd`: the result keeps files and
takes updates. Requirements: Python 3.12+ on the host, root, an 8 GiB or larger stick with UEFI boot,
and the host tools `parted`, `mkfs.fat`, `mkfs.ext4`, `rsync`, `blkid`, `file`.

## Rules for the agent

1.  **Never choose the target disk silently.** List candidates with:

    ```bash
    lsblk -J -b -o NAME,SIZE,TYPE,TRAN,RM,FSTYPE,LABEL,MODEL,MOUNTPOINT
    ```

    Candidates are USB disks (``tran: usb``, ``rm: true``) that are not the running system's root.
    Read the model, size, label and current mounts back to the user and get an explicit go-ahead
    before anything destructive. When several removable disks exist, or the running system itself
    boots from USB, insist on the exact target: `--device /dev/sdX`.
2.  **The wipe confirmation belongs to the user.** The tool asks them to type `WIPE`. Only pass
    `--yes` for a run the user explicitly requested unattended.
3.  **Never echo a password.** Omit `--password` and let the tool prompt on the terminal, or accept
    the generated password printed at the end. Never write it to shell history or logs.
4.  **Prefix every sudo run with `PYTHONDONTWRITEBYTECODE=1`.** Root runs otherwise write bytecode
    caches into the tool's own installation, which later breaks `uv tool install --force` with
    permission errors (root-owned `__pycache__` inside a user-owned venv).
5.  **Verify the ISO first.** It should sit next to its official `SHA256SUMS`; the tool verifies it
    automatically in that case. Otherwise verify manually before the run:
    `sha256sum ubuntu-26.04.1-desktop-amd64.iso`.
6.  **Read `/var/log/usbuntu.log` after any failure.** It records every command, every phase message,
    the full traceback, and - when the chroot fails - the real `apt` error. On-disk leftovers
    (apt history, dpkg status, `boot/grub/grub.cfg`) corroborate what reached what.

## Install

```bash
uv tool install git+https://github.com/jpsanders/usbuntu
# from an existing clone instead: make init

# 1. plan without writing anything:
sudo ~/.local/bin/usbuntu install /path/to/ubuntu-26.04.1-desktop-amd64.iso \
    --device /dev/sdX --username NAME --dry-run

# 2. the real run:
sudo PYTHONDONTWRITEBYTECODE=1 ~/.local/bin/usbuntu install \
    /path/to/ubuntu-26.04.1-desktop-amd64.iso --device /dev/sdX --username NAME
```

```text
ISO -> verify -> partition (1 GiB ESP + ext4 root) -> copy layers -> configure (hostname, locale,
timezone) -> chroot (apt: GRUB, kernel, account) -> ESP: signed shim + GRUB, md5-verified -> done.
```

## Flags that matter

| Flag | Purpose | Default |
| --- | --- | --- |
| `--username NAME` | the account to create | required |
| `--device /dev/sdX` | pin the target disk | auto-detect (risky with many disks) |
| `--hostname NAME` | machine name of the new system | `usb-ubuntu` |
| `--password P` | starting password | generated, printed at the end |
| `--no-force-password-change` | keep the starting password | first login forces a change |
| `--flavor full\|minimal` | desktop size | `full` |
| `--language en` | language layers | `en` |
| `--remove-snap` | purge snapd (Firefox goes with it) | snap kept |
| `--packages curl,vim,git` | extra apt packages | none |
| `--with opencode` | bundled extras; repeatable (`opencode`, `claude-code`, `build-tools`) | none |
| `--yes` | skip the `WIPE` prompt | asks |
| `--dry-run` | print the plan, write nothing | - |

## Re-running after a failure

A completed copy is marked on the stick (`.usbuntu-install.json`) and the next run resumes from it,
skipping the ~7 GB copy. But a failed run leaves the stick mounted, and the desktop environment
re-mounts it again besides. Before the retry:

```bash
# stop the desktop auto-mount monitor (user scope; returns after next login):
systemctl --user stop gvfs-udisks2-volume-monitor.service

# unmount the failed run's leftovers, children first:
sudo umount /mnt/usbuntu-install/target/dev/pts /mnt/usbuntu-install/target/run \
    /mnt/usbuntu-install/target/sys /mnt/usbuntu-install/target/proc \
    /mnt/usbuntu-install/target/dev /mnt/usbuntu-install/target/boot/efi \
    /mnt/usbuntu-install/target
```

**Missing this step is the costliest mistake available**: with the leftovers mounted, the resume
probe fails, the command falls back to "start fresh", which wipes the stick and re-copies ~7 GB.

## Verify

```bash
sudo ~/.local/bin/usbuntu verify /dev/sdX
```

Reports missing kernels, wrong root UUID in `grub.cfg`, or mismatched ESP binaries. The stick then
boots by the firmware boot menu key (often F12) with Secure Boot on or off.

## Troubleshooting checklist

*   `wipefs ... returned status 1` or "device busy" early on: something re-mounted the stick, most
    often the gvfs monitor. Stop the service, unmount by device, retry.
*   `FileNotFoundError: ... /etc/mtab` in `_configure_target`: fixed in 1.0.0. Update the tool:
    `uv tool install git+https://github.com/jpsanders/usbuntu --force`.
*   CalledProcessError exit status 100 from the chroot: `apt` failed. Read the printed stderr and the
    log; the live image's own `file:///cdrom` source aborting `apt-get update` was fixed in 1.0.0.
*   `BootError: signed binary not found ... mmx64.efi.signed`: fixed in 1.0.0 (26.04 ships it as
    `mmx64.efi`). Update the tool.
*   Successful log ends with `DONE - full Ubuntu installed on ...`; a `verify` run ending
    `all boot checks passed` is the final word.

## Known-good reference

The pipeline was verified end to end (full install with `--remove-snap`, multi-stage resume, clean
`verify`) against `ubuntu-26.04.1-desktop-amd64.iso` on a 16 GiB SanDisk Cruzer Blade. See the `1.0.0`
release notes for the four 26.04 fixes this release carries.
