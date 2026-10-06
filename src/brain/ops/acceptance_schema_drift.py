"""The install acceptance check for a source's schema: a renamed field seen, shown, not answered.

One check, over the worker's own pieces inside the check's transaction. A helpdesk made up for the
run is connected as the Connectors route connects one and read twice by the worker's
`brain.ops.connector_sync_run.attempt`, each attempt recorded as the scheduled run records it. The
first read is the helpdesk as it was; the second is the same helpdesk calling the ticket's status
by another name, which is what a vendor's rename looks like from here.

**What is checked is the whole path the owner asked for (M11.8.7).**
- After the first read the source is healthy and nothing is lost, and a question's live read of the
  ticket reaches the source, so the check is not satisfied by a lane that refuses everything.
- After the second the read is still a read, its health is degraded, and its sentence on the
  Connectors screen (`StoredSyncStates`, the screen's own reader) names `ticket.status` and no
  value.
- The answer lane's own reader of that sentence (`brain.ops.live_read_run.lost_by_source`) hands
  `SourceRecords` the lost field, and the same live read is refused with
  `FailureReason.SHAPE_CHANGED` and no call to the source, which is what the lane turns into the
  sentence every unreadable source gets.

**No socket is opened.** The helpdesk is the sources check's recorded `_Helpdesk`, and the live
source the answer lane would read is the check's own `_Desk`, which counts its calls. What only a
real helpdesk proves is the rename itself, which no install can be asked to make.

Task ids: M11.8.7
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.connectors.contract import FetchRequest
    from brain.connectors.live_read import LiveReply
    from brain.core.envelope import IdentityMode
    from brain.ops.connector_store import Connection
    from brain.ops.connector_sync import Attempt, SyncState
    from brain.ops.connector_sync_store import LiveConnection

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 302

A, _ = RESERVED_DEPARTMENTS


@dataclass
class _Desk:
    """`LiveSources` with the check's helpdesk read live, its one source counting its calls."""

    subject: str
    calls: list[FetchRequest] = field(default_factory=list)

    async def connected(self) -> _Desk:
        return self

    def reads(self, connector: str, entity: str) -> IdentityMode | None:
        from brain.connectors.freshdesk import FRESHDESK, TICKET
        from brain.core.envelope import IdentityMode

        return IdentityMode.SERVICE if (connector, entity) == (FRESHDESK, TICKET) else None

    def source_for(self, connector: str, *, mode: IdentityMode, asker: str) -> Any:
        del connector, mode, asker
        return self

    async def __call__(self, request: FetchRequest) -> LiveReply:
        from brain.connectors.live_read import LiveReply
        from brain.connectors.throttle import CallOutcome
        from brain.connectors.transports import SourceRecord
        from brain.core.envelope import TypedResult

        self.calls.append(request)
        (record_id,) = [value for key, value in request.filters if key == "id"]
        found = SourceRecord.model_validate(
            {"entity": "ticket", "id": record_id, "subject": self.subject}
        )
        return LiveReply(
            CallOutcome.OK, rows=TypedResult[SourceRecord](records=(found,), source="freshdesk")
        )


async def _read(
    h: Harness,
    live: LiveConnection,
    connection: Connection,
    caller: Any,
    *,
    at: datetime,
    previous: SyncState | None,
) -> Attempt:
    """One scheduled read of the check's helpdesk, recorded as the worker's run records it."""
    from brain.ops.acceptance_checks_connectors import _Keys, _no_wait, _Resolver
    from brain.ops.connector_sync import plan_for
    from brain.ops.connector_sync_run import attempt
    from brain.ops.connector_sync_store import attempt_row

    plan = plan_for(connection, last=previous, now=at)
    if plan.refused or not plan.due:
        raise CheckFailedError("the worker's plan would not read the check's helpdesk when due")
    done = await attempt(
        live,
        plan,
        previous=previous,
        sessions=h.sessions,
        keys=_Keys(),
        caller=caller,
        resolver=_Resolver(),
        clock=lambda: at,
        sleep=_no_wait,
    )
    await h.execute(attempt_row(live.id, done))
    return done


@check(
    leaves=("M11.8.7",),
    sentence=(
        "A helpdesk made up for the check, read as it was and then read again calling the "
        "ticket's status by another name: the second read is degraded on the source's health, "
        "names ticket.status and no value, and a question's live read of the ticket is refused "
        "as a source that could not be read, where after the first it reached the source."
    ),
)
async def a_field_the_source_renamed_is_seen_shown_and_not_answered(h: Harness) -> None:
    from functools import partial

    from brain.connectors import freshdesk
    from brain.connectors.contract import HealthState
    from brain.connectors.federation import FailureReason
    from brain.core.envelope import TypedResult
    from brain.knowledge.rows import RowRecord
    from brain.ops.acceptance_checks_connectors import _nothing_kept
    from brain.ops.acceptance_checks_sources import HELPDESK, _connection, _Helpdesk
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.connector_sync import fields_lost_detail
    from brain.ops.connector_sync_store import StoredSyncStates, read_live, read_states
    from brain.ops.live_read_run import lost_by_source
    from brain.ops.live_records import FIELD_LOST_AT_THE_SOURCE, SourceRecords

    if (await h.execute(live(freshdesk.FRESHDESK))).scalar_one_or_none() is not None:
        raise CheckNotRunError(
            "this install has Freshdesk connected already, so the check does not connect a "
            "helpdesk of its own beside it"
        )
    await h.found_departments()
    subject = h.word()
    ticket = {
        "id": 900_000 + uuid.uuid4().int % 99_999,
        "subject": subject,
        "status": 2,
        "priority": 1,
        "company_id": 1,
        "requester_id": 1,
        "group_id": 1,
        "created_at": "2019-03-01T10:00:00Z",
        "updated_at": "2019-03-02T10:00:00Z",
        "due_by": "2019-03-08T10:00:00Z",
    }
    connection = _connection(
        h,
        freshdesk.FRESHDESK,
        {freshdesk.DOMAIN_SETTING: HELPDESK, freshdesk.DEPARTMENT_SETTING: A},
    )
    await StoredConnections(h.sessions).connect(
        connector=connection.connector,
        settings=connection.settings,
        digest=connection.digest,
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=_nothing_kept,
    )
    async with h.sessions() as session:
        [one] = [
            each for each in await read_live(session) if each.connection.connector == "freshdesk"
        ]

    # The first read, of the helpdesk as it was.
    first = await _read(
        h, one, connection, _Helpdesk(ticket), at=h.now - timedelta(hours=1), previous=None
    )
    states = StoredSyncStates(h.sessions)
    desk = _Desk(subject=subject)
    records = SourceRecords(
        connected=desk.connected, clock=lambda: h.now, lost=partial(lost_by_source, states)
    )
    asked = TypedResult[RowRecord](
        records=(RowRecord.model_validate({"entity": "ticket", "id": str(ticket["id"])}),),
        source=freshdesk.FRESHDESK,
    )
    clean = (await states.states()).get(freshdesk.FRESHDESK)
    if first.health is not HealthState.OK or clean is None or await lost_by_source(states):
        raise CheckFailedError("a read of the helpdesk as it was did not leave it healthy")
    before = await records.refresh(
        asked, source=freshdesk.FRESHDESK, entity="ticket", asker=h.actor
    )
    if before is None or before.result is None or len(desk.calls) != 1:
        raise CheckFailedError("a question's live read did not reach a source with nothing lost")

    # The second read, of the helpdesk calling the status by another name.
    renamed = {("state" if key == "status" else key): value for key, value in ticket.items()}
    async with h.sessions() as session:
        previous = (await read_states(session)).get(one.id)
    second = await _read(h, one, connection, _Helpdesk(renamed), at=h.now, previous=previous)
    shown = (await states.states()).get(freshdesk.FRESHDESK)
    said = fields_lost_detail(("ticket.status",))
    if (
        second.health is not HealthState.DEGRADED
        or shown is None
        or (shown.health, shown.detail, shown.synced_detail) != (HealthState.DEGRADED, said, said)
    ):
        raise CheckFailedError("a renamed field was not shown on the source's health by name")
    if str(ticket["status"]) in shown.detail:
        raise CheckFailedError("the source's health quoted a value from its records")
    after = await records.refresh(asked, source=freshdesk.FRESHDESK, entity="ticket", asker=h.actor)
    if (
        after is None
        or after.result is not None
        or after.partial.trace_lines()
        != (f"freshdesk: {FailureReason.SHAPE_CHANGED} ({FIELD_LOST_AT_THE_SOURCE})",)
        or len(desk.calls) != 1
    ):
        raise CheckFailedError("a question over a source that lost a field was answered from it")
