"""The rebuild install check: registered, held, passing on PostgreSQL at head, and failing with the
product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: the check passes
and leaves nothing. Then it is shown failing with the page finding nothing (for a login that cannot
read across owners, which is the application role the page must never run as), with a window queued
for somebody who is not the document's owner, and with the page queueing nothing for what it found.

Task ids: M7.3.5
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_reembed as module
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_reembed"
CHECK = "a_model_change_moves_every_chunk_and_changes_no_permission"


def test_the_check_is_registered_with_the_leaf_it_shows_and_no_more() -> None:
    """M7.7.8 is deliberately not named: its sentence says answers keep using the previous
    vectors, which the product decided against. Delete this and the check can take M7.7.8 and close
    a leaf whose sentence is half false."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(CHECK, ("M7.3.5",))]
    assert checks_in(MODULE) == [CHECK]
    assert 1100 <= module.CHECK_ORDER <= 1199


def test_the_leaf_is_held_because_the_server_is_a_transport_the_check_made() -> None:
    """Delete this and M7.3.5 closes on a pass over a model server nobody asked."""
    held = json.loads((ROOT / "docs" / "proof-sweep-holds.json").read_text())["held"]
    assert held.get("M7.3.5", "").strip()
    assert "M7.7.8" not in held


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_reembed") as url:
        yield url


def run_check(url: str) -> tuple[str, str]:
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
    [one] = results
    return one.outcome, one.reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** It passes, and no chunk, item, person or grant it
    wrote is left. Delete this and a check that commits, or one that cannot pass on a real schema,
    reaches the owner's server."""
    before = counts(install)
    assert run_check(install) == (PASSED, "")
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_page_that_reads_as_the_application_role_finds_nothing_and_fails(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page's read run without stepping out of the application role, so the policy hides every
    other owner's chunks. Delete this and the check passes with the page reading as a role that
    sees company documents only, which on a real install is a rebuild that reports finished over a
    corpus it never saw."""

    async def as_the_role(self: Any, statement: Any) -> Any:
        result = await self._h.connection.execute(statement)
        return module._Rows(result.mappings().all())

    monkeypatch.setattr(module._AsTheLogin, "execute", as_the_role)
    outcome, reason = run_check(install)
    assert outcome == FAILED and "did not find a stale document" in reason, reason


@pytest.mark.needs_db
def test_a_window_queued_for_somebody_else_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every window queued for a fixed other person. Delete this and the rebuild can embed a
    department's documents on behalf of somebody who does not own them, which reads them under the
    wrong reach."""
    from brain.knowledge import reembed
    from brain.knowledge.embed_queue import embed_job

    real = reembed.jobs_for

    def for_somebody_else(page: Any, model: Any) -> Any:
        return tuple(
            embed_job(
                document_id=str(dict(job.args)["document_id"]),
                first_ordinal=int(dict(job.args)["first_ordinal"]),
                last_ordinal=int(dict(job.args)["last_ordinal"]),
                model=model,
                owner_id="u_someone_else",
            )
            for job in real(page, model)
        )

    monkeypatch.setattr(reembed, "jobs_for", for_somebody_else)
    outcome, reason = run_check(install)
    assert outcome == FAILED and "somebody other than the owner" in reason, reason


@pytest.mark.needs_db
def test_a_page_that_queues_no_window_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page finding its chunks and queueing nothing for them. Delete this and a rebuild that
    queues no window passes, leaving the corpus on the old model with a clean report."""
    from brain.knowledge import reembed

    monkeypatch.setattr(reembed, "jobs_for", lambda page, model: ())
    outcome, reason = run_check(install)
    assert outcome == FAILED and "did not find a stale document" in reason, reason
