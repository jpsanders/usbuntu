"""The command line interface."""

import argparse
import getpass
import os
import sys
from pathlib import Path

from usbuntu.config import InstallConfig, generate_password
from usbuntu.devices import find_target, list_devices
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
    parser.add_argument("--version", action="version", version="usbuntu, version from git via setuptools_scm")
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
    return parser


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


def main() -> None:
    """
    Parse the arguments and run the requested command.

    :raises SystemExit: On a usage error, or when the user declines the wipe
    """
    parser = _build_parser()
    args = parser.parse_args()

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
