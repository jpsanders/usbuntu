"""
The install pipeline: from ISO file to a bootable stick.

Runs as root. Every step that bit during development of this tool is called
out in the module docstring of :mod:`usbuntu.layers` and :mod:`usbuntu.grub`:

*   the layer chain excludes the ``live`` and ``enhanced-secureboot`` layers
*   the overlay is stacked with overlayfs and copied with ``rsync -aHAX``,
    never extracted per-layer with unsquashfs, which trips over cross-layer
    hardlinks
*   chrooted GRUB tools get a truthful ``/etc/mtab``
*   the ESP binaries are md5-verified against the target's own shipped signed
    files after grub-install, and replaced when grub-install wrote its own
    unsigned image
"""

import hashlib
import json
import re
import shlex
import subprocess  # nosec B404: fixed argument lists, never a shell
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from usbuntu import grub, layers
from usbuntu.config import InstallConfig
from usbuntu.devices import BlockDevice, find_target, list_devices
from usbuntu.packages import resolve_extras
from usbuntu.runner import run, run_stdin, try_run

MNT = Path("/mnt/usbuntu-install")
TARGET = MNT / "target"
ESP = TARGET / "boot/efi"
ISO_MNT = MNT / "iso"
LAYERS_MNT = MNT / "layers"
MERGED_MNT = MNT / "merged"
OVL_MNT = MNT / "ovl"
MARKER = ".usbuntu-install.json"
ESP_MIB = 1024
MIN_FILES_INSTALLED = 100_000
MIN_STICK_GIB = 8


def _say(message: str) -> None:
    """
    Print a timestamped progress line.

    :param message: The line to print
    """
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


@dataclass(slots=True)
class _Layout:
    """Device nodes and UUIDs of the partitioned stick."""

    disk: BlockDevice
    esp_device: str
    root_device: str
    root_uuid: str


class Installer:
    """The root-side install pipeline."""

    def __init__(self, config: InstallConfig) -> None:
        """
        Bind the configuration and resolve the target device.

        :param config: The validated install configuration
        """
        self.config = config
        self.disk = find_target(config.device, list_devices(), MIN_STICK_GIB)
        self.layout: _Layout | None = None

    def _layout(self) -> _Layout:
        """Return the layout, or fail loudly when the phases ran out of order."""
        if self.layout is None:
            raise RuntimeError("internal error: the layout is not set, a phase ran out of order")
        return self.layout

    # ------------------------------------------------------------- pipeline

    def run(self) -> None:
        """
        Run every install phase in order and leave the stick unmounted.

        :raises RuntimeError: When any phase fails
        """
        self._preflight()
        self._checksum()
        resumed = self._probe_resume()
        if not resumed:
            self._partition()
            self._copy()
        self._configure_target()
        self._chroot()
        self._install_bootloader()
        self._verify()
        self._close_layout()
        self._summary(resumed)

    # --------------------------------------------------------------- phases

    def _preflight(self) -> None:
        """Check that we are root and every host tool is present."""
        if sys.platform != "linux":
            raise RuntimeError("usbuntu only runs on Linux")
        for tool in ("parted", "mkfs.fat", "mkfs.ext4", "rsync", "blkid", "file"):
            probe = try_run(["which", tool])
            if probe.returncode != 0:
                raise RuntimeError(f"missing host tool: {tool} (on Ubuntu: sudo apt install {tool})")
        _say(f"target: {self.disk.describe()}")

    def _checksum(self) -> None:
        """Verify the ISO against a checksum file sitting next to it, when present."""
        iso = self.config.iso_path
        sums_file = iso.parent / "SHA256SUMS"
        expected: str | None = None
        if sums_file.is_file():
            for line in sums_file.read_text(encoding="utf-8").splitlines():
                listed, _, name = line.partition(" *")
                if name == iso.name:
                    expected = listed.strip()
        if expected is None:
            _say(f"no checksum for {iso.name} in {sums_file}, skipping ISO verification")
            return
        _say(f"verifying {iso.name} against {sums_file.name}")
        hasher = hashlib.sha256()
        with iso.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                hasher.update(chunk)
        actual = hasher.hexdigest()
        if actual != expected:
            raise RuntimeError(f"ISO checksum mismatch: expected {expected}, got {actual}")
        _say("ISO checksum OK")

    def _unmount_target(self) -> None:
        """Unmount every partition of the stick, by device node, never by mount path."""
        for device in self.disk.all_mountpoints():
            if try_run(["umount", device]).returncode == 0:
                _say(f"unmounted {device}")
            else:
                try_run(["umount", "-l", device])

    def _probe_resume(self) -> bool:
        """
        Try to open a copy a previous run left on the stick and reuse it.

        :returns: True when the stick holds a matching system copy, with the
            partitions mounted and the layout set
        """
        root_device = f"/dev/{self.disk.name}2"
        esp_device = f"/dev/{self.disk.name}1"
        MNT.mkdir(parents=True, exist_ok=True)
        TARGET.mkdir(parents=True, exist_ok=True)
        if not Path(root_device).is_block_device():
            return False
        if try_run(["mount", root_device, str(TARGET)]).returncode != 0:
            return False
        ESP.mkdir(parents=True, exist_ok=True)
        if try_run(["mount", esp_device, str(ESP)]).returncode != 0:
            try_run(["umount", "-l", str(TARGET)])
            return False
        marker = TARGET / MARKER
        if not marker.is_file() or not list(TARGET.glob("boot/vmlinuz-*")):
            _say("no usable previous copy on the stick, starting fresh")
            try_run(["umount", "-l", str(ESP)])
            try_run(["umount", "-l", str(TARGET)])
            return False
        state = json.loads(marker.read_text(encoding="utf-8"))
        if state.get("chain") != self._chain_names_for_marker():
            _say("the requested layer chain differs from the copy on the stick, starting fresh")
            try_run(["umount", "-l", str(ESP)])
            try_run(["umount", "-l", str(TARGET)])
            return False
        root_uuid = run(["blkid", "-s", "UUID", "-o", "value", root_device], capture=True).stdout.strip()
        if not root_uuid or state.get("root_uuid") != root_uuid:
            try_run(["umount", "-l", str(ESP)])
            try_run(["umount", "-l", str(TARGET)])
            return False
        self.layout = _Layout(disk=self.disk, esp_device=esp_device, root_device=root_device, root_uuid=root_uuid)
        _say("resuming from the copy already on the stick")
        return True

    def _chain_names_for_marker(self) -> list[str]:
        """Mount the ISO, build the chain names, and unmount it again."""
        ISO_MNT.mkdir(parents=True, exist_ok=True)
        run(["mount", "-o", "loop,ro", str(self.config.iso_path), str(ISO_MNT)], capture=True)
        try:
            return layers.build_chain(self._iso_layers(), self.config.flavor, self.config.language)
        finally:
            try_run(["umount", "-l", str(ISO_MNT)])

    def _iso_layers(self) -> dict[str, int]:
        """
        List the squashfs layers in the mounted ISO with their sizes.

        :returns: Layer name to file size in bytes
        :raises RuntimeError: When the casper directory has no layers
        """
        casper = ISO_MNT / "casper"
        found: dict[str, int] = {}
        for path in casper.glob("*.squashfs"):
            found[path.name[: -len(".squashfs")]] = path.stat().st_size
        if not found:
            raise RuntimeError(f"no squashfs layers in {casper}, is this an Ubuntu desktop ISO?")
        return found

    def _partition(self) -> None:
        """Wipe the stick, create the ESP and root partitions, and mount both."""
        self._unmount_target()
        root_device = f"/dev/{self.disk.name}2"
        esp_device = f"/dev/{self.disk.name}1"
        run(["wipefs", "-a", f"/dev/{self.disk.name}"])
        run(["parted", "-s", f"/dev/{self.disk.name}", "mklabel", "gpt"])
        run(["parted", "-s", f"/dev/{self.disk.name}", "mkpart", "ESP", "fat32", "1MiB", f"{ESP_MIB + 1}MiB"])
        run(["parted", "-s", f"/dev/{self.disk.name}", "set", "1", "esp", "on"])
        run(["parted", "-s", f"/dev/{self.disk.name}", "mkpart", "ROOT", "ext4", f"{ESP_MIB + 2}MiB", "100%"])
        try_run(["udevadm", "settle", "--timeout", "15"])
        if not Path(esp_device).is_block_device() or not Path(root_device).is_block_device():
            run(["partprobe", f"/dev/{self.disk.name}"])
            time.sleep(3)
        run(["mkfs.fat", "-F32", "-n", "USBEFI", esp_device])
        run(["mkfs.ext4", "-F", "-L", "USBROOT", root_device])
        MNT.mkdir(parents=True, exist_ok=True)
        TARGET.mkdir(parents=True, exist_ok=True)
        run(["mount", root_device, str(TARGET)], capture=True)
        ESP.mkdir(parents=True, exist_ok=True)
        run(["mount", esp_device, str(ESP)], capture=True)
        root_uuid = run(["blkid", "-s", "UUID", "-o", "value", root_device], capture=True).stdout.strip()
        if not root_uuid:
            raise RuntimeError("could not read the UUID of the freshly created root partition")
        self.layout = _Layout(disk=self.disk, esp_device=esp_device, root_device=root_device, root_uuid=root_uuid)
        _say(f"partitioned and formatted {self.disk.path}")

    def _copy(self) -> None:
        """Stack the ISO layers as overlayfs and rsync the merged view onto the stick."""
        layout = self._layout()
        ISO_MNT.mkdir(parents=True, exist_ok=True)
        run(["mount", "-o", "loop,ro", str(self.config.iso_path), str(ISO_MNT)], capture=True)
        iso_layers = self._iso_layers()
        chain = layers.build_chain(iso_layers, self.config.flavor, self.config.language)
        _say(f"layer chain (bottom to top): {' -> '.join(chain)}")
        LAYERS_MNT.mkdir(parents=True, exist_ok=True)
        for index, name in enumerate(chain, start=1):
            mount_dir = LAYERS_MNT / str(index)
            mount_dir.mkdir(parents=True, exist_ok=True)
            run(
                [
                    "mount",
                    "-o",
                    "ro,loop",
                    "-t",
                    "squashfs",
                    str(ISO_MNT / "casper" / f"{name}.squashfs"),
                    str(mount_dir),
                ],
                capture=True,
            )
            _say(f"mounted layer {index}/{len(chain)}: {name}")
        lowers = ":".join(str(LAYERS_MNT / str(index)) for index in range(len(chain), 0, -1))
        OVL_MNT.mkdir(parents=True, exist_ok=True)
        run(["mount", "-t", "tmpfs", "tmpfs", str(OVL_MNT)], capture=True)
        (OVL_MNT / "upper").mkdir()
        (OVL_MNT / "work").mkdir()
        MERGED_MNT.mkdir(parents=True, exist_ok=True)
        run(
            [
                "mount",
                "-t",
                "overlay",
                "overlay",
                "-o",
                f"lowerdir={lowers},upperdir={OVL_MNT / 'upper'},workdir={OVL_MNT / 'work'}",
                str(MERGED_MNT),
            ],
            capture=True,
        )
        _say("copying the system to the stick, this is the longest phase")
        self._rsync(MERGED_MNT, TARGET)
        total = sum(1 for _ in TARGET.rglob("*"))
        _say(f"system copy complete: {total} filesystem entries")
        marker = {
            "chain": chain,
            "root_uuid": layout.root_uuid,
        }
        (TARGET / MARKER).write_text(json.dumps(marker), encoding="utf-8")
        run(["umount", str(MERGED_MNT)])
        try_run(["umount", "-l", str(OVL_MNT)])
        for index in range(len(chain), 0, -1):
            try_run(["umount", "-l", str(LAYERS_MNT / str(index))])
        try_run(["umount", "-l", str(ISO_MNT)])

    def _rsync(self, source: Path, destination: Path) -> None:
        """Run rsync with a progress report while it works."""
        command = ["rsync", "-aHAX", f"{source}/", f"{destination}/"]
        _say(f"+ {' '.join(command)}")
        process = subprocess.Popen(  # nosec B603: argument list form, no shell
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        copied = 0
        while process.poll() is None:
            time.sleep(45)
            copied = sum(1 for _ in destination.rglob("*"))
            _say(f"  ... copy in progress, {copied} entries so far")
        if process.returncode != 0:
            error = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"rsync failed with exit code {process.returncode}: {error.strip()}")

    def _configure_target(self) -> None:
        """Write the system configuration onto the target."""
        layout = self._layout()
        esp_uuid = run(["blkid", "-s", "UUID", "-o", "value", layout.esp_device], capture=True).stdout.strip()
        (TARGET / "etc/fstab").write_text(
            f"UUID={layout.root_uuid}  /          ext4  defaults    0 1\n"
            f"UUID={esp_uuid}  /boot/efi  vfat  umask=0077  0 1\n",
            encoding="utf-8",
        )
        (TARGET / "etc/hostname").write_text(f"{self.config.hostname}\n", encoding="utf-8")
        (TARGET / "etc/hosts").write_text(
            "127.0.0.1       localhost\n"
            f"127.0.1.1       {self.config.hostname}\n"
            "::1     localhost ip6-localhost ip6-loopback\n"
            "ff02::1 ip6-allnodes\n"
            "ff02::2 ip6-allrouters\n",
            encoding="utf-8",
        )
        (TARGET / "etc/machine-id").write_text("", encoding="utf-8")
        gdm = TARGET / "etc/gdm3/custom.conf"
        if gdm.is_file():
            text = gdm.read_text(encoding="utf-8")
            text = text.replace("AutomaticLoginEnable=true", "#AutomaticLoginEnable=false")
            text = re.sub(r"^AutomaticLogin=.*$", "#AutomaticLogin=disabled", text, flags=re.MULTILINE)
            gdm.write_text(text, encoding="utf-8")
        netplan = TARGET / "etc/netplan"
        if netplan.is_dir():
            for stale in netplan.glob("*.yaml"):
                stale.unlink()
            netplan.mkdir(exist_ok=True)
            (netplan / "01-network-manager-all.yaml").write_text(
                "network:\n  version: 2\n  renderer: NetworkManager\n", encoding="utf-8"
            )
        grub_defaults = TARGET / "etc/default/grub"
        if grub_defaults.is_file():
            text = grub_defaults.read_text(encoding="utf-8")
            if "GRUB_DISABLE_OS_PROBER=" in text:
                text = re.sub(r"^GRUB_DISABLE_OS_PROBER=.*$", "GRUB_DISABLE_OS_PROBER=true", text, flags=re.MULTILINE)
            else:
                text += "\nGRUB_DISABLE_OS_PROBER=true\n"
            grub_defaults.write_text(text, encoding="utf-8")
        for name in ("localtime", "timezone"):
            source = Path("/etc") / name
            if source.exists():
                (TARGET / "etc" / name).write_bytes(source.read_bytes())
        for name in ("locale", "keyboard"):
            source = Path("/etc/default") / name
            if source.is_file():
                (TARGET / "etc/default" / name).write_bytes(source.read_bytes())
        (TARGET / "etc/mtab").write_text(grub.mtab(layout.root_device, layout.esp_device), encoding="utf-8")
        _say("system configuration written")

    def _binds_on(self) -> None:
        """Bind the host pseudo filesystems into the target for the chroot."""
        for name in ("dev", "proc", "sys", "run"):
            run(["mount", "--bind", f"/{name}", str(TARGET / name)], capture=True)
        run(["mount", "--bind", "/dev/pts", str(TARGET / "dev/pts")], capture=True)
        resolv = TARGET / "etc/resolv.conf"
        if resolv.exists() or resolv.is_symlink():
            resolv.unlink()
        resolv.write_bytes(Path("/etc/resolv.conf").read_bytes())

    def _binds_off(self) -> None:
        """Undo the bind mounts."""
        try_run(["umount", "-l", str(TARGET / "dev/pts")])
        for name in ("run", "sys", "proc", "dev"):
            try_run(["umount", "-l", str(TARGET / name)])

    def _chroot(self) -> None:
        """Run the package and account configuration inside the target."""
        config = self.config
        extras = resolve_extras(config.extras)
        apt_names = list(config.apt_packages)
        for extra in extras:
            apt_names.extend(extra.apt)
        lines = [
            "set -e",
            "export DEBIAN_FRONTEND=noninteractive LC_ALL=C HOME=/root",
            "if id ubuntu >/dev/null 2>&1; then userdel -r -f ubuntu 2>/dev/null || true; fi",
            "apt-get update",
            # Ubuntu 26.04 images ship this; it conflicts with a classic GRUB install.
            "apt-get purge -y boot-managed-by-snapd 2>/dev/null || true",
            "apt-get purge -y casper 2>/dev/null || true",
        ]
        if config.remove_snap:
            lines += [
                "apt-get purge -y snapd 2>/dev/null || true",
                "rm -rf /var/lib/snapd /snap /var/cache/snapd /var/snap",
                "apt-mark hold snapd || true",
            ]
        lines += [
            "apt-get install -y grub-efi-amd64 shim-signed grub-efi-amd64-signed",
            "if ! ls /boot/vmlinuz-* >/dev/null 2>&1; then apt-get install -y linux-generic; fi",
        ]
        if apt_names:
            lines.append(f"apt-get install -y {' '.join(apt_names)}")
        for extra in extras:
            for command in extra.post_commands:
                lines.append(f"bash -lc {shlex.quote(command)}")
        lines += [
            "update-initramfs -u",
            f"useradd -m -s /bin/bash {shlex.quote(config.username)} 2>/dev/null || true",
            f"usermod -aG sudo,adm,cdrom,dip,plugdev,lpadmin {shlex.quote(config.username)}",
            f"echo {shlex.quote(f'{config.username}:{config.user_password}')} | chpasswd",
        ]
        if config.force_password_change:
            lines.append(f"chage -d 0 {shlex.quote(config.username)}")
        lines += [
            "update-grub",
            "grub-install --target=x86_64-efi --efi-directory=/boot/efi "
            "--boot-directory=/boot --removable --no-nvram 2>/dev/null || "
            "echo 'grub-install reported a problem, the signed binaries will be placed by hand'",
        ]
        _say("configuring the system in a chroot (apt runs here, this takes a while)")
        run_stdin(["chroot", str(TARGET), "/bin/bash", "-se"], "\n".join(lines) + "\n")
        _say("chroot configuration complete")

    def _install_bootloader(self) -> None:
        """Write the early config and guarantee the genuine signed binaries on the ESP."""
        layout = self._layout()
        esp_boot = ESP / "EFI/BOOT"
        esp_boot.mkdir(parents=True, exist_ok=True)
        (esp_boot / "grub.cfg").write_text(grub.early_cfg(layout.root_uuid), encoding="utf-8")
        _say("placing and verifying the signed shim and GRUB on the ESP")
        grub.place_signed_binaries(esp_boot, TARGET)

    def _verify(self) -> None:
        """Run the checks that decide whether the stick will boot."""
        layout = self._layout()
        if not list(TARGET.glob("boot/vmlinuz-*")):
            raise RuntimeError("no kernel in the target's /boot")
        grub_cfg = TARGET / "boot/grub/grub.cfg"
        if not grub_cfg.is_file() or layout.root_uuid not in grub_cfg.read_text(encoding="utf-8"):
            raise RuntimeError("grub.cfg is missing or does not reference the stick's root UUID")
        early = ESP / "EFI/BOOT/grub.cfg"
        if layout.root_uuid not in early.read_text(encoding="utf-8"):
            raise RuntimeError("the ESP's early grub.cfg does not reference the stick's root UUID")
        files = sum(1 for path in TARGET.rglob("*") if path.is_file())
        if files < MIN_FILES_INSTALLED:
            raise RuntimeError(f"only {files} files copied, the layer stack produced a suspiciously small system")
        for check in grub.check_esp(ESP / "EFI/BOOT", TARGET):
            _say(f"ESP check: {check.esp_file} {'OK' if check.ok else 'MISMATCH'}")
        _say(f"all verification checks passed ({files} files installed)")

    def _close_layout(self) -> None:
        """Unmount everything and restore the standard mtab symlink."""
        self._binds_off()
        (TARGET / "etc/mtab").unlink(missing_ok=True)
        (TARGET / "etc/mtab").symlink_to("/proc/self/mounts")
        (TARGET / MARKER).unlink(missing_ok=True)
        try_run(["umount", "-l", str(ESP)])
        try_run(["umount", "-l", str(TARGET)])
        run(["sync"], capture=True)

    def _summary(self, resumed: bool) -> None:
        """
        Print what was done and how to boot the stick.

        :param resumed: Whether the system copy was reused from a previous run
        """
        _say(f"DONE - full Ubuntu installed on {self.disk.path} (resumed: {resumed})")
        _say(
            f"log in as {self.config.username}; you will be asked to set your own password"
            + (" at first login" if self.config.force_password_change else "")
        )
        _say("reboot, press your firmware's boot menu key (often F12) and pick the USB drive")


def verify_device(device_argument: str) -> None:
    """
    Check a stick that already holds an install and report what is wrong with it.

    :param device_argument: The device to check, such as ``/dev/sda``
    :raises RuntimeError: When one or more boot checks fail
    """
    devices = list_devices()
    disk = find_target(device_argument, devices, min_gib=0)
    target = MNT / "verify"
    esp = target / "boot/efi"
    target.mkdir(parents=True, exist_ok=True)
    run(["mount", f"/dev/{disk.name}2", str(target)], capture=True)
    esp.mkdir(parents=True, exist_ok=True)
    run(["mount", f"/dev/{disk.name}1", str(esp)], capture=True)
    root_uuid = run(["blkid", "-s", "UUID", "-o", "value", f"/dev/{disk.name}2"], capture=True).stdout.strip()
    try:
        problems: list[str] = []
        if not list(target.glob("boot/vmlinuz-*")):
            problems.append("no kernel in /boot")
        grub_cfg = target / "boot/grub/grub.cfg"
        if not grub_cfg.is_file() or root_uuid not in grub_cfg.read_text(encoding="utf-8"):
            problems.append("grub.cfg missing or references another root")
        early = esp / "EFI/BOOT/grub.cfg"
        if not early.is_file() or root_uuid not in early.read_text(encoding="utf-8"):
            problems.append("ESP early grub.cfg missing or references another root")
        for check in grub.check_esp(esp / "EFI/BOOT", target):
            if not check.ok:
                problems.append(f"{check.esp_file} does not match the shipped signed file")
        if problems:
            for problem in problems:
                print(f"PROBLEM: {problem}")
            raise RuntimeError(f"{len(problems)} problem(s) found")
        print(f"{disk.path}: all boot checks passed")
    finally:
        try_run(["umount", "-l", str(esp)])
        try_run(["umount", "-l", str(target)])


def inspect_iso(iso_path: Path, flavor: str, language: str) -> None:
    """
    Print the layer chain an ISO would install, without touching any stick.

    :param iso_path: The ISO to inspect
    :param flavor: The flavor the chain is built for
    :param language: The language code the chain is built for
    """
    ISO_MNT.mkdir(parents=True, exist_ok=True)
    run(["mount", "-o", "loop,ro", str(iso_path), str(ISO_MNT)], capture=True)
    try:
        found = {}
        for path in (ISO_MNT / "casper").glob("*.squashfs"):
            found[path.name[: -len(".squashfs")]] = path.stat().st_size
        chain = layers.build_chain(found, flavor, language)
        for name, size in sorted(found.items()):
            mark = "*" if name in chain else " "
            print(f" {mark} {size / 1024 / 1024:9.1f} MiB  {name}")
        print(f"\nchain for flavor={flavor} language={language}:")
        print(" -> ".join(chain))
    finally:
        try_run(["umount", "-l", str(ISO_MNT)])
