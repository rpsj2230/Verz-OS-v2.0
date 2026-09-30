"""The list of arriving webhooks the Webhooks screen draws, held against the source it describes.

Each row says whether a channel's check is written and names it, and the sentence above the rows
names the channels this release receives. All three are claims about code, so each is asserted
against the code: the named function is imported, a channel said to have no check is searched for
one, and the application's routes are searched for every address a platform could post to, which
is one route, received on only for the channels with a wire.

Task ids: M27.8.12, M10.2.1, M10.6.2
"""

from __future__ import annotations

import importlib
import inspect
import re
from collections.abc import Iterable, Iterator
from itertools import pairwise
from unittest.mock import patch

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from brain.agent_routes import CHANNEL_ADAPTERS
from brain.api import API_PREFIX
from brain.api_routes import asking
from brain.app import Settings, create_app
from brain.channel_routes import EVENTS_PATH, TEST_PATH
from brain.channels.adapter import channel_wires
from brain.gate.context import Channel
from brain.ops.inbound_webhooks import (
    CHANNEL_EVENTS_PATH,
    INBOUND,
    InboundChannel,
    Verification,
    receiving,
)
from brain.ops.webhook_admin import NO_CHANNEL_RECEIVES_A_WEBHOOK, receiving_told

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


def _checking_functions(channel: Channel) -> list[str]:
    """Every function the channel's module defines that takes a secret, a signature or a token."""
    module = importlib.import_module(f"brain.channels.{channel.value}")
    return [
        f"{name}({', '.join(inspect.signature(function).parameters)})"
        for name, function in inspect.getmembers(module, inspect.isfunction)
        if function.__module__ == module.__name__
        and any(_CHECKING_PARAMETER.search(p) for p in inspect.signature(function).parameters)
    ]


def test_a_channel_said_to_have_no_check_has_no_function_that_could_be_one() -> None:
    """**The sentence the screen replaced was false for exactly these channels.** Searched rather
    than trusted: no function in the channel's module takes a secret, a signature or a token. No
    row says not written since WhatsApp's check was written, so the search is held to a module
    where it must find one, and an empty answer for a row said to have none is still a finding.

    Delete this and the day somebody writes a check for a channel said to have none, the screen goes
    on telling an administrator that a forged request could not be told apart."""
    for one in INBOUND:
        if one.verification is Verification.NOT_WRITTEN:
            assert _checking_functions(one.channel) == [], one.channel
    assert "verify_signature(app_secret, signature, body)" in _checking_functions(Channel.WHATSAPP)


def _api_routes(routes: Iterable[object]) -> Iterator[APIRoute]:
    """Every route the application serves, through the routers it included.

    FastAPI 0.141 keeps an included router as one object holding the router it was given, which is
    why `tests/unit/test_api.py` reads the document instead; this walks into each one, and the test
    below holds the walk to the document so that a walk which stopped seeing routes fails."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _api_routes(included.routes)


def _posted_to_by_a_platform(route: APIRoute, channels: set[str]) -> bool:
    """A POST route a platform could send a channel's message to: one that takes no caller, since
    a platform has no session, and whose path names a channel or takes one as the parameter after
    `channels`, which is how `/channels/{name}/events` names it."""
    if "POST" not in (route.methods or set()):
        return False
    if any(one.call is asking for one in route.dependant.dependencies):
        return False
    parts = route.path.strip("/").split("/")
    after_channels = [one for before, one in pairwise(parts) if before == "channels"]
    return bool(channels & set(parts)) or any(one.startswith("{") for one in after_channels)


def test_the_one_address_a_platform_posts_to_is_the_channel_events_route() -> None:
    """What the screen says, held against the application's own routes. Exactly one route takes a
    platform's message, at `CHANNEL_EVENTS_PATH`, whichever channel it names, and the sentence
    above the list names exactly the channels with a receiver, each of which has a written check.

    Delete this and a second receiving route can be mounted, or a channel given a receiver, while
    the screen goes on naming the old ones."""
    app = create_app(Settings(env="development"))
    paths = app.openapi()["paths"]
    routes = list(_api_routes(app.routes))
    channels = {one.channel.value for one in INBOUND}
    receiving_paths = [route.path for route in routes if _posted_to_by_a_platform(route, channels)]
    assert receiving_paths == [API_PREFIX + EVENTS_PATH]
    # The guard on the guard: the walk sees every documented path, and the routes beside the one
    # that receives take a caller, so they would be counted if that check stopped being made.
    assert {route.path for route in routes} >= set(paths)
    assert API_PREFIX + TEST_PATH in {route.path for route in routes}
    assert API_PREFIX + EVENTS_PATH.replace("{name}", "{channel}") == CHANNEL_EVENTS_PATH
    assert any(path.endswith("/webhooks/subscribers") for path in paths)

    received = receiving()
    assert (
        received
        == frozenset(channel_wires())
        == {
            Channel.EMAIL,
            Channel.LARK,
            Channel.SLACK,
            Channel.TEAMS,
            Channel.WEBHOOK,
            Channel.WHATSAPP,
        }
    )
    told = receiving_told()
    assert told != NO_CHANNEL_RECEIVES_A_WEBHOOK
    for one in INBOUND:
        named = f"for: {one.channel.value}" in told or f", {one.channel.value}" in told
        assert named == (one.channel in received), one.channel
        if one.channel in received:
            assert one.verification is Verification.WRITTEN


def test_a_channel_with_no_receiver_answers_at_the_address_as_though_nothing_were_there() -> None:
    """The sentence's "every other channel's address answers as though nothing were there", asked
    of the running application for every channel with no wire, and for a name that is no channel.

    Delete this and the templated route could start receiving for a channel whose check the screen
    lists as not written."""
    with TestClient(create_app(Settings(env="development"))) as client:
        for name in [
            *(one.channel.value for one in INBOUND if one.channel not in receiving()),
            "x",
        ]:
            answer = client.post(API_PREFIX + EVENTS_PATH.format(name=name), content=b"{}")
            assert answer.status_code == 404, name


def test_with_no_receiver_the_screen_says_no_channel_receives() -> None:
    """The other branch of the sentence. Delete this and a release whose receivers were all removed
    could tell an administrator the address still works."""
    with patch("brain.ops.webhook_admin.receiving", return_value=frozenset()):
        assert receiving_told() == NO_CHANNEL_RECEIVES_A_WEBHOOK


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
