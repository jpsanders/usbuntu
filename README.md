# usbuntu

Install a complete, bootable Ubuntu system on a USB stick from an ISO, straight from the terminal.

`usbuntu` is not `dd`. A raw ISO copy gives you a live session that forgets everything. A normal install
needs an installer boot first. usbuntu skips both: it unpacks the ISO's own system layers straight onto
the stick, installs the bootloader, and hands you a full Ubuntu that keeps its files, takes updates and
installs software - a portable machine in your pocket.

```bash
sudo usbuntu install ubuntu-26.04.1-desktop-amd64.iso --username james --hostname usb-ubuntu
```

Type `WIPE` at the prompt, wait about twenty minutes, reboot, press F12 and pick the stick.

## Install

It needs Python 3.12 or later, on any Linux machine that can mount things: Ubuntu, Debian and friends work
out of the box.

```bash
uv tool install git+https://github.com/jpsanders/usbuntu
```

`pipx install git+https://github.com/jpsanders/usbuntu` works too.

## Use

```bash
sudo usbuntu install ubuntu.iso --username james                    # everything else optional
sudo usbuntu install ubuntu.iso --username james --dry-run          # show the plan, touch nothing
sudo usbuntu inspect ubuntu.iso                                     # which layers an ISO would install
sudo usbuntu verify /dev/sda                                       # check a stick's boot chain
```

Every variable:

| Variable | Flag | Default |
| --- | --- | --- |
| Account name | `--username james` | required |
| Starting password | `--password secret` | generated, printed at the end |
| Force a new password at first login | `--no-force-password-change` | forced |
| Machine name | `--hostname my-stick` | `usb-ubuntu` |
| Full or reduced desktop | `--flavor full\|minimal` | `full` |
| Language layers | `--language en` | `en` |
| Snap | `--remove-snap` | kept |
| Extra apt packages | `--packages curl,vim,git` | none |
| Bundled extras | `--with opencode`, `--with claude-code`, `--with build-tools` | none |
| Target disk | `--device /dev/sda` | auto-detected |
| Unattended | `--yes` | asks for `WIPE` |

The password is written to the new system through a pipe, never to a file and never to a log, and a fresh
install always asks for its own password at first login.

## How it works

Ubuntu desktop ISOs since 24.04 ship as a stack of squashfs overlay layers: a `minimal` base, a `standard`
full-desktop layer, thin language layers, and two kinds of layer that must never reach an installed stick.
usbuntu mounts the right chain with overlayfs and copies the merged view over with `rsync -aHAX` - the
same path the official installer takes, minus the installer.

```text
ISO  ->  squashfs layer chain  ->  overlayfs merged view  ->  rsync  ->  stick
                                                          chroot: apt, account, GRUB
                                                          ESP: signed shim + signed GRUB, md5-verified
```

Every step in that pipeline exists because its absence broke a real install:

1. **Layer selection.** The `live` layer only belongs to the live session. The `enhanced-secureboot` layers
   whiteout the deb kernel from `/boot`, because Ubuntu 26.04 can hand the boot chain to snapd
   (`boot-managed-by-snapd`). usbuntu keeps the classic GRUB path and always excludes both.
2. **overlayfs, not unsquashfs.** Extracting stacked layers one by one with unsquashfs dies on
   cross-layer hardlinks. Overlayfs consumes whiteouts correctly and rsync preserves what it merges.
3. **A truthful `/etc/mtab`.** Chrooted GRUB tools read the host's mount table and probe the wrong root.
   usbuntu writes a real `mtab` naming the stick before `update-grub` runs.
4. **The signed binaries, verified.** `grub-install` in a chroot can silently write its own unsigned GRUB
   image to `EFI/BOOT/BOOTX64.EFI`, which boots to a bare `grub>` prompt. After every install usbuntu
   copies the genuine signed shim and GRUB from the target's own packages and verifies them with md5.
   `sudo usbuntu verify /dev/sda` re-runs the same checks on any stick, any time.

## Notes

* The stick must be at least 8 GiB and the machine must mount with UEFI. The result boots with Secure Boot
  on or off, because the chain is the same signed shim Ubuntu ships.
* `--remove-snap` purges snapd and holds it back. Firefox and the Snap Store go with it; install a deb
  browser in `--packages` if you want one.
* A failed run costs nothing: the completed system copy is marked on the stick and the next run resumes
  from it instead of re-copying 7 GB.
* `make checks` runs the same eight checks CI runs: black, isort, editorconfig, darglint, flake8, mypy
  strict, bandit and pytest with coverage.

## Layout

```text
src/usbuntu/       the package, with py.typed so type checkers trust its hints
tests/usbuntu/     pytest tests, mirroring the package
.github/workflows/ CI: lint, then tests on Python 3.12, 3.13 and 3.14
Makefile           every command in this file
```

## Versions

There is no version number in the code. setuptools_scm reads it from git. Tag a commit `v0.1.0` and
`make build` writes a 0.1.0 wheel to `build/dist`.

Issues and pull requests are welcome.

[James Phillip Sanders](https://jamesphillipsanders.com)

## License

MIT
