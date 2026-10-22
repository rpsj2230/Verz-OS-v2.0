"""The install checks for a provider that answers badly, each passing on PostgreSQL at head and
failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M30.4.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_fault_injection"
LIMIT = "a_rate_limit_is_walked_past_and_does_not_open_the_breaker"
MALFORMED = "a_reply_that_is_not_a_completion_is_not_shopped_to_another_step"


def test_the_module_declares_a_check_for_each_failure_shape() -> None:
    """Delete this and a check can lose the leaf with the Install page showing the same rows."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (LIMIT, ("M30.4.4",)),
        (MALFORMED, ("M30.4.4",)),
    ]
    assert checks_in(MODULE) == [LIMIT, MALFORMED]


@pytest.fixture
def hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hosted install holding a vault, with every key a test value that reaches nothing: the
    stand-ins answer in the process and the real providers are never asked."""
    from brain.ops import model_probe_run
    from brain.ops.openbao import OpenBaoVault
    from brain.ops.provider_keys import PROVIDER_SLOTS

    for one in PROVIDER_SLOTS:
        monkeypatch.delenv(one.env_var, raising=False)
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")
    monkeypatch.setattr(model_probe_run, "_PROCESS_KEYS", {})
    monkeypatch.setattr(
        OpenBaoVault,
        "read_static_kv",
        lambda self, path: {"api_key": f"test-{path.rsplit('/', 1)[-1]}-not-a-key"},
    )


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_fault_injection") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from(
        {
            "BRAIN_DATABASE_URL": url,
            "BRAIN_VAULT_ADDRESS": "https://vault.acceptance.invalid",
            "BRAIN_VAULT_TOKEN": "test-token-not-a-token",
        }
    )
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
@pytest.mark.usefixtures("hosted")
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass and no ladder, attempt or request row is
    left. Delete this and a check that can never pass on a real schema, or that leaves a pinned
    ladder on the owner's install, reaches it."""
    before = counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert counts(install) == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("hosted")
def test_a_chain_that_stops_at_a_rate_limit_fails_the_rate_limit_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 429 read as outside the closed set. Delete this and a burst of limits ends a person's
    question with the next step standing by."""
    from brain.models import driver
    from brain.models.routing import trigger_for as real

    def stops_on_429(**kwargs: object) -> object:
        return None if kwargs.get("status") == 429 else real(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(driver, "trigger_for", stops_on_429)
    assert _failed(install, LIMIT) == "a question behind a rate-limited step was not answered"


@pytest.mark.needs_db
@pytest.mark.usefixtures("hosted")
def test_a_chain_that_falls_back_on_rubbish_fails_the_malformed_reply_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every unrecognised failure read as a provider error, which is the quality fallback the
    closed set refuses. Delete this and the chain shops for a reply that parses."""
    from brain.models import driver
    from brain.models.routing import FallbackTrigger
    from brain.models.routing import trigger_for as real

    def shops(**kwargs: object) -> object:
        return real(**kwargs) or FallbackTrigger.PROVIDER_ERROR  # type: ignore[arg-type]

    monkeypatch.setattr(driver, "trigger_for", shops)
    assert _failed(install, MALFORMED) == "a reply that was not JSON was not told as a stop"
