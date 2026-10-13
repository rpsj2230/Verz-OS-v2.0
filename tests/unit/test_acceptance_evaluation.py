"""The evaluation checks, passing on PostgreSQL at head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M28.2.2, M28.2.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_evaluation"
STORES = "a_planted_canary_is_found_in_no_store_but_the_upload_s_own"
SCHEDULE = "the_scheduled_canary_run_is_owed_runs_and_alerts"


def test_the_module_declares_each_check_naming_the_leaf_it_proves() -> None:
    """Two checks, one leaf each. Delete this and a check can lose its leaf with the page
    showing the same row, or start closing a leaf it does not prove."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (STORES, ("M28.2.2",)),
        (SCHEDULE, ("M28.2.4",)),
    ]
    assert checks_in(MODULE) == [STORES, SCHEDULE]
    from brain.ops import acceptance_checks_evaluation as module

    assert 870 <= module.CHECK_ORDER <= 889


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_evaluation") as url:
        yield url


def run_evaluation(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _canaries_started(url: str, outcome: str) -> None:
    from tests.fixtures.scratch_postgres import sql

    sql(url, "DELETE FROM ops.control_run WHERE name = 'canary_run'")
    # The outcome is one of this module's two literals, never input.
    sql(
        url,
        "INSERT INTO ops.control_run (name, started_at, finished_at, outcome)"  # noqa: S608
        f" VALUES ('canary_run', now() - interval '1 minute', now(), '{outcome}')",
    )


@pytest.mark.needs_db
def test_the_evaluation_checks_pass_on_an_install_where_the_worker_started_the_canaries(
    install: str,
) -> None:
    """**The checks as the worker runs them**, on an install whose worker has run the canaries
    once and found nothing. Both pass and nothing they wrote is left. Delete this and a check that
    can never pass on a real schema reaches the owner's server."""
    _canaries_started(install, "ok")
    before = counts(install)
    assert run_evaluation(install) == {STORES: (PASSED, ""), SCHEDULE: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_the_schedule_check_is_not_run_before_the_worker_has_started_the_canaries(
    install: str,
) -> None:
    """No run on record. Delete this and an install whose worker never starts the canaries
    closes M28.2.4 on the product's functions alone."""
    from tests.fixtures.scratch_postgres import sql

    sql(install, "DELETE FROM ops.control_run WHERE name = 'canary_run'")
    seen = run_evaluation(install)
    assert seen[SCHEDULE][0] == NOT_RUN
    assert "has not started" in seen[SCHEDULE][1]
    assert seen[STORES] == (PASSED, "")


@pytest.mark.needs_db
def test_a_last_scheduled_run_that_was_red_fails_the_schedule_check(install: str) -> None:
    """The install's own newest run failed. Delete this and the check passes beside a gate the
    install's own schedule has found leaking."""
    _canaries_started(install, "failed")
    outcome, reason = run_evaluation(install)[SCHEDULE]
    assert outcome == FAILED
    assert "was red" in reason


@pytest.mark.needs_db
def test_a_lane_that_reads_and_shows_every_column_fails_the_stores_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row plane selecting every column and the redactor passing them whole, so a reader
    without the cost grant is told the cost. Delete this and the check closes M28.2.2 on a lane
    that discloses what the canary was planted to catch."""
    from brain.core.redaction import (
        OPAQUE_LABEL,
        ChannelPayload,
        RedactedAnswer,
        RedactionTrace,
    )
    from brain.gate import answer
    from brain.knowledge import classified_rows

    def every_column(classification: Any, **_: Any) -> tuple[str, ...]:
        return tuple(rule.column for rule in classification.rules)

    def whole(result: Any, *, entitlement: Any, policy: Any, now: Any = None) -> RedactedAnswer:
        del now
        raw = tuple(record.model_dump(mode="json") for record in result.records)
        return RedactedAnswer(
            payload=ChannelPayload(
                records=raw,
                label=OPAQUE_LABEL,
                source=result.source if raw else "",
                fetched_at=result.fetched_at if raw else "",
                truncated=result.truncated if raw else False,
            ),
            trace=RedactionTrace(
                policy_epoch=policy.epoch(), ent_hash=entitlement.ent_hash(), opaque=True
            ),
        )

    monkeypatch.setattr(classified_rows, "compile_projection", every_column)
    monkeypatch.setattr(answer, "redact", whole)
    _canaries_started(install, "ok")
    outcome, reason = run_evaluation(install)[STORES]
    assert outcome == FAILED
    assert "reached an answer" in reason


@pytest.mark.needs_db
def test_a_store_that_may_hold_nothing_fails_the_stores_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The table the upload lives in taken out of the allowed list, which is the same finding as
    a canary kept in some other table. Delete this and the check passes without ever reading the
    tables: a search that finds the canary nowhere also passes a check that never planted it."""
    from brain.ops import acceptance_checks_evaluation as module

    monkeypatch.setattr(module, "WHERE_THE_UPLOAD_LIVES", frozenset())
    _canaries_started(install, "ok")
    outcome, reason = run_evaluation(install)[STORES]
    assert outcome == FAILED
    assert "other than the upload's own" in reason


@pytest.mark.needs_db
def test_a_canary_run_that_does_not_raise_fails_the_schedule_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verdict returning for a run that found a defect. Delete this and the check closes
    M28.2.4 on a schedule whose red run is recorded as green."""
    from brain.ops import canary_run

    monkeypatch.setattr(canary_run, "verdict", lambda run: "passed")
    _canaries_started(install, "ok")
    outcome, reason = run_evaluation(install)[SCHEDULE]
    assert outcome == FAILED
    assert "did not raise" in reason


@pytest.mark.needs_db
def test_a_cadence_that_moved_fails_the_schedule_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The canaries' declared interval changed without the control following. Delete this and
    the check closes M28.2.4 on a schedule that is not the one declared."""
    from brain.ops import canaries

    monkeypatch.setattr(canaries, "CANARY_INTERVAL_SECONDS", 1)
    _canaries_started(install, "ok")
    outcome, reason = run_evaluation(install)[SCHEDULE]
    assert outcome == FAILED
    assert "cadence" in reason
