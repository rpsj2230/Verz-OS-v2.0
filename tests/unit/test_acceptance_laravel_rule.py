"""The Laravel one-department rule check: registered, passing, and able to fail.

Run as the worker would, then against the product broken where it proves: a rule listing several
departments accepted, a refusal that names the wrong rule or gives no reason, and a record stored
under a department its view's rule does not name.

Task ids: M11.9.16, M11.9.17
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_laravel_rule"
NAME = "a_laravel_view_rule_names_one_department_for_every_record"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def test_the_laravel_rule_check_is_listed_with_the_leaves_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M11.9.16", "M11.9.17")


@pytest.mark.needs_db
def test_on_a_real_database_the_one_department_rule_is_held_and_nothing_is_left() -> None:
    """**The check as the worker runs it.** Delete this and a rule naming several departments, or
    a record kept under another one, can pass unseen on an install."""
    with at_head("brain_acceptance_laravel_rule") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _accepts_a_list(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.connectors.laravel as laravel
    from brain.core.scope import Clause, Op, Scope

    real = laravel.rule_of

    def first_only(text: str) -> Any:
        found = real(text)
        clause = found.clauses[0]
        value = clause.value[0] if isinstance(clause.value, tuple) else clause.value
        return Scope(clauses=(Clause(field=clause.field, op=Op.EQ, value=value),))

    monkeypatch.setattr(laravel, "rule_of", first_only)


def _stores_a_clash(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.ops.connector_sync as sync

    real = sync.stored_fields

    def lax(record: Any, visibility: Any) -> Any:
        from dataclasses import replace

        return real(
            replace(record, fields={k: v for k, v in record.fields.items() if k != "department"}),
            visibility,
        )

    monkeypatch.setattr(sync, "stored_fields", lax)


BREAKS: dict[str, tuple[Any, str]] = {
    "accepts_a_list": (_accepts_a_list, "A_LIST_WAS_ACCEPTED"),
    "stores_a_clash": (_stores_a_clash, "A_CLASH_WAS_STORED"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_laravel_rule_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Each way the product can be wrong is found. Delete this and the check can pass over a list
    that is connected and never read, or a record kept under a department it does not name."""
    import brain.ops.acceptance_checks_laravel_rule as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_laravel_rule_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
