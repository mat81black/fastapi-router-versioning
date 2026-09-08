from datetime import date
from typing import Any

from ._versions import VersionFormat, VersionInfo, VersionT


def format_string(format_str: str, version: VersionT) -> str:
    if isinstance(version, tuple):
        return format_str.format(major=version[0], minor=version[1], version=f"{version[0]}_{version[1]}")
    return format_str.format(version=version, major=version, minor=version)


def version_gte(a: VersionT, b: VersionT) -> bool:
    if isinstance(a, tuple) and isinstance(b, tuple):
        return a >= b
    if isinstance(a, str) and isinstance(b, str):
        return a >= b
    return False


class VersionScheme:
    """The version dialect in use: SemVer tuples or CalVer strings, and the formats that turn
    one into a mount prefix and a documentation label.
    """

    def __init__(
        self,
        version_format: VersionFormat,
        prefix_format: str,
        semantic_version_format: str,
        default_version: VersionT,
    ) -> None:
        self.version_format = version_format
        self.prefix_format = prefix_format
        self.semantic_version_format = semantic_version_format
        self.default_version = default_version

    @classmethod
    def build(
        cls,
        version_format: VersionFormat,
        prefix_format: str | None,
        semantic_version_format: str | None,
        default_version: VersionT | None,
    ) -> "VersionScheme":
        """Fills in the formats and the fallback version that version_format implies, and
        validates default_version when the caller gave one. A default computed here is correct
        by construction and is not re-validated.
        """
        if prefix_format is None:
            prefix_format = "/v{major}_{minor}" if version_format == VersionFormat.SEMVER else "/{version}"

        if semantic_version_format is None:
            semantic_version_format = "{major}.{minor}" if version_format == VersionFormat.SEMVER else "{version}"

        if default_version is None:
            resolved_default: VersionT = (1, 0) if version_format == VersionFormat.SEMVER else "1"
            scheme = cls(version_format, prefix_format, semantic_version_format, resolved_default)
        else:
            scheme = cls(version_format, prefix_format, semantic_version_format, default_version)
            scheme.validate(default_version, "default_version fallback")

        return scheme

    def validate(self, version: Any, route_path: str) -> None:
        if self.version_format == VersionFormat.SEMVER:
            if not isinstance(version, tuple) or len(version) != 2 or not all(isinstance(i, int) for i in version):
                error_msg = f"RouterVersioner expects SEMVER, but found an invalid version '{version}' on {route_path}. Use a tuple of exactly two integers: (major, minor). e.g., (1, 0)."
                raise ValueError(error_msg)
        elif self.version_format == VersionFormat.CALVER:
            if not isinstance(version, str):
                error_msg = f"RouterVersioner expects CALVER, but found a non-string version '{version}' on {route_path}. Use a string like '2025-01-01'."
                raise ValueError(error_msg)

    def prefix(self, version: VersionT) -> str:
        return format_string(self.prefix_format, version)

    def doc_version(self, version: VersionT) -> str:
        return format_string(self.semantic_version_format, version)

    def extract(self, endpoint: Any, attribute: str, route_path: str) -> VersionT | None:
        val = getattr(endpoint, attribute, None)
        if isinstance(val, (tuple, str)):
            self.validate(val, route_path)
            return val
        return None


def validate_version_info(
    version_info: dict[VersionT, VersionInfo] | None, scheme: VersionScheme
) -> dict[VersionT, VersionInfo] | None:
    if version_info is None:
        return None
    if not isinstance(version_info, dict):
        raise TypeError(
            f"version_info must be a dict mapping version -> VersionInfo, got {type(version_info).__name__!r} instead."
        )
    for key, value in version_info.items():
        scheme.validate(key, "version_info key")
        if not isinstance(value, VersionInfo):
            raise TypeError(f"version_info[{key!r}] must be a VersionInfo, got {type(value).__name__!r} instead.")
        if value.release_date is not None and not isinstance(value.release_date, date):
            raise TypeError(
                f"version_info[{key!r}].release_date must be a datetime.date (or datetime), "
                f"got {type(value.release_date).__name__!r} instead."
            )
        if value.guide is not None:
            if not isinstance(value.guide, str):
                raise TypeError(
                    f"version_info[{key!r}].guide must be a str (URL), got {type(value.guide).__name__!r} instead."
                )
            if "\n" in value.guide or "\r" in value.guide:
                # It is interpolated into a Link response header; a newline there is a
                # header-injection attempt or a typo. Fail here, not at response time.
                raise ValueError(f"version_info[{key!r}].guide must not contain a newline.")
    return version_info
