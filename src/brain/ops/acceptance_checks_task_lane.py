"""The install acceptance checks for the task lane's exactly-once guarantee: a keyed effect is made
once, an operation walks its six states in the install's own ledger, a lost answer is read back
rather than repeated, and every connector that can write can be read back.

**The ledger is the install's, reached through a bridge.** `brain.ops.idempotency.issue_once` is
synchronous and `PostgresOperationLedger` commits for real, which a check inside a rolled-back
transaction must never do. So the check hands `issue_once` a ledger whose three moves (`claim`,
`win`, `settle`) run the same statements against `ops.operation` through the check's own
transaction, called from a worker thread and awaited on the event loop that holds that
transaction. The door that decides whether an effect is made is the product's own; only where its
three statements run is the check's. See `A_LEDGER_ON_THE_CHECKS_TRANSACTION_FORGETS_NOTHING`.

**The effect is a counter, and says so.** Nothing leaves the process: the "effect" a check issues
adds one to a list, so the number of effects made is a number the check can count rather than a
claim about a message nobody reads. A connector's read-back is a function returning the word
`found`, which is what a source that holds the record answers. That the same door sends a real
message once is proved per channel in the unit suite; this proves the door and the install's
ledger together.

**What the check does not do.** It does not kill a process: the answer is lost by an effect that
raises after it counted itself, which is the case `AN_EFFECT_THAT_RAISED_MAY_HAVE_HAPPENED`
names and the one every real crash after a send reduces to.

Task ids: M17.3.1, M17.3.2, M17.3.3, M17.3.4, M17.3.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Final, TypeVar

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness
from brain.ops.idempotency import (
    Disposition,
    Intent,
    Issued,
    Operation,
    OperationState,
    advance,
    issue_once,
    operation_for,
)

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2000

# ------------------------------------------------------------------ written-down reasons
#: Why the check's ledger runs the product's statements on the check's own transaction.
A_LEDGER_ON_THE_CHECKS_TRANSACTION_FORGETS_NOTHING: Final = (
    "The product's ledger refuses a connection that is inside a caller's transaction, because "
    "inside one it would forget what it issued on a rollback. That is exactly what a check wants: "
    "every record is the check's, and the run rolls the whole of it back. So the three moves run "
    "as the same SQL on the check's transaction, and the door above them is the product's."
)

#: How long ago the check backdates the record it leaves in doubt, so the sweep sees it as left.
LEFT_BEHIND: Final = timedelta(minutes=10)

_T = TypeVar("_T")


class _InstallLedger:
    """`OperationLedger` over `ops.operation` on the check's transaction, called from a thread."""

    def __init__(self, h: Harness, loop: asyncio.AbstractEventLoop) -> None:
        self.h = h
        self.loop = loop

    def _run(self, work: Callable[[], Any]) -> Any:
        return asyncio.run_coroutine_threadsafe(work(), self.loop).result(timeout=60)

    def claim(self, operation: Operation) -> Operation:
        async def work() -> Operation:
            await self.h.execute(
                text(
                    "INSERT INTO ops.operation (key, connector, tool, principal_id, intent_ref,"
                    " state) VALUES (:key, :connector, :tool, :principal, :intent, 'pending')"
                    " ON CONFLICT (key) DO NOTHING"
                ).bindparams(
                    key=operation.key,
                    connector=operation.connector,
                    tool=operation.tool,
                    principal=operation.principal_id,
                    intent=operation.intent_ref,
                )
            )
            return await _read(self.h, operation.key)

        found: Operation = self._run(work)
        return found

    def win(self, key: str) -> bool:
        async def work() -> bool:
            moved = await self.h.execute(
                text(
                    "UPDATE ops.operation SET state = 'sent', updated_at = statement_timestamp()"
                    " WHERE key = :key AND state = 'pending' RETURNING key"
                ).bindparams(key=key)
            )
            return moved.first() is not None

        won: bool = self._run(work)
        return won

    def settle(self, key: str, *, frm: OperationState, to: OperationState) -> Operation:
        advance(frm, to)

        async def work() -> Operation:
            moved = await self.h.execute(
                text(
                    "UPDATE ops.operation SET state = :to, updated_at = statement_timestamp()"
                    " WHERE key = :key AND state = :frm RETURNING key"
                ).bindparams(key=key, to=to.value, frm=frm.value)
            )
            if moved.first() is None:
                raise CheckFailedError("a record moved by somebody else was settled as if unmoved")
            return await _read(self.h, key)

        settled: Operation = self._run(work)
        return settled


async def _read(h: Harness, key: str) -> Operation:
    """The record a key holds, as the ledger answers it."""
    row = (
        await h.execute(
            text(
                "SELECT key, connector, tool, principal_id, intent_ref, state"
                " FROM ops.operation WHERE key = :key"
            ).bindparams(key=key)
        )
    ).one()
    return Operation(
        key=row.key,
        connector=row.connector,
        tool=row.tool,
        principal_id=row.principal_id,
        intent_ref=row.intent_ref,
        state=OperationState(row.state),
    )


def _operation(h: Harness, n: int, connector: str) -> Operation:
    return operation_for(
        Intent(principal_id=h.principal(A, "issuer"), intent_ref=f"acceptance-{h.run}-lane-{n}"),
        connector=connector,
        tool=f"{connector}.effect",
    )


# ------------------------------------------------------------- 1. exactly once
@check(
    leaves=("M17.3.1", "M17.3.2", "M17.3.5"),
    sentence=(
        "Through the install's operation ledger the same keyed effect asked for twice is made "
        "once; an operation is walked through all six states and read back in each; and an effect "
        "whose answer was lost is left unknown, not made again, and settled by a read-back."
    ),
)
async def a_keyed_effect_is_made_once_and_a_lost_answer_is_read_back(h: Harness) -> None:
    from brain.connectors.throttle import CallOutcome

    loop = asyncio.get_running_loop()
    ledger = _InstallLedger(h, loop)
    connector = f"acceptance-{h.run}-lane"

    # 1. The same intent twice is one effect (M17.3.1).
    made: list[str] = []

    def effect(one: Operation) -> CallOutcome:
        made.append(one.key)
        return CallOutcome.OK

    keyed = _operation(h, 1, connector)
    first: Issued = await asyncio.to_thread(issue_once, ledger, keyed, effect)
    again: Issued = await asyncio.to_thread(issue_once, ledger, keyed, effect)
    if not first.issued or first.operation.state is not OperationState.SUCCEEDED:
        raise CheckFailedError("a keyed effect asked for the first time was not made and settled")
    if again.issued or len(made) != 1:
        raise CheckFailedError("a keyed effect asked for twice was made more than once")
    if again.resumption is None or again.resumption.disposition is not Disposition.DONE:
        raise CheckFailedError("the second ask for a made effect was not told it was done")

    # 2. The six states, each read back from the install's ledger (M17.3.2).
    walked = _operation(h, 2, connector)
    refused = _operation(h, 3, connector)
    seen: list[OperationState] = []
    await asyncio.to_thread(ledger.claim, walked)
    await asyncio.to_thread(ledger.claim, refused)
    seen.append((await _read(h, walked.key)).state)
    if not await asyncio.to_thread(ledger.win, walked.key):
        raise CheckFailedError("a pending record could not be moved to sent")
    seen.append((await _read(h, walked.key)).state)
    for frm, to in (
        (OperationState.SENT, OperationState.UNKNOWN),
        (OperationState.UNKNOWN, OperationState.VERIFYING),
        (OperationState.VERIFYING, OperationState.SUCCEEDED),
    ):
        await asyncio.to_thread(ledger.settle, walked.key, frm=frm, to=to)
        seen.append((await _read(h, walked.key)).state)
    await asyncio.to_thread(ledger.win, refused.key)
    await asyncio.to_thread(
        ledger.settle, refused.key, frm=OperationState.SENT, to=OperationState.FAILED
    )
    seen.append((await _read(h, refused.key)).state)
    if seen != [
        OperationState.PENDING,
        OperationState.SENT,
        OperationState.UNKNOWN,
        OperationState.VERIFYING,
        OperationState.SUCCEEDED,
        OperationState.FAILED,
    ]:
        raise CheckFailedError("an operation was not read back in each of its six states")
    moved_back = True
    try:
        await asyncio.to_thread(
            ledger.settle, walked.key, frm=OperationState.SUCCEEDED, to=OperationState.SENT
        )
    except Exception:  # the machine refusing a move out of a settled state, whatever it raises
        moved_back = False
    if moved_back:
        raise CheckFailedError("a settled operation was moved back to sent")

    # 3. The answer is lost after the effect was made (M17.3.5).
    landed: list[str] = []

    def lost(one: Operation) -> CallOutcome:
        landed.append(one.key)
        msg = "the connection dropped after the request was made"
        raise ConnectionError(msg)

    doubtful = _operation(h, 4, connector)
    try:
        await asyncio.to_thread(issue_once, ledger, doubtful, lost)
    except ConnectionError:
        pass
    else:
        raise CheckFailedError("an effect that raised was reported as made")
    if (await _read(h, doubtful.key)).state is not OperationState.UNKNOWN:
        raise CheckFailedError("an effect whose answer was lost was not left unknown")
    retried: Issued = await asyncio.to_thread(issue_once, ledger, doubtful, lost)
    if retried.issued or len(landed) != 1:
        raise CheckFailedError("an effect whose answer was lost was made a second time")
    if retried.resumption is None or retried.resumption.disposition is not Disposition.VERIFY:
        raise CheckFailedError("the ask after a lost answer was not told to read it back")
    held = await ledger_settle_verified(h, ledger, doubtful)
    if held.state is not OperationState.SUCCEEDED:
        raise CheckFailedError("a read-back that found the effect did not settle it succeeded")
    if len(landed) != 1:
        raise CheckFailedError("settling a lost answer made the effect again")


async def ledger_settle_verified(
    h: Harness, ledger: _InstallLedger, operation: Operation
) -> Operation:
    """The sweep's own read-back of one record: unknown to verifying, asked, then settled."""
    from brain.ops.crash import verify_once

    current = await asyncio.to_thread(
        ledger.settle, operation.key, frm=OperationState.UNKNOWN, to=OperationState.VERIFYING
    )
    answered = verify_once(current, lambda _: "found")
    await asyncio.to_thread(
        ledger.settle, operation.key, frm=OperationState.VERIFYING, to=answered.state
    )
    return await _read(h, operation.key)


# --------------------------------------------------------- 2. what can write can be read
@check(
    leaves=("M17.3.3", "M17.3.4"),
    sentence=(
        "Every connector this release ships states its read-back, every connector declaring a "
        "write has a way to read one back, and the verdict a reply settles never reads a refusal, "
        "a quota or an outage as the effect being absent."
    ),
)
async def every_connector_that_can_write_can_be_read_back(h: Harness) -> None:
    del h
    from brain.connectors.declaration import read_backs
    from brain.connectors.throttle import CallOutcome
    from brain.connectors.write_verification import Reading, connectors, read_back_gaps, verdict
    from brain.ops.idempotency import Verification

    discovered = connectors()
    if not discovered:
        raise CheckFailedError("no connector was found to be asked")
    gaps = read_back_gaps(discovered, read_backs())
    if gaps:
        raise CheckFailedError(
            "the connector declarations disagree with the connectors this release ships"
        )
    table = read_backs()
    writers = [name for name, writes in discovered.items() if writes]
    if any(table[name].reading is None for name in writers):
        raise CheckFailedError("a connector that declares a write has no reading to read it back")

    if verdict(Reading(outcome=CallOutcome.OK, matched=1, complete=True)) is not Verification.FOUND:
        raise CheckFailedError("a reply holding the record did not settle as found")
    if verdict(Reading(outcome=CallOutcome.OK, matched=0, complete=True)) is not (
        Verification.ABSENT
    ):
        raise CheckFailedError("a complete reply with nothing in it did not settle as absent")
    if (
        verdict(Reading(outcome=CallOutcome.OK, matched=0, complete=False))
        is not Verification.INCONCLUSIVE
    ):
        raise CheckFailedError("an unfinished look was read as the effect being absent")
    for outcome in (CallOutcome.REJECTED, CallOutcome.QUOTA, CallOutcome.UNAVAILABLE):
        if (
            verdict(Reading(outcome=outcome, matched=0, complete=False))
            is not Verification.INCONCLUSIVE
        ):
            raise CheckFailedError("a refusal, a quota or an outage was read as the effect absent")
