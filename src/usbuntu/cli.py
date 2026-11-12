"""The command line interface."""

import argparse
import getpass
import json
import os
import shutil
import subprocess  # nosec B404: runs man with fixed arguments only
import sys
import time
from importlib import metadata, resources
from pathlib import Path
from typing import TextIO, cast

from usbuntu.config import InstallConfig, generate_password
from usbuntu.devices import MIN_TARGET_GIB, find_target, list_devices, refusal_reasons
from usbuntu.installer import Installer, inspect_iso, verify_device
from usbuntu.packages import available


def _build_parser() -> argparse.ArgumentParser:
    """
    Build the argument parser.

    :returns: The configured parser
    """
    parser = argparse.ArgumentParser(
        prog="usbuntu",
        description=(
            "Install a complete, bootable Ubuntu system on a USB stick from an ISO, "
            "without booting an installer. The stick keeps its files, updates itself "
            "and works on any UEFI machine."
        ),
    )
    parser.add_argument("--version", action="version", version=f"usbuntu {_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="install Ubuntu from an ISO onto a USB stick")
    install.add_argument("iso", type=Path, help="path to the Ubuntu desktop ISO")
    install.add_argument(
        "--device",
        help="target disk such as /dev/sda; auto-detected when exactly one removable USB stick is plugged in",
    )
    install.add_argument("--username", required=True, help="the account the new system will log in with")
    install.add_argument(
        "--password",
        help="the account's starting password; generated and printed at the end when omitted",
    )
    install.add_argument(
        "--no-force-password-change",
        action="store_true",
        help="do not require a new password at first login",
    )
    install.add_argument(
        "--hostname", default="usb-ubuntu", help="machine name of the new system (default: usb-ubuntu)"
    )
    install.add_argument("--language", default="en", help="language layers to include, such as en or pt (default: en)")
    flavor = install.add_mutually_exclusive_group()
    flavor.add_argument(
        "--flavor",
        choices=["full", "minimal"],
        default="full",
        help="full featured desktop, or the reduced minimal one (default: full)",
    )
    install.add_argument(
        "--remove-snap",
        action="store_true",
        help="purge snapd instead of keeping it; Firefox and the Snap Store go with it",
    )
    install.add_argument(
        "--packages",
        default="",
        help="comma separated apt packages to add, such as curl,vim,git",
    )
    install.add_argument(
        "--with",
        dest="extras",
        action="append",
        default=[],
        metavar="EXTRA",
        help="add a registered extra, repeatable; one of: " + ", ".join(extra.key for extra in available()),
    )
    install.add_argument("--yes", action="store_true", help="do not ask before wiping the stick")
    install.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve and print the plan, including the detected target, then stop",
    )

    verify = sub.add_parser("verify", help="check the boot chain of a stick that already holds an install")
    verify.add_argument("device", help="disk to check, such as /dev/sda")

    inspect = sub.add_parser("inspect", help="show the layer chain an ISO would install")
    inspect.add_argument("iso", type=Path, help="path to the Ubuntu desktop ISO")
    inspect.add_argument("--flavor", choices=["full", "minimal"], default="full", help="chain to display")
    inspect.add_argument("--language", default="en", help="language code for the chain to display")

    devices = sub.add_parser("devices", help="list the disks and say which ones usbuntu would accept; no root needed")
    devices.add_argument("--json", action="store_true", help="print JSON")

    sub.add_parser("guide", help="print the full manual, for people and agents")
    man = sub.add_parser("man", help="show the man page")
    man.add_argument("--install", action="store_true", help="install it so `man usbuntu` works")
    man.add_argument("--raw", action="store_true", help="print the roff source")
    return parser


def _version() -> str:
    """
    Read the installed version, which setuptools_scm takes from the git tag.

    :returns: The version, or ``unknown`` in a source tree that was never installed
    """
    try:
        return metadata.version("usbuntu")
    except metadata.PackageNotFoundError:
        return "unknown"


def _data(name: str) -> str:
    """
    Read a file shipped in the package's data folder.

    :param name: File name inside ``data``
    :returns: Its text
    """
    return (resources.files("usbuntu") / "data" / name).read_text(encoding="utf-8")


def _show_devices(as_json: bool) -> None:
    """
    List every disk with the reasons usbuntu would refuse it, if any.

    :param as_json: Print JSON instead of a table
    """
    disks = [d for d in list_devices() if d.kind == "disk"]
    rows = [
        {
            "device": d.path,
            "size_bytes": d.size,
            "model": d.model,
            "transport": d.tran,
            "removable": d.removable,
            "accepted": not refusal_reasons(d),
            "refused_because": refusal_reasons(d),
        }
        for d in disks
    ]
    if as_json:
        print(json.dumps({"min_size_gib": MIN_TARGET_GIB, "disks": rows}))
        return
    for disk, row in zip(disks, rows):
        verdict = "ACCEPTED" if row["accepted"] else "refused: " + "; ".join(cast(list[str], row["refused_because"]))
        print(f"{disk.describe()}  {verdict}")
    if not any(row["accepted"] for row in rows):
        print("No disk is a safe target. Plug in a USB stick of at least 8 GiB.")


def _man(install: bool, raw: bool) -> None:
    """
    Show the man page, print its roff source, or install it for ``man usbuntu``.

    :param install: Write it to the per user man folder
    :param raw: Print the roff source
    """
    page = _data("usbuntu.1")
    if install:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        target = Path(base) / "man" / "man1" / "usbuntu.1"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        print(f"installed {target}; open it with: man usbuntu")
        return
    man = shutil.which("man")
    if man and sys.stdout.isatty() and not raw:
        with resources.as_file(resources.files("usbuntu") / "data" / "usbuntu.1") as path:
            subprocess.call([man, "-l", str(path)])  # nosec B603: man, fixed arguments
        return
    print(page, end="")


def _ask_password() -> str:
    """
    Read a password twice from the terminal, or generate one when the user wants that.

    :returns: The chosen password
    :raises SystemExit: When the two entries do not match
    """
    typed = getpass.getpass("Password for the new account (hidden, blank to generate one): ")
    if not typed:
        generated = generate_password()
        print(f"generated password: {generated}")
        return generated
    repeated = getpass.getpass("Repeat the password: ")
    if typed != repeated:
        raise SystemExit("the two passwords do not match")
    return typed


def _confirm_or_exit(config: InstallConfig, description: str) -> None:
    """
    Show the plan and the warning, and stop unless the user agrees.

    :param config: The install configuration to show
    :param description: One line describing the target device
    :raises SystemExit: When the user declines or stdin is not a terminal
    """
    print(f"\n{description}\n")
    print(config.summary())
    print("\nEverything on the device above is about to be destroyed.\n")
    if config.assume_yes:
        return
    if not sys.stdin.isatty():
        raise SystemExit("refusing to wipe without a confirmation; pass --yes for unattended runs")
    answer = input("Type WIPE to continue: ")
    if answer != "WIPE":
        raise SystemExit("aborted, nothing was written")


class _Tee:
    """Write to the wrapped terminal stream and to the log file at the same time."""

    def __init__(self, stream: TextIO, handle: TextIO) -> None:
        """
        Wrap a stream.

        :param stream: The terminal stream to write through
        :param handle: The open log file to write to as well
        """
        self.stream = stream
        self.handle = handle

    def write(self, text: str) -> int:
        """
        Write the text to both streams.

        :param text: The text to write
        :returns: The number of characters written to the terminal stream
        """
        written = self.stream.write(text)
        self.handle.write(text)
        self.handle.flush()
        return written

    def flush(self) -> None:
        """Flush the terminal stream."""
        self.stream.flush()

    def fileno(self) -> int:
        """
        Return the underlying file descriptor of the terminal stream.

        :returns: The descriptor number of the wrapped stream
        """
        return self.stream.fileno()

    def isatty(self) -> bool:
        """
        Tell whether the terminal stream is a TTY.

        :returns: True when the wrapped stream is a terminal
        """
        return self.stream.isatty()


def _setup_log() -> None:
    """Mirror standard output and standard error into a log file."""
    log_path = Path("/var/log/usbuntu.log")
    try:
        handle = log_path.open("a", encoding="utf-8")
    except OSError:
        return
    stamp = time.strftime("%F %T")
    handle.write(f"\n=== usbuntu started {stamp}, pid {os.getpid()} ===\n")
    sys.stdout = cast(TextIO, _Tee(sys.stdout, handle))
    sys.stderr = cast(TextIO, _Tee(sys.stderr, handle))
    print(f"log file: {log_path}")


def main() -> None:
    """
    Parse the arguments and run the requested command.

    :raises SystemExit: On a usage error, or when the user declines the wipe
    """
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "guide":
        print(_data("MANUAL.md"), end="")
        return
    if args.command == "man":
        _man(args.install, args.raw)
        return
    if args.command == "devices":
        _show_devices(args.json)
        return
    _setup_log()

    if args.command == "verify":
        if os.geteuid() != 0:
            raise SystemExit("verify needs root; run: sudo usbuntu verify ...")
        verify_device(args.device)
        return

    if args.command == "inspect":
        if os.geteuid() != 0:
            raise SystemExit("inspect needs root to mount the ISO; run: sudo usbuntu inspect ...")
        if not args.iso.is_file():
            raise SystemExit(f"ISO not found: {args.iso}")
        inspect_iso(args.iso, args.flavor, args.language)
        return

    if os.geteuid() != 0:
        raise SystemExit("install needs root; run: sudo usbuntu install ...")

    apt_packages = [name.strip() for name in args.packages.split(",") if name.strip()]
    config = InstallConfig(
        iso_path=args.iso,
        device=args.device,
        username=args.username,
        user_password=args.password or _ask_password(),
        force_password_change=not args.no_force_password_change,
        hostname=args.hostname,
        language=args.language,
        flavor=args.flavor,
        remove_snap=args.remove_snap,
        apt_packages=apt_packages,
        extras=list(args.extras),
        assume_yes=args.yes,
    )
    try:
        config.validate()
    except ValueError as error:
        raise SystemExit(f"error: {error}") from error

    target = find_target(config.device, list_devices())
    _confirm_or_exit(config, target.describe())
    config.device = target.path
    if args.dry_run:
        print("\nDry run: nothing was written. Re-run without --dry-run to install.")
        return

    Installer(config).run()
