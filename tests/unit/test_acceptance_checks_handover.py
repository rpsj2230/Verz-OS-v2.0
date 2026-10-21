"""The install checks for the handover pack, each passing on PostgreSQL at head and failing with the
product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M30.5.4, M30.6.6, M37.4.2.4, M37.4.3.3, M37.4.3.5, M37.2.4.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_handover"
STATEMENT = "the_statement_is_made_only_after_a_rehearsal_verified"
PROVIDERS = "the_subprocessors_are_the_providers_whose_key_is_held"
OWNERS = "owners_and_the_review_are_recorded_and_checked"
WRITTEN = ("ops.setting",)


def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Delete this and a check can lose a leaf with the Install page showing the same rows."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (STATEMENT, ("M30.5.4", "M30.6.6")),
        (PROVIDERS, ("M37.4.2.4",)),
        (OWNERS, ("M37.4.3.3", "M37.4.3.5", "M37.2.4.4")),
    ]
    assert checks_in(MODULE) == [STATEMENT, PROVIDERS, OWNERS]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_handover") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    both.update({one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN})  # noqa: S608
    return both


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All three pass and no owner, review or switch is
    left. Delete this and a check that can never pass on a real schema, or that leaves the
    handover recorded on the owner's install, reaches it."""
    before = _counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 3
    assert _counts(install) == before


@pytest.mark.needs_db
def test_a_statement_made_without_a_verified_rehearsal_fails_the_statement_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal removed. Delete this and M30.6.6 closes on a statement that can be made
    before anything was rehearsed."""
    from datetime import UTC, datetime

    from brain import handover_routes
    from brain.launch import ServiceLevel
    from brain.ops import acceptance_checks_handover as module

    def made(profile: str, **_: Any) -> ServiceLevel:
        return ServiceLevel(
            profile=profile,
            rpo_seconds=1,
            rto_seconds=1,
            scheduled_exposure_seconds=1,
            measured_rto_seconds=1.0,
            measured_at=datetime.now(UTC),
            because="x",
        )

    monkeypatch.setattr(handover_routes, "service_level", made)
    assert _failed(install, STATEMENT) == module.THE_STATEMENT_WAS_MADE_WITH_NO_REHEARSAL


@pytest.mark.needs_db
def test_a_route_that_ignores_the_switch_fails_the_owners_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch read as always on. Delete this and the handover is rewritten on an install
    where nobody turned recording on."""
    from brain import handover_routes
    from brain.ops import acceptance_checks_handover as module

    async def always(_session: Any, _feature: Any) -> bool:
        return True

    monkeypatch.setattr(handover_routes, "is_on", always)
    assert _failed(install, OWNERS) == module.THE_SWITCH_WAS_IGNORED


@pytest.mark.needs_db
def test_a_review_window_that_stops_refusing_fails_the_owners_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window check dropped. Delete this and a review nobody will hold is booked."""
    from brain import handover_routes
    from brain.ops import acceptance_checks_handover as module

    monkeypatch.setattr(handover_routes, "review_gaps", lambda **_: ())
    assert _failed(install, OWNERS) == module.A_LATE_REVIEW_WAS_BOOKED


@pytest.mark.needs_db
def test_a_list_that_names_a_provider_nobody_holds_fails_the_subprocessor_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the agreement names a provider the install never configured."""
    from brain import handover_routes
    from brain.ops import acceptance_checks_handover as module

    monkeypatch.setattr(handover_routes, "held_providers", lambda: frozenset({"anthropic"}))
    assert _failed(install, PROVIDERS) == module.A_PROVIDER_WAS_INVENTED
