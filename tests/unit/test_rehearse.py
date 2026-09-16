"""Rehearsing a built agent: the gate is the real one and the world is not there.

Three leaves, and the first two are the interesting pair because they pull against each
other. M20.3.1 wants the run put through the real gate, leash and redactor, so the tests below
drive `brain.gate.leash.govern` and `brain.core.redaction` and never a stand-in. M20.3.2 wants
no real side effect to fire, so the tests that matter most are the ones asserting there is
nowhere for one to fire from: no callable in the entry point's signature, no reader on a take,
no suspension on the way out. M20.3.4 is the measurement, and it is held against
`brain.ops.spend.preflight` rather than against itself.

Task ids: M20.3.1, M20.3.2, M20.3.4
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest

import brain.builder.rehearse as rehearse_module
from brain.builder.compose import BuilderError
from brain.builder.publish import Detail, Rehearsal, RehearsalOutcome
from brain.builder.rehearse import (
    DID_NOT_REACH_THE_TOOL,
    NAMES_THAT_WOULD_REACH_A_SOURCE,
    REACHED_THE_TOOL,
    REHEARSAL_SURFACE,
    REHEARSAL_SUSPENSION_PREFIX,
    RehearsalReport,
    Step,
    Take,
    entry_annotations,
    measured_cost,
    rehearsal_gaps,
    rehearse,
    shown_report,
    tool_calls_made,
)
from brain.console.workspace import intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.core.lane import Lane
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.leash import IDENTIFIER, Action, CheckName, Leash, LeashEntry, Route, govern
from brain.models.routing import Tier
from brain.ops.spend import NO_CORRECTION, Correction, CostInputs, preflight
from tests.fixtures.cassettes import CASSETTES, Source, for_source
from tests.fixtures.operation_ledger import MemoryLedger

# A date well outside any plausible wall clock in either direction is not what this file
# needs: the gate is handed `now` explicitly everywhere and nothing here has an expiry, so a
# fixed instant is a label rather than a clock. It is stated so the next reader does not
# "fix" it into the present.
NOW = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
CLEAN = RiskAssessment(score=0, matched=())

AGENT = "ag_desk"
PERSONA = "p_operator"
AUTHOR = "p_watcher"
TRACE = "tr_rehearsal"

UPDATE_STATUS = ToolDefinition(
    name="ticket.update_status",
    description="Set the status of a ticket",
    entity="ticket",
    required_capability="write:ticket.status",
    side_effect=SideEffect.WRITE,
    identity_mode=IdentityMode.DELEGATED,
)

CLOSE_CASE = ToolDefinition(
    name="ticket.close_case",
    description="Close a ticket",
    entity="ticket",
    required_capability="write:ticket.resolution",
    side_effect=SideEffect.WRITE,
    identity_mode=IdentityMode.DELEGATED,
)

POLICY = FieldPolicy(
    rules=(
        FieldRule.of("ticket", "status", "read:ticket.status", Classification.INTERNAL),
        FieldRule.of("ticket", "subject", "read:ticket.subject", Classification.INTERNAL),
    )
)


class Ticket(Entity):
    status: str = ""
    subject: str = ""


def entitlement(*capabilities: str, principal_id: str = PERSONA) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(
            Grant(capability=Capability(value=value), scope=Scope.unrestricted())
            for value in capabilities
        ),
    )


#: Everything the agent could ever reach. The ceiling, so the intersection is the persona's.
CEILING = entitlement(
    "write:ticket.status",
    "write:ticket.resolution",
    "read:ticket.status",
    principal_id=AGENT,
)

REPLAYED = TypedResult[Entity](
    records=(Ticket(entity="ticket", id="t_9", status="closed"),), source="recorded"
)

#: A real recording from the corpus `tests/invariants/test_cassettes.py` guards. Lark's
#: happy path, chosen because it is a 200 that carries a body rather than an empty one.
RECORDED = next(
    c for c in for_source(Source.LARK_BASE) if c.status == 200 and c.body.get("code") == 0
)


def action(*, tool: ToolDefinition = UPDATE_STATUS, fields: tuple[str, ...] = ()) -> Action:
    """One action with no touched fields, so the mask check permits and the redactor is the
    thing under test rather than the pre-flight mask."""
    return Action(
        agent_id=AGENT,
        tool=tool,
        target=tool.name,
        touched_fields=fields,
        row={"department": "support"},
    )


def take(
    *,
    tool: ToolDefinition = UPDATE_STATUS,
    replay: TypedResult[Entity] = REPLAYED,
    recording: object = RECORDED,
) -> Take:
    # The cassette is handed over as it stands. `Recording` is a protocol and `Cassette`
    # satisfies it, which is the whole of the reuse.
    return Take(action=action(tool=tool), recording=recording, replay=replay)  # type: ignore[arg-type]


def leash_at(rung: AutonomyTier, *, targets: tuple[str, ...] = ("ticket.update_status",)) -> Leash:
    return Leash(
        entries=tuple(
            LeashEntry(agent_id=AGENT, target=target, scope=Scope.unrestricted(), rung=rung)
            for target in targets
        )
    )


SHAPE = CostInputs(lane=Lane.TASK, tier=Tier.MAIN, tool_calls=0, retrieval_tokens=2_000, fan_out=1)
REHEARSAL = Rehearsal(agent_id=AGENT, persona_id=PERSONA, author_id=AUTHOR)


def run(
    takes: tuple[Take, ...] = (),
    *,
    caller: EntitlementSet | None = None,
    ceiling: EntitlementSet = CEILING,
    run_reach: EntitlementSet | None = None,
    leash: Leash | None = None,
    shape: CostInputs = SHAPE,
    correction: Correction = NO_CORRECTION,
    rehearsal: Rehearsal = REHEARSAL,
) -> RehearsalReport:
    reach = caller if caller is not None else entitlement("write:ticket.status")
    return rehearse(
        rehearsal,
        takes or (take(),),
        caller=reach,
        agent_ceiling=ceiling,
        run_reach=run_reach if run_reach is not None else reach.intersect(ceiling, NOW),
        policy=POLICY,
        leash=leash if leash is not None else leash_at(AutonomyTier.SHADOW),
        assessment=CLEAN,
        shape=shape,
        trace_id=TRACE,
        now=NOW,
        correction=correction,
    )


# ------------------------------------------------- M20.3.1 the gate is the real one
def test_the_rung_the_leash_says_is_the_rung_the_rehearsal_runs_at() -> None:
    """**The reconciliation, stated as a property.** The cheap way to stop a rehearsal acting
    is to pin it to SHADOW, and then the rehearsal previews a run the published agent will
    never make: the case worth rehearsing is the autonomous one.

    Delete this and somebody adds the pin, every test about rehearsals still passes, and the
    one outcome an author most needs to see stops being reachable."""
    autonomous = run(leash=leash_at(AutonomyTier.AUTONOMOUS))
    assisted = run(leash=leash_at(AutonomyTier.ASSISTED))
    shadow = run(leash=leash_at(AutonomyTier.SHADOW))

    assert [one.steps[0].route for one in (autonomous, assisted, shadow)] == [
        Route.EXECUTE,
        Route.SUSPEND,
        Route.SIMULATE,
    ]
    assert autonomous.steps[0].tier is AutonomyTier.AUTONOMOUS


def test_a_step_the_gate_refuses_is_reported_refused_and_by_which_check() -> None:
    """The gate's verdict is carried out rather than recomputed. A persona holding nothing the
    tool requires is stopped at the capability check, which is the first of the three.

    Delete this and a rehearsal can report every step as having run while the real gate would
    have refused it, which is the failure that looks most like success."""
    report = run(caller=entitlement("read:ticket.status"))

    assert report.steps[0].route is Route.REFUSED
    assert report.steps[0].refused_by is CheckName.CAPABILITY
    assert report.outcome.tools_reached == ()
    assert report.outcome.answered is False


def test_a_step_the_gate_permits_reaches_the_tool_and_is_named() -> None:
    """The positive sibling of the test above. A gate tested only by its refusals is satisfied
    by a rehearsal that refuses everything and reports a cost of nothing.

    Delete this and every refusal test passes against a rehearsal that never runs a step."""
    report = run()

    assert report.steps[0].route is Route.SIMULATE
    assert report.steps[0].refused_by is None
    assert report.outcome.tools_reached == ("ticket.update_status",)
    assert report.outcome.answered is True


def test_the_real_redactor_runs_and_says_what_this_persona_would_lose() -> None:
    """M20.3.1 names the redactor and this is it: a persona who may call the tool and may not
    read any field it returns loses the record whole, which is the record-level
    collapse `brain.core.redaction` exists for.

    Delete this and "the redactor ran" becomes a claim with nothing able to falsify it."""
    report = run(caller=entitlement("write:ticket.status"))

    # The record collapses, so the real redactor reports a record rather than the names of
    # the fields it would have lost: a withheld record has no fields left to name.
    assert report.steps[0].withheld_a_record is True
    assert report.steps[0].withheld == ()


def test_a_persona_who_may_read_the_field_loses_nothing() -> None:
    """The positive sibling. A redactor asserted only by what it removes is satisfied by one
    that removes everything, and a rehearsal reporting that would send an author to widen a
    grant that was never narrow.

    Delete this and the test above passes against a redactor that withholds unconditionally."""
    reads = ("write:ticket.status", "read:ticket.status", "read:ticket.subject")
    # The default ceiling never grants the subject, so a persona could hold every read and
    # still lose it. The positive case has to be a run whose reach may read the whole record.
    report = run(caller=entitlement(*reads), ceiling=entitlement(*reads, principal_id=AGENT))

    assert report.steps[0].withheld == ()
    assert report.steps[0].withheld_a_record is False


def test_a_persona_missing_one_read_loses_that_field_and_keeps_the_record() -> None:
    """The case an author acts on: the persona may read the record but not all of it, and
    the rehearsal names the one field that goes. It is the only test here where the
    redactor's answer is a field name, so it is what stops a step dropping those names while
    the record flag stays honest.

    Delete this and every step can report that a persona loses no field by name."""
    report = run(caller=entitlement("write:ticket.status", "read:ticket.status"))

    assert report.steps[0].withheld == ("ticket.subject",)
    assert report.steps[0].withheld_a_record is False


def test_the_redactor_is_not_run_for_a_step_that_called_nothing() -> None:
    """A refused step has no result. Reporting withheld fields for it would tell an author the
    persona could not see those fields, when what happened is that the persona could not make
    the call, and the two send them to different people.

    Delete this and a capability refusal starts reading as a field-policy problem."""
    report = run(caller=entitlement("read:ticket.status"))

    assert report.steps[0].route is Route.REFUSED
    assert report.steps[0].withheld == ()
    assert report.steps[0].withheld_a_record is False


def test_a_rehearsal_handed_another_persons_reach_is_refused() -> None:
    """`publish.reach_refusals` is the M20.3.3 gate and nothing called it until this module.
    A rehearsal run at the author's reach previews the author's own intersection and ships
    somebody else's.

    Delete this and the check goes back to being a function with no caller."""
    other = entitlement("write:ticket.status", principal_id=AUTHOR)
    report = run(caller=other, run_reach=other.intersect(CEILING, NOW))

    assert report.rehearsed is False
    assert report.steps == ()
    assert report.cost is None
    assert "different run" in report.refusals[0]


def test_a_reach_that_is_not_the_one_the_gate_computed_is_refused() -> None:
    """**The rehearsal is handed the run reach and never works it out**, so the only thing
    standing between the redactor and a different entitlement is this check: `decide` records
    the digest of the reach it used, and a mismatch means the mask check and the redactor were
    looking at two different reaches.

    Delete this and a rehearsal can redact at the persona's unnarrowed reach and report more
    visible than any real run would show."""
    # A grant the ceiling does not hold, so the reach the gate computes is genuinely narrower
    # than the caller's. Without it the caller and the intersection are the same set, the
    # "wrong" reach is the right one, and the guard is never asked anything.
    caller = entitlement("write:ticket.status", "read:ticket.subject")
    report = run(caller=caller, run_reach=caller)

    assert report.rehearsed is False
    assert report.steps == ()
    assert "two different entitlements" in report.refusals[0]


def test_a_rehearsal_of_nothing_is_refused_rather_than_reported_as_a_run() -> None:
    """An empty take list produces a report indistinguishable from a run the gate stopped at
    every step, and those are opposite findings.

    Delete this and an author whose takes failed to load reads "your agent reaches nothing"."""
    with pytest.raises(BuilderError, match="refused everywhere"):
        rehearse(
            REHEARSAL,
            (),
            caller=entitlement("write:ticket.status"),
            agent_ceiling=CEILING,
            run_reach=entitlement("write:ticket.status").intersect(CEILING, NOW),
            policy=POLICY,
            leash=leash_at(AutonomyTier.SHADOW),
            assessment=CLEAN,
            shape=SHAPE,
            trace_id=TRACE,
            now=NOW,
        )


# --------------------------------------------- M20.3.2 nothing outside the process moves
def test_nothing_the_rehearsal_is_handed_could_reach_a_source() -> None:
    """**The guarantee is a signature, not a body.** `govern` has to be given a `simulate` and
    an `execute`; the whole of M20.3.2 is that neither of them can come from outside this
    module, and the way to keep that is to have nowhere to put one.

    Delete this and a `reader` parameter added to make the rehearsal work against a live
    connector looks exactly like a convenience in review."""
    declared = entry_annotations()

    assert declared, "no annotations were read, so the absence below proves nothing"
    for name, annotation in declared.items():
        names = set(rehearse_module._names_in(annotation))
        assert not names & NAMES_THAT_WOULD_REACH_A_SOURCE, f"rehearse takes {name} as {annotation}"


def test_what_this_refuses_to_be_handed_is_what_the_gate_must_be_handed() -> None:
    """The constant anchored outside itself. `NAMES_THAT_WOULD_REACH_A_SOURCE` is only worth
    anything if it names what a live tool call actually arrives as, and the independent fact is
    `govern`'s own declaration for `simulate` and `execute`.

    Delete this and the frozenset can be renamed, emptied of the one entry that matters, or
    filled with plausible words that no signature in this repository uses, and every test
    above still passes."""
    parameters = inspect.signature(govern).parameters

    for side in ("simulate", "execute"):
        names = set(rehearse_module._names_in(parameters[side].annotation))
        assert names & NAMES_THAT_WOULD_REACH_A_SOURCE, (
            f"govern takes {side} as {parameters[side].annotation}, and nothing in "
            f"NAMES_THAT_WOULD_REACH_A_SOURCE would refuse a parameter of that shape"
        )


def test_an_autonomous_rehearsal_executes_a_recording_and_names_which_one() -> None:
    """The execute route is the one M20.3.2 exists for, and it is a normal outcome here. What
    makes it safe is not that the route was avoided but that the only thing on the far side of
    it is a value, and the recording's own id is what lets a reader check that.

    Delete this and a rehearsal can report EXECUTE without anything tying the answer back to a
    recorded exchange, which is the hand-built fixture the corpus was recorded to replace."""
    report = run(leash=leash_at(AutonomyTier.AUTONOMOUS))

    assert report.steps[0].route is Route.EXECUTE
    assert report.steps[0].recording_id == RECORDED.cid
    assert RECORDED.cid in {c.cid for c in CASSETTES}


def test_a_suspension_raised_during_a_rehearsal_never_leaves_the_function() -> None:
    """**The side effect a cassette does not stop.** An assisted agent suspends, and a
    suspension that reached a queue would put an approval in front of a person for an action
    nobody is taking. A person's queue is outside this process.

    Delete this and the report can grow a `suspension` field, which reads as useful and is the
    one way a rehearsal fires something a recording cannot prevent."""
    report = run(leash=leash_at(AutonomyTier.ASSISTED))

    assert report.steps[0].route is Route.SUSPEND
    carried = {
        name for holder in REHEARSAL_SURFACE for name in getattr(holder, "__dataclass_fields__", {})
    }
    assert not {"suspension", "approval", "record", "governed"} & carried


def test_the_suspension_id_a_rehearsal_builds_cannot_be_mistaken_for_a_minted_one() -> None:
    """The constant anchored against two facts outside it: the grammar `leash.IDENTIFIER`
    accepts, so the value cannot become something pydantic refuses at the moment a rehearsal
    suspends, and the shape `uuid4().hex` produces, so one that somehow escaped into a store
    does not read as a real suspension.

    Delete this and the prefix can be changed to a hex string, or to a character the id pattern
    rejects, and the failure arrives only on the assisted path."""
    import re
    from uuid import uuid4

    built = f"{REHEARSAL_SUSPENSION_PREFIX}.0"

    assert re.match(IDENTIFIER, built), f"{built} is not an identifier the leash would accept"
    assert not re.fullmatch(r"[0-9a-f]{32}", REHEARSAL_SUSPENSION_PREFIX)
    assert len(uuid4().hex) != len(REHEARSAL_SUSPENSION_PREFIX)


def test_a_take_whose_recording_has_no_id_is_refused() -> None:
    """A take that names no recording is a take whose answer somebody typed, which is the mock
    the corpus exists to replace and is indistinguishable from a replay once it is in a report.

    Delete this and the recording beside a take becomes decoration."""

    class Unnamed:
        cid = "  "
        status = 200
        body = None

    with pytest.raises(BuilderError, match="traced back to the corpus"):
        Take(action=action(), recording=Unnamed(), replay=REPLAYED)


def test_a_replay_tagged_with_another_object_is_refused() -> None:
    """The redactor asks the field policy about the entity on the record. A replay tagged with
    something else would be redacted against another object's rules, the walk would run, names
    would come back, and every one of them would be about the wrong record.

    Delete this and a rehearsal reports a confident verdict about a policy it never consulted."""
    other = TypedResult[Entity](records=(Ticket(entity="invoice", id="i_1"),))

    with pytest.raises(BuilderError, match="answer about the wrong object"):
        take(replay=other)


def test_the_recorded_corpus_drives_the_rehearsal_as_it_stands() -> None:
    """**The reuse, asserted rather than described.** `Recording` is a protocol and
    `tests.fixtures.cassettes.Cassette` satisfies it with no adapter, so a rehearsal runs
    against the corpus the invariant suite already guards instead of a second recording type.

    Delete this and the protocol can drift from the corpus, at which point somebody writes the
    translation layer and then the second corpus."""
    failures = [c for c in CASSETTES if c.status >= 400]

    assert failures, "no failing cassette was read, so this drove nothing"
    report = run(takes=(take(recording=failures[0]),))

    assert report.steps[0].recording_id == failures[0].cid


def test_this_module_cannot_wait_for_anything_and_imports_no_transport() -> None:
    """The structural half of `THE_GATE_IS_REAL_AND_THE_WORLD_IS_ABSENT`, checked the way
    `brain.ops.spend` checks its own estimator: by parsing the module. A rehearsal that could
    await something is a rehearsal with an I/O path, whatever its signature says.

    Delete this and an `async def` helper added for a live preview passes review."""
    source = Path(rehearse_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert not [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
    imported = {
        name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names
    } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported, "nothing was read, so the absence below proves nothing"
    for banned in ("httpx", "redis", "psycopg", "sqlalchemy", "brain.connectors"):
        assert not [one for one in imported if one.startswith(banned)], f"{banned} is imported"


def test_the_rehearsal_computes_no_reach_of_its_own() -> None:
    """`E_run` has one implementation and two call sites, both in the gate. A builder working
    it out for itself would be a third copy in the layer furthest from the gate, and
    `tests/invariants/test_single_implementation.py` pins the list it would have to join.

    Delete this and the run reach can quietly be computed here, which is the exact drift that
    file was written after."""
    source = Path(rehearse_module.__file__).read_text(encoding="utf-8")

    assert "intersect" in source, "nothing was read, so the absence below proves nothing"
    assert intersections_in(source) == ()


# ------------------------------------------------------- M20.3.4 the measured cost
def test_the_cost_is_the_figure_a_real_run_would_be_admitted_at() -> None:
    """**The anchor is outside the rehearsal.** `spend.preflight` is what admits a real
    request, so the rehearsal's figure is worth something exactly when it equals the figure the
    pre-flight would compute for the same run.

    Delete this and the rehearsal can price a run with its own arithmetic, and the first
    symptom is a budget refusing work a rehearsal said was affordable."""
    report = run(leash=leash_at(AutonomyTier.AUTONOMOUS))
    assert report.cost is not None

    expected = preflight(
        CostInputs(
            lane=SHAPE.lane,
            tier=SHAPE.tier,
            tool_calls=1,
            retrieval_tokens=SHAPE.retrieval_tokens,
            fan_out=SHAPE.fan_out,
        ),
        allowances=(),
        # An automation is the run a rehearsal predicts. With no allowances `preflight`
        # admits at the top and never consults the class, so the figure cannot depend on it.
        traffic=TrafficClass.AUTOMATION,
    )
    assert report.cost.minor == expected.estimate_minor
    assert report.cost.minor > 0


def test_the_tool_count_priced_is_the_gate_s_and_not_the_number_of_takes() -> None:
    """The one input a form cannot know. Three takes, one of which the gate refuses, is two
    round trips, and pricing three would overstate every run with a refusal in it.

    Delete this and the measured figure becomes a count of what somebody drew rather than a
    measurement of what ran."""
    takes = (take(), take(tool=CLOSE_CASE), take())
    report = run(
        takes=takes,
        leash=leash_at(AutonomyTier.SHADOW, targets=("ticket.update_status", "ticket.close_case")),
    )

    assert len(report.steps) == 3
    assert tool_calls_made(report.steps) == 2
    assert report.cost is not None
    assert report.cost.inputs.tool_calls == 2


def test_a_persona_holding_less_rehearses_a_cheaper_run() -> None:
    """The property that ties the measurement to the gate: the cost moves because the gate
    refused a step, not because anybody typed a smaller number.

    Delete this and the cost stops being evidence about the run and becomes a restatement of
    the shape it was handed."""
    takes = (take(), take(tool=CLOSE_CASE))
    leash = leash_at(AutonomyTier.SHADOW, targets=("ticket.update_status", "ticket.close_case"))

    wide = run(
        takes=takes,
        caller=entitlement("write:ticket.status", "write:ticket.resolution"),
        leash=leash,
    )
    narrow = run(takes=takes, caller=entitlement("write:ticket.status"), leash=leash)

    assert wide.cost is not None
    assert narrow.cost is not None
    assert narrow.cost.minor < wide.cost.minor


def test_the_correction_a_real_run_carries_moves_the_rehearsals_figure() -> None:
    """A rehearsal priced with no correction while production runs above one understates by
    exactly that factor, and it understates in the direction that admits work.

    Delete this and the correction parameter can be dropped, and the rehearsal quietly stops
    agreeing with the pre-flight it is meant to predict."""
    learnt = Correction(factor=2.0, samples=40, reason="forty runs came in at twice their estimate")

    plain = run(leash=leash_at(AutonomyTier.AUTONOMOUS))
    corrected = run(leash=leash_at(AutonomyTier.AUTONOMOUS), correction=learnt)

    assert plain.cost is not None
    assert corrected.cost is not None
    assert corrected.cost.minor > plain.cost.minor
    assert corrected.cost.factor == learnt.factor


def test_the_routes_that_cost_something_are_the_routes_the_gate_answers_on() -> None:
    """**The constant anchored against the gate's own behaviour.** `REACHED_THE_TOOL` is only
    right if it is exactly the set of routes on which `govern` hands a result back to the agent
    loop, and that is measured by running the gate to each route rather than asserted.

    Delete this and a route can be moved between the two sets, every cost test still passes
    because it still produces a number, and a whole route stops being counted."""
    answered: set[Route] = set()
    for leash, caller in (
        (leash_at(AutonomyTier.SHADOW), entitlement("write:ticket.status")),
        (leash_at(AutonomyTier.ASSISTED), entitlement("write:ticket.status")),
        (leash_at(AutonomyTier.AUTONOMOUS), entitlement("write:ticket.status")),
        (leash_at(AutonomyTier.AUTONOMOUS), entitlement("read:ticket.status")),
    ):
        governed = govern(
            action(),
            caller=caller,
            agent_ceiling=CEILING,
            policy=POLICY,
            leash=leash,
            assessment=CLEAN,
            trace_id=TRACE,
            now=NOW,
            simulate=lambda _: REPLAYED,
            execute=lambda _: REPLAYED,
            ledger=MemoryLedger(),
        )
        if governed.for_agent() is not None:
            answered.add(governed.route)

    assert answered == set(REACHED_THE_TOOL)
    assert set(Route) - answered == set(DID_NOT_REACH_THE_TOOL)


def test_the_estimator_refuses_a_shape_that_could_not_have_made_a_call() -> None:
    """The rehearsal does not catch the estimator's own refusals, and this is the one that
    fires: a fast lane runs no model and holds no tool, so a measured tool call against a
    fast-lane shape is a contradiction rather than a cheaper run.

    Delete this and a contradictory shape is priced at zero and reported as a run."""
    from brain.ops.spend import SpendError

    fast = CostInputs(lane=Lane.FAST, tier=Tier.NONE)
    reached = Step(
        tool="ticket.update_status",
        recording_id=RECORDED.cid,
        route=Route.SIMULATE,
        tier=AutonomyTier.SHADOW,
        refused_by=None,
    )

    assert measured_cost(fast, ()).minor == 0
    with pytest.raises(SpendError):
        measured_cost(fast, (reached,))


# ------------------------------------------------------ what the author is shown
def test_an_author_who_cannot_read_grants_is_shown_no_steps_and_no_cost() -> None:
    """The cost moves with how many steps the gate let through, so it is a count of what a
    persona was refused wearing a shape nobody reads as a count. It is emptied with the steps
    rather than rounded or summarised.

    Delete this and the narrow detail level hands back a number that differs between personas,
    which is the subtraction the whole detail split exists to prevent."""
    report = run()
    narrowed = shown_report(report, Detail.OUTCOME)

    assert narrowed.steps == ()
    assert narrowed.cost is None
    assert narrowed.outcome.tools_reached == ()
    assert narrowed.outcome.answered is report.outcome.answered


def test_an_author_who_can_read_grants_is_shown_the_steps_and_the_figure() -> None:
    """The positive sibling. A detail gate tested only by what it hides is satisfied by one
    that hides everything, and a rehearsal that shows nothing to anybody is not a rehearsal.

    Delete this and the gate above can be tightened to a constant."""
    report = run()

    assert shown_report(report, Detail.PER_TOOL) == report
    assert report.cost is not None
    assert report.steps


def test_a_refusal_survives_at_both_detail_levels() -> None:
    """A refusal says the rehearsal was set up wrongly, which is a fact about the author's own
    request. Withheld, it leaves them staring at an empty report with no way to tell it from a
    run that happened and found nothing.

    Delete this and a mis-paired reach reads as an agent that reaches nothing."""
    other = entitlement("write:ticket.status", principal_id=AUTHOR)
    report = run(caller=other, run_reach=other.intersect(CEILING, NOW))

    assert shown_report(report, Detail.OUTCOME).refusals == report.refusals
    assert report.refusals


# ------------------------------------------------------------------- the diagnostic
def test_this_rehearsal_has_no_gaps() -> None:
    """The deployment check, and the positive half of every test below it. A diagnostic whose
    findings are only ever asserted on doctored inputs proves nothing about the module.

    Delete this and the module can acquire any of the faults below without anything saying so."""
    assert rehearsal_gaps() == ()


def test_the_diagnostic_reports_an_entry_point_that_could_be_handed_a_reader() -> None:
    """Delete this and the signature check is a loop nobody has watched succeed at finding
    anything, which is this repository's most common defect."""
    found = rehearsal_gaps(annotations={"reader": "PageReader"})

    assert len(found) == 1
    assert "reaches a source" in found[0]


def test_the_diagnostic_reports_a_take_that_could_fetch_its_own_answer() -> None:
    """The second door. A take holding a reader makes the recording beside it decoration, and
    the signature check would not see it because it is not a parameter.

    Delete this and the two doors become one."""

    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Fetching:
        source: object

    Fetching.__dataclass_fields__["source"].type = "Callable[[Action], TypedResult[Entity]]"
    found = rehearsal_gaps(take_type=Fetching)

    assert len(found) == 1
    assert "fetches its own answer" in found[0]


def test_the_diagnostic_reports_a_report_type_that_could_carry_rows() -> None:
    """`publish.row_shaped_fields` is applied to this module's own return types rather than
    copied, so there is one list of the field names that would hand an author somebody else's
    data.

    Delete this and the report can grow a `records` field and only the publish gate would
    notice, which is a different set of types."""

    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Leaky:
        rows: tuple[str, ...] = ()

    found = rehearsal_gaps(surface=(Leaky,))

    assert len(found) == 1
    assert "rows a rehearsal read" in found[0]


def test_the_diagnostic_reports_a_route_nobody_decided_the_price_of() -> None:
    """A fifth route would land in neither set and be costed at nothing, so the measured figure
    would quietly stop counting a whole class of run.

    Delete this and the two sets can drift from `Route` without anything failing."""
    found = rehearsal_gaps(reached=frozenset({Route.SIMULATE}), unreached=frozenset())

    assert len(found) == 3
    assert all("neither priced nor unpriced" in one for one in found)


def test_the_diagnostic_reports_a_route_that_is_both_priced_and_not() -> None:
    """The other half. A route in both sets makes what a run cost depend on which set is read
    first, which is the evaluation-order failure this repository refuses everywhere else.

    Delete this and the overlap check is unreachable."""
    found = rehearsal_gaps(
        reached=frozenset(Route), unreached=frozenset(Route), routes=(Route.SIMULATE,)
    )

    assert len(found) == 1
    assert "both priced and unpriced" in found[0]


def test_the_diagnostic_reports_a_rehearsal_that_works_out_its_own_reach() -> None:
    """The check that would catch the third copy of the central rule arriving here.

    Delete this and `intersections_in` is called on a module that has never had an
    intersection in it, which is a test that cannot fail."""
    found = rehearsal_gaps(source="def f(a, b):\n    return a.intersect(b)\n")

    assert len(found) == 1
    assert "third copy of the central rule" in found[0]


def test_an_outcome_is_all_the_report_is_when_the_rehearsal_did_not_run() -> None:
    """A refused rehearsal must not look like a finished one. `rehearsed` is the flag that
    separates them, and both halves of it are asserted here because a property that is always
    True is not a property.

    Delete this and an author cannot tell a rehearsal that was refused from one that ran."""
    assert run().rehearsed is True
    assert (
        RehearsalReport(
            outcome=RehearsalOutcome(agent_id=AGENT, persona_id=PERSONA, answered=False),
            refusals=("something",),
        ).rehearsed
        is False
    )
