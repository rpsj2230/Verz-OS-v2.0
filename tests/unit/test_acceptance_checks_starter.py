"""The install check for what a new install is furnished with, passing on PostgreSQL at head and
failing with the product broken the way it would plausibly break.

The database half runs the module against a database the application has furnished and whose
built-in templates it has signed, as every start does: the check passes and leaves nothing. Then it
is shown failing: a platform furnishing other than six roles, a furnishing that installed an agent,
a session limit that is not the one the defaults name, and a default that has become a setting; and
shown not run where nothing furnished the database or somebody retired the furnished pack.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.
The template signing clock is 2999, for the reason CLAUDE.md records about fixtures.

Task ids: M41.2.7
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_starter import (
    FURNITURE_WAS_RETIRED_BY_SOMEBODY,
    NO_BUILT_IN_TEMPLATE_IS_ON_FILE,
    NOTHING_HAS_FURNISHED_THIS_INSTALL,
    THE_FOUR_DEFAULTS,
    THE_SIX_ROLES,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_operations_console import _sessions

MODULE = "brain.ops.acceptance_checks_starter"
FURNISHED = "a_new_install_is_furnished_as_decided_and_not_blank"

#: The signing key and clock the fixture's start signs the built-in templates with.
KEY = "k" * 64
AT = datetime(2999, 1, 1, tzinfo=UTC)


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_the_one_check_for_the_leaf() -> None:
    """One check closing M41.2.7. Delete this and the check can lose the leaf with the page
    showing the same row, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(FURNISHED, ("M41.2.7",))]
    assert checks_in(MODULE) == [FURNISHED]


def test_the_module_sits_in_the_range_this_package_was_given() -> None:
    """The coordinator gave this package the keys 600 to 699, so two packages cannot share one.
    Delete this and a key outside the range is not noticed until two modules collide."""
    from brain.ops import acceptance_checks_starter as module

    assert 600 <= module.CHECK_ORDER <= 699


def test_the_roles_and_the_defaults_are_the_ones_the_owner_decided() -> None:
    """The six roles the owner's register names and the four defaults item 168 decided, written
    here as words and not read back from the module that declares them. Delete this and a seventh
    role, or a fifth default, can arrive with nothing on the owner's side to say it was asked."""
    assert {
        "super_admin",
        "department_admin",
        "member",
        "auditor",
        "connector_admin",
        "approver",
    } == THE_SIX_ROLES
    assert set(THE_FOUR_DEFAULTS) == {
        "session_idle_minutes",
        "session_absolute_hours",
        "approval_required_above",
        "knowledge_visibility",
    }


def test_the_sentences_a_check_may_end_with_fit_the_result() -> None:
    """Stored whole. Delete this and why the check was not run is cut short on the Install page."""
    assert len(FURNITURE_WAS_RETIRED_BY_SOMEBODY) <= REASON_CHARS
    assert len(NOTHING_HAS_FURNISHED_THIS_INSTALL) <= REASON_CHARS
    assert len(NO_BUILT_IN_TEMPLATE_IS_ON_FILE) <= REASON_CHARS


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    """A database at head started once as the application starts: furnished, templates signed."""
    from brain.firstrun import GRANTED_BY
    from brain.ops.builtin_templates import sign_built_ins
    from brain.ops.starter_store import furnish
    from tests.fixtures.scratch_postgres import run

    with at_head("brain_acceptance_starter") as url:
        sessions = _sessions(url)
        furnished, signed = "install.furnish.0123456789abcdef", "install.furnish.fedcba9876543210"
        run(lambda: furnish(sessions, actor=GRANTED_BY, trace_id=furnished))
        run(lambda: sign_built_ins(sessions, key=KEY, at=AT, actor=GRANTED_BY, trace_id=signed))
        yield url


def run_starter(url: str) -> dict[str, tuple[str, str]]:
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
def test_the_furnished_check_passes_on_a_furnished_install_and_leaves_nothing(
    install: str,
) -> None:
    """**The module as the worker runs it.** On an install furnished and signed as a start does,
    the check passes and writes nothing. Delete this and a check that can never pass on a real
    schema reaches the owner's server first."""
    before = counts(install)
    assert run_starter(install) == {FURNISHED: (PASSED, "")}
    assert counts(install) == before


def _failed(url: str) -> str:
    [(outcome, reason)] = run_starter(url).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_platform_that_furnishes_other_than_six_roles_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Five roles furnished. Delete this and M41.2.7 closes on an install missing one of the six
    every permission decision is written against."""
    from brain.ops import starter

    five = starter.roles()[:5]
    monkeypatch.setattr(starter, "roles", lambda: five)
    assert "exactly the six roles" in _failed(install)


@pytest.mark.needs_db
def test_a_furnishing_that_installed_an_agent_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A furnishing whose trace carries an agent, which item 168 decided no install starts with.
    Delete this and M41.2.7 closes on an install with an agent answering before anybody chose
    one."""
    from brain.ops import acceptance_checks_starter as module

    monkeypatch.setattr(module, "FURNISHING_WRITES_ONLY", frozenset({"setting", "scope"}))
    assert "besides its setting, scope and pack" in _failed(install)


@pytest.mark.needs_db
def test_a_session_limit_that_is_not_the_defaults_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sign-in code enforcing a longer idle limit than the one the defaults name, then a
    shorter absolute one. Delete this and the defaults can describe a limit the product does not
    keep, which is a default nobody could tell had gone wrong."""
    from brain.identity import sessions

    with monkeypatch.context() as patched:
        patched.setattr(sessions, "SESSION_IDLE", timedelta(minutes=31))
        assert "idle limit" in _failed(install)
    monkeypatch.setattr(sessions, "SESSION_ABSOLUTE_MAX", timedelta(hours=11))
    assert "absolute limit" in _failed(install)


@pytest.mark.needs_db
def test_a_default_that_has_become_a_setting_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One of the four declared as an installation setting, which item 168 decided against.
    Delete this and a setting that changes nothing can be added under a default's name."""
    from brain import install as installation

    declared = dict(installation.BY_NAME)
    declared["INSTALL_SESSION_IDLE_MINUTES"] = next(iter(declared.values()))
    monkeypatch.setattr(installation, "BY_NAME", declared)
    assert "is a setting" in _failed(install)


@pytest.mark.needs_db
def test_a_database_nothing_furnished_or_a_retired_pack_is_not_judged_by_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No furnishing record, then a furnished pack the install does not hold. Both say so in a
    sentence and neither is a failure. Delete this and M41.2.7 closes on an install nobody
    furnished, or fails an install whose owner retired a pack."""
    from brain.identity.packs import CapabilityPack
    from brain.ops import starter, starter_store

    with monkeypatch.context() as patched:
        patched.setattr(starter_store, "FURNISHED_KEY", "starter.acceptance_never_written")
        assert run_starter(install) == {FURNISHED: (NOT_RUN, NOTHING_HAS_FURNISHED_THIS_INSTALL)}
    extra = CapabilityPack(
        slug="acceptance_never_furnished",
        label="Never furnished",
        capabilities=starter.PACKS[0].capabilities,
    )
    monkeypatch.setattr(starter, "PACKS", (*starter.PACKS, extra))
    assert run_starter(install) == {FURNISHED: (NOT_RUN, FURNITURE_WAS_RETIRED_BY_SOMEBODY)}
