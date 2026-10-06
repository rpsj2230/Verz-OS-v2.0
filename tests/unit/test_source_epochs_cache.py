"""The answer key's source epochs, read through the cache (M6.2.5).

Over `brain.ops.connector_sync_store.ReadThroughSourceEpochs` with `brain.cache`'s own store on
an in-memory client, so what is kept is what Valkey would be handed. The counter it reads is
`StoredSourceEpochs`, which `tests/unit/test_connector_read_state.py` and the change-signal install
check prove against a database.

Task ids: M6.2.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from types import MappingProxyType, SimpleNamespace

from brain.api_routes import source_epochs_of
from brain.cache import source_epochs_cache
from brain.gate.caches import SOURCE_EPOCHS_KEY, SOURCE_EPOCHS_TTL_SECONDS
from brain.ops.connector_sync_store import ReadThroughSourceEpochs, SourceEpochs
from tests.unit.test_caches import DeadValkey, FakeValkey


class Counter:
    """`SourceEpochs` standing in for the database: what it holds now, and how often it was read."""

    def __init__(self, **held: int) -> None:
        self.held = dict(held)
        self.reads = 0

    async def epochs(self) -> Mapping[str, int]:
        self.reads += 1
        return MappingProxyType(dict(self.held))


def read(epochs: SourceEpochs) -> dict[str, int]:
    return dict(asyncio.run(epochs.epochs()))


def test_a_second_question_inside_the_lifetime_costs_no_database_read() -> None:
    """The leaf's point: one read of the counter serves every question until it expires, and is
    kept under the one key for the one lifetime. Delete this and the read-through can read the
    database on every question, which is the cost M6.2.5 exists to remove, with every answer still
    right."""
    counter = Counter(xero=3, freshdesk=1)
    client = FakeValkey()
    through = ReadThroughSourceEpochs(counter, source_epochs_cache(client))

    first = read(through)
    second = read(through)

    assert first == second == {"xero": 3, "freshdesk": 1}
    assert counter.reads == 1
    assert client.ttls == {SOURCE_EPOCHS_KEY: SOURCE_EPOCHS_TTL_SECONDS}


def test_an_expired_reading_is_read_again_and_a_moved_counter_reaches_the_key() -> None:
    """When the reading is gone the counter is read again, and what it now says is what the answer
    key gets. Delete this and a reading could be kept past its lifetime or rebuilt from the old
    one, so a source's change never reaches the answer cache's key."""
    counter = Counter(xero=3)
    client = FakeValkey()
    through = ReadThroughSourceEpochs(counter, source_epochs_cache(client))
    read(through)

    counter.held["xero"] = 4
    del client.data[SOURCE_EPOCHS_KEY]

    assert read(through) == {"xero": 4}
    assert counter.reads == 2


def test_a_cache_that_is_down_reads_the_counter_every_time_and_answers_the_same() -> None:
    """An unreachable cache slows a question down and never changes its key or fails it. Delete
    this and an outage could surface as an error on the answer route, or as an empty mapping that
    keys every answer as if no source had ever changed."""
    counter = Counter(xero=3)
    through = ReadThroughSourceEpochs(counter, source_epochs_cache(DeadValkey()))

    assert read(through) == {"xero": 3}
    assert read(through) == {"xero": 3}
    assert counter.reads == 2


def test_no_source_changed_yet_is_kept_as_a_reading_too() -> None:
    """An install whose worker has changed nothing has an empty counter table, and that is a
    reading like any other. Delete this and the empty case reads the database on every question
    for as long as no source has changed, which is the whole of a new install's first sync."""
    counter = Counter()
    through = ReadThroughSourceEpochs(counter, source_epochs_cache(FakeValkey()))

    assert read(through) == {}
    assert read(through) == {}
    assert counter.reads == 1


def test_the_answer_route_reads_the_epochs_the_application_installed() -> None:
    """`source_epochs_of` asks the reader on the application's state, which is where the lifespan
    puts the read-through. Delete this and the route can go back to building its own
    `StoredSourceEpochs`, so the cache is written by nobody and read by nobody."""
    counter = Counter(xero=3)
    through = ReadThroughSourceEpochs(counter, source_epochs_cache(FakeValkey()))
    state = SimpleNamespace(answer_store=object(), source_epochs=through, db_sessions=None)

    async def twice() -> tuple[Mapping[str, int], Mapping[str, int]]:
        return await source_epochs_of(state), await source_epochs_of(state)

    first, second = asyncio.run(twice())

    assert dict(first) == dict(second) == {"xero": 3}
    assert counter.reads == 1
