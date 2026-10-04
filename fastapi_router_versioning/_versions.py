from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Annotated, Any, TypeAlias, TypeVar

from annotated_doc import Doc

CallableT = TypeVar("CallableT", bound=Callable[..., Any])
VersionT: TypeAlias = tuple[int, int] | str

_ATTR_API_VERSION = "_api_version"
_ATTR_DEPRECATE_IN = "_deprecate_in_version"
_ATTR_REMOVE_IN = "_remove_in_version"


class VersionFormat(str, Enum):
    """The versioning strategy a RouterVersioner enforces, and with it the type every version
    must have: ``SEMVER`` takes ``tuple[int, int]`` (e.g. ``(1, 0)``), ``CALVER`` takes ``str``
    (e.g. ``"2025-01-01"``, ``"v1"``).
    """

    SEMVER = "semver"
    CALVER = "calver"


@dataclass(frozen=True)
class VersionInfo:
    """Per-version metadata for ``RouterVersioner(version_info=...)``. Both fields are optional;
    only the ones you set have an effect. Nothing here changes routing.
    """

    release_date: Annotated[
        date | None,
        Doc(
            "The calendar date this version goes live (`datetime.date` or `datetime`; a `date` is read as midnight UTC, an aware `datetime` keeps its own offset and a naive one is read as UTC, so a naive `datetime` from a non-UTC local clock shifts the value clients see). Used only with `deprecation_headers=True`: on a route whose `deprecate_in` is this version it becomes the `Deprecation` header (RFC 9745); on a route whose `remove_in` is this version, the `Sunset` header (RFC 8594)."
        ),
    ] = None
    guide: Annotated[
        str | None,
        Doc(
            'URL of this version\'s upgrade guide. With `deprecation_headers=True` it is emitted as `Link: <guide>; rel="deprecation"` (RFC 9745) on routes deprecated at this version; it is also listed for the version on the versions endpoint and the dashboard, regardless of `deprecation_headers`.'
        ),
    ] = None


def _validate_api_version_arg(value: Any, param_name: str) -> None:
    if not isinstance(value, (tuple, str)):
        raise TypeError(
            f"api_version: '{param_name}' must be a tuple[int, int] (SemVer) or str (CalVer), "
            f"got {type(value).__name__!r} instead. "
            "Example: @api_version((1, 0)) or @api_version('2025-01-01')."
        )


def api_version(
    version: Annotated[
        VersionT,
        Doc(
            "The version this route first appears in: `tuple[int, int]` under `VersionFormat.SEMVER`, `str` under `VersionFormat.CALVER`."
        ),
    ],
    *,
    deprecate_in: Annotated[
        VersionT | None,
        Doc(
            "From this version on the route is flagged `deprecated` in the OpenAPI schema, and carries deprecation headers when `RouterVersioner` was built with `deprecation_headers=True`. It keeps being served."
        ),
    ] = None,
    remove_in: Annotated[VersionT | None, Doc("The first version that no longer serves the route.")] = None,
) -> Callable[[CallableT], CallableT]:
    """Annotate an endpoint with the version that introduces it, and optionally the versions
    that deprecate and remove it.

    The values are set as attributes on the decorated function, which is returned unchanged:
    there is no wrapper, so the signature FastAPI introspects stays the original one.

    Raises ``TypeError`` at decoration time if an argument is neither a tuple nor a str.
    Whether the type matches the configured ``VersionFormat`` is checked later, by
    ``RouterVersioner``.
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
    """The value of one VersionInfo field, or None when there is no map, no version, or no
    entry: "absent means nothing to say" is decided here instead of at each call site.
    """
    if version is None or version_info is None:
        return None
    info = version_info.get(version)
    return getattr(info, field) if info is not None else None
