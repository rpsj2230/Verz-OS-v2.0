"""Where a read of a connected source stands, what the next one asks for, and what moves an epoch.

`brain.ops.connector_sync` decides all of it without a connection, so every property here is held
without one; `tests/unit/test_connector_change_signals.py` drives the worker's run over a database,
and `tests/unit/test_acceptance_change_signals.py` the install's checks. The helpdesk here is
Freshdesk's own reading, because it is the one this release can ask for only what changed, and the
ledger is Xero's, because it cannot.

**Each decision is held from both sides.** A read of changes has a sibling that reads everything,
a read carried on has one that begins, and a page that changes the index has one that only
confirms it; a function answering every question the same way fails one of each pair.

Task ids: M11.4.6, M11.4.8, M11.8.4, M11.8.11
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from types import MappingProxyType, SimpleNamespace
from typing import Any, Final, cast

import pytest

from brain.api_routes import (
    AN_ANSWER_IS_KEYED_ON_EVERY_SOURCE_ITS_READER_REACHES,
    caching_of,
    source_epochs_of,
)
from brain.connectors.backfill import BackfillCursor
from brain.connectors.change_signal import MAX_RECONCILE_INTERVAL, DeletionCheck
from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import ChangedSince
from brain.connectors.freshdesk import (
    EVERY_TICKET_SINCE,
    FRESHDESK,
    READING_INTERVAL,
    RECONCILE_EVERY,
    TICKET,
    UPDATED_SINCE_FORMAT,
    FreshdeskReading,
)
from brain.connectors.manifest import ChangeSignal
from brain.connectors.projection import ProjectedRecord
from brain.gate.cache_key import key_for
from brain.ops.connector_sync import (
    CURSOR_OVERLAP,
    READINGS,
    ReadPass,
    ReadState,
    ReadStateError,
    SourceReading,
    StoredValue,
    after_the_read,
    changed,
    next_read,
    page_cursor,
    page_of,
    page_to_ask,
)

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
HOUR: Final = timedelta(hours=1)

HELPDESK: Final = FreshdeskReading()
#: Xero's reading, which is a `SourceReading`; `READINGS` also holds a database's views.
LEDGER: Final = cast(SourceReading, READINGS["xero"])


def the_second_page() -> Mapping[str, str]:
    """The helpdesk list's second page, as its own paging names it."""
    first = HELPDESK.first_page(TICKET)
    following = HELPDESK.next_page(TICKET, first, [], 100)
    assert following is not None
    return following


def walked_to(page: Mapping[str, str]) -> BackfillCursor:
    """A ticket walk that has read one full page and would ask `page` next."""
    return BackfillCursor(connector=FRESHDESK, entity=TICKET).advance(
        cursor=page_cursor(page), returned=100, exhausted=False
    )


def walked_through() -> BackfillCursor:
    """A ticket walk read to its last page."""
    return BackfillCursor(connector=FRESHDESK, entity=TICKET).advance(
        cursor="", returned=3, exhausted=True
    )


# ------------------------------------------------------------------ what the next read asks
def test_a_new_connection_is_read_from_the_beginning() -> None:
    """M11.4.6's first clause: a connection with no state is read whole, and the helpdesk's whole is
    `updated_since` 2000, since without it the list holds only a month. Delete this and a first read
    could ask from a cursor nothing set."""
    read = next_read(HELPDESK, None, now=NOW)
    assert read == ReadPass(started_at=NOW) and read.everything
    first = page_to_ask(HELPDESK, read, read.walk(FRESHDESK, TICKET))
    assert first is not None and first["updated_since"] == EVERY_TICKET_SINCE


def test_a_helpdesk_read_to_the_end_is_next_asked_only_for_what_changed_since_that_read_began() -> (
    None
):
    """M11.4.6: the cursor is the last complete read's start, less the overlap, written in the
    vendor's form, and it is the one argument the first page changes. Delete this and a read of
    changes could ask from the end of the last read, which loses what changed while it walked."""
    state = ReadState(changed_since=NOW - HOUR, reconciled_at=NOW - HOUR)
    read = next_read(HELPDESK, state, now=NOW)
    assert (read.started_at, read.since) == (NOW, NOW - HOUR - CURSOR_OVERLAP)
    assert not read.everything
    asked = page_to_ask(HELPDESK, read, read.walk(FRESHDESK, TICKET))
    whole = HELPDESK.first_page(TICKET)
    assert asked is not None
    assert asked["updated_since"] == (NOW - HOUR - CURSOR_OVERLAP).strftime(UPDATED_SINCE_FORMAT)
    assert {name for name in whole if asked[name] != whole[name]} == {"updated_since"}


def test_a_read_owed_its_reconciliation_reads_everything_and_one_a_second_short_does_not() -> None:
    """`A_CURSOR_CANNOT_SEE_A_DELETION`: once the subscription's reconciliation falls due the read
    is whole again, because only a whole read can notice a ticket that went. Delete this and a
    helpdesk read by cursor alone never notices a deletion."""
    owed = ReadState(changed_since=NOW - HOUR, reconciled_at=NOW - RECONCILE_EVERY)
    assert next_read(HELPDESK, owed, now=NOW).everything
    early = dataclasses.replace(owed, reconciled_at=NOW - RECONCILE_EVERY + timedelta(seconds=1))
    assert not next_read(HELPDESK, early, now=NOW).everything


def test_a_source_never_read_whole_is_read_whole_before_it_is_read_for_changes() -> None:
    """A state with a cursor and no reconciliation is a source whose deletions were never looked
    for, so it is read whole. Delete this and a state written by a read of changes alone would
    keep a source off reconciliation for good."""
    state = ReadState(changed_since=NOW - HOUR, reconciled_at=None)
    assert next_read(HELPDESK, state, now=NOW).everything


def test_a_source_that_cannot_be_asked_for_its_changes_is_read_whole_every_time() -> None:
    """Xero's changes are asked by a header a reading cannot send, so every Xero read is whole,
    which is also what lets every complete Xero read retire. Delete this and a reading with no
    `changed_since` could be planned a read of changes it would answer with everything."""
    assert isinstance(HELPDESK, ChangedSince)
    assert not isinstance(LEDGER, ChangedSince)
    state = ReadState(changed_since=NOW - HOUR, reconciled_at=NOW - HOUR)
    assert next_read(LEDGER, state, now=NOW).everything


def test_a_read_that_stopped_is_carried_on_from_its_own_page_with_its_own_since() -> None:
    """M11.4.8: a read an attempt stopped inside is the next attempt's read, its start and what it
    asked for unchanged, and its walk asks the page after the last one read; a walk read to its end
    asks nothing. Delete this and a read cut short starts again at page one, spending again every
    call it spent."""
    page = the_second_page()
    stopped = ReadPass(
        started_at=NOW - 2 * HOUR,
        since=NOW - 3 * HOUR,
        walks=MappingProxyType({TICKET: walked_to(page)}),
    )
    state = ReadState(changed_since=NOW - 3 * HOUR, reconciled_at=NOW - 3 * HOUR, walking=stopped)
    read = next_read(HELPDESK, state, now=NOW)
    assert read == stopped
    assert page_to_ask(HELPDESK, read, read.walk(FRESHDESK, TICKET)) == page
    assert page_to_ask(HELPDESK, read, walked_through()) is None


# ---------------------------------------------------------------------- what a read leaves
def test_a_complete_read_moves_the_cursor_and_only_a_read_of_everything_the_reconciliation() -> (
    None
):
    """A read to the end becomes the cursor from its own start, and a whole one is also the last
    reconciliation; a read of changes leaves the reconciliation where it was. Delete this and a
    read of changes could count as a reconciliation, and deletions would never be looked for."""
    done = MappingProxyType({TICKET: walked_through()})
    before = ReadState(changed_since=NOW - HOUR, reconciled_at=NOW - 20 * HOUR)
    whole = ReadPass(started_at=NOW, walks=done)
    assert after_the_read(before, whole, (TICKET,)) == ReadState(
        changed_since=NOW, reconciled_at=NOW
    )
    changes = ReadPass(started_at=NOW, since=NOW - HOUR, walks=done)
    assert after_the_read(before, changes, (TICKET,)) == ReadState(
        changed_since=NOW, reconciled_at=NOW - 20 * HOUR
    )


def test_a_read_that_stopped_keeps_the_cursor_it_had_and_is_left_to_be_carried_on() -> None:
    """A read not complete moves no cursor and is kept to carry on; a read with an entity it has
    not begun, or with no entity at all, is not complete. Delete this and a read cut short at page
    one moves the cursor past every record it never asked for."""
    part = ReadPass(started_at=NOW, walks=MappingProxyType({TICKET: walked_to(the_second_page())}))
    before = ReadState(changed_since=NOW - HOUR, reconciled_at=NOW - 20 * HOUR)
    assert after_the_read(before, part, (TICKET,)) == dataclasses.replace(before, walking=part)
    assert after_the_read(None, part, (TICKET,)) == ReadState(walking=part)
    assert not ReadPass(started_at=NOW).complete((TICKET,))
    assert not ReadPass(started_at=NOW).complete(())
    done = ReadPass(started_at=NOW, walks=MappingProxyType({TICKET: walked_through()}))
    assert done.complete((TICKET,)) and not done.complete((TICKET, "contact"))


def test_a_read_state_is_stored_as_json_and_read_back_whole() -> None:
    """The column round trip: instants with their zone, and each walk's cursor and counts. Delete
    this and a state the worker wrote could read back as none, and every read would start again."""
    walking = ReadPass(
        started_at=NOW - HOUR,
        since=NOW - 2 * HOUR,
        walks=MappingProxyType(
            {
                TICKET: walked_to(the_second_page()),
                "other": dataclasses.replace(walked_through(), entity="other"),
            }
        ),
    )
    state = ReadState(changed_since=NOW - 2 * HOUR, reconciled_at=NOW - 9 * HOUR, walking=walking)
    stored = json.loads(json.dumps(state.stored()))
    assert ReadState.from_stored(FRESHDESK, stored) == state
    assert ReadState.from_stored(FRESHDESK, ReadState().stored()) == ReadState()


@pytest.mark.parametrize(
    "stored",
    [
        None,
        [],
        "a string",
        {"walking": "a string"},
        {"changed_since": 5},
        {"changed_since": "2999-01-01T09:00:00"},
        {"walking": {"started_at": None, "walks": {}}},
        {"walking": {"started_at": "2999-01-01T09:00:00+00:00", "walks": []}},
        {
            "walking": {
                "started_at": "2999-01-01T09:00:00+00:00",
                "walks": {
                    "ticket": {"cursor": "[1]", "pages": 1, "records": 1, "exhausted": False}
                },
            }
        },
        {
            "walking": {
                "started_at": "2999-01-01T09:00:00+00:00",
                "walks": {"ticket": {"cursor": "", "pages": -1, "records": 0, "exhausted": False}},
            }
        },
    ],
)
def test_a_value_no_worker_wrote_reads_as_no_state_so_the_next_read_reads_everything(
    stored: Any,
) -> None:
    """None rather than a refusal, for `ReadState.from_stored`'s reason: reading everything costs
    calls and loses nothing, and a refusal would stop the source being read until somebody edited
    a row. Delete this and a row with a naive instant or a page cursor that is not a page can stop
    a source being read at all."""
    assert ReadState.from_stored(FRESHDESK, stored) is None


def test_a_page_s_cursor_is_the_same_text_whatever_order_its_arguments_came_in() -> None:
    """The loop refusal in `BackfillCursor.advance` compares cursors as text, so one page must be
    one text. Delete this and a reading that returns its arguments in another order would pass the
    loop check while asking the same page for ever."""
    page = {"page": "2", "per_page": "100"}
    assert page_cursor(page) == page_cursor(dict(reversed(list(page.items()))))
    assert page_of(page_cursor(page)) == page
    with pytest.raises(ReadStateError):
        page_of('{"page": 2}')


# ---------------------------------------------------------------------- what moves an epoch
def test_a_page_changes_the_index_only_by_a_record_it_did_not_hold_or_a_field_that_moved() -> None:
    """M11.8.4's rule on one page: a new record or a moved field changes the index; the same fields
    confirmed do not, and an empty page changes nothing. Delete this and either every read moves
    the epoch, which drops every cached answer every quarter hour, or none does, which serves a
    cached answer after its source changed."""
    record = ProjectedRecord(
        source=FRESHDESK, entity=TICKET, source_id="1", last_seen_at=NOW, fields={"status": 2}
    )
    fields: dict[str, StoredValue] = {"status": 2, "department": "support"}
    assert changed({}, [(record, fields)])
    assert not changed({"1": dict(fields)}, [(record, fields)])
    assert changed({"1": {**fields, "status": 3}}, [(record, fields)])
    assert changed({"2": dict(fields)}, [(record, fields)])
    assert not changed({}, [])


def test_the_overlap_is_shorter_than_the_interval_any_source_is_read_for_its_changes_at() -> None:
    """`CURSOR_OVERLAP` held against the readings that use it rather than against itself: longer
    than the interval, every read of changes would re-read more than the read before it covered.
    Delete this and the overlap can grow to a day with every test green."""
    asked = [one for one in READINGS.values() if isinstance(one, ChangedSince)]
    assert asked
    assert all(timedelta() < CURSOR_OVERLAP < one.refresh_interval() for one in asked)


# ----------------------------------------------------------------- the helpdesk's own words
def test_the_helpdesk_is_asked_for_its_changes_in_the_vendor_s_form_cut_down_to_the_second() -> (
    None
):
    """Freshdesk documents `updated_since` as whole seconds in UTC with a `Z`. An instant in another
    zone is converted, a fraction of a second is cut rather than rounded up, and a naive instant is
    refused. Delete this and a read of changes could ask from an instant a few hours out, or from
    the next second and miss what changed in this one."""
    eight_hours_ahead = timezone(timedelta(hours=8))
    asked = HELPDESK.changed_since(
        TICKET, datetime(2999, 1, 1, 17, 0, 5, 999_999, tzinfo=eight_hours_ahead)
    )
    assert asked["updated_since"] == "2999-01-01T09:00:05Z"
    with pytest.raises(ConnectorContractError):
        HELPDESK.changed_since(TICKET, datetime(2999, 1, 1, 9, 0))


def test_the_helpdesk_subscribes_by_cursor_and_sweeps_for_deletions_within_the_day() -> None:
    """The subscription the worker measures reconciliation by: an updated-since cursor, polled at
    the reading's interval, which cannot see a deletion and so sweeps for one, whole, at the floor
    every subscription carries. Delete this and the reconciliation interval can be loosened past a
    day with nothing refusing it."""
    subscription = HELPDESK.subscription(TICKET)
    assert subscription.kind is ChangeSignal.UPDATED_SINCE
    assert subscription.deletion_check is DeletionCheck.ID_SWEEP
    assert subscription.notify_within == READING_INTERVAL
    assert subscription.reconcile_every == RECONCILE_EVERY == MAX_RECONCILE_INTERVAL


# ------------------------------------------------------------------- the answer cache's key
def test_an_answer_is_keyed_on_the_epoch_of_every_source_its_reader_reaches() -> None:
    """`AN_ANSWER_IS_KEYED_ON_EVERY_SOURCE_ITS_READER_REACHES`: each source the reader reaches is in
    the key with its epoch, zero where it has none, a source the reader does not reach is not, and
    the key moves when a reached source's epoch does. Delete this and the key can go back to
    carrying no epoch, and a cached answer is served after the source it read changed."""
    assert (
        "every source the reader reaches" in AN_ANSWER_IS_KEYED_ON_EVERY_SOURCE_ITS_READER_REACHES
    )
    state = SimpleNamespace(answer_store=object())
    epochs = {"xero": 3, "hubspot": 9}
    caching = caching_of(state, {}, ("xero", FRESHDESK), epochs)
    assert caching is not None
    assert dict(caching.source_epochs) == {FRESHDESK: 0, "xero": 3}

    def key(held: Mapping[str, int]) -> str:
        again = caching_of(state, {}, ("xero", FRESHDESK), held)
        assert again is not None
        return key_for("q", "0" * 32, "agent", again.policy_epoch, again.source_epochs, None)

    assert key(epochs) == key({**epochs, "hubspot": 10})
    assert key(epochs) != key({**epochs, "xero": 4})
    assert key(epochs) != key({**epochs, FRESHDESK: 1})
    assert caching_of(SimpleNamespace(), {}, ("xero",), epochs) is None


def test_the_epochs_are_read_only_where_an_answer_is_cached() -> None:
    """With no answer store nothing is read, since nothing is keyed; with one, the epochs are read
    from what the process holds; with a store and no database there is no source that changes.
    Delete this and every question on a process with no cache pays a database read for nothing."""

    class Epochs:
        def __init__(self) -> None:
            self.asked = 0

        async def epochs(self) -> Mapping[str, int]:
            self.asked += 1
            return {"xero": 2}

    held = Epochs()
    assert asyncio.run(source_epochs_of(SimpleNamespace(source_epochs=held))) == {}
    assert held.asked == 0
    stored = SimpleNamespace(answer_store=object(), source_epochs=held)
    assert asyncio.run(source_epochs_of(stored)) == {"xero": 2}
    assert asyncio.run(source_epochs_of(SimpleNamespace(answer_store=object()))) == {}
