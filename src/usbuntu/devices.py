r"""
Discovery of the USB devices safe to wipe, using lsblk JSON output.

Mount points are read from JSON, never from lsblk's text mode: the text mode
escapes spaces as ``\x20`` and parsing it once broke a real install.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from usbuntu.runner import run

MIN_TARGET_GIB = 8


@dataclass
class BlockDevice:
    """One entry from lsblk, disk or partition."""

    name: str
    size: int
    kind: str
    tran: str | None
    removable: bool
    fstype: str | None = None
    label: str | None = None
    model: str | None = None
    mountpoint: str | None = None
    children: list[BlockDevice] = field(default_factory=list)

    @property
    def path(self) -> str:
        """
        The device node path.

        :returns: The absolute path of this device node
        """
        return f"/dev/{self.name}"

    def all_mountpoints(self) -> list[str]:
        """
        Collect the device node paths of this device and every mounted child.

        :returns: Device node paths such as ``/dev/sda1``, root first
        """
        mounted = [child.path for child in self.children if child.mountpoint]
        if self.mountpoint:
            mounted.insert(0, self.path)
        return mounted

    def describe(self) -> str:
        """
        Render one line for the device table.

        :returns: A human readable description of the device
        """
        size_gib = self.size / (1024**3)
        label = f" label {self.label!r}" if self.label else ""
        model = self.model or "unknown model"
        return f"{self.path:<14} {size_gib:6.1f} GiB  {model}{label}"


def parse_lsblk(json_text: str) -> list[BlockDevice]:
    """
    Parse lsblk JSON output into device objects.

    :param json_text: The output of ``lsblk -J -b -o ...``
    :returns: The top level devices, with their children
    :raises ValueError: When the JSON does not have the expected shape
    """

    def to_device(entry: dict[str, Any]) -> BlockDevice:
        children = [to_device(child) for child in entry.get("children") or []]
        return BlockDevice(
            name=str(entry["name"]),
            size=int(entry["size"]),
            kind=str(entry["type"]),
            tran=entry.get("tran"),
            removable=bool(entry.get("rm", False)),
            fstype=entry.get("fstype"),
            label=entry.get("label"),
            model=entry.get("model"),
            mountpoint=entry.get("mountpoint"),
            children=children,
        )

    data = json.loads(json_text)
    devices = data.get("blockdevices")
    if not isinstance(devices, list):
        raise ValueError("lsblk JSON output has no 'blockdevices' list")
    return [to_device(entry) for entry in devices]


def list_devices() -> list[BlockDevice]:
    """
    Read every block device on this machine.

    :returns: The top level devices, with their children
    """
    result = run(
        [
            "lsblk",
            "-J",
            "-b",
            "-o",
            "NAME,SIZE,TYPE,TRAN,RM,FSTYPE,LABEL,MODEL,MOUNTPOINT",
        ],
        capture=True,
    )
    return parse_lsblk(result.stdout)


def iter_devices(devices: list[BlockDevice]) -> Iterator[BlockDevice]:
    """
    Walk a device tree depth first.

    :param devices: The top level devices
    :yields: Every device and child, in tree order
    """
    for device in devices:
        yield device
        yield from iter_devices(device.children)


def install_targets(devices: list[BlockDevice], min_gib: int = MIN_TARGET_GIB) -> list[BlockDevice]:
    """
    Pick the devices that may be wiped: removable, on USB, big enough for the system.

    :param devices: The top level devices
    :param min_gib: The smallest stick worth considering, in GiB
    :returns: The candidate devices
    """
    return [
        device
        for device in devices
        if device.kind == "disk" and device.tran == "usb" and device.removable and device.size >= min_gib * 1024**3
    ]


def find_target(device_argument: str | None, devices: list[BlockDevice], min_gib: int = MIN_TARGET_GIB) -> BlockDevice:
    """
    Resolve the target device from a flag or by auto-detection.

    :param device_argument: The ``--device`` value, such as ``/dev/sda``, or None to auto-detect
    :param devices: The top level devices
    :param min_gib: The smallest stick worth considering, in GiB
    :returns: The chosen device
    :raises ValueError: When the flag names an unsafe device, or auto-detection is ambiguous
    """
    if device_argument:
        wanted = device_argument.removeprefix("/dev/")
        for device in iter_devices(devices):
            if device.name == wanted and device.kind == "disk":
                if device.tran != "usb" or not device.removable:
                    raise ValueError(f"{device.path} is not a removable USB device, refusing to touch it")
                if device.size < min_gib * 1024**3:
                    raise ValueError(f"{device.path} is smaller than {min_gib} GiB")
                return device
        raise ValueError(f"no disk named {device_argument} found")
    candidates = install_targets(devices, min_gib)
    if not candidates:
        raise ValueError("no removable USB disk found; plug the stick in or pass --device explicitly")
    if len(candidates) > 1:
        listing = "\n".join(f"  {device.describe()}" for device in candidates)
        raise ValueError(f"more than one removable USB disk:\n{listing}\npass --device to choose one")
    return candidates[0]
