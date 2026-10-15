"""Tests for the GRUB configuration and the signed bootloader verification."""

from pathlib import Path

import pytest

from usbuntu.grub import BootError, check_esp, early_cfg, mtab, place_signed_binaries


def _shipped_tree(root: Path, shim: bytes = b"shim-bytes", grub_bytes: bytes = b"grub-bytes", mm: bytes = b"mm") -> Path:
    """
    Create a target root with the shipped signed binaries.

    :param root: The root directory to populate
    :param shim: The content to write as the shipped shim
    :param grub_bytes: The content to write as the shipped signed GRUB
    :param mm: The content to write as the shipped MOK manager
    :returns: The populated root
    """
    shim_dir = root / "usr/lib/shim"
    grub_dir = root / "usr/lib/grub/x86_64-efi-signed"
    shim_dir.mkdir(parents=True)
    grub_dir.mkdir(parents=True)
    (shim_dir / "shimx64.efi.signed").write_bytes(shim)
    (shim_dir / "mmx64.efi.signed").write_bytes(mm)
    (grub_dir / "grubx64.efi.signed").write_bytes(grub_bytes)
    return root


class TestEarlyCfg:
    def test_references_the_root_uuid(self) -> None:
        cfg = early_cfg("86e648c8-8518-418f-b425-827190652768")
        assert "search.fs_uuid 86e648c8-8518-418f-b425-827190652768 root hd0,gpt2" in cfg
        assert "set prefix=($root)'/boot/grub'" in cfg
        assert "configfile $prefix/grub.cfg" in cfg


class TestMtab:
    def test_lists_target_devices(self) -> None:
        text = mtab("/dev/sda2", "/dev/sda1")
        assert "/dev/sda2 / ext4 rw,relatime 0 0" in text
        assert "/dev/sda1 /boot/efi vfat rw,relatime 0 0" in text


class TestCheckEsp:
    def test_matching_binaries_pass(self, tmp_path: Path) -> None:
        root = _shipped_tree(tmp_path / "root")
        esp_boot = tmp_path / "esp/EFI/BOOT"
        esp_boot.mkdir(parents=True)
        (esp_boot / "BOOTX64.EFI").write_bytes(b"shim-bytes")
        (esp_boot / "grubx64.efi").write_bytes(b"grub-bytes")
        checks = check_esp(esp_boot, root)
        assert all(check.ok for check in checks)

    def test_locally_built_unsigned_grub_fails(self, tmp_path: Path) -> None:
        root = _shipped_tree(tmp_path / "root")
        esp_boot = tmp_path / "esp/EFI/BOOT"
        esp_boot.mkdir(parents=True)
        (esp_boot / "BOOTX64.EFI").write_bytes(b"a locally built image without a config")
        (esp_boot / "grubx64.efi").write_bytes(b"another locally built image")
        checks = check_esp(esp_boot, root)
        assert not any(check.ok for check in checks)


class TestPlaceSignedBinaries:
    def test_places_and_verifies(self, tmp_path: Path) -> None:
        root = _shipped_tree(tmp_path / "root")
        esp_boot = tmp_path / "esp/EFI/BOOT"
        esp_boot.mkdir(parents=True)
        place_signed_binaries(esp_boot, root)
        assert (esp_boot / "BOOTX64.EFI").read_bytes() == b"shim-bytes"
        assert (esp_boot / "grubx64.efi").read_bytes() == b"grub-bytes"
        assert (esp_boot / "mmx64.efi").read_bytes() == b"mm"

    def test_missing_source_raises(self, tmp_path: Path) -> None:
        root = _shipped_tree(tmp_path / "root")
        (root / "usr/lib/shim/shimx64.efi.signed").unlink()
        esp_boot = tmp_path / "esp/EFI/BOOT"
        esp_boot.mkdir(parents=True)
        with pytest.raises(BootError, match="not found"):
            place_signed_binaries(esp_boot, root)
