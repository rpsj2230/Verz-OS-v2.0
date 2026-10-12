"""The install acceptance check that the vault and the worker run, and the worker reads a source
with the key the console wrote there.

M32.7.2 is the first install's whole secrets path in one sentence: the worker and the vault run, a
connector key written in the console is stored in the vault, the worker reads that source on
schedule with it, and the system health screen shows it healthy. **This check writes nothing and
asks the install what it already did.** It does not connect a source, put a key in the vault or
start a read, because a check that did would be proving that a made-up key can be written rather
than that the owner's can: the rule every connector check here keeps is that nothing reaches the
vault (`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`), and the
install's vault cannot delete a slot, so a key a check wrote would outlive it.

**What it reads, and the four things that have to be true of one source at once.**

1. The vault answers and is open (`brain.ops.vault_status.report`, the screen's own reader).
2. A source the install has connected holds a key in its slot (`SlotState.HELD`, from the slot's
   metadata; no value is ever read).
3. The worker's newest read of that source came to a read and not a refusal or a failure, and the
   next one is booked and not overdue: what "on schedule" means is that the worker is still asking.
4. That read held a lease on the key: the lease tally counts the worker's attempts that were handed
   a short-lived key by the vault, which a read with no key at all would never have.

The system health screen's worker figure, when the worker was last seen, is the newest start or
finish of a scheduled run; the check reads the same rows and requires one inside three ticks of
the connector control's own cadence (`brain.ops.connector_sync.CONTROL_EVERY`). The readiness parts
the screen's strip also shows are the web process's own and live only in it, so they are not asked
here: this check does not claim the strip drew them.

**An install that has not yet done the owner's part is not failed.** No vault named, no connected
source that takes a key, a connection whose key has not been written, and a source not yet read are
each a state an install passes through before the owner has finished connecting it, and each is
`NOT_RUN` with its own literal sentence, so the leaf stays open until the install can show the
whole path and the Install page says which step it is waiting for. What is a failure is a state the
product should never reach: a sealed or silent vault, a key held with the last read failed, a read
that was never handed a lease, a source whose next read is overdue, or a worker nobody has seen.

Task ids: M32.7.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness
from brain.ops.connector_slots import SLOT_SCOPES
from brain.ops.connector_sync import CONTROL_EVERY, LONGEST_WAIT_AFTER_FAILURES, SyncOutcome
from brain.ops.vault_status import Seal, SlotState

if TYPE_CHECKING:
    from brain.ops.connector_sync import SyncState
    from brain.ops.connector_sync_store import LeaseTally

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1110

# ------------------------------------------------------------------ written-down reasons
#: Why the check writes nothing.
A_CHECK_ASKS_WHAT_THE_INSTALL_DID_AND_WRITES_NOTHING: Final = (
    "The path being shown is the owner's own key in the install's own vault, read by the worker "
    "on its own schedule. A check that connected a source, wrote a key or started a read would "
    "show that a made-up key can be written, and would leave a slot behind in a vault that "
    "cannot delete one, so it asks what the install did and writes nothing."
)

#: How long after its booked time a source's next read may be before the worker is not on schedule.
OVERDUE_AFTER: Final = CONTROL_EVERY * 2

#: How recently the worker must have been seen doing anything.
WORKER_SEEN_WITHIN: Final = CONTROL_EVERY * 3

#: How far back a lease counts: a failing source waits up to this long between reads.
LEASES_COUNTED_SINCE: Final = LONGEST_WAIT_AFTER_FAILURES

# What an install that has not finished is told, literally and each under the result's limit.
NO_VAULT_HERE: Final = (
    "this install names no secrets vault address or token, so no key written in the console can "
    "be held in one"
)
NO_SOURCE_THAT_TAKES_A_KEY: Final = (
    "no source that takes a key is connected on this install, so there is no key in the vault for "
    "the worker to read with; connect one on the Connectors screen"
)
NO_KEY_HAS_BEEN_WRITTEN: Final = (
    "a source is connected and none holds a key in the vault yet; paste its key into the masked "
    "field on the Connectors screen"
)
NO_SOURCE_HAS_BEEN_READ: Final = (
    "a source holds a key in the vault and the worker has not yet read it; the connector control "
    "runs every few minutes, so this passes once one read has finished"
)


THE_VAULT_IS_NOT_OPEN: Final = (
    "the secrets vault is not open: sealed, not answering, never initialised or not named; the "
    "Secrets vault screen says which and ops/openbao/UNSEAL.md has the steps"
)

# What a source holding a key is failing at, each its own literal: no result is built from a value.
THE_NEWEST_READ_DID_NOT_READ: Final = (
    "the worker's newest read of a source holding a key did not read it"
)
THE_KEY_WAS_NEVER_HANDED_OUT: Final = (
    "a source holding a key was read without the vault handing the key out"
)
THE_NEXT_READ_IS_OVERDUE: Final = (
    "a source holding a key is overdue its next read, so the worker is late"
)
NO_WORKER_HAS_BEEN_SEEN: Final = (
    "no scheduled run has started or finished lately, so the health screen's worker figure is "
    "stale and the worker is not running"
)


@dataclass(frozen=True)
class Reading:
    """Everything the check judges, as the install said it. Names and instants, no value."""

    now: datetime
    seal: Seal
    #: The sources with a live connection.
    connected: tuple[str, ...]
    #: The sources whose slot in the vault holds a key.
    holding_a_key: frozenset[str]
    #: Each connected source's newest attempt, by the source's name.
    states: Mapping[str, SyncState]
    #: Each source's leases handed out since `LEASES_COUNTED_SINCE`.
    leases: Mapping[str, LeaseTally]
    #: The scheduled runs' start and finish, newest first or not.
    runs: Sequence[tuple[datetime, datetime | None]]


def assess(reading: Reading) -> str:
    """The sentence a pass is, or raises `CheckNotRunError` or `CheckFailedError` with its own.

    Pure, so every refusal is tested without a vault or a database. The order is the order the
    path is walked in: the vault, the source, the key, the read, the lease, the schedule, the
    worker.
    """
    if reading.seal is not Seal.OPEN:
        raise CheckFailedError(THE_VAULT_IS_NOT_OPEN)
    keyed = tuple(name for name in reading.connected if name in SLOT_SCOPES)
    if not keyed:
        raise CheckNotRunError(NO_SOURCE_THAT_TAKES_A_KEY)
    held = tuple(name for name in keyed if name in reading.holding_a_key)
    if not held:
        raise CheckNotRunError(NO_KEY_HAS_BEEN_WRITTEN)
    read = tuple(name for name in held if name in reading.states)
    if not read:
        raise CheckNotRunError(NO_SOURCE_HAS_BEEN_READ)

    seen = max((one for pair in reading.runs for one in pair if one is not None), default=None)
    worker_is_alive = seen is not None and reading.now - seen <= WORKER_SEEN_WITHIN
    # The first source that is on schedule decides; failing that, the first one's own failing.
    failing = ""
    for name in read:
        state = reading.states[name]
        if state.outcome is not SyncOutcome.SYNCED:
            failing = failing or "read"
        elif reading.leases.get(name) is None or reading.leases[name].issued < 1:
            failing = failing or "lease"
        elif reading.now - state.next_attempt_at > OVERDUE_AFTER:
            failing = failing or "overdue"
        elif not worker_is_alive:
            raise CheckFailedError(NO_WORKER_HAS_BEEN_SEEN)
        else:
            return f"{name} was read on schedule with a key the vault handed out"
    if failing == "read":
        raise CheckFailedError(THE_NEWEST_READ_DID_NOT_READ)
    if failing == "lease":
        raise CheckFailedError(THE_KEY_WAS_NEVER_HANDED_OUT)
    raise CheckFailedError(THE_NEXT_READ_IS_OVERDUE)


# ------------------------------------------------------------------ the reading
async def _read(h: Harness) -> Reading:
    """Ask the vault, the connections, the attempts, the leases and the scheduled runs."""
    from brain.jobs_routes import last_run_of_each_control
    from brain.ops.connector_sync_store import StoredLeaseCounts, read_live, read_states
    from brain.ops.openbao import OpenBaoVault
    from brain.ops.vault_status import report

    address, token = h.settings.vault_address, h.settings.vault_token
    if not (address and token):
        raise CheckNotRunError(NO_VAULT_HERE)
    vault = await asyncio.to_thread(lambda: report(OpenBaoVault(address, token)))
    async with h.sessions() as session, session.begin():
        live = await read_live(session)
        by_id = await read_states(session)
        rows = (await session.execute(last_run_of_each_control())).all()
    connected = tuple(one.connection.connector for one in live)
    states = {one.connection.connector: by_id[one.id] for one in live if one.id in by_id}
    leases = await StoredLeaseCounts(h.sessions).tallies(h.now - LEASES_COUNTED_SINCE)
    holding = frozenset(
        name
        for name in connected
        if name in SLOT_SCOPES
        and any(
            slot.slot == SLOT_SCOPES[name].path and slot.state is SlotState.HELD
            for slot in vault.connectors
        )
    )
    return Reading(
        now=h.now,
        seal=vault.seal,
        connected=connected,
        holding_a_key=holding,
        states=states,
        leases=leases,
        runs=[(row[1], row[2]) for row in rows],
    )


@check(
    leaves=("M32.7.2",),
    sentence=(
        "The vault is open, a connected source holds a key in its slot, the worker's newest read "
        "of it came to a read with a lease the vault handed out and the next is not overdue, and "
        "a scheduled run was seen lately; an install that has not yet connected one is not run."
    ),
)
async def the_worker_reads_a_connected_source_with_the_key_the_vault_holds(h: Harness) -> None:
    assess(await _read(h))
