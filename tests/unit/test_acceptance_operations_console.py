"""The install checks for the install's own screens, each passing on PostgreSQL at head and each
failing with the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head that the
application has furnished and whose built-in templates it has signed, as every start does. Every
check passes and leaves nothing, and the process holds the settings it held before. Then each is
shown failing: a request opened without naming its class, a screen answering a person who may not
open it, the release check reading only the environment, a saved value said to need a restart, and
an install with no record of its furnishing.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.
The template signing clock is 2999, for the reason CLAUDE.md records about fixtures.

Task ids: M27.1.6, M27.6.1, M27.15.51, M27.12.7, M27.7.27, M27.9.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_operations_console import (
    NO_TEMPLATE_IS_ON_FILE,
    NOTHING_HAS_FURNISHED_THIS_DATABASE,
    screen_grants,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_operations_console"
TRAFFIC = "a_request_s_traffic_class_is_declared_at_ingress_with_no_default"
INSTALL = "this_install_says_what_is_running_and_at_what_level"
FEATURE = "a_feature_switched_on_from_the_console_reaches_what_reads_it"
SETTING = "a_setting_is_saved_from_the_console_and_says_when_it_applies"
LIMITS = "rate_limits_and_capacity_answer_their_readers"
FURNISHED = "the_install_was_furnished_once_by_the_product"

#: The signing key and clock the fixture's start signs the built-in templates with.
KEY = "k" * 64
AT = datetime(2999, 1, 1, tzinfo=UTC)


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Six checks, each closing its own leaves. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (TRAFFIC, ("M27.1.6",)),
        (INSTALL, ("M27.6.1",)),
        (FEATURE, ("M27.15.51",)),
        (SETTING, ("M27.12.7",)),
        (LIMITS, ("M27.7.27",)),
        (FURNISHED, ("M27.9.5",)),
    ]


def test_the_operations_console_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [TRAFFIC, INSTALL, FEATURE, SETTING, LIMITS, FURNISHED]


def test_a_screen_reader_holds_the_screen_s_read_and_the_configuration_plane() -> None:
    """Held against `brain.console.reads.permitted`, the question every install route asks first.
    Delete this and the checks' readers can be refused for a grant the helper forgot, so every
    screen check fails on every install with nothing wrong in the product."""
    from brain.console.reads import permitted
    from brain.console.screens import screen
    from brain.core.entitlement import Capability, EntitlementSet, Grant

    for key in ("install", "updates", "limits", "connections"):
        held = EntitlementSet(
            principal_id="p",
            grants=tuple(
                Grant(capability=Capability(value=capability), scope=scope)
                for capability, scope in screen_grants(key)
            ),
        )
        assert permitted(screen(key).read, held)
        alone = EntitlementSet(principal_id="p", grants=held.grants[:1])
        assert not permitted(screen(key).read, alone)


def test_the_sentence_a_check_may_end_with_fits_the_result() -> None:
    """The not-run sentence is stored whole. Delete this and the one sentence saying why the
    templates could not be looked at is cut short on the Install page."""
    assert len(NO_TEMPLATE_IS_ON_FILE) <= REASON_CHARS
    assert len(NOTHING_HAS_FURNISHED_THIS_DATABASE) <= REASON_CHARS


# --------------------------------------------------------------------- on an install
def _sessions(url: str) -> Any:
    from brain.db import normalise_database_url
    from brain.session import make_app_engine, make_application_sessions

    return make_application_sessions(make_app_engine(normalise_database_url(url)))


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    """A database at head started once as the application starts: furnished, templates signed."""
    from brain.firstrun import GRANTED_BY
    from brain.ops.builtin_templates import sign_built_ins
    from brain.ops.starter_store import furnish
    from tests.fixtures.scratch_postgres import run

    with at_head("brain_acceptance_ops_console") as url:
        sessions = _sessions(url)
        # Two traces, as a start gives each of its two writes its own.
        furnished, signed = "install.furnish.0123456789abcdef", "install.furnish.fedcba9876543210"
        run(lambda: furnish(sessions, actor=GRANTED_BY, trace_id=furnished))
        run(lambda: sign_built_ins(sessions, key=KEY, at=AT, actor=GRANTED_BY, trace_id=signed))
        yield url


#: A cache address nothing answers at: `held_cache` hands the window store an in-memory one.
CACHE = "redis://cache.invalid:6379/0"


@pytest.fixture(autouse=True)
def held_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install's cache, answered in memory as Valkey answers the window store's statements."""
    import brain.cache as cache
    from tests.unit.test_acceptance_capacity import HeldCache

    held = HeldCache()
    monkeypatch.setattr(cache, "make_client", lambda url: held)


def run_ops(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url, "BRAIN_VALKEY_URL": CACHE})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


#: What these checks write beyond the suite's list.
ALSO_WRITTEN = ("gate.capability_registry", "gate.capability_pack", "agent.template_version")


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_every_operations_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All six pass, nothing a check wrote is left, and the
    process holds the saved settings it held before. Delete this and a check that can never pass
    on a real schema, or one that leaves a switch on, reaches the owner's server first."""
    from brain.install import saved_values

    before, held = _counts(install), dict(saved_values())
    outcomes = run_ops(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 6
    assert _counts(install) == before
    assert dict(saved_values()) == held


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_ops(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_request_opened_without_naming_its_class_fails_the_traffic_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ingress given a default class, the shape `A_TRAFFIC_CLASS_WITH_A_DEFAULT_IS_A_TRAFFIC_
    CLASS_NOBODY_SETS` refuses. Delete this and M27.1.6 closes on a check that a defaulted class
    passes."""
    from brain.gate.context import TrafficClass
    from brain.ops import telemetry

    def defaulted(
        *, traffic_class: TrafficClass = TrafficClass.SYSTEM, received_at: datetime
    ) -> Any:
        return telemetry.Ingress(
            trace_id=telemetry.mint_trace_id(), traffic_class=traffic_class, received_at=received_at
        )

    monkeypatch.setattr(telemetry, "open_request", defaulted)
    assert "without naming its class" in _failed(install, TRAFFIC)


@pytest.mark.needs_db
def test_a_screen_answering_anybody_fails_the_install_and_limits_checks(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The install routes' one question removed, so every screen answers a person with no grant.
    Delete this and M27.6.1 and M27.7.27 close on checks that pass a screen open to anybody."""
    from brain import install_routes

    monkeypatch.setattr(install_routes, "_permitted", lambda reach, key, now: None)
    assert "may not open This install" in _failed(install, INSTALL)
    assert "may not open Rate limits" in _failed(install, LIMITS)


@pytest.mark.needs_db
def test_a_database_version_the_database_is_not_at_fails_the_install_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen naming a revision nobody applied. Delete this and This install can report a
    level the install's database is not at with M27.6.1 green."""
    from brain import install_routes
    from brain.console.installation import DATABASE_VERSION_FACT, Fact, Source
    from brain.console.installation import install_facts as real

    def wrong(**kwargs: Any) -> Any:
        return tuple(
            Fact(name=one.name, source=Source.DECLARED, value="0000_nowhere")
            if one.name == DATABASE_VERSION_FACT
            else one
            for one in real(**kwargs)
        )

    monkeypatch.setattr(install_routes, "install_facts", wrong)
    assert "database is at" in _failed(install, INSTALL)


@pytest.mark.needs_db
def test_a_release_check_reading_only_the_environment_fails_the_feature_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Version and updates ignoring the console's switch, as it did before M27.15.51. Delete this
    and the switch closes M27.15.51 while reaching nothing."""
    from brain import install_routes

    async def never(session: Any, one: Any) -> bool:
        return False

    monkeypatch.setattr(install_routes, "is_on", never)
    assert "once switched on" in _failed(install, FEATURE)


@pytest.mark.needs_db
def test_a_switch_anybody_may_turn_fails_the_feature_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Features screen's authority removed. Delete this and a release check anybody can
    switch on closes M27.15.51."""
    from brain import feature_routes

    monkeypatch.setattr(feature_routes, "may_switch", lambda reach, now: True)
    assert "without the authority" in _failed(install, FEATURE)


@pytest.mark.needs_db
def test_a_save_that_writes_nothing_fails_the_settings_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route answering a save without writing it. Delete this and M27.12.7 closes on a
    screen whose saves vanish, and the check leaves the process holding nothing new either way."""
    from brain import settings_routes
    from brain.install import saved_values

    async def nothing(session: Any, values: Any, *, updated_by: str) -> int:
        return 0

    held = dict(saved_values())
    monkeypatch.setattr(settings_routes, "save", nothing)
    assert "the value it saved" in _failed(install, SETTING)
    assert dict(saved_values()) == held


@pytest.mark.needs_db
def test_a_database_nothing_furnished_is_not_judged_by_the_furnished_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database the application never started against has no furnishing record, and the check
    says so rather than passing. Delete this and M27.9.5 closes on an install nobody furnished."""
    from brain.ops import starter_store

    monkeypatch.setattr(starter_store, "FURNISHED_KEY", "starter.acceptance_never_written")
    assert run_ops(install, FURNISHED) == {
        FURNISHED: (NOT_RUN, NOTHING_HAS_FURNISHED_THIS_DATABASE)
    }


@pytest.mark.needs_db
def test_a_capability_left_unregistered_fails_the_furnished_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A capability the product declares with no row, as an install furnished by a release that
    did not register it would be. Delete this and M27.9.5 closes with the Capabilities screen
    missing what the gate checks."""
    from brain.core.entitlement import Capability
    from brain.ops import starter
    from brain.ops.starter import Declared

    real = starter.vocabulary()
    extra = Declared(
        capability=Capability(value="read:acceptance_never_registered"), description="Unheld."
    )
    monkeypatch.setattr(starter, "vocabulary", lambda: (*real, extra))
    assert "is not registered" in _failed(install, FURNISHED)


@pytest.mark.needs_db
def test_a_furnishing_that_wrote_a_person_fails_the_furnished_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A furnishing whose trace carries a person's row, as a demo seed would. Delete this and
    M27.9.5 closes on an install furnished with somebody's data."""
    from brain.ops import acceptance_operations_console as console

    monkeypatch.setattr(console, "FURNISHING_WRITES_ONLY", frozenset({"setting", "scope"}))
    assert "not the product's own" in _failed(install, FURNISHED)


@pytest.mark.needs_db
def test_rate_limits_that_cannot_read_the_cache_fail_the_limits_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route reading no live windows whatever the process holds. Delete this and M27.7.27
    closes on a screen that never says what is throttled now."""
    from brain import install_routes

    monkeypatch.setattr(install_routes, "throttle_source_of", lambda request: None)
    assert "throttled now" in _failed(install, LIMITS)
