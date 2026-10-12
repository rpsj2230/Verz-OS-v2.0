"""The roll-up helper: what a composite check says of the checks that ran before it, and the
entity resolution roll-up run against a real database.

Task ids: M14.8.1
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_roll_up as roll
from brain.ops import acceptance_run
from brain.ops.acceptance import (
    FAILED,
    NOT_RUN,
    PASSED,
    Check,
    CheckFailedError,
    CheckNotRunError,
    registered,
)
from brain.ops.acceptance_run import Harness
from brain.settings import settings_from
from tests.unit.test_acceptance import LONG_AGO, at_head, counts

OWN = "the_roll_up_itself"


async def _nothing(h: Harness) -> None:
    del h


def _check(name: str, *leaves: str) -> Check:
    return Check(name=name, leaves=tuple(leaves), sentence="Said.", run=_nothing)


def _harness(earlier: Mapping[str, tuple[str, str]]) -> Harness:
    return Harness(
        run="0a1b2c3d",
        now=LONG_AGO,
        settings=settings_from({}),
        connection=None,  # type: ignore[arg-type]
        earlier=earlier,
    )


@pytest.fixture
def suite(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Check]]:
    checks: list[Check] = []
    monkeypatch.setattr(roll, "registered", lambda: tuple(checks))
    yield checks


def _run(coroutine: Any) -> None:
    asyncio.run(coroutine)


def test_a_clause_is_shown_when_a_check_naming_it_passed_in_this_run(suite: list[Check]) -> None:
    """The positive case. Delete this and a roll-up that refuses everything passes every test
    written for its refusals."""
    suite += [_check("first_check", "M1.1.1"), _check("second_check", "M1.1.2")]
    h = _harness({"first_check": (PASSED, ""), "second_check": (PASSED, "")})
    _run(roll.clauses_demonstrated(h, {"one": ("M1.1.1",), "two": ("M1.1.2",)}, own=OWN))


def test_a_failed_clause_check_fails_the_roll_up(suite: list[Check]) -> None:
    """A clause that went red. Delete this and a composite leaf closes beside a failing check."""
    suite += [_check("first_check", "M1.1.1"), _check("second_check", "M1.1.2")]
    h = _harness({"first_check": (PASSED, ""), "second_check": (FAILED, "it did not")})
    with pytest.raises(CheckFailedError, match="second_check"):
        _run(roll.clauses_demonstrated(h, {"one": ("M1.1.1",), "two": ("M1.1.2",)}, own=OWN))


def test_a_clause_with_no_check_is_not_shown_and_the_others_do_not_cover_for_it(
    suite: list[Check],
) -> None:
    """`A_CLAUSE_WITH_NO_CHECK_IS_NOT_DEMONSTRATED`. Delete this and a roll-up passes on the
    clauses that have checks, closing a leaf on less than its sentence says."""
    suite += [_check("first_check", "M1.1.1")]
    h = _harness({"first_check": (PASSED, "")})
    with pytest.raises(CheckNotRunError, match="no check names a clause"):
        _run(roll.clauses_demonstrated(h, {"one": ("M1.1.1",), "two": ("M1.1.2",)}, own=OWN))


def test_a_clause_whose_check_was_not_run_or_has_not_run_yet_is_not_shown(
    suite: list[Check],
) -> None:
    """Not run, and not yet run, are both a clause nobody saw. Delete this and a roll-up that
    comes before a check it reads, or one whose check could not be asked, passes."""
    suite += [_check("first_check", "M1.1.1")]
    for earlier in ({"first_check": (NOT_RUN, "no relay")}, {}):
        with pytest.raises(CheckNotRunError, match="first_check"):
            _run(roll.clauses_demonstrated(_harness(earlier), {"one": ("M1.1.1",)}, own=OWN))


def test_a_roll_up_is_never_the_evidence_for_a_clause(suite: list[Check]) -> None:
    """A check naming only composite leaves reads others and asks nothing. Delete this and two
    roll-ups can vouch for each other with nothing on the install behind either."""
    suite += [_check("a_roll_up", "M14.8.1", "M1.1.1")]
    assert not roll.is_roll_up(suite[0])
    suite += [_check("only_a_roll_up", "M14.8.1")]
    assert roll.is_roll_up(suite[1])
    assert [one.name for one in roll.checks_naming("M14.8.1", excluding=OWN)] == ["a_roll_up"]


def test_the_roll_up_leaves_are_each_a_leaf_of_the_breakdown() -> None:
    """A mistyped composite leaf would make a real roll-up count as evidence. Delete this and
    one can."""
    wbs = json.loads(
        (Path(__file__).resolve().parents[2] / "docs" / "wbs.json").read_text(encoding="utf-8")
    )
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert leaves >= roll.ROLL_UP_LEAVES


# ------------------------------------------------------------------ the database half
MODULES = (
    "brain.ops.acceptance_checks_registry",
    "brain.ops.acceptance_checks_entity_merge",
    "brain.ops.acceptance_checks_matching",
    "brain.ops.acceptance_checks_review",
    "brain.ops.acceptance_checks_unresolved",
    "brain.ops.acceptance_checks_calibration",
    "brain.ops.acceptance_checks_er_proof",
    "brain.ops.acceptance_checks_er_cascade",
    "brain.ops.acceptance_checks_er_roll_up",
)
ONE = "entity_resolution_is_shown_clause_by_clause_in_this_run"


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_er_roll_up") as url:
        yield url


def run_modules(url: str, modules: Sequence[str]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings_from({"BRAIN_DATABASE_URL": url}),
            commit="abc1234",
            checks=list(registered(tuple(modules))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_the_roll_up_reads_what_the_entity_resolution_checks_came_to_in_the_same_run(
    install: str,
) -> None:
    """**The roll-up as the worker runs it**, after every check it reads. Every clause check
    passes and so does the roll-up, and nothing is left. Delete this and a roll-up that cannot see
    the run's earlier results reaches the owner's server."""
    before = counts(install)
    seen = run_modules(install, MODULES)
    assert seen[ONE] == (PASSED, "")
    assert seen == dict.fromkeys(seen, (PASSED, ""))
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_roll_up_run_without_the_checks_it_reads_is_not_run(install: str) -> None:
    """The roll-up alone, so none of its clause checks ran before it. Delete this and a roll-up
    passes in a run that never asked the questions it reports."""
    seen = run_modules(install, ("brain.ops.acceptance_checks_er_roll_up",))
    assert seen[ONE][0] == NOT_RUN


@pytest.mark.needs_db
def test_a_clause_check_that_fails_fails_the_clause_roll_up(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A merge allowed across the money boundary. Delete this and the composite closes M14.8.1
    beside a red check."""
    from brain.resolution import merge

    monkeypatch.setattr(
        merge.MoneyCheck, "permits_automatic", property(lambda self: True), raising=True
    )
    seen = run_modules(install, MODULES)
    assert seen["a_match_across_the_money_boundary_waits_for_a_person"][0] == FAILED
    assert seen[ONE][0] == FAILED
