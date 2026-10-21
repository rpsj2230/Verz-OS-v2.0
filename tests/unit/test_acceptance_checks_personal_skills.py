"""The personal skills install check, passing on PostgreSQL at head and failing when broken.

The database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.3.2.1, M40.3.2.2, M40.3.2.3
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_personal_skills"
NAME = "a_member_writes_a_skill_and_nobody_sees_it_until_they_offer_it"


def test_the_module_declares_its_leaves_and_does_not_name_the_one_it_cannot_prove() -> None:
    """One check naming the three leaves it proves and not M40.3.2.4, whose own-agents half is
    unbuilt. Delete this and the check can name the fourth leaf, and a green run closes it on a
    refusal alone."""
    from brain.ops import acceptance_checks_personal_skills as module

    [one] = registered((MODULE,))
    assert (one.name, one.leaves) == (NAME, ("M40.3.2.1", "M40.3.2.2", "M40.3.2.3"))
    assert checks_in(MODULE) == [NAME]
    assert module.CHECK_ORDER == 1950


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_personal_skills") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str) -> dict[str, tuple[str, str]]:
    return run_check(url, list(registered((MODULE,))))


def _failed(url: str) -> str:
    [(outcome, reason)] = run(url).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_personal_skills_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and nothing is left behind. Delete this and a
    check that cannot pass on a real schema, or one that commits a skill, ships."""
    before = counts(install)
    assert run(install) == {NAME: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_library_that_shows_an_unoffered_skill_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clause that leaves an unoffered skill out of the library taken away. Delete this and
    M40.3.2.3 closes on a library every reviewer can read a colleague's draft in."""
    from sqlalchemy import true

    from brain.ops import skill_store

    monkeypatch.setattr(skill_store, "not_an_unfinished_personal_skill", lambda: true())
    reason = _failed(install)
    assert "library" in reason or "reviewer" in reason


@pytest.mark.needs_db
def test_a_route_that_finds_a_skill_by_its_key_alone_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner left out of the lookup behind the offer, so a colleague's press is answered
    differently from a press on a key nobody made. Delete this and M40.3.2.3 closes on a route that
    can be used to ask whether somebody has written a particular file."""
    from brain.ops import personal_skill_store
    from brain.ops.personal_skill_store import PersonalEntry, StoredPersonalSkills

    real = StoredPersonalSkills.one_of_mine

    async def by_key_alone(
        self: StoredPersonalSkills, owner_id: str, digest: str
    ) -> PersonalEntry | None:
        async with self._sessions() as session:
            from sqlalchemy import select

            from brain.tables.skill_personal import SkillPersonalRow

            owner = (
                await session.execute(
                    select(SkillPersonalRow.owner_id).where(SkillPersonalRow.digest == digest)
                )
            ).scalar_one_or_none()
        return None if owner is None else await real(self, owner, digest)

    monkeypatch.setattr(personal_skill_store.StoredPersonalSkills, "one_of_mine", by_key_alone)
    assert "tell it apart" in _failed(install)
