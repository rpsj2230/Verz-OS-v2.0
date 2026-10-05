"""The takeover acceptance check: registered, passing on a real schema, and able to fail.

The pure half holds the check to its leaves and to its place on the Install page. The database half
builds PostgreSQL to head once and runs the check as the worker would: it passes and leaves nothing
behind. Then the check is run against the install broken once for each thing its sentence states:
the card not offering a takeover, the standing never read so the rung never falls, and a breaker
that falls on the first takeover. Each is a failed check with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M8.3.5, M38.5.1
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from brain.console.approvals import card as real_card
from brain.gate.abstain import AutonomyBreaker
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.ops.acceptance_takeover import (
    BEFORE_THE_THIRD_TAKEOVER_THE_ACTION_DID_NOT_WAIT,
    THE_CARD_DID_NOT_OFFER_TAKING_OVER,
    THE_THIRD_TAKEOVER_DID_NOT_LOWER_THE_AGENT,
)
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_tools import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_takeover"
NAME = "a_third_takeover_in_a_week_lowers_the_agent_a_step"


def the_check() -> Check:
    return {one.name: one for one in registered((MODULE,))}[NAME]


# ------------------------------------------------------------------------ without a server
def test_the_check_is_registered_with_the_leaves_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert the_check().leaves == ("M8.3.5", "M33.6.1.3")
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(the_check().leaves) <= leaves


def test_the_takeover_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this and
    a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """One database at head for every run here; each check's writes are rolled back."""
    with at_head("brain_acceptance_takeover") as url:
        yield url


@pytest.mark.needs_db
def test_on_a_real_database_the_takeover_check_passes_and_leaves_nothing_behind(
    database: str,
) -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes with no reason,
    and the people, the grants and the ledger hold what they held before. Delete this and a check
    that cannot pass on the real schema reaches the owner's server first."""
    before = counts(database)
    outcome = run_checks(database, (the_check(),))

    assert outcome == {NAME: (PASSED, "")}
    assert counts(database) == before


def _never_offered(*args: Any, **kwargs: Any) -> Any:
    """`brain.console.approvals.card` building every card with no takeover offered."""
    shown = real_card(*args, **kwargs)
    return None if shown is None else dataclasses.replace(shown, may_take_over=False)


async def _never_read(self: Any, agent_id: str, target: str, now: Any) -> AutonomyBreaker:
    """`StoredTakeovers.standing` answering an empty standing whatever was taken over."""
    del self, now
    return AutonomyBreaker(agent_id=agent_id, target=target)


def _open_on_the_first(self: AutonomyBreaker, now: Any, **kwargs: Any) -> bool:
    """`AutonomyBreaker.is_open` falling at one takeover rather than at the threshold."""
    del kwargs
    return self.recent(now) >= 1


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("target", "broken", "reason"),
    [
        (
            "brain.approval_routes.card",
            _never_offered,
            THE_CARD_DID_NOT_OFFER_TAKING_OVER,
        ),
        (
            "brain.gate.takeover_store.StoredTakeovers.standing",
            _never_read,
            THE_THIRD_TAKEOVER_DID_NOT_LOWER_THE_AGENT,
        ),
        (
            "brain.gate.abstain.AutonomyBreaker.is_open",
            _open_on_the_first,
            BEFORE_THE_THIRD_TAKEOVER_THE_ACTION_DID_NOT_WAIT,
        ),
    ],
)
def test_the_check_fails_in_its_own_words_for_each_way_the_flow_breaks(
    database: str, monkeypatch: pytest.MonkeyPatch, target: str, broken: Any, reason: str
) -> None:
    """The card, the feed and the threshold, each broken the way it would break. Delete this and
    the check can pass with a card that never offers the choice, a standing nobody reads, or a
    breaker that falls on the first takeover."""
    monkeypatch.setattr(target, broken)

    [(outcome, said)] = run_checks(database, (the_check(),)).values()

    assert (outcome, said) == (FAILED, reason)
