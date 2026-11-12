# Security

## Reporting a vulnerability

Please report security problems privately, through GitHub's
[private vulnerability reporting](https://github.com/jpsanders/usbuntu/security/advisories/new), not in a public
issue. You will get an answer within a week.

## What usbuntu does on your machine

`install` runs as root and erases the target disk. It refuses any disk that is not on USB, not removable, smaller
than 8 GiB, or holding the running system, refuses to guess between several candidates, and asks the user to type
`WIPE` unless `--yes` is given. `inspect` and `verify` run as root to mount the ISO or the stick, and write nothing.
`devices`, `guide` and `man` need no root.

The account password reaches the new system through a pipe, never a file, an argument list or the log. Every root run
appends its commands and errors to `/var/log/usbuntu.log`, which is readable by root only on a standard Ubuntu.

There is deliberately no MCP server: erasing a disk should stay a decision a person makes at a terminal.
