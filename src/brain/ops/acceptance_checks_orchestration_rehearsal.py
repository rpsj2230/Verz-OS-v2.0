"""Install checks for weighing a multi-agent plan: the fan-out gate decides and keeps its decision,
and what subtasks return is checked against what each promised and merged with a stated gap.

Every check calls the route the console calls, as the reader that page serves, in the shape
`brain.ops.acceptance_operations_console` sets out (`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`): an
application holding the check's sessions, and the asking the gate would hand the route for a
reserved administrator on the console, with a second factor.

**What is proved is the deterministic half of an orchestrator, over a written-down plan.**
No agent is started and no model is asked, because no coordinating agent exists (M18.5). The plans
are made up for the check: four independent subtasks that the gate splits, and a chain it keeps as
one loop, so both verdicts are seen and neither is assumed. The decision the route keeps is read
back from `ops.fanout_gate` as the migration built it.

**The switch is set in both directions and never assumed.** An install that already has
`orchestration_rehearsal` on is not the empty state, so the check turns it off through the Features
route, shows a plan refused, and turns it on.

**Not claimed:** M18.2.4 asks for the record to be shown "on the run's page", and a rehearsal has
no run page, so the check reads the decisions list the Features page draws. A person looking at
the page is the proof of the page; this is the proof of the record.

Task ids: M18.1.3, M18.2.1, M18.2.2, M18.2.3, M18.2.4, M18.4.1, M18.4.2, M18.4.3
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    traced,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2240

A, _B = RESERVED_DEPARTMENTS

#: The authorities the check's administrator holds. Restated rather than imported, so a change to a
#: route's authority fails its check instead of moving with it.
WEIGHS_PLANS: Final = "admin:agent_lifecycle"
SWITCHES_FEATURES: Final = "admin:feature"

#: The six conditions the gate evaluates, in the order it evaluates them. Restated so a seventh, or
#: a renamed one, fails here and not silently.
THE_SIX: Final = (
    "enough_branches",
    "within_run_concurrency",
    "within_depth",
    "cost_multiplier_bounded",
    "speedup_worth_it",
    "no_branch_dominates",
)

SHOWN_TO_ANYBODY: Final = "a person without the authority over agents was shown the gate"
WEIGHED_WITH_THE_SWITCH_OFF: Final = "a plan was weighed while weighing was switched off"
A_SPLIT_PLAN_WAS_KEPT_AS_ONE: Final = "four independent subtasks were not split across agents"
A_PARALLEL_VERDICT_SKIPPED_A_CONDITION: Final = "a plan was split without all six conditions"
A_CHAIN_WAS_SPLIT: Final = "a plan with nothing to run at once was split across agents"
THE_FAILURE_WAS_NOT_NAMED: Final = "a plan kept as one loop did not say which condition it failed"
A_DECISION_WAS_NOT_KEPT: Final = "the decision the gate made was not in the table that keeps it"
THE_RECORD_HELD_MORE_THAN_NUMBERS: Final = "the kept decision named something other than numbers"
A_BAD_PLAN_WAS_WEIGHED: Final = "a plan that depends on a subtask it does not hold was weighed"
A_REFUSED_PLAN_WAS_KEPT: Final = "a refused plan left a decision behind"
AN_INVALID_RESULT_WAS_MERGED: Final = "a result that broke its contract was merged as an input"
A_GAP_WAS_NOT_STATED: Final = "an answer missing a subtask did not say it was missing something"
A_COMPLETE_ANSWER_SAID_IT_WAS_MISSING_SOMETHING: Final = (
    "an answer from subtasks that all returned said it was incomplete"
)
THE_TOTAL_WAS_NOT_THE_ROWS: Final = "the run's cost was not the sum of its subtasks' costs"
A_COST_WAS_NOT_SHOWN: Final = "a subtask that returned was shown with no cost"
AN_UNKNOWN_RESULT_WAS_ACCEPTED: Final = "a result for a subtask the plan does not hold was merged"


def _subtask(name: str, *, depends_on: tuple[str, ...] = (), **more: Any) -> dict[str, Any]:
    """One subtask of the plans these checks write: two promised fields and a size."""
    return {
        "subtask_id": name,
        "objective": f"Find what {name} knows about the made-up company",
        "depends_on": list(depends_on),
        "output": [{"name": "ref", "kind": "identifier"}, {"name": "count", "kind": "integer"}],
        "tier": "main",
        "tool_calls": 1,
        "retrieval_tokens": 2000,
        "seconds": 10.0,
        **more,
    }


def _split_plan(**more: Any) -> dict[str, Any]:
    """Four independent, equal subtasks: more than one at once, nothing dominating, and a speedup
    of four, which the gate splits."""
    return {"depth": 0, "subtasks": [_subtask(f"part_{n}") for n in "abcd"], **more}


def _chain_plan() -> dict[str, Any]:
    """One after another: nothing can start at once, so the gate keeps it as a single loop."""
    return {
        "depth": 0,
        "subtasks": [
            _subtask("first"),
            _subtask("second", depends_on=("first",)),
            _subtask("third", depends_on=("second",)),
        ],
        "coupling": [
            {"before": "first", "after": "second", "tokens": 100},
            {"before": "second", "after": "third", "tokens": 100},
        ],
    }


async def _administrator(h: Harness) -> str:
    made = h.principal(A, "orchestration")
    await h.person(
        made,
        department=A,
        grants=(
            (WEIGHS_PLANS, Scope.unrestricted()),
            (SWITCHES_FEATURES, Scope.unrestricted()),
        ),
    )
    return made


async def _switched(h: Harness, administrator: str, *, on: bool, n: int) -> None:
    """The weighing switch, through the Features route, as the administrator presses it."""
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.ops.features import ORCHESTRATION_REHEARSAL

    async with traced(h, n):
        await switch_feature(
            console_for(h).request("POST"),
            ORCHESTRATION_REHEARSAL.name,
            SwitchAsked(on=on),
            await asking_as(h, administrator, strong=True),
        )


async def _weigh(h: Harness, who: str, plan: dict[str, Any]) -> Any:
    from brain.orchestration_routes import RehearsalAsked, rehearse

    return await rehearse(
        console_for(h).request("POST"),
        RehearsalAsked.model_validate(plan),
        await asking_as(h, who, strong=True),
    )


async def _kept(h: Harness, run_id: str) -> int:
    return int(
        (
            await h.execute(
                text("SELECT count(*) FROM ops.fanout_gate WHERE run_id = :run").bindparams(
                    run=run_id
                )
            )
        ).scalar_one()
    )


# --------------------------------------- 1. the gate decides and keeps it (M18.2.1 to M18.2.4)
@check(
    leaves=("M18.2.1", "M18.2.2", "M18.2.3", "M18.2.4"),
    sentence=(
        "A plan of four independent subtasks, weighed by the console's route, is split across "
        "agents after all six conditions are evaluated; a chain of three is kept as one loop and "
        "names the condition it failed; each decision is kept and listed with who asked; a plan "
        "depending on a subtask it lacks, or weighed while the switch is off, keeps nothing."
    ),
)
async def the_gate_splits_a_plan_or_keeps_one_loop_and_keeps_its_decision(h: Harness) -> None:
    from brain.orchestration_routes import decisions

    await h.found_departments()
    admin, other = await _administrator(h), h.principal(A, "other")
    await h.person(other, department=A)
    console = console_for(h)
    if not await refused(decisions(console.request(), await asking_as(h, other))):
        raise CheckFailedError(SHOWN_TO_ANYBODY)
    if not await refused(_weigh(h, other, _split_plan())):
        raise CheckFailedError(SHOWN_TO_ANYBODY)

    await _switched(h, admin, on=False, n=1)
    if not await refused(_weigh(h, admin, _split_plan())):
        raise CheckFailedError(WEIGHED_WITH_THE_SWITCH_OFF)
    await _switched(h, admin, on=True, n=2)

    split = await _weigh(h, admin, _split_plan())
    if split.gate.verdict != "parallel":
        raise CheckFailedError(A_SPLIT_PLAN_WAS_KEPT_AS_ONE)
    if split.gate.failed or tuple(split.gate.evaluated) != THE_SIX:
        raise CheckFailedError(A_PARALLEL_VERDICT_SKIPPED_A_CONDITION)

    chain = await _weigh(h, admin, _chain_plan())
    if chain.gate.verdict != "single_loop":
        raise CheckFailedError(A_CHAIN_WAS_SPLIT)
    if "enough_branches" not in chain.gate.failed or tuple(chain.gate.evaluated) != THE_SIX:
        raise CheckFailedError(THE_FAILURE_WAS_NOT_NAMED)

    if await _kept(h, split.run_id) != 1 or await _kept(h, chain.run_id) != 1:
        raise CheckFailedError(A_DECISION_WAS_NOT_KEPT)
    listed = {
        one.run_id: one
        for one in (
            await decisions(console.request(), await asking_as(h, admin, strong=True))
        ).decisions
    }
    if (
        listed.get(split.run_id) is None
        or listed[split.run_id].verdict != "parallel"
        or listed[split.run_id].decided_by != admin
        or listed.get(chain.run_id) is None
    ):
        raise CheckFailedError(A_DECISION_WAS_NOT_KEPT)
    held = (
        await h.execute(
            text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = 'ops' AND table_name = 'fanout_gate'"
            )
        )
    ).scalars()
    if any(word in str(name) for name in held for word in ("objective", "subtask", "question")):
        raise CheckFailedError(THE_RECORD_HELD_MORE_THAN_NUMBERS)

    before = int((await h.execute(text("SELECT count(*) FROM ops.fanout_gate"))).scalar_one())
    broken = _chain_plan()
    broken["subtasks"][1]["depends_on"] = ["a_subtask_the_plan_lacks"]
    if not await refused(_weigh(h, admin, broken)):
        raise CheckFailedError(A_BAD_PLAN_WAS_WEIGHED)
    if int((await h.execute(text("SELECT count(*) FROM ops.fanout_gate"))).scalar_one()) != before:
        raise CheckFailedError(A_REFUSED_PLAN_WAS_KEPT)


# ----------------------------------------- 2. results are checked and merged (M18.1.3, M18.4)
@check(
    leaves=("M18.1.3", "M18.4.1", "M18.4.2", "M18.4.3"),
    sentence=(
        "Of four subtasks handed results, three keep their promise and one returns a number as "
        "text: the merge holds the three, states the fourth as missing in words, shows each "
        "subtask's cost and duration with a total that is the sum of the rows, and a run where "
        "all four keep their promise is complete and says nothing is missing."
    ),
)
async def results_are_checked_and_merged_with_a_stated_gap(
    h: Harness,
) -> None:
    await h.found_departments()
    admin = await _administrator(h)
    await _switched(h, admin, on=True, n=3)

    def returned(name: str, count: object, minor: int) -> dict[str, Any]:
        return {
            "subtask_id": name,
            "values": {"ref": f"ref_{name}", "count": count},
            "minor": minor,
            "seconds": 2.0,
        }

    fine = _split_plan(
        returned=[returned(f"part_{n}", 3, 4 + index) for index, n in enumerate("abcd")]
    )
    whole = await _weigh(h, admin, fine)
    if whole.merged is None or not whole.merged.complete or whole.merged.notice:
        raise CheckFailedError(A_COMPLETE_ANSWER_SAID_IT_WAS_MISSING_SOMETHING)
    if sorted(whole.merged.values) != sorted(f"part_{n}" for n in "abcd"):
        raise CheckFailedError(A_GAP_WAS_NOT_STATED)

    partial = _split_plan(
        returned=[
            returned("part_a", 3, 4),
            returned("part_b", 3, 5),
            returned("part_c", 3, 6),
            returned("part_d", "three", 7),
        ]
    )
    answer = await _weigh(h, admin, partial)
    merged = answer.merged
    if merged is None or "part_d" in merged.values:
        raise CheckFailedError(AN_INVALID_RESULT_WAS_MERGED)
    if merged.complete or "part_d" not in merged.notice:
        raise CheckFailedError(A_GAP_WAS_NOT_STATED)
    if sorted(one.subtask_id for one in merged.reports) != sorted(f"part_{n}" for n in "abcd"):
        raise CheckFailedError(A_COST_WAS_NOT_SHOWN)
    if merged.total_minor != sum(one.minor for one in merged.reports) or merged.total_minor != 22:
        raise CheckFailedError(THE_TOTAL_WAS_NOT_THE_ROWS)

    strange = _split_plan(returned=[returned("part_z", 3, 1)])
    if not await refused(_weigh(h, admin, strange)):
        raise CheckFailedError(AN_UNKNOWN_RESULT_WAS_ACCEPTED)
