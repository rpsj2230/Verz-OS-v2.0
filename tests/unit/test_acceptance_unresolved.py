"""The ambiguous name's acceptance check: registered, passing on a real schema, and able to fail.

Task ids: M14.6.5
"""

from __future__ import annotations

from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_unresolved"
NAMED = "a_shared_name_is_named_and_a_withheld_record_changes_nothing"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_unresolved_name_check_is_listed() -> None:
    """The one check this module registers. Delete this and it can drop out of the page."""
    assert checks_in(MODULE) == [NAMED]
    assert MODULE in check_modules()


@pytest.mark.needs_db
def test_on_a_real_database_the_unresolved_name_check_passes_and_leaves_nothing() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** Delete this and an
    ambiguous name can go back to being guessed at with nothing on the owner's install saying
    so."""
    with at_head("brain_acceptance_unresolved") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {NAMED: (PASSED, "")}
    assert after == before


def _reads_past_the_row_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """A lane that reads every row whatever the asker's department, so a withheld record is held."""
    import brain.gate.fast_lane as lane
    from brain.core.entitlement import EntitlementSet, Grant
    from brain.core.scope import Scope

    original = lane._read

    async def wide(match: Any, readers: Any, *, entitlement: Any, now: Any) -> Any:
        everything = EntitlementSet(
            principal_id=entitlement.principal_id,
            grants=tuple(
                Grant(capability=one.capability, scope=Scope.unrestricted())
                for one in entitlement.grants
            ),
        )
        return await original(match, readers, entitlement=everything, now=now)

    monkeypatch.setattr(lane, "_read", wide)


def _no_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.api_routes as routes

    monkeypatch.setattr(routes, "ambiguity_of", lambda state: None)


def _link_for_anybody(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.gate.answer as answer
    from brain.resolution.guardrails import UNRESOLVED_TEXT, UnresolvedNotice

    def anybody(found: Any, *, entitlement: Any, now: Any) -> str:
        if found.review_ref is None:
            return UNRESOLVED_TEXT
        return UnresolvedNotice(review_ref=found.review_ref).render()

    monkeypatch.setattr(answer, "unresolved_text", anybody)


def _no_review_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.resolution.ambiguity_store import StoredAmbiguity

    async def none(self: Any, entity_ids: Any) -> None:
        return None

    monkeypatch.setattr(StoredAmbiguity, "open_review", none)


BREAKS: dict[str, tuple[Any, str]] = {
    "reads_past_the_row_scope": (_reads_past_the_row_scope, "WITHHELD_RECORD_TOLD"),
    "no_registry": (_no_registry, "NOT_NAMED_AMBIGUOUS"),
    "link_for_anybody": (_link_for_anybody, "LINK_TO_A_NON_REVIEWER"),
    "no_review_found": (_no_review_found, "REVIEWER_NOT_LINKED"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_unresolved_name_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: a lane that reads
    a record past the asker's reach, a route that hands the lane no registry, a link shown to
    anybody, and a reviewer given no link. Delete this and the check can pass with any of those
    properties gone."""
    import brain.ops.acceptance_checks_unresolved as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_unresolved_{broken}") as url:
        outcome = run_checks(url, (mine()[NAMED],))
    assert outcome[NAMED] == (FAILED, getattr(module, reason))
