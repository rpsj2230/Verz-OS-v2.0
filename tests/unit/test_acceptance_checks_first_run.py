"""The first-run wizard's install checks, passing on PostgreSQL at head, leaving nothing, and
failing with the wizard broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M42.5.3, M42.5.4, M42.5.10, M42.5.11, M42.5.13, M42.5.8, M42.6.2
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import INSTALL, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_first_run"
CODE = "the_wizard_wants_the_setup_code_and_says_what_is_wrong_in_words"
STEPS = "the_wizard_counts_steps_and_reviews_everything_before_writing"
CLOSED = "a_closed_wizard_answers_as_a_path_that_does_not_exist"
VALUES = "the_wizard_s_values_are_held_in_the_install_s_settings"
KEY = "a_provider_key_the_wizard_was_given_is_held_in_the_vault"


def test_the_module_declares_the_leaves_each_check_proves() -> None:
    """The checks and the leaves each closes. Delete this and a check can lose a leaf, or gain one
    it does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        CODE: ("M42.5.3", "M42.5.13"),
        STEPS: ("M42.5.4", "M42.5.10"),
        CLOSED: ("M42.5.11",),
        VALUES: ("M42.6.2",),
        KEY: ("M42.5.8",),
    }
    assert checks_in(MODULE) == [CODE, STEPS, CLOSED, VALUES, KEY]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_first_run") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
def test_the_checks_pass_on_an_install_and_leave_nothing(install: str, issuer: None) -> None:
    """**The checks as the worker runs them.** They pass and leave no person, grant or ledger
    entry, though the third gives a reserved person every grant a first administrator holds for
    the length of its transaction. Delete this and a check that commits would leave a second
    administrator on the owner's server."""
    before = counts(install)
    results = run_module(install, MODULE)
    assert {name: results[name] for name in (CODE, STEPS, CLOSED)} == dict.fromkeys(
        (CODE, STEPS, CLOSED), (PASSED, "")
    )
    # A scratch database was not set up through the wizard and names no vault.
    assert results[VALUES][0] == NOT_RUN and results[KEY][0] == NOT_RUN
    assert counts(install) == before


@pytest.mark.needs_db
def test_the_values_check_passes_when_every_required_value_is_held_and_fails_when_one_is_not(
    install: str, issuer: None
) -> None:
    """The wizard's required settings written as the appointment writes them pass; with one gone
    the check fails. Delete this and M42.6.2 is only ever shown as not run."""
    from brain.setup_wizard import WIZARD
    from tests.fixtures.scratch_postgres import sql

    required = sorted({q.setting for s in WIZARD for q in s.questions if q.setting and q.required})
    written: list[str] = []
    try:
        for name in required:
            key = f"install.{name.removeprefix('INSTALL_').lower()}"
            sql(
                install,
                "INSERT INTO ops.setting (key, value_type, value, description, updated_by)"
                " VALUES (%s, 'string', '\"x\"'::jsonb, 'acceptance', 'acceptance')",
                key,
            )
            written.append(key)
            if name != required[-1]:
                outcome, reason = run_module(install, MODULE)[VALUES]
                assert outcome == FAILED, reason
        assert run_module(install, MODULE)[VALUES] == (PASSED, "")
    finally:
        for key in written:
            sql(install, "DELETE FROM ops.setting WHERE key = %s", key)


@pytest.mark.needs_db
def test_a_wizard_that_never_checks_the_code_on_later_screens_fails_the_code_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A screen behind the first that accepts any code lets whoever finds the page write the
    install. Delete this and M42.5.3 closes on a wizard that checks the code only at the ends."""
    from brain import setup_wizard

    monkeypatch.setattr(setup_wizard, "assert_unlocked", lambda *args, **kwargs: None)
    outcome, reason = run_module(install, MODULE)[CODE]
    assert outcome == FAILED, reason
    assert "behind the first accepted a wrong" in reason


@pytest.mark.needs_db
def test_a_review_that_prints_a_secret_fails_the_review_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A review that shows the provider key puts it on a screen and in a browser's history. Delete
    this and M42.5.10 closes on a review that prints what it was told to keep out of sight."""
    from dataclasses import replace

    from brain import setup_wizard

    real = setup_wizard.review

    def printing(*args: object, **kwargs: object) -> tuple[object, ...]:
        lines = real(*args, **kwargs)  # type: ignore[arg-type]
        return tuple(
            replace(one, shown="acceptance-key-printed", state_key="")
            if one.field == "provider_key"
            else one
            for one in lines
        )

    monkeypatch.setattr(setup_wizard, "review", printing)
    outcome, reason = run_module(install, MODULE)[STEPS]
    assert outcome == FAILED, reason
    assert "secret" in reason


@pytest.mark.needs_db
def test_a_wizard_that_stays_open_after_an_administrator_exists_fails_the_closed_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wizard that answers an install that already has an administrator lets whoever finds the
    page replay the install. Delete this and M42.5.11 closes on a door that never shuts."""
    from brain import setup_routes

    monkeypatch.setattr(setup_routes, "assert_open", lambda administrators: None)
    outcome, reason = run_module(install, MODULE)[CLOSED]
    assert outcome == FAILED, reason


def test_the_vault_check_passes_on_a_held_provider_key_and_is_not_run_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A held provider key passes; an empty slot, a sealed vault and no vault are each not run
    and none is a pass. Delete this and M42.5.8 closes on an install holding no key."""
    import asyncio
    from types import SimpleNamespace

    from brain.ops import vault_status
    from brain.ops.acceptance import CheckNotRunError
    from brain.ops.vault_status import Seal, SlotState

    body: Any = next(one.run for one in registered((MODULE,)) if one.name == KEY)

    def harness(address: str) -> SimpleNamespace:
        return SimpleNamespace(settings=SimpleNamespace(vault_address=address, vault_token="t"))

    def reporting(seal: Seal, state: SlotState) -> Any:
        def report(reader: object) -> object:
            slot = SimpleNamespace(state=state)
            return SimpleNamespace(seal=seal, providers=(slot,))

        return report

    monkeypatch.setattr(vault_status, "report", reporting(Seal.OPEN, SlotState.HELD))
    asyncio.run(body(harness("https://vault.example.invalid")))
    for seal, state, address in (
        (Seal.OPEN, SlotState.EMPTY, "https://vault.example.invalid"),
        (Seal.SEALED, SlotState.HELD, "https://vault.example.invalid"),
        (Seal.OPEN, SlotState.HELD, ""),
    ):
        monkeypatch.setattr(vault_status, "report", reporting(seal, state))
        with pytest.raises(CheckNotRunError):
            asyncio.run(body(harness(address)))
