"""
Rename the template's package in place.

Run once, right after creating a repository from the template::

    python scripts/rename.py acme_widgets

It replaces the import name ``python_template`` and the distribution, command
and image name ``python-template`` in every tracked text file, then moves the
package and test directories to the new name. Nothing else is touched.
"""

import argparse
import re
import subprocess  # nosec B404: runs git with fixed arguments only
import sys
from pathlib import Path

OLD_IMPORT = "python_template"
OLD_DIST = "python-template"
ROOT = Path(__file__).resolve().parent.parent


def tracked_files() -> list[Path]:
    """
    List the files git tracks, so build output and virtual envs are skipped.

    :returns: Absolute paths of tracked files
    """
    out = subprocess.run(  # nosec B603 B607: fixed git command, no shell
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout
    return [ROOT / p for p in out.decode().split("\0") if p]


def rename(import_name: str, dist_name: str) -> list[str]:
    """
    Replace the template names and move the package directories.

    :param import_name: New import name, such as ``acme_widgets``
    :param dist_name: New distribution and command name, such as ``acme-widgets``
    :returns: Paths that changed, relative to the repository root
    :raises SystemExit: When the template was already renamed
    """
    if not (ROOT / "src" / OLD_IMPORT).is_dir():
        raise SystemExit(f"src/{OLD_IMPORT} not found: this repository was already renamed")
    changed = []
    for path in tracked_files():
        if path.resolve() == Path(__file__).resolve() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = text.replace(OLD_IMPORT, import_name).replace(OLD_DIST, dist_name)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(str(path.relative_to(ROOT)))
    for parent in ("src", "tests"):
        old_dir = ROOT / parent / OLD_IMPORT
        if old_dir.is_dir():
            old_dir.rename(ROOT / parent / import_name)
            changed.append(f"{parent}/{OLD_IMPORT} -> {parent}/{import_name}")
    return changed


def main() -> None:
    """Parse the arguments and rename."""
    parser = argparse.ArgumentParser(description="Rename the template package.")
    parser.add_argument("import_name", help="new import name, lowercase with underscores")
    parser.add_argument("--dist", help="distribution and command name (default: import name with hyphens)")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.import_name):
        sys.exit("import name must be lowercase letters, digits and underscores, starting with a letter")
    dist_name = args.dist or args.import_name.replace("_", "-")
    for line in rename(args.import_name, dist_name):
        print(line)


if __name__ == "__main__":
    main()
