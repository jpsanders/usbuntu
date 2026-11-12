# usbuntu

## NAME

usbuntu - install a complete, bootable Ubuntu system on a USB stick from an ISO, straight from the terminal

## SYNOPSIS

```
sudo usbuntu install ISO --username NAME [options]
sudo usbuntu inspect ISO [--flavor full|minimal] [--language CODE]
sudo usbuntu verify DEVICE
usbuntu devices [--json]
usbuntu guide
usbuntu man [--install | --raw]
usbuntu --version
```

## DESCRIPTION

usbuntu is not `dd`. A raw ISO copy gives a live session that forgets everything, and a normal install needs an
installer boot first. usbuntu skips both: it unpacks the ISO's own system layers onto the stick, configures the
system in a chroot, installs the genuine signed boot chain and verifies it, and leaves a full Ubuntu that keeps its
files, takes updates and installs software. It boots on any UEFI machine, with Secure Boot on or off.

It needs root for `install`, `inspect` and `verify`, a stick of at least 8 GiB, and the host tools `parted`,
`mkfs.fat`, `mkfs.ext4`, `rsync`, `blkid` and `file`. Ubuntu desktop ISOs from 24.04 on are supported; the pipeline
was verified end to end against the 26.04.1 desktop ISO.

## COMMANDS

| Command | What it does |
| --- | --- |
| `install` | Wipe the stick after a typed `WIPE`, then install Ubuntu from the ISO. About twenty minutes. |
| `inspect` | Mount the ISO and show the layer chain an install would copy. Writes nothing. |
| `verify` | Check the boot chain of a stick that already holds an install: kernels, root UUID, signed binaries. |
| `devices` | List every disk and say which ones usbuntu would accept as a target, and why the rest are refused. |
| `guide` | Print this manual as Markdown, for people and agents. |
| `man` | Show this manual as a man page. `--install` puts it where `man usbuntu` finds it. |

## INSTALL OPTIONS

| Option | Meaning |
| --- | --- |
| `--username NAME` | The account the new system logs in with. Required. |
| `--password P` | The starting password. Default: generated and printed at the end. |
| `--no-force-password-change` | Keep the starting password; by default the first login asks for a new one. |
| `--hostname NAME` | The machine name. Default: usb-ubuntu. |
| `--flavor full` | `full` desktop or the `minimal` one. Default: full. |
| `--language CODE` | Language layers to include, such as `en` or `pt`. Default: en. |
| `--remove-snap` | Purge snapd and hold it back. Firefox and the Snap Store go with it. |
| `--packages LIST` | Extra apt packages, comma separated, such as `curl,vim,git`. |
| `--with NAME` | A bundled extra: `opencode`, `claude-code` or `build-tools`. Repeatable. |
| `--device /dev/sdX` | The target disk. Default: the one removable USB disk found; with several, this is required. |
| `--yes` | Do not ask for `WIPE`. Only for a run the user asked to be unattended. |
| `--dry-run` | Print the plan and the target, write nothing. |

## HOW IT WORKS

Ubuntu desktop ISOs ship as a stack of squashfs overlay layers: a minimal base, a standard desktop layer, thin
language layers, and two kinds of layer that must never reach an installed stick. usbuntu mounts the right chain with
overlayfs and copies the merged view with `rsync -aHAX`, the same path the official installer takes, minus the
installer.

```
ISO -> squashfs layer chain -> overlayfs merged view -> rsync -> stick
                                           chroot: apt, account, GRUB
                                           ESP: signed shim and signed GRUB, md5 verified
```

- **Layer selection.** The live layer belongs to the live session only, and the enhanced secure boot layers hand the
  boot chain to snapd. usbuntu keeps the classic GRUB path and always leaves both out.
- **overlayfs, not unsquashfs.** Extracting stacked layers one by one fails on hardlinks across layers.
- **A truthful mtab.** Chrooted GRUB tools read the mount table; usbuntu writes one that names the stick.
- **The signed binaries, verified.** After every install the genuine signed shim and GRUB are copied from the target's
  own packages and checked with md5, because a chrooted `grub-install` can write an unsigned image that boots to a
  bare `grub>` prompt.

## SAFETY

- usbuntu refuses any disk that is not on USB, not removable, smaller than 8 GiB, or holds the running system (has
  `/`, `/boot`, `/boot/efi`, `/usr`, `/var`, `/home` or swap on it). `usbuntu devices` shows the same verdicts.
- With more than one acceptable disk, it refuses to guess and asks for `--device`.
- The wipe needs the user to type `WIPE`, unless `--yes` was given.
- The password reaches the new system through a pipe, never a file or a log. Omit `--password` to be prompted.

## RESUMING AFTER A FAILURE

A completed system copy is marked on the stick (`.usbuntu-install.json`), and the next run resumes from it instead of
copying about 7 GB again. The desktop re-mounts the stick between runs, so before a retry stop the monitor and unmount
the failed run's leftovers, children first:

```
systemctl --user stop gvfs-udisks2-volume-monitor.service
sudo umount /mnt/usbuntu-install/target/dev/pts /mnt/usbuntu-install/target/run \
    /mnt/usbuntu-install/target/sys /mnt/usbuntu-install/target/proc \
    /mnt/usbuntu-install/target/dev /mnt/usbuntu-install/target/boot/efi /mnt/usbuntu-install/target
```

With the leftovers mounted the resume probe fails, and the run starts fresh: it wipes the stick and copies again.

## FILES

`/var/log/usbuntu.log` gets every command, phase message and traceback of each root run, and the real `apt` error
when the chroot fails. Read it before anything else after a failure. `~/.local/share/man/man1/usbuntu.1` is where
`man --install` puts the man page.

## EXIT STATUS

0 on success. Non zero when the arguments are wrong, the user declines the wipe, root is missing, or a step fails;
the reason is printed and logged.

## EXAMPLES

See which disks are safe targets, plan, then install:

```
usbuntu devices
sudo usbuntu install ubuntu-26.04.1-desktop-amd64.iso --username james --device /dev/sdb --dry-run
sudo PYTHONDONTWRITEBYTECODE=1 usbuntu install ubuntu-26.04.1-desktop-amd64.iso --username james --device /dev/sdb
sudo usbuntu verify /dev/sdb
```

Reboot, press the firmware boot menu key (often F12) and pick the stick.

## FOR AGENTS

- Never choose the target disk silently. Run `usbuntu devices --json`, read the accepted disks' model, size and
  device back to the user, and get an explicit go ahead. With more than one, always pass `--device`.
- The `WIPE` confirmation belongs to the user. Pass `--yes` only when the user asked for an unattended run.
- Never echo a password: omit `--password` and let the tool prompt, or use the generated one it prints.
- Prefix every sudo run with `PYTHONDONTWRITEBYTECODE=1`, or root writes bytecode into the user's tool environment.
- Verify the ISO against its official `SHA256SUMS` first; usbuntu does it automatically when the file sits beside it.
- After any failure, read `/var/log/usbuntu.log`. A good run ends with `DONE`, and `verify` ends with
  `all boot checks passed`.

## SEE ALSO

https://github.com/jpsanders/usbuntu

## AUTHOR

James Phillip Sanders, https://jamesphillipsanders.com
