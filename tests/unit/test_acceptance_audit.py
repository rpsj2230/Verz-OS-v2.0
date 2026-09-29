"""The install acceptance check for audit and tracing, run as the worker runs it.

The check ends as not run on every install while a browser session writes no ledger entry and there
is no trace store, so its sentence is the proof that every earlier step held: a failing step ends it
as failed first. So the database half runs it against PostgreSQL at head and expects that sentence
exactly, then removes the one trigger a merge is recorded by and expects a failure, which is the
check failing for the reason it exists.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.5.1, M24.3.4
"""

from __future__ import annotations

import asyncio
from collections import Counter

import pytest

from brain.audit.ledger import SUBJECT_KINDS, AuditAction
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, REASON_CHARS, registered
from brain.ops.acceptance_audit import (
    A_BROWSER_SESSION_AND_A_TRACE_STORE_ARE_NOT_BUILT,
    ACTED_UNDER_THEIR_OWN_TRACE,
    ACTS,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, counts

MODULE = "brain.ops.acceptance_audit"
NAME = "each_audited_act_is_in_the_ledger_and_a_missing_entry_is_caught"


def test_every_act_is_one_the_ledger_records_under_a_kind_it_holds() -> None:
    """Held against `AuditAction` and `SUBJECT_KINDS`, outside this module. Delete this and the
    check can look for an action the ledger has no member for, and fail on every install."""
    actions = {one.value for one in AuditAction}
    assert all(action in actions and kind in SUBJECT_KINDS for action, kind in ACTS)
    assert Counter(action for action, _ in ACTS)["entity_merge"] == 2
    assert ACTED_UNDER_THEIR_OWN_TRACE.issubset({action for action, _ in ACTS})


def test_the_sentence_the_check_ends_with_fits_the_result_and_names_what_is_missing() -> None:
    """The reason is stored whole or not at all. Delete this and the one sentence saying why the
    leaf cannot close is cut short on the Install page."""
    assert len(A_BROWSER_SESSION_AND_A_TRACE_STORE_ARE_NOT_BUILT) <= REASON_CHARS
    assert "browser session" in A_BROWSER_SESSION_AND_A_TRACE_STORE_ARE_NOT_BUILT
    assert "trace store" in A_BROWSER_SESSION_AND_A_TRACE_STORE_ARE_NOT_BUILT
    assert [one.name for one in registered((MODULE,))] == [NAME]


def run_audit(url: str) -> tuple[str, str]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=registered((MODULE,)),
            force=True,
        )
    )
    [one] = results
    return one.outcome, one.reason


@pytest.mark.needs_db
def test_every_act_that_exists_is_seen_and_the_leaf_is_said_not_to_be_provable_whole() -> None:
    """**The check as the worker runs it.** Every act reaches the ledger with its actor and trace,
    the auditor's view shows each, the ledger verifies and catches its missing newest entry, and
    the check then says not run with the named sentence, leaving nothing behind. Delete this and
    any of those steps can stop working on a real schema with the check reading as it always did."""
    with at_head("brain_acceptance_audit") as url:
        before = counts(url)
        said = run_audit(url)
        after = counts(url)
    assert said == (NOT_RUN, A_BROWSER_SESSION_AND_A_TRACE_STORE_ARE_NOT_BUILT)
    assert after == before


@pytest.mark.needs_db
def test_an_act_the_ledger_does_not_record_fails_the_check() -> None:
    """The check failing for its reason: with the trigger that records a merge removed, the merge
    reaches no entry and the check fails rather than ending on its sentence. Delete this and a
    check that never looks at the entries passes the same way."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_audit_nomerge") as url:
        sql(url, "DROP TRIGGER canonical_merge_is_audited ON er.canonical")
        said = run_audit(url)
    assert said == (FAILED, "an act did not reach the ledger with the actor who made it")
