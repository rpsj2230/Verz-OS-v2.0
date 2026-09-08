"""A kill after any durable write leaves at most one side effect behind, at every one of them.

M17.3.5 already proves this, and it proves it at eleven points somebody typed out.
`tests/unit/test_idempotency.py::CRASH_POINTS` is that list, and it is right today and
silently short the morning after somebody adds a seventh state: the parametrisation stays
green, the report says eleven cases passed, and the state nobody had thought about is the one
that is not in it. **A property that has to hold at every boundary cannot be tested at a list
of boundaries.**

So this file asks `brain.ops.crash.side_effect_boundaries` where the boundaries are, and that
function reads them out of the transition tables themselves. Three claims are asserted about
the enumeration before anything is asserted with it, because a derived list that has quietly
gone empty passes every property in this file:

- the record boundaries are exactly the edge set of the live table, both directions;
- the write that created the record is in there too, which no edge describes and which the
  typed list opens with;
- and feeding the derivation a machine this repository does not have produces boundaries for
  it, which is what "derived rather than typed" means when it is checked rather than claimed.

**What is not covered has not changed and is not weakened by any of this.**
`brain.ops.idempotency.WHAT_THE_CRASH_MODEL_DOES_NOT_COVER` says it: no process is killed
anywhere here, the store has to make the write durable and the key unique, the source has to
honour the key it is sent, and a source that refuses after having acted has lied. This is
at-most-once under a model of a crash, over every boundary the model has.

Task ids: M30.4.8
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType

from brain.connectors.throttle import CallOutcome
from brain.ops.crash import (
    NOTHING_HAPPENED,
    Boundary,
    Crossing,
    Machine,
    durable_machines,
    side_effect_boundaries,
    verify_once,
)
from brain.ops.idempotency import (
    ALLOWED_TRANSITIONS,
    RESUME_PLAN,
    Disposition,
    Operation,
    OperationState,
    Verification,
    derive_key,
    resume,
    state_after_call,
)

#: The machine this file is about, named by the module that declares it rather than by the
#: enum, so a second machine keyed on the same states could not be silently substituted.
OPERATION_MACHINE = "brain.ops.idempotency.ALLOWED_TRANSITIONS"

KEY = derive_key(principal_id="u_1", tool="xero.create_invoice", intent_ref="turn_1")


def an_operation(state: OperationState) -> Operation:
    return Operation(
        key=KEY,
        connector="xero",
        tool="xero.create_invoice",
        principal_id="u_1",
        intent_ref="turn_1",
        state=state,
    )


@dataclass
class Source:
    """A source that has, or has not, already been acted on, and counts what we do to it.

    `landed` is the axis a recovering worker cannot observe and must therefore never assume.
    `issued` counts calls made by *this* run, so the exactly-once assertion is about what
    recovery did rather than about the world's total.
    """

    landed: bool
    issued: int = field(default=0)

    def issue(self, operation: Operation) -> Operation:
        """The write-ahead, the call, and the recorded outcome, in that order.

        The order is the whole of `THE_RECORD_IS_WRITTEN_BEFORE_THE_CALL`: the record reaches
        `SENT` before anything leaves, so a process dying in the middle of this is a process
        that left a record saying a side effect may exist.
        """
        sent = operation.advanced(OperationState.SENT)
        self.issued += 1
        self.landed = True
        return sent.advanced(state_after_call(CallOutcome.OK))

    def read_back(self, _: Operation) -> object:
        return Verification.FOUND if self.landed else Verification.ABSENT


def recover(operation: Operation, source: Source) -> Operation:
    """Drive a recovering worker from one record until it settles.

    Bounded by the size of the state graph rather than by a number, so a machine that grew a
    state grows the bound with it, and a plan that cycles is a hang this reports as a failure
    instead of one that runs for ever.
    """
    current = operation
    for _ in range(len(OperationState) + 2):
        plan = resume(current)
        current = plan.operation
        if plan.disposition is Disposition.ISSUE:
            current = source.issue(current)
        elif plan.disposition is Disposition.VERIFY:
            current = verify_once(current, source.read_back)
        else:
            return current
    msg = f"recovery from {operation.state} did not settle"
    raise AssertionError(msg)


def operation_boundaries() -> tuple[Boundary, ...]:
    return tuple(one for one in side_effect_boundaries() if one.machine == OPERATION_MACHINE)


def landings(after: str) -> tuple[bool, ...]:
    """Whether the side effect may already have happened, read off the recovery plan.

    Derived rather than paired by hand, which is what `CRASH_POINTS` does and is the half of
    that list that would have to be re-thought for every state added. A state a worker resumes
    by issuing, or by stopping, is one where nothing happened: `ISSUE` means nothing has left
    and `STOP` means it definitely did not land. A state it resumes by asking is one where
    nobody knows, so both worlds are possible. Anything else is a state that says it happened.
    """
    action = RESUME_PLAN[OperationState[after]][1]
    if action is Disposition.VERIFY:
        return (False, True)
    if action.name in NOTHING_HAPPENED:
        return (False,)
    return (True,)


def test_the_record_boundaries_are_exactly_the_edges_of_the_live_transition_table() -> None:
    """Delete this and the enumeration below can drift from the table it claims to read.

    Both directions, because each failure is silent in its own way. An edge with no boundary
    is a crash point the property is never asserted at, which is the defect a typed list has.
    A boundary with no edge is an invented crash point, which makes the suite red for a
    transition the machine cannot make and trains whoever reads it to widen the derivation
    until it goes green.
    """
    derived = {
        (one.before, one.after) for one in operation_boundaries() if one.crossing is Crossing.RECORD
    }
    declared = {
        (state.name, onward.name)
        for state, onwards in ALLOWED_TRANSITIONS.items()
        for onward in onwards
    }
    assert derived == declared


def test_the_write_that_created_the_record_is_a_boundary_although_no_edge_describes_it() -> None:
    """Delete this and the first line of `CRASH_POINTS` has no derived counterpart.

    A process can die between writing the record and issuing anything, and `PENDING` is the
    target of no edge at all, so an enumeration built from the edge set alone would not
    contain it. That case is not a curiosity: it is the one where recovery has to go on and
    *do* the work, which is the positive half of exactly-once.
    """
    created = [one for one in operation_boundaries() if one.crossing is Crossing.CREATE]
    assert [one.after for one in created] == [OperationState.PENDING.name]
    assert created[0].before == ""
    assert OperationState.PENDING not in {
        onward for onwards in ALLOWED_TRANSITIONS.values() for onward in onwards
    }


def test_every_state_of_the_machine_is_a_boundary_a_kill_can_land_in() -> None:
    """Delete this and the derivation can go short by a state with nothing noticing.

    The equality is what matters rather than the count. A state that no write can land in is
    a state no crash can leave behind, and if one ever appears it is either unreachable, which
    is a defect in the table, or the derivation has stopped seeing an edge.
    """
    assert {one.after for one in operation_boundaries()} == {state.name for state in OperationState}


def test_a_machine_this_repository_does_not_have_still_produces_boundaries() -> None:
    """Delete this and "derived rather than typed" becomes a claim about two known tables.

    Everything above is consistent with an enumeration hard-coded to the operation machine.
    This hands the derivation a table nobody has written, with a state and an edge that do not
    exist in this repository, and watches the boundary set grow to fit it: the create write,
    every edge, and the call derived as the step from nothing-issued to nobody-knowing.
    """
    invented = Machine(
        module="somewhere.else",
        symbol="ALLOWED_TRANSITIONS",
        kind="somewhere.else.Payment",
        states=("DRAFT", "PLACED", "DOUBTFUL", "CLEARED"),
        start="DRAFT",
        edges=(("DRAFT", "PLACED"), ("PLACED", "CLEARED"), ("PLACED", "DOUBTFUL")),
        terminal=frozenset({"CLEARED"}),
        plan=MappingProxyType(
            {
                "DRAFT": ("DRAFT", "ISSUE"),
                "PLACED": ("DOUBTFUL", "VERIFY"),
                "DOUBTFUL": ("DOUBTFUL", "VERIFY"),
                "CLEARED": ("CLEARED", "DONE"),
            }
        ),
        plan_from="somewhere.else.RESUME_PLAN",
    )
    found = side_effect_boundaries([invented])

    assert [(one.crossing, one.before, one.after) for one in found] == [
        (Crossing.CREATE, "", "DRAFT"),
        (Crossing.RECORD, "DRAFT", "PLACED"),
        (Crossing.EFFECT, "DRAFT", "PLACED"),
        (Crossing.RECORD, "PLACED", "CLEARED"),
        (Crossing.RECORD, "PLACED", "DOUBTFUL"),
    ]


def test_a_kill_after_any_boundary_leaves_at_most_one_side_effect() -> None:
    """M30.4.8, asserted at every boundary the code has rather than at eleven somebody typed.

    Each case is a process that died with this write committed, so recovery starts from the
    state the write landed in, paired with both worlds the record cannot distinguish between
    where the plan admits both. What is asserted at every one of them is the same three
    things: recovery issues at most once, it never repeats an effect that had already landed,
    and it leaves the record settled rather than parked.

    **A loop and not a parametrisation, and that is not a style preference.** Parametrising
    over a derived list calls the derivation during collection, so a change that breaks it
    breaks collection, and a broken collection is not a failing test: it exits non-zero with
    no `FAILED path::name` line, which is exactly the reading `brain.ops.mutation` refuses to
    score as a catch. Ten mutations of `brain.ops.crash` came back as crashes rather than
    catches for that reason, and a mutation table full of crashes is a table that has stopped
    measuring anything. The boundary is named in every assertion instead.

    Delete this and the exactly-once claim rests on a hand-written list of crash points that
    a new state does not appear in.
    """
    boundaries = operation_boundaries()
    assert boundaries, "the derivation found no boundaries, so this asserts nothing"
    for boundary in boundaries:
        for landed in landings(boundary.after):
            source = Source(landed=landed)
            settled = recover(an_operation(OperationState[boundary.after]), source)

            assert source.issued <= 1, f"{boundary}: recovery issued more than one side effect"
            if landed:
                assert source.issued == 0, f"{boundary}: the effect had happened and was repeated"
            assert settled.is_settled, f"{boundary}: recovery left the operation unsettled"


def test_a_kill_before_anything_was_issued_still_gets_the_work_done() -> None:
    """The positive half, and without it every assertion above is satisfied by a recovery that
    refuses everything.

    A boundary the plan resumes by issuing is one where the world is unchanged, and the
    correct answer there is not "do nothing", it is "do it, once". Asserted at every such
    boundary rather than at the one that exists today, so a second issuing state has to be
    right about this too.

    A loop rather than a parametrisation, because this one *filters* the boundary set and an
    empty parametrised list is collected as no tests at all and reported green. The equality
    checks above catch the whole set going empty and would not catch this subset going empty,
    so the non-emptiness is asserted here, in the test that depends on it.

    Delete this and `resume` returning `STOP` for every state passes the whole file.
    """
    issuing = [
        one
        for one in operation_boundaries()
        if RESUME_PLAN[OperationState[one.after]][1] is Disposition.ISSUE
    ]
    assert issuing, "no boundary resumes by issuing, so nothing here would ever do the work"
    for boundary in issuing:
        source = Source(landed=False)
        settled = recover(an_operation(OperationState[boundary.after]), source)
        assert source.issued == 1, boundary
        assert settled.state is OperationState.SUCCEEDED, boundary


def test_the_boundary_set_covers_every_machine_this_repository_declares() -> None:
    """Delete this and a second state machine can arrive with no boundaries enumerated for it.

    The parametrised properties above are about the operation machine, because it is the one
    that holds a side effect. This is the check that the enumeration itself is not narrower
    than the tree: every machine `durable_machines` found contributes boundaries, so a third
    one arriving with none is a discovery that silently produced nothing.
    """
    machines = durable_machines()
    assert machines, "nothing was discovered, so every property in this file is vacuous"
    covered = {one.machine for one in side_effect_boundaries()}
    assert covered == {one.name for one in machines}
