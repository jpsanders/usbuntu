"""A typed subprocess wrapper that logs every command it runs."""

import subprocess  # nosec B404: every call site passes a fixed argument list, never a shell
import sys
from collections.abc import Sequence


def _show(command: Sequence[str]) -> str:
    """
    Render a command for logging.

    :param command: The command and its arguments
    :returns: The command as a single quoted line
    """
    return " ".join(str(part) for part in command)


def run(command: Sequence[str], *, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
    """
    Run a command, logging it to stderr first.

    :param command: The command and its arguments as a list
    :param capture: Capture and return stdout instead of letting it inherit the terminal
    :param check: Raise ``CalledProcessError`` on a non-zero exit code
    :returns: The completed process with decoded stdout and stderr
    :raises subprocess.CalledProcessError: When ``check`` is set and the command fails
    """
    printed = _show(command)
    print(f"+ {printed}", file=sys.stderr)
    return subprocess.run(  # nosec B603: fixed argument list, no shell
        list(command),
        check=check,
        capture_output=capture,
        text=True,
    )


def try_run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """
    Run a command that is allowed to fail.

    :param command: The command and its arguments as a list
    :returns: The completed process with decoded stdout and stderr
    """
    printed = _show(command)
    print(f"+ {printed} (allowed to fail)", file=sys.stderr)
    return subprocess.run(  # nosec B603: fixed argument list, no shell
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )


def run_stdin(command: Sequence[str], text: str) -> subprocess.CompletedProcess[str]:
    """
    Run a command feeding it a script on standard input.

    Only the command is logged. The script text is deliberately not logged,
    because callers pass secrets such as the new account password in it.

    :param command: The command and its arguments as a list
    :param text: The script or input written to the command's standard input
    :returns: The completed process with decoded stdout and stderr
    :raises subprocess.CalledProcessError: When the command fails
    """
    printed = _show(command)
    print(f"+ {printed} <script on stdin, not logged>", file=sys.stderr)
    process = subprocess.run(  # nosec B603: fixed argument list, no shell
        list(command),
        check=False,
        capture_output=True,
        text=True,
        input=text,
    )
    if process.returncode != 0:
        # The captured stderr is the only record of the failure, since the
        # chroot output is never echoed while it runs. The script on stdin is
        # not echoed by the shell, so secrets stay out of the terminal and log.
        print(process.stderr, file=sys.stderr)
        raise subprocess.CalledProcessError(process.returncode, process.args, process.stdout, process.stderr)
    return process
