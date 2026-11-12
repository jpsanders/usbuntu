"""Tests for the command line parser."""

import json
import sys
from pathlib import Path

import pytest

from usbuntu import cli
from usbuntu.cli import _build_parser, main
from usbuntu.devices import BlockDevice


class TestParser:
    def test_install_requires_a_username(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["install", "ubuntu.iso"])

    def test_install_defaults(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["install", "ubuntu.iso", "--username", "james"])
        assert args.hostname == "usb-ubuntu"
        assert args.flavor == "full"
        assert args.language == "en"
        assert not args.remove_snap
        assert not args.yes
        assert not args.dry_run
        assert args.extras == []
        assert args.packages == ""
        assert args.device is None
        assert not args.no_force_password_change

    def test_extras_repeat_and_accumulate(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            ["install", "ubuntu.iso", "--username", "james", "--with", "opencode", "--with", "claude-code"]
        )
        assert args.extras == ["opencode", "claude-code"]

    def test_remove_snap_and_flavors(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            ["install", "ubuntu.iso", "--username", "james", "--remove-snap", "--flavor", "minimal"]
        )
        assert args.remove_snap
        assert args.flavor == "minimal"

    def test_no_command_prints_help(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit) as caught:
            parser.parse_args([])
        assert caught.value.code == 2

    def test_verify_takes_a_device(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["verify", "/dev/sda"])
        assert args.command == "verify"
        assert args.device == "/dev/sda"

    def test_inspect_defaults(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["inspect", "ubuntu.iso"])
        assert args.flavor == "full"
        assert args.language == "en"


def _run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> None:
    monkeypatch.setattr(sys, "argv", ["usbuntu", *argv])
    main()


def test_devices_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    gib = 1024**3
    root = BlockDevice(name="sda1", size=32 * gib, kind="part", tran=None, removable=True, mountpoint="/")
    disks = [
        BlockDevice(
            name="sda", size=32 * gib, kind="disk", tran="usb", removable=True, model="Booted", children=[root]
        ),
        BlockDevice(name="sdb", size=64 * gib, kind="disk", tran="usb", removable=True, model="Spare"),
    ]
    monkeypatch.setattr(cli, "list_devices", lambda: disks)
    _run(monkeypatch, "devices", "--json")
    rows = json.loads(capsys.readouterr().out)["disks"]
    assert [(r["device"], r["accepted"]) for r in rows] == [("/dev/sda", False), ("/dev/sdb", True)]
    assert rows[0]["refused_because"] == ["holds the running system (/)"]
    _run(monkeypatch, "devices")
    assert "ACCEPTED" in capsys.readouterr().out


def test_guide_and_man(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    _run(monkeypatch, "guide")
    assert capsys.readouterr().out.startswith("# usbuntu")
    _run(monkeypatch, "man", "--raw")
    assert capsys.readouterr().out.startswith(".TH USBUNTU 1")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _run(monkeypatch, "man", "--install")
    assert (tmp_path / "man" / "man1" / "usbuntu.1").is_file()
