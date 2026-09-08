"""Planning from a declaration, and compiling a plan down to what a caller may actually do.

The structural half of M19.2.1 is in `test_browsing_shape.py`. This is the behavioural half:
what the planner does with a declaration, and what envelope compilation removes.

Task ids: M19.2.1, M19.2.2
"""

from __future__ import annotations

import pytest

from brain.browsing.envelope import (
    DIGEST_SCHEMA,
    Dropped,
    Envelope,
    EnvelopeError,
    compilation_only_removes,
    compile_envelope,
    side_effect_of,
    tier_for,
)
from brain.browsing.grading import GOAL_SCHEMA
from brain.browsing.planning import (
    MAX_GOAL,
    Goal,
    Plan,
    PlanningError,
    PlanRequest,
    Step,
    plan,
    render_brief,
)
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.gate.leash import DIGEST_SCHEMA as LEASH_DIGEST_SCHEMA

READ = Capability(value="read:browser_surface")
WRITE = Capability(value="write:browser_surface")
ORIGIN = "https://books.example"


def read_surface() -> Surface:
    return Surface(
        name="invoices",
        origin=ORIGIN,
        path="/invoices",
        verbs=frozenset({Verb.OPEN, Verb.READ}),
        capability=READ,
        reads=("number", "total"),
    )


def write_surface() -> Surface:
    return Surface(
        name="filing",
        origin=ORIGIN,
        path="/filing",
        verbs=frozenset({Verb.OPEN, Verb.TYPE, Verb.SUBMIT}),
        capability=WRITE,
    )


def books() -> Target:
    return Target(
        name="books",
        origins=frozenset({ORIGIN}),
        surfaces=(read_surface(), write_surface()),
    )


def registry() -> TargetRegistry:
    return TargetRegistry(targets=(books(),))


def request(*surfaces: str) -> PlanRequest:
    return PlanRequest(
        goal=Goal(text="Read this month's invoice totals", asked_by="alex"),
        target="books",
        surfaces=surfaces or ("invoices",),
    )


def reach(*capabilities: Capability) -> EntitlementSet:
    return EntitlementSet(
        principal_id="alex",
        grants=tuple(
            Grant(capability=one, scope=Scope.department("finance")) for one in capabilities
        ),
    )


# --------------------------------------------------------------------- the planner


def test_a_plan_comes_from_the_declaration_and_is_the_same_every_time() -> None:
    """The positive case, and the determinism the envelope digest depends on.

    Delete this and the planner can start ordering steps by something that varies between
    runs, which changes an approved envelope's fingerprint without changing what it permits.
    """
    first = plan(request(), registry())
    second = plan(request(), registry())

    assert first == second
    assert first.steps == (
        Step(surface="invoices", verb=Verb.OPEN),
        Step(surface="invoices", verb=Verb.READ),
    )


def test_a_surface_the_target_does_not_declare_is_refused_rather_than_skipped() -> None:
    """A quietly shorter plan fails later and blames the goal.

    Delete this and a typo in a surface name produces a plan that runs, does less than was
    asked, and reports that it could not achieve the goal for a reason nobody can find.
    """
    with pytest.raises(PlanningError, match="declares no surface"):
        plan(request("ledger"), registry())


def test_a_plan_against_an_undeclared_target_is_refused() -> None:
    """A run cannot be planned against a system nobody has described and reviewed.

    Delete this and a plan can name any target string, and the origin allowlist it would have
    been checked against does not exist.
    """
    with pytest.raises(PlanningError, match="no target named"):
        plan(
            PlanRequest(
                goal=Goal(text="do the thing", asked_by="alex"),
                target="ledger",
                surfaces=("invoices",),
            ),
            registry(),
        )


def test_a_goal_longer_than_the_limit_is_refused() -> None:
    """The goal is the only free text that reaches the planner, so it is the only channel a
    document could arrive through.

    **The limit is pinned between two fixed numbers rather than against itself.** Building the
    over-long string from `MAX_GOAL` is green for every value `MAX_GOAL` could hold, including
    a hundred thousand, and a mutation raising it to that passed. Two hundred characters must
    be accepted because a real goal has conditions in it; two thousand must be refused because
    that is a document.

    Delete this and pasting a page into the goal field is a way to hand the planner page
    content that every structural check in `shape` is blind to, because it is a `str`.
    """
    with pytest.raises(PlanningError, match="is a document rather than a goal"):
        Goal(text="x" * 2000, asked_by="alex")

    assert Goal(text="x" * 200, asked_by="alex").text
    assert 200 <= MAX_GOAL < 2000


def test_a_goal_of_only_whitespace_is_refused() -> None:
    """An empty goal and a goal of three spaces are the same absence with different bytes.

    Delete this and a rubric is built from nothing and grades against nothing, while the goal
    digest still binds to a value that looks like a goal.
    """
    with pytest.raises(PlanningError, match="no text"):
        Goal(text="   ", asked_by="alex")


def test_a_plan_request_naming_no_surfaces_is_refused() -> None:
    """A planner free to choose from every declared surface is choosing where to go, which is
    the decision the declaration was supposed to have made.

    Delete this and the surface list becomes optional, and an empty one reads as permission to
    use all of them.
    """
    with pytest.raises(PlanningError, match="names no surfaces"):
        PlanRequest(goal=Goal(text="go", asked_by="alex"), target="books", surfaces=())


def test_the_brief_a_planner_model_would_read_contains_only_declared_values() -> None:
    """`render_brief` is the seam a model arrives at, so what it prints is the whole of what a
    planner could ever be told.

    Delete this and the brief can grow a line assembled from something a run produced, which
    is the first step of page content reaching a planner by a route the import graph cannot
    see.
    """
    brief = render_brief(request(), books())

    assert "Read this month's invoice totals" in brief
    assert f"{ORIGIN}/invoices" in brief
    assert "open, read" in brief


# --------------------------------------------------------------------- compilation


def test_compilation_keeps_the_steps_the_reach_admits() -> None:
    """The positive case: an envelope that dropped everything would satisfy every refusal test
    below and permit no work at all.

    Delete this and `compile_envelope` can start returning an empty envelope and only the
    refusal tests would notice, which is to say none of them would.
    """
    compiled = compile_envelope(
        plan(request(), registry()),
        books(),
        run_id="run-1",
        reach=reach(READ),
        ceiling=AutonomyTier.AUTONOMOUS,
    )

    assert compiled.steps == (
        Step(surface="invoices", verb=Verb.OPEN),
        Step(surface="invoices", verb=Verb.READ),
    )
    assert compiled.dropped == ()
    assert compiled.admits("invoices", Verb.READ)


def test_a_step_the_reach_does_not_admit_is_dropped() -> None:
    """The capability narrowing, and the whole of what "intersected with capabilities" means
    at this layer.

    Delete this and a caller with no write grant gets a write step in the envelope, which is
    then compiled into a policy that permits it.
    """
    compiled = compile_envelope(
        plan(request("invoices", "filing"), registry()),
        books(),
        run_id="run-1",
        reach=reach(READ),
        ceiling=AutonomyTier.AUTONOMOUS,
    )

    assert frozenset(step.surface for step in compiled.steps) == frozenset({"invoices"})
    assert compiled.dropped
    assert all(one.surface == "filing" for one in compiled.dropped)


def test_a_dropped_step_never_names_the_capability_that_was_missing() -> None:
    """DENIED and ABSENT must be indistinguishable, and the caller's own step is the one place
    it is tempting to explain the refusal in full.

    Naming the surface back is safe: the caller named it themselves against a registry they
    can read. Naming the capability hands them a permission somebody else holds.

    Delete this and the reason string grows the capability value the first time somebody is
    debugging a compilation.
    """
    compiled = compile_envelope(
        plan(request("filing"), registry()),
        books(),
        run_id="run-1",
        reach=reach(READ),
        ceiling=AutonomyTier.AUTONOMOUS,
    )

    assert compiled.dropped
    for one in compiled.dropped:
        assert WRITE.value not in one.reason
        assert "write" not in one.reason


def test_a_write_under_a_shadow_ceiling_is_dropped_and_survives_an_assisted_one() -> None:
    """The skill ceiling narrowing, in both directions.

    A refusal test on its own is satisfied by compilation that drops every write, so the
    assisted half is what proves the ceiling is being read rather than the verb.

    Delete this and the ceiling stops being consulted, and a shadow agent files a return.
    """
    shadowed = compile_envelope(
        plan(request("filing"), registry()),
        books(),
        run_id="run-1",
        reach=reach(WRITE),
        ceiling=AutonomyTier.SHADOW,
    )
    assisted = compile_envelope(
        plan(request("filing"), registry()),
        books(),
        run_id="run-1",
        reach=reach(WRITE),
        ceiling=AutonomyTier.ASSISTED,
    )

    assert not any(step.is_write() for step in shadowed.steps)
    assert any("shadow" in one.reason for one in shadowed.dropped)
    assert any(step.is_write() for step in assisted.steps)


def test_the_write_budget_is_the_number_of_write_steps_the_plan_contained() -> None:
    """A second configured budget would be a second number to keep in agreement.

    Delete this and the budget can be defaulted to something generous, and the count check in
    the enforcer stops binding at the point the plan said.
    """
    compiled = compile_envelope(
        plan(request("filing"), registry()),
        books(),
        run_id="run-1",
        reach=reach(WRITE),
        ceiling=AutonomyTier.AUTONOMOUS,
    )

    assert compiled.allowance(Verb.TYPE) == 1
    assert compiled.allowance(Verb.SUBMIT) == 1
    assert compiled.allowance(Verb.CLICK) == 0
    assert compiled.allowance(Verb.OPEN) == 0


def test_compilation_can_only_remove_steps() -> None:
    """The narrowing property, asserted rather than argued.

    Checked as a subsequence, so a reordering fails too: order is what the digest covers, and
    a reordered envelope has a different fingerprint without permitting anything different.

    Delete this and a future compilation step that adds a step, an implicit login say, passes
    review because it reads as a convenience.
    """
    original = plan(request("invoices", "filing"), registry())
    compiled = compile_envelope(
        original,
        books(),
        run_id="run-1",
        reach=reach(READ, WRITE),
        ceiling=AutonomyTier.AUTONOMOUS,
    )

    assert compilation_only_removes(original, compiled)


def test_a_step_added_during_compilation_is_caught_by_the_narrowing_check() -> None:
    """The positive case for the property itself: it must be able to fail.

    Delete this and `compilation_only_removes` could return True unconditionally and the test
    above would still pass.
    """
    original = plan(request(), registry())
    widened = Envelope(
        run_id="run-1",
        plan=original,
        origins=frozenset({ORIGIN}),
        steps=(*original.steps, Step(surface="filing", verb=Verb.SUBMIT)),
        budget=((Verb.SUBMIT, 1),),
        tiers=((Verb.SUBMIT, AutonomyTier.ASSISTED),),
    )

    assert not compilation_only_removes(original, widened)


def test_the_digest_changes_when_what_is_permitted_changes_and_not_otherwise() -> None:
    """The seal. A policy claiming to come from an envelope is checked against this.

    Both halves matter: a digest that never changed would let a container present a policy
    permitting more, and a digest that changed on anything would void an approval because
    somebody edited a refusal message.

    Delete this and the control plane's second check compares two strings that mean nothing.
    """
    base = compile_envelope(
        plan(request(), registry()),
        books(),
        run_id="run-1",
        reach=reach(READ),
        ceiling=AutonomyTier.AUTONOMOUS,
    )
    wider = Envelope(
        run_id=base.run_id,
        plan=base.plan,
        origins=base.origins,
        steps=(*base.steps, Step(surface="filing", verb=Verb.SUBMIT)),
        budget=((Verb.SUBMIT, 1),),
        tiers=base.tiers,
    )
    annotated = Envelope(
        run_id=base.run_id,
        plan=base.plan,
        origins=base.origins,
        steps=base.steps,
        budget=base.budget,
        tiers=base.tiers,
        dropped=(Dropped(surface="filing", verb=Verb.SUBMIT, reason="a note for a person"),),
    )

    assert base.digest() != wider.digest()
    assert base.digest() == annotated.digest()


def test_an_envelope_with_no_origin_is_refused() -> None:
    """An empty allowlist is either a refusal of everything or a set somebody reads as no
    restriction, and which of those it is cannot be told from the value.

    Delete this and an envelope compiled from a target with no origins becomes the permissive
    reading the first time somebody writes `if envelope.origins:`.
    """
    with pytest.raises(EnvelopeError, match="allows no origin"):
        Envelope(
            run_id="run-1",
            plan=Plan(request=request(), steps=()),
            origins=frozenset(),
            steps=(),
            budget=(),
            tiers=(),
        )


def test_a_zero_budget_row_is_refused() -> None:
    """A row saying a verb is allowed zero times is the absence of the verb wearing a
    permission's clothes.

    Delete this and `allowance` returns 0 for both "not budgeted" and "budgeted at nothing",
    and an operator reading the envelope sees a verb listed as permitted.
    """
    with pytest.raises(EnvelopeError, match="zero budget"):
        Envelope(
            run_id="run-1",
            plan=Plan(request=request(), steps=()),
            origins=frozenset({ORIGIN}),
            steps=(),
            budget=((Verb.SUBMIT, 0),),
            tiers=(),
        )


def test_every_verb_declares_a_side_effect_and_the_reads_declare_none() -> None:
    """Asserted against the enumeration rather than against the mapping itself.

    A test comparing `side_effect_of(Verb.OPEN)` with a constant imported from the same module
    is green for every value that constant could hold. This states the property: exactly the
    two read verbs have no side effect, and every other verb has one.

    Delete this and a verb can be reclassified as NONE, which drops it out of the write budget
    and out of the ceiling composition at the same time.
    """
    without = {verb for verb in Verb if side_effect_of(verb) is SideEffect.NONE}

    assert without == {Verb.OPEN, Verb.READ}
    assert side_effect_of(Verb.UPLOAD) is SideEffect.SEND


def test_the_ceiling_can_only_tighten_what_a_verb_runs_at() -> None:
    """`rung_ceiling` is `min`, and this is the property that makes composing it safe.

    Delete this and `tier_for` can start returning the verb's own default rung, which raises a
    shadow-pinned agent to assisted for every write.
    """
    for ceiling in AutonomyTier:
        for verb in Verb:
            assert tier_for(verb, ceiling) <= ceiling


def test_a_goal_nobody_asked_for_is_refused() -> None:
    """A goal with no asker has no reach to compile against, so the envelope would be
    narrowed by nothing and the run would proceed on an empty question.

    Whitespace as well as empty: `" "` is what an identity field holds when the caller passed
    a blank form value, and it is the survivor CLAUDE.md records for validators.

    Delete this and a plan can be built for nobody, and the capability filter in
    `compile_envelope` has no principal to ask about.
    """
    for bad in ("", "   "):
        with pytest.raises(PlanningError, match="nobody asked for"):
            Goal(text="Read the totals", asked_by=bad)


def test_a_plan_request_naming_no_target_is_refused() -> None:
    """A request with no target has no allowlist to plan inside, and the origin check per
    action is decided against that allowlist.

    Delete this and a request with a blank target reaches `plan`, which reports that no target
    is declared by that name, which is true and unhelpful.
    """
    for bad in ("", "   "):
        with pytest.raises(PlanningError, match="names no target"):
            PlanRequest(goal=Goal(text="go", asked_by="alex"), target=bad, surfaces=("invoices",))


def test_a_plan_request_naming_one_surface_twice_is_refused() -> None:
    """A repeated surface doubles every step on it, and therefore doubles the write budget
    the envelope is compiled with.

    That is the failure worth naming: the count check in the enforcer is exactly as tight as
    the plan, so a duplicated line in a request is a duplicated allowance.

    Delete this and a request naming a filing surface twice gets two submissions.
    """
    with pytest.raises(PlanningError, match="names one surface twice"):
        PlanRequest(
            goal=Goal(text="go", asked_by="alex"),
            target="books",
            surfaces=("invoices", "invoices"),
        )


def test_the_brief_says_a_surface_is_not_declared_rather_than_inventing_one() -> None:
    """`render_brief` is the seam a planner model reads, and a request can name a surface the
    target does not declare, because the two are validated separately.

    Saying so is the only safe answer. Omitting the line would hand the model a brief that
    silently describes fewer surfaces than were asked for; inventing a plausible path would
    hand it a page nobody declared.

    Delete this and the branch is unreachable by any test, and the next edit to it is
    unverified.
    """
    asked = PlanRequest(
        goal=Goal(text="Read the totals", asked_by="alex"),
        target="books",
        surfaces=("invoices", "ledger"),
    )

    brief = render_brief(asked, books())

    assert "ledger: not declared" in brief
    assert f"invoices: {ORIGIN}/invoices" in brief


def test_an_envelope_or_a_compilation_with_no_run_is_refused() -> None:
    """A policy is matched to a run by its id, so an envelope with none produces a policy that
    matches whichever action arrives.

    Both the constructor and `compile_envelope` are checked, and the second is checked
    through the first: compilation carries no run-id check of its own, deliberately, because a
    second statement of the rule could only ever raise at the same moment and mutating it away
    changed nothing. What this asserts is that compiling with no run still refuses.

    Delete this and the first check in `authorise`, that an action belongs to this run,
    compares two empty strings and answers yes.
    """
    for bad in ("", "   "):
        with pytest.raises(EnvelopeError, match="belonging to no run"):
            compile_envelope(
                plan(request(), registry()),
                books(),
                run_id=bad,
                reach=reach(READ),
                ceiling=AutonomyTier.AUTONOMOUS,
            )

    for bad in ("", "   "):
        with pytest.raises(EnvelopeError, match="belonging to no run"):
            Envelope(
                run_id=bad,
                plan=Plan(request=request(), steps=()),
                origins=frozenset({ORIGIN}),
                steps=(),
                budget=(),
                tiers=(),
            )


def narrower() -> Target:
    """The same target with the read surface reduced to navigation and the write one gone.

    A plan is made against one target and compiled against another whenever the declaration
    changes between the two, which is the ordinary case: a plan approved on Monday is compiled
    against whatever the registry says on Tuesday.
    """
    return Target(
        name="books",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="invoices",
                origin=ORIGIN,
                path="/invoices",
                verbs=frozenset({Verb.OPEN}),
                capability=READ,
            ),
        ),
    )


def test_a_step_on_a_surface_the_target_no_longer_declares_is_dropped() -> None:
    """A plan outlives the declaration it was made against, and compilation is where that is
    noticed.

    Delete this and a step naming a surface nobody declares reaches the envelope, and the
    policy compiled from it admits a surface and verb pair with no origin behind it.
    """
    compiled = compile_envelope(
        plan(request("invoices", "filing"), registry()),
        narrower(),
        run_id="run-1",
        reach=reach(READ, WRITE),
        ceiling=AutonomyTier.AUTONOMOUS,
    )

    assert any(
        one.surface == "filing" and "does not declare this surface" in one.reason
        for one in compiled.dropped
    )


def test_a_step_whose_verb_the_surface_no_longer_declares_is_dropped() -> None:
    """The narrower case of the same thing: the surface is still there and does less.

    Delete this and a READ step survives against a surface that has been reduced to
    navigation, and the enforcer admits it because the envelope says so.
    """
    compiled = compile_envelope(
        plan(request(), registry()),
        narrower(),
        run_id="run-1",
        reach=reach(READ),
        ceiling=AutonomyTier.AUTONOMOUS,
    )

    assert compiled.steps == (Step(surface="invoices", verb=Verb.OPEN),)
    assert any(
        one.verb is Verb.READ and "does not declare this verb" in one.reason
        for one in compiled.dropped
    )


def test_a_verb_the_envelope_did_not_admit_runs_at_shadow() -> None:
    """`Envelope.tier` is asked on the enforcement path about a verb an untrusted container
    named, so the answer for one nobody compiled is the most supervised rung rather than an
    exception a caller might catch.

    Both halves: the recorded tier for a verb that is in the envelope, and SHADOW for one that
    is not.

    Delete this and the lookup can return the first tier in the list for every verb, which
    reads as the right answer for the common case and hands an uncompiled verb whatever rung
    the compiled one got.
    """
    compiled = compile_envelope(
        plan(request("filing"), registry()),
        books(),
        run_id="run-1",
        reach=reach(WRITE),
        ceiling=AutonomyTier.ASSISTED,
    )

    assert compiled.tier(Verb.SUBMIT) is AutonomyTier.ASSISTED
    assert compiled.tier(Verb.UPLOAD) is AutonomyTier.SHADOW


def test_the_digest_covers_the_origins_the_run_may_reach() -> None:
    """Two envelopes that differ only in where the run may go are different envelopes.

    The origin allowlist is the whole of M19.3.3 and a digest that did not cover it would let
    a policy compiled against a wider allowlist match an approval given for a narrower one.

    Delete this and the origins line can be dropped from the digest, which changes nothing any
    other test looks at.
    """
    narrow = compile_envelope(
        plan(request(), registry()),
        books(),
        run_id="run-1",
        reach=reach(READ),
        ceiling=AutonomyTier.AUTONOMOUS,
    )
    wide = Envelope(
        run_id=narrow.run_id,
        plan=narrow.plan,
        origins=frozenset({ORIGIN, "https://elsewhere.example"}),
        steps=narrow.steps,
        budget=narrow.budget,
        tiers=narrow.tiers,
    )

    assert narrow.digest() != wide.digest()


def test_the_two_digest_schemas_are_distinct_from_each_other_and_from_the_leash() -> None:
    """A schema tag exists to stop a digest computed for one thing meaning another.

    Asserted against the other schemas rather than against itself, which is the trap CLAUDE.md
    records from `hubspot.CEILING_NAME`: a test comparing a constant with the constant it
    imported is green for every value it could hold.

    Delete this and the envelope schema can be repointed at `brain.leash.v1`, and an envelope
    digest and an action digest become the same namespace.
    """
    # Asserted as the size of the set rather than as three inequalities, because every one of
    # these is a `Final` holding a literal and mypy folds `a != b` on two known literals into a
    # non-overlapping comparison error. The set is the same property with nothing to fold.
    assert len({DIGEST_SCHEMA, GOAL_SCHEMA, LEASH_DIGEST_SCHEMA}) == 3
