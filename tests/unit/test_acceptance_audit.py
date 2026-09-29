"""The install acceptance check for audit and tracing, run as the worker runs it.

The pure half holds the acts to the ledger's vocabulary and the reasons to the page. The database
half runs the check against PostgreSQL at head: on an install that has recorded a deploy it passes
and leaves nothing behind, on one that has recorded none it ends as not run with its sentence, and
with each clause broken in turn it fails with that clause's sentence. That last half is what makes
it a check: a trigger removed, a mask switched off, a trace store the application can read, and an
export that carries the release history each fail it.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.
The clock in the deploy recorded here is 2019, for the reason CLAUDE.md records about fixtures.

Task ids: M38.5.1, M24.3.4
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.audit.ledger import SUBJECT_KINDS, AuditAction
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_audit import (
    ACTED_UNDER_THEIR_OWN_TRACE,
    ACTS,
    NO_DEPLOYMENT_IS_RECORDED_TO_KEEP_OUT,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, counts

MODULE = "brain.ops.acceptance_audit"
NAME = "each_audited_act_is_in_the_ledger_and_a_missing_entry_is_caught"

#: What the deploy writes, which the check reads and must leave as found.
WRITTEN_HERE = ("ops.deployment_record",)

#: One deploy, long ago, whose values the export must not carry.
COMMIT = "0123456789abcdef0123456789abcdef01234567"
IMAGE = "registry.invalid/brain@sha256:" + "ab" * 32


def test_every_act_is_one_the_ledger_records_under_a_kind_it_holds() -> None:
    """Held against `AuditAction` and `SUBJECT_KINDS`, outside this module. Delete this and the
    check can look for an action the ledger has no member for, and fail on every install."""
    actions = {one.value for one in AuditAction}
    assert all(action in actions and kind in SUBJECT_KINDS for action, kind in ACTS)
    assert Counter(action for action, _ in ACTS)["entity_merge"] == 2
    assert Counter(ACTS)[("browser_session", "session")] == 2
    assert ACTED_UNDER_THEIR_OWN_TRACE.issubset({action for action, _ in ACTS})


def test_the_sentence_the_check_ends_with_fits_the_result_and_names_what_is_missing() -> None:
    """The reason is stored whole or not at all. Delete this and the one sentence saying why the
    export could not be shown to keep a deploy out is cut short on the Install page."""
    assert len(NO_DEPLOYMENT_IS_RECORDED_TO_KEEP_OUT) <= REASON_CHARS
    assert "no deployment" in NO_DEPLOYMENT_IS_RECORDED_TO_KEEP_OUT
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


def record_a_deploy(url: str) -> None:
    """One deploy through the deploy's own writer, as the login it runs as."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from brain.db import normalise_database_url
    from brain.ops.deployment_store import record
    from brain.ops.deployments import Deployment

    engine = create_engine(normalise_database_url(url), poolclass=NullPool)
    try:
        with engine.begin() as conn:
            record(
                conn,
                [
                    Deployment(
                        at=datetime(2019, 3, 4, 9, 0, tzinfo=UTC),
                        outcome="deployed",
                        commit=COMMIT,
                        image=IMAGE,
                        previous="registry.invalid/brain@sha256:" + "cd" * 32,
                        task_ids=("M24.3.4",),
                    )
                ],
            )
    finally:
        engine.dispose()


def left_as_found(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        **counts(url),
        **{one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN_HERE},  # noqa: S608
    }


@pytest.fixture(scope="module")
def deployed() -> Iterator[str]:
    """One database at head with one deploy recorded, shared by the runs that change no schema."""
    with at_head("brain_acceptance_audit") as url:
        record_a_deploy(url)
        yield url


@pytest.mark.needs_db
def test_every_clause_is_seen_on_an_install_that_recorded_a_deploy_and_nothing_is_left(
    deployed: str,
) -> None:
    """**The check as the worker runs it.** Every act reaches the ledger with its actor and trace,
    the auditor's view shows each and the browser session's recording, the ledger verifies and
    catches its missing newest entry, the read's trace is stored masked behind its own role, and
    the export carries no deploy: the check passes, and every table it wrote holds what it held.
    Delete this and any of those parts can stop working on a real schema with the check green."""
    before = left_as_found(deployed)
    said = run_audit(deployed)
    after = left_as_found(deployed)
    assert said == (PASSED, "")
    assert after == before


@pytest.mark.needs_db
def test_a_trace_stored_without_its_mask_fails_the_check(
    deployed: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mask switched off for attributes and left on for payloads, so the store accepts the rows:
    the person's id and the record's own word reach the trace, and the check fails on them. Delete
    this and a check that never looks inside a step passes the same way."""
    from brain.ops import trace_store
    from brain.ops.tracing import Span, mask

    def half(span: Span) -> Span:
        return replace(mask(span), attributes=dict(span.attributes))

    monkeypatch.setattr(trace_store, "mask", half)
    assert run_audit(deployed) == (FAILED, "a stored trace held content that was not masked")


@pytest.mark.needs_db
def test_a_trace_the_recorder_never_stored_fails_the_check(
    deployed: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no mask at all the payload columns refuse the rows, the recorder logs and carries on,
    and the check finds no graph. Delete this and a recorder that stores nothing passes."""
    from brain.ops import trace_store
    from brain.ops.tracing import Span

    def none(span: Span) -> Span:
        return span

    monkeypatch.setattr(trace_store, "mask", none)
    assert run_audit(deployed) == (FAILED, "a run's trace graph was not stored under its trace")


@pytest.mark.needs_db
def test_an_export_that_carries_the_release_history_fails_the_check(
    deployed: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The export given a line naming the deployed commit, as a manifest that named the release
    would: the check fails. Delete this and a check that never compares the history with the
    document passes whatever the export carries."""
    from brain.ops import data_transfer

    produce = data_transfer.produce_audit_export

    def with_release(*args: Any, **kwargs: Any) -> data_transfer.Produced:
        made = produce(*args, **kwargs)
        return replace(made, document=f"{made.document}\nrelease {COMMIT}\n")

    monkeypatch.setattr(data_transfer, "produce_audit_export", with_release)
    assert run_audit(deployed) == (FAILED, "the compliance export held the deployment history")


@pytest.mark.needs_db
def test_an_install_that_recorded_no_deploy_says_the_export_clause_was_not_run() -> None:
    """Every other clause passes and the last is not run with its sentence, because an empty history
    proves nothing about keeping one out. Delete this and the check can pass vacuously on an
    install whose deploys are never recorded."""
    with at_head("brain_acceptance_audit_nodeploy") as url:
        assert run_audit(url) == (NOT_RUN, NO_DEPLOYMENT_IS_RECORDED_TO_KEEP_OUT)


@pytest.mark.needs_db
def test_an_act_the_ledger_does_not_record_fails_the_check() -> None:
    """The check failing for its reason: with the trigger that records a merge removed, the merge
    reaches no entry and the check fails. Delete this and a check that never looks at the entries
    passes the same way."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_audit_nomerge") as url:
        record_a_deploy(url)
        sql(url, "DROP TRIGGER canonical_merge_is_audited ON er.canonical")
        said = run_audit(url)
    assert said == (FAILED, "an act did not reach the ledger with the actor who made it")


@pytest.mark.needs_db
def test_a_browser_session_the_ledger_does_not_record_fails_the_check() -> None:
    """With `0150`'s trigger removed a session opens and closes with no entry, and the check fails.
    Delete this and the browser session's clause can be satisfied by the other acts' entries."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_audit_nosession") as url:
        record_a_deploy(url)
        sql(url, "DROP TRIGGER browser_session_is_audited ON agent.browser_session")
        said = run_audit(url)
    assert said == (FAILED, "an act did not reach the ledger with the actor who made it")


@pytest.mark.needs_db
def test_a_trace_store_the_application_can_read_fails_the_check() -> None:
    """With SELECT granted to the application's own role the separation is gone, and the check
    fails before it reads anything. Delete this and a grant widened in a later migration passes."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_audit_readable") as url:
        record_a_deploy(url)
        sql(url, "GRANT SELECT ON obs.trace_step TO brain_app")
        said = run_audit(url)
    assert said == (FAILED, "a stored trace is readable by the application's own role")
