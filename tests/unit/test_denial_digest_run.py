"""The denial digest, run: the hour's patterns from the ledger, the people to tell, the store.

`test_denial_alerts.py` holds `digest`. What is here is its caller: the statement that reads the
ledger's `deny` entries (compiled, and run for real where CI has a server), the classification of
what it returns, and a pass over a literal store, which is what the Notifications screen reads.

Task ids: M23.2.2
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.ops.denial_alert_store import AlertStore
from brain.ops.denial_digest_run import (
    NOBODY_NEW_TO_TELL,
    NOTHING_WORTH_RAISING,
    RAISED,
    SWITCHED_OFF,
    UNATTRIBUTED,
    DenialDigestError,
    denials_between,
    digest_pass,
    patterns_from,
    run_denial_digest_now,
)
from brain.ops.limits import DENIALS_WORTH_NOTICING, ENUMERATION_DISTINCT_TARGETS, DenialShape
from tests.fixtures.fake_alert_valkey import FakeAlertValkey

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
NOW = datetime(2999, 6, 15, 12, 0, tzinfo=UTC)
PRICES = "read:price_list"


def holder(principal_id: str, capability: str = PRICES) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=(Grant(capability=Capability(value=capability), scope=Scope.unrestricted()),),
    )


# ----------------------------------------------------------------------- the statement
def test_the_statement_reads_deny_entries_grouped_by_person_and_capability() -> None:
    """One pass over the ledger: refusals and different things reached for, per person and
    capability, in the window, with an unattributed entry left out in the statement.

    Delete this and the read can drift to every action, or count entries rather than targets,
    which makes persistence look like breadth."""
    compiled = denials_between(NOW, NOW).compile(dialect=DIALECT)
    sql = str(compiled)

    assert "obs.audit_entry.action = " in sql
    assert "count(DISTINCT obs.audit_entry.subject)" in sql
    assert "GROUP BY obs.audit_entry.actor_id" in sql
    assert "IS DISTINCT FROM" in sql
    assert "deny" in compiled.params.values()
    assert UNATTRIBUTED in compiled.params.values()


def test_only_a_pattern_worth_an_alert_leaves_the_classifier() -> None:
    """Below the noticing threshold nothing is raised; breadth is enumeration and persistence is
    a missing grant. A capability that does not parse is passed over rather than stopping the
    pass for everybody.

    Delete this and every mistyped client name in the company becomes an alert."""
    found = patterns_from(
        [
            ("u_quiet", PRICES, DENIALS_WORTH_NOTICING - 1, 1),
            ("u_wide", PRICES, DENIALS_WORTH_NOTICING, ENUMERATION_DISTINCT_TARGETS),
            ("u_stuck", PRICES, DENIALS_WORTH_NOTICING, 1),
            ("u_bad", "NOT A CAPABILITY", DENIALS_WORTH_NOTICING, 1),
        ]
    )

    assert [(one.subject_id, one.shape) for one in found] == [
        ("u_wide", DenialShape.ENUMERATION),
        ("u_stuck", DenialShape.ACCESS_NEEDED),
    ]
    assert all(dict(one.where) == {} for one in found)


# ----------------------------------------------------------------------------- a pass
def test_a_pass_keeps_an_alert_for_whoever_holds_what_was_refused_and_not_for_the_subject() -> None:
    """The whole path the Notifications screen reads: a pattern, the people, the store. The
    holder is told, somebody without the capability is not, and the subject never is.

    Delete this and the runner can keep alerts for everybody, or for nobody, with `digest`'s own
    tests green."""
    client = FakeAlertValkey()
    store = AlertStore(client=client)
    [pattern] = patterns_from([("u_wide", PRICES, 12, 9)])

    said = digest_pass(
        now=NOW,
        patterns=(pattern,),
        recipients=(holder("u_admin"), holder("u_wide"), holder("u_elsewhere", "read:hr")),
        alerts=store,
    )

    assert said == RAISED
    assert [one.subject_id for one in store.alerts_for("u_admin")] == ["u_wide"]
    assert store.alerts_for("u_wide") == ()
    assert store.alerts_for("u_elsewhere") == ()


def test_a_second_pass_in_the_window_tells_nobody_again() -> None:
    """The log is read from the store at the start of every pass. Delete this and the digest's
    window holds only inside one process's memory."""
    store = AlertStore(client=FakeAlertValkey())
    patterns = patterns_from([("u_wide", PRICES, 12, 9)])
    digest_pass(now=NOW, patterns=patterns, recipients=(holder("u_admin"),), alerts=store)

    again = digest_pass(now=NOW, patterns=patterns, recipients=(holder("u_admin"),), alerts=store)

    assert again == NOBODY_NEW_TO_TELL
    assert len(store.alerts_for("u_admin")) == 1


def test_what_a_pass_says_names_nobody_and_counts_nothing() -> None:
    """A run's detail is read by whoever reads control runs, who are not the people entitled to
    the alerts. Delete this and a detail reading "raised 3 alerts about u_wide" is one edit away."""
    for said in (SWITCHED_OFF, NOTHING_WORTH_RAISING, NOBODY_NEW_TO_TELL, RAISED):
        assert not re.search(r"[0-9]", said)
        assert "u_" not in said
    store = AlertStore(client=FakeAlertValkey())
    assert digest_pass(now=NOW, patterns=(), recipients=(), alerts=store) == NOTHING_WORTH_RAISING


def test_an_install_with_no_cache_refuses_the_pass_rather_than_raising_into_nothing() -> None:
    """A pass that kept alerts nowhere would record a success for telling nobody.

    Delete this and the control reads as working on every install without a cache."""
    with pytest.raises(DenialDigestError):
        run_denial_digest_now("postgresql://unused", now=NOW, valkey_url="")


# --------------------------------------------------------------------- against the ledger
@pytest.fixture
def ledger() -> Iterator[str]:
    from tests.unit.test_decision_entries import at_head

    with at_head("brain_test_m2322_denial_digest") as url:
        yield url


def test_the_statement_reads_real_deny_entries(ledger: str) -> None:
    """Run for real against `gate.record_denial`'s entries, in a transaction rolled back after:
    nine refusals of one capability across six things, and one of another.

    Delete this and the JSON path the statement reads the capability from is asserted only as
    text."""
    import psycopg

    statement = denials_between(datetime(2000, 1, 1, tzinfo=UTC), NOW).compile(dialect=DIALECT)
    with psycopg.connect(ledger) as conn, conn.transaction(force_rollback=True):
        conn.execute("SELECT set_config('brain.actor_id', 'u_wide', true)")
        conn.execute("SELECT set_config('brain.trace_id', 'trace-digest', true)")
        for n in range(9):
            conn.execute(
                "SELECT gate.record_denial(%s, %s, 'no_grant')", (f"entity:e{n % 6}", PRICES)
            )
        conn.execute("SELECT gate.record_denial('entity:hr', 'read:hr', 'no_grant')")
        rows = conn.execute(str(statement), statement.params).fetchall()

    counted = {
        (actor, capability): (denials, targets) for actor, capability, denials, targets in rows
    }
    assert counted[("u_wide", PRICES)] == (9, 6)
    assert counted[("u_wide", "read:hr")] == (1, 1)
    [pattern] = patterns_from([tuple(row) for row in rows])
    assert pattern.shape is DenialShape.ENUMERATION
