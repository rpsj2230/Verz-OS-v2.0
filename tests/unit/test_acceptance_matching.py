"""The online cascade's acceptance checks: registered, passing on a real schema, and able to fail.

Task ids: M14.2.5, M14.3.2, M14.3.3, M14.3.4, M14.3.6, M14.3.7, M14.3.8, M14.5.6, M14.6.2
Task ids: M14.6.3
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_matching"
NAMES = "a_corroborated_name_is_matched_and_scored_in_the_database"
CLOSE = "close_names_match_at_stage_three_and_bare_names_go_to_a_person"
SHORT = "a_name_too_short_to_measure_goes_to_a_person"
FREE_MAIL = "a_free_mail_domain_joins_nothing"
MONEY = "a_match_across_the_money_boundary_waits_for_a_person"
HARD = "a_hard_match_merges_only_within_its_caps_and_without_a_tie"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_matching_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in page order. Delete this and a check can drop out of
    the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [NAMES, CLOSE, SHORT, FREE_MAIL, MONEY, HARD]
    assert MODULE in check_modules()


@pytest.mark.needs_db
def test_on_a_real_database_the_matching_checks_pass_and_nothing_is_left_behind() -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Delete this and the
    cascade can stop comparing records with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_matching") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == dict.fromkeys((NAMES, CLOSE, SHORT, FREE_MAIL, MONEY, HARD), (PASSED, ""))
    assert after == before


def broken_and_run(monkeypatch: pytest.MonkeyPatch, name: str, label: str, setup: Any) -> Any:
    """Apply one break, run one check against PostgreSQL at head, and return its outcome."""
    setup(monkeypatch)
    with at_head(f"brain_acceptance_matching_{label}") as url:
        outcome = run_checks(url, (mine()[name],))
    return outcome[name]


def _without_stage(stage_name: str) -> Any:
    def setup(monkeypatch: pytest.MonkeyPatch) -> None:
        import brain.resolution.matching_store as store
        from brain.resolution.cascade import Stage
        from brain.resolution.entities import profile_for

        def narrower(entity_type: Any) -> Any:
            kept = profile_for(entity_type)
            return dataclasses.replace(
                kept, auto_merge_stages=kept.auto_merge_stages - {Stage[stage_name]}
            )

        monkeypatch.setattr(store, "profile_for", narrower)

    return setup


def _sql_weights_doubled(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.query as query

    kept = query.weight_parameters
    monkeypatch.setattr(
        query, "weight_parameters", lambda *a: {k: v * 2 for k, v in kept(*a).items()}
    )


def _phonetic_heavy(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.matching_store as store
    from brain.resolution.cascade import DECLARED_WEIGHTS, Feature, WeightTable
    from brain.resolution.entities import resolve_pair

    heavy = WeightTable(
        version="heavy",
        weights={**DECLARED_WEIGHTS.weights, Feature.NAME_PHONETIC: 20.0},
    )
    monkeypatch.setattr(
        store,
        "resolve_pair",
        lambda left, right, profile: resolve_pair(left, right, profile, weights=heavy),
    )


def _questions_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.matching_store as store
    from brain.resolution.cascade import CascadeResult, Decision, Stage
    from brain.resolution.entities import resolve_pair

    def no_band(left: Any, right: Any, profile: Any) -> Any:
        result = resolve_pair(left, right, profile)
        if result.decision is not Decision.TO_REVIEW:
            return result
        return CascadeResult(
            decision=Decision.NOT_MATCHED,
            stage=Stage.HUMAN_REVIEW,
            left=result.left,
            right=result.right,
            evidence=result.evidence,
            reason="dropped",
        )

    monkeypatch.setattr(store, "resolve_pair", no_band)


def _short_names_usable(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.normalise as normalise

    monkeypatch.setattr(normalise, "MIN_KEY_CHARS", 2)


def _free_mail_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.cascade as cascade

    monkeypatch.setattr(cascade, "FREE_MAIL_DOMAINS", frozenset())


def _money_unread(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.matching_store as store
    from brain.resolution.merge import MoneyBearing

    monkeypatch.setattr(
        store, "money_of", lambda members, declared: MoneyBearing.NO_FINANCIAL_RECORDS_FOUND
    )


def _switch_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.merge_store as merge_store

    async def always(session: Any, one: Any) -> bool:
        return True

    monkeypatch.setattr(merge_store, "is_on", always)


def _caps_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.matching_store as store

    monkeypatch.setattr(store, "cap_breaches", lambda *args: ())


def _first_claim_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.matching_store as store
    from brain.resolution.guardrails import Collision, CollisionOutcome

    def first(claims: Any) -> Any:
        return Collision(
            outcome=CollisionOutcome.DECIDED,
            entity_id=claims[0].entity_id,
            deciding_kind=claims[0].kind,
            reason="first",
        )

    monkeypatch.setattr(store, "resolve_collision", first)


BREAKS: dict[str, tuple[str, Any, str]] = {
    "stage_two_withheld": (NAMES, _without_stage("CORROBORATED_NAME"), "NOT_MATCHED_ON_NAMES"),
    "sql_weights_doubled": (NAMES, _sql_weights_doubled, "NOT_SCORED_IN_SQL"),
    "stage_three_withheld": (CLOSE, _without_stage("SIMILARITY"), "NOT_STAGE_THREE"),
    "phonetic_heavy": (CLOSE, _phonetic_heavy, "PHONETIC_NOT_LOW"),
    "questions_dropped": (CLOSE, _questions_dropped, "NO_QUESTION"),
    "short_names_usable": (SHORT, _short_names_usable, "SHORT_NAME_MATCHED"),
    "free_mail_kept": (FREE_MAIL, _free_mail_kept, "FREE_MAIL_JOINED"),
    "money_unread": (MONEY, _money_unread, "MONEY_NOT_HELD"),
    "switch_ignored": (HARD, _switch_ignored, "MERGED_WHILE_OFF"),
    "caps_ignored": (HARD, _caps_ignored, "CAP_NOT_HELD"),
    "first_claim_wins": (HARD, _first_claim_wins, "COLLISION_NOT_HELD"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_each_matching_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing its check with its own sentence: a corroborated name
    not matched, a database score that is not the cascade's sum (M14.3.2, M14.3.6); a near name
    not matched at stage three, a phonetic agreement weighted heavily, a bare name never put to a
    person (M14.3.3, M14.3.8, M14.3.4); a short name measured (M14.2.5); a mail provider's
    domain kept (M14.3.7); the money boundary unread (M14.5.6); the switch ignored, a cap
    ignored and a tie broken by whoever came first (M14.6.2, M14.6.3). Delete this and any of
    these checks can pass with its property gone."""
    import brain.ops.acceptance_checks_matching as module

    name, setup, reason = BREAKS[broken]
    assert broken_and_run(monkeypatch, name, broken, setup) == (FAILED, getattr(module, reason))
