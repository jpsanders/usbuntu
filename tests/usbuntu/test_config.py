"""Tests for the install configuration and the extras registry."""

from pathlib import Path
from typing import Any

import pytest

from usbuntu.config import InstallConfig, generate_password
from usbuntu.packages import available, resolve_extras


def _config(tmp_path: Path, **overrides: object) -> InstallConfig:
    """
    Build a valid configuration, with overrides for the field under test.

    :param tmp_path: pytest's temporary directory, used for the ISO file
    :param overrides: Field names to replace
    :returns: The configuration
    """
    iso = tmp_path / "ubuntu.iso"
    iso.write_bytes(b"")
    values: dict[str, Any] = {
        "iso_path": iso,
        "device": None,
        "username": "james-sanders",
        "user_password": "starter",
        "force_password_change": True,
        "hostname": "usb-ubuntu",
        "language": "en",
        "flavor": "full",
        "remove_snap": False,
        "apt_packages": [],
        "extras": [],
        "assume_yes": False,
    }
    values.update(overrides)
    return InstallConfig(**values)


class TestValidate:
    def test_valid_configuration_passes(self, tmp_path: Path) -> None:
        _config(tmp_path).validate()

    def test_missing_iso_raises(self, tmp_path: Path) -> None:
        config = _config(tmp_path, iso_path=tmp_path / "nowhere.iso")
        with pytest.raises(ValueError, match="ISO not found"):
            config.validate()

    def test_bad_username_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="invalid username"):
            _config(tmp_path, username="James!").validate()

    def test_empty_password_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="password"):
            _config(tmp_path, user_password="").validate()

    def test_bad_hostname_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="invalid hostname"):
            _config(tmp_path, hostname="USB Ubuntu").validate()

    def test_bad_language_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="invalid language"):
            _config(tmp_path, language="english").validate()

    def test_bad_flavor_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="invalid flavor"):
            _config(tmp_path, flavor="everything").validate()

    def test_bad_apt_package_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="invalid apt package"):
            _config(tmp_path, apt_packages=["curl; rm -rf /"]).validate()

    def test_unknown_extra_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="unknown extra"):
            _config(tmp_path, extras=["teleport"]).validate()


class TestJsonRoundTrip:
    def test_survives_serialisation(self, tmp_path: Path) -> None:
        config = _config(tmp_path, apt_packages=["curl", "vim"], extras=["opencode"], device="/dev/sda")
        assert InstallConfig.from_json(config.to_json()) == config


class TestGeneratePassword:
    def test_generates_distinct_values(self) -> None:
        first = generate_password()
        second = generate_password()
        assert first
        assert second
        assert first != second


class TestExtras:
    def test_registry_contains_the_documented_extras(self) -> None:
        keys = {extra.key for extra in available()}
        assert {"opencode", "claude-code", "build-tools"} <= keys

    def test_resolve_known_keys(self) -> None:
        extras = resolve_extras(["opencode", "claude-code"])
        assert extras[0].post_commands[0].startswith("curl")
        assert "nodejs" in extras[1].apt

    def test_resolve_unknown_key(self) -> None:
        with pytest.raises(ValueError, match="unknown extra"):
            resolve_extras(["nope"])
