"""The install check for a document's whole life, passing on PostgreSQL at head and failing.

The pure half holds the module to its one leaf and holds the document it adds to the lifecycle
checks' heading, which is what makes the newer version a version of the same document.

The database half runs the check as the worker would, with the hosted profile and every provider's
key in a vault the test answers for, the link answered by the recorded page, and the ladder the
wizard writes, and the check passes and leaves nothing. Then it is shown failing at three stages
with the product broken the way each would plausibly break: the hand-over recorded nowhere, the
answer handed passages without their badges, and the worker's re-verification run opening nothing.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M7.7.6
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_knowledge import TABLE, a_document_holding_a_table
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_models import Providers, laddered, live_ladder

MODULE = "brain.ops.acceptance_knowledge"
LIFE = "a_document_is_added_answered_replaced_and_falls_due_for_review"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_for_its_one_leaf() -> None:
    """One check, closing M7.7.6 alone. Delete this and the flow can start claiming the stages'
    own leaves, which would close them on a check that says only that the flow stopped."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(LIFE, ("M7.7.6",))]


def test_the_document_is_the_lifecycle_checks_document_holding_one_table_row() -> None:
    """The document is under the lifecycle checks' heading and holds the table's header, its
    rule and the row keyed by the word the question asks about. Delete this and a newer version
    stops being a version of the same document, or the question stops finding the table."""
    from brain.ops.acceptance_checks_lifecycle import HEADING

    text = a_document_holding_a_table("kestrel", "falcon").decode("utf-8")
    assert text.startswith(f"# {HEADING}\n")
    assert TABLE.format(key="kestrel", value="falcon") in text
    assert "| kestrel | falcon |" in text.splitlines()


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_knowledge") as url:
        laddered(url)
        yield url


@pytest.fixture
def vaulted(monkeypatch: pytest.MonkeyPatch) -> Providers:
    """The hosted profile and the vault the answer checks use, and the install offline."""
    from tests.unit.test_acceptance import INSTALL
    from tests.unit.test_acceptance_answers import vault_the_providers
    from tests.unit.test_acceptance_ingest import offline_install

    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)
    offline_install(monkeypatch)
    return vault_the_providers(monkeypatch)


def run_life(url: str) -> dict[str, tuple[str, str]]:
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
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_a_document_s_whole_life_passes_on_an_install_and_leaves_nothing(
    install: str, vaulted: Providers
) -> None:
    """**The check as the worker runs it.** It passes; nothing it wrote is left, the ladder
    included; and no provider of the product was asked. Delete this and a flow that can never pass
    on a real schema, or one that commits a document, reaches the owner's server first."""
    before, ladder = counts(install), live_ladder(install)
    assert run_life(install) == {LIFE: (PASSED, "")}
    assert counts(install) == before and live_ladder(install) == ladder
    assert vaulted.sent == []


def _failed(url: str) -> str:
    [(outcome, reason)] = run_life(url).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_hand_over_recorded_nowhere_fails_the_life_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hand-over route answering without writing the steward. Delete this and M7.7.6 closes
    with a document whose steward was never set."""
    from brain.knowledge import lifecycle_store

    async def forgetful(session: Any, item: Any, *, to: str) -> None:
        return None

    monkeypatch.setattr(lifecycle_store, "record_steward", forgetful)
    assert "hand the document to its steward" in _failed(install)


@pytest.mark.needs_db
def test_an_answer_without_its_badge_fails_the_life_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lane handed no item lookup, so it badges nothing. Delete this and M7.7.6 closes on an
    answer that never said whether anybody vouched for what it cited."""
    from dataclasses import replace

    from brain.gate import model_lane

    original = model_lane.evidence_of

    async def unbadged(composed: Any, *, lane: Any, **kwargs: Any) -> Any:
        return await original(composed, lane=replace(lane, items=None), **kwargs)

    monkeypatch.setattr(model_lane, "evidence_of", unbadged)
    assert "live and verified" in _failed(install)


@pytest.mark.needs_db
def test_a_re_verification_run_opening_nothing_fails_the_life_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker's run reading no due document. Delete this and M7.7.6 closes with a review date
    that passes and nobody is asked to look again."""
    from brain.knowledge import item_store

    original = item_store.run_reverification

    async def blind(session: Any, *, now: Any) -> Any:
        return await original(session, now=now.replace(year=2000))

    monkeypatch.setattr(item_store, "run_reverification", blind)
    assert "re-verification task" in _failed(install)


def test_the_knowledge_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here,
    beside the module's other tests, since 2026-09-30, so a package adding a check edits its own
    file and never a list every package appends to. Delete this and a check can drop out of the
    module with the page simply listing one fewer row."""
    assert checks_in("brain.ops.acceptance_knowledge") == [
        "a_document_is_added_answered_replaced_and_falls_due_for_review",
    ]
