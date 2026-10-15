"""Tests for the block device discovery."""

import json
import textwrap

import pytest

from usbuntu.devices import find_target, install_targets, parse_lsblk

GIB = 1024**3


def _lsblk_output() -> str:
    """
    Build a realistic lsblk tree: a stick, a big external disk and the internal NVMe.

    :returns: lsblk JSON text
    """
    return textwrap.dedent(
        f"""
        {{
          "blockdevices": [
            {{
              "name": "sda", "size": {57 * GIB}, "type": "disk", "tran": "usb", "rm": true,
              "fstype": null, "label": "Ubuntu 18.04.6 LTS amd64", "model": "Ultra USB 3.0",
              "mountpoint": null,
              "children": [
                {{
                  "name": "sda1", "size": {GIB}, "type": "part", "tran": "usb", "rm": true,
                  "fstype": "vfat", "label": "USBEFI", "model": null,
                  "mountpoint": "/media/james-sanders/USBEFI", "children": []
                }},
                {{
                  "name": "sda2", "size": {56 * GIB}, "type": "part", "tran": "usb", "rm": true,
                  "fstype": "ext4", "label": "USBROOT", "model": null,
                  "mountpoint": "/media/james-sanders/USBROOT", "children": []
                }}
              ]
            }},
            {{
              "name": "sdb", "size": {1800 * GIB}, "type": "disk", "tran": "usb", "rm": false,
              "fstype": null, "label": "PredatorRecovery", "model": "External Drive",
              "mountpoint": "/media/james-sanders/PredatorRecovery", "children": []
            }},
            {{
              "name": "nvme0n1", "size": {953 * GIB}, "type": "disk", "tran": "nvme", "rm": false,
              "fstype": null, "label": null, "model": "SAMSUNG MZVL21T0HCLR-00BH1",
              "mountpoint": null,
              "children": [
                {{
                  "name": "nvme0n1p1", "size": {GIB}, "type": "part", "tran": "nvme", "rm": false,
                  "fstype": "vfat", "label": null, "model": null,
                  "mountpoint": "/boot/efi", "children": []
                }}
              ]
            }}
          ]
        }}
        """
    )


def _devices() -> list:
    """Parse the standard fixture tree."""
    return parse_lsblk(_lsblk_output())


class TestParseLsblk:
    def test_parses_disk_and_children(self) -> None:
        devices = _devices()
        assert len(devices) == 3
        stick = devices[0]
        assert stick.name == "sda"
        assert stick.tran == "usb"
        assert stick.removable
        assert [child.name for child in stick.children] == ["sda1", "sda2"]
        assert stick.children[0].mountpoint == "/media/james-sanders/USBEFI"

    def test_mountpoints_of_children(self) -> None:
        stick = _devices()[0]
        assert stick.all_mountpoints() == ["/dev/sda1", "/dev/sda2"]
        assert _devices()[1].all_mountpoints() == ["/dev/sdb"]

    def test_rejects_non_lsblk_json(self) -> None:
        with pytest.raises(ValueError):
            parse_lsblk(json.dumps({"unexpected": []}))


class TestInstallTargets:
    def test_only_removable_usb_disks_qualify(self) -> None:
        targets = install_targets(_devices())
        assert [device.name for device in targets] == ["sda"]

    def test_size_floor_excludes_small_sticks(self) -> None:
        targets = install_targets(_devices(), min_gib=58)
        assert targets == []


class TestFindTarget:
    def test_autodetects_the_single_stick(self) -> None:
        target = find_target(None, _devices())
        assert target.name == "sda"

    def test_explicit_device_resolves(self) -> None:
        target = find_target("/dev/sda", _devices())
        assert target.path == "/dev/sda"

    def test_refuses_non_removable_disk(self) -> None:
        with pytest.raises(ValueError, match="refusing to touch it"):
            find_target("/dev/sdb", _devices())

    def test_refuses_unknown_disk(self) -> None:
        with pytest.raises(ValueError, match="no disk named"):
            find_target("/dev/sdz", _devices())

    def test_ambiguous_autodetect_lists_candidates(self) -> None:
        devices = _devices()
        devices.append(devices[0].__class__(name="sdc", size=64 * GIB, kind="disk", tran="usb", removable=True))
        with pytest.raises(ValueError, match="more than one removable USB disk"):
            find_target(None, devices)

    def test_no_stick_plugged_in(self) -> None:
        with pytest.raises(ValueError, match="no removable USB disk"):
            find_target(None, [])
