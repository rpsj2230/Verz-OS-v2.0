"""The cascade checks, passing on PostgreSQL at head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M14.3.1, M14.7.1, M14.7.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from types import MappingProxyType

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_er_cascade"
STAGE_ONE = "stage_one_decides_on_a_hard_identifier_and_only_a_verified_one"
PEOPLE = "people_in_three_sources_are_compared_and_never_joined_on_a_name"
PROJECTS = "projects_are_queued_and_never_matched_on_their_clients_address"


def test_the_module_declares_each_check_naming_the_leaves_it_proves() -> None:
    """Three checks, one leaf each. Delete this and a check can lose its leaf with the page
    showing the same row, or start closing a leaf it does not prove."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (STAGE_ONE, ("M14.3.1",)),
        (PEOPLE, ("M14.7.1",)),
        (PROJECTS, ("M14.7.2",)),
    ]
    assert checks_in(MODULE) == [STAGE_ONE, PEOPLE, PROJECTS]
    from brain.ops import acceptance_checks_er_cascade as module

    assert 870 <= module.CHECK_ORDER <= 889


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_er_cascade") as url:
        yield url


def run_cascade(url: str) -> dict[str, tuple[str, str]]:
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
def test_the_cascade_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The checks as the worker runs them.** Each passes and nothing it wrote is left. Delete
    this and a check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_cascade(install) == {
        STAGE_ONE: (PASSED, ""),
        PEOPLE: (PASSED, ""),
        PROJECTS: (PASSED, ""),
    }
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_cascade_that_never_decides_on_a_tax_number_fails_the_stage_one_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tax numbers taken out of the hard identifiers. Delete this and the check closes M14.3.1
    on a cascade whose first stage ignores a tax number."""
    from brain.resolution import cascade
    from brain.resolution.canonical import IdentifierKind

    monkeypatch.setattr(
        cascade,
        "HARD_IDENTIFIERS",
        tuple(one for one in cascade.HARD_IDENTIFIERS if one is not IdentifierKind.TAX_ID),
    )
    outcome, reason = run_cascade(install)[STAGE_ONE]
    assert outcome == FAILED
    assert "tax number" in reason


@pytest.mark.needs_db
def test_a_cascade_that_trusts_an_unverified_telephone_number_fails_the_stage_one_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verification no longer required of a telephone number. Delete this and the check closes
    M14.3.1 on a cascade that merges on a number nobody confirmed."""
    from brain.resolution import cascade

    monkeypatch.setattr(cascade, "VERIFICATION_REQUIRED", frozenset())
    outcome, reason = run_cascade(install)[STAGE_ONE]
    assert outcome == FAILED
    assert "nobody verified" in reason


@pytest.mark.needs_db
def test_a_cascade_that_does_not_ask_for_a_verified_telephone_number_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every identifier treated as unverified, so a verified telephone number decides nothing.
    Delete this and the check passes on a cascade that never reaches stage one on a phone."""
    from brain.resolution import cascade
    from brain.resolution.canonical import IdentifierKind

    monkeypatch.setattr(
        cascade,
        "HARD_IDENTIFIERS",
        tuple(one for one in cascade.HARD_IDENTIFIERS if one is not IdentifierKind.PHONE),
    )
    outcome, reason = run_cascade(install)[STAGE_ONE]
    assert outcome == FAILED
    assert "verified telephone" in reason


@pytest.mark.needs_db
def test_people_given_the_company_profile_fail_the_people_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The person profile replaced by the company's, so a domain becomes a join key for people.
    Delete this and the check closes M14.7.1 on a cascade that joins a company's staff."""
    from brain.resolution import entities
    from brain.resolution.canonical import EntityType

    monkeypatch.setattr(
        entities,
        "PROFILES",
        MappingProxyType({**entities.PROFILES, EntityType.PERSON: entities.COMPANY_PROFILE}),
    )
    outcome, reason = run_cascade(install)[PEOPLE]
    assert outcome == FAILED
    assert "domain" in reason


@pytest.mark.needs_db
def test_projects_given_the_company_profile_fail_the_projects_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The project profile replaced by the company's, so a client's address corroborates a
    project's name. Delete this and the check closes M14.7.2 on a cascade that matches two
    projects of one client on the client's own postcode."""
    from brain.resolution import entities
    from brain.resolution.canonical import EntityType

    monkeypatch.setattr(
        entities,
        "PROFILES",
        MappingProxyType({**entities.PROFILES, EntityType.PROJECT: entities.COMPANY_PROFILE}),
    )
    outcome, reason = run_cascade(install)[PROJECTS]
    assert outcome == FAILED
    assert "client's address" in reason
