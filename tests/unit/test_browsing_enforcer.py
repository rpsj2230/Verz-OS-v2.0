"""The guard: one action at a time, against a policy nothing in the run can change.

Every check has a refusal test and a sibling proving the action still works when that check
passes, because a guard tested only by its refusals is satisfied by a function that refuses
everything.

Task ids: M19.3.1, M19.3.2, M19.3.3, M19.3.4, M19.3.6, M19.6.5
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from brain.browsing.enforcer import (
    Action,
    ActionRecord,
    Enforcement,
    EnforcementError,
    Policy,
    Refusal,
    Spend,
    authorise,
    compile_policy,
    enforcement_gaps,
    policy_gaps,
    recheck,
    stopped_now,
)
from brain.browsing.envelope import Envelope, compile_envelope
from brain.browsing.observation import Node, Snapshot
from brain.browsing.planning import Goal, PlanRequest, plan
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.ops.halt import (
    NOTHING_HALTED,
    Effect,
    Halt,
    HaltScope,
    HaltState,
    in_force,
    stop_everything,
)

READ = Capability(value="read:browser_surface")
WRITE = Capability(value="write:browser_surface")
ORIGIN = "https://books.example"
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def books() -> Target:
    return Target(
        name="books",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="invoices",
                origin=ORIGIN,
                path="/invoices",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=READ,
                reads=("number",),
            ),
            Surface(
                name="filing",
                origin=ORIGIN,
                path="/filing",
                verbs=frozenset({Verb.OPEN, Verb.SUBMIT}),
                capability=WRITE,
            ),
        ),
    )


def envelope(*surfaces: str) -> Envelope:
    request = PlanRequest(
        goal=Goal(text="Read this month's invoice totals", asked_by="alex"),
        target="books",
        surfaces=surfaces or ("invoices",),
    )
    reach = EntitlementSet(
        principal_id="alex",
        grants=(
            Grant(capability=READ, scope=Scope.department("finance")),
            Grant(capability=WRITE, scope=Scope.department("finance")),
        ),
    )
    return compile_envelope(
        plan(request, TargetRegistry(targets=(books(),))),
        books(),
        run_id="run-1",
        reach=reach,
        ceiling=AutonomyTier.AUTONOMOUS,
    )


def snapshot(sequence: int = 1, origin: str = ORIGIN, run_id: str = "run-1") -> Snapshot:
    return Snapshot(
        run_id=run_id,
        sequence=sequence,
        origin=origin,
        nodes=(Node(ref="n1", role="table", name="Invoices"),),
    )


def action(**changes: object) -> Action:
    fields: dict[str, object] = {
        "run_id": "run-1",
        "surface": "invoices",
        "verb": Verb.READ,
        "origin": ORIGIN,
        "ref": "n1",
        "sequence": 1,
    }
    fields.update(changes)
    return Action(**fields)  # type: ignore[arg-type]


def decide(
    one: Action,
    *,
    seen: Snapshot | None = None,
    spend: Spend | None = None,
    halts: HaltState = NOTHING_HALTED,
    sequence: int = 1,
    env: Envelope | None = None,
) -> Enforcement:
    policy = compile_policy(env or envelope())
    return authorise(
        policy,
        one,
        seen or snapshot(),
        spend or Spend(),
        halts=halts,
        sequence=sequence,
    )


# --------------------------------------------------------------------- the policy


def test_a_policy_carries_the_digest_of_the_envelope_it_came_from() -> None:
    """The whole of the control plane's second check is a comparison against this.

    Delete this and `compile_policy` can stop carrying the digest, and a policy inside a
    container has nothing tying it to what was sealed outside one.
    """
    sealed = envelope()
    policy = compile_policy(sealed)

    assert policy.envelope_digest == sealed.digest()
    assert policy.run_id == sealed.run_id
    assert policy.origins == sealed.origins


def test_a_policy_has_no_field_that_would_let_it_be_reloaded() -> None:
    """M19.3.1. The failure is not somebody deciding to make a policy refreshable, it is a
    field called `refreshed_at` arriving with a plausible default.

    Delete this and the shape check goes with it, and the field arrives in a change that is
    about something else.
    """
    assert policy_gaps() == ()


def test_a_policy_without_an_envelope_digest_is_refused() -> None:
    """The positive case for the shape check, and for the constructor's own guard.

    Delete this and a policy can be built with nothing to compare, which makes `recheck`
    silently weaker rather than failing.
    """
    with pytest.raises(EnforcementError, match="no envelope digest"):
        Policy(
            run_id="run-1",
            envelope_digest="",
            origins=frozenset({ORIGIN}),
            allowed=frozenset(),
            budget=(),
        )


def test_a_policy_belonging_to_no_run_is_refused() -> None:
    """A policy with no run cannot be matched to an action, and every action would pass the
    run check by comparing two empty strings.

    Delete this and the first check in `authorise` compares nothing against nothing.
    """
    with pytest.raises(EnforcementError, match="belonging to no run"):
        Policy(
            run_id="  ",
            envelope_digest="abc",
            origins=frozenset({ORIGIN}),
            allowed=frozenset(),
            budget=(),
        )


# --------------------------------------------------------------------- the decision


def test_an_action_the_envelope_admits_on_the_current_snapshot_is_allowed() -> None:
    """The positive case. Every refusal below is worthless without it.

    Delete this and `authorise` can return a refusal for everything, and each refusal test
    still passes with its own reason arriving by accident.
    """
    verdict = decide(action())

    assert verdict.allowed
    assert verdict.refusal is None


def test_a_halt_on_everything_stops_a_run_at_its_next_action() -> None:
    """M19.6.5, and the first consumer of `Effect.SIGNAL_RUNNING` in this repository.

    Delete this and the stop button refuses new browser sessions and lets a running one carry
    on typing into a supplier portal, which is the first lie `brain.ops.halt` names.
    """
    halted = in_force([stop_everything(declared_by="sam", at=NOW, reason="supplier portal wrong")])

    verdict = decide(action(), halts=halted)

    assert not verdict.allowed
    assert verdict.refusal is Refusal.HALTED


def test_a_halt_state_that_could_not_be_read_stops_a_run() -> None:
    """Fails closed, exactly as `HaltState.admits` does.

    The moment the halt store is unreachable is disproportionately likely to be the moment
    something is wrong, and carrying on then means ignoring a halt during the incident that
    caused it.

    Delete this and `stopped_now` can drop the `known` half, which reads as a simplification
    and inverts the one thing in this system that fails closed.
    """
    assert stopped_now(HaltState.unknown())

    verdict = decide(action(), halts=HaltState.unknown())

    assert verdict.refusal is Refusal.HALTED


def test_a_halt_that_only_refuses_new_work_does_not_stop_a_running_action() -> None:
    """The two effects are separate and this is the one that proves they are read separately.

    A halt carrying `REFUSE_NEW` alone stops admission and says nothing about work in flight,
    so treating every covering halt as a stop would refuse actions nothing had stopped. That
    is the bug `brain.ops.halt` records finding in `HaltState.refusal`, from the other side.

    Delete this and `stopped_now` can be written as "any covering halt", which is the obvious
    implementation and the wrong one.
    """
    refuse_only = Halt(
        scope=HaltScope.EVERYTHING,
        target="",
        declared_by="sam",
        at=NOW,
        reason="draining before a deploy",
        effects=frozenset({Effect.REFUSE_NEW}),
    )

    assert not stopped_now(in_force([refuse_only]))
    assert decide(action(), halts=in_force([refuse_only])).allowed


def test_an_action_from_another_run_is_refused() -> None:
    """Nothing below the run check means anything if the policy is not this run's.

    Delete this and a container can present an action from a run with a wider envelope and
    have it decided against this policy's origins by coincidence.
    """
    verdict = decide(action(run_id="run-2"))

    assert verdict.refusal is Refusal.WRONG_RUN


def test_an_origin_outside_the_allowlist_is_refused() -> None:
    """M19.3.3, per action rather than per run, because a run navigates.

    Delete this and an undeclared redirect carries the session to a host nobody approved, and
    the reference on that page validates against whatever tree came back.
    """
    verdict = decide(action(origin="https://evil.test"), seen=snapshot(origin="https://evil.test"))

    assert verdict.refusal is Refusal.ORIGIN_NOT_ALLOWED


def test_an_action_on_an_allowed_origin_that_is_not_the_snapshot_is_refused() -> None:
    """Two origins, two checks. A tree read on one host cannot authorise an action on another.

    Delete this and a target allowing an identity host and an application host lets a
    reference read on one be acted on at the other, and both pass the allowlist.
    """
    wide = Target(
        name="books",
        origins=frozenset({ORIGIN, "https://login.example"}),
        surfaces=books().surfaces,
    )
    sealed = envelope()
    policy = Policy(
        run_id=sealed.run_id,
        envelope_digest=sealed.digest(),
        origins=wide.origins,
        allowed=frozenset((step.surface, step.verb) for step in sealed.steps),
        budget=sealed.budget,
    )

    verdict = authorise(
        policy,
        action(origin="https://login.example"),
        snapshot(),
        Spend(),
        halts=NOTHING_HALTED,
        sequence=1,
    )

    assert verdict.refusal is Refusal.ORIGIN_NOT_THE_SNAPSHOT


def test_an_action_citing_an_older_snapshot_is_refused() -> None:
    """M19.3.2. A reference is only meaningful against the tree it was minted from.

    Delete this and the page can replace the node under a reference between the snapshot and
    the action, and the action succeeds on a different element with nothing to show for it.
    """
    verdict = decide(action(sequence=1), seen=snapshot(sequence=2), sequence=2)

    assert verdict.refusal is Refusal.STALE_SNAPSHOT


def test_a_snapshot_the_control_plane_did_not_expect_is_refused() -> None:
    """The number comes from outside the container, so replaying an old tree with its own old
    number does not work.

    Delete this and the currency check reads the sequence off the snapshot it is checking,
    which is a comparison of a value with itself.
    """
    verdict = decide(action(sequence=1), seen=snapshot(sequence=1), sequence=2)

    assert verdict.refusal is Refusal.STALE_SNAPSHOT


def test_a_reference_that_is_not_in_the_snapshot_is_refused() -> None:
    """The reference check itself, against the tree just produced.

    Delete this and a container can name any element it likes, including one it invented,
    and the enforcer has nothing to compare it to.
    """
    verdict = decide(action(ref="n99"))

    assert verdict.refusal is Refusal.UNKNOWN_REFERENCE


def test_an_action_that_touches_no_node_needs_no_reference() -> None:
    """The positive sibling: `OPEN` navigates and has nothing to point at.

    Delete this and the reference check can be made unconditional, which refuses every
    navigation and makes a run impossible to start.
    """
    verdict = decide(action(verb=Verb.OPEN, ref=""))

    assert verdict.allowed


def test_a_surface_and_verb_pair_the_envelope_did_not_admit_is_refused() -> None:
    """The envelope is the contract, and the container is not asked whether it agrees.

    Delete this and a run can act on a surface that was dropped during compilation, which is
    the exact set of steps the caller's reach did not admit.
    """
    verdict = decide(action(surface="filing", verb=Verb.SUBMIT))

    assert verdict.refusal is Refusal.NOT_IN_ENVELOPE


def test_a_write_is_allowed_until_the_planned_count_is_spent() -> None:
    """M19.3.4, in both directions. The budget is the plan's own count.

    A refusal test alone would be satisfied by a budget of zero for everything, so the first
    half of this is what proves a planned write can happen at all.

    Delete this and a loop that submits twice where the plan submitted once is refused by
    nothing, and the second submission is the one that files a duplicate.
    """
    sealed = envelope("filing")
    first = decide(
        action(surface="filing", verb=Verb.SUBMIT, ref="n1"),
        env=sealed,
    )

    assert first.allowed
    assert first.spend.of(Verb.SUBMIT) == 1

    second = decide(
        action(surface="filing", verb=Verb.SUBMIT, ref="n1"),
        spend=first.spend,
        env=sealed,
    )

    assert second.refusal is Refusal.BUDGET_SPENT


def test_a_refused_action_does_not_spend_the_budget() -> None:
    """A caller deciding for itself whether to advance the count advances it on the refusal
    path, which costs a run its budget for actions it was not allowed to take.

    Delete this and a run that is refused three times has no writes left for the one it was
    entitled to.
    """
    verdict = decide(action(verb=Verb.SUBMIT, surface="filing", ref="n99"), env=envelope("filing"))

    assert not verdict.allowed
    assert verdict.spend == Spend()


def test_a_read_never_touches_the_write_budget() -> None:
    """Reads are unbounded by the envelope's count and that is deliberate: the budget is about
    what a run changes, not about how much it looks.

    Delete this and a read starts consuming a write allowance, which exhausts a filing budget
    by opening a page.
    """
    verdict = decide(action())

    assert verdict.allowed
    assert verdict.spend == Spend()


def test_an_enforcement_that_refuses_without_a_reason_is_refused() -> None:
    """A refusal nothing can name is a refusal nothing downstream can report.

    Delete this and a code path can return a bare False, and the operator screen shows a run
    that stopped for no stated cause.
    """
    with pytest.raises(EnforcementError, match="names no reason"):
        Enforcement(allowed=False, spend=Spend())

    with pytest.raises(EnforcementError, match="carries refusal"):
        Enforcement(allowed=True, spend=Spend(), refusal=Refusal.HALTED)


# --------------------------------------------------------------------- the second check


def test_the_control_plane_reaches_the_same_verdict_whatever_the_container_claimed() -> None:
    """M19.3.6. The container's own verdict is not read, and the property is the invariance.

    Asserted by running the same records twice with the claim flipped, rather than by reading
    the source, because "does not read a field" is exactly the kind of claim that stops being
    true in a change about something else.

    Delete this and `recheck` can start believing the container, which is the process whose
    compromise it exists to survive.
    """
    sealed = envelope("filing")
    records = [
        ActionRecord(action=action(surface="filing", verb=Verb.SUBMIT), claimed_allowed=True),
        ActionRecord(action=action(surface="filing", verb=Verb.SUBMIT), claimed_allowed=True),
    ]
    denied = [ActionRecord(action=one.action, claimed_allowed=False) for one in records]

    assert recheck(sealed, records) == recheck(sealed, denied)


def test_the_control_plane_finds_a_write_the_container_allowed_beyond_the_budget() -> None:
    """The finding that matters: a container that bypassed its own enforcer still has to
    report what it did.

    Delete this and the second check has nothing to say about the case it was built for.
    """
    sealed = envelope("filing")
    records = [
        ActionRecord(action=action(surface="filing", verb=Verb.SUBMIT), claimed_allowed=True),
        ActionRecord(action=action(surface="filing", verb=Verb.SUBMIT), claimed_allowed=True),
    ]

    findings = recheck(sealed, records)

    assert any("against a budget of 1" in one for one in findings)


def test_the_control_plane_finds_an_action_that_was_never_in_the_envelope() -> None:
    """Delete this and a container can act on a surface the caller's reach did not admit and
    the returned record passes review."""
    findings = recheck(
        envelope(),
        [ActionRecord(action=action(surface="filing", verb=Verb.SUBMIT), claimed_allowed=True)],
    )

    assert any("is not in the envelope" in one for one in findings)


def test_the_control_plane_finds_a_run_that_went_back_to_an_older_tree() -> None:
    """Ordering is decidable from the sealed side, and going backwards is what a replay looks
    like from here.

    Delete this and a container can act on a tree it had already replaced, and only the
    in-container check, the one inside the blast radius, would ever have noticed.
    """
    findings = recheck(
        envelope(),
        [
            ActionRecord(action=action(sequence=2), claimed_allowed=True),
            ActionRecord(action=action(sequence=1), claimed_allowed=True),
        ],
    )

    assert any("acted on a tree it had already replaced" in one for one in findings)


def test_a_clean_run_produces_no_findings_in_the_control_plane() -> None:
    """The positive case. A `recheck` that always found something would be ignored within a
    week, which is worse than not having one.

    Delete this and the second check can become unconditional and every run reads as a
    breach.
    """
    findings = recheck(
        envelope(),
        [
            ActionRecord(action=action(verb=Verb.OPEN, ref=""), claimed_allowed=False),
            ActionRecord(action=action(verb=Verb.READ), claimed_allowed=False),
        ],
    )

    assert findings == ()


# --------------------------------------------------------------------- what is not enforced


def test_the_module_reports_the_halt_axes_it_does_not_enforce() -> None:
    """An administrator halting one compromised agent must not have to read the code to find
    out that no browser session stops.

    Delete this and the gap becomes a paragraph in a commit message, which is where the
    identical gap about admission was before `brain.ops.halt.ENFORCED_AXES` existed.
    """
    gaps = enforcement_gaps()

    assert any("halt on everything" in one for one in gaps)
    assert any("agent" in one for one in gaps)
    assert any("belongs on HaltState" in one for one in gaps)


def test_an_action_whose_origin_did_not_parse_is_refused() -> None:
    """`null` is what a sandboxed iframe and a `file://` document send, and it is the absence
    of an origin rather than a value for one.

    Refused on its own line rather than left to the membership test, because a single
    membership test admits every unparseable origin the moment an empty entry reaches the
    allowlist by any route.

    Delete this and the enforcement path stops stating the rule, and it holds only for as long
    as every constructor upstream keeps refusing the empty entry.
    """
    for unparseable in ("null", "not-a-url", ""):
        verdict = decide(action(origin=unparseable))

        assert verdict.refusal is Refusal.ORIGIN_NOT_ALLOWED, unparseable


def test_the_control_plane_finds_an_action_whose_origin_did_not_parse() -> None:
    """The same rule on the trusted side, where the record is being reviewed afterwards.

    Delete this and a returned record naming `null` reads as an origin the envelope allowed.
    """
    findings = recheck(
        envelope(),
        [ActionRecord(action=action(origin="null"), claimed_allowed=True)],
    )

    assert any("an origin the envelope does not allow" in one for one in findings)


def test_an_unparseable_origin_is_refused_even_if_the_allowlist_holds_an_empty_entry() -> None:
    """The defence-in-depth half of the empty-origin hole, on the enforcement path.

    `brain.browsing.targets` refuses an empty entry at construction, but a `Policy` is a value
    a caller can build directly, and this is the function that decides. With an empty entry in
    the set, a bare membership test would admit `null`, `not-a-url` and a `file://` document,
    because that is what `normalise_origin` returns for all three.

    Delete this and the check on the enforcement path becomes an equivalent mutation, which is
    exactly how the audit reported it before this existed.
    """
    sealed = envelope()
    leaky = Policy(
        run_id=sealed.run_id,
        envelope_digest=sealed.digest(),
        origins=frozenset({ORIGIN, ""}),
        allowed=frozenset((step.surface, step.verb) for step in sealed.steps),
        budget=sealed.budget,
    )

    for unparseable in ("null", "not-a-url", ""):
        verdict = authorise(
            leaky,
            action(origin=unparseable),
            snapshot(),
            Spend(),
            halts=NOTHING_HALTED,
            sequence=1,
        )

        assert verdict.refusal is Refusal.ORIGIN_NOT_ALLOWED, unparseable


def test_a_snapshot_from_another_run_is_refused_even_at_the_expected_sequence() -> None:
    """The run half of the currency check, which the sequence half cannot see.

    References are minted per tree, so two runs against one target produce colliding ones by
    construction. A snapshot from run two at sequence one satisfies every number the enforcer
    compares and describes a different browser.

    Delete this and `is_current` can be reduced to a sequence comparison, which is the obvious
    simplification and drops the only check that the tree belongs to this run.
    """
    verdict = decide(
        action(sequence=1),
        seen=snapshot(sequence=1, run_id="run-2"),
        sequence=1,
    )

    assert verdict.refusal is Refusal.STALE_SNAPSHOT


def test_the_control_plane_finds_a_record_belonging_to_another_run() -> None:
    """A container returning records from a different run is either confused or presenting
    another run's work for approval against this envelope.

    Delete this and the first check in `recheck` is unreachable, and a record naming any run
    at all is measured against this policy's origins and budget.
    """
    findings = recheck(
        envelope(),
        [ActionRecord(action=action(run_id="run-2"), claimed_allowed=True)],
    )

    assert any("belongs to run 'run-2'" in one for one in findings)


def test_a_policy_type_carrying_a_reason_to_reload_is_reported() -> None:
    """The positive case for the shape check: it has to be able to fail.

    Planted rather than asserted against `Policy`, because the whole value of the check is
    that it fires when the field appears, and a check run only against a type that does not
    carry one reports the same clean answer as a check that scans nothing.

    Delete this and `policy_gaps` could return an empty tuple unconditionally, and the test
    that `Policy` has no such field would pass for every shape `Policy` could have.
    """

    @dataclass(frozen=True)
    class Refreshable:
        run_id: str
        envelope_digest: str
        refreshed_at: str

    findings = policy_gaps(Refreshable)

    assert len(findings) == 1
    assert "Refreshable carries refreshed_at" in findings[0]


def test_a_policy_type_with_nothing_to_compare_against_the_envelope_is_reported() -> None:
    """The other half of the same check, and the one that matters to `recheck`.

    A policy with no digest cannot be checked against the envelope it claims to come from, and
    the control plane's second check then has nothing to compare.

    Delete this and the digest can be dropped from `Policy` in a change about something else,
    and only the field's absence would say so.
    """

    @dataclass(frozen=True)
    class Undigested:
        run_id: str
        origins: frozenset[str]

    findings = policy_gaps(Undigested)

    assert any("carries no envelope digest" in one for one in findings)


def test_a_write_the_policy_admits_with_no_budget_row_is_refused() -> None:
    """Zero is the honest answer for a verb nothing budgeted, and it has to be the answer the
    lookup gives rather than one the caller supplies.

    `compile_envelope` budgets every write step it keeps, so this state does not arise from a
    compilation. It arises from a `Policy` built directly, which is a value a caller can
    construct, and the safe reading of a missing budget row is none rather than unlimited.

    Found by mutation: returning 99 for an unbudgeted verb passed every other test here,
    because the envelope check already refuses a verb that is not admitted at all.

    Delete this and the default can be raised to anything, and a policy whose budget rows were
    lost admits writes without limit.
    """
    sealed = envelope("filing")
    unbudgeted = Policy(
        run_id=sealed.run_id,
        envelope_digest=sealed.digest(),
        origins=sealed.origins,
        allowed=frozenset({("filing", Verb.SUBMIT)}),
        budget=(),
    )

    verdict = authorise(
        unbudgeted,
        action(surface="filing", verb=Verb.SUBMIT),
        snapshot(),
        Spend(),
        halts=NOTHING_HALTED,
        sequence=1,
    )

    assert verdict.refusal is Refusal.BUDGET_SPENT
