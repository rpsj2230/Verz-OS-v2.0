"""Running a built agent through the real gate, with the world unplugged.

`brain.builder.publish` says twice that nothing in it runs anything: M20.3.1 wants the
rehearsal run against the real gate, leash and redactor, and M20.3.2 wants a cassette player.
This is the half that runs it, and the two leaves pull in opposite directions hard enough
that reconciling them is the whole design. **A rehearsal against a stand-in only proves the
stand-in is self-consistent**, so the evidence has to come from the system somebody will
actually run. **A rehearsal that sends one email is not a rehearsal**, so nothing outside this
process may change. Every decision below says which of those two it landed on.

**The gate is real and the world is absent, and that is the line the two are separated
along.** Nothing here decides anything the gate decides. `brain.gate.leash.govern` is called
rather than copied, so the capability check, the rung, the mask, the risk ceiling and the
route all come back from the one implementation, and the reach they were computed under is
the one `EntitlementSet.intersect` produced inside `decide`. What is replaced is strictly the
far side of the tool boundary, where a recorded exchange stands in for a source. See
`THE_GATE_IS_REAL_AND_THE_WORLD_IS_ABSENT`.

**Rejected: a rehearsal flag inside the gate.** The obvious design is a parameter on `govern`
that suppresses execution, and it changes the wrong half. It puts a second policy inside the
one module whose entire claim is that there is a single path to a side effect, and a boolean
that suppresses a side effect is one assignment away from being False on the afternoon
somebody rehearses against production.

**Rejected: pinning the rung to SHADOW for the duration.** Also tempting, also the wrong half.
`publish.REHEARSAL_RUNG` is SHADOW and that is a statement about the rehearsal's own
supervision; forcing the gate to it would mean previewing a run at a rung the published agent
will never run at, which is `A_REHEARSAL_AT_THE_AUTHORS_REACH_IS_A_PREVIEW_OF_A_DIFFERENT_RUN`
aimed at the rung instead of at the reach. So the leash handed in is the agent's own, the
route comes out however it comes out, and `Route.EXECUTE` is a normal outcome of a rehearsal.
What stops an execute from executing is that there is nothing on the other side of it.

**One replay is handed to the gate as both callables.** `govern` takes a `simulate` and an
`execute` because it is the router; a rehearsal that passed the real `execute` would fire on
exactly the route most worth rehearsing. Passing an `execute` that raises was rejected as
well, and for a sharper reason than it looks: that changes the outcome rather than the effect,
so an author rehearsing an autonomous agent would learn nothing about the run past its first
write, and the failure would read as the agent's rather than the harness's.

**There is nowhere in this module to put a client, and that is checked rather than promised.**
`Take` carries a recorded value, not a reader; `rehearse` takes no callable; the replay is
built here from a value that is already in hand. `rehearsal_gaps` reads the entry point's own
signature and `Take`'s own fields and reports either, which is the construction
`brain.ops.spend` uses for its estimator and `brain.core.redaction.assert_channel_adapter`
uses for an adapter: the guarantee is a signature, because a body can be read and a signature
cannot be argued with. `brain.gate.leash.run_shadow` says it cannot check whether the
simulator itself touches the world and names a recorded fixture as the compensating control.
This is that control, made a mechanism.

**A suspension is a side effect a cassette does not stop, and it is the one this nearly
missed.** A rehearsal whose agent lands on `Route.SUSPEND` makes `govern` build a
`SuspendedAction`, and a suspension that reached a queue would put an approval in front of a
person for an action nobody is taking. A person's queue is part of the world. So the
suspension is read for its route and discarded, its id is derived rather than random so the
module has no clock and no entropy in it, and the id begins with
`REHEARSAL_SUSPENSION_PREFIX` so one that somehow escaped is not indistinguishable from a real
one. See `A_SUSPENSION_THAT_ESCAPED_IS_A_SIDE_EFFECT_NO_CASSETTE_STOPS`.

**A rehearsal writes no record, for the same reason.** `govern` builds an `ActionRecord` per
call and `ActionRecord` has no field distinguishing a rehearsal from a run, which is correct
for it and fatal here: returning the `Governed` so a caller could persist it would put rows
saying EXECUTE into the history of an agent that has never run. `Step` carries the route and
nothing that could be written to the ledger as a fact.

**Nor an operation key.** Since 2026-09-16 `govern` keys every execute through
`brain.ops.idempotency.issue_once`, and a key claimed in the real operation ledger is a record
that an effect happened, which a later real run of the same action would be deduplicated
against. The rehearsal hands the gate a ledger that keeps nothing and wins every key. See
`A_REHEARSAL_KEYS_NOTHING_A_REAL_RUN_WOULD_MEET`. This is argued and not tested: a `Step` is
built from the route, so a ledger that remembered would produce the same report, and the row it
would leave in the real ledger is outside anything a unit test here can see.

**The cassette moves the privacy rule from the output to the input.** `publish` argues at
length that a rehearsal must not become a way of reading a colleague's data by picking them as
a persona, and answers it by giving `RehearsalOutcome` nowhere to put a row. Replay answers it
one layer earlier: a rehearsal driven by recordings never queries anything, so there are no
rows of the persona's to withhold. The output rule still stands and `rehearsal_gaps` still
applies `publish.row_shaped_fields` to this module's own report types, because the two protect
against different edits.

**The reach the redactor runs at is handed in and checked, never computed.** `E_run` has one
implementation and `gate.leash.decide` is one of its two call sites, so a builder working the
run reach out for itself would be a third copy of the central rule in the layer with the least
reason to be trusted with it. Instead `run_reach` is a parameter, and a rehearsal is refused
when its digest is not the digest `decide` computed for the reach it actually used. That is
the check `leash.resume` makes against a suspension, and it means the mask check and the
redactor cannot be looking at two different reaches without this saying so. The principal is
checked separately by `publish.reach_refusals`, because two principals with identical grants
share a digest by design.

**The cost is the estimator a real run's pre-flight uses, with one measured input** (M20.3.4).
`brain.ops.spend.estimate` prices a run from lane, tier, tool count, retrieval size and
fan-out, and `spend.preflight` is what a real run is admitted by. The rehearsal changes exactly
one of those five and takes the rest from the agent's own shape: `tool_calls` is the number of
takes that actually reached a tool, which is the one input a form cannot know and only a run
can produce. A step the gate refused never called anything and never cost anything.

**Rejected: counting the characters the replay returned and dividing by something.** It reads
like a better measurement and it is a second cost model. `TOKENS_PER_TOOL_CALL` already prices
a round trip including the result the model reads back, so a token count taken here would
disagree with the estimator by whatever divisor somebody chose, and the disagreement would be
invisible: the rehearsal would show one figure and the budget check another, both derived from
the same run. See `A_COST_THE_REHEARSAL_INVENTS_IS_A_SECOND_COST_MODEL`.

**And the cost is shown at the same detail the tool names are, because it is the same fact.**
The figure moves with how many steps the gate let through, so the same agent rehearsed as two
personas returns two costs differing by exactly what the second persona was refused. That is
the subtraction rule arriving through a number that does not look like a count, which is the
shape it is hardest to see. `shown_report` empties the steps and the cost together at
`Detail.OUTCOME` rather than rounding either. See
`A_COST_IS_A_STATEMENT_ABOUT_WHAT_THE_GATE_REFUSED`.

Scope: domain logic. Nothing here opens a connection, renders anything or reads a clock; `now`
is a parameter and is required, for the reason `publish` gives about its own.

Task ids: M20.3.1, M20.3.2, M20.3.4
"""

from __future__ import annotations

import inspect
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final, Protocol

from brain.builder.compose import BuilderError
from brain.builder.publish import (
    Detail,
    Rehearsal,
    RehearsalOutcome,
    reach_refusals,
    row_shaped_fields,
    shown,
)
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import Entity, TypedResult
from brain.core.field_policy import FieldPolicy
from brain.core.redaction import simulate_redaction
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.leash import Action, CheckName, Governed, Leash, Route, govern
from brain.ops.idempotency import Operation, OperationState
from brain.ops.spend import NO_CORRECTION, Correction, CostInputs, Estimate, estimate

# ------------------------------------------------------------------ written-down reasons
#: Which half of a rehearsal is the real system and which half is missing.
THE_GATE_IS_REAL_AND_THE_WORLD_IS_ABSENT: Final = (
    "A rehearsal has to be evidence about the system somebody will run, so every decision is "
    "taken by the gate that will take it in production: the capability check, the rung, the "
    "mask, the risk ceiling and the route all come back from brain.gate.leash.govern and none "
    "of them is restated here. A rehearsal also has to leave nothing behind, so the far side "
    "of the tool boundary is a recorded exchange rather than a source. Weakening a check to "
    "keep the world safe would be the same rehearsal with the evidence removed; replacing the "
    "world keeps every check and removes the only thing that could travel."
)

#: Why a rehearsal does not force the rung it runs at.
A_REHEARSAL_THAT_PINNED_THE_RUNG_WOULD_PREVIEW_A_DIFFERENT_RUN: Final = (
    "Pinning the gate to SHADOW for the duration of a rehearsal is the obvious way to stop an "
    "action being carried out, and it makes the rehearsal a preview of a run that will never "
    "happen: the published agent runs at the rung its leash says, and the one outcome worth "
    "rehearsing is the one where that rung is AUTONOMOUS. It is the same failure "
    "publish.A_REHEARSAL_AT_THE_AUTHORS_REACH_IS_A_PREVIEW_OF_A_DIFFERENT_RUN describes, "
    "aimed at the rung instead of at the reach, and it passes in exactly the same way."
)

#: Why a suspension raised during a rehearsal is discarded rather than returned.
A_SUSPENSION_THAT_ESCAPED_IS_A_SIDE_EFFECT_NO_CASSETTE_STOPS: Final = (
    "A cassette stops a source being called and does nothing at all about the gate's own "
    "by-products. An agent on the assisted rung suspends, and a suspension that reached a "
    "queue would put an approval in front of a person for an action nobody is taking: a "
    "person's queue is outside this process, so that is a real side effect fired by a "
    "rehearsal. The suspension is read for its route and dropped, and the id it is built "
    "with says what it was so that one which somehow escaped does not look like a real one."
)

#: Why a rehearsal's executes are keyed in a ledger that keeps nothing.
A_REHEARSAL_KEYS_NOTHING_A_REAL_RUN_WOULD_MEET: Final = (
    "govern keys every execute in an operation ledger so a real action runs once. A rehearsal "
    "keyed in the real one would leave a record saying an effect happened when a replay "
    "happened, in the table recovery reads, and a real run of the same action under the same "
    "trace would then be handed a repeat and never run. So a rehearsal's ledger lives for the "
    "rehearsal and wins every key, which is the same line the suspension and the action "
    "record are drawn along: what the gate produces is read, and nothing is left behind."
)

#: Why the rehearsal does not measure tokens for itself.
A_COST_THE_REHEARSAL_INVENTS_IS_A_SECOND_COST_MODEL: Final = (
    "Counting the characters a replay returned and converting them to tokens reads like a "
    "better measurement than the estimator's flat figure, and it is a second cost model. "
    "spend.TOKENS_PER_TOOL_CALL already prices a round trip including the result the model "
    "reads back, so a count taken here would disagree with the estimator by whatever divisor "
    "somebody picked, and both figures would be derived from the same run: the rehearsal "
    "would show one and the budget check would refuse on the other."
)

#: Why the measured cost is shown only to a reader who may already read the persona's grants.
A_COST_IS_A_STATEMENT_ABOUT_WHAT_THE_GATE_REFUSED: Final = (
    "The figure moves with how many steps the gate let through, so one agent rehearsed as two "
    "personas returns two costs that differ by exactly what the second persona was refused. "
    "That is a count of hidden things arriving through a number nobody reads as a count, "
    "which is the shape it is hardest to notice. It is therefore shown behind the same grant "
    "the tool names are, and emptied rather than rounded when that grant is absent."
)


# ------------------------------------------------------------- the recording (M20.3.2)
class Recording(Protocol):
    """A recorded exchange, in the shape the corpus already records one.

    **A protocol rather than a record type, and that is the reuse.**
    `tests.fixtures.cassettes.Cassette` satisfies this as it stands, so a rehearsal is driven
    by the corpus `tests/invariants/test_cassettes.py` guards rather than by a second
    recording with its own fields, its own idea of what a failure looks like and its own
    drift. `brain.connectors.freshdesk.Reply`, `lark_base.Reply` and `google_drive.Reply` each
    say the same thing about themselves in a docstring; this says it in a type.

    Members are read-only, so a frozen dataclass satisfies it without being asked to grow a
    setter it should not have.

    **Rejected: judging here whether the recording succeeded.** The corpus deliberately holds
    a 200 carrying an application error, and which bodies mean failure is a vendor fact:
    `code` of zero is success in one source's envelope, an ordinary field name in another's,
    and absent from a third's. A generic rule about it would be a second, wrong opinion in the
    layer furthest from the vendor, so the connectors keep that judgement and this keeps the
    shape.
    """

    @property
    def cid(self) -> str: ...

    @property
    def status(self) -> int: ...

    @property
    def body(self) -> Any: ...


#: Identifiers that, appearing in an annotation here, would give a rehearsal a way to reach a
#: source. Names rather than a rule about types, for the reason
#: `brain.core.redaction.UNREDACTED_TYPE_NAMES` is names: the failure arrives as a parameter
#: somebody adds to make the rehearsal useful against a live connector, and it is caught by
#: reading the annotation rather than by resolving it.
#:
#: `Callable` is the load-bearing entry, and it is not arbitrary: it is what
#: `brain.gate.leash.govern` declares for `simulate` and `execute`, so the thing this module
#: refuses to be handed is exactly the thing the gate has to be handed.
NAMES_THAT_WOULD_REACH_A_SOURCE: Final[frozenset[str]] = frozenset(
    {
        "Awaitable",
        "Callable",
        "Client",
        "Connection",
        "Coroutine",
        "PageReader",
        "Reader",
        "RowSource",
        "Session",
        "Transport",
    }
)


@dataclass(frozen=True)
class Take:
    """One step of a rehearsal: the action, the recording that answers it, and what it carried.

    Three fields and none of them can fetch anything. `replay` is a value decoded by whoever
    owns that source's parser, `recording` is the exchange it was decoded from, and the `cid`
    is what lets a report say which recording answered rather than asking a reader to take it
    on trust.

    **The replay's records must be tagged with the tool's own object.** A replay tagged
    otherwise would be redacted against the field policy for a different entity, so the
    rehearsal's evidence about what the persona may see would be evidence about something
    else, and it would look right: the redactor would run, return withheld names, and every
    one of them would be about the wrong record.
    """

    action: Action
    recording: Recording
    #: The records that recording carried. Rows are permitted here and nowhere on the way out:
    #: this is what the author hands in, and the rule is about the return path.
    replay: TypedResult[Entity]

    def __post_init__(self) -> None:
        if not self.recording.cid.strip():
            msg = (
                "a take whose recording has no id cannot be traced back to the corpus, so "
                "nothing distinguishes a replay of a recorded exchange from a fixture "
                "somebody typed, which is the mock the recordings exist to replace"
            )
            raise BuilderError(msg)
        wrong = sorted(
            {one.entity for one in self.replay.records if one.entity != self.action.tool.entity}
        )
        if wrong:
            msg = (
                f"{self.action.tool.name} is a tool on {self.action.tool.entity!r} and its "
                f"replay carries {wrong}; the redactor would answer about the wrong object's "
                "policy and the rehearsal would read as though it had checked this one"
            )
            raise BuilderError(msg)


# --------------------------------------------------------- what a route costs (M20.3.4)
#: The routes on which a tool was actually called, and which therefore cost something.
#:
#: Declared rather than derived, and anchored outside itself: these are exactly the routes for
#: which `govern` returns a result to the agent loop, which is a fact about the gate that a
#: test measures by running it four ways. Deriving it from `Governed.for_agent()` would make
#: the constant true by construction and say nothing about whether the right routes are priced.
REACHED_THE_TOOL: Final[frozenset[Route]] = frozenset({Route.SIMULATE, Route.EXECUTE})

#: And the routes on which nothing was called. Declared rather than subtracted, so that a
#: fifth route is reported by `rehearsal_gaps` as unclassified instead of being priced at
#: nothing by a set difference that quietly absorbed it.
DID_NOT_REACH_THE_TOOL: Final[frozenset[Route]] = frozenset({Route.REFUSED, Route.SUSPEND})

#: What a rehearsal's suspension ids begin with. See
#: `A_SUSPENSION_THAT_ESCAPED_IS_A_SIDE_EFFECT_NO_CASSETTE_STOPS`: `govern` mints a random hex
#: id when it is not given one, and a random id is precisely what a real suspension carries.
REHEARSAL_SUSPENSION_PREFIX: Final = "rehearsal"


@dataclass(frozen=True)
class Step:
    """What the real gate did with one take. Verdicts and names, and nothing a record held.

    `withheld` is the real redactor's answer, in the shape `SimulationReport` returns it:
    `entity.field`, sorted and deduplicated, with a flag rather than a count for whether a
    whole record would go. It is here because "the redactor ran" is otherwise a claim nothing
    could falsify from the outside, and it is shown only at `Detail.PER_TOOL` because which
    fields a persona loses is which grants the persona is missing.
    """

    tool: str
    #: Which recording answered this step.
    recording_id: str
    route: Route
    tier: AutonomyTier
    #: The check that stopped this step, or None when nothing did.
    refused_by: CheckName | None
    #: `entity.field` the redactor would withhold from this persona.
    withheld: tuple[str, ...] = ()
    #: Whether a whole record would go. A flag and never a count (M4.3.2).
    withheld_a_record: bool = False

    @property
    def reached_the_tool(self) -> bool:
        """Whether anything was called on this step, and therefore whether it cost anything."""
        return self.route in REACHED_THE_TOOL


@dataclass(frozen=True)
class RehearsalReport:
    """One rehearsal: what came back, what the gate did at each step, and what it would cost.

    **No field here holds a row**, which `rehearsal_gaps` asks of the type through
    `publish.row_shaped_fields` rather than of whoever edits it next. `cost` is an `Estimate`
    from `brain.ops.spend`, which carries the inputs it was computed from so a figure can be
    argued with rather than believed.
    """

    outcome: RehearsalOutcome
    steps: tuple[Step, ...] = ()
    #: What this run would cost, from the estimator a real run's pre-flight uses. None when
    #: the rehearsal did not run, and None at `Detail.OUTCOME`.
    cost: Estimate | None = None
    #: Why the rehearsal did not run. Facts about how it was set up, never about the persona.
    refusals: tuple[str, ...] = ()

    @property
    def rehearsed(self) -> bool:
        """Whether the gate was actually asked anything."""
        return not self.refusals


# ---------------------------------------------------------------------- the replay
class _EveryTakeIsAFirstRun:
    """The operation ledger a rehearsal hands `govern`: it keeps nothing and refuses nothing.

    `govern` keys an execute through `brain.ops.idempotency.issue_once` and cannot be called
    without a ledger. See `A_REHEARSAL_KEYS_NOTHING_A_REAL_RUN_WOULD_MEET` for why it is not the
    real one. It wins every key, because each take replays a recording of one run and a
    ledger that remembered takes would turn the second identical take into a repeat that no
    recording shows. It has no guard to get wrong: the only edge it checks is the state
    machine's own, through `Operation.advanced`.
    """

    def __init__(self) -> None:
        self._claimed: dict[str, Operation] = {}

    def claim(self, operation: Operation) -> Operation:
        self._claimed[operation.key] = operation
        return operation

    def win(self, key: str) -> bool:
        del key  # Every take is a first run; see the class docstring.
        return True

    def settle(self, key: str, *, frm: OperationState, to: OperationState) -> Operation:
        return replace(self._claimed[key], state=frm).advanced(to)


def _replaying(result: TypedResult[Entity]) -> Callable[[Action], TypedResult[Entity]]:
    """A callable that answers with a value already in hand, whatever it is asked.

    A factory rather than a closure written at the call site, because a closure over a loop
    variable is a bug this repository's linter refuses and the version that silences it is the
    version that captures the last take. The action is ignored deliberately: a replay that
    chose its answer from the action would be a stub with behaviour, which is a source of
    truth nobody recorded.
    """

    def replay(_: Action) -> TypedResult[Entity]:
        return result

    return replay


def _refused(rehearsal: Rehearsal, refusals: tuple[str, ...]) -> RehearsalReport:
    """A rehearsal that did not run: no steps, no cost, and nothing said about the persona."""
    return RehearsalReport(
        outcome=RehearsalOutcome(
            agent_id=rehearsal.agent_id, persona_id=rehearsal.persona_id, answered=False
        ),
        refusals=refusals,
    )


def _step(
    take: Take,
    governed: Governed[Entity],
    *,
    run_reach: EntitlementSet,
    policy: FieldPolicy,
    now: datetime,
) -> Step:
    """One take's verdict, with the redactor run over what came back (M20.3.1).

    `simulate_redaction` rather than `redact`, and the choice is the reconciliation in
    miniature: it runs the enforcing walk, which is what "the real redactor" means, and
    returns a type that physically cannot carry a value, which is what stops the rehearsal
    becoming a window onto the persona's rows. Its own docstring makes the argument: a preview
    with its own logic is the component most likely to lie.

    Nothing is redacted on a step that never called anything. A refused step has no result,
    and reporting withheld fields for it would tell an author that the persona could not see
    those fields when what happened is that the persona could not make the call.
    """
    withheld: tuple[str, ...] = ()
    withheld_a_record = False
    if governed.route in REACHED_THE_TOOL:
        seen = simulate_redaction(take.replay, entitlement=run_reach, policy=policy, now=now)
        withheld = seen.would_withhold
        withheld_a_record = seen.would_withhold_a_record
    return Step(
        tool=take.action.tool.name,
        recording_id=take.recording.cid,
        route=governed.route,
        tier=governed.decision.tier,
        refused_by=governed.decision.refused_by,
        withheld=withheld,
        withheld_a_record=withheld_a_record,
    )


# ------------------------------------------------------------- the measured cost (M20.3.4)
def tool_calls_made(steps: Sequence[Step]) -> int:
    """How many steps actually called a tool (M20.3.4).

    The one input to the cost that a form cannot know and only a run can produce. A step the
    gate refused never reached the tool and never cost a round trip, which is why the same
    agent costs less for a persona holding less.
    """
    return sum(1 for step in steps if step.reached_the_tool)


def measured_cost(
    shape: CostInputs, steps: Sequence[Step], *, correction: Correction = NO_CORRECTION
) -> Estimate:
    """What this rehearsal's run would cost, priced by the estimator a real run uses (M20.3.4).

    `shape` is the agent's own priced shape: its lane, its tier, the retrieval it is
    configured for and its fan-out. Exactly one field is replaced, and it is the measured one.
    Everything else, including the rate table and the rounding, is
    `brain.ops.spend.estimate`'s, which is the function `spend.preflight` admits a real
    request by. See `A_COST_THE_REHEARSAL_INVENTS_IS_A_SECOND_COST_MODEL`.

    `correction` is a parameter and not a constant for the same reason. A real run is priced
    with whatever `spend.correct` has learnt from actuals, so a rehearsal defaulted to
    `NO_CORRECTION` while production runs at 1.6x under-states by that factor and disagrees
    with the pre-flight it is meant to predict. The default is here because a rehearsal can
    honestly be run before any actuals exist, not because it is the right value once they do.

    The estimator's own refusals are not caught. A fast-lane shape that made a tool call is a
    contradiction and `SpendError` is the right answer to it; catching it here would be a
    second opinion about whether a lane may hold a tool.
    """
    return estimate(replace(shape, tool_calls=tool_calls_made(steps)), correction=correction)


# ------------------------------------------------------------------ the run (M20.3.1)
def rehearse(
    rehearsal: Rehearsal,
    takes: Sequence[Take],
    *,
    caller: EntitlementSet,
    agent_ceiling: EntitlementSet,
    run_reach: EntitlementSet,
    policy: FieldPolicy,
    leash: Leash,
    assessment: RiskAssessment,
    shape: CostInputs,
    trace_id: str,
    now: datetime,
    correction: Correction = NO_CORRECTION,
) -> RehearsalReport:
    """Put every take through the real gate and report what happened (M20.3.1, M20.3.2).

    `caller` is the persona's own reach and `publish.reach_refusals` is what says so; handing
    the author's would preview a different run from the one being published. `run_reach` is
    `E(persona) intersect agent_ceiling`, computed by whoever already holds it and never here:
    a rehearsal whose digest does not match the one `decide` computed for the reach it
    actually used is refused, so the mask check and the redactor cannot silently be looking at
    two different reaches.

    **Nothing about the author is a parameter.** What the author may be shown is decided
    afterwards by `shown_report`, so no fact about who is watching can influence what the run
    does, which is the difference between a preview and a demonstration.

    The gate's by-products are read and dropped. The `ActionRecord` `govern` builds is not
    returned, because it has no field saying this was a rehearsal and a row saying EXECUTE
    would be a lie in the one table nobody re-derives; the `SuspendedAction` is not returned,
    because an approval in a person's queue is a side effect outside this process and no
    cassette prevents it.

    An empty take list is refused rather than reported. A rehearsal of nothing comes back
    looking exactly like a run the gate refused at every step, and those two must not be one
    answer.
    """
    if not takes:
        msg = (
            "a rehearsal with no takes reports a run that was refused everywhere, and an "
            "author cannot tell that from an agent whose every step the gate stopped"
        )
        raise BuilderError(msg)

    refusals = reach_refusals(rehearsal, caller)
    if refusals:
        return _refused(rehearsal, refusals)

    expected = run_reach.ent_hash()
    steps: list[Step] = []
    unkept = _EveryTakeIsAFirstRun()
    for index, take in enumerate(takes):
        # One replay, handed to the gate as both of its callables. `govern` is the router and
        # necessarily holds both; this is the one place that can decide what is on the far
        # side of each, and it decides the same thing for both.
        replay = _replaying(take.replay)
        governed = govern(
            take.action,
            caller=caller,
            agent_ceiling=agent_ceiling,
            policy=policy,
            leash=leash,
            assessment=assessment,
            trace_id=trace_id,
            now=now,
            simulate=replay,
            execute=replay,
            ledger=unkept,
            suspension_id=f"{REHEARSAL_SUSPENSION_PREFIX}.{index}",
        )
        if governed.decision.ent_hash != expected:
            return _refused(
                rehearsal,
                (
                    "the reach handed to the redactor is not the reach the gate computed for "
                    "this run, so what a persona was shown and what they may see were decided "
                    "under two different entitlements and the rehearsal proves neither",
                ),
            )
        steps.append(_step(take, governed, run_reach=run_reach, policy=policy, now=now))

    return RehearsalReport(
        outcome=RehearsalOutcome(
            agent_id=rehearsal.agent_id,
            persona_id=rehearsal.persona_id,
            answered=all(step.reached_the_tool for step in steps),
            # Sorted and deduplicated, so neither the order the takes were drawn in nor how
            # many times a tool was called can be read back out of the list. A tool called
            # twice is one name here, because the alternative is a count.
            tools_reached=tuple(sorted({step.tool for step in steps if step.reached_the_tool})),
        ),
        steps=tuple(steps),
        cost=measured_cost(shape, steps, correction=correction),
    )


def shown_report(report: RehearsalReport, detail: Detail) -> RehearsalReport:
    """The report as this author may see it (M20.3.1, M20.3.4).

    At `Detail.OUTCOME` the steps go and the cost goes with them, and neither is trimmed,
    counted or rounded. `publish.shown` already makes that argument about the tool list; the
    cost is the same fact wearing a different shape, because it moves with how many steps the
    gate let through. See `A_COST_IS_A_STATEMENT_ABOUT_WHAT_THE_GATE_REFUSED`.

    The refusals survive at both levels. They say the rehearsal was set up wrongly, which is a
    fact about the author's own request rather than about the persona's grants, and withheld
    they would leave an author looking at an empty report with no way to tell it from a run
    that happened and found nothing.
    """
    if detail is Detail.PER_TOOL:
        return report
    return RehearsalReport(
        outcome=shown(report.outcome, detail),
        steps=(),
        cost=None,
        refusals=report.refusals,
    )


# ------------------------------------------------------------------------- the diagnostic
#: The types an author of a rehearsal is handed back. Listed rather than discovered, following
#: `brain.console.workspace.WORKSPACE_SURFACE`.
#:
#: `Take` is deliberately absent and that is the one judgement in this tuple. A take is what
#: the author hands in, and a recording is data they already chose; the rule the surface check
#: enforces is about the return path, which is where a rehearsal would become a way of reading
#: somebody else's rows.
REHEARSAL_SURFACE: Final[tuple[type, ...]] = (Step, RehearsalReport)


def _names_in(annotation: object) -> frozenset[str]:
    """Every identifier appearing in an annotation, however it is spelled.

    Crude on purpose, and the fifth private copy of this in the repository rather than an
    import of somebody's underscore-prefixed helper. `Callable[[Action], TypedResult[Entity]]`,
    `"Callable[..., object] | None"` and `collections.abc.Callable` all have to read the same,
    and a parser that understood the type algebra would be a second, subtly different opinion
    about what an annotation means. `brain.core.redaction._names_in` says the same thing about
    its own copy.
    """
    text = annotation.__name__ if isinstance(annotation, type) else str(annotation)
    return frozenset(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))


def entry_annotations() -> Mapping[str, object]:
    """What `rehearse` declares it may be handed, by parameter name.

    Read off the function rather than listed, so a parameter added tomorrow is checked today.
    """
    return {
        name: parameter.annotation
        for name, parameter in inspect.signature(rehearse).parameters.items()
    }


def rehearsal_gaps(
    *,
    annotations: Mapping[str, object] | None = None,
    take_type: type = Take,
    surface: Sequence[type] = REHEARSAL_SURFACE,
    reached: Iterable[Route] = REACHED_THE_TOOL,
    unreached: Iterable[Route] = DID_NOT_REACH_THE_TOOL,
    routes: Iterable[Route] = Route,
    source: str | None = None,
) -> tuple[str, ...]:
    """Everything about this rehearsal that would let it touch the world or compute a reach.

    Takes its inputs rather than reading this module's own constants, for the reason
    `brain.builder.publish.publish_gaps` and `brain.console.workspace.workspace_gaps` both
    give about theirs: a diagnostic that can only run against a healthy tree has nothing to
    report on today's data, so switching off any of its refusals changes nothing observable
    and every one of them survives a mutation. Calling it with no arguments is the deployment
    check and calling it with a constructed set is the test.
    """
    from brain.console.workspace import intersections_in

    gaps: list[str] = []

    declared = entry_annotations() if annotations is None else annotations
    for name, annotation in declared.items():
        found = sorted(_names_in(annotation) & NAMES_THAT_WOULD_REACH_A_SOURCE)
        if found:
            gaps.append(
                f"rehearse takes {name!r} as {found}, so a rehearsal can be handed something "
                f"that reaches a source and nothing recorded would stand between it and the "
                f"world. {THE_GATE_IS_REAL_AND_THE_WORLD_IS_ABSENT}"
            )

    fields: Mapping[str, Any] = getattr(take_type, "__dataclass_fields__", {})
    for name, declared_field in fields.items():
        found = sorted(_names_in(declared_field.type) & NAMES_THAT_WOULD_REACH_A_SOURCE)
        if found:
            gaps.append(
                f"{take_type.__name__}.{name} is {found}, so a take fetches its own answer "
                f"and the recording beside it is decoration. "
                f"{THE_GATE_IS_REAL_AND_THE_WORLD_IS_ABSENT}"
            )

    gaps.extend(
        f"{found} would hand the author the rows a rehearsal read, and a cassette does not "
        "make that safe: it makes the rows the author's own choice of recording, right up "
        "until somebody points the same report at a live run"
        for found in row_shaped_fields(surface)
    )

    priced = set(reached)
    unpriced = set(unreached)
    for route in routes:
        if route not in priced and route not in unpriced:
            gaps.append(
                f"{route.value} is neither priced nor unpriced, so a run taking it is costed "
                "at nothing and the measured figure silently stops counting a whole route"
            )
        if route in priced and route in unpriced:
            gaps.append(
                f"{route.value} is both priced and unpriced, so what a run cost depends on "
                "which set is read first"
            )

    text = inspect.getsource(sys.modules[__name__]) if source is None else source
    gaps.extend(
        f"line {line} intersects two entitlement sets, so the rehearsal works out the run "
        "reach rather than being handed one and checking it, which is a third copy of the "
        "central rule in the layer furthest from the gate"
        for line in intersections_in(text)
    )

    return tuple(gaps)
