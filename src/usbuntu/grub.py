"""
GRUB configuration and the signed bootloader verification.

Two hard-won rules live here.

1.  ``grub-install`` inside a chroot cannot see the ESP through the host's
    ``/proc``, and silently falls back to writing a locally built, unsigned
    GRUB image to ``EFI/BOOT/BOOTX64.EFI``. That image carries no embedded
    config, so the stick boots to a bare ``grub>`` prompt. The fix is to copy
    the genuine signed binaries from the target system's own packages and
    verify them with md5sums, every install, no exceptions.

2.  ``update-grub`` in the chroot needs a truthful ``/etc/mtab`` file listing
    the target's own root and ESP, otherwise ``grub-probe`` reads the host's
    root UUID into the generated configuration.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

SHIM_SOURCE = Path("usr/lib/shim/shimx64.efi.signed")
GRUB_SOURCE = Path("usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed")
MM_SOURCE = Path("usr/lib/shim/mmx64.efi.signed")
ESP_BOOT_DIR = Path("EFI/BOOT")


class BootError(Exception):
    """Raised when the ESP cannot be made bootable or fails verification."""


def early_cfg(root_uuid: str, hint: str = "hd0,gpt2") -> str:
    """
    Render the small GRUB config that lives on the ESP and finds the real one.

    :param root_uuid: The UUID of the target root partition
    :param hint: The device hint GRUB should try first
    :returns: The contents of ``EFI/BOOT/grub.cfg``
    """
    return (
        f"search.fs_uuid {root_uuid} root {hint} \n" "set prefix=($root)'/boot/grub'\n" "configfile $prefix/grub.cfg\n"
    )


def mtab(root_device: str, esp_device: str) -> str:
    """
    Render the truthful /etc/mtab file that lets chrooted GRUB tools probe the target.

    :param root_device: The target root device node, such as ``/dev/sda2``
    :param esp_device: The target ESP device node, such as ``/dev/sda1``
    :returns: The contents of the target's /etc/mtab during the install
    """
    return f"{root_device} / ext4 rw,relatime 0 0\n{esp_device} /boot/efi vfat rw,relatime 0 0\n"


def _md5(path: Path) -> str:
    """
    Hash a file in chunks.

    :param path: The file to hash
    :returns: The hexadecimal md5 digest
    """
    digest = hashlib.md5(usedforsecurity=False)  # md5 compares two local copies of one file
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ESPCheck:
    """The result of checking one ESP file against the shipped original."""

    esp_file: str
    source_file: str
    ok: bool


def check_esp(esp_boot: Path, target_root: Path) -> list[ESPCheck]:
    """
    Compare the ESP binaries with the signed binaries shipped in the target system.

    :param esp_boot: The ESP directory that holds the bootloader, such as ``EFI/BOOT``
    :param target_root: The target root mount, with the target's ``/usr`` under it
    :returns: One check per ESP binary
    """
    pairs = [
        ("BOOTX64.EFI", SHIM_SOURCE),
        ("grubx64.efi", GRUB_SOURCE),
    ]
    checks = []
    for esp_name, source in pairs:
        esp_file = esp_boot / esp_name
        source_file = target_root / source
        ok = esp_file.is_file() and source_file.is_file() and _md5(esp_file) == _md5(source_file)
        checks.append(ESPCheck(esp_file=str(esp_file), source_file=str(source_file), ok=ok))
    return checks


def place_signed_binaries(esp_boot: Path, target_root: Path) -> None:
    """
    Copy the genuine signed shim and GRUB onto the ESP and verify them.

    This runs after ``grub-install``, always. When grub-install already did
    the right thing the copy is a no-op in content terms; when it silently
    wrote its own unsigned image instead, this replaces it with the real
    signed pair, which is what makes the stick boot.

    :param esp_boot: The ESP directory that holds the bootloader, such as ``EFI/BOOT``
    :param target_root: The target root mount, with the target's ``/usr`` under it
    :raises BootError: When a source binary is missing or the copy does not verify
    """
    pairs = [
        (SHIM_SOURCE, "BOOTX64.EFI"),
        (GRUB_SOURCE, "grubx64.efi"),
        (MM_SOURCE, "mmx64.efi"),
    ]
    for source, esp_name in pairs:
        source_file = target_root / source
        if not source_file.is_file():
            raise BootError(f"signed binary not found in target system: {source_file}")
        esp_file = esp_boot / esp_name
        esp_file.write_bytes(source_file.read_bytes())
    checks = check_esp(esp_boot, target_root)
    failed = [check for check in checks if not check.ok]
    if failed:
        detail = ", ".join(f"{check.esp_file} != {check.source_file}" for check in failed)
        raise BootError(f"ESP binaries do not match the shipped signed files after copy: {detail}")
