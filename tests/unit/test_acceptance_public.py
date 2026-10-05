"""The public knowledge check: registered, passing as the worker runs it, and able to fail.

The check adds two documents, marks one and unmarks it inside its own transaction, so the database
half runs it against PostgreSQL at head and asserts the tables hold what they held before. Then the
product is broken where the check proves it, the way it would break: a marking rule that admits
every department, a widget search that reaches what a person in the department reaches, and an
unmarking that leaves the marking in place. Each is a failed check with its own sentence.

Task ids: M10.7.2
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_public"
NAME = "a_visitor_reads_only_what_an_administrator_marked_public"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M10.7.2",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert "M10.7.2" in {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert checks_in(MODULE) == [NAME]


def run_check(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url, **INSTALL}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_on_a_real_database_the_check_passes_and_leaves_nothing_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    holds what it held before. Delete this and a check that cannot pass on the real schema, or one
    that leaves a public document on a client's install, reaches the owner first."""
    with at_head("brain_acceptance_public") as url:
        before = counts(url)
        outcomes = run_check(url, tuple(mine().values()))
        after = counts(url)

    assert outcomes == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("scope", "another department's administrator was not refused the marking"),
        ("reach", "a question about an unmarked document was told something"),
        ("unmark", "unmarking was not recorded naming who did it"),
    ],
)
def test_the_check_fails_where_public_knowledge_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, each the way it happens: the department test answered yes for every
    department, so one department's administrator publishes another's knowledge; the widget's
    search built as a person's in the department, both walls with it, which is needs-rupash 26's
    "a general search that then filters"; and an unmarking that touches the row and leaves it
    public. Delete this and the check is satisfied by a widget that answers from anything."""
    from brain.knowledge import document_tools, public, public_store, search
    from brain.ops.acceptance import RESERVED_DEPARTMENTS

    if broken == "scope":
        monkeypatch.setattr(public, "admits_department", lambda *_: True)
    elif broken == "reach":
        person = search.Reach(principal_id="u_somebody", departments=(RESERVED_DEPARTMENTS[0],))
        real_predicate, real_settings = search.reach_predicate, search.session_settings
        monkeypatch.setattr(search, "public_predicate", lambda: real_predicate(person))

        def as_person(reach: Any) -> Any:
            return real_settings(person if isinstance(reach, search.PublicReach) else reach)

        monkeypatch.setattr(document_tools, "session_settings", as_person)
    else:
        from sqlalchemy import text

        real = public_store.record_marking

        async def touched(session: Any, item_id: str, *, public: bool, by: str, at: Any) -> None:
            if public:
                await real(session, item_id, public=public, by=by, at=at)
                return
            await session.execute(
                text("UPDATE know.item SET updated_at = now() WHERE item_id = :id"),
                {"id": item_id},
            )

        monkeypatch.setattr(public_store, "record_marking", touched)
    with at_head("brain_acceptance_public") as url:
        assert run_check(url, (mine()[NAME],)) == {NAME: (FAILED, reason)}
