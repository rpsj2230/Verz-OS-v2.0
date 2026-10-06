"""Sending a change a person approved: with the grant's own key, once, and read back before done.

A connector's write is a grant of its own (`brain.connectors.declaration.WriteGrant`): off until the
install gives its key, which is kept in a slot of its own beside the read key. This module is what
happens to an approved prepared action for such a grant, and it adds no rule about who may approve
or when an action may run: `brain.gate.leash.resume` re-checks the approval, its expiry, the reach
it runs at and the leash exactly as for every other action, and this module only supplies the
execution and reads the result back. The owner's register decides the shape: every write is a
deliberate grant that runs only as an approved prepared action and is verified by reading it back
(OWN-24), a DNS change stops for a person before it is made (OWN-141), and writing is a separate
grant shown when the connector is connected (ARC-A-140).

**Without the grant's key nothing is sent, and nothing is claimed.** The key is borrowed before the
approval is resumed, and a slot holding none ends the attempt as `NOT_ALLOWED` with the grant's own
sentence, before the operation ledger is asked. So an approval taken on an install that had not yet
allowed the write can be sent later, once somebody allows it: it was never recorded as tried. See
`WITHOUT_ITS_KEY_A_WRITE_IS_NOT_TRIED`.

**Sent once, because the ledger is the leash's.** `resume` runs the execution through
`brain.ops.idempotency.issue_once`, keyed by the approval's id and the action's digest, so an
approval resumed twice finds the key already won and is handed a `Repeated`, and this module sends
nothing the second time (`ALREADY_SENT`). The ledger is the caller's: `PostgresOperationLedger` on
an install, which outlives the process. A send the source refused leaves the record UNKNOWN, and a
retry is told so rather than sending again, which is the leash's own rule.

**Reported done only when read back as approved.** After the send, the record is read again through
the connector's live lookup with the read key (`brain.ops.live_read_run.ConnectedSources.read_one`),
the reply is judged by `brain.connectors.write_verification.verdict` over the same classified
reading every connector's read-back uses, and the connector's `PreparesWrite.differs` names every
field the change set that the record does not hold. Done needs a FOUND verdict and no field named;
anything else is `FAILED`, naming the fields. Rejected: trusting the send's own reply, which is the
source's account of the request rather than of the record, and is exactly what a read-back exists
to check. See `A_WRITE_IS_DONE_ONLY_WHEN_READ_BACK_AS_APPROVED`.

**What a report tells a reader is redacted at their reach.** The record read back is kept as a typed
result, carrying the fields its connection's visibility rule tests as its index row does (`scoped`),
and `WriteReport.for_reader` hands it through `brain.core.redaction.redact`, so a reader who may not
see the record, or a field of it, is told what they would be told of a record that was never found.
The field names a report gives are the fields the change set, which the approver read on the card.

Scope: every part that touches the world is handed in (the keys, the caller, the resolver, the
clock, the ledger), so the tests drive it over recorded replies. Nothing here decides who may
approve; nothing here reads a table.

Task ids: M11.7.3, M11.8.12
"""

from __future__ import annotations

import enum
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol

from brain.connectors.contract import ConnectorContractError, FetchRequest
from brain.connectors.declaration import (
    CodeReading,
    ConnectorDeclaration,
    PageReply,
    ToolReading,
    ViewReading,
    WriteGrant,
    shipped,
)
from brain.connectors.live_read import RECORD_ID_FILTER
from brain.connectors.rest import MAX_RESPONSE_BYTES
from brain.connectors.throttle import CallOutcome, classify
from brain.connectors.transports import SourceRecord
from brain.connectors.write_verification import classified_reading, verdict
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.core.field_policy import FieldPolicy
from brain.core.redaction import redact
from brain.gate.injection import RiskAssessment
from brain.gate.leash import Action, Leash, RunOutcome, SuspendedAction, resume
from brain.ops.connectable import READING_ROLE, manifest_for
from brain.ops.connector_store import Connection
from brain.ops.connector_sync_run import (
    ConnectorKeyAbsentError,
    ConnectorKeys,
    SourceAnswer,
    SourceCaller,
    authorization,
)
from brain.ops.credentials import connector_write_slot
from brain.ops.idempotency import OperationLedger, Verification
from brain.ops.live_read_run import ConnectedSources
from brain.ops.secrets import SecretRef, SecretsUnavailableError
from brain.tools.fetch import Resolver

# ------------------------------------------------------------------ written-down reasons
#: Why a write whose key was never given is not tried, and so not recorded as tried.
WITHOUT_ITS_KEY_A_WRITE_IS_NOT_TRIED: Final = (
    "A write grant is off until the install gives its key. An approved change on an install that "
    "has not given it is not sent and not resumed: the key is asked for first, and its absence "
    "ends the attempt before the operation ledger records anything, so the approval can still be "
    "sent once somebody allows the write, rather than being remembered as a send that failed."
)

#: Why a sent change is reported done only after it is read back.
A_WRITE_IS_DONE_ONLY_WHEN_READ_BACK_AS_APPROVED: Final = (
    "The source's answer to a change is its account of the request, not of the record. So a sent "
    "change is read again with the read key, by the connector's own one-record call, and reported "
    "done only when the source found the record and every field the change set holds what was "
    "approved. A record that could not be read back, or holds something else, is reported failed, "
    "naming the fields, and never done."
)

#: Why a change is judged against every record read back under its id.
A_CHANGE_HOLDS_WHEN_ONE_RECORD_READ_BACK_HOLDS_IT: Final = (
    "Most changes are read back as the one record they changed. Some can only be read back among "
    "others named the same way, as a reply is among its ticket's conversations, because the "
    "source gives the new record's own id only in its answer to the send, which a read-back "
    "exists not to trust. So every record read back under the change's id is judged, the change "
    "holds when one of them holds exactly what was approved, and only that record is reported."
)

# What a report says, one sentence per outcome. Constant: a source's reply and a record's value
# can carry anything, and a sentence built from one would carry it to whoever reads the report.
SENT_AND_READ_BACK: Final = "Done: the change was sent and read back holding what was approved."
READ_BACK_DIFFERS: Final = (
    "Not done: the change was sent, and the record read back does not hold what was approved."
)
READ_BACK_UNKNOWN: Final = (
    "Not done: the change was sent, and the record could not be read back, so it is not reported "
    "done."
)
SOURCE_REFUSED_THE_CHANGE: Final = "Not done: the source did not accept the change."
WRITE_KEY_UNREADABLE: Final = (
    "Not sent: the key for this change could not be borrowed from the vault, so nothing was sent."
)
NOT_SENT: Final = "Not sent: this approval can no longer run as it was approved."
SENT_ALREADY: Final = "Not sent again: this approval has already run once."
MAY_HAVE_BEEN_SENT: Final = (
    "Not sent again: an earlier attempt at this approval may have reached the source, so check the "
    "record there before asking again."
)


class WriteOutcome(enum.StrEnum):
    """What sending one approved change came to. Closed."""

    #: Sent, and read back holding what was approved.
    DONE = "done"
    #: Sent and not read back as approved, or refused by the source.
    FAILED = "failed"
    #: The install has not given the grant's key, so nothing was sent or tried.
    NOT_ALLOWED = "not_allowed"
    #: The approval could not run as approved (not approved, lapsed, the reach or leash moved).
    NOT_SENT = "not_sent"
    #: This approval had already run; nothing was sent again.
    ALREADY_SENT = "already_sent"


class SourceSender(Protocol):
    """One change to a source, with its body, to the address the rule checked, never following."""

    def send(
        self,
        method: str,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        body: bytes,
        max_bytes: int,
    ) -> SourceAnswer:
        """The answer, or a timeout or a failed connection. Never raises for the network."""
        ...


class SourceWriter(SourceCaller, SourceSender, Protocol):
    """A caller that reads with `get` and sends an approved change with `send`."""


class ChangeRefusedError(ConnectorContractError):
    """The source did not accept a change it was sent. Carries the call's outcome, never a body."""

    def __init__(self, outcome: CallOutcome) -> None:
        super().__init__(f"the source answered {outcome}")
        self.outcome = outcome


@dataclass(frozen=True)
class WriteReport:
    """What sending one approved change came to, in words and in fields, and the record read back.

    `found` is the record as the read-back found it, a typed result so a reader is told only what
    their reach admits (`for_reader`). `differs` names the fields the change set that the record
    does not hold, never their values.
    """

    outcome: WriteOutcome
    told: str
    differs: tuple[str, ...] = ()
    found: TypedResult[SourceRecord] | None = None
    verification: Verification | None = None

    def for_reader(
        self, reach: EntitlementSet, policy: FieldPolicy, now: datetime
    ) -> list[dict[str, Any]]:
        """The record read back as this reader may see it. See the module docstring.

        A reader who may not see the record is handed the same empty list as a report whose record
        was never found, which is DENIED and ABSENT told alike.
        """
        if self.found is None:
            return []
        answer = redact(self.found, entitlement=reach, policy=policy, now=now)
        records: list[dict[str, Any]] = answer.payload.model_dump(mode="json")["records"]
        return records


def grant_for(
    connection: Connection,
    tool: str,
    declarations: Mapping[str, ConnectorDeclaration],
) -> tuple[ConnectorDeclaration, WriteGrant]:
    """The connection's declaration and the grant that sends `tool`, or a contract error."""
    declared = declarations.get(connection.connector)
    grant = (
        None
        if declared is None
        else next((one for one in declared.writes if tool in one.tools), None)
    )
    if declared is None or grant is None:
        msg = f"{tool!r} is not a write this connection's connector is granted"
        raise ConnectorContractError(msg)
    return declared, grant


def write_key(connector: str, grant: WriteGrant) -> SecretRef:
    """Where the grant's key is kept, read under the worker's role like every connector key."""
    return SecretRef(path=connector_write_slot(connector, grant.name).path, role=READING_ROLE)


def send_approved(
    suspension: SuspendedAction,
    *,
    connection: Connection,
    keys: ConnectorKeys,
    caller: SourceWriter,
    resolver: Resolver,
    clock: Callable[[], datetime],
    reach: EntitlementSet,
    agent_ceiling: EntitlementSet,
    policy: FieldPolicy,
    leash: Leash,
    assessment: RiskAssessment,
    trace_id: str,
    ledger: OperationLedger,
    declarations: Mapping[str, ConnectorDeclaration] | None = None,
) -> WriteReport:
    """Send one approved change with its grant's key, once, and read it back (M11.7.3).

    `reach` is the reach of the person the action runs for, resolved now, as
    `brain.gate.suspension_store.resume_stored` resolves it. See the module docstring for each
    outcome.
    """
    known = shipped() if declarations is None else declarations
    declared, grant = grant_for(connection, suspension.action.tool.name, known)
    reading = declared.reading
    # A database's views are read in a read-only session and have no call a write could be sent
    # by (M11.6.1), so a write is declared only beside a reading that makes calls.
    if reading is None or isinstance(reading, ViewReading | ToolReading | CodeReading):
        msg = f"{connection.connector} declares a write and no reading to send and read it with"
        raise ConnectorContractError(msg)
    lease = keys.lease(write_key(connection.connector, grant), now=clock())
    try:
        try:
            key = lease.key()
        except ConnectorKeyAbsentError:
            return WriteReport(outcome=WriteOutcome.NOT_ALLOWED, told=grant.not_allowed)
        except SecretsUnavailableError:
            return WriteReport(outcome=WriteOutcome.FAILED, told=WRITE_KEY_UNREADABLE)
        headers = {
            **reading.call_headers(connection.settings),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": authorization(reading.key_scheme(), key),
        }

        def execute(action: Action) -> TypedResult[SourceRecord]:
            call = grant.prepares.call_for(action, settings=connection.settings)
            checked = call.operation.prepare(call.arguments, resolver=resolver)
            answer = caller.send(
                call.operation.operation.method.upper(),
                checked.url,
                address=checked.address,
                headers=headers,
                body=json.dumps(dict(call.body)).encode("utf-8"),
                max_bytes=MAX_RESPONSE_BYTES,
            )
            outcome = classify(
                status=answer.status,
                timed_out=answer.timed_out,
                connection_failed=answer.connection_failed or answer.status is None,
            )
            if outcome is not CallOutcome.OK:
                raise ChangeRefusedError(outcome)
            return TypedResult[SourceRecord](
                records=(), source=connection.connector, fetched_at=clock().isoformat()
            )

        try:
            resumed = resume(
                suspension,
                caller=reach,
                agent_ceiling=agent_ceiling,
                policy=policy,
                leash=leash,
                assessment=assessment,
                trace_id=trace_id,
                now=clock(),
                execute=execute,
                ledger=ledger,
            )
        except ChangeRefusedError:
            return WriteReport(outcome=WriteOutcome.FAILED, told=SOURCE_REFUSED_THE_CHANGE)
    finally:
        lease.close(clock())
    if resumed.repeated is not None:
        said = (
            SENT_ALREADY if resumed.repeated.outcome is RunOutcome.HAPPENED else MAY_HAVE_BEEN_SENT
        )
        return WriteReport(outcome=WriteOutcome.ALREADY_SENT, told=said)
    if not resumed.resumed:
        return WriteReport(outcome=WriteOutcome.NOT_SENT, told=NOT_SENT)
    return read_back(
        suspension.action,
        grant,
        declared,
        connection=connection,
        keys=keys,
        caller=caller,
        resolver=resolver,
        clock=clock,
    )


def read_back(
    action: Action,
    grant: WriteGrant,
    declared: ConnectorDeclaration,
    *,
    connection: Connection,
    keys: ConnectorKeys,
    caller: SourceCaller,
    resolver: Resolver,
    clock: Callable[[], datetime],
) -> WriteReport:
    """Read a sent change back with the read key and say whether it holds what was approved.

    See `A_WRITE_IS_DONE_ONLY_WHEN_READ_BACK_AS_APPROVED`.
    """
    call = grant.prepares.call_for(action, settings=connection.settings)
    sources = ConnectedSources(
        {connection.connector: connection},
        keys=keys,
        caller=caller,
        resolver=resolver,
        clock=clock,
        declarations={connection.connector: declared},
    )
    reply = sources.read_one(
        connection,
        declared,
        FetchRequest(entity=call.entity, filters=((RECORD_ID_FILTER, call.source_id),), limit=1),
    )
    judged = verdict(classified_reading(PageReply(call=reply.outcome, rows=reply.rows)))
    if judged is not Verification.FOUND or reply.rows is None:
        return WriteReport(outcome=WriteOutcome.FAILED, told=READ_BACK_UNKNOWN, verification=judged)
    # Every record read back under the change's id is a candidate, and the change holds when one
    # of them holds it: a reply is one conversation among its ticket's. See
    # `A_CHANGE_HOLDS_WHEN_ONE_RECORD_READ_BACK_HOLDS_IT`.
    candidates = [one for one in reply.rows.records if one.id == call.source_id]
    if not candidates:
        return WriteReport(outcome=WriteOutcome.FAILED, told=READ_BACK_UNKNOWN, verification=judged)
    judged_each = [(one, grant.prepares.differs(action, one.model_dump())) for one in candidates]
    record, differs = next(
        ((one, named) for one, named in judged_each if not named), judged_each[0]
    )
    found = scoped(reply.rows.model_copy(update={"records": (record,)}), connection, call.entity)
    if differs:
        return WriteReport(
            outcome=WriteOutcome.FAILED,
            told=READ_BACK_DIFFERS,
            differs=differs,
            found=found,
            verification=judged,
        )
    return WriteReport(
        outcome=WriteOutcome.DONE, told=SENT_AND_READ_BACK, found=found, verification=judged
    )


def scoped(
    rows: TypedResult[SourceRecord], connection: Connection, entity: str
) -> TypedResult[SourceRecord]:
    """Rows read back, carrying the fields their connection's visibility rule tests.

    A source's record does not repeat the department or the account its connection names, and a
    grant scoped by them is judged against the record, so a record without them is withheld from
    everybody. The index row carries them for the same reason
    (`brain.ops.connector_sync.stored_fields`); a record read back is scoped the same way, and the
    rule's value wins over anything the source sent under the same name.
    """
    projection = manifest_for(connection.connector, connection.settings).projection_for(entity)
    if projection is None:
        return rows
    placed = {clause.field: str(clause.value) for clause in projection.visibility.clauses}
    return TypedResult[SourceRecord](
        records=tuple(
            SourceRecord.model_validate({**one.model_dump(), **placed}) for one in rows.records
        ),
        source=rows.source,
        fetched_at=rows.fetched_at,
        truncated=rows.truncated,
    )


def unsent_because(tool: str, held: Callable[[str, WriteGrant], bool | None]) -> str:
    """What an approver is told about an action of this tool that approving would not send.

    The grant's own sentence when the install has not given its key (`held` answers False), and
    nothing for a tool no grant sends, for a grant whose key is held, and when the vault could not
    say (`held` answers None): a sentence claiming the install has not allowed a write is only
    said when the vault said so.
    """
    for name, declared in shipped().items():
        for grant in declared.writes:
            if tool in grant.tools and held(name, grant) is False:
                return grant.not_allowed
    return ""
