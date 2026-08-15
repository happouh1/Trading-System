"""Version parsing and namespaced hashing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from trading_system.serialization import canonical_hash

PACKAGE_VERSION = "0.2.0"
SPEC_VERSION = "1.0.0"
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
                     r"(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$")


@dataclass(frozen=True, slots=True, order=True)
class SemanticVersion:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    @classmethod
    def parse(cls, value: str) -> SemanticVersion:
        match = _SEMVER.fullmatch(value)
        if match is None:
            raise ValueError(f"invalid semantic version: {value!r}")
        return cls(int(match[1]), int(match[2]), int(match[3]), match[4], match[5])

    def __str__(self) -> str:
        result = f"{self.major}.{self.minor}.{self.patch}"
        result += f"-{self.prerelease}" if self.prerelease else ""
        result += f"+{self.build}" if self.build else ""
        return result


def versioned_hash(value: object, version: str = SPEC_VERSION) -> str:
    SemanticVersion.parse(version)
    return canonical_hash({"version": version, "payload": value})
