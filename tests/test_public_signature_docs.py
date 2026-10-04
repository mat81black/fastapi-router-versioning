import dataclasses
import inspect

from collections.abc import Callable
from typing import Any, get_args, get_type_hints

import pytest

from annotated_doc import Doc

from fastapi_router_versioning import RouterVersioner, VersionInfo, api_version


def _doc_text(hint: Any) -> str | None:
    candidates = [hint, *get_args(hint)]
    return next(
        (
            meta.documentation
            for candidate in candidates
            for meta in getattr(candidate, "__metadata__", ())
            if isinstance(meta, Doc)
        ),
        None,
    )


@pytest.mark.parametrize(
    "target",
    [RouterVersioner.__init__, api_version],
    ids=["RouterVersioner.__init__", "api_version"],
)
def test_every_parameter_of_a_public_callable_is_documented(target: Callable[..., Any]) -> None:
    """The reference site is generated from these Doc annotations, so a parameter without one
    would be published with no description."""
    hints = get_type_hints(target, include_extras=True)
    names = [name for name in inspect.signature(target).parameters if name != "self"]

    assert names
    undocumented = [name for name in names if not _doc_text(hints[name])]
    assert undocumented == []


def test_every_version_info_field_is_documented() -> None:
    hints = get_type_hints(VersionInfo, include_extras=True)
    names = [field.name for field in dataclasses.fields(VersionInfo)]

    assert names == ["release_date", "guide"]
    undocumented = [name for name in names if not _doc_text(hints[name])]
    assert undocumented == []


def test_public_annotations_resolve_for_downstream_introspection() -> None:
    """typing.get_type_hints and inspect.signature(eval_str=True) are what third-party tools
    call on a typed package; both must resolve the Annotated/Doc annotations without a NameError."""
    for target in (RouterVersioner.__init__, api_version):
        assert get_type_hints(target)
        inspect.signature(target, eval_str=True)
    assert get_type_hints(VersionInfo)
