"""Install acceptance checks for two rules retrieval keeps about what it hands an answer: a
reranking stage is adopted only when it earns its latency, and one fact held by two planes is one
result with both citations kept.

**Neither rule is a feature an install runs, so each is shown by asking the product's own function
and reading what it concludes.** The reranking leaf (M15.3.1) is an evaluation with a recorded
verdict, and the product ships no reranker: what an install can be asked is whether the decision
rule the owner asked for is the one the product applies, and whether the verdict it records is
one that rests on a measurement. The deduplication leaf (M15.3.3) is `brain.knowledge.assembly.
deduplicate`, which groups a caller's own results and drops nothing.

**Reranking: the rule is shown on five judged sets the check makes, and each answers differently.**
A set of twenty questions where a reranker lifts every relevant passage from fifth place to first,
inside the latency budget, is adopted. The same lift over the budget is not adopted and the
refusal names the latency. A reranker that changes nothing is not adopted however fast it is. A
set smaller than the product's own minimum is not measurable and is never adopted, which is the
direction the leaf asks the default to point. And a trial that reranks into a passage the
candidate set did not carry is refused outright, because the candidates came out of a query that
held the caller's reach and a stage able to add one could add one from outside it. See
`A_RERANKER_IS_ADOPTED_ONLY_BY_A_MEASURED_GAIN_INSIDE_ITS_BUDGET`.

**Reranking: the verdict the product records is read, and it must not be an adoption nobody
measured.** `brain.knowledge.quality.RERANKING` is the decision as it stands. The check fails if it
says adopted while the evaluation above has never been run over a set of the product's own: today
it says not measurable, on the absence of a judged set, with the falsifier written beside it.

**Deduplication: one fact in a row and in a passage is one result, and both stay.** A row and a
passage stating one claim come back as one group whose representative is the row, which holds the
passage as `also`, reports both planes and is corroborated. A result stating nothing comparable is
its own group and is never merged. Two results stating different facts are never one group, and
forcing them into one is refused by the group's own constructor. A result listed twice is refused,
because it would corroborate itself. Every result in is in exactly one group out, in the order of
each group's earliest member. See `A_DUPLICATE_LOSES_ITS_PLACE_ONLY_TO_A_RESULT_THE_CALLER_HOLDS`.

**What the second check does not show, and why its leaf is held.** `deduplicate` is not called on
an answer's path today: no answer draws on a row and a passage that state one claim, because
nothing links a passage to a record, so there is no claim for a passage to carry. The check is
the rule over results the check made, which is what a made-up pass is, so M15.3.3 is held in
`docs/proof-sweep-holds.json` until a source of claims exists and the groups are drawn on an
answer. Naming that plainly is the alternative to a green tick read as a wired feature.

Nothing here reads the install's data, writes a row or reaches a network, so both checks run
unchanged on an empty database and on the owner's.

Task ids: M15.3.1, M15.3.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1100

# ------------------------------------------------------------------ written-down reasons
#: Why the made-up sets are shaped as they are.
A_RERANKER_IS_ADOPTED_ONLY_BY_A_MEASURED_GAIN_INSIDE_ITS_BUDGET: Final = (
    "Reranking spends latency against an ordering gain, so the rule needs both halves: a gain "
    "past the product's threshold and an added latency inside its budget at the ninety-fifth "
    "percentile. A set too small to carry a verdict is never adopted, because the default "
    "direction in the absence of evidence is that nothing is switched on. The check makes sets "
    "that fail each half on its own, so a rule that read only one of them would adopt one."
)

#: Why the groups are read both ways.
A_DUPLICATE_LOSES_ITS_PLACE_ONLY_TO_A_RESULT_THE_CALLER_HOLDS: Final = (
    "Grouping the caller's own results is safe because a representative is always another result "
    "the caller is holding. The check asks that nothing is dropped, that nothing unrelated is "
    "merged and that one result listed twice is refused, since each is a way a fact is shown "
    "twice, lost without trace or made to corroborate itself."
)


# ------------------------------------------------------------------ the helpers
def _judged(count: int) -> tuple[tuple[object, ...], dict[str, tuple[str, ...]]]:
    """`count` judged cases, each with one relevant reference among ten candidates.

    The relevant reference is the fifth of the candidates as retrieval ordered them, so a stage
    that lifts it to first place has a large, unambiguous gain and one that leaves the order alone
    has none.
    """
    from brain.knowledge.quality import JudgedCase

    cases = []
    orders: dict[str, tuple[str, ...]] = {}
    for n in range(count):
        case_id = f"case-{n:03d}"
        refs = tuple(f"{case_id}-ref-{k}" for k in range(10))
        cases.append(JudgedCase(case_id=case_id, relevant=frozenset({refs[4]})))
        orders[case_id] = refs
    return tuple(cases), orders


def _trials(
    orders: dict[str, tuple[str, ...]], *, lift: bool, latency_ms: float
) -> tuple[object, ...]:
    """One trial per case: retrieval's order, and the order after the stage, at a stated cost.

    A lifting stage moves the fifth reference to the front and keeps everything else in the
    order it was in, which is a permutation of the candidates and so a legal reranking.
    """
    from brain.knowledge.quality import Trial

    out = []
    for case_id, refs in orders.items():
        reranked = (refs[4], *refs[:4], *refs[5:]) if lift else refs
        out.append(
            Trial(case_id=case_id, baseline=refs, candidate=reranked, added_latency_ms=latency_ms)
        )
    return tuple(out)


# ------------------------------------------------------- 1. reranking earns its latency (M15.3.1)
@check(
    leaves=("M15.3.1",),
    sentence=(
        "A reranking stage is adopted only when it improves the ordering past the product's "
        "threshold and adds no more than its latency budget at the 95th percentile; the same "
        "lift over budget, no lift and too small a set are not adopted, and the recorded "
        "verdict is not an unmeasured adoption."
    ),
)
async def a_reranker_is_adopted_only_when_it_earns_its_latency(h: Harness) -> None:
    from typing import Any, cast

    from brain.knowledge.quality import (
        MINIMUM_JUDGED_CASES,
        RERANK_BUDGET_MS,
        RERANKING,
        QualityError,
        Trial,
        Verdict,
        evaluate,
    )

    cases, orders = _judged(MINIMUM_JUDGED_CASES)
    judged = cast("Any", cases)

    earns = evaluate(judged, cast("Any", _trials(orders, lift=True, latency_ms=40.0)))
    if earns.verdict is not Verdict.ADOPTED:
        raise CheckFailedError(
            "a stage lifting every relevant passage to first place inside the budget was not "
            "adopted"
        )

    slow = evaluate(
        judged, cast("Any", _trials(orders, lift=True, latency_ms=RERANK_BUDGET_MS + 50.0))
    )
    if slow.verdict is not Verdict.NOT_ADOPTED or "budget" not in slow.because:
        raise CheckFailedError("a stage over the latency budget was adopted, or not told why")

    idle = evaluate(judged, cast("Any", _trials(orders, lift=False, latency_ms=1.0)))
    if idle.verdict is not Verdict.NOT_ADOPTED:
        raise CheckFailedError("a stage that changed nothing was adopted for being fast")

    few_cases, few_orders = _judged(MINIMUM_JUDGED_CASES - 1)
    few = evaluate(
        cast("Any", few_cases), cast("Any", _trials(few_orders, lift=True, latency_ms=1.0))
    )
    if few.verdict is not Verdict.NOT_MEASURABLE or few.verdict.adopted:
        raise CheckFailedError("a set too small to judge produced a verdict that could adopt")

    first = next(iter(orders))
    try:
        Trial(
            case_id=first,
            baseline=orders[first],
            candidate=(*orders[first], "a-passage-from-outside-the-reach"),
            added_latency_ms=1.0,
        )
    except QualityError:
        pass
    else:
        raise CheckFailedError("a stage that introduced a passage the candidates lacked was built")

    if RERANKING.verdict.adopted:
        raise CheckFailedError(
            "this install records reranking as adopted, and the evaluation of the product's "
            "own judged set is not what says so"
        )
    if not RERANKING.what_would_change_it.strip():
        raise CheckFailedError("the recorded verdict names nothing that would reverse it")


# ------------------------------------------------------- 2. one fact in two planes (M15.3.3)
@check(
    leaves=("M15.3.3",),
    sentence=(
        "A row and a passage stating one claim are one group, represented by the row, keeping the "
        "passage and naming both planes; a result stating nothing comparable stays alone, "
        "different facts are never merged, a result listed twice is refused, and none is lost."
    ),
)
async def one_fact_in_a_row_and_a_passage_is_one_result_and_both_are_kept(h: Harness) -> None:
    from brain.knowledge.assembly import (
        AssemblyError,
        Candidate,
        Claim,
        DuplicateGroup,
        Plane,
        deduplicate,
    )

    word = f"checkfact{h.run[:8]}"
    stated = Claim(entity="contract", record_id=f"rec-{word}", field="value", value=word)
    other = Claim(entity="contract", record_id=f"rec-{word}", field="value", value=f"{word}x")
    row = Candidate(plane=Plane.ROW, ref=f"rec-{word}", position=3, claim=stated)
    passage = Candidate(plane=Plane.DOCUMENT, ref=f"doc-{word}.c2", position=1, claim=stated)
    unlinked = Candidate(plane=Plane.DOCUMENT, ref=f"doc-{word}.c9", position=2)
    different = Candidate(plane=Plane.ROW, ref=f"rec-{word}-b", position=1, claim=other)

    groups = deduplicate([passage, unlinked, row, different])
    held = [one.ref for g in groups for one in g.members]
    if sorted(held) != sorted(c.ref for c in (passage, unlinked, row, different)):
        raise CheckFailedError("a result was lost or shown twice by the grouping")
    if len(groups) != 3:
        raise CheckFailedError("one fact in two planes was not one group, or two facts were merged")
    first = groups[0]
    if first.kept != row or first.also != (passage,):
        raise CheckFailedError("the row did not represent the fact, or the passage was dropped")
    if first.planes != ("document", "row") or not first.corroborated:
        raise CheckFailedError("a fact found by both planes was not reported as corroborated")
    if groups[1].kept != unlinked or groups[1].also:
        raise CheckFailedError("a result stating nothing comparable was merged into another")
    if groups[2].kept != different:
        raise CheckFailedError("a different fact was merged with this one, or the order moved")

    try:
        DuplicateGroup(kept=row, also=(different,))
    except AssemblyError:
        pass
    else:
        raise CheckFailedError("two different facts were accepted as one group")
    try:
        deduplicate([row, row])
    except AssemblyError:
        pass
    else:
        raise CheckFailedError("one result listed twice was accepted, and would corroborate itself")
