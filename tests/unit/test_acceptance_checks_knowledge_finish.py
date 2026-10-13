"""The install checks for retiring a document and fetching a link again from an agent's section.

Each passes on PostgreSQL where the release is applied, says so in a literal sentence where it is
not, and is shown failing with the product broken the way it would plausibly break.

The database half runs the module as the worker would: every check passes and leaves nothing. Then
each is shown failing: a retire that archives nothing, an authority that says yes to everybody, and
a refetch that writes no newer version. A database without the release's archive function or
columns is shown to be answered as not run, never as failed.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does,
and the ones that break the product skip on a database the release has not been applied to.

Task ids: M39.9.1.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_knowledge_finish import (
    THE_ARCHIVE_FUNCTION_IS_NOT_HERE,
    THE_SOURCE_COLUMNS_ARE_NOT_HERE,
)
from brain.settings import settings_from
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_knowledge_finish"
RETIRE = "a_retired_document_is_no_longer_drawn_on_by_the_agent"
REFETCH = "a_link_is_fetched_again_only_when_a_person_asks"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_the_two_checks_for_the_one_leaf_in_page_order() -> None:
    """Retire, then fetch again, both for M39.9.1.5. Delete this and a check can drop out of the
    module, or take another leaf's name, with the Install page listing one row fewer."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (RETIRE, ("M39.9.1.5",)),
        (REFETCH, ("M39.9.1.5",)),
    ]
    assert checks_in(MODULE) == [RETIRE, REFETCH]


def test_the_checks_stand_where_the_agent_knowledge_checks_leave_off_and_in_this_range() -> None:
    """The order this module declares is inside the range it was given. Delete this and a second
    module taking the same number puts two modules at one place on the page."""
    from brain.ops import acceptance_checks_knowledge_finish as module

    assert 1680 <= module.CHECK_ORDER <= 1699


def test_the_sentences_a_check_may_end_with_fit_the_result() -> None:
    """Stored whole. Delete this and why a check was not run is cut short on the Install page."""
    assert len(THE_ARCHIVE_FUNCTION_IS_NOT_HERE) <= REASON_CHARS
    assert len(THE_SOURCE_COLUMNS_ARE_NOT_HERE) <= REASON_CHARS


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_kfinish") as url:
        yield url


def run_finish(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
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


def _release_applied(url: str) -> bool:
    function = sql(
        url, "SELECT to_regprocedure('know.archive_item(character varying)') IS NOT NULL"
    )
    columns = sql(
        url,
        "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'know' "
        "AND table_name = 'item' AND column_name IN ('arrived_as', 'source_url')",
    )
    return bool(function[0][0]) and int(columns[0][0]) == 2


def _needs_the_release(url: str) -> None:
    if not _release_applied(url):
        pytest.skip("the archive function and the source columns are not on this database yet")


@pytest.mark.needs_db
def test_both_checks_pass_where_the_release_is_applied_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass, and nothing they wrote is left: no document,
    no passage, no agent. Where the release is not applied they say not run, in the literal
    sentences, and still leave nothing. Delete this and a check that can never pass on a real
    schema, or one that leaves a retired document behind, reaches the owner's server."""
    before = counts(install)
    outcomes = run_finish(install)
    if _release_applied(install):
        assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    else:
        assert outcomes == {
            RETIRE: (NOT_RUN, THE_ARCHIVE_FUNCTION_IS_NOT_HERE),
            REFETCH: (NOT_RUN, THE_SOURCE_COLUMNS_ARE_NOT_HERE),
        }
    assert len(outcomes) == 2
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_database_without_the_release_is_answered_as_not_run_and_never_as_failed() -> None:
    """The archive function and the two columns dropped from a scratch database, as an install the
    release has not reached. Delete this and a half-applied release shows the product as failing,
    which sends somebody to debug code that is fine."""
    with at_head("brain_acceptance_kfinish_bare") as url:
        sql(url, "DROP FUNCTION IF EXISTS know.archive_item(character varying)")
        sql(url, "ALTER TABLE know.item DROP COLUMN IF EXISTS source_url CASCADE")
        sql(url, "ALTER TABLE know.item DROP COLUMN IF EXISTS arrived_as CASCADE")
        assert run_finish(url) == {
            RETIRE: (NOT_RUN, THE_ARCHIVE_FUNCTION_IS_NOT_HERE),
            REFETCH: (NOT_RUN, THE_SOURCE_COLUMNS_ARE_NOT_HERE),
        }


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_finish(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_retire_that_archives_nothing_or_that_anybody_may_press_fails_the_retire_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The archive made a no-op, then the authority over a document given to every reader. Delete
    this and M39.9.1.5 closes on a button that retires nothing, or that anybody may press."""
    _needs_the_release(install)
    from brain import agent_knowledge_routes
    from brain.knowledge.lifecycle import Authority

    async def nothing(request: Any, asked: Any, item_id: str) -> Any:
        return object()

    with monkeypatch.context() as patched:
        patched.setattr(agent_knowledge_routes, "archive", nothing)
        assert "still listed" in _failed(install, RETIRE)
    monkeypatch.setattr(Authority, "may_act", lambda self, item: True)
    assert "Retire was not offered" in _failed(install, RETIRE)


@pytest.mark.needs_db
def test_a_refetch_that_writes_no_newer_version_fails_the_refetch_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The successor made without being written. Delete this and M39.9.1.5 closes on a button that
    reports a newer page and leaves the old one answering."""
    _needs_the_release(install)
    from brain import agent_knowledge_routes
    from brain.knowledge_lifecycle_routes import VersionAddedView, refused

    async def reports_only(*args: Any, **kwargs: Any) -> Any:
        # The refusal of an unchanged page stands; what a changed page would write does not.
        if args[5].item.item_id in {one.item_id for one in args[4]}:
            return refused("file", "already_on_file", kwargs["already"])
        return VersionAddedView(
            item_id="upload.not_written",
            supersedes=args[3].item_id,
            title="x",
            level="department",
            department="acceptance_a",
            passages=1,
            found_by="text search",
        )

    monkeypatch.setattr(agent_knowledge_routes, "write_successor", reports_only)
    assert "old version was still listed" in _failed(install, REFETCH)
