"""A browser write waits for a person's approval of the envelope, taken through the leash.

The suspension is raised by `raise_approval`, decided by `brain.console.approvals.decide` over a
real ledger chain, and read back by `approval_of`. Nothing here builds a decided suspension by
hand except the one test about an edited one.

The clock is 2999, for the reason CLAUDE.md records about fixtures that go off.

Task ids: M19.7.2
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.audit.ledger import AuditAction, AuditChain
from brain.audit.record import ApprovalVerdict, AuditRecorder
from brain.browsing.approval import (
    ApprovalError,
    EnvelopeApproval,
    approval_action,
    approval_of,
    approved,
    raise_approval,
)
from brain.browsing.autonomy import SurfaceException
from brain.browsing.enforcer import (
    Action,
    ActionRecord,
    EnforcementError,
    Policy,
    Refusal,
    Spend,
    authorise,
    compile_policy,
    recheck,
)
from brain.browsing.envelope import Envelope, compile_envelope
from brain.browsing.observation import Node, Snapshot
from brain.browsing.planning import Goal, PlanRequest, plan
from brain.browsing.sessions import (
    ACT_ON_SURFACE,
    ACT_ON_SURFACE_CAPABILITY,
    SurfaceReading,
    surface_scope,
)
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.console.approvals import card, decide
from brain.console.role_surfaces import pending_for
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect, ToolDefinition, TypedResult
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.gate.leash import (
    DEFAULT_APPROVAL_WINDOW,
    ApprovalState,
    SuspendedAction,
    render_artefact,
)
from brain.gate.leash import Action as LeashAction
from brain.ops.halt import NOTHING_HALTED
from brain.tools.registry import ToolRegistry

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
READ = Capability(value="read:browser_surface")
WRITE = ACT_ON_SURFACE_CAPABILITY
ORIGIN = "https://books.example"


def books(name: str = "books") -> Target:
    return Target(
        name=name,
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


def reach(who: str = "alex") -> EntitlementSet:
    return EntitlementSet(
        principal_id=who,
        grants=(
            Grant(capability=READ, scope=Scope.department("finance")),
            Grant(capability=WRITE, scope=Scope.department("finance")),
        ),
    )


def compiled(*surfaces: str) -> Envelope:
    request = PlanRequest(
        goal=Goal(text="File this month's return", asked_by="alex"),
        target="books",
        surfaces=surfaces or ("invoices", "filing"),
    )
    return compile_envelope(
        plan(request, TargetRegistry(targets=(books(),))),
        books(),
        run_id="run-1",
        reach=reach(),
        ceiling=AutonomyTier.AUTONOMOUS,
    )


def raised(envelope: Envelope | None = None) -> SuspendedAction:
    return raise_approval(
        envelope or compiled(),
        books(),
        agent_id="agent_books",
        reach=reach(),
        trace_id="trace_test",
        now=NOW,
    )


def an_approver(target: str = "books") -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_approver",
        grants=(Grant(capability=WRITE, scope=surface_scope(books(target))),),
    )


def a_recorder() -> AuditRecorder:
    return AuditRecorder(
        AuditChain(),
        actor_id="u_approver",
        ent_hash="e" * 32,
        trace_id="trace_test",
        clock=lambda: NOW,
    )


def act(verb: Verb, surface: str) -> Action:
    return Action(run_id="run-1", surface=surface, verb=verb, origin=ORIGIN, ref="n1", sequence=1)


def run(
    envelope: Envelope, approval: EnvelopeApproval | None, verb: Verb, surface: str
) -> Refusal | None:
    return authorise(
        compile_policy(envelope, approval),
        act(verb, surface),
        Snapshot(
            run_id="run-1",
            sequence=1,
            origin=ORIGIN,
            nodes=(Node(ref="n1", role="button", name="File"),),
        ),
        Spend(),
        halts=NOTHING_HALTED,
        sequence=1,
    ).refusal


def test_an_unapproved_write_is_refused_and_a_read_in_the_same_run_proceeds() -> None:
    """The gate, and the read-first order beside it.

    Delete this and a write in an envelope nobody approved runs as soon as a container starts."""
    envelope = compiled()

    assert run(envelope, None, Verb.SUBMIT, "filing") is Refusal.WRITE_NOT_APPROVED
    assert run(envelope, None, Verb.READ, "invoices") is None


def test_a_write_runs_once_a_person_approves_the_envelope_through_the_leash() -> None:
    """Raised, decided by the console's own `decide`, recorded in the ledger, read back, and
    compiled into a policy that lets the write go.

    Delete this and the approval route can be refused everything and every refusal still pass."""
    suspension = raised()
    decided = decide(
        suspension, an_approver(), a_recorder(), verdict=ApprovalVerdict.APPROVED, now=NOW
    )
    approval = approval_of(decided.suspension, compiled())

    assert decided.entry.action is AuditAction.APPROVAL
    assert decided.entry.subject == "leash:run-1"
    assert approval == EnvelopeApproval(
        run_id="run-1",
        envelope_digest=compiled().digest(),
        approved_by="u_approver",
        approved_at=NOW,
    )
    assert run(compiled(), approval, Verb.SUBMIT, "filing") is None


def test_a_rejected_or_undecided_envelope_grants_no_approval() -> None:
    """Delete this and `approval_of` can read a rejection as a yes."""
    rejected = decide(
        raised(),
        an_approver(),
        a_recorder(),
        verdict=ApprovalVerdict.REJECTED,
        now=NOW,
        reason_code="not_this_month",
    )

    assert rejected.suspension.state is ApprovalState.REJECTED
    assert approval_of(rejected.suspension, compiled()) is None
    assert approval_of(raised(), compiled()) is None


def test_an_approval_does_not_carry_to_an_envelope_that_changed() -> None:
    """Same run id, different permissions: the approval is not found for it, and handing it to
    the compiler anyway raises.

    Delete this and a person's yes to one set of writes starts another."""
    decided = decide(
        raised(), an_approver(), a_recorder(), verdict=ApprovalVerdict.APPROVED, now=NOW
    )
    approval = approval_of(decided.suspension, compiled())
    narrower = compiled("filing")

    assert approval is not None
    assert narrower.digest() != compiled().digest()
    assert approval_of(decided.suspension, narrower) is None
    with pytest.raises(EnforcementError, match="some other set of writes"):
        compile_policy(narrower, approval)
    with pytest.raises(EnforcementError, match="some other set of writes"):
        compile_policy(
            compiled(),
            EnvelopeApproval(
                run_id="run-2",
                envelope_digest=compiled().digest(),
                approved_by="u_approver",
                approved_at=NOW,
            ),
        )


def test_an_approval_counts_only_when_decided_inside_its_window_by_somebody() -> None:
    """Every half of `approved`, each with its positive beside it.

    Delete this and a decision recorded after the window closed, or by nobody, starts a run."""
    envelope = compiled()
    digest = envelope.digest()
    ends = NOW + timedelta(hours=4)

    def asked(**changes: object) -> EnvelopeApproval | None:
        fields: dict[str, object] = {
            "run_id": "run-1",
            "digest": digest,
            "state": ApprovalState.APPROVED,
            "decided_by": "u_approver",
            "decided_at": ends - timedelta(seconds=1),
            "expires_at": ends,
        }
        fields.update(changes)
        return approved(envelope, **fields)  # type: ignore[arg-type]

    assert asked() is not None
    assert asked(decided_at=ends) is None
    assert asked(state=ApprovalState.PENDING) is None
    assert asked(state=None) is None
    assert asked(run_id="run-2") is None
    assert asked(digest="f" * 64) is None
    assert asked(decided_by="") is None
    assert asked(decided_at=None) is None
    assert asked(expires_at=None) is None


def test_an_edited_suspension_or_one_for_another_tool_approves_nothing() -> None:
    """A suspension whose action no longer matches its stored digest was changed after it was
    shown, and one for an ordinary tool is not an envelope approval.

    Delete this and an approval of one card can be moved onto different arguments."""
    decided = decide(
        raised(), an_approver(), a_recorder(), verdict=ApprovalVerdict.APPROVED, now=NOW
    ).suspension
    original = decided.action
    edited = decided.model_copy(
        update={
            "action": original.model_copy(
                update={"args": {**original.args, "writes": "filing submit x9"}}
            )
        }
    )
    ticket = LeashAction(
        agent_id="agent_books",
        tool=ToolDefinition(
            name="ticket.update_status",
            description="an ordinary tool whose approval is not an envelope's",
            entity="ticket",
            required_capability="write:ticket.status",
            side_effect=SideEffect.WRITE,
        ),
        target="ticket",
        touched_fields=original.touched_fields,
        row=dict(original.row),
        args=dict(original.args),
    )
    other_tool = decided.model_copy(update={"action": ticket, "action_digest": ticket.digest()})

    assert approval_of(decided, compiled()) is not None
    assert approval_of(edited, compiled()) is None
    assert approval_of(other_tool, compiled()) is None


def test_only_somebody_who_could_write_the_target_is_offered_the_card() -> None:
    """The write capability scoped to this target is offered it; the same capability scoped to
    another target is not.

    Delete this and anybody holding a browser write anywhere approves writes everywhere."""
    suspension = raised()

    assert pending_for(an_approver(), [suspension], NOW) == (suspension,)
    assert pending_for(an_approver("payroll"), [suspension], NOW) == ()


def test_the_card_shows_the_writes_that_wait_and_never_the_capability() -> None:
    """What will happen, with counts, and none of the permission model.

    Delete this and the card can tell an approver nothing they could judge."""
    suspension = raised()
    shown = card(suspension, an_approver(), NOW)

    assert shown is not None
    assert "writes: filing submit x1" in shown.artefact
    assert f"origins: {ORIGIN}" in shown.artefact
    assert WRITE.value not in shown.artefact
    assert shown.runs_as == "alex"
    assert suspension.expires_at == NOW + DEFAULT_APPROVAL_WINDOW


def test_the_card_lists_only_the_writes_that_still_wait_for_a_person() -> None:
    """A write a signed exception compiled to run unattended is not on the card, and the write
    beside it that still waits is.

    Delete this and an approver is asked about writes their answer does not govern."""
    payments = Surface(
        name="payments",
        origin=ORIGIN,
        path="/payments",
        verbs=frozenset({Verb.OPEN, Verb.SUBMIT}),
        capability=WRITE,
    )
    both = Target(name="books", origins=frozenset({ORIGIN}), surfaces=(*books().surfaces, payments))
    exception = SurfaceException(
        target="books",
        surface="filing",
        signed_by="sam",
        expires_at=NOW + timedelta(days=1),
        reason="the filing export runs nightly and nobody needs to watch it",
    )
    request = PlanRequest(
        goal=Goal(text="File and pay", asked_by="alex"),
        target="books",
        surfaces=("filing", "payments"),
    )
    envelope = compile_envelope(
        plan(request, TargetRegistry(targets=(both,))),
        both,
        run_id="run-1",
        reach=reach(),
        ceiling=AutonomyTier.AUTONOMOUS,
        exceptions=(exception,),
        now=NOW,
    )

    action = approval_action(envelope, both, agent_id="agent_books")

    assert envelope.unattended == (("filing", Verb.SUBMIT),)
    assert action.args["writes"] == "payments submit x1"


def test_an_envelope_with_nothing_waiting_is_refused_a_card() -> None:
    """Delete this and the approval queue fills with runs that only read."""
    with pytest.raises(ApprovalError, match="nothing to approve"):
        raised(compiled("invoices"))


def test_an_envelope_raised_under_another_persons_reach_or_on_another_target_is_refused() -> None:
    """Delete this and a card carries somebody's name who never asked, or a run approved for one
    system is presented as a run on another."""
    with pytest.raises(ApprovalError, match="somebody other than the reach"):
        raise_approval(
            compiled(),
            books(),
            agent_id="agent_books",
            reach=reach("mallory"),
            trace_id="trace_test",
            now=NOW,
        )
    with pytest.raises(ApprovalError, match="cannot be approved as a run on"):
        approval_action(compiled(), books("payroll"), agent_id="agent_books")


def test_a_policy_carrying_an_approval_of_another_envelope_is_refused() -> None:
    """Delete this and a policy can be built by hand carrying any digest as approved."""
    with pytest.raises(EnforcementError, match="different envelope"):
        Policy(
            run_id="run-1",
            envelope_digest="a" * 64,
            origins=frozenset({ORIGIN}),
            allowed=frozenset(),
            budget=(),
            approved_digest="b" * 64,
        )


def test_the_control_plane_finds_a_write_nobody_approved_and_not_one_somebody_did() -> None:
    """The second check applies the same rule.

    Delete this and a container that skipped its own enforcer returns an unapproved filing and
    the control plane finds nothing."""
    records = [ActionRecord(action=act(Verb.SUBMIT, "filing"), claimed_allowed=True)]
    decided = decide(
        raised(), an_approver(), a_recorder(), verdict=ApprovalVerdict.APPROVED, now=NOW
    )

    assert any("is a write nobody approved" in one for one in recheck(compiled(), records))
    assert recheck(compiled(), records, approval_of(decided.suspension, compiled())) == ()


def test_an_approval_naming_nobody_or_no_digest_is_refused() -> None:
    """Delete this and an approval can be recorded with no name on it."""
    with pytest.raises(ApprovalError, match="names nobody"):
        EnvelopeApproval(run_id="run-1", envelope_digest="a" * 64, approved_by=" ", approved_at=NOW)
    with pytest.raises(ApprovalError, match="not an envelope digest"):
        EnvelopeApproval(
            run_id="run-1", envelope_digest="short", approved_by="u_approver", approved_at=NOW
        )


def test_the_write_tool_registers_and_its_action_digest_covers_the_envelope() -> None:
    """The tool is real and the approval action changes when the envelope does.

    Delete this and the write tool can drift into one no registry accepts, or the envelope's
    digest can fall out of the action a person approves."""

    def handler() -> TypedResult[SurfaceReading]:
        return TypedResult[SurfaceReading](records=())

    registered = ToolRegistry().register(ACT_ON_SURFACE, handler, scope=surface_scope(books()))
    wide = approval_action(compiled(), books(), agent_id="agent_books")
    narrow = approval_action(compiled("filing"), books(), agent_id="agent_books")

    assert registered.capability == WRITE
    assert ACT_ON_SURFACE.side_effect is SideEffect.SEND
    assert wide.digest() != narrow.digest()
    assert render_artefact(wide) != ""
