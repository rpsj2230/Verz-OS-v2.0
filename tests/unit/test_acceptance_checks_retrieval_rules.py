"""The retrieval-rule install checks: registered, passing at head, and able to fail.

Neither check reads the install's data or writes a row, so each runs here against a stub harness,
passes, and is then shown failing with the product's rule broken in the way that would matter: a
latency budget nobody applies, a gain threshold nobody applies, an adoption recorded with nothing
behind it, a grouping that drops the passage, and a grouping that merges what states nothing.

Task ids: M15.3.1, M15.3.3
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from brain.ops import acceptance_checks_retrieval_rules as module
from brain.ops.acceptance import CheckFailedError, registered
from tests.unit.test_acceptance import checks_in

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_retrieval_rules"

RERANK = "a_reranker_is_adopted_only_when_it_earns_its_latency"
DEDUPLICATE = "one_fact_in_a_row_and_a_passage_is_one_result_and_both_are_kept"

LEAVES = {RERANK: ("M15.3.1",), DEDUPLICATE: ("M15.3.3",)}


def body(name: str) -> Any:
    return next(one for one in registered((MODULE,)) if one.name == name).run


def run(name: str) -> None:
    asyncio.run(body(name)(SimpleNamespace(run="abc123def456")))


def test_the_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Delete this and a check can be given a leaf it does not show, or lose its own, and the
    proof sweep closes or leaves open the wrong task with the suite green."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == LEAVES
    assert checks_in(MODULE) == list(LEAVES)
    assert 1100 <= module.CHECK_ORDER <= 1199


def test_only_the_leaf_whose_pass_is_over_something_made_up_is_held() -> None:
    """Deduplication is shown over results the check made, because nothing on an answer's path
    links a passage to a record, so M15.3.3 is held and says why. The reranking rule is the
    product's own decision function and is not. Delete this and a pass over made-up results closes
    a leaf as though an answer were drawing on both planes, or the reranking leaf is held for
    ever for a pass that is not made up."""
    held = json.loads((ROOT / "docs" / "proof-sweep-holds.json").read_text())["held"]
    assert held.get("M15.3.3", "").strip()
    assert "M15.3.1" not in held


def test_both_checks_pass_on_the_product_as_it_stands() -> None:
    """The positive case. Delete this and a check that refuses everything passes every
    refusal test below."""
    run(RERANK)
    run(DEDUPLICATE)


def test_the_reranking_check_fails_where_the_latency_budget_is_not_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The evaluation told to accept any added latency, the half of the rule that is easiest to
    drop because the gain is what somebody is proud of. Delete this and a stage three seconds
    slower is adopted with the check green."""
    from brain.knowledge import quality

    real = quality.evaluate
    monkeypatch.setattr(
        quality, "evaluate", lambda cases, trials: real(cases, trials, budget_ms=10.0**9)
    )
    with pytest.raises(CheckFailedError, match="latency budget"):
        run(RERANK)


def test_the_reranking_check_fails_where_no_gain_is_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The evaluation told that any ordering, including the same one, is a gain. Delete this and
    a stage that changes nothing is adopted for being fast."""
    from brain.knowledge import quality

    real = quality.evaluate
    monkeypatch.setattr(
        quality, "evaluate", lambda cases, trials: real(cases, trials, minimum_gain=-1.0)
    )
    with pytest.raises(CheckFailedError, match="changed nothing"):
        run(RERANK)


def test_the_reranking_check_fails_where_an_unmeasured_adoption_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorded verdict switched to adopted with its old reason, which is what somebody who
    'knows reranking helps' would write. Delete this and the install records an adoption no
    judged set supports."""
    from datetime import date

    from brain.knowledge import quality

    monkeypatch.setattr(
        quality,
        "RERANKING",
        quality.AdoptionRecord(
            decided_on=date(2999, 1, 1),
            verdict=quality.Verdict.ADOPTED,
            because="it should help",
            what_would_change_it="nothing",
        ),
    )
    with pytest.raises(CheckFailedError, match="adopted"):
        run(RERANK)


def test_the_deduplication_check_fails_where_the_passage_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A grouping that keeps the row and discards the passage, which is the cheaper rule and
    loses the citation. Delete this and every fact the row plane also holds loses its passage."""
    from brain.knowledge import assembly

    real = assembly.deduplicate

    def dropping(candidates: Any) -> Any:
        return tuple(assembly.DuplicateGroup(kept=g.kept) for g in real(candidates))

    monkeypatch.setattr(assembly, "deduplicate", dropping)
    with pytest.raises(CheckFailedError):
        run(DEDUPLICATE)


def test_the_deduplication_check_fails_where_a_result_stating_nothing_is_merged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every candidate put in one group, which is what a grouping on a missing claim does when
    two missing claims compare equal. Delete this and unrelated passages collapse into one."""
    from brain.knowledge import assembly

    def merging(candidates: Any) -> Any:
        everything = tuple(candidates)
        return (assembly.DuplicateGroup(kept=everything[0], also=()),) if everything else ()

    monkeypatch.setattr(assembly, "deduplicate", merging)
    with pytest.raises(CheckFailedError):
        run(DEDUPLICATE)
