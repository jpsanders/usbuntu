"""Optional software the installer can add on top of the base system."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Extra:
    """A named bundle of apt packages and shell commands run inside the new system."""

    key: str
    description: str
    apt: tuple[str, ...]
    post_commands: tuple[str, ...]


def _build_registry() -> dict[str, Extra]:
    """
    Build the registry of known extras.

    :returns: Extra key to Extra mapping
    """
    registry = {}

    def add(extra: Extra) -> None:
        registry[extra.key] = extra

    add(
        Extra(
            key="opencode",
            description="OpenCode, the open source AI coding agent",
            apt=(),
            post_commands=("curl -fsSL https://opencode.ai/v2/install | bash",),
        )
    )
    add(
        Extra(
            key="claude-code",
            description="Claude Code CLI",
            apt=("nodejs", "npm"),
            post_commands=("npm install --global @anthropic-ai/claude-code",),
        )
    )
    add(
        Extra(
            key="build-tools",
            description="The usual C build toolchain",
            apt=("build-essential", "git", "curl", "wget"),
            post_commands=(),
        )
    )
    return registry


_EXTRAS = _build_registry()


def available() -> list[Extra]:
    """
    List every registered extra, in registration order.

    :returns: The registered extras
    """
    return list(_EXTRAS.values())


def resolve_extras(keys: list[str]) -> tuple[Extra, ...]:
    """
    Look up extras by key.

    :param keys: Extra keys as given on the command line
    :returns: The matching extras
    :raises ValueError: When a key is not registered
    """
    resolved = []
    for key in keys:
        if key not in _EXTRAS:
            raise ValueError(f"unknown extra {key!r}, available: {', '.join(sorted(_EXTRAS))}")
        resolved.append(_EXTRAS[key])
    return tuple(resolved)
