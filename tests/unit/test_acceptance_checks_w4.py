"""The wave-four milestone check, passing on PostgreSQL at head and failing with the product broken
the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: the check
passes and every table the suite counts holds afterwards what it held before. Then it is shown
failing in each of its three parts: an automation its owner could start alone, an approval whose
card is offered to nobody, and a press that decides nothing.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.2.2.5
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_cards import INSTALL, run_checks

MODULE = "brain.ops.acceptance_checks_w4"
WAVE_FOUR = "automations_run_and_approvals_land_in_lark_on_one_install"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_the_one_check_for_the_milestone() -> None:
    """One check closing M38.2.2.5. Delete this and the check can lose the leaf with the page
    showing the same row, and the milestone closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (WAVE_FOUR, ("M38.2.2.5",))
    ]
    assert checks_in(MODULE) == [WAVE_FOUR]


def test_the_module_sits_in_the_range_this_package_was_given() -> None:
    """The coordinator gave this package the keys 600 to 699, so two packages cannot share one.
    Delete this and a key outside the range is not noticed until two modules collide."""
    from brain.ops import acceptance_checks_w4 as module

    assert 600 <= module.CHECK_ORDER <= 699


def test_the_milestone_is_held_on_a_real_send_until_the_owner_shows_one() -> None:
    """The check's Lark is a stand-in that keeps what it is sent, so the milestone's task is on
    the proof sweep's hold list with its reason. Delete this and M38.2.2.5 closes on a card no
    chat ever showed, which is the claim the sweep was written not to make."""
    import json
    from pathlib import Path

    held = json.loads(
        (Path(__file__).resolve().parents[2] / "docs" / "proof-sweep-holds.json").read_text(
            encoding="utf-8"
        )
    )["held"]
    assert "M38.2.2.5" in held


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_w4") as url:
        yield url


@pytest.fixture(autouse=True)
def _install_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
def test_the_milestone_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** The check passes and nothing it wrote is left in any
    table the suite counts. Delete this and a check that can never pass on a real schema, or one
    that leaves an automation scheduled on the owner's install, reaches it first."""
    before = counts(install)
    assert run_checks(install, registered((MODULE,))) == {WAVE_FOUR: (PASSED, "")}
    assert counts(install) == before


def _outcome(url: str) -> tuple[str, str]:
    return run_checks(url, registered((MODULE,)))[WAVE_FOUR]


@pytest.mark.needs_db
def test_an_automation_its_owner_may_start_fails_the_milestone_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the second-person rule gone, an owner starts their own automation, and the milestone
    says so. Delete this and the milestone closes on an install where whoever an automation runs as
    widens its unattended schedule alone."""
    monkeypatch.setattr(
        "brain.console.automation_schedule.may_change_schedule",
        lambda one, *, becomes, approved_by: True,
    )
    assert _outcome(install) == (
        FAILED,
        "an automation's owner could start it without a second person",
    )


@pytest.mark.needs_db
def test_an_approval_whose_card_is_never_sent_fails_the_milestone_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With nothing sending a card when an approval is raised, the approver is sent nothing and the
    milestone says so. Delete this and the milestone closes on an install where approvals never
    land on a Lark card."""

    async def nothing(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr("brain.approval_cards.send_raised", nothing)
    assert _outcome(install) == (
        FAILED,
        "the card was not sent to the approver's kept address alone",
    )
