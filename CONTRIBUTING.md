# Contributing

Issues and pull requests are welcome. A bug report is easiest to act on with the end of `/var/log/usbuntu.log`, the
ISO's file name and `usbuntu devices --json`.

## Set up

```sh
git clone https://github.com/jpsanders/usbuntu && cd usbuntu
python3.15 -m venv .venv && . .venv/bin/activate
make init-dev
```

## Before a pull request

```sh
make format      # black and isort
make checks      # every check CI runs, in the same order
```

`make checks` runs isort, black, editorconfig-checker, darglint, flake8, mypy in strict mode, bandit, the man page
check and pytest with coverage. CI runs the tests on Python 3.14 and 3.15, then installs the built wheel on its own.
Changes to the install pipeline also need a real run on a stick; say which ISO and stick in the pull request.
