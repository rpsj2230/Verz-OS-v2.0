"""The builder-choices check: registered, passing on a real schema, and able to fail (M13.9.2).

The breaks put back, one at a time, a form that does not say it was cut, one that offers every tool,
one that offers none, and one that cuts the builder who holds the authority over everything.

Task ids: M13.9.2
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from typing import Any

import pytest

from brain.ops.acceptance import (
    FAILED,
    PASSED,
    REASON_CHARS,
    SENTENCE_CHARS,
    Check,
    check_modules,
    registered,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_builder_choices"
NAME = "a_department_builder_is_offered_only_what_their_department_holds"


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


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_builder_choices_check_is_listed_with_the_leaf_it_proves() -> None:
    """The one check this module registers, naming M13.9.2 alone and found by the suite, with a
    sentence that fits the Install page. Delete this and the check can drop out of its module or
    close a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M13.9.2",)
    assert len(mine()[NAME].sentence) <= SENTENCE_CHARS


def test_every_reason_the_builder_choices_check_can_give_fits_the_page() -> None:
    """Each sentence is a module constant that fits the result's column, and the one for an install
    with nothing to cut is a not-run reason and not a failure. Delete this and a reason can be cut
    off on the page, or an install with one source read as failing."""
    import ast
    import inspect

    import brain.ops.acceptance_checks_builder_choices as module

    failed: list[str] = []
    not_run: list[str] = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {
            "CheckFailedError",
            "CheckNotRunError",
        }:
            [argument] = node.args
            assert isinstance(argument, ast.Name)
            (failed if node.func.id == "CheckFailedError" else not_run).append(  # type: ignore[attr-defined]
                getattr(module, argument.id)
            )
    assert len(failed) == 4 and len(not_run) == 1
    assert all(0 < len(one) <= REASON_CHARS for one in (*failed, *not_run))


@pytest.mark.needs_db
def test_on_a_real_database_a_department_builder_is_offered_only_what_they_hold() -> None:
    """**The check as the worker runs it.** It passes over the install's own registry, and the
    people and grants it made are gone. Delete this and the cut can stop working on an install with
    nothing saying so."""
    with at_head("brain_acceptance_builder_choices") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _not_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes

    monkeypatch.setattr(routes, "limited_to_a_department", lambda reach, now: False)


def _everything_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes
    from brain.builder.choices import Choices

    def all_of_them(registry: Any, reach: Any, now: Any) -> Choices:
        names = tuple(sorted(registry.names()))
        return Choices(tools=names, connectors=tuple(sorted({n.split(".")[0] for n in names})))

    monkeypatch.setattr(routes, "held_choices", all_of_them)


def _nothing_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes
    from brain.builder.choices import Choices

    monkeypatch.setattr(routes, "held_choices", lambda *a: Choices(tools=(), connectors=()))


def _everybody_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes

    monkeypatch.setattr(routes, "limited_to_a_department", lambda reach, now: True)


BREAKS: dict[str, tuple[Any, str]] = {
    "not_limited": (_not_limited, "NOT_TOLD_WHY"),
    "everything_offered": (_everything_offered, "OFFERED_WHAT_IS_NOT_HELD"),
    "nothing_offered": (_nothing_offered, "NOT_OFFERED_WHAT_IS_HELD"),
    "everybody_limited": (_everybody_limited, "SUPER_ADMIN_CUT"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_builder_choices_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Four breaks, each putting the form back as it was or cutting it wrongly, each failing with
    its own sentence. Delete this and the check can pass with the form uncut, cut to nothing, or
    cut for the builder it must not cut."""
    import brain.ops.acceptance_checks_builder_choices as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_builder_choices_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
