"""The application's live read of one record, over Xero's recorded replies and a stand-in vault.

The replies are the documented recordings in `tests/fixtures/cassettes/xero.py`, so the rows come
out of Xero's own `interpret` exactly as a scheduled page's would, and the recorded amount carries a
canary: finding it in the reply is the proof that a live read brings back the value the index never
keeps. Nothing here contacts a vendor or a vault.

Task ids: M11.9.2, M11.2.5, M11.5.1
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Final
from urllib.parse import parse_qs, urlsplit

import pytest
import structlog

from brain.connectors import xero
from brain.connectors.contract import FetchRequest
from brain.connectors.live_read import LiveReply
from brain.connectors.manifest import manifest_digest
from brain.connectors.throttle import CallOutcome
from brain.core.envelope import IdentityMode
from brain.ops.connectable import manifest_for
from brain.ops.connector_store import Connection
from brain.ops.connector_sync_run import SourceAnswer
from brain.ops.live_read_run import (
    A_QUESTION_BORROWS_A_KEY_FOR_ONE_READ,
    DECLARATION_CHANGED,
    ConnectedSources,
    live_records_for,
)
from tests.unit.test_connector_sync_run import (
    INVOICE_ID,
    KEY,
    MONEY_CANARY,
    TENANT,
    Keys,
    NoKeys,
    Replay,
    Resolver,
    answer_for,
)

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)

ONE_INVOICE: Final = FetchRequest(entity="invoice", filters=(("id", INVOICE_ID),), limit=1)


def connection(name: str = "xero", *, digest: str | None = None) -> Connection:
    settings = {"tenant_id": TENANT}
    return Connection(
        connector=name,
        settings=settings,
        digest=digest if digest is not None else manifest_digest(manifest_for(name, settings)),
        connected_by="u_admin",
        connected_at=NOW,
    )


def sources(
    *connected: Connection, keys: Keys | NoKeys | None = None, caller: Replay | None = None
) -> tuple[ConnectedSources, Keys | NoKeys, Replay]:
    held = keys if keys is not None else Keys()
    replay = caller if caller is not None else Replay([answer_for("XERO-200-invoices")])
    return (
        ConnectedSources(
            {one.connector: one for one in connected},
            keys=held,
            caller=replay,
            resolver=Resolver(),
            clock=lambda: NOW,
        ),
        held,
        replay,
    )


def fetch(found: ConnectedSources, request: FetchRequest = ONE_INVOICE) -> LiveReply:
    source = found.source_for("xero", mode=IdentityMode.SERVICE, asker="p_priya")
    assert source is not None

    async def once() -> LiveReply:
        return await source(request)

    return asyncio.run(once())


def test_a_connected_record_is_read_live_under_a_key_borrowed_for_that_one_read() -> None:
    """The positive case, end to end over Xero's recorded reply: one GET narrowed by Xero's `where`
    filter to the invoice the index row named, the key in the one header and given back when the
    read ended, and the reply read by Xero's own `interpret` into a row with the recorded amount,
    which the index never holds.

    Delete this and the live read can quietly read a whole page, keep the key past the read, or
    answer from something other than the source's reply, with every refusal below still green."""
    found, keys, caller = sources(connection())

    reply = fetch(found)

    assert found.reads("xero", "invoice") is IdentityMode.SERVICE
    assert reply.outcome is CallOutcome.OK
    assert reply.rows is not None
    (row,) = reply.rows.records
    assert (row.id, row.model_dump()["amount_due"]) == (INVOICE_ID, MONEY_CANARY)
    (asked,) = caller.calls
    assert parse_qs(urlsplit(asked.url).query)["where"] == [f'InvoiceID==Guid("{INVOICE_ID}")']
    assert asked.headers["Authorization"] == f"Bearer {KEY}"
    assert asked.headers[xero.TENANT_HEADER] == TENANT
    assert isinstance(keys, Keys)
    assert [lease.closed for lease in keys.leases] == [[NOW]]
    assert "one read" in A_QUESTION_BORROWS_A_KEY_FOR_ONE_READ


def test_only_a_connected_source_with_a_live_lookup_is_read_live_and_only_its_entities() -> None:
    """Connected and declaring a live lookup for that entity, or not read live at all.

    Delete this and a source nobody connected, or an entity its connector never said how to read,
    is asked for at question time and fails in front of the asker."""
    found, _, _ = sources(connection())
    assert found.reads("xero", "contact") is IdentityMode.SERVICE
    assert found.reads("xero", "payment") is None
    assert found.reads("freshdesk", "ticket") is None

    unconnected, _, _ = sources()
    assert unconnected.reads("xero", "invoice") is None
    assert unconnected.source_for("xero", mode=IdentityMode.SERVICE, asker="p_priya") is None


def test_a_delegated_read_is_given_no_source_here_even_for_a_connected_one() -> None:
    """This process holds no person's own credential for any source, so a read declared as the
    requester's gets nothing, rather than the connection's key (M11.2.5).

    Delete this and a read meant to run under the asker's own credentials runs under the service's,
    dropping the source's own check on what that person may see."""
    found, keys, caller = sources(connection())

    assert found.source_for("xero", mode=IdentityMode.DELEGATED, asker="p_priya") is None
    assert found.source_for("xero", mode=IdentityMode.SERVICE, asker="p_priya") is not None
    assert (keys.asked if isinstance(keys, Keys) else None, caller.calls) == ([], [])


def test_a_read_under_a_declaration_nobody_agreed_to_is_refused_before_a_key_is_borrowed() -> None:
    """The manifest a live read runs under is the one agreed to at connect, as for a scheduled read.

    Delete this and a release that changed what a connector declares is read by every question
    before anybody has accepted the change."""
    found, keys, caller = sources(connection(digest="0" * 64))

    with structlog.testing.capture_logs() as logged:
        reply = fetch(found)

    assert reply.outcome is CallOutcome.REJECTED
    assert isinstance(keys, Keys)
    assert (keys.asked, caller.calls) == ([], [])
    assert [one["why"] for one in logged if one["event"] == "live_read.refused"] == [
        DECLARATION_CHANGED
    ]


def test_an_id_that_could_change_xeros_query_is_refused_and_nothing_is_called() -> None:
    """The id is laid into Xero's own query language, so one carrying a quote is refused rather
    than escaped, the call is never made and the borrowed key is still given back.

    Delete this and an id from the index becomes a way to widen a query against the client's
    ledger."""
    found, keys, caller = sources(connection())
    hostile = FetchRequest(entity="invoice", filters=(("id", 'x")||1==1||("'),), limit=1)

    reply = fetch(found, hostile)

    assert reply.outcome is CallOutcome.REJECTED
    assert caller.calls == []
    assert isinstance(keys, Keys)
    assert [lease.closed for lease in keys.leases] == [[NOW]]
    with pytest.raises(xero.XeroError):
        xero.XeroLiveLookup().arguments_for("invoice", 'x"')
    assert xero.XeroLiveLookup().arguments_for("contact", "c-0447") == {
        "where": 'ContactID==Guid("c-0447")'
    }


def test_a_failed_call_gives_the_key_back_and_says_what_the_source_said() -> None:
    """A source that is down is unavailable, a quota refusal carries the wait the source stated,
    and the key is given back either way.

    Delete this and a failing source keeps a run token alive until its TTL on every question."""
    down = Replay([SourceAnswer(status=503, headers={}, body=b"")])
    found, keys, _ = sources(connection(), caller=down)
    assert fetch(found).outcome is CallOutcome.UNAVAILABLE

    busy = Replay([answer_for("XERO-429")])
    refused, _, _ = sources(connection(), caller=busy)
    reply = fetch(refused)
    assert reply.outcome is CallOutcome.QUOTA
    assert reply.retry_after_seconds == xero.retry_after(answer_for("XERO-429").headers or {})
    assert isinstance(keys, Keys)
    assert [lease.closed for lease in keys.leases] == [[NOW]]


def test_a_key_that_cannot_be_borrowed_is_a_refusal_and_not_the_sources_ill_health() -> None:
    """No key is this install's to fix, not the source being down, so it is a rejection, which the
    breaker ignores, and no call is made.

    Delete this and a missing key opens the source's breaker, reporting a healthy source as down."""
    found, _, caller = sources(connection(), keys=NoKeys())

    assert fetch(found).outcome is CallOutcome.REJECTED
    assert caller.calls == []


def test_a_process_with_no_database_reads_nothing_live() -> None:
    """With no connection table there is nothing to say what is connected, so the lane answers
    from what it has.

    Delete this and a process with no database fails every fast-path question on a connection read
    it cannot make."""
    assert live_records_for(None, None) is None


# ------------------------------------------------------------- a field the source lost (M11.8.7)
def test_the_lane_is_told_what_each_source_s_newest_read_lost_even_after_a_failed_attempt() -> None:
    """The answer lane this process builds reads lost fields through `lost_by_source` over the
    install's stored sync states, and that reads each source's newest read rather than its newest
    attempt: Xero's newest read lost the invoice's status and a failed attempt came after, Freshdesk
    was read to the end. Delete this and the lane can be built with nothing telling it what was
    lost, or forget a lost field the moment a source has one bad minute."""
    import asyncio
    from datetime import UTC, datetime
    from functools import partial

    from brain.connectors.contract import HealthState
    from brain.ops.connector_sync import (
        READ_TO_THE_END,
        SOURCE_UNREACHABLE,
        SyncOutcome,
        SyncState,
        fields_lost_detail,
    )
    from brain.ops.connector_sync_store import StoredSyncStates
    from brain.ops.live_read_run import live_records_for, lost_by_source

    built = live_records_for(object(), None)  # type: ignore[arg-type]
    assert built is not None
    assert isinstance(built.lost, partial)
    assert built.lost.func is lost_by_source
    assert isinstance(built.lost.args[0], StoredSyncStates)

    at = datetime(2999, 1, 1, tzinfo=UTC)
    lost = fields_lost_detail(("invoice.status",))

    def state(name: str, detail: str, synced: str) -> SyncState:
        return SyncState(
            connector=name,
            finished_at=at,
            outcome=SyncOutcome.FAILED if detail != synced else SyncOutcome.SYNCED,
            health=HealthState.DEGRADED,
            consecutive_failures=0,
            next_attempt_at=at,
            detail=detail,
            last_synced_at=at,
            synced_detail=synced,
        )

    class States:
        async def states(self) -> dict[str, SyncState]:
            return {
                "xero": state("xero", SOURCE_UNREACHABLE, lost),
                "freshdesk": state("freshdesk", READ_TO_THE_END, READ_TO_THE_END),
            }

    assert asyncio.run(lost_by_source(States())) == {"xero": frozenset({"invoice.status"})}
