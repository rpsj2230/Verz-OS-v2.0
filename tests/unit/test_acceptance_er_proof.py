"""The registration-number check, passing on PostgreSQL at head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M14.2.6
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

MODULE = "brain.ops.acceptance_checks_er_proof"
NAME = "a_uen_joins_in_one_spelling_and_a_mistyped_one_does_not"


def test_the_module_declares_one_check_naming_the_leaf_it_proves() -> None:
    """One check, one leaf. Delete this and the check can lose its leaf with the page showing the
    same row, or start closing a leaf it does not prove."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(NAME, ("M14.2.6",))]
    assert checks_in(MODULE) == [NAME]
    from brain.ops import acceptance_checks_er_proof as module

    assert 800 <= module.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_er_proof") as url:
        yield url


def run_er(url: str) -> dict[str, tuple[str, str]]:
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
def test_the_registration_number_check_passes_on_an_install_and_leaves_nothing(
    install: str,
) -> None:
    """**The check as the worker runs it.** It passes and nothing it wrote is left. Delete this and
    a check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_er(install) == {NAME: (PASSED, "")}
    assert counts(install) == before


def _check_uen_that(accepts: str) -> Any:
    from brain.resolution.normalise import UenCheck, UenKind

    def check_uen(value: str, *, year_ceiling: int | None = None) -> UenCheck:
        del year_ceiling
        spelled = value.strip().upper() if accepts == "everything" else value.strip()
        return UenCheck(
            valid=True, kind=UenKind.LOCAL_COMPANY, canonical=spelled, reason="accepted"
        )

    return check_uen


@pytest.mark.needs_db
def test_a_registry_that_accepts_any_value_as_a_registration_number_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The structural check answering valid for every value, in one spelling. Delete this and the
    check closes M14.2.6 on a registry that joins records on a typing mistake."""
    from brain.resolution import cascade

    monkeypatch.setattr(cascade, "check_uen", _check_uen_that("everything"))
    [(outcome, reason)] = run_er(install).values()
    assert outcome == FAILED
    assert "not a registration number was kept" in reason


@pytest.mark.needs_db
def test_a_registry_that_hashes_a_number_as_written_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valid numbers hashed as written, so two spellings are two keys. Delete this and the check
    closes M14.2.6 on a registry in which one number in two spellings never joins."""
    from brain.resolution import cascade

    monkeypatch.setattr(cascade, "check_uen", _check_uen_that("as written"))
    [(outcome, reason)] = run_er(install).values()
    assert outcome == FAILED
    assert "lower case did not join" in reason
