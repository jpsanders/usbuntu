# Changelog

Versions follow [semantic versioning](https://semver.org). Tags carry the bare version, such as `1.2.0`.

## 1.2.0 (2026-11-12)

- Safer: usbuntu now refuses a disk that holds the running system (`/`, `/boot`, `/boot/efi`, `/usr`, `/var`,
  `/home` or swap on it), both when it picks the stick itself and when `--device` names it. Before, on a machine that
  boots from a USB stick, its own disk could be offered for wiping, with only the `WIPE` prompt in the way.
- `usbuntu devices` lists every disk and says which ones usbuntu would accept, and why the rest are refused. It needs
  no root, and `--json` gives agents the same verdicts.
- A full manual: `usbuntu guide` prints it, `usbuntu man` shows it, `usbuntu man --install` makes `man usbuntu` work.
- `usbuntu --version` prints the real version.
- Python 3.14 or later; CI tests 3.14 and 3.15 and installs the built wheel on its own. A release workflow attaches
  the wheel and the sdist.
- A Claude Code plugin with the skill (now `skills/usbuntu/SKILL.md`), AGENTS.md, llms.txt, a security policy, a code
  of conduct, issue forms and Dependabot. The template's leftover Dockerfile and rename script are gone.

## 1.1.0 (2026-11-01)

Release notes on GitHub.

## 1.0.0 (2026-11-01)

The first release, verified end to end against the 26.04.1 desktop ISO. Release notes on GitHub.
