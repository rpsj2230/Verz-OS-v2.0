"""The install check for the knowledge inventory, passing on PostgreSQL at head and failing with
the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M25.3.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_knowledge_export import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_knowledge_export"
EXPORT = "the_inventory_holds_what_the_reader_may_see_and_no_text"


def test_the_module_names_its_leaf_in_one_check_inside_its_range() -> None:
    """One check naming the leaf, in a range of its own. Delete this and the leaf can move to a
    check that never looked at it."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(EXPORT, ("M25.3.3",))]
    assert checks_in(MODULE) == [EXPORT]
    assert 2130 < CHECK_ORDER < 2150


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_knowledge_export") as url:
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
    """**The module as the worker runs it.** It passes and nothing is left behind. Delete this and
    a check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_module(install) == {EXPORT: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_inventory_that_states_every_document_as_company_wide_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The level flattened on the way out. Delete this and a department's document can be listed as
    reaching everybody and the check goes on passing."""
    from brain import knowledge_export_routes as routes

    monkeypatch.setattr(routes, "who_may_read", lambda row: "everyone in the company")
    outcome, reason = run_module(install)[EXPORT]
    assert outcome == FAILED
    assert "level and department" in reason


@pytest.mark.needs_db
def test_an_inventory_nobody_records_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record dropped. Delete this and an inventory can leave with no ledger entry."""
    from brain import knowledge_export_routes as routes

    class Nowhere:
        async def record_report(self, **given: object) -> object:
            import uuid

            from brain.ops.data_export_store import TakenExport
            from brain.tables.data_export import ExportDataSet, ExportForm

            return TakenExport(
                export_id=str(uuid.uuid4()),
                data_set=ExportDataSet.KNOWLEDGE,
                requested_by="u",
                reason=given["reason"],  # type: ignore[arg-type]
                reason_reference="X",
                produced_at=given["at"],  # type: ignore[arg-type]
                form=ExportForm.READABLE,
                first_seq=None,
                last_seq=None,
                entries=0,
                verified=None,
                document_digest="0" * 64,
            )

    monkeypatch.setattr(routes, "report_records_of", lambda request: Nowhere())
    outcome, reason = run_module(install)[EXPORT]
    assert outcome == FAILED
    assert "ledger" in reason
