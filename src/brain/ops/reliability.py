"""What breaks, what may be retried, and the numbers this system promises about both.

Three questions that are usually three documents, here because they are one argument. A
failure-mode matrix that does not say what may be retried is a list of symptoms. An
operation classification with no service level behind it is a taxonomy nobody consults. And
a service level objective with no failure modes under it is a number somebody wrote down.

**Every figure in this module is a default and the next company may need a different one.**
That is not a caveat, it is the design constraint: this repository is the product and Verz
is the first install, so a latency target chosen for one company and compiled into a module
is the template's central failure mode. Every check below takes its policy as a parameter
and defaults to the declaration, so a client's own figures go through the same arithmetic
rather than round the outside of it. See
`EVERY_NUMBER_HERE_IS_A_STARTING_POSITION_AND_NOT_A_REQUIREMENT`.

**The lane figures are copies and the copying is the point.** `brain.ops.admission.
LOAD_TEST_TARGET` already states the service levels the architecture asks for, as prose,
inside a load-test specification. Writing them again here as integers looks like duplication
and is what makes them checkable: `tests/unit/test_reliability.py` parses the numbers out of
that sentence and holds them equal, so neither can move alone. It is the construction
`ops/seaweedfs/provision.sh` uses against `brain.ops.storage.BUCKETS`, for the same reason.

**A refusal is a successful request, and getting that wrong turns the dashboard into a
hidden item count.** The whole system rests on DENIED and ABSENT being indistinguishable. A
success rate that counted `NOTHING_RETURNED` as a failure would show a lower number for a
person with less reach than for their manager, on a screen neither of them controls, and the
difference is exactly the count of things they were not allowed to see. So
`SUCCESS_STATUSES` includes it, and that is a permission decision wearing an availability
decision's clothes. See
`A_REFUSAL_IS_A_SUCCESSFUL_REQUEST_OR_THE_DASHBOARD_COUNTS_WHAT_A_READER_MAY_NOT_SEE`.

**The stage budgets partition the fast lane's target exactly rather than fitting inside it.**
`stage_budget_gaps` reports a sum that is not equal to `FAST_P95_MS`, not one that is over
it. A budget with slack is a budget where every stage can be raised a little and the sum
still passes, which is how nine stages each grow by thirty milliseconds and the lane misses
its target with every component inside its own allocation. Raising one stage has to mean
lowering another, and the check is what makes that true.

**None of the latency objectives can be measured today, and one of them can.** The metadata
ledger carries `received_at` and no completion time, so there is no duration in it to take a
percentile of, and `time_to_first_token_ms` is in `brain.ops.telemetry.UNFILLABLE_TODAY`
because nothing calls a model. It does carry `status`, with no default, on every row. So the
success-rate half of every objective is measurable from the ledger now and the latency half
is not measurable at all, and `measurement_gaps` derives that from telemetry's own
declarations rather than restating them. M30.5.2 is not claimed: what it needs is one field.

**The failure-mode matrix declares what an outage blocks because nothing can derive it.**
`brain.ops.wiring.COMPONENTS` is the component register and it carries a memory limit, a
profile set, a database wiring and a readiness sentence, and no edge to any other component.
So "the object store is down, what stops working" has no answer in this repository that is
not prose somebody wrote. `blocks` is that prose, `matrix_gaps` holds it to naming real
components, and the alternative is worse than the duplication: a dependency graph invented
here would be a second declaration of the deployment, disagreeing with the compose files
that actually wire it. See
`A_COMPONENT_REGISTER_WITH_NO_EDGES_CANNOT_SAY_WHAT_AN_OUTAGE_BLOCKS`.

**The matrix covers more components than the register does, and that gap is a finding.**
`COMPONENTS` is wave two: workers, the object store, the identity provider, the trace stack.
The four services in `docker-compose.yml` that every install actually runs, the application,
the pooler, the database and the cache, are not in it, because `wiring.PRODUCTION_BASELINE_MIB`
costs them as a single number instead. A matrix built from `COMPONENTS` alone would omit
the database, so `BASELINE_COMPONENTS` names them and a test asserts them against the
compose file rather than against this list.

**This module classifies an operation, not an outcome and not a record.**
`brain.connectors.throttle.is_retryable` answers whether a particular call outcome is worth
another go, and `brain.ops.idempotency.Disposition` answers what a recovering worker does
with a record it found after a crash. `RetryClass` answers a third question, asked before
either: what may ever be done twice. A read is safe to repeat in every state; a message sent
to a person is unsafe in every state; and the reason the vocabularies must stay separate is
that conflating them is how somebody retries an `UNKNOWN` side effect. See
`THIS_CLASSIFIES_THE_OPERATION_AND_NOT_THE_OUTCOME_OR_THE_RECORD`.

Rejected: deriving the stage vocabulary from the module names in `src/brain/gate/`. There
are twenty-two files there and they are a package layout rather than a pipeline, so the
derivation would produce `cache_key` and `rule_store` as stages. The nine members below are
the nine task groups of M3, which is the decomposition the work was planned against, and a
test holds the count against `docs/wbs.json` so a tenth group has to be classified rather
than silently falling outside.

Rejected: an SLO type with a generic `target` float and a `unit` string. It types every
objective the same and makes the one distinction that matters unrepresentable, which is that
the task lane has a success rate and deliberately no latency percentile: nobody is waiting,
so a percentile there is an instrument measuring the wrong thing precisely.

Scope: domain logic and declarations. Nothing here reads a clock, a metric, a compose file
or an environment.

Task ids: M30.4.1, M30.4.2, M30.5.1
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from brain.core.lane import Lane
from brain.ops.telemetry import TELEMETRY_FIELDS, UNFILLABLE_TODAY, RequestStatus
from brain.ops.wiring import COMPONENTS, PROFILES, assert_known_profile

# ----------------------------------------------------------------- written-down reasons
#: Why nothing here is a requirement.
EVERY_NUMBER_HERE_IS_A_STARTING_POSITION_AND_NOT_A_REQUIREMENT: Final = (
    "This repository is the product and the first install is one company. A service level "
    "written for that company and compiled into a module is right once and wrong for "
    "everybody after, and it is wrong invisibly, because a number in source looks like a "
    "fact. So every check takes its objectives as a parameter and defaults to these, which "
    "means a client who sets their own figures gets the same arithmetic applied to them "
    "rather than a check that quietly stops describing their install."
)

#: Why a refused request counts as a success.
A_REFUSAL_IS_A_SUCCESSFUL_REQUEST_OR_THE_DASHBOARD_COUNTS_WHAT_A_READER_MAY_NOT_SEE: Final = (
    "DENIED and ABSENT are one status in the ledger precisely so that nobody can count the "
    "difference. A success rate that treated NOTHING_RETURNED as a failure would put that "
    "count back: a person with narrow reach would show a lower availability figure than "
    "their manager for the same traffic, and the gap between the two numbers is the number "
    "of things they were refused. The system did its job on every one of those requests. "
    "It answered the question it was allowed to answer, which is what availability means "
    "here."
)

#: Why the stage budgets are a partition rather than a ceiling.
A_BUDGET_WITH_SLACK_IS_A_BUDGET_EVERY_STAGE_GROWS_INTO: Final = (
    "Nine stage budgets summing to less than the lane target means every one of them can be "
    "raised and the sum still passes, so each change is locally reasonable and the lane "
    "misses its objective with every component inside its own allocation and nobody at "
    "fault. Requiring the sum to equal the target makes the trade explicit: a stage that "
    "needs more milliseconds has to take them from a named neighbour, in the same diff, in "
    "front of the same reviewer."
)

#: Why `blocks` is declared prose rather than computed.
A_COMPONENT_REGISTER_WITH_NO_EDGES_CANNOT_SAY_WHAT_AN_OUTAGE_BLOCKS: Final = (
    "brain.ops.wiring.COMPONENTS declares a memory limit, a profile set, how a component "
    "reaches Postgres and what ready means for it. It declares no dependency on any other "
    "component, so there is no graph here to walk and the question an operator asks first, "
    "what stops working, has no computed answer. Inventing the graph in this module would "
    "put a second description of the deployment beside the compose files that actually "
    "wire it, and the two would disagree the first time a service moved. So the answer is "
    "written down, and what is checked is that it names components that exist."
)

#: Why this retry vocabulary is not the two that already exist.
THIS_CLASSIFIES_THE_OPERATION_AND_NOT_THE_OUTCOME_OR_THE_RECORD: Final = (
    "brain.connectors.throttle.is_retryable asks whether this outcome is worth another "
    "attempt, which is a question about a response. brain.ops.idempotency.Disposition asks "
    "what a recovering worker does with a record whose state it found, which is a question "
    "about a crash. RetryClass asks what may ever be repeated at all, which is a property "
    "of the work itself and is the same in every state and after every response. Reading "
    "any of the three as the other two is how somebody retries a side effect nobody knows "
    "the fate of."
)

#: Why an operation with a side effect can never be classified safe.
AN_OPERATION_WITH_A_SIDE_EFFECT_IS_NEVER_SAFE_TO_REPEAT_BLIND: Final = (
    "Safe to retry means the second attempt is indistinguishable from the first not "
    "happening. Anything that changed something outside this process fails that by "
    "definition, whatever the transport said, because the transport is exactly what could "
    "not be relied on. The honest ceiling for work with a side effect is retry after "
    "verification, which is brain.ops.idempotency's whole construction, and the refusal "
    "lives in a constructor because this is the classification somebody edits under "
    "pressure during an incident."
)


class ReliabilityError(Exception):
    """Raised when a failure mode, a retry class or an objective is stated as more than it is."""


# ------------------------------------------------------------------ the stage vocabulary
class Stage(enum.StrEnum):
    """Where in a request the clock is read. One per task group of M3, and nine of them.

    Not derived from the modules in `src/brain/gate/`: that directory is a package layout
    with twenty-two files in it, and a stage list read off it would contain `cache_key` and
    `rule_store`. These are the groups the gate was planned as, and a test holds the count
    against `docs/wbs.json` so that a tenth group is classified deliberately rather than
    falling outside a list nobody notices is short.
    """

    #: M3.1. The context object, the middleware chain and the recorder, before anything.
    CONTEXT = "context"
    #: M3.2. Normalising a channel event and resolving it to a principal.
    INGRESS = "ingress"
    #: M3.3. Resolving entitlements and computing the hash.
    ENTITLE = "entitle"
    #: M3.4. The injection classifier, which never blocks and always scores.
    SCREEN = "screen"
    #: M3.5. The answer cache, looked up and stored.
    CACHE = "cache"
    #: M3.6. Lane classification and agent selection.
    ROUTE = "route"
    #: M3.7. Projecting the tool catalogue through the run reach.
    PROJECT = "project"
    #: M3.8. The agent loop and the leash checks around each call.
    INVOKE = "invoke"
    #: M3.9. Redaction, citations, freshness and the trace reference.
    COMPOSE = "compose"


# ------------------------------------------------------------------ the service levels
#: The three figures `brain.ops.admission.LOAD_TEST_TARGET` states in prose, as integers.
#:
#: **Copies, held equal by a test that parses that sentence.** The prose belongs where it is:
#: it is a pass condition for a load test and reads as one. The integers belong here because
#: an objective is arithmetic. Neither can move without the test noticing, which is the only
#: reason writing the numbers twice is safe.
FAST_P95_MS: Final[int] = 500
ANSWER_P95_MS: Final[int] = 8_000
SUCCESSFUL_REQUEST_RATE: Final[float] = 0.995

#: Statuses that count as the system having done its job.
#:
#: `NOTHING_RETURNED` is here on purpose and it is the load-bearing member. See
#: `A_REFUSAL_IS_A_SUCCESSFUL_REQUEST_OR_THE_DASHBOARD_COUNTS_WHAT_A_READER_MAY_NOT_SEE`.
#: `UNRESOLVED` is here because the asker was told the name matched more than one thing,
#: which is a correct answer to an ambiguous question rather than a fault.
SUCCESS_STATUSES: Final[frozenset[RequestStatus]] = frozenset(
    {RequestStatus.ANSWERED, RequestStatus.NOTHING_RETURNED, RequestStatus.UNRESOLVED}
)

#: Statuses that count against the objective. Declared rather than derived as the complement.
#:
#: A complement would classify a sixth status as a failure the moment somebody added one,
#: silently and in the direction that makes an availability figure drop for a reason nobody
#: can find. Declaring both and checking the partition makes a new status a finding.
FAILURE_STATUSES: Final[frozenset[RequestStatus]] = frozenset(
    {RequestStatus.DEGRADED, RequestStatus.FAILED}
)


@dataclass(frozen=True)
class LaneObjective:
    """What one lane promises end to end (M30.5.1)."""

    lane: Lane
    #: The 95th percentile a request must come back inside. `None` where a percentile is the
    #: wrong instrument rather than an unset one, which is why `because` is required.
    p95_ms: int | None
    #: The share of requests that must end in a `SUCCESS_STATUSES` member.
    success_rate: float
    because: str

    def __post_init__(self) -> None:
        if not self.because.strip():
            msg = f"the {self.lane.value} lane's objective states no reason for its figures"
            raise ReliabilityError(msg)
        if self.p95_ms is not None and self.p95_ms < 1:
            msg = f"the {self.lane.value} lane promises a p95 of {self.p95_ms}ms"
            raise ReliabilityError(msg)
        if not 0.0 < self.success_rate <= 1.0:
            msg = (
                f"the {self.lane.value} lane promises a success rate of {self.success_rate}, "
                "which is not a share of anything"
            )
            raise ReliabilityError(msg)


@dataclass(frozen=True)
class StageObjective:
    """One stage's share of the tightest lane's budget (M30.5.1)."""

    stage: Stage
    p95_ms: int
    because: str

    def __post_init__(self) -> None:
        if self.p95_ms < 1:
            msg = f"the {self.stage.value} stage is budgeted {self.p95_ms}ms, which is no budget"
            raise ReliabilityError(msg)
        if not self.because.strip():
            msg = f"the {self.stage.value} stage's budget states no reason"
            raise ReliabilityError(msg)


#: Per lane, end to end. The task lane carries no percentile and says why.
LANE_OBJECTIVES: Final[tuple[LaneObjective, ...]] = (
    LaneObjective(
        lane=Lane.FAST,
        p95_ms=FAST_P95_MS,
        success_rate=SUCCESSFUL_REQUEST_RATE,
        because=(
            "no model is in the loop, so the whole cost is the gate plus one projected row "
            "read, and the target is what makes the lane worth having: an answer slower "
            "than this is one the answer lane could have given better"
        ),
    ),
    LaneObjective(
        lane=Lane.ANSWER,
        p95_ms=ANSWER_P95_MS,
        success_rate=SUCCESSFUL_REQUEST_RATE,
        because=(
            "a person is waiting and the cost is dominated by a model call this system does "
            "not control the tail of; eight seconds is the point past which somebody "
            "switches tabs and the answer arrives to nobody"
        ),
    ),
    LaneObjective(
        lane=Lane.TASK,
        p95_ms=None,
        success_rate=SUCCESSFUL_REQUEST_RATE,
        because=(
            "nobody is watching the spinner, so a latency percentile measures the wrong "
            "thing precisely: a task that takes nine minutes instead of four has cost "
            "nothing, and one that ends without saying so has cost everything. The "
            "objective a task lane needs is that it finishes and reports, which is the "
            "success rate, and a deadline per task rather than a percentile across them"
        ),
    ),
)

#: Per stage, summing to exactly `FAST_P95_MS`. See
#: `A_BUDGET_WITH_SLACK_IS_A_BUDGET_EVERY_STAGE_GROWS_INTO`.
#:
#: Allocated against the fast lane rather than the answer lane because the fast lane is the
#: binding one: a stage inside 500ms of total budget is inside 8000ms of it as well, and a
#: budget written against the looser target would be no budget for the lane that needs one.
STAGE_OBJECTIVES: Final[tuple[StageObjective, ...]] = (
    StageObjective(
        stage=Stage.CONTEXT,
        p95_ms=5,
        because="constructing a context object and a recorder, with nothing to wait for",
    ),
    StageObjective(
        stage=Stage.INGRESS,
        p95_ms=10,
        because=(
            "normalising an event and one indexed lookup of a channel identity; the dedupe "
            "index is what keeps it a lookup rather than a scan"
        ),
    ),
    StageObjective(
        stage=Stage.ENTITLE,
        p95_ms=60,
        because=(
            "a cache hit is a round trip to Valkey and a miss is a query over the grants, "
            "and the budget has to hold the miss because a cold principal is the one whose "
            "first question this is"
        ),
    ),
    StageObjective(
        stage=Stage.SCREEN,
        p95_ms=40,
        because=(
            "the injection classifier runs on every request and never blocks, so its cost "
            "is paid by every request including the ones it scores at zero"
        ),
    ),
    StageObjective(
        stage=Stage.CACHE,
        p95_ms=20,
        because="two round trips to Valkey, a lookup and a store, on the path that misses",
    ),
    StageObjective(
        stage=Stage.ROUTE,
        p95_ms=30,
        because=(
            "lane classification is computable without a model by construction, and agent "
            "selection is a binding lookup before it is anything more expensive"
        ),
    ),
    StageObjective(
        stage=Stage.PROJECT,
        p95_ms=15,
        because=(
            "intersecting a catalogue with a reach that has already been computed; the "
            "static tool prefix exists so this is not a per-request assembly"
        ),
    ),
    StageObjective(
        stage=Stage.INVOKE,
        p95_ms=300,
        because=(
            "the largest share, and in this lane it is one projected row read plus the "
            "three leash checks around it. It is the stage that would have to shrink if any "
            "other needed to grow, which is why it is sized last and generously"
        ),
    ),
    StageObjective(
        stage=Stage.COMPOSE,
        p95_ms=20,
        because=(
            "the redaction walker over one record, plus citations and freshness; the walk is "
            "over fields rather than over rows, so it is bounded by the schema"
        ),
    ),
)


def lane_objective(lane: Lane, objectives: Sequence[LaneObjective] | None = None) -> LaneObjective:
    """The objective for one lane, refusing a lane nothing declares one for.

    Refuses rather than returning `None`, for the reason `brain.ops.storage.bucket_for`
    gives about a default: a lane with no objective is a lane whose traffic is measured
    against nothing, and a caller handed `None` will render a dash and move on.
    """
    declared = LANE_OBJECTIVES if objectives is None else tuple(objectives)
    for one in declared:
        if one.lane is lane:
            return one
    msg = (
        f"no objective declares the {lane.value} lane; "
        f"declared: {[one.lane.value for one in declared]}"
    )
    raise ReliabilityError(msg)


def stage_budget_gaps(
    objectives: Sequence[StageObjective] | None = None,
    *,
    ceiling_ms: int = FAST_P95_MS,
) -> tuple[str, ...]:
    """Every way the stage budgets fail to be an allocation of the lane target (M30.5.1).

    Three findings: a stage with no budget, a stage budgeted twice, and a total that is not
    the ceiling. The third is an equality rather than a comparison. See
    `A_BUDGET_WITH_SLACK_IS_A_BUDGET_EVERY_STAGE_GROWS_INTO`.
    """
    declared = STAGE_OBJECTIVES if objectives is None else tuple(objectives)
    findings: list[str] = []
    seen: dict[Stage, int] = {}
    for one in declared:
        seen[one.stage] = seen.get(one.stage, 0) + 1
    findings.extend(
        f"the {stage.value} stage has no latency budget, so its cost is charged to whichever "
        "neighbour is measured next"
        for stage in Stage
        if stage not in seen
    )
    findings.extend(
        f"the {stage.value} stage is budgeted {count} times, and the total depends on which "
        "line the reader stops at"
        for stage, count in seen.items()
        if count > 1
    )
    total = sum(one.p95_ms for one in declared)
    if total != ceiling_ms:
        findings.append(
            f"the stage budgets total {total}ms against a lane target of {ceiling_ms}ms. "
            f"{A_BUDGET_WITH_SLACK_IS_A_BUDGET_EVERY_STAGE_GROWS_INTO}"
        )
    return tuple(findings)


def status_gaps(
    successes: frozenset[RequestStatus] = SUCCESS_STATUSES,
    failures: frozenset[RequestStatus] = FAILURE_STATUSES,
) -> tuple[str, ...]:
    """Statuses a success rate would count twice or not at all.

    Both sets are parameters so the check can be shown to fail, which is the only way anybody
    knows it works: run against the declarations it is silent for every value they could
    hold, and a partition check that has never failed is a partition check nobody has read.
    """
    findings: list[str] = []
    findings.extend(
        f"{status.value} is both a success and a failure, so the rate depends on which set "
        "the counter reads first"
        for status in sorted(successes & failures)
    )
    findings.extend(
        f"{status.value} is neither a success nor a failure, so requests ending that way "
        "leave the rate silently and the denominator with them"
        for status in sorted(set(RequestStatus) - successes - failures)
    )
    return tuple(findings)


def success_rate(statuses: Sequence[RequestStatus]) -> float:
    """The share of these requests that count as the system having done its job.

    Refuses an empty window rather than returning 1.0 or 0.0. A rate over no requests is not
    perfect attainment, it is no measurement, and the version of this function that returns
    1.0 for an empty sequence is how a dashboard shows a green light for a system that
    stopped receiving traffic an hour ago.
    """
    if not statuses:
        msg = (
            "a success rate over no requests is not 100%, it is unknown, and a green figure "
            "on an empty window is what a stopped ingest looks like"
        )
        raise ReliabilityError(msg)
    return sum(1 for one in statuses if one in SUCCESS_STATUSES) / len(statuses)


def attainment(
    objective: LaneObjective,
    *,
    observed_p95_ms: float | None,
    observed_success_rate: float,
) -> tuple[str, ...]:
    """How this lane is missing its objective, one sentence per way. Empty when it is not.

    An objective with a percentile and no measurement is reported as a shortfall rather than
    passed over. That is today's state for every lane and it is the honest reading: an
    unmeasured target is not a met one, and a dashboard that showed those rows green would be
    reporting the absence of a metric as compliance.
    """
    findings: list[str] = []
    if objective.p95_ms is not None:
        if observed_p95_ms is None:
            findings.append(
                f"the {objective.lane.value} lane promises a p95 of {objective.p95_ms}ms and "
                "nothing measures one, so the target is unmet rather than met"
            )
        elif observed_p95_ms > objective.p95_ms:
            findings.append(
                f"the {objective.lane.value} lane is at {observed_p95_ms:.0f}ms against a "
                f"target of {objective.p95_ms}ms"
            )
    if observed_success_rate < objective.success_rate:
        findings.append(
            f"the {objective.lane.value} lane succeeded on {observed_success_rate:.4f} of "
            f"requests against a target of {objective.success_rate}"
        )
    return tuple(findings)


# ------------------------------------------------- what the ledger can and cannot measure
#: Field names a whole-request duration could be computed from. None is in the ledger.
#:
#: Written as a set of candidates rather than one name because the fix has several shapes: a
#: completion timestamp subtracted from `received_at`, or a duration recorded directly. Any
#: of them makes the lane objectives measurable, so the check asks whether any is present
#: rather than naming the one somebody ought to add.
WHOLE_REQUEST_DURATION_FIELDS: Final[tuple[str, ...]] = (
    "completed_at",
    "duration_ms",
    "latency_ms",
    "elapsed_ms",
    "total_ms",
)

#: The field a per-stage objective would be measured from. The ledger has no such field, so
#: every stage budget above is a design figure with nothing observing it.
STAGE_FIELD: Final[str] = "stage"

#: The field the success-rate half rests on, and the one thing here that does work today.
STATUS_FIELD: Final[str] = "status"


def measurement_gaps(
    fields: Sequence[str] | None = None,
    unfillable: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """What the metadata ledger cannot currently measure about these objectives (M30.5.2).

    Derived from `brain.ops.telemetry`'s own declarations rather than restated: `fields`
    defaults to the ledger's field list and `unfillable` to the mapping telemetry keeps of
    fields nothing can fill yet. Both are parameters so the healthy case is reachable, which
    matters here more than usual because the declared case is entirely unhealthy and a check
    with no passing input is a check nobody has watched succeed.

    Three findings and a fourth that is currently silent. No whole-request duration, so no
    lane percentile. No stage field, so no stage percentile. `time_to_first_token_ms`
    declared unfillable, so even the partial timing that exists is not being filled. And a
    missing `status`, which would take the one half that works away too.
    """
    present = set(TELEMETRY_FIELDS if fields is None else fields)
    blocked = set(UNFILLABLE_TODAY if unfillable is None else unfillable)
    findings: list[str] = []
    if not present & set(WHOLE_REQUEST_DURATION_FIELDS):
        findings.append(
            "the ledger records when a request arrived and never when it finished, so there "
            "is no duration in it to take a percentile of and every lane latency objective "
            "is unmeasurable rather than unmet"
        )
    if STAGE_FIELD not in present:
        findings.append(
            "the ledger carries one row per request and no field naming a stage, so the "
            "stage budgets are an allocation nothing observes"
        )
    if "time_to_first_token_ms" in blocked:
        findings.append(
            "time_to_first_token_ms is declared unfillable, so the one timing field the "
            "ledger does carry is empty on every row"
        )
    if STATUS_FIELD not in present:
        findings.append(
            "the ledger carries no status, so the success-rate half of every objective is "
            "unmeasurable as well, and nothing about these targets is observed at all"
        )
    return tuple(findings)


# --------------------------------------------------------- recovery objectives (M30.5.4)
@dataclass(frozen=True)
class RecoveryObjective:
    """How much work a profile may lose, and how long it may be down.

    Both in seconds and both per profile, because the two are traded against each other by
    the same decision: a tighter recovery point costs more frequent copies and a tighter
    recovery time costs somewhere to restore into.
    """

    profile: str
    #: The recovery point. How far behind the copies may be.
    rpo_seconds: int
    #: The recovery time. How long from the decision to restore until the system answers.
    rto_seconds: int
    because: str

    def __post_init__(self) -> None:
        assert_known_profile(self.profile)
        if self.rpo_seconds < 1:
            msg = (
                f"the {self.profile} profile promises a recovery point of "
                f"{self.rpo_seconds}s, which is a promise to lose nothing ever"
            )
            raise ReliabilityError(msg)
        if self.rto_seconds < 1:
            msg = f"the {self.profile} profile promises to be back in {self.rto_seconds}s"
            raise ReliabilityError(msg)
        if not self.because.strip():
            msg = f"the {self.profile} profile's recovery objectives state no reason"
            raise ReliabilityError(msg)


#: Recovery objectives per deployment profile (M30.5.4), and defaults like everything here.
#:
#: Keyed on `brain.ops.wiring.PROFILES` through `assert_known_profile` rather than on a
#: vocabulary of its own. `brain.ops.admission.seed_profiles` uses a different set of three
#: names, `lite`, `full` and `ha`, for capacity sizing, and the two are not the same axis: a
#: deployment profile decides which containers run, and taking either list for the other is
#: how a client ends up promised a recovery objective for a profile they are not on.
#:
#: **Not written into a client agreement by anything, which is why M30.5.4 is not claimed.**
#: What exists is the figure and the check that the schedule can meet it; what is missing is
#: the document.
RECOVERY_OBJECTIVES: Final[tuple[RecoveryObjective, ...]] = (
    RecoveryObjective(
        profile="lite",
        rpo_seconds=86_400,
        rto_seconds=28_800,
        because=(
            "a lite install runs four containers on one host and has no second host to "
            "restore onto, so the recovery time is however long it takes somebody to build "
            "one. A day of exposure is what a nightly copy gives, and promising less would "
            "be promising an hourly job nobody has scheduled"
        ),
    ),
    RecoveryObjective(
        profile="standard",
        rpo_seconds=14_400,
        rto_seconds=14_400,
        because=(
            "the workers and the object store are running, so a restore has somewhere to go "
            "and the time is dominated by replaying archived segments rather than by "
            "provisioning. Four hours of exposure is a working day quartered, which is the "
            "granularity a client notices losing"
        ),
    ),
    RecoveryObjective(
        profile="full",
        rpo_seconds=3_600,
        rto_seconds=7_200,
        because=(
            "the tightest figures this system offers, and they are bounded by the slowest "
            "thing on the backup schedule rather than by the database, which is archived "
            "continuously and could support minutes. See the object store's snapshot "
            "interval: an hour is what is actually being promised"
        ),
    ),
)


def recovery_objective(
    profile: str, objectives: Sequence[RecoveryObjective] | None = None
) -> RecoveryObjective:
    """The recovery objectives for one profile, refusing a profile nothing declares.

    Refuses through the declaration rather than through `assert_known_profile` alone: a
    profile that is spelled correctly and has no objective is the interesting case, and a
    known-profile check would pass it through to a `None` somebody renders as a dash.
    """
    declared = RECOVERY_OBJECTIVES if objectives is None else tuple(objectives)
    for one in declared:
        if one.profile == profile:
            return one
    msg = (
        f"no recovery objective declares the {profile!r} profile; "
        f"declared: {[one.profile for one in declared]}"
    )
    raise ReliabilityError(msg)


def profiles_without_objectives(
    objectives: Sequence[RecoveryObjective] | None = None,
) -> tuple[str, ...]:
    """Deployment profiles nothing promises a recovery objective for.

    Read off `brain.ops.wiring.PROFILES` rather than from a list here, so a fourth profile
    arrives as a finding rather than as a profile whose clients are promised nothing.
    """
    declared = RECOVERY_OBJECTIVES if objectives is None else tuple(objectives)
    named = {one.profile for one in declared}
    return tuple(one for one in PROFILES if one not in named)


# ------------------------------------------------------- operation classification (M30.4.2)
class RetryClass(enum.StrEnum):
    """What may be done with a piece of work after it failed or after nobody knows.

    Four, and the four the leaf names. See
    `THIS_CLASSIFIES_THE_OPERATION_AND_NOT_THE_OUTCOME_OR_THE_RECORD` for why this is not
    `brain.ops.idempotency.Disposition` and not `brain.connectors.throttle.is_retryable`.
    """

    #: Repeating it is indistinguishable from the first attempt not having happened.
    SAFE = "safe"
    #: Repeatable, but only after asking the far side what actually happened.
    AFTER_VERIFICATION = "after_verification"
    #: A second attempt produces a second effect that cannot be withdrawn.
    UNSAFE = "unsafe"
    #: A person decides, because the state after the failure is not one a rule covers.
    NEEDS_A_HUMAN = "needs_a_human"


@dataclass(frozen=True)
class OperationClass:
    """One kind of work this system does, and what may be done with it after it fails."""

    name: str
    #: True when performing it changes something outside this process.
    has_side_effect: bool
    retry: RetryClass
    because: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "an operation class with no name classifies nothing"
            raise ReliabilityError(msg)
        if not self.because.strip():
            msg = f"operation {self.name!r} is classified with no reason attached"
            raise ReliabilityError(msg)
        if self.has_side_effect and self.retry is RetryClass.SAFE:
            msg = (
                f"operation {self.name!r} changes something outside this process and is "
                "classified safe to retry. "
                f"{AN_OPERATION_WITH_A_SIDE_EFFECT_IS_NEVER_SAFE_TO_REPEAT_BLIND}"
            )
            raise ReliabilityError(msg)


#: Every kind of work this system does, classified (M30.4.2).
OPERATION_CLASSES: Final[tuple[OperationClass, ...]] = (
    OperationClass(
        name="read a projected row",
        has_side_effect=False,
        retry=RetryClass.SAFE,
        because="a read changes nothing, and the second one is answered from the same tables",
    ),
    OperationClass(
        name="federate a read to a connector",
        has_side_effect=False,
        retry=RetryClass.SAFE,
        because=(
            "no effect at the far end, and whether a particular failure is worth another "
            "attempt is brain.connectors.throttle.is_retryable's question rather than this "
            "one: a rejection is not retryable and the operation is still safe to repeat"
        ),
    ),
    OperationClass(
        name="call a model",
        has_side_effect=False,
        retry=RetryClass.SAFE,
        because=(
            "no effect at the far end and the cost is money rather than correctness, which "
            "is a budget's problem and not a retry classification's"
        ),
    ),
    OperationClass(
        name="restore a backup into a scratch target",
        has_side_effect=False,
        retry=RetryClass.SAFE,
        because=(
            "the target is thrown away, which is what makes a drill repeatable at all; a "
            "restore into anything else is a different operation and is refused before it "
            "gets a classification"
        ),
    ),
    OperationClass(
        name="write a record through a connector",
        has_side_effect=True,
        retry=RetryClass.AFTER_VERIFICATION,
        because=(
            "the honest ceiling for anything with an effect. brain.ops.idempotency exists "
            "for exactly this: the way out of nobody knowing is asking the source, never a "
            "second attempt"
        ),
    ),
    OperationClass(
        name="send a message on a channel",
        has_side_effect=True,
        retry=RetryClass.UNSAFE,
        because=(
            "a second message is read by a person and cannot be withdrawn, and unlike a "
            "record there is nothing to read back that distinguishes one send from two"
        ),
    ),
    OperationClass(
        name="apply a migration",
        has_side_effect=True,
        retry=RetryClass.NEEDS_A_HUMAN,
        because=(
            "a migration that failed halfway has left a schema in a state the next run was "
            "not written against, and brain.ops.migration_policy refuses the combination "
            "that makes it reversible; a recovery sweep re-driving it is how data is lost"
        ),
    ),
    OperationClass(
        name="deploy a release",
        has_side_effect=True,
        retry=RetryClass.NEEDS_A_HUMAN,
        because=(
            "a deploy that failed may or may not have moved production, and the pipeline "
            "cannot tell: a healthy site proves nothing about which commit it is serving. "
            "Somebody reads the tag before anything runs again"
        ),
    ),
)


def retry_class_for(name: str, classes: Sequence[OperationClass] | None = None) -> RetryClass:
    """How this operation may be retried, refusing one nothing has classified.

    Refuses rather than defaulting, and the default it refuses to have is the dangerous one:
    an unclassified operation is by definition one nobody has thought about, and a lookup
    with a `SAFE` default retries it.
    """
    declared = OPERATION_CLASSES if classes is None else tuple(classes)
    for one in declared:
        if one.name == name:
            return one.retry
    msg = f"nothing classifies the operation {name!r}, and an unclassified operation is not retried"
    raise ReliabilityError(msg)


def classification_gaps(
    classes: Sequence[OperationClass] | None = None,
) -> tuple[str, ...]:
    """Ways the operation classification stops covering the four classes or itself.

    A class nothing uses is reported because it is the shape that rots: a category declared
    and never applied looks like coverage in a review and is a word in an enum. A name
    classified twice is reported because the answer then depends on iteration order, which is
    the same failure `brain.console.installation.installation_gaps` catches on a fact.
    """
    declared = OPERATION_CLASSES if classes is None else tuple(classes)
    findings: list[str] = []
    used = {one.retry for one in declared}
    findings.extend(
        f"nothing is classified {kind.value}, so the class is a word rather than a decision "
        "anybody has taken"
        for kind in RetryClass
        if kind not in used
    )
    seen: dict[str, int] = {}
    for one in declared:
        seen[one.name] = seen.get(one.name, 0) + 1
    findings.extend(
        f"operation {name!r} is classified {count} times, and which answer a caller gets "
        "depends on which entry is read first"
        for name, count in seen.items()
        if count > 1
    )
    return tuple(findings)


# ---------------------------------------------------------- the failure matrix (M30.4.1)
#: The four services `docker-compose.yml` declares, which `wiring.COMPONENTS` does not name.
#:
#: `wiring.PRODUCTION_BASELINE_MIB` costs them as one number and the register starts at wave
#: two, so a matrix built from `COMPONENTS` alone would have no row for the database. A test
#: asserts these against the compose file rather than against this tuple, for the reason
#: `ops/seaweedfs/provision.sh` gives about writing a value twice.
BASELINE_COMPONENTS: Final[tuple[str, ...]] = ("app", "cache", "db", "pgbouncer")


def all_components() -> tuple[str, ...]:
    """Every component a failure-mode matrix has to cover, in name order.

    The union of the baseline services and the wave-two register. Derived rather than
    written down, so a component added to `brain.ops.wiring.COMPONENTS` arrives here as a
    gap in the matrix rather than as an omission nobody sees.
    """
    return tuple(sorted({*BASELINE_COMPONENTS, *(one.name for one in COMPONENTS)}))


@dataclass(frozen=True)
class FailureMode:
    """One way a component fails, and everything an operator needs before they touch it.

    `presents_as` is the field worth the most and the one a matrix usually omits. The
    expensive outages here are the ones that present as nothing: a queue behind a
    transaction pooler that stops receiving notifications looks exactly like a queue with
    nothing in it, and an inference server that loaded one model of three answers a third of
    what it is asked while presenting a listening socket.
    """

    component: str
    fails: str
    presents_as: str
    #: What stops working. Declared prose. See
    #: `A_COMPONENT_REGISTER_WITH_NO_EDGES_CANNOT_SAY_WHAT_AN_OUTAGE_BLOCKS`.
    blocks: tuple[str, ...]
    #: How work interrupted by this failure may be resumed.
    retry: RetryClass
    response: str

    def __post_init__(self) -> None:
        for name in ("component", "fails", "presents_as", "response"):
            value: str = getattr(self, name)
            if not value.strip():
                msg = f"a failure mode for {self.component!r} states no {name}"
                raise ReliabilityError(msg)
        if self.component in self.blocks:
            msg = (
                f"the failure mode for {self.component!r} lists it as blocking itself, which "
                "tells an operator nothing they did not have"
            )
            raise ReliabilityError(msg)


#: What breaks, per component (M30.4.1).
MATRIX: Final[tuple[FailureMode, ...]] = (
    FailureMode(
        component="app",
        fails="the application container is not running or is failing readiness",
        presents_as="the site does not answer, or answers /health/live and not /health/ready",
        blocks=("everything a person can ask",),
        retry=RetryClass.SAFE,
        response=(
            "check readiness rather than liveness. A container that is up and cannot reach "
            "the database answers from whatever it can still reach, which is the failure "
            "ops/DEPLOY.md names when it insists the health check path is /health/ready"
        ),
    ),
    FailureMode(
        component="db",
        fails="PostgreSQL is down, out of connections, or out of disk",
        presents_as=(
            "readiness fails; out of connections presents as intermittent failure under load "
            "and nothing at all when it is quiet"
        ),
        blocks=("app", "brain-worker", "brain-parse-worker", "every answer and every write"),
        retry=RetryClass.AFTER_VERIFICATION,
        response=(
            "brain.ops.connections holds the ceiling arithmetic and its headroom figure is "
            "what a restore, a migration or a diagnosis has to fit in; a full disk is the "
            "case below and is not the same fault"
        ),
    ),
    FailureMode(
        component="pgbouncer",
        fails="the pooler is down, or a session-state client has been pointed through it",
        presents_as=(
            "down is a connection refused and is loud. The misuse is silent: LISTEN stops "
            "receiving, a session advisory lock is released by another transaction, and a "
            "prepared statement executes on a backend that never saw it"
        ),
        blocks=("app",),
        retry=RetryClass.AFTER_VERIFICATION,
        response=(
            "brain.ops.wiring.pooler_misuse refuses the combination at declaration time; a "
            "component that needs session state is wired DIRECT and never through here"
        ),
    ),
    FailureMode(
        component="cache",
        fails="Valkey is unreachable",
        presents_as=(
            "slower answers and nothing else, because every cache in this system treats a "
            "miss as a miss. The exception is deliberate and inverted: an unreadable halt "
            "store means halted"
        ),
        blocks=("nothing outright",),
        retry=RetryClass.SAFE,
        response=(
            "expect entitlement resolution and the answer cache to fall through to the "
            "database, and expect the connection budget to feel it"
        ),
    ),
    FailureMode(
        component="brain-worker",
        fails="the worker is down or its queue driver has stopped fetching",
        presents_as=(
            "nothing at all from outside. Work is accepted, queued, and never runs, which "
            "looks identical to a system with nothing to do"
        ),
        blocks=("scheduled work", "digests", "background jobs"),
        retry=RetryClass.AFTER_VERIFICATION,
        response=(
            "the record decides, not the worker: brain.ops.idempotency.resume issues only "
            "from PENDING and everything else is verified against the source"
        ),
    ),
    FailureMode(
        component="brain-parse-worker",
        fails="a parse exceeds the container's memory and the cgroup kills it",
        presents_as=(
            "exit 137 on one job and a queue that otherwise looks healthy; the file that "
            "caused it succeeds nowhere and is retried for ever unless the cause says so"
        ),
        blocks=("knowledge ingestion of the file that failed",),
        retry=RetryClass.SAFE,
        response=(
            "brain.knowledge.parse_budget.parse_worker_gaps compares the door's largest "
            "admissible file against the container; it refuses today when asked about "
            "brain-worker, which is why this component exists separately"
        ),
    ),
    FailureMode(
        component="seaweedfs",
        fails="the S3 gateway is down or a bucket is missing",
        presents_as=(
            "uploads fail loudly and reads of existing originals fail loudly; a missing "
            "lifecycle rule fails silently and for ever"
        ),
        blocks=("knowledge uploads", "exports", "recordings", "backup destinations"),
        retry=RetryClass.SAFE,
        response=(
            "ops/seaweedfs/provision.sh is idempotent and re-running it finishes a partial "
            "provision; brain.ops.storage.lifecycle_gaps is what compares the live store "
            "against the declaration"
        ),
    ),
    FailureMode(
        component="keycloak",
        fails="the identity provider is down, or its realm was never imported",
        presents_as=(
            "nobody can sign in. The realm case is worse than the outage: /health/ready is "
            "true only once the realm is imported, so an unimported realm presents as a "
            "provider that is up and rejects everybody"
        ),
        blocks=("every new session",),
        retry=RetryClass.SAFE,
        response=(
            "existing sessions are unaffected, so the blast radius is people arriving "
            "rather than people working; brain.ops.realm_import is what makes the import "
            "checkable"
        ),
    ),
    FailureMode(
        component="keycloak-db",
        fails="the identity provider's own PostgreSQL is down",
        presents_as="keycloak fails readiness, which presents as the row above",
        blocks=("keycloak",),
        retry=RetryClass.SAFE,
        response=(
            "separate from the application's database on purpose: sharing would put the "
            "credential store and the company's records in one blast radius"
        ),
    ),
    FailureMode(
        component="presidio-analyzer",
        fails="the analyser is down or is answering without its models loaded",
        presents_as=(
            "down is a refused connection. Loaded-without-models is the dangerous one: it "
            "returns no detections, which is indistinguishable from text containing no "
            "personal data"
        ),
        blocks=("anything that redacts before sending text onward",),
        retry=RetryClass.SAFE,
        response=(
            "readiness is a detection for a known-positive probe rather than a socket, "
            "which is the whole reason wiring.Component requires a ready_when sentence"
        ),
    ),
    FailureMode(
        component="inference-server",
        fails="the server is up with fewer than all of its models resident",
        presents_as=(
            "two thirds of requests fail against a listening socket; the container is green "
            "in every view that checks liveness"
        ),
        blocks=("embedding", "entity recognition", "any local generation"),
        retry=RetryClass.SAFE,
        response=(
            "readiness probes every model in brain.ops.inference.SERVED_MODELS rather than "
            "the process, and the memory limit is arithmetic over the weights rather than "
            "what was left over"
        ),
    ),
    FailureMode(
        component="langfuse-web",
        fails="the trace ledger's ingest endpoint refuses or is unreachable",
        presents_as=(
            "nothing visible. The client library retries and drops inside itself, so traces "
            "stop arriving and no request fails"
        ),
        blocks=("the step-by-step trace an operator reads during an incident",),
        retry=RetryClass.SAFE,
        response=(
            "the audit ledger is unaffected and is the client-facing record; see "
            "brain.ops.wiring.LITE_KEEPS_THE_AUDIT_LEDGER for what is and is not lost"
        ),
    ),
    FailureMode(
        component="langfuse-worker",
        fails="the ingest queue stops draining",
        presents_as="traces arrive and never become readable; the web tier still accepts them",
        blocks=("trace readback",),
        retry=RetryClass.SAFE,
        response="readiness is a falling or empty queue depth rather than a live process",
    ),
    FailureMode(
        component="langfuse-clickhouse",
        fails="the column store is down or out of disk",
        presents_as="the worker cannot write and the queue grows, which is the row above",
        blocks=("langfuse-worker", "langfuse-web"),
        retry=RetryClass.SAFE,
        response=(
            "its practical floor is a gigabyte and budget_breaches already reports that the "
            "full profile does not fit on the measured host"
        ),
    ),
    FailureMode(
        component="langfuse-cache",
        fails="the trace stack's own Valkey is unreachable",
        presents_as="ingest slows and the queue grows",
        blocks=("langfuse-worker",),
        retry=RetryClass.SAFE,
        response="separate from the application cache; an outage here reaches no answer path",
    ),
    FailureMode(
        component="activepieces",
        fails="the automation canvas or its egress proxy is down",
        presents_as="flows stop running; the flow runner reports no worker",
        blocks=("automation flows",),
        retry=RetryClass.AFTER_VERIFICATION,
        response=(
            "a flow step may have reached a connector before the canvas stopped, so what "
            "resumes is decided by the operation record rather than by the canvas; it holds "
            "no connection string to this system's database by design"
        ),
    ),
)


def matrix_gaps(
    rows: Sequence[FailureMode] | None = None,
    components: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Every way the failure matrix stops covering the deployment (M30.4.1).

    Four findings: a component with no row, a row for a component nothing deploys, a row
    blocking something that is not a component or a plain-English consequence, and two rows
    for one component.

    The third is deliberately lenient. `blocks` holds component names and phrases like
    "every answer and every write", because what an outage costs is not always another
    container, and a check that demanded component names would force the useful half of the
    field to be deleted. So an entry is a finding only when it looks like a component name
    and is not one: a single token containing a hyphen or matching nothing.
    """
    declared = MATRIX if rows is None else tuple(rows)
    known = set(all_components() if components is None else components)
    findings: list[str] = []

    covered: dict[str, int] = {}
    for one in declared:
        covered[one.component] = covered.get(one.component, 0) + 1
    findings.extend(
        f"{name}: no failure mode is written for it, so the first person to see it fail "
        "writes one from scratch during the incident"
        for name in sorted(known - set(covered))
    )
    findings.extend(
        f"{name}: a failure mode is written for a component nothing deploys"
        for name in sorted(set(covered) - known)
    )
    findings.extend(
        f"{name}: {count} failure modes, and an operator reads whichever is first"
        for name, count in sorted(covered.items())
        if count > 1
    )
    for one in declared:
        findings.extend(
            f"{one.component}: blocks {blocked!r}, which is named like a component and is not one"
            for blocked in one.blocks
            if "-" in blocked and " " not in blocked and blocked not in known
        )
    return tuple(findings)
