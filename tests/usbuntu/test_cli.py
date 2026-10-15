"""Tests for the command line parser."""

import pytest

from usbuntu.cli import _build_parser


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
