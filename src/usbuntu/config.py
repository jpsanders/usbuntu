"""The install configuration and its validation."""

import json
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from usbuntu.packages import resolve_extras

_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_HOSTNAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_APT_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9.+\-_]+$")


def generate_password() -> str:
    """
    Generate a readable random password for the new account.

    :returns: A URL-safe random string, without leading or trailing noise
    """
    return secrets.token_urlsafe(12)


@dataclass(slots=True)
class InstallConfig:
    """Everything the installer needs, gathered from the command line."""

    iso_path: Path
    device: str | None
    username: str
    user_password: str
    force_password_change: bool
    hostname: str
    language: str
    flavor: str
    remove_snap: bool
    apt_packages: list[str] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)
    assume_yes: bool = False

    def validate(self) -> None:
        """
        Check every field, raising with a plain message on the first problem.

        :raises ValueError: When a field is empty, malformed or unsafe
        """
        if not self.iso_path.is_file():
            raise ValueError(f"ISO not found: {self.iso_path}")
        if not re.fullmatch(_USERNAME_RE, self.username):
            raise ValueError(
                f"invalid username {self.username!r}: lowercase letters, digits, '-' and '_', "
                "must not start with a digit"
            )
        if not self.user_password:
            raise ValueError("password must not be empty")
        if not re.fullmatch(_HOSTNAME_RE, self.hostname):
            raise ValueError(f"invalid hostname {self.hostname!r}: lowercase letters, digits and '-'")
        if not re.fullmatch(r"^[a-z]{2,3}(_[A-Z]{2})?$", self.language):
            raise ValueError(f"invalid language code {self.language!r}, such as 'en' or 'pt_PT'")
        if self.flavor not in ("full", "minimal"):
            raise ValueError(f"invalid flavor {self.flavor!r}: 'full' or 'minimal'")
        for name in self.apt_packages:
            if not re.fullmatch(_APT_PACKAGE_RE, name):
                raise ValueError(f"invalid apt package name {name!r}")
        # Fail early on unknown extras, before anything is written.
        resolve_extras(self.extras)

    def summary(self) -> str:
        """
        Render the configuration for the confirmation prompt.

        :returns: A multi-line, human readable summary
        """
        lines = [
            f"ISO:       {self.iso_path}",
            f"Device:    {self.device}",
            f"Flavor:    {self.flavor} desktop, language {self.language}",
            f"Hostname:  {self.hostname}",
            f"User:      {self.username}",
            f"Snap:      {'removed' if self.remove_snap else 'kept'}",
        ]
        if self.apt_packages:
            lines.append(f"Apt:       {', '.join(self.apt_packages)}")
        if self.extras:
            lines.append(f"Extras:    {', '.join(self.extras)}")
        lines.append("Password:   set at the command line or generated, change "
                     f"{'forced at first login' if self.force_password_change else 'not forced'}")
        return "\n".join(lines)

    def to_json(self) -> str:
        """
        Serialise the configuration.

        :returns: The configuration as a JSON string
        """
        return json.dumps(
            {
                "iso_path": str(self.iso_path),
                "device": self.device,
                "username": self.username,
                "user_password": self.user_password,
                "force_password_change": self.force_password_change,
                "hostname": self.hostname,
                "language": self.language,
                "flavor": self.flavor,
                "remove_snap": self.remove_snap,
                "apt_packages": self.apt_packages,
                "extras": self.extras,
                "assume_yes": self.assume_yes,
            }
        )

    @classmethod
    def from_json(cls, text: str) -> InstallConfig:
        """
        Rebuild a configuration from its JSON form.

        :param text: The JSON string produced by :meth:`to_json`
        :returns: A new configuration object
        :raises ValueError: When the JSON is not a valid configuration
        """
        data = json.loads(text)
        config = cls(
            iso_path=Path(data["iso_path"]),
            device=data["device"],
            username=data["username"],
            user_password=data["user_password"],
            force_password_change=data["force_password_change"],
            hostname=data["hostname"],
            language=data["language"],
            flavor=data["flavor"],
            remove_snap=data["remove_snap"],
            apt_packages=list(data["apt_packages"]),
            extras=list(data["extras"]),
            assume_yes=bool(data["assume_yes"]),
        )
        config.validate()
        return config
