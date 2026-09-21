"""A chat message is claimed before anything answers it, and a leading mention names the agent.

The claim itself is `brain.gate.event_store.first_delivery`, held to the database in
`tests/unit/test_front_half_row.py`. This holds `brain.channels.inbound.claim` to calling it, on
the adapter's own event, before an address exists, and to answering nothing for a redelivery.

Task ids: M3.2.2, M3.9.8
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from brain.channels.inbound import claim
from brain.channels.lark import LarkAdapter
from brain.gate.context import Channel
from brain.gate.ingress import ChannelEvent
from tests.fixtures.scratch_postgres import run

AT = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)


class Adapter(LarkAdapter):
    """The Lark adapter with a normaliser that returns a fixed event, counting its calls."""

    def __init__(self, text: str, external_id: str = "m-1") -> None:
        super().__init__()
        self.text = text
        self.external_id = external_id

    def normalise(self, raw: object) -> ChannelEvent:
        del raw
        return ChannelEvent(
            channel=Channel.LARK,
            external_id=self.external_id,
            channel_identity="ou_someone",
            text=self.text,
            received_at=AT,
        )


class Claimed:
    """What `first_delivery`'s insert returns: a row when it went in, none on a conflict."""

    def __init__(self, went_in: bool) -> None:
        self.went_in = went_in

    def first(self) -> object | None:
        return object() if self.went_in else None


class Session:
    """A session whose unique index is a set of keys, so a second insert of one key conflicts."""

    def __init__(self) -> None:
        self.keys: set[tuple[str, str]] = set()
        self.inserts = 0

    async def execute(self, statement: Any) -> Claimed:
        self.inserts += 1
        values = statement.compile().params
        key = (values["channel"], values["external_id"])
        went_in = key not in self.keys
        self.keys.add(key)
        return Claimed(went_in)


def test_a_first_delivery_is_claimed_and_its_leading_mention_names_the_agent() -> None:
    """The event goes through the claim and comes back addressed to the agent it opens with.

    Delete this and an adapter can hand the gate a message nothing claimed."""
    session = Session()
    got = run(lambda: claim(session, Adapter("@finance what did Acme pay?"), {}))  # type: ignore[arg-type]
    assert session.inserts == 1
    assert got is not None
    assert got.address.agent_id == "finance"
    assert got.address.question == "what did Acme pay?"


def test_a_redelivered_message_is_answered_by_nothing() -> None:
    """M3.2.2: the second delivery of one message is refused by the claim, so no answer runs.

    Delete this and a provider retrying on a timeout gets two answers, or two side effects."""
    session = Session()
    adapter = Adapter("how many hours are left on Acme")
    assert run(lambda: claim(session, adapter, {})) is not None  # type: ignore[arg-type]
    assert run(lambda: claim(session, adapter, {})) is None  # type: ignore[arg-type]
    assert session.inserts == 2


def test_a_mention_inside_the_message_addresses_nobody() -> None:
    """Only a leading mention counts: text quoted from elsewhere cannot choose the agent."""
    session = Session()
    got = run(lambda: claim(session, Adapter("please forward to @finance"), {}))  # type: ignore[arg-type]
    assert got is not None
    assert got.address.agent_id is None
