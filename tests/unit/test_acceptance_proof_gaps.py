"""The proof-gap roll-ups: which clauses have no check today, pinned, and what the page says.

Task ids: M1.8.5, M11.8.3, M1.6.18
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import NOT_RUN, registered
from brain.ops.acceptance_checks_proof_gaps import (
    A_REAL_ACCOUNT_AND_A_REAL_MAILBOX_ARE_NEEDED,
    A_REAL_LARK_ACCOUNT_AND_A_REAL_SIGN_IN_ARE_NEEDED,
    IDENTITY_CLAUSES,
    LIVE_READING_CLAUSES,
)
from brain.ops.acceptance_roll_up import checks_naming
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_proof_gaps"
IDENTITY = "identity_is_shown_clause_by_clause_in_this_run"
LIVE = "live_reading_is_shown_clause_by_clause_in_this_run"
FORGOT = "a_reserved_person_resets_their_password_and_sets_a_second_factor"
LARK_IN = "a_reserved_person_signs_in_with_lark_and_a_leaver_cannot"

#: The clauses no check shows today, by the roll-up that names them. When somebody writes the check
#: for one, this is the line to move it off, and the roll-up then reads that check.
NO_CHECK_YET = {
    IDENTITY: {
        "signs in through the identity provider",
        "idle and absolute session limits",
        "an account bound to nobody is told once",
    },
    LIVE: {
        "a question spanning many records",
        "embeddings need no outbound call",
    },
}


def test_the_checks_are_registered_with_the_leaves_they_name() -> None:
    """Delete this and a roll-up can close a leaf it does not name, or name an id no task has."""
    named = {one.name: one.leaves for one in registered((MODULE,))}
    assert named == {
        IDENTITY: ("M1.8.5",),
        LIVE: ("M11.8.3",),
        FORGOT: ("M1.6.18",),
        LARK_IN: ("M1.1.9",),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for module in wbs["modules"] for leaf in module["leaf_ids"]}
    for clauses in (IDENTITY_CLAUSES, LIVE_READING_CLAUSES):
        assert {leaf for one in clauses.values() for leaf in one} <= leaves


def test_the_clauses_with_no_check_are_exactly_the_ones_said_to_have_none() -> None:
    """**The gap list is pinned.** Delete this and a clause can be written out of a roll-up to make
    it pass, or a check written for one can leave the roll-up still saying there is none."""
    for own, expected in NO_CHECK_YET.items():
        clauses = IDENTITY_CLAUSES if own == IDENTITY else LIVE_READING_CLAUSES
        uncovered = {
            clause
            for clause, leaves in clauses.items()
            if not any(checks_naming(leaf, excluding=own) for leaf in leaves)
        }
        assert uncovered == expected


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_proof_gaps") as url:
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
def test_each_roll_up_is_not_run_and_names_the_clauses_nothing_shows(install: str) -> None:
    """What the Install page says. Delete this and a roll-up can say "not run" with nothing about
    what is missing, which is the one thing a person reading it needs."""
    seen = run_modules(install, (MODULE,))
    for name, expected in NO_CHECK_YET.items():
        outcome, reason = seen[name]
        assert outcome == NOT_RUN
        assert reason.startswith("no check names a clause of this leaf: ")
        assert all(clause in reason for clause in expected), reason


@pytest.mark.needs_db
def test_the_forgot_password_check_says_why_it_cannot_run(install: str) -> None:
    """Delete this and the leaf's row on the Install page says nothing of why nobody has proved
    it, or the check can run and make an account at the owner's sign-in service."""
    seen = run_modules(install, (MODULE,))
    assert seen[FORGOT] == (NOT_RUN, A_REAL_ACCOUNT_AND_A_REAL_MAILBOX_ARE_NEEDED)
    assert seen[LARK_IN] == (NOT_RUN, A_REAL_LARK_ACCOUNT_AND_A_REAL_SIGN_IN_ARE_NEEDED)
