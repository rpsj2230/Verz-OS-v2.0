"""Send the evening digest to, over HTTP: read, chosen from the list, switched off, and refused to
anybody without the Settings screen's authority.

The channel record, its secret and the vendor are stand-ins on the application's state, the way
`brain.channel_routes` lets a test put them there; the save goes through the Settings screen's own
upsert, answered by the same stub rows its tests use.

Task ids: M38.3.3.1, M38.3.3.4
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.digest_routes import DESTINATION_PATH
from brain.install import hold_saved, value_of
from brain.ops.digest_destination import DESTINATION_SETTING
from tests.fixtures.console_http import Stub, console_client, get, headers
from tests.unit.test_digest_destination import Pages, Secrets, groups_page, record
from tests.unit.test_settings_routes import GRANTS, InstallRows

PATH = f"{API_PREFIX}{DESTINATION_PATH}"


class Records:
    """`ChannelRecords` holding the one Lark record."""

    def __init__(self, *held: Any) -> None:
        self.held = held

    async def every(self) -> tuple[Any, ...]:
        return tuple(self.held)

    async def get(self, channel: Any) -> Any:
        return next((one for one in self.held if one.channel is channel), None)

    async def save(self, channel: Any, **_: Any) -> Any:
        raise AssertionError("choosing a destination never writes a channel record")

    async def switch(self, channel: Any, **_: Any) -> Any:
        raise AssertionError("choosing a destination never switches a channel")


@pytest.fixture(autouse=True)
def nothing_saved() -> Iterator[None]:
    before = hold_saved({})
    yield
    hold_saved(before)


@pytest.fixture
def served() -> Iterator[tuple[TestClient, Stub, InstallRows]]:
    rows = InstallRows()
    with console_client(GRANTS) as (client, stub):
        stub.answerers.append(rows.answer)
        app: Any = client.app
        app.state.channel_records = Records(record())
        app.state.channel_secrets = Secrets()
        yield client, stub, rows


def listing(client: TestClient) -> None:
    app: Any = client.app
    app.state.channel_transport = Pages(groups_page([("oc_1", "Brain daily"), ("oc_2", "Ops")]))


def test_the_page_is_off_until_chosen_and_offers_each_group_the_bot_is_in(
    served: tuple[TestClient, Stub, InstallRows],
) -> None:
    """Delete this and the Settings row could offer nothing, or name a destination nobody chose."""
    client, _, _ = served
    listing(client)

    page = get(client, "u_admin", PATH).json()

    assert page["channel"] is None and page["stopped_because"].startswith("Off:")
    assert page["offers"] == [
        {
            "channel": "lark",
            "conversations": [
                {"channel": "lark", "conversation": "oc_1", "name": "Brain daily"},
                {"channel": "lark", "conversation": "oc_2", "name": "Ops"},
            ],
            "why_none": "",
        }
    ]


def test_a_group_on_the_list_is_saved_audited_and_outranks_the_environment(
    served: tuple[TestClient, Stub, InstallRows],
) -> None:
    """**The leaf's choice.** Saved as the Settings screen saves, with the chooser attributed before
    the write, and read back through `value_of` ahead of any environment value.

    Delete this and a choice could be kept somewhere the worker does not read, or unattributed."""
    client, stub, rows = served
    listing(client)

    answered = client.put(
        PATH, json={"channel": "lark", "conversation": "oc_2"}, headers=headers("u_admin")
    )

    assert answered.status_code == 200, answered.text
    assert answered.json()["channel"] == "lark" and answered.json()["conversation"] == "oc_2"
    assert answered.json()["stopped_because"] == ""
    assert rows.writes and rows.writes[-1]["key"] == "install.digest_destination"
    assert rows.writes[-1]["value"] == "lark:oc_2"
    assert ("brain.actor_id", "u_admin") in stub.attributions
    assert value_of(DESTINATION_SETTING, {DESTINATION_SETTING: "lark:oc_env"}) == "lark:oc_2"


def test_an_id_that_is_not_on_the_list_is_refused_and_nothing_is_written(
    served: tuple[TestClient, Stub, InstallRows],
) -> None:
    """Delete this and a typed id that is wrong by one character is saved, and the digest posts
    nowhere, or somewhere nobody meant."""
    client, _, rows = served
    listing(client)

    refused = client.put(
        PATH, json={"channel": "lark", "conversation": "oc_typed"}, headers=headers("u_admin")
    )
    no_channel = client.put(
        PATH, json={"channel": "nowhere", "conversation": "oc_1"}, headers=headers("u_admin")
    )

    assert (refused.status_code, no_channel.status_code) == (404, 404)
    assert rows.writes == []


def test_off_is_saved_as_unset_and_the_digest_says_it_is_off(
    served: tuple[TestClient, Stub, InstallRows],
) -> None:
    """Delete this and there is no way to stop the digest from the console once it is chosen."""
    client, _, rows = served
    listing(client)

    answered = client.put(PATH, json={"off": True}, headers=headers("u_admin"))

    assert answered.status_code == 200
    assert rows.writes[-1]["value"] == "unset"
    assert answered.json()["stopped_because"].startswith("Off:")


@pytest.mark.parametrize("pid", ["u_none", "u_narrow", "u_wide"])
def test_a_caller_without_the_settings_authority_is_refused_before_a_channel_is_asked(
    served: tuple[TestClient, Stub, InstallRows], pid: str
) -> None:
    """The read and the write, refused alike, with no vendor asked and nothing written. Delete this
    and a caller with a department's grant learns which channels the install has connected."""
    client, _, rows = served
    pages = Pages()
    app: Any = client.app
    app.state.channel_transport = pages

    read = get(client, pid, PATH)
    write = client.put(PATH, json={"off": True}, headers=headers(pid))

    assert (read.status_code, write.status_code) == (404, 404)
    assert pages.asked == [] and rows.writes == []


def test_a_chosen_channel_that_is_switched_off_later_stops_and_says_why(
    served: tuple[TestClient, Stub, InstallRows],
) -> None:
    """Delete this and the Settings row keeps showing a destination the digest can no longer
    reach, with nothing saying it has stopped."""
    client, _, _ = served
    app: Any = client.app
    app.state.channel_records = Records(record(enabled=False))
    app.state.channel_transport = Pages()
    hold_saved({DESTINATION_SETTING: "lark:oc_2"})

    page = get(client, "u_admin", PATH).json()

    assert page["channel"] == "lark" and page["conversation"] == "oc_2"
    assert page["stopped_because"] == "Stopped: This channel is switched off."
