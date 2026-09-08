"""Version types and the @api_version decorator: what a version is, and how a route declares
the one it belongs to. Nothing here knows about routing, docs or FastAPI apps.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, TypeAlias, TypeVar

CallableT = TypeVar("CallableT", bound=Callable[..., Any])
VersionT: TypeAlias = tuple[int, int] | str

_ATTR_API_VERSION = "_api_version"
_ATTR_DEPRECATE_IN = "_deprecate_in_version"
_ATTR_REMOVE_IN = "_remove_in_version"


class VersionFormat(str, Enum):
    """
    Defines the allowed versioning strategy for the RouterVersioner.
    """

    SEMVER = "semver"  # Accepts tuple[int, int] (e.g., (1, 0))
    CALVER = "calver"  # Accepts str (e.g., "2025-01-01", "v1")


@dataclass(frozen=True)
class VersionInfo:
    """Per-version metadata for ``RouterVersioner(version_info=...)``. Both fields are optional;
    only the ones you set have an effect. Nothing here changes routing.

    :param release_date: the calendar date this version goes live (``datetime.date`` or
        ``datetime``). Used only with ``deprecation_headers=True``: on a route whose
        ``deprecate_in`` is this version it becomes the RFC 9745 ``Deprecation`` header; on a
        route whose ``remove_in`` is this version, the RFC 8594 ``Sunset`` header.
    :param guide: URL of this version's upgrade guide. With ``deprecation_headers=True`` it is
        emitted as ``Link: <guide>; rel="deprecation"`` (RFC 9745) on routes deprecated at this
        version; it is also listed for the version on the ``/versions`` JSON endpoint and the
        versions dashboard, regardless of ``deprecation_headers``.
    """

    release_date: date | None = None
    guide: str | None = None


def _validate_api_version_arg(value: Any, param_name: str) -> None:
    if not isinstance(value, (tuple, str)):
        raise TypeError(
            f"api_version: '{param_name}' must be a tuple[int, int] (SemVer) or str (CalVer), "
            f"got {type(value).__name__!r} instead. "
            "Example: @api_version((1, 0)) or @api_version('2025-01-01')."
        )


def api_version(
    version: VersionT,
    *,
    deprecate_in: VersionT | None = None,
    remove_in: VersionT | None = None,
) -> Callable[[CallableT], CallableT]:
    """
    Decorator to annotate API routes with their specific version.

    Accepts both Semantic Versioning (e.g., tuple (1, 0)) and Calendar Versioning
    or strings (e.g., "2025-01-01", "v1").
    Metadata is injected directly into the wrapper function, allowing the
    RouterVersioner to organize the routes dynamically.
    """
    _validate_api_version_arg(version, "version")
    if deprecate_in is not None:
        _validate_api_version_arg(deprecate_in, "deprecate_in")
    if remove_in is not None:
        _validate_api_version_arg(remove_in, "remove_in")

    def decorator(func: CallableT) -> CallableT:
        setattr(func, _ATTR_API_VERSION, version)  # noqa: B010

        if deprecate_in is not None:
            setattr(func, _ATTR_DEPRECATE_IN, deprecate_in)  # noqa: B010

        if remove_in is not None:
            setattr(func, _ATTR_REMOVE_IN, remove_in)  # noqa: B010

        return func

    return decorator


def version_field(version_info: dict[VersionT, VersionInfo] | None, version: VersionT | None, field: str) -> Any:
    """One VersionInfo field for one version, or None when there is no map, no version, or no
    entry for it. Both the deprecation headers and the /versions payload look versions up this
    way, so the "absent means nothing to say" rule lives in one place.
    """
    if version is None or version_info is None:
        return None
    info = version_info.get(version)
    return getattr(info, field) if info is not None else None
