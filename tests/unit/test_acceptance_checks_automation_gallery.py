"""The install check for the gallery's three newer outcomes, passing on PostgreSQL at head and
failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M17.7.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import replace

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_automation_gallery"
NAME = "the_gallery_offers_three_outcomes_that_say_who_decides"


def test_the_module_declares_its_check_and_names_its_leaf() -> None:
    """Delete this and the check can lose its leaf with the Install page showing the same row."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(NAME, ("M17.7.5",))]
    assert checks_in(MODULE) == [NAME]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_automation_gallery") as url:
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
    """Delete this and a check that can never pass on a real schema reaches the owner's install."""
    before = counts(install)
    assert run_module(install) == {NAME: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_drafting_outcome_with_no_approver_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and M17.7.5 closes on a gallery that offers to draft customer records and says
    nothing of who approves them.

    The template is rebuilt with `drafts` off and no approval, which the constructor allows and
    the gallery then lists as an outcome that only reads.
    """
    from brain.console import automation_gallery
    from brain.ops import acceptance_checks_automation_gallery as module

    changed = tuple(
        replace(one, drafts=False, approval="") if one.template_id == "deal_capture" else one
        for one in automation_gallery.BUILT_IN
    )
    from brain import automation_gallery_routes

    monkeypatch.setattr(
        automation_gallery_routes,
        "gallery",
        lambda installed: automation_gallery.gallery(installed, catalogue=changed),
    )
    outcomes = run_module(install)
    assert outcomes[NAME][0] == FAILED
    assert outcomes[NAME][1] == module.A_DRAFT_HAD_NO_APPROVER
