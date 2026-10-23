"""The install checks for the connections step and the connector key, each passing on
PostgreSQL at head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M42.5.9, M42.6.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_first_run_sources import CHECK_ORDER
from brain.ops.connectable import CONNECTABLE, given
from brain.ops.connector_admin import connection_problems
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_first_run_sources"
STEP = "the_connections_step_hands_on_to_screens_that_connect_a_source"
KEY = "a_connector_key_is_kept_in_the_vault_and_shown_nowhere"


def test_the_module_names_each_leaf_in_one_check_inside_its_range() -> None:
    """One check per leaf, in the order range assigned. Delete this and a leaf can move to a check
    that never looked at it, or the module can slip out of its place on the Install page."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (STEP, ("M42.5.9",)),
        (KEY, ("M42.6.5",)),
    ]
    assert checks_in(MODULE) == [STEP, KEY]
    assert CHECK_ORDER == 1836


@pytest.fixture(autouse=True)
def issuer_of_this_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install values a console sign-in needs, set as the whole-suite run sets them."""
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_first_run_sources") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url, **INSTALL})
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


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_both_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass and nothing is left behind. Delete this and
    a check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_connect_that_is_refused_to_the_administrator_fails_the_step_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The administrator's own grant no longer enough to connect. Delete this and M42.5.9 closes on
    first-run screens whose connect request is refused to the person it was made for."""
    from brain import connector_routes

    monkeypatch.setattr(connector_routes, "may_connect_source", lambda *args: False)
    assert "administrator" in _failed(install, STEP)


@pytest.mark.needs_db
def test_a_screen_that_lists_no_source_fails_the_step_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The catalogue gone from the Connectors screen. Delete this and M42.5.9 closes on a first-run
    step that offers a person nothing to connect."""

    monkeypatch.setattr("brain.connector_routes.CONNECTABLE", {})
    assert "every source" in _failed(install, STEP)


@pytest.mark.needs_db
def test_a_key_that_is_not_kept_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write to the vault skipped. Delete this and M42.6.5 closes on a connection whose key is
    held nowhere, which reads as connected until the first read."""
    from brain import connector_routes
    from brain.ops.credentials import Kept

    async def nowhere(*args: object, **kwargs: object) -> Kept:
        return Kept(slot="nowhere", set_at=None)

    monkeypatch.setattr(connector_routes, "keep_credential", nowhere)
    assert "kept" in _failed(install, KEY)


@pytest.mark.needs_db
def test_a_list_that_cannot_ask_the_vault_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list reporting no key held. Delete this and M42.6.5 closes on a screen that tells a
    person to paste a key again that is already safe."""
    from brain.ops.credentials import VaultState

    monkeypatch.setattr(
        "brain.connector_routes.keys_held", lambda store, names: (VaultState.READY, {})
    )
    assert "held" in _failed(install, KEY)


@pytest.mark.needs_db
def test_a_response_that_repeats_the_key_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The key quoted back in the sentence the connect request answers. Delete this and M42.6.5
    closes on a screen that shows a key to whoever reads the response, which is the leak a vault
    exists to prevent."""
    from brain import connector_routes
    from brain.ops import acceptance_checks_connector_framework as framework

    key = "k" * 48
    monkeypatch.setattr(framework, "_credential", lambda name: key)
    monkeypatch.setattr(connector_routes, "CONNECTED", f"Connected with {key}.")
    assert "held the key" in _failed(install, KEY)


@pytest.mark.needs_db
def test_a_step_that_sets_a_value_fails_the_step_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Naming a source writing an installation value. Delete this and M42.5.9 closes on a step
    that commits a connection the person has only skimmed past."""
    from brain import setup_wizard

    real = setup_wizard.settings_from

    def writing(draft: setup_wizard.Draft) -> object:
        values = dict(real(draft))
        if draft.values_for(setup_wizard.StepId.CONNECTIONS).get("connections"):
            values["INSTALL_COMPANY_NAME"] = "named by the connections step"
        return values

    monkeypatch.setattr(setup_wizard, "settings_from", writing)
    assert "installation value" in _failed(install, STEP)


@pytest.mark.needs_db
def test_a_step_that_takes_any_name_fails_the_step_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name no source could have accepted. Delete this and M42.5.9 closes on a step that keeps
    whatever was typed and hands the console a name it cannot look up."""
    import re

    from brain import setup_wizard

    monkeypatch.setattr(setup_wizard, "SLUG", re.compile(r"^.*$"))
    assert "refused" in _failed(install, STEP)


@pytest.mark.needs_db
def test_a_screen_missing_one_source_fails_the_step_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One source dropped from the Connectors list. Delete this and M42.5.9 closes on a screen that
    offers some of the sources the console can connect."""

    kept = dict(CONNECTABLE)
    kept.pop(sorted(kept)[-1])
    monkeypatch.setattr("brain.connector_routes.CONNECTABLE", kept)
    assert "every source" in _failed(install, STEP)


@pytest.mark.needs_db
def test_a_source_listed_with_no_steps_fails_the_step_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guide dropped from every source. Delete this and M42.5.9 closes on a screen that shows
    a form with nothing said about where its values come from."""
    import dataclasses

    bare = {name: dataclasses.replace(kind, guide=()) for name, kind in CONNECTABLE.items()}
    monkeypatch.setattr("brain.connector_routes.CONNECTABLE", bare)
    assert "no steps" in _failed(install, STEP)


@pytest.mark.needs_db
def test_a_connect_the_route_refuses_fails_the_step_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The form judged wrong though it was filled as the console fills it. Delete this and M42.5.9
    closes on a first-run screen whose connect request is refused."""
    from brain.ops.connectable import SettingProblem

    refusal = (SettingProblem(field="source", code="x", message="No."),)
    monkeypatch.setattr("brain.connector_routes.connection_problems", lambda *args: refusal)
    assert "not accepted" in _failed(install, STEP)


@pytest.mark.needs_db
def test_a_connected_source_the_list_does_not_show_fails_the_step_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list hiding a connection that was made. Delete this and M42.5.9 closes on a screen that
    connects a source and then shows an empty list."""
    from brain import connector_routes

    monkeypatch.setattr(connector_routes, "admitted_connections", lambda *args: ())
    assert "listed as connected" in _failed(install, STEP)


@pytest.mark.needs_db
def test_a_connect_that_answers_a_vault_less_install_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source that takes a key connected where nothing can hold it. Delete this and M42.6.5
    closes on an install that says connected and holds no key."""
    from fastapi.responses import JSONResponse

    from brain import connector_routes

    monkeypatch.setattr(connector_routes, "_not_kept", lambda state: JSONResponse({}, 200))
    assert "no vault" in _failed(install, KEY)


@pytest.mark.needs_db
def test_a_key_kept_at_another_slot_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route and the declaration naming different slots. Delete this and M42.6.5 closes on a
    key the worker will never find, which reads as a source that is down."""
    from brain.ops import credentials

    real = credentials.connector_key_slot
    other = "freshdesk"
    monkeypatch.setattr(
        credentials, "connector_key_slot", lambda name: real(other if name != other else "xero")
    )
    assert "declaration" in _failed(install, KEY)


@pytest.mark.needs_db
def test_a_list_that_names_the_vault_path_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The slot's path drawn in the list. Delete this and M42.6.5 closes on a screen that tells
    anyone who reads it where the keys are kept."""
    from brain import connector_routes
    from brain.ops.credentials import connector_key_slot

    real = connector_routes.connected_view

    def naming(*args: object, **kwargs: object) -> object:
        shown = real(*args, **kwargs)  # type: ignore[arg-type]
        return shown.model_copy(update={"sync": connector_key_slot(shown.name).path})

    monkeypatch.setattr(connector_routes, "connected_view", naming)
    assert "vault path" in _failed(install, KEY)


@pytest.mark.needs_db
def test_a_key_stored_in_the_settings_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The key copied into the connection's stored settings. Delete this and M42.6.5 closes on a
    key sitting in a table beside its vault copy."""
    from brain.ops import acceptance_checks_connector_framework as framework

    key = "k" * 48
    real = given
    monkeypatch.setattr(framework, "_credential", lambda name: key)

    def copying(kind: object, settings: dict[str, str]) -> object:
        return {**real(kind, settings), "note": key}  # type: ignore[arg-type]

    monkeypatch.setattr("brain.connector_routes.given", copying)
    assert "key" in _failed(install, KEY)


@pytest.mark.needs_db
def test_a_step_that_keeps_nothing_fails_the_step_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sources named and no answer kept. Delete this and M42.5.9 closes on a step that thanks the
    person and forgets what they said."""
    from brain import setup_wizard

    real = setup_wizard.answer

    def forgetting(
        draft: setup_wizard.Draft, key: setup_wizard.StepId, values: object, *a: object, **k: object
    ) -> object:
        if key is setup_wizard.StepId.CONNECTIONS and values.get("connections"):  # type: ignore[attr-defined]
            return draft, ()
        return real(draft, key, values, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(setup_wizard, "answer", forgetting)
    assert "did not keep" in _failed(install, STEP)


@pytest.mark.needs_db
def test_a_step_that_refuses_to_be_skipped_fails_the_step_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blank answer refused. Delete this and M42.5.9 closes on a step that makes connecting a
    source a condition of finishing setup, which its own reason argues against."""
    from brain import setup_wizard
    from brain.locale import FieldError

    real = setup_wizard.answer

    def insisting(
        draft: setup_wizard.Draft, key: setup_wizard.StepId, values: object, *a: object, **k: object
    ) -> object:
        if key is setup_wizard.StepId.CONNECTIONS and not values.get("connections"):  # type: ignore[attr-defined]
            return draft, (FieldError(field="connections", key="setup.error.blank"),)
        return real(draft, key, values, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(setup_wizard, "answer", insisting)
    assert "skipping" in _failed(install, STEP)


@pytest.mark.needs_db
def test_a_connect_refused_only_with_a_vault_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real connect judged wrong after the two refusals were right. Delete this and M42.6.5
    closes on a key check that never confirms the keyed connect itself worked."""
    from brain.ops.connectable import SettingProblem

    real = connection_problems
    calls: list[int] = []

    def third_refused(*args: object) -> object:
        calls.append(1)
        if len(calls) == 3:
            return (SettingProblem(field="source", code="x", message="No."),)
        return real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr("brain.connector_routes.connection_problems", third_refused)
    assert "was not connected" in _failed(install, KEY)


@pytest.mark.needs_db
def test_a_blank_key_that_is_accepted_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both layers that refuse a blank key off. Delete this and M42.6.5 closes on a connect that
    takes an empty key and reads as connected."""
    from brain import connector_routes
    from brain.ops.credentials import Kept

    real = connection_problems
    calls: list[int] = []

    def blank_passes(*args: object) -> object:
        calls.append(1)
        return () if len(calls) == 2 else real(*args)  # type: ignore[arg-type]

    async def keeping_nothing(*args: object, **kwargs: object) -> Kept:
        return Kept(slot="nowhere", set_at=None)

    monkeypatch.setattr("brain.connector_routes.connection_problems", blank_passes)
    monkeypatch.setattr(connector_routes, "keep_credential", keeping_nothing)
    assert "blank key" in _failed(install, KEY)
