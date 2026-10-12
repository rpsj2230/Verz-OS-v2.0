"""The vault-and-worker install check: registered, passing on a healthy reading, and failing or not
run for each way the first install's secrets path is not yet whole.

`assess` is pure, so each refusal is shown over a reading the test builds; the body is shown not run
on an install naming no vault. Nothing here opens a vault or writes a row.

Task ids: M32.7.2
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from brain.connectors.contract import HealthState
from brain.ops import acceptance_checks_vault_worker as module
from brain.ops.acceptance import REASON_CHARS, CheckFailedError, CheckNotRunError, registered
from brain.ops.acceptance_checks_vault_worker import Reading, assess
from brain.ops.connector_slots import SLOT_SCOPES, STAFF_LIST
from brain.ops.connector_sync import CONTROL_EVERY, SyncOutcome, SyncState
from brain.ops.connector_sync_store import LeaseTally
from brain.ops.vault_status import Seal
from tests.unit.test_acceptance import checks_in

MODULE = "brain.ops.acceptance_checks_vault_worker"
CHECK = "the_worker_reads_a_connected_source_with_the_key_the_vault_holds"

#: Pinned far from any wall clock: nothing here is about the present.
NOW = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)
SOURCE = next(name for name in SLOT_SCOPES if name != STAFF_LIST)


def state(**changes: Any) -> SyncState:
    fields: dict[str, Any] = {
        "connector": SOURCE,
        "finished_at": NOW - timedelta(minutes=2),
        "outcome": SyncOutcome.SYNCED,
        "health": HealthState.OK,
        "consecutive_failures": 0,
        "next_attempt_at": NOW + timedelta(minutes=30),
        "detail": "",
        "last_synced_at": NOW - timedelta(minutes=2),
    }
    fields.update(changes)
    return SyncState(**fields)


def healthy(**changes: Any) -> Reading:
    reading = Reading(
        now=NOW,
        seal=Seal.OPEN,
        connected=(SOURCE,),
        holding_a_key=frozenset({SOURCE}),
        states={SOURCE: state()},
        leases={SOURCE: LeaseTally(revoked=1)},
        runs=[(NOW - timedelta(minutes=1), NOW - timedelta(seconds=30))],
    )
    return replace(reading, **changes)


def test_the_check_is_registered_with_the_leaf_it_shows() -> None:
    """Delete this and the check can lose M32.7.2 or take another leaf, and the sweep closes or
    leaves open the wrong task with the suite green."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {CHECK: ("M32.7.2",)}
    assert checks_in(MODULE) == [CHECK]
    assert 1100 <= module.CHECK_ORDER <= 1199


def test_every_sentence_an_unfinished_install_is_told_fits_the_result() -> None:
    """Stored whole. Delete this and the sentence that says which step is awaited is cut short on
    the Install page."""
    for sentence in (
        module.NO_VAULT_HERE,
        module.NO_SOURCE_THAT_TAKES_A_KEY,
        module.NO_KEY_HAS_BEEN_WRITTEN,
        module.NO_SOURCE_HAS_BEEN_READ,
    ):
        assert len(sentence) <= REASON_CHARS


def test_a_healthy_reading_passes_and_says_which_source() -> None:
    """The positive case. Delete this and a check that refuses everything passes every
    refusal test below."""
    assert SOURCE in assess(healthy())


def test_a_vault_that_is_not_open_fails_with_the_screens_own_sentence() -> None:
    """Sealed, silent, uninitialised and absent, each its own sentence from the Secrets vault
    screen. Delete this and an install whose vault is sealed is reported as one that has not yet
    connected a source, which waits for the owner when it is the owner's server that is broken."""
    from brain.ops.vault_status import SEAL_SAYS

    for seal in (Seal.SEALED, Seal.UNREACHABLE, Seal.UNINITIALISED, Seal.ABSENT):
        with pytest.raises(CheckFailedError) as raised:
            assess(healthy(seal=seal))
        assert str(raised.value) == SEAL_SAYS[seal]


def test_an_install_that_has_not_finished_connecting_is_not_run_and_says_which_step() -> None:
    """No source that takes a key (a keyless source has no slot to hold one), a connected
    source with no key, and a key not yet read, each a different sentence and none a failure.
    Delete this and an install mid-setup is failed, or its sentence names the wrong step."""
    with pytest.raises(CheckNotRunError) as none:
        assess(healthy(connected=("a_source_with_no_slot",)))
    assert str(none.value) == module.NO_SOURCE_THAT_TAKES_A_KEY
    with pytest.raises(CheckNotRunError) as keyless:
        assess(healthy(holding_a_key=frozenset()))
    assert str(keyless.value) == module.NO_KEY_HAS_BEEN_WRITTEN
    with pytest.raises(CheckNotRunError) as unread:
        assess(healthy(states={}))
    assert str(unread.value) == module.NO_SOURCE_HAS_BEEN_READ


def test_a_read_that_failed_a_read_with_no_lease_and_a_late_read_each_fail() -> None:
    """The three ways a held key is not being used on schedule. Delete this and a worker whose
    last read of the source failed, or never asked the vault for the key, or has stopped asking, is
    reported as reading the source on schedule."""
    with pytest.raises(CheckFailedError, match="did not read it"):
        assess(healthy(states={SOURCE: state(outcome=SyncOutcome.FAILED)}))
    with pytest.raises(CheckFailedError, match="without the vault handing"):
        assess(healthy(leases={}))
    with pytest.raises(CheckFailedError, match="without the vault handing"):
        assess(healthy(leases={SOURCE: LeaseTally()}))
    late = NOW - CONTROL_EVERY * 3
    with pytest.raises(CheckFailedError, match="overdue"):
        assess(healthy(states={SOURCE: state(next_attempt_at=late)}))


def test_a_source_booked_to_be_read_soon_is_not_overdue() -> None:
    """A read booked a minute ago, which is a tick late and not a missed schedule. Delete this and
    the tolerance goes to nothing, so a worker a minute behind its own tick fails."""
    soon = NOW - timedelta(minutes=1)
    assert SOURCE in assess(healthy(states={SOURCE: state(next_attempt_at=soon)}))


def test_a_worker_nobody_has_seen_lately_fails_whatever_the_sources_say() -> None:
    """No scheduled run at all, and one an hour ago. Delete this and a worker that stopped after
    its last read still shows its source as read on schedule until the next one is overdue."""
    with pytest.raises(CheckFailedError, match="no scheduled run"):
        assess(healthy(runs=[]))
    with pytest.raises(CheckFailedError, match="no scheduled run"):
        assess(healthy(runs=[(NOW - timedelta(hours=1), NOW - timedelta(minutes=59))]))
    unfinished = [(NOW - timedelta(minutes=1), None)]
    assert SOURCE in assess(healthy(runs=unfinished))


def test_one_source_reading_well_is_enough_and_another_failing_does_not_hide_it() -> None:
    """Two sources, one failing. Delete this and the first source decides, so the install's
    healthy path is judged by whichever source sorts first."""
    other = next(name for name in SLOT_SCOPES if name not in {STAFF_LIST, SOURCE})
    reading = healthy(
        connected=(other, SOURCE),
        holding_a_key=frozenset({other, SOURCE}),
        states={
            other: state(connector=other, outcome=SyncOutcome.FAILED),
            SOURCE: state(),
        },
        leases={SOURCE: LeaseTally(revoked=2)},
    )
    assert SOURCE in assess(reading)


def test_an_install_naming_no_vault_is_not_run_before_anything_is_asked() -> None:
    """The body, with settings that name no vault. Delete this and the check opens a database
    transaction and a vault client on an install that has neither, and fails for an absence."""
    run = next(one for one in registered((MODULE,)) if one.name == CHECK).run
    harness: Any = SimpleNamespace(
        settings=SimpleNamespace(vault_address="", vault_token=""), run="abc123def456"
    )
    with pytest.raises(CheckNotRunError) as raised:
        asyncio.run(run(harness))
    assert str(raised.value) == module.NO_VAULT_HERE
