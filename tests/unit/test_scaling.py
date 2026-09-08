"""Scaling triggers are anchored, and source fan-out is bounded by the budgets that already
exist (M36.1.1.4, M36.1.2.4, M36.1.3.3, M36.1.4.3, M36.2.1.3, M36.2.3.1, M36.2.3.2).

The module's central claim is that there is nowhere in it to write a number somebody liked.
Half of these tests are that claim: every threshold is asserted against the value in the other
module it came from, never against a copy declared here, so a mutation of either side fails
rather than moving both.

The other half is the claim that the module builds nothing twice. The source-call graph is
`brain.connectors.federation`'s and the sharing key is `brain.gate.cache_key`'s, and two tests
assert that this module points at those objects rather than at objects of its own, because the
first draft declared a second `SourceCall`, a second plan, a second critical path and a second
key. What is genuinely added is contention, and the tests for it turn on the one case
federation cannot see: a wave that cannot all start at once.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass, fields
from pathlib import Path

import pytest

from brain.connectors.federation import (
    FEDERATION_TIMEOUT_MS,
    CallBudget,
    FanOutPlan,
    FlightRole,
    SourceCall,
    flight_key,
)
from brain.gate.cache_key import CacheKeyParts, cache_key, is_volatile
from brain.ops import scaling
from brain.ops.admission import (
    Budget,
    CapacityProfile,
    CapacityState,
    ClassPools,
    Resource,
    WorkloadClass,
    little_law_concurrency,
    pools_for,
    seed_budgets,
    seed_profiles,
)
from brain.ops.partitioning import PARTITION_INTERVAL, longest_days
from brain.ops.reliability import ANSWER_P95_MS
from brain.ops.scaling import (
    HOST_ANCHOR,
    PARTITION_ANCHOR,
    REPORT_ANCHOR,
    TRIGGERS,
    ScalingError,
    ScalingMove,
    ScalingObservable,
    ScalingTrigger,
    ThresholdAnchor,
    ThresholdBasis,
    admitted_from,
    calls_in,
    coalescing_gaps,
    contended_critical_path_ms,
    contention_ms,
    fanout_refusals,
    host_split_is_due,
    implied_global_ceiling,
    may_share,
    partitioning_is_due,
    replica_headroom,
    replica_is_due,
    report_is_due,
    rounds_for,
    scaling_gaps,
    share_refusals,
    share_role,
    trigger_gaps,
    triggers_for,
    unanchored,
)
from brain.ops.telemetry import LEDGER_RETENTION_DAYS

REACH = "a" * 32
OTHER_REACH = "b" * 32


def _anchor(**overrides: object) -> ThresholdAnchor:
    base: dict[str, object] = {
        "source": "brain.ops.reliability.ANSWER_P95_MS",
        "value": 1.0,
        "unit": "ms",
        "because": "a declared figure somewhere else",
    }
    base.update(overrides)
    return ThresholdAnchor(**base)  # type: ignore[arg-type]


def _trigger(**overrides: object) -> ScalingTrigger:
    base: dict[str, object] = {
        "move": ScalingMove.MATERIALISED_REPORTS,
        "observable": ScalingObservable.REPORT_P95_MS,
        "basis": ThresholdBasis.FROM_A_DECLARED_FIGURE,
        "unit": "ms",
        "because": "because a screen is waiting",
        "anchor": _anchor(),
    }
    base.update(overrides)
    return ScalingTrigger(**base)  # type: ignore[arg-type]


def _profile(peak: float, service: float = 4.0) -> CapacityProfile:
    return CapacityProfile(
        name="test",
        peak_arrivals_per_second=peak,
        mean_service_seconds=service,
        reason="a sizing built for one assertion",
    )


# --------------------------------------------------------------------------- the anchors
def test_the_report_threshold_is_the_answer_lanes_promise_and_not_the_leafs_two_seconds():
    """Delete this and two seconds can be written back in, which is the number M36.1.3.3 asks
    for and which nothing in this repository derives. The threshold is asserted against
    `brain.ops.reliability.ANSWER_P95_MS` so a mutation of the anchor here fails rather than
    moving both sides of the comparison."""
    assert REPORT_ANCHOR.value == float(ANSWER_P95_MS)
    assert REPORT_ANCHOR.value != 2_000.0


def test_the_partition_threshold_is_the_interval_the_other_module_derived():
    """Delete this and the trigger's number stops following the partition scheme. If the backup
    window changed and the interval moved to weekly, this trigger would still be comparing a
    retained window against thirty-one days."""
    assert PARTITION_ANCHOR.value == float(longest_days(PARTITION_INTERVAL))


def test_the_host_threshold_is_a_breach_count_and_not_a_size_in_mebibytes():
    """Delete this and somebody writes a memory figure here, which would be a second answer to
    whether a profile fits and would disagree with `brain.ops.wiring` the first time the host
    was re-measured."""
    assert HOST_ANCHOR.value == 0.0
    assert HOST_ANCHOR.unit == "breaches"


def test_a_threshold_is_the_anchored_value_times_the_stated_multiple():
    """Delete this and `multiple` becomes decoration, with the threshold silently equal to the
    anchor whatever the table says."""
    assert _trigger(anchor=_anchor(value=250.0), multiple=4.0).threshold == 1_000.0
    assert _trigger(anchor=_anchor(value=250.0)).threshold == 250.0


def test_a_trigger_nobody_anchored_carries_no_threshold_at_all():
    """Delete this and an unanchored trigger could acquire a number, which is the whole failure
    the basis exists to make visible: a figure in the table that nobody can derive reads exactly
    like one that was measured."""
    open_question = _trigger(basis=ThresholdBasis.NOT_ANCHORED, anchor=None)
    assert open_question.threshold is None


# ------------------------------------------------------------------------- the validators
def test_an_anchor_with_no_source_cannot_be_built():
    """Delete this and an anchor becomes a number with a paragraph beside it, which is the
    arrangement `brain.ops.wiring.HOST_HEADROOM_MIB` was in while it was wrong."""
    for blank in ("", " "):
        with pytest.raises(ScalingError, match="no source"):
            _anchor(source=blank)


def test_an_anchor_with_no_unit_cannot_be_built():
    """Delete this and a threshold in milliseconds can be compared against a reading in seconds,
    which is a trigger that fires a thousand times too late and looks configured."""
    for blank in ("", " "):
        with pytest.raises(ScalingError, match="states no unit"):
            _anchor(unit=blank)


def test_an_anchor_that_says_nothing_about_why_cannot_be_built():
    """Delete this and an anchor can point at any figure that happens to be nearby. The reason
    is what a reviewer checks the pointing against."""
    for blank in ("", " "):
        with pytest.raises(ScalingError, match="says nothing about why"):
            _anchor(because=blank)


def test_a_trigger_with_no_unit_cannot_be_built():
    """Delete this and the observable and the threshold can be in different units with nothing
    on the row to say so."""
    for blank in ("", " "):
        with pytest.raises(ScalingError, match="states no unit"):
            _trigger(unit=blank)


def test_a_trigger_that_says_nothing_about_why_cannot_be_built():
    """Delete this and a trigger joins every other threshold nobody can explain, which is the
    one that gets raised the first time it fires inconveniently."""
    for blank in ("", " "):
        with pytest.raises(ScalingError, match="says nothing about why"):
            _trigger(because=blank)


def test_a_multiple_that_cannot_be_crossed_is_refused():
    """Delete this and a move is switched off by editing a multiple to zero, which leaves the
    row reading as configured. Turning a move off is a decision and belongs in the table as a
    row somebody removed."""
    for dead in (0.0, -1.0):
        with pytest.raises(ScalingError, match="nothing can cross"):
            _trigger(multiple=dead)


def test_a_declared_figure_without_an_anchor_cannot_be_built():
    """Delete this and a trigger can say it came from a declared figure while carrying none,
    which is the exact claim this module is arranged to make impossible."""
    with pytest.raises(ScalingError, match="carries no anchor"):
        _trigger(anchor=None)


def test_a_trigger_that_is_not_a_declared_figure_may_not_carry_an_anchor():
    """Delete this and a row can show a threshold beside a basis saying the threshold is not
    consulted, which is the combination `brain.ops.retention.Horizon` refuses for the same
    reason: whichever half a reader believes, the other half of the callers believe the other."""
    with pytest.raises(ScalingError, match="carries anchor"):
        _trigger(basis=ThresholdBasis.NOT_ANCHORED, computed_by="")
    with pytest.raises(ScalingError, match="carries anchor"):
        _trigger(basis=ThresholdBasis.FROM_THE_INSTALL, computed_by="replica_headroom")


def test_a_trigger_computed_from_the_install_has_to_name_what_computes_it():
    """Delete this and "computed from the install" becomes a way of having no threshold and no
    open question at all, which is worse than either."""
    with pytest.raises(ScalingError, match="names ''"):
        _trigger(basis=ThresholdBasis.FROM_THE_INSTALL, anchor=None)


def test_only_a_trigger_computed_from_the_install_names_a_function():
    """Delete this and a fixed threshold can also name a function, so a reader cannot tell which
    of the two produced the number in front of them."""
    with pytest.raises(ScalingError, match="names 'replica_headroom'"):
        _trigger(computed_by="replica_headroom")


# ----------------------------------------------------------------------------- the table
def test_every_scaling_move_has_a_trigger_and_every_anchor_points_outside_this_module():
    """Delete this and a move can be added with no trigger, which means it happens when somebody
    feels like it, or an anchor can point back at this module, which is a number agreeing with
    itself."""
    assert trigger_gaps() == ()


def test_a_move_nothing_declares_a_trigger_for_is_a_finding():
    """Delete this and `trigger_gaps` can only ever be run against the complete table, so nobody
    has seen it produce a finding and nobody knows it can."""
    partial = tuple(one for one in TRIGGERS if one.move is not ScalingMove.READ_REPLICA)
    findings = trigger_gaps(partial)
    assert any("read_replica" in one for one in findings)


def test_an_anchor_naming_this_module_is_a_finding():
    """Delete this and a threshold can be anchored to a constant in this file, which is the
    self-referential check `brain.ops.wiring` had for as long as its cap was wrong."""
    findings = trigger_gaps(
        (*TRIGGERS, _trigger(anchor=_anchor(source="brain.ops.scaling.SOMETHING"))),
    )
    assert any("an anchor inside the thing it anchors" in one for one in findings)


def test_a_trigger_naming_a_function_this_module_does_not_define_is_a_finding():
    """Delete this and a threshold can claim to be computed by something that does not exist,
    which reads in the table exactly like one that is."""
    findings = trigger_gaps(
        (
            *TRIGGERS,
            _trigger(
                basis=ThresholdBasis.FROM_THE_INSTALL,
                anchor=None,
                computed_by="no_such_function",
            ),
        ),
    )
    assert any("no such thing" in one for one in findings)


def test_the_hosts_are_split_for_two_reasons_and_both_are_returned():
    """Delete this and `triggers_for` can return the first match, which would hide whichever was
    declared second. The one that would be hidden is the unanchored resilience decision, which
    is exactly the row a reader has to see."""
    found = triggers_for(ScalingMove.SPLIT_THE_HOSTS)
    assert len(found) == 2
    assert {one.basis for one in found} == {
        ThresholdBasis.FROM_A_DECLARED_FIGURE,
        ThresholdBasis.NOT_ANCHORED,
    }


def test_asking_about_a_move_nothing_declares_is_a_refusal():
    """Delete this and a move with no trigger returns an empty tuple, which a caller renders as
    "no reason to act" rather than as "nothing says when to act"."""
    with pytest.raises(ScalingError, match="no trigger declares"):
        triggers_for(
            ScalingMove.READ_REPLICA,
            tuple(one for one in TRIGGERS if one.move is not ScalingMove.READ_REPLICA),
        )


def test_the_only_unanchored_trigger_is_the_resilience_decision():
    """Delete this and an unanchored trigger can be added without anybody noticing, because the
    table renders it the same way as the rest. This is the list the module says has to be read
    before the table is believed."""
    open_questions = unanchored()
    assert [one.observable for one in open_questions] == [
        ScalingObservable.SINGLE_HOST_FAILURE_IS_ACCEPTABLE
    ]


# ------------------------------------------------------------------------------ the moves
def test_partitioning_is_due_for_a_window_longer_than_one_partition_and_not_for_a_shorter_one():
    """Delete this and the partition trigger becomes a function that returns True. The negative
    case is a table retained for less than one interval, which is one partition and nothing to
    cut."""
    interval = longest_days(PARTITION_INTERVAL)
    assert partitioning_is_due(retained_window_days=LEDGER_RETENTION_DAYS, interval_days=interval)
    assert not partitioning_is_due(retained_window_days=interval, interval_days=interval)
    assert not partitioning_is_due(retained_window_days=7, interval_days=interval)


def test_a_window_or_an_interval_of_no_days_is_not_a_partitioning_question():
    """Delete this and zero days answers False, which reads as "no need to partition" for a
    reading that is nonsense rather than reassuring."""
    with pytest.raises(ScalingError, match="not a partitioning question"):
        partitioning_is_due(retained_window_days=0, interval_days=31)
    with pytest.raises(ScalingError, match="not a partitioning question"):
        partitioning_is_due(retained_window_days=1825, interval_days=0)


def test_the_replica_headroom_is_the_interactive_pool_less_the_answer_paths_own_peak():
    """Delete this and the replica trigger stops being anchored to `brain.ops.admission` at all.
    Asserted against Little's law computed here from the same profile, so the arithmetic has to
    be the pool minus the occupancy rather than a fraction somebody preferred."""
    pools = pools_for(20)
    profile = _profile(2.0)
    occupied = math.ceil(little_law_concurrency(2.0, 4.0))
    assert replica_headroom(profile, pools) == pools.interactive - occupied


def test_a_fraction_of_a_connection_is_an_occupied_connection():
    """Delete this and the rounding can go the other way, which every shipped profile hides:
    lite, full and ha all give a whole number of calls in flight, so ceiling and floor agree on
    all three. An install whose peak is not a round multiple would be handed a connection that
    is already half taken."""
    pools = ClassPools(interactive=10, background=3, batch=2)
    assert little_law_concurrency(0.3, 4.0) == pytest.approx(1.2)
    assert replica_headroom(_profile(0.3), pools) == 8


def test_a_profile_that_already_fills_the_interactive_pool_reports_no_headroom_rather_than_less():
    """Delete this and a negative headroom makes the replica due at zero console reads, which
    blames the console for a pool the answer path had already outgrown."""
    assert replica_headroom(_profile(8.0), ClassPools(interactive=4, background=2, batch=2)) == 0


def test_the_replica_is_due_only_once_console_reads_pass_what_is_left():
    """Delete this and the trigger is satisfied by a function that always says yes or always
    says no. Both sides are asserted at the boundary, which is where an off-by-one would put a
    replica in front of a pool that had room."""
    pools = pools_for(20)
    profile = _profile(2.0)
    room = replica_headroom(profile, pools)
    assert not replica_is_due(profile, pools, console_reads_in_flight=room)
    assert replica_is_due(profile, pools, console_reads_in_flight=room + 1)


def test_a_negative_count_of_console_reads_is_refused():
    """Delete this and a negative reading answers False, so a broken counter reports that a
    replica is not needed."""
    with pytest.raises(ScalingError, match="not a count"):
        replica_is_due(_profile(1.0), pools_for(20), console_reads_in_flight=-1)


def test_a_report_nobody_measured_is_not_due_and_a_slow_one_is():
    """Delete this and an unmeasured report either always builds a materialised view or never
    does. Materialising is a permanent maintenance obligation, so it is not taken on for a
    reading nobody has, and the boundary is the answer lane's own promise."""
    assert not report_is_due(observed_p95_ms=None)
    assert not report_is_due(observed_p95_ms=float(ANSWER_P95_MS))
    assert report_is_due(observed_p95_ms=float(ANSWER_P95_MS) + 1)
    assert not report_is_due(observed_p95_ms=2_000.0)


def test_the_hosts_are_split_exactly_when_the_profile_does_not_fit_the_measured_machine():
    """Delete this and the memory trigger stops agreeing with `brain.ops.wiring`, which is the
    module that has the measurement. Lite fits and standard does not, on the host recorded
    there today."""
    assert not host_split_is_due("lite")
    assert host_split_is_due("standard")
    assert host_split_is_due("full")


# -------------------------------- source fan-out under the estate's ceilings (M36.2.1.3)
def _plan(*specs: tuple[str, str, int, tuple[str, ...]]) -> FanOutPlan:
    """A federation plan, built through federation's own types.

    Built from `brain.connectors.federation` rather than from a local stand-in, because the
    whole claim of this half is that the graph is federation's and this module only adds
    contention to it. A test type here would let the two drift.
    """
    return FanOutPlan(
        calls=tuple(
            SourceCall(
                call_id=call_id,
                connector=connector,
                entity="thing",
                timeout_ms=timeout,
                depends_on=depends,
            )
            for call_id, connector, timeout, depends in specs
        )
    )


def _wide(connector: str, how_many: int, timeout: int = 100) -> FanOutPlan:
    """One wave of independent calls to one connector."""
    return _plan(*((f"c{index}", connector, timeout, ()) for index in range(how_many)))


def _defined_in_scaling() -> set[str]:
    """Every class the module defines, read out of the source rather than off the module object.

    Parsed for the reason `tests/invariants/test_single_implementation.py` parses: an import
    and a definition look identical through `getattr`, and it is the definition that is the
    second implementation. A docstring saying the graph is federation's is exactly what this
    exists to disbelieve.
    """
    tree = ast.parse(Path(scaling.__file__).read_text(encoding="utf-8"))
    return {one.name for one in ast.walk(tree) if isinstance(one, ast.ClassDef)}


def _imported_by_scaling(module: str) -> set[str]:
    """The names this module imports from another, read out of the source."""
    tree = ast.parse(Path(scaling.__file__).read_text(encoding="utf-8"))
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == module
        for alias in node.names
    }


def test_the_source_call_graph_is_federations_and_this_module_defines_no_second_one():
    """Delete this and a second `SourceCall` can appear here, which is what the first draft of
    the module had, along with a second plan and a second critical path. The names collide with
    `brain.connectors.federation`, the invariant suite does not pin this one, and the two would
    drift the first time either grew a field."""
    assert "SourceCall" in _imported_by_scaling("brain.connectors.federation")
    assert not _defined_in_scaling() & {"SourceCall", "SourceCallPlan", "FanOutPlan"}
    assert (
        "brain.connectors.federation"
        in scaling.THE_GRAPH_IS_FEDERATIONS_AND_THE_CONTENTION_IS_NOBODYS
    )


def test_an_uncontended_plan_costs_exactly_what_federation_already_says_it_does():
    """This is the property that keeps the two arithmetics from being two answers. Delete it
    and the contention term can drift away from zero on a plan nothing is competing for, which
    would make every plan look slower than federation reports and send somebody to reconcile
    two numbers that were meant to agree."""
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=8, mean_service_seconds=1.0),)
    plan = _wide("xero", 4)
    assert contention_ms(plan, budgets, CapacityState(), WorkloadClass.INTERACTIVE) == 0
    assert (
        contended_critical_path_ms(plan, budgets, CapacityState(), WorkloadClass.INTERACTIVE)
        == plan.critical_path_ms()
    )


def test_a_wave_larger_than_its_connectors_ceiling_costs_another_round():
    """This is the leaf. Delete it and `assert_within` keeps passing a plan that cannot meet its
    budget on a busy system: eight calls against a ceiling of five is two rounds, and the second
    round is a whole extra timeout of wall clock that federation's own arithmetic does not
    count because it assumes the wave starts at once."""
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=5, mean_service_seconds=1.0),)
    plan = _wide("xero", 8, timeout=200)
    assert plan.critical_path_ms() == 200
    assert contention_ms(plan, budgets, CapacityState(), WorkloadClass.INTERACTIVE) == 200
    assert (
        contended_critical_path_ms(plan, budgets, CapacityState(), WorkloadClass.INTERACTIVE) == 400
    )


def test_a_second_round_costs_the_waves_slowest_timeout_and_not_its_fastest():
    """Delete this and a mixed wave is costed at whichever call happened to be cheapest, which
    understates exactly the plans that mix a fast source with a slow one."""
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=1, mean_service_seconds=1.0),)
    plan = _plan(("quick", "xero", 50, ()), ("slow", "xero", 400, ()))
    assert contention_ms(plan, budgets, CapacityState(), WorkloadClass.INTERACTIVE) == 400


def test_a_chain_of_dependent_calls_is_already_serial_and_contention_adds_nothing():
    """Delete this and the contention term can be charged per call rather than per extra round,
    which would double-count a plan whose calls were never going to run together anyway."""
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=1, mean_service_seconds=1.0),)
    plan = _plan(("a", "xero", 100, ()), ("b", "xero", 100, ("a",)), ("c", "xero", 100, ("b",)))
    assert plan.waves() == (("a",), ("b",), ("c",))
    assert contention_ms(plan, budgets, CapacityState(), WorkloadClass.INTERACTIVE) == 0


def test_the_class_ceiling_narrows_a_wave_the_way_admission_says_it_should():
    """Delete this and the workload class stops mattering, so a batch fan-out would take the
    whole of a connector's budget and the request path would keep none of it. The number comes
    from `brain.ops.admission.Budget.ceiling_for` rather than being recomputed here."""
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=4, mean_service_seconds=1.0),)
    plan = _wide("xero", 4, timeout=100)
    assert contention_ms(plan, budgets, CapacityState(), WorkloadClass.INTERACTIVE) == 0
    assert contention_ms(plan, budgets, CapacityState(), WorkloadClass.BATCH) == 100


def test_what_is_already_in_flight_reduces_what_a_wave_may_start():
    """Delete this and the snapshot is ignored, so a plan is costed against an idle system while
    the connector is full. `brain.ops.admission.headroom` is what subtracts it, and this is what
    proves the call is being made."""
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=4, mean_service_seconds=1.0),)
    busy = CapacityState(used={(Resource.SOURCE_CALLS, "xero"): 3})
    calls = _wide("xero", 4).calls
    assert len(admitted_from(calls, budgets, busy, WorkloadClass.INTERACTIVE)) == 1


def test_calls_are_admitted_in_the_order_the_plan_declared_them():
    """Delete this and a fairness rule can be introduced, which would be the one number in this
    arithmetic that nobody could argue with. The plan's order is the priority, and two readings
    of one plan have to produce the same answer."""
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=2, mean_service_seconds=1.0),)
    calls = _wide("xero", 5).calls
    admitted = admitted_from(calls, budgets, CapacityState(), WorkloadClass.INTERACTIVE)
    assert [one.call_id for one in admitted] == ["c0", "c1"]


def test_a_global_ceiling_bounds_a_wave_every_connector_would_have_admitted():
    """This is the global half of M36.2.1.3. Delete it and the total is never enforced, which is
    the state the estate is in today: the per-connector rows would each say yes and every call
    would start at once."""
    budgets = (
        Budget(resource=Resource.SOURCE_CALLS, key="a", limit=8, mean_service_seconds=1.0),
        Budget(resource=Resource.SOURCE_CALLS, key="b", limit=8, mean_service_seconds=1.0),
    )
    calls = _plan(
        *((f"a{index}", "a", 100, ()) for index in range(4)),
        *((f"b{index}", "b", 100, ()) for index in range(4)),
    ).calls
    assert len(admitted_from(calls, budgets, CapacityState(), WorkloadClass.INTERACTIVE)) == 8
    narrowed = admitted_from(
        calls, budgets, CapacityState(), WorkloadClass.INTERACTIVE, global_ceiling=3
    )
    assert len(narrowed) == 3


def test_a_negative_global_ceiling_is_refused():
    """Delete this and a negative total admits nothing while reading as a configured budget,
    which presents as every connector being full."""
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=4, mean_service_seconds=1.0),)
    with pytest.raises(ScalingError, match="is not a budget"):
        admitted_from(
            _wide("xero", 1).calls,
            budgets,
            CapacityState(),
            WorkloadClass.INTERACTIVE,
            global_ceiling=-1,
        )


def test_a_wave_whose_connectors_are_all_full_refuses_rather_than_reporting_a_round_count():
    """Delete this and the round loop spins for ever on a full system, or worse returns zero,
    which would be a wall clock computed for work that cannot start."""
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=2, mean_service_seconds=1.0),)
    full = CapacityState(used={(Resource.SOURCE_CALLS, "xero"): 2})
    with pytest.raises(ScalingError, match="no call in a wave"):
        rounds_for(_wide("xero", 2).calls, budgets, full, WorkloadClass.INTERACTIVE)


def test_a_connector_with_no_row_of_its_own_falls_back_to_the_default_row():
    """Delete this and the fallback in `brain.ops.admission.budget_for` stops being exercised
    from here, so an unmeasured connector would refuse rather than getting the conservative
    default the seed rows declare for exactly this case."""
    calls = _wide("a-connector-nobody-measured", 8).calls
    admitted = admitted_from(calls, seed_budgets(), CapacityState(), WorkloadClass.INTERACTIVE)
    assert len(admitted) == 4


def test_a_budget_list_with_no_row_at_all_refuses_rather_than_admitting_none():
    """Delete this and a missing budget reads as a full connector. The two send an operator to
    opposite places: one is a configuration gap and the other is a busy afternoon."""
    with pytest.raises(ScalingError, match="no budget row governs"):
        admitted_from(_wide("xero", 1).calls, (), CapacityState(), WorkloadClass.INTERACTIVE)


def test_costing_a_wave_over_calls_the_plan_does_not_hold_is_refused():
    """Delete this and a wave computed from one plan can be costed against another, which would
    produce a shorter answer that reads as a faster one."""
    with pytest.raises(ScalingError, match="holds no call"):
        calls_in(_wide("xero", 2), ["c0", "nowhere"])


def test_a_plan_affordable_per_question_can_still_be_unaffordable_per_machine():
    """This is the finding the whole half exists for. Delete it and `assert_within` keeps saying
    yes to a plan whose critical path fits only because it assumed the wave would start at once,
    and nothing anywhere would say the two checks never met."""
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=2, mean_service_seconds=1.0),)
    plan = _wide("xero", 6, timeout=FEDERATION_TIMEOUT_MS)
    plan.assert_within()
    assert CallBudget().check(plan) == ()
    findings = fanout_refusals(plan, budgets, CapacityState(), WorkloadClass.INTERACTIVE)
    assert any("on an idle system" in one for one in findings)


def test_a_plan_the_question_budget_refuses_is_reported_through_federations_own_check():
    """Delete this and the per-question budget is dropped on the floor here, so a caller using
    this function would be told about the machine and not about the twenty-one calls."""
    plan = _wide("xero", 8, timeout=10)
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=8, mean_service_seconds=1.0),)
    findings = fanout_refusals(
        plan,
        budgets,
        CapacityState(),
        WorkloadClass.INTERACTIVE,
        call_budget=CallBudget(total=4),
    )
    assert any("against a budget of 4" in one for one in findings)


def test_a_plan_that_fits_both_budgets_is_refused_by_nothing():
    """Delete this and the positive case goes with it: a check tested only where it bites is
    satisfied by a function that refuses every plan."""
    plan = _wide("xero", 2, timeout=100)
    budgets = (Budget(resource=Resource.SOURCE_CALLS, key="", limit=8, mean_service_seconds=1.0),)
    assert fanout_refusals(plan, budgets, CapacityState(), WorkloadClass.INTERACTIVE) == ()


# ------------------------------------------ the budgets nobody totalled (M36.2.1.3)
def test_the_implied_global_ceiling_is_the_sum_of_the_per_connector_ones():
    """Delete this and the figure the module reports as undeclared stops being the figure that
    binds. It is an addition rather than a decision, which is the finding."""
    budgets = seed_budgets()
    assert implied_global_ceiling(budgets, WorkloadClass.INTERACTIVE, connectors=["xero"]) == 5
    assert (
        implied_global_ceiling(
            budgets, WorkloadClass.INTERACTIVE, connectors=["xero", "lark_base", "freshdesk"]
        )
        == 21
    )


def test_a_connector_named_twice_is_counted_once():
    """Delete this and a wave of eight calls to one connector would imply a ceiling eight times
    the connector's own, which would make the global check never bind for the commonest shape of
    plan there is."""
    budgets = seed_budgets()
    assert (
        implied_global_ceiling(budgets, WorkloadClass.INTERACTIVE, connectors=["xero", "xero"]) == 5
    )


def test_the_absence_of_a_global_source_budget_is_reported_with_the_number_it_comes_to():
    """Delete this and the gap goes quiet. `brain.ops.admission` declares no total for source
    calls, so twenty-one may be in flight for the interactive class and nobody chose twenty-one,
    and a finding that does not say the number is one nobody acts on."""
    findings = scaling_gaps(seed_budgets(), WorkloadClass.INTERACTIVE)
    assert len(findings) == 1
    assert "21 may be in flight" in findings[0]


def test_a_budget_list_with_no_source_rows_has_nothing_to_report():
    """Delete this and the gaps function can only ever be run against the seeds, so nobody has
    seen it stay quiet and nobody knows the finding is conditional on anything."""
    assert scaling_gaps((), WorkloadClass.INTERACTIVE) == ()


# ------------------------------------------- sharing one answer execution (M36.2.3)
def _parts(**overrides: object) -> CacheKeyParts:
    base: dict[str, object] = {
        "question": "what is the registered address of the client",
        "ent_hash": REACH,
        "agent_config_hash": "cfg-1",
        "policy_epoch": 7,
        "source_epochs": {"freshdesk": 3},
    }
    base.update(overrides)
    return CacheKeyParts(**base)  # type: ignore[arg-type]


def test_the_sharing_rule_is_the_cache_key_and_this_module_declares_no_second_one():
    """Delete this and a second key can be declared here, which the first draft of this module
    had. Two keys deciding which two callers are the same caller disagree first on whichever
    part one of them forgot, and the agent configuration and the source epochs are both parts
    that change what an answer says without changing the question."""
    assert "CacheKeyParts" in _imported_by_scaling("brain.gate.cache_key")
    assert not _defined_in_scaling() & {"CacheKeyParts", "InFlightKey", "ShareKey"}
    assert may_share(_parts(), _parts())
    assert cache_key(_parts()) == cache_key(_parts())


def test_two_requests_with_the_same_question_and_the_same_reach_share_one_execution():
    """Delete this and the positive case goes: a sharing rule tested only by its refusals is
    satisfied by a function that never shares anything, which is correct and useless."""
    assert share_role(_parts(), _parts()) is FlightRole.FOLLOWER
    assert share_refusals(_parts(), _parts()) == ()


def test_a_different_entitlement_hash_refuses_the_share():
    """Delete this and two callers with overlapping reaches can share one execution, and
    whichever ran first decides what the other was shown. That is the invariant failing in
    whichever direction the race happened to go, and nothing afterwards records it."""
    other = _parts(ent_hash=OTHER_REACH)
    assert not may_share(_parts(), other)
    assert share_role(_parts(), other) is FlightRole.LEADER


def test_every_part_of_the_key_has_to_match_and_not_only_the_question_and_the_reach():
    """Delete this and somebody narrows the comparison to the two obvious parts. A different
    agent configuration, policy epoch or source epoch each changes what the answer says while
    leaving the question and the asker identical."""
    for different in (
        _parts(agent_config_hash="cfg-2"),
        _parts(policy_epoch=8),
        _parts(source_epochs={"freshdesk": 4}),
    ):
        assert not may_share(_parts(), different)


def test_a_question_too_volatile_to_cache_is_too_volatile_to_share():
    """Delete this and two identical volatile questions share one execution, so the follower is
    handed a figure computed before they asked. The window being seconds is not a defence,
    because nothing in the domain layer knows how many seconds it was."""
    live = _parts(question="what is the balance right now")
    assert is_volatile(live.question, frozenset(live.source_epochs))
    assert not may_share(live, live)
    assert any("too volatile" in one for one in share_refusals(live, live))


def test_a_volatile_source_refuses_the_share_even_when_the_question_reads_as_stable():
    """Delete this and the sharing decision consults only the question's wording, which
    `brain.gate.cache_key` calls a backstop rather than the mechanism: the reliable signal is
    the source, and a question about a live ticket count is volatile however it was phrased.
    The shape patterns are language-dependent and this half is not."""
    live = _parts(
        question="what is the registered address of the client", source_epochs={"freshdesk_live": 2}
    )
    assert not is_volatile(live.question)
    assert is_volatile(live.question, frozenset(live.source_epochs))
    assert not may_share(live, live)


def test_a_refusal_names_the_part_and_never_the_values():
    """Delete this and the refusal grows the two keys for debuggability, which would put a pair
    of questions, and the fact that two named people asked nearly the same thing, into an
    operational log with its own retention."""
    refusals = share_refusals(_parts(), _parts(ent_hash=OTHER_REACH))
    assert refusals == (
        "ent_hash differs, so these are not the same question under the same reach",
    )
    assert OTHER_REACH not in refusals[0]
    assert "registered address" not in refusals[0]


def test_every_differing_part_is_reported_rather_than_the_first():
    """Delete this and an operator cannot tell a near miss on one part from two unrelated
    requests that happened to arrive together, which are different problems."""
    other = _parts(ent_hash=OTHER_REACH, policy_epoch=8, agent_config_hash="cfg-2")
    assert len(share_refusals(_parts(), other)) == 3


def test_the_fetch_key_and_the_answer_key_disagree_about_reach_on_purpose():
    """Delete this and the two coalescing rules look like an inconsistency somebody should fix,
    which is exactly the edit that would break one of them. `flight_key` shares an unredacted
    fetch and must not carry a reach; the answer key shares a redacted answer and must."""
    assert REACH not in flight_key("freshdesk", "ticket", (("status", "open"),))
    assert "ent_hash" in {one.name for one in fields(CacheKeyParts)}
    assert "flight_key" in scaling.SIMILAR_REACH_IS_NOT_EQUAL_REACH


def test_the_declared_key_admits_no_similarity_and_carries_a_reach():
    """Delete this and the scan is never run against the real key, so nobody knows whether it
    would pass. It is pointed at another module's type on purpose: an edit made for a cache hit
    rate would arrive there."""
    assert coalescing_gaps() == ()


def test_a_key_with_a_tolerance_field_is_a_finding():
    """Delete this and sharing can be widened by adding a field, and the person adding it will
    be looking at a hit rate rather than at a permission rule."""

    @dataclass(frozen=True)
    class Loose:
        question: str
        ent_hash: str
        similarity: float

    assert any("tolerance on a comparison" in one for one in coalescing_gaps(Loose))


def test_a_key_with_no_entitlement_hash_at_all_is_a_finding():
    """Delete this and a key can drop the reach entirely, which is the same failure as a
    tolerance with nothing left to compare: two requests shared on the question alone."""

    @dataclass(frozen=True)
    class NoReach:
        question: str
        policy_epoch: int

    assert any("no entitlement hash" in one for one in coalescing_gaps(NoReach))


def test_the_capacity_profiles_this_module_reads_are_the_ones_admission_declares():
    """Delete this and the replica trigger could be exercised only against profiles built in
    this file, so it would keep passing after the shipped sizings changed shape."""
    names = {one.name for one in seed_profiles()}
    assert {"lite", "full", "ha"} <= names
