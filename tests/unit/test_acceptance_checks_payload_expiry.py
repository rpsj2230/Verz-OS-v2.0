"""The install check for the payload store's thirty-day expiry, passing on PostgreSQL at head and
failing with the policy broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M25.1.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import psycopg
import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_payload_expiry import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_payload_expiry"
EXPIRY = "a_trace_step_leaves_at_thirty_days_and_not_before"


def test_the_module_names_its_leaf_in_one_check_inside_its_range() -> None:
    """One check, one leaf, in the assigned order range. Delete this and the leaf can move to a
    check that never looked at it."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(EXPIRY, ("M25.1.3",))]
    assert checks_in(MODULE) == [EXPIRY]
    assert 2100 <= CHECK_ORDER <= 2199


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_payload_expiry") as url:
        yield url


def run_module(url: str) -> dict[str, tuple[str, str]]:
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


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** It passes and no step is left. Delete this and a
    check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_module(install) == {EXPIRY: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_policy_that_admits_every_step_fails_the_check(install: str) -> None:
    """The delete policy replaced by one admitting every row. Delete this and M25.1.3 closes on a
    role that may delete a trace from yesterday."""
    with psycopg.connect(install, autocommit=True) as conn:
        conn.execute("DROP POLICY trace_step_expired_removable ON obs.trace_step")
        conn.execute(
            "CREATE POLICY trace_step_expired_removable ON obs.trace_step FOR DELETE TO brain_app"
            " USING (true)"
        )
    try:
        [(outcome, reason)] = run_module(install).values()
        assert outcome == FAILED
        assert "inside thirty days" in reason
    finally:
        with psycopg.connect(install, autocommit=True) as conn:
            conn.execute("DROP POLICY trace_step_expired_removable ON obs.trace_step")
            conn.execute(
                "CREATE POLICY trace_step_expired_removable ON obs.trace_step FOR DELETE TO"
                " brain_app USING (recorded_at < now() - interval '30 days')"
            )


@pytest.mark.needs_db
def test_a_role_with_no_delete_fails_the_check(install: str) -> None:
    """The grant revoked, which is `0150`'s shape. Delete this and M25.1.3 closes on a table the
    sweep still cannot remove from."""
    with psycopg.connect(install, autocommit=True) as conn:
        conn.execute("REVOKE DELETE ON obs.trace_step FROM brain_app")
    try:
        [(outcome, _)] = run_module(install).values()
        assert outcome == FAILED
    finally:
        with psycopg.connect(install, autocommit=True) as conn:
            conn.execute("GRANT DELETE ON obs.trace_step TO brain_app")
