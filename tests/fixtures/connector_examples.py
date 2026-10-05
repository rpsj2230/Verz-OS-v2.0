"""The settings every test connects a connector with, read off the connector's own declaration.

Until 2026-10-05 five test files each typed one identifier and the further settings per connector,
the same values in every one, and every connector PR appended a row to all five, so every connector
that landed put every other open one in conflict. Each connector now declares them once, as its
form's `ConnectExample.settings` (`brain.connectors.declaration`), and these read them.

Task ids: M11.1.6
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from brain.connectors.declaration import ConnectExample, shipped


def _example(name: str) -> ConnectExample:
    form = shipped()[name].console
    assert form is not None, f"{name} has no console form, so nothing connects it with settings"
    assert form.example is not None, f"{name}'s form declares no example settings"
    return form.example


#: Every declared form's example settings, by the connector's name.
EXAMPLES: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        name: MappingProxyType(dict(_example(name).settings))
        for name, one in shipped().items()
        if one.console is not None
    }
)


def example_settings(name: str) -> dict[str, str]:
    """Every setting `name`'s form asks for, as its declaration's example gives them."""
    return dict(_example(name).settings)


def identifier(name: str) -> str:
    """The first setting `name`'s form asks for, which its scope is pinned to, from the example."""
    form = shipped()[name].console
    assert form is not None
    return example_settings(name)[form.settings[0].name]
