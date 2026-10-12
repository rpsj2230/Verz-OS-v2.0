"""The channels' roll-up: every clause names checks that exist, and the roll-up reads them in a run.

Task ids: M10.7.3
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from brain.ops.acceptance_checks_channels_roll_up import CLAUSES
from brain.ops.acceptance_roll_up import checks_naming
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head
from tests.unit.test_acceptance_channels import lends, save_relay

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_channels_roll_up"
ONE = "every_shipped_channel_is_shown_clause_by_clause_in_this_run"
OWN = ONE

#: Every module holding a check the roll-up reads, then the roll-up, which sits after them all.
MODULES = (
    "brain.ops.acceptance_checks",
    "brain.ops.acceptance_checks_agent_reach",
    "brain.ops.acceptance_checks_cards",
    "brain.ops.acceptance_checks_channel_framework",
    "brain.ops.acceptance_checks_channels",
    "brain.ops.acceptance_checks_chat",
    "brain.ops.acceptance_checks_runtime",
    "brain.ops.acceptance_checks_speed",
    "brain.ops.acceptance_checks_widget",
    "brain.ops.acceptance_threads",
    MODULE,
)


def test_the_roll_up_is_registered_with_the_leaf_it_proves_and_asks_nothing_itself() -> None:
    """Delete this and the roll-up can close a leaf it does not name, or be counted as evidence."""
    [one] = registered((MODULE,))
    assert (one.name, one.leaves) == (ONE, ("M10.7.3",))
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert set(one.leaves) <= {leaf for m in wbs["modules"] for leaf in m["leaf_ids"]}


def test_every_clause_names_a_leaf_a_check_proves_and_every_leaf_is_one_of_the_breakdown() -> None:
    """**A clause with no check is a clause the roll-up can never show**, so the leaf could never
    close, and one naming a leaf that is not in the breakdown is a clause nothing can prove. Delete
    this and either is found by the owner's install not closing the task."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for m in wbs["modules"] for leaf in m["leaf_ids"]}
    for clause, named in CLAUSES.items():
        assert set(named) <= leaves, clause
        assert any(checks_naming(leaf, excluding=OWN) for leaf in named), clause


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_channels_roll_up") as url:
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


@pytest.fixture(scope="module")
def relay_saved(install: str) -> str:
    """The relay on Notifications, saved once: the email check runs only half without one."""
    save_relay(install)
    return install


@pytest.fixture
def with_a_relay(relay_saved: str, monkeypatch: pytest.MonkeyPatch) -> str:
    from tests.unit.test_acceptance import INSTALL

    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("brain.channel_routes.mail_password_of", lambda request: lends("pw"))
    return relay_saved


@pytest.mark.needs_db
def test_the_roll_up_passes_in_a_run_where_every_channel_check_passed(with_a_relay: str) -> None:
    """**The roll-up as the worker runs it**, after every check it reads. Delete this and a
    roll-up that cannot see the run's earlier results reaches the owner's server."""
    seen = run_modules(with_a_relay, MODULES)
    assert seen[ONE] == (PASSED, "")


@pytest.mark.needs_db
def test_a_roll_up_run_without_the_checks_it_reads_is_not_run(install: str) -> None:
    """Delete this and a roll-up passes in a run that never asked the questions it reports."""
    seen = run_modules(install, (MODULE,))
    assert seen[ONE][0] == NOT_RUN


@pytest.mark.needs_db
def test_a_channel_check_that_fails_fails_the_roll_up(
    with_a_relay: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Telegram header check that passes anything. Delete this and the composite closes M10.7.3
    beside a red channel."""
    from brain.channels import telegram

    monkeypatch.setattr(telegram, "assert_from_telegram", lambda **kwargs: None)
    seen = run_modules(with_a_relay, MODULES)
    assert seen["a_telegram_message_on_the_registered_header_is_answered"][0] == FAILED
    assert seen[ONE][0] == FAILED
