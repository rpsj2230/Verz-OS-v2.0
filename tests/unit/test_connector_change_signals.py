"""The worker's run of a connected source, read after read: what it asks, where it carries on,
what it retires, and when its source's epoch moves.

`tests/unit/test_connector_read_state.py` holds the decisions without a database. This drives the
worker's own run, `brain.ops.connector_sync_run.sync_on`, over connections written by the store the
Connectors route writes with and a PostgreSQL database of the test's own, reading the state each run
left in `ops.connector_sync` before the next, as the worker does. It reuses the stand-ins of
`tests/unit/test_connector_sync_run.py`: the key is a sentinel, the call is a replay, the address is
the one a stand-in resolver hands out, and the helpdesk answers in the bare array Freshdesk's list
documents. Nothing here calls a source.

Task ids: M11.4.6, M11.4.8, M11.8.4, M11.8.11
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import pytest

import brain.ops.connector_sync_run as sync_run
from brain.connectors import freshdesk
from brain.connectors.freshdesk import EVERY_TICKET_SINCE, UPDATED_SINCE_FORMAT, FreshdeskReading
from brain.ops.connector_sync import (
    CURSOR_OVERLAP,
    PROBE_ANSWERED,
    READ_BUT_CUT_SHORT,
    READ_TO_THE_END,
    READINGS,
    SHAPE_DISAGREED,
    SOURCE_ALLOWANCE_REFUSED,
    ReadState,
    after_probe,
)
from brain.ops.connector_sync_run import SourceAnswer
from brain.ops.connector_sync_store import StoredSourceEpochs, StoredSyncStates, attempt_row
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_connector_sync_run import (
    ENTITLED,
    INVOICE_ID,
    NO_CONTACTS,
    NOW,
    Replay,
    a_database,
    answer_for,
    projected,
    read_as,
    sync,
    through,
)
from tests.unit.test_connector_sync_run import connect as connect_ledger
from tests.unit.test_freshdesk_sync import connect as connect_helpdesk

#: Past a helpdesk's reading interval, so the next run is due.
LATER: Final = freshdesk.READING_INTERVAL + timedelta(minutes=1)

#: Xero's invoices endpoint answering with none, in its own envelope.
NO_INVOICES: Final = SourceAnswer(status=200, headers={}, body=b'{"Invoices": []}')


def ticket(number: int, *, status: int = 2) -> dict[str, Any]:
    """One ticket as Freshdesk's list writes it."""
    return {
        "id": 70_000 + number,
        "subject": f"Ticket {number}",
        "status": status,
        "priority": 1,
        "created_at": "2019-03-06T09:00:00Z",
        "updated_at": "2019-03-06T09:00:00Z",
    }


def listed(tickets: Sequence[Mapping[str, Any]], **headers: str) -> SourceAnswer:
    """One page of Freshdesk's ticket list: the array itself, with these headers."""
    return SourceAnswer(status=200, headers=headers, body=json.dumps(list(tickets)).encode())


def asked(caller: Replay) -> list[dict[str, str]]:
    """Each call's query, one value to a name."""
    return [
        {name: values[-1] for name, values in parse_qs(urlsplit(one.url).query).items()}
        for one in caller.calls
    ]


def state_of(url: str, name: str) -> ReadState | None:
    """Where reading the source stood, as the worker reads it before its next run."""
    states = through(url, lambda sessions: StoredSyncStates(sessions).states())
    one = states.get(name)
    return None if one is None else one.read_state


def epochs(url: str) -> Mapping[str, int]:
    """Every source's epoch, as the answer path reads it."""
    return through(url, lambda sessions: StoredSourceEpochs(sessions).epochs())


def tickets_in(url: str) -> dict[str, bool]:
    """Each kept ticket row's id and whether it is live, retired ones included."""
    rows = sql(
        url,
        "SELECT source_id, deleted_at IS NULL FROM proj.record WHERE source = 'freshdesk'"
        " ORDER BY source_id, deleted_at NULLS LAST",
    )
    return {str(one): bool(live) for one, live in rows}


def outcomes(url: str) -> list[tuple[str, str]]:
    return [
        (str(a), str(b))
        for a, b in sql(url, "SELECT outcome, detail FROM ops.connector_sync ORDER BY finished_at")
    ]


# ------------------------------------------------------------- only what changed (M11.4.6)
@pytest.mark.needs_db
def test_a_helpdesk_is_read_from_the_beginning_then_only_for_what_changed_since_that_read() -> None:
    """**M11.4.6 in the worker.** A new connection's first run asks from 2000; the next, planned
    from the state the first left in `ops.connector_sync`, asks only for tickets updated since the
    first began, less the overlap, and a ticket it does not return is left live, because a read of
    changes cannot see a deletion. Delete this and the worker can go back to reading every ticket
    on every run, or a read of changes can retire everything it did not mention."""
    with a_database("brain_change_signals_cursor") as url:
        connect_helpdesk(url)
        first = Replay([listed([ticket(1), ticket(2)])])
        sync(url, first)
        cursor = state_of(url, freshdesk.FRESHDESK)
        second = Replay([listed([ticket(2, status=3)])])
        sync(url, second, at=NOW + LATER)
        moved = state_of(url, freshdesk.FRESHDESK)
        held = tickets_in(url)

    assert [one["updated_since"] for one in asked(first)] == [EVERY_TICKET_SINCE]
    assert cursor is not None and cursor.changed_since is not None and cursor.walking is None
    assert cursor.reconciled_at == cursor.changed_since
    since = (cursor.changed_since - CURSOR_OVERLAP).strftime(UPDATED_SINCE_FORMAT)
    assert [one["updated_since"] for one in asked(second)] == [since]
    assert moved is not None and moved.changed_since is not None
    assert moved.changed_since > cursor.changed_since
    assert moved.reconciled_at == cursor.reconciled_at
    assert held == {"70001": True, "70002": True}


@pytest.mark.needs_db
def test_a_test_of_the_connection_between_two_runs_does_not_start_the_read_again() -> None:
    """A test a person asks for is an attempt row with no read state, and it is the newest. The next
    run still reads the state the last read left, so it asks for changes. Delete this and pressing
    Test connection makes the next run read every ticket again."""
    with a_database("brain_change_signals_probed") as url:
        connect_helpdesk(url)
        sync(url, Replay([listed([ticket(1)])]))
        (connection,) = sql(url, "SELECT id FROM ops.connector_connection")
        probed = after_probe(
            connector=freshdesk.FRESHDESK,
            started_at=NOW + timedelta(minutes=2),
            finished_at=NOW + timedelta(minutes=2),
            detail=PROBE_ANSWERED,
            interval=freshdesk.READING_INTERVAL,
            previous=None,
        )

        async def probe(sessions: Any) -> None:
            async with sessions() as session, session.begin():
                await session.execute(attempt_row(connection[0], probed))

        through(url, probe)
        second = Replay([listed([ticket(1)])])
        sync(url, second, at=NOW + LATER)

    assert [one["updated_since"] for one in asked(second)] != [EVERY_TICKET_SINCE]


# ------------------------------------------ owed a reconciliation, and retiring (M11.8.11)
@pytest.mark.needs_db
def test_a_helpdesk_owed_its_reconciliation_is_read_whole_and_a_ticket_it_lost_is_retired() -> None:
    """A day after the last whole read the helpdesk is read whole again, and the ticket that read no
    longer returns is retired while the one it returned stays live; the retirement moves the epoch.
    Delete this and a ticket deleted in the helpdesk is counted and answered from for ever."""
    with a_database("brain_change_signals_reconciled") as url:
        connect_helpdesk(url)
        sync(url, Replay([listed([ticket(1), ticket(2)])]))
        before = epochs(url)
        whole = Replay([listed([ticket(1)])])
        sync(url, whole, at=NOW + freshdesk.RECONCILE_EVERY + LATER)
        held = tickets_in(url)
        after = epochs(url)

    assert [one["updated_since"] for one in asked(whole)] == [EVERY_TICKET_SINCE]
    assert held == {"70001": True, "70002": False}
    assert after[freshdesk.FRESHDESK] == before[freshdesk.FRESHDESK] + 1


@pytest.mark.needs_db
def test_a_ledger_read_whole_retires_the_invoice_it_no_longer_returns_and_hands_it_to_nobody() -> (
    None
):
    """**M11.8.11 in the worker.** Every Xero read is whole, so the run after the invoice stopped
    being listed retires its row, stamped between the run's start and now, and the reader who was
    handed it is handed nothing. Delete this and a deleted invoice is answered from for ever."""
    with a_database("brain_change_signals_retired") as url:
        connect_ledger(url)
        sync(url, Replay([answer_for("XERO-200-invoices"), NO_CONTACTS]))
        handed = read_as(url, ENTITLED)
        before = epochs(url)
        (started,) = sql(url, "SELECT clock_timestamp()")
        sync(url, Replay([NO_INVOICES, NO_CONTACTS]), at=NOW + timedelta(days=2))
        (finished,) = sql(url, "SELECT clock_timestamp()")
        rows = projected(url)
        after = read_as(url, ENTITLED)
        moved = epochs(url)

    assert [one["id"] for one in handed["records"]] == [INVOICE_ID]
    ((_, _, source_id, _, _, deleted_at),) = rows
    assert source_id == INVOICE_ID
    assert deleted_at is not None and started[0] <= deleted_at <= finished[0]
    assert after["records"] == []
    assert moved["xero"] == before["xero"] + 1


# ------------------------------------------------- carried on, not begun again (M11.4.8)
@pytest.mark.needs_db
def test_a_read_cut_short_by_the_page_cap_carries_on_and_retires_nothing_until_it_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**M11.4.8 at the page cap.** With a cap of one page, a whole read of a helpdesk holding a
    full page and more stops after the first, says so, and retires nothing, since it did not see
    everything; the next run asks page two, with the same `updated_since`, reads to the end, and
    only then retires the ticket neither page held. Delete this and a helpdesk larger than one run's
    pages is read from page one for ever and never reaches its end."""
    monkeypatch.setattr(sync_run, "MAX_PAGES_PER_ENTITY", 1)
    full = [ticket(n) for n in range(100, 200)]
    with a_database("brain_change_signals_capped") as url:
        connect_helpdesk(url)
        sql(
            url,
            "INSERT INTO proj.record (source, entity, source_id, fields, last_seen_at)"
            " VALUES ('freshdesk', 'ticket', '1', '{}'::jsonb, %s)",
            NOW - timedelta(days=30),
        )
        first = Replay([listed(full)])
        sync(url, first)
        stopped = tickets_in(url)
        second = Replay([listed([ticket(1)])])
        sync(url, second, at=NOW + LATER)
        ended = tickets_in(url)
        said = outcomes(url)

    assert [(one["page"], one["updated_since"]) for one in asked(first)] == [
        ("1", EVERY_TICKET_SINCE)
    ]
    assert [(one["page"], one["updated_since"]) for one in asked(second)] == [
        ("2", EVERY_TICKET_SINCE)
    ]
    assert said == [("synced", READ_BUT_CUT_SHORT), ("synced", READ_TO_THE_END)]
    assert stopped["1"] is True
    assert ended["1"] is False
    assert all(ended[str(one["id"])] for one in [*full, ticket(1)])


@pytest.mark.needs_db
def test_a_read_the_source_refused_part_way_asks_the_refused_page_next_and_not_the_first() -> None:
    """**M11.4.8 at the source's ceiling.** The helpdesk answers page one and refuses page two for
    volume; the run keeps page one and waits, and the next run asks page two first. Delete this and
    a read refused part way spends its first pages again on every attempt."""
    refused = SourceAnswer(status=429, headers={"retry-after": "60"}, body=b"{}")
    with a_database("brain_change_signals_refused") as url:
        connect_helpdesk(url)
        first = Replay([listed([ticket(n) for n in range(100)]), refused])
        sync(url, first)
        second = Replay([listed([ticket(100)])])
        sync(url, second, at=NOW + LATER)
        said = outcomes(url)

    assert [one["page"] for one in asked(first)] == ["1", "2"]
    assert [one["page"] for one in asked(second)] == ["2"]
    assert said == [("quota", SOURCE_ALLOWANCE_REFUSED), ("synced", READ_TO_THE_END)]


class Looping(FreshdeskReading):
    """A reading whose every full page names itself as the page after it."""

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        following = super().next_page(entity, asked, body, returned)
        return None if following is None else asked


@pytest.mark.needs_db
def test_a_reading_that_names_the_page_it_just_read_as_the_next_is_stopped_at_once() -> None:
    """`BackfillCursor.advance`'s loop refusal, reached from the worker: the second time a page
    names itself the run fails in the shape sentence, having asked twice rather than fifty. Delete
    this and a reading that loops spends a run's whole page allowance on one page every run."""
    readings = {**READINGS, freshdesk.FRESHDESK: Looping()}
    with a_database("brain_change_signals_looping") as url:
        connect_helpdesk(url)
        caller = Replay([listed([ticket(n) for n in range(100)])])
        sync(url, caller, readings=readings)
        said = outcomes(url)

    assert [one["page"] for one in asked(caller)] == ["1", "1"]
    assert said == [("failed", SHAPE_DISAGREED)]


# ------------------------------------------------------------------- the epoch (M11.8.4)
@pytest.mark.needs_db
def test_a_run_that_changes_the_index_moves_its_epoch_and_one_that_confirms_it_does_not() -> None:
    """**M11.8.4 in the worker.** The first run writes two tickets and advances the helpdesk's epoch
    from nothing to one; a run returning the same two leaves it; a run changing one ticket's status
    advances it. The ledger's epoch is not touched by any of it. Delete this and the answer cache's
    key either never moves or moves on every read."""
    with a_database("brain_change_signals_epoch") as url:
        connect_helpdesk(url)
        seen = [dict(epochs(url))]
        for at, tickets in (
            (NOW, [ticket(1), ticket(2)]),
            (NOW + LATER, [ticket(1), ticket(2)]),
            (NOW + 2 * LATER, [ticket(1, status=4), ticket(2)]),
        ):
            sync(url, Replay([listed(tickets)]), at=at)
            seen.append(dict(epochs(url)))

    assert seen == [{}, {"freshdesk": 1}, {"freshdesk": 1}, {"freshdesk": 2}]
