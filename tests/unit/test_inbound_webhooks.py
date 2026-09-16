"""The list of arriving webhooks the Webhooks screen draws, held against the source it describes.

Each row says whether a channel's check is written and names it, and every row says nothing
receives the request and nothing holds a secret. All three are claims about code, so each is
asserted against the code: the named function is imported, a channel said to have no check is
searched for one, and the application's routes are searched for an address a platform could post
to.

Task ids: M27.8.12
"""

from __future__ import annotations

import importlib
import inspect
import re

import pytest

from brain.agent_routes import CHANNEL_ADAPTERS
from brain.app import Settings, create_app
from brain.gate.context import Channel
from brain.ops.inbound_webhooks import INBOUND, InboundChannel, Verification

#: Parameter names a function checking where a request came from takes, in the modules that have
#: one: a signing secret, a signature, a token or key set, an Authorization header.
_CHECKING_PARAMETER = re.compile(r"secret|signature|authori[sz]ation|token|keys|presented|nonce")


def test_every_channel_an_adapter_declares_has_exactly_one_row() -> None:
    """Delete this and a channel added to the adapters is missing from the screen, which reads as
    a channel with nothing to say rather than one nobody described."""
    declared = {one().capabilities().channel for one in CHANNEL_ADAPTERS}
    listed = [one.channel for one in INBOUND]

    assert len(listed) == len(set(listed))
    assert declared <= set(listed)
    assert Channel.WEBHOOK in listed


def test_every_check_the_screen_names_is_a_function_its_module_has() -> None:
    """The positive half: a written row points at something real, and it takes a parameter a
    check needs. Delete this and a renamed function leaves the screen naming nothing."""
    written = [one for one in INBOUND if one.verification is Verification.WRITTEN]
    assert written
    for one in written:
        module, _, name = one.check.partition(":")
        found = getattr(importlib.import_module(module), name)
        assert callable(found), one.check
        parameters = list(inspect.signature(found).parameters)
        assert any(_CHECKING_PARAMETER.search(p) for p in parameters), (one.check, parameters)


@pytest.mark.parametrize(
    "channel", [one.channel for one in INBOUND if one.verification is Verification.NOT_WRITTEN]
)
def test_a_channel_said_to_have_no_check_has_no_function_that_could_be_one(
    channel: Channel,
) -> None:
    """**The sentence the screen replaced was false for exactly these channels.** Searched rather
    than trusted: no function in the channel's module takes a secret, a signature or a token.

    Delete this and the day somebody writes a check for one of them, the screen goes on telling an
    administrator that a forged request could not be told apart."""
    module = importlib.import_module(f"brain.channels.{channel.value}")
    checking = [
        f"{name}({', '.join(inspect.signature(function).parameters)})"
        for name, function in inspect.getmembers(module, inspect.isfunction)
        if function.__module__ == module.__name__
        and any(_CHECKING_PARAMETER.search(p) for p in inspect.signature(function).parameters)
    ]
    assert checking == []


def test_no_route_on_this_application_is_an_address_a_platform_could_post_to() -> None:
    """What every row says, held against the application's own routes. Delete this and a receiving
    route is mounted while the screen goes on saying nothing receives a webhook."""
    paths = create_app(Settings(env="development")).openapi()["paths"]
    channels = {one.channel.value for one in INBOUND}
    receiving = [
        path
        for path, operations in paths.items()
        if "post" in operations and channels & set(path.strip("/").split("/"))
    ]
    assert receiving == []
    assert any(path.endswith("/webhooks/subscribers") for path in paths)


def test_a_row_names_a_check_exactly_when_one_is_written() -> None:
    """Delete this and a row can say written beside an empty name, or name a function beside a
    state saying there is none."""
    with pytest.raises(ValueError, match="names its function"):
        InboundChannel(Channel.LARK, Verification.WRITTEN, "", "how")
    with pytest.raises(ValueError, match="names its function"):
        InboundChannel(Channel.LARK, Verification.NOT_WRITTEN, "brain.channels.lark:x", "how")
    with pytest.raises(ValueError, match="says how"):
        InboundChannel(Channel.LARK, Verification.NOT_WRITTEN, "", " ")
    assert InboundChannel(Channel.LARK, Verification.NOT_WRITTEN, "", "how").check == ""
