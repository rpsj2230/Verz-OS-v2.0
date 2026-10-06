"""The attachment acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a document
added at its owner's own level, attached to their thread, and read through the registered tool as
the owner, as a colleague, and for a document nobody attached. It passes, and every table it writes
holds afterwards what it held before. Then it is run against the product broken where it proves.

Task ids: M12.3.6
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_attachments"
NAME = "an_attached_file_is_read_at_its_owner_s_reach_and_by_nobody_else"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M12.3.6",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for m in wbs["modules"] for one in m["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


@pytest.mark.needs_db
def test_on_a_real_database_an_attached_file_is_read_by_its_owner_alone() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    holds afterwards what it held before, the conversation and its notes included, since the check
    attaches to a thread and records an answer in it. Delete this and attaching a file can break on
    a real schema with nothing on the install saying so, or a check can leave a person's thread
    behind on the owner's server."""
    from tests.fixtures.scratch_postgres import sql

    def chat(url: str) -> dict[str, int]:
        # The names are this module's constants, never input.
        return {
            one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
            for one in ("chat.conversation", "chat.message")
        }

    with at_head("brain_acceptance_attachments") as url:
        before = counts(url), chat(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url), chat(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("any_document", "the attachment tool read a document nobody attached"),
        ("nothing_kept", "the attached file was not read at its owner's reach"),
        ("anybody_attaches", "a colleague attached another person's own document to a thread"),
    ],
)
def test_the_check_fails_where_attaching_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks: the tool reading any document its caller may read, attached or not, an
    attach that keeps nothing on the thread, and the route attaching a document without asking
    whether its caller may read it. Each fails the check with its own sentence. Delete
    this and the check can pass with the property gone."""
    import sqlalchemy as sa

    import brain.chat.attachments as attachments
    from brain.chat.thread_store import StoredThreads
    from brain.knowledge.rows import RowQuery

    if broken == "any_document":

        def anything(attachment_id: str, *, principal_id: str, settings: Any) -> RowQuery:
            del attachment_id, principal_id
            return RowQuery(
                entity="knowledge",
                source="chat",
                columns=("message_id",),
                statement=sa.select(sa.literal(1).label("message_id")),
                certainly_empty=False,
                settings=settings,
            )

        monkeypatch.setattr(attachments, "attached_query", anything)
    elif broken == "anybody_attaches":
        import brain.thread_routes as thread_routes
        from brain.core.envelope import TypedResult

        def readable(records: Any) -> Any:
            del records

            async def read(request: Any, **kwargs: Any) -> Any:
                del request, kwargs
                return TypedResult[Any](records=("a passage",), source="knowledge")

            return read

        monkeypatch.setattr(thread_routes, "reader", readable)
    else:

        async def keeps_nothing(self: Any, principal_id: str, **kwargs: Any) -> str:
            del self, principal_id, kwargs
            return "00000000-0000-0000-0000-000000000000"

        monkeypatch.setattr(StoredThreads, "attach", keeps_nothing)
    with at_head(f"brain_acceptance_attachments_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, reason)
