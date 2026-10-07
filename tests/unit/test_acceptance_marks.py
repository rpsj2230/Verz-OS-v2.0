"""The marking check, passing on PostgreSQL at head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M16.6.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from typing import Any, Final

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE: Final = "brain.ops.acceptance_checks_marks"
NAME: Final = "an_answer_is_marked_with_one_action_on_the_web_and_in_a_chat"

#: What the check writes beyond the suite's list.
ALSO_WRITTEN: Final = ("chat.conversation", "chat.message", "mem.mark")


def test_the_check_names_the_leaf_it_proves() -> None:
    """One check, one leaf. Delete this and the check can lose its leaf with the page showing the
    same row, or start closing a leaf it does not prove."""
    from brain.ops import acceptance_checks_marks as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(NAME, ("M16.6.4",))]
    assert checks_in(MODULE) == [NAME]
    assert 800 <= module.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_marks") as url:
        yield url


@pytest.fixture(autouse=True)
def an_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run_check(url: str) -> dict[str, tuple[str, str]]:
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


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and nothing it wrote is left: no mark, thread,
    binding or channel. Delete this and a check that can never pass on a real schema, or one that
    commits a person's marks, reaches the owner's server."""
    before = _counts(install)
    assert run_check(install) == {NAME: (PASSED, "")}
    assert _counts(install) == before


def _counted_nowhere(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import api_routes

    class Nowhere:
        async def mark(self, **kwargs: Any) -> bool:
            return True

        async def on(self, trace_id: str) -> Any:
            raise AssertionError("the route asks the store only to write")

    monkeypatch.setattr(api_routes, "marks_of", lambda state: Nowhere())


def _anybody_may_mark(monkeypatch: pytest.MonkeyPatch) -> None:

    from sqlalchemy import literal, select

    from brain.ops import learning_signal_store as store

    monkeypatch.setattr(store, "answer_given_to", lambda *args, **kwargs: select(literal(True)))


def _no_reference_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import chat_answer

    monkeypatch.setattr(chat_answer, "mark_line", lambda trace: "")


def _a_reply_is_never_a_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.channels import inbound

    monkeypatch.setattr(inbound, "read_mark", lambda text: None)


BREAKS: Final[dict[str, tuple[Callable[[pytest.MonkeyPatch], None], str]]] = {
    "counted_nowhere": (_counted_nowhere, "NOT_COUNTED_ON_THE_WEB"),
    "anybody_may_mark": (_anybody_may_mark, "A_COLLEAGUE_MARKED_IT"),
    "no_reference_offered": (_no_reference_offered, "NO_REFERENCE_OFFERED"),
    "a_reply_is_never_a_mark": (_a_reply_is_never_a_mark, "NOT_COUNTED_IN_CHAT"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_check_fails_where_the_product_is_broken(
    install: str, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Four breaks, each failing with its own sentence: a mark counted nowhere, anybody marking
    anybody's answer, a chat answer that offers no reference, and a reply that is never read as a
    mark. Delete this and the check can pass with any of those properties gone."""
    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    import brain.ops.acceptance_checks_marks as module

    assert run_check(install) == {NAME: (FAILED, getattr(module, reason))}


@pytest.mark.needs_db
def test_a_marks_table_that_could_keep_a_sentence_fails_the_check(install: str) -> None:
    """A column of free text added to the marks table for one run and dropped. Delete this and the
    check closes M16.6.4 on a table that keeps a reason beside the mark."""
    import brain.ops.acceptance_checks_marks as module
    from tests.fixtures.scratch_postgres import sql

    sql(install, "ALTER TABLE mem.mark ADD COLUMN why text")
    try:
        assert run_check(install) == {NAME: (FAILED, module.A_SENTENCE_COULD_BE_KEPT)}
    finally:
        sql(install, "ALTER TABLE mem.mark DROP COLUMN why")
