"""Where the evening digest goes: the saved value, what a connected channel offers, and why the
digest has stopped when it has.

Lark's group list is read here from the payload Lark documents, so the wire's reading is tested
against the vendor's shape rather than against a value this file built for it.

Task ids: M38.3.3.1, M38.3.3.4
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from brain.channels.adapter import VendorAnswer, VendorRequest
from brain.channels.lark import CANNOT_LIST_GROUPS, WIRE, LarkSecret
from brain.gate.context import Channel
from brain.ops.channel_store import ChannelRecord, ChannelSecretsUnavailableError
from brain.ops.digest_destination import (
    DESTINATION_SETTING,
    KEY_NOT_HELD,
    NOT_CONNECTED,
    SEND_TIME_SETTING,
    SWITCHED_OFF,
    VAULT_UNREADABLE,
    Destination,
    destination_of,
    is_offered,
    offered,
    standing,
)
from brain.ops.lark_connect import CHAT_LIST_SCOPE
from brain.ops.secrets import SecretRef, VaultRole
from tests.fixtures.lark_events import (
    APP_ID,
    APP_SECRET,
    BOT_OPEN_ID,
    ENCRYPT_KEY,
    VERIFICATION_TOKEN,
)

SECRET = LarkSecret(
    app_secret=APP_SECRET, encrypt_key=ENCRYPT_KEY, verification_token=VERIFICATION_TOKEN
).kept()
TENANT = {"app_id": APP_ID, "platform": "larksuite.com", "bot_id": BOT_OPEN_ID}
AT = datetime(2999, 1, 1, tzinfo=UTC)


def groups_page(groups: list[tuple[str, str]], *, more: str = "") -> dict[str, Any]:
    """One page of the bot's groups, as `GET /open-apis/im/v1/chats` answers."""
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "items": [
                {"chat_id": cid, "name": name, "owner_id": "ou_x", "external": False}
                for cid, name in groups
            ],
            "page_token": more,
            "has_more": bool(more),
        },
    }


def record(channel: Channel = Channel.LARK, *, enabled: bool = True) -> ChannelRecord:
    return ChannelRecord(
        channel=channel,
        enabled=enabled,
        tenant=TENANT,
        secret=SecretRef(path=f"providers/channel_{channel.value}", role=VaultRole.APPLICATION),
        updated_by="u_admin",
        updated_at=AT,
    )


class Secrets:
    """`ChannelSecrets` holding one value, or raising as a vault that cannot be read."""

    def __init__(self, value: str | None = SECRET, *, unreadable: bool = False) -> None:
        self.value = value
        self.unreadable = unreadable

    def read(self, ref: SecretRef) -> str | None:
        if self.unreadable:
            from brain.ops.channel_store import VaultState

            raise ChannelSecretsUnavailableError(VaultState.UNREACHABLE)
        return self.value

    def held(self, ref: SecretRef) -> bool:
        return self.value is not None


class Pages:
    """A transport answering each read with the next page, recording what was asked. Asked for
    nothing, it holds nothing, and a read then fails the test."""

    def __init__(self, *answers: Mapping[str, Any]) -> None:
        self.answers = list(answers)
        self.asked: list[VendorRequest] = []

    def send(self, request: VendorRequest) -> VendorAnswer:
        raise AssertionError("listing a channel's groups never sends")

    def read(self, request: VendorRequest) -> VendorAnswer:
        """The next page; the last one again once the rest are read, as a vendor asked twice."""
        self.asked.append(request)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return VendorAnswer(status=200, body=json.dumps(answer).encode())


def test_a_saved_value_names_a_channel_and_a_conversation_or_nothing() -> None:
    """Unset, empty and unreadable are all off. Delete this and a hand-edited value nobody can
    read is treated as a destination, and the digest is sent to a channel named by a typo."""
    chosen = destination_of("lark:oc_abc")
    assert chosen == Destination(Channel.LARK, "oc_abc")
    assert chosen is not None and chosen.saved == "lark:oc_abc"
    for off in ("unset", "", "  ", "lark", "nochannel:oc_abc", "lark:"):
        assert destination_of(off) is None
    assert DESTINATION_SETTING == "INSTALL_DIGEST_DESTINATION"
    assert SEND_TIME_SETTING == "INSTALL_DIGEST_TIME"


def test_lark_lists_the_bots_groups_page_by_page_from_the_payload_it_documents() -> None:
    """A GET with the token exchange beside it, every page followed, each group by id and name,
    and a group with no name offered by its id. Delete this and the list could stop at the first
    page, or a group with no name could be offered as a blank a person cannot choose."""
    first = WIRE.conversations_request(page="", secret=SECRET, tenant=TENANT)
    assert first.method == "GET" and first.exchange is not None
    assert urlsplit(first.url).path == "/open-apis/im/v1/chats"
    assert parse_qs(urlsplit(first.url).query) == {"page_size": ["100"]}
    later = WIRE.conversations_request(page="p2", secret=SECRET, tenant=TENANT)
    assert parse_qs(urlsplit(later.url).query)["page_token"] == ["p2"]

    body = json.dumps(groups_page([("oc_1", "Brain daily"), ("oc_2", " ")], more="p2")).encode()
    rows, following = WIRE.conversations_page(VendorAnswer(status=200, body=body))
    assert rows == (("oc_1", "Brain daily"), ("oc_2", "oc_2")) and following == "p2"
    last = json.dumps(groups_page([("oc_3", "Ops")])).encode()
    assert WIRE.conversations_page(VendorAnswer(status=200, body=last))[1] == ""


def test_lark_refusing_the_list_for_its_scope_is_said_in_words_naming_the_scope() -> None:
    """Delete this and an app without the scope offers an empty list with no reason, which reads
    as a bot in no groups rather than a bot that may not say."""
    refused = {"code": 99991672, "msg": f"Access denied. [{CHAT_LIST_SCOPE}]"}
    with pytest.raises(ValueError, match=CHAT_LIST_SCOPE):
        WIRE.conversations_page(VendorAnswer(status=200, body=json.dumps(refused).encode()))
    assert CHAT_LIST_SCOPE in CANNOT_LIST_GROUPS
    for broken in (b'{"code":0,"data":{"items":[{"name":"no id"}]}}', b'{"code":230002}'):
        with pytest.raises(ValueError):
            WIRE.conversations_page(VendorAnswer(status=200, body=broken))


def test_a_connected_channel_offers_every_group_on_every_page() -> None:
    """**The leaf's list.** Delete this and the offer could be built from something other than
    what the channel itself answered."""
    pages = Pages(groups_page([("oc_1", "Brain daily")], more="p2"), groups_page([("oc_2", "Ops")]))

    offers = asyncio.run(offered((record(),), secrets=Secrets(), transport=pages))

    assert [(o.channel, o.why_none) for o in offers] == [(Channel.LARK, "")]
    assert [(one.destination.saved, one.name) for one in offers[0].conversations] == [
        ("lark:oc_1", "Brain daily"),
        ("lark:oc_2", "Ops"),
    ]
    assert len(pages.asked) == 2
    assert is_offered(Destination(Channel.LARK, "oc_2"), offers)
    assert not is_offered(Destination(Channel.LARK, "oc_typed"), offers)


def test_a_channel_that_is_off_unkeyed_unreadable_or_cannot_list_offers_nothing_and_says_why() -> (
    None
):
    """Delete this and a switched-off channel could be offered, or an empty list shown with no
    reason, which reads as a channel with nowhere to post."""
    refused = {"code": 99991672, "msg": "Access denied."}
    cases = [
        (record(enabled=False), Secrets(), Pages(), SWITCHED_OFF),
        (record(), Secrets(None), Pages(), KEY_NOT_HELD),
        (record(), Secrets(unreadable=True), Pages(), VAULT_UNREADABLE),
        (record(), Secrets(), Pages(refused), CANNOT_LIST_GROUPS),
    ]
    for one, secrets, pages, why in cases:
        (offer,) = asyncio.run(offered((one,), secrets=secrets, transport=pages))
        assert offer.conversations == () and offer.why_none == why


def test_a_channel_whose_wire_cannot_list_is_not_a_choice_at_all() -> None:
    """The webhook channel posts to a subscriber and lists no conversations, so it is left out
    rather than offered empty. Delete this and every connected channel appears with an empty list
    beside the one that works."""
    offers = asyncio.run(offered((record(Channel.WEBHOOK),), secrets=Secrets(), transport=Pages()))
    assert offers == ()


def test_the_digest_standing_says_off_stopped_or_nothing() -> None:
    """Off until chosen; stopped, in words, when the chosen channel is gone, off or unkeyed; and
    empty only when it can go. Delete this and the Settings row can show a destination while the
    digest silently stopped."""
    assert standing("unset", record=None, secret_held=False) == (
        None,
        "Off: nobody has chosen where the evening digest goes.",
    )
    chosen = Destination(Channel.LARK, "oc_1")
    assert standing("lark:oc_1", record=None, secret_held=False) == (
        chosen,
        f"Stopped: {NOT_CONNECTED}",
    )
    assert standing("lark:oc_1", record=record(enabled=False), secret_held=True)[1] == (
        f"Stopped: {SWITCHED_OFF}"
    )
    assert standing("lark:oc_1", record=record(), secret_held=False)[1] == (
        f"Stopped: {KEY_NOT_HELD}"
    )
    assert standing("lark:oc_1", record=record(), secret_held=True) == (chosen, "")
