"""The install check for what a model call costs, passing on PostgreSQL and failing in each
direction its sentence names: no cost written for an answered question, and no stop for a used-up
ceiling.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.12.5, M27.7.15
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from brain.ops import acceptance_models, acceptance_run, model_probe_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from brain.ops.provider_keys import PROVIDER_SLOTS
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in
from tests.unit.test_acceptance_models import Providers, laddered

MODULE = "brain.ops.acceptance_checks_model_spend"
CHECK = "a_model_call_is_costed_and_a_used_up_budget_stops_the_next"


def test_the_module_declares_one_check_naming_its_two_leaves() -> None:
    """Delete this and the check can name a leaf it does not prove, or drop one from the Install
    page without a test going red."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        CHECK: ("M27.12.5", "M27.7.15")
    }
    assert checks_in(MODULE) == [CHECK]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    """A database at head, as the application leaves it. Nothing is furnished for this check."""
    with at_head("brain_acceptance_model_spend") as url:
        laddered(url)
        yield url


@pytest.fixture(autouse=True)
def vaulted(monkeypatch: pytest.MonkeyPatch) -> Providers:
    """The hosted profile, every provider's key in a vault the test answers for, and the providers
    answered in the process, as the routing checks' tests do. Nothing leaves the process and no real
    key is read; the check's own model is a stand-in that is never asked over a network."""
    from brain.ops.openbao import OpenBaoVault

    answering = Providers()
    for one in PROVIDER_SLOTS:
        monkeypatch.delenv(one.env_var, raising=False)
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")
    monkeypatch.setattr(model_probe_run, "_PROCESS_KEYS", {})
    monkeypatch.setattr(
        OpenBaoVault,
        "read_static_kv",
        lambda self, path: {"api_key": f"test-{path.rsplit('/', 1)[-1]}-not-a-key"},
    )
    monkeypatch.setattr(
        acceptance_models,
        "_client",
        lambda: httpx.Client(transport=httpx.MockTransport(answering)),
    )
    return answering


@pytest.fixture(autouse=True)
def a_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install has a currency, as a configured one does: without it the check says it was not
    run, which is its own answer and is held below."""
    monkeypatch.setenv("INSTALL_CURRENCY", "USD")


def run_check(url: str) -> tuple[str, str]:
    from brain.db import normalise_database_url

    settings = settings_from(
        {
            "BRAIN_DATABASE_URL": url,
            "BRAIN_VAULT_ADDRESS": "https://vault.acceptance.invalid",
            "BRAIN_VAULT_TOKEN": "test-token-not-a-token",
        }
    )
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    [one] = results
    return one.outcome, one.reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install(install: str) -> None:
    """The product as it ships, with enforcement off, as an install is: the second question is
    answered and its stop is listed as not enforced. Delete this and the check is never shown to
    pass against a database."""
    assert run_check(install) == (PASSED, "")


@pytest.mark.needs_db
def test_the_check_says_it_was_not_run_on_an_install_with_no_currency(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No currency, no cost is recorded, so there is nothing to follow and the check says so
    rather than failing a correct install. Delete this and the check is either red there or
    quietly green."""
    monkeypatch.delenv("INSTALL_CURRENCY")
    outcome, reason = run_check(install)
    assert outcome == NOT_RUN and "currency" in reason


@pytest.mark.needs_db
def test_the_check_fails_when_an_answered_question_leaves_no_cost(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recorder writes nothing, as it did before a model call reached it. Delete this and a
    cost nobody writes leaves the check green."""

    async def writes_nothing(self: Any, request: Any) -> None:
        return None

    monkeypatch.setattr("brain.ops.usage_store.UsageRecorder.finished", writes_nothing)
    outcome, reason = run_check(install)
    assert outcome == FAILED
    assert "cost" in reason


@pytest.mark.needs_db
def test_the_check_fails_when_a_used_up_ceiling_leaves_no_stop(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The budget is never judged, so no stop is recorded. Delete this and a ceiling that nothing
    reads leaves the check green."""

    async def never_judged(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr("brain.api_routes.budget_refusal_for", never_judged)
    outcome, reason = run_check(install)
    assert outcome == FAILED
    assert "stop" in reason


@pytest.mark.needs_db
def test_the_check_fails_when_the_cost_recorded_is_not_the_tokens_used(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recorder writes twice the tokens, a price applied wrongly. Delete this and a cost that
    does not equal what the request row says was used leaves the check green."""
    import dataclasses

    from brain.ops import usage_store

    real = usage_store.actual_for

    def doubled(request: Any, costed: Any) -> Any:
        row = real(request, costed)
        return dataclasses.replace(row, cost_minor=row.cost_minor * 2)

    monkeypatch.setattr(usage_store, "actual_for", doubled)
    outcome, reason = run_check(install)
    assert outcome == FAILED
    assert "tokens used" in reason


@pytest.mark.needs_db
def test_the_check_fails_when_a_reader_of_another_department_is_shown_the_stop(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stop board shows every stop to every reader. Delete this and a stop leaking across
    departments leaves the check green, while the positive case above still passes."""
    monkeypatch.setattr("brain.spend_detail_routes.budget_stops", lambda placed, *_a, **_k: placed)
    outcome, reason = run_check(install)
    assert outcome == FAILED
    assert "another department" in reason
