"""A browser write is Assisted unless a person who could perform it signed for its surface.

The clock is 2999, for the reason CLAUDE.md records about fixtures that go off.

Task ids: M19.7.3
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.browsing.autonomy import AutonomyError, SurfaceException, runs_unattended, sign
from brain.browsing.enforcer import Action, Refusal, Spend, authorise, compile_policy
from brain.browsing.envelope import Envelope, EnvelopeError, compile_envelope
from brain.browsing.observation import Node, Snapshot
from brain.browsing.planning import Goal, PlanRequest, plan
from brain.browsing.skill_gate import MAX_EXEMPTION
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.ops.halt import NOTHING_HALTED

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
READ = Capability(value="read:browser_surface")
WRITE = Capability(value="write:browser_surface")
ORIGIN = "https://books.example"
REASON = "the export button files nothing and runs nightly with nobody awake"


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


def holder(*capabilities: Capability, who: str = "alex") -> EntitlementSet:
    return EntitlementSet(
        principal_id=who,
        grants=tuple(
            Grant(capability=one, scope=Scope.department("finance")) for one in capabilities
        ),
    )


def signed(*, expires_at: datetime = NOW + timedelta(days=30)) -> SurfaceException:
    return sign(
        books(),
        "filing",
        signer=holder(WRITE, who="sam"),
        expires_at=expires_at,
        reason=REASON,
        now=NOW,
    )


def compiled(
    *,
    ceiling: AutonomyTier = AutonomyTier.AUTONOMOUS,
    exceptions: tuple[SurfaceException, ...] = (),
    at: datetime | None = NOW,
) -> Envelope:
    request = PlanRequest(
        goal=Goal(text="File this month's return", asked_by="alex"),
        target="books",
        surfaces=("invoices", "filing"),
    )
    return compile_envelope(
        plan(request, TargetRegistry(targets=(books(),))),
        books(),
        run_id="run-1",
        reach=holder(READ, WRITE),
        ceiling=ceiling,
        exceptions=exceptions,
        now=at,
    )


def submit(envelope: Envelope) -> Refusal | None:
    decided = authorise(
        compile_policy(envelope),
        Action(
            run_id="run-1", surface="filing", verb=Verb.SUBMIT, origin=ORIGIN, ref="n1", sequence=1
        ),
        Snapshot(
            run_id="run-1",
            sequence=1,
            origin=ORIGIN,
            nodes=(Node(ref="n1", role="button", name="File"),),
        ),
        Spend(),
        halts=NOTHING_HALTED,
        sequence=1,
    )
    return decided.refusal


def test_an_autonomous_agent_writes_at_assisted_with_no_exception() -> None:
    """The ceiling itself: the agent is trusted to act alone, the write still waits.

    Delete this and a browser write can run unattended because the agent's leash said so."""
    envelope = compiled()

    assert envelope.tier(Verb.SUBMIT) is AutonomyTier.ASSISTED
    assert envelope.unattended == ()
    assert envelope.awaits_approval()
    assert submit(envelope) is Refusal.WRITE_NOT_APPROVED


def test_a_signed_live_exception_lets_that_surfaces_writes_run_unattended() -> None:
    """The positive case, end to end: signed, compiled in, and the enforcer lets the write go
    with no approval.

    Delete this and an exception that changed nothing would pass every refusal below."""
    exception = signed()
    envelope = compiled(exceptions=(exception,))

    assert (exception.target, exception.surface, exception.signed_by) == ("books", "filing", "sam")
    assert envelope.unattended == (("filing", Verb.SUBMIT),)
    assert not envelope.awaits_approval()
    assert submit(envelope) is None


def test_an_exception_never_lifts_an_agent_below_autonomous() -> None:
    """An Assisted agent with a signed surface stays Assisted. See
    `AN_EXCEPTION_LIFTS_THE_SURFACE_AND_NEVER_THE_AGENT`.

    Delete this and whoever signs for a surface sets every agent's rung on it."""
    envelope = compiled(ceiling=AutonomyTier.ASSISTED, exceptions=(signed(),))

    assert envelope.unattended == ()
    assert envelope.awaits_approval()


def test_an_expired_exception_leaves_the_write_waiting() -> None:
    """Judged at the compilation instant: live one second before its end, spent at it.

    Delete this and a signature outlives its expiry."""
    exception = signed()

    assert compiled(
        exceptions=(exception,), at=exception.expires_at - timedelta(seconds=1)
    ).unattended
    assert compiled(exceptions=(exception,), at=exception.expires_at).unattended == ()


def test_an_exception_for_another_surface_or_target_applies_to_neither() -> None:
    """Exactly one target and one surface.

    Delete this and an exception on one system's export signs for another system's filing."""
    other_surface = SurfaceException(
        target="books",
        surface="exports",
        signed_by="sam",
        expires_at=NOW + timedelta(days=1),
        reason=REASON,
    )
    other_target = SurfaceException(
        target="payroll",
        surface="filing",
        signed_by="sam",
        expires_at=NOW + timedelta(days=1),
        reason=REASON,
    )

    assert compiled(exceptions=(other_surface, other_target)).unattended == ()


def test_a_read_is_never_unattended_even_on_a_signed_surface() -> None:
    """A read never waited for anybody, so it has no place in the set of writes nobody approved.

    Delete this and a read appears in `unattended`, which a reviewer reads as a write."""
    on_invoices = SurfaceException(
        target="books",
        surface="invoices",
        signed_by="sam",
        expires_at=NOW + timedelta(days=1),
        reason=REASON,
    )

    assert not runs_unattended(
        books(),
        "invoices",
        Verb.READ,
        ceiling=AutonomyTier.AUTONOMOUS,
        exceptions=(on_invoices,),
        now=NOW,
    )
    assert runs_unattended(
        books(),
        "invoices",
        Verb.CLICK,
        ceiling=AutonomyTier.AUTONOMOUS,
        exceptions=(on_invoices,),
        now=NOW,
    )


def test_a_signer_who_could_not_perform_the_write_is_refused() -> None:
    """Somebody who may only read the surface cannot sign for an agent to write on it.

    Delete this and anybody with a read grant can wave an agent through a filing."""
    with pytest.raises(AutonomyError, match="may not perform writes"):
        sign(
            books(),
            "filing",
            signer=holder(READ, who="sam"),
            expires_at=NOW + timedelta(days=1),
            reason=REASON,
            now=NOW,
        )


def test_an_exception_on_nothing_signable_is_refused() -> None:
    """An undeclared surface and a surface with no write both sign for nothing.

    Delete this and a signature reads on review as covering something it never could."""
    with pytest.raises(AutonomyError, match="declares no surface"):
        sign(
            books(),
            "exports",
            signer=holder(WRITE),
            expires_at=NOW + timedelta(days=1),
            reason=REASON,
            now=NOW,
        )
    with pytest.raises(AutonomyError, match="declares no write"):
        sign(
            books(),
            "invoices",
            signer=holder(READ, WRITE),
            expires_at=NOW + timedelta(days=1),
            reason=REASON,
            now=NOW,
        )


def test_an_exception_that_has_ended_or_runs_past_a_quarter_is_refused() -> None:
    """Both ends of the window, and the boundary of the quarter admitted.

    Delete this and a signature can be written to last a decade."""
    with pytest.raises(AutonomyError, match="already ended"):
        signed(expires_at=NOW)
    with pytest.raises(AutonomyError, match="outlives"):
        signed(expires_at=NOW + MAX_EXEMPTION + timedelta(seconds=1))

    assert signed(expires_at=NOW + MAX_EXEMPTION).expires_at == NOW + MAX_EXEMPTION


def test_an_exception_nobody_signed_or_with_no_reason_is_refused() -> None:
    """Delete this and an exception is a flag somebody set, with nothing to review."""
    with pytest.raises(AutonomyError, match="names no signer"):
        SurfaceException(
            target="books", surface="filing", signed_by=" ", expires_at=NOW, reason=REASON
        )
    with pytest.raises(AutonomyError, match="is not a reason"):
        SurfaceException(
            target="books", surface="filing", signed_by="sam", expires_at=NOW, reason="ok"
        )
    with pytest.raises(AutonomyError, match="no target or no surface"):
        SurfaceException(target="books", surface="", signed_by="sam", expires_at=NOW, reason=REASON)


def test_exceptions_with_no_instant_to_judge_them_at_are_refused() -> None:
    """Delete this and an expiry is judged at whatever clock the compiler happens to read."""
    with pytest.raises(EnvelopeError, match="no instant"):
        compiled(exceptions=(signed(),), at=None)


def test_an_envelope_that_waits_and_one_that_runs_unattended_have_different_digests() -> None:
    """An approval raised for one cannot start the other.

    Delete this and `unattended` can fall out of the digest, so an envelope compiled after an
    exception was signed matches a card approved before it."""
    assert compiled().digest() != compiled(exceptions=(signed(),)).digest()


def test_an_unattended_pair_that_is_not_an_admitted_write_is_refused() -> None:
    """Delete this and a read, or a step the envelope never admitted, can be sealed as a write
    nobody approved."""
    envelope = compiled()
    for pair in (("invoices", Verb.READ), ("exports", Verb.SUBMIT)):
        with pytest.raises(EnvelopeError, match="unattended"):
            Envelope(
                run_id=envelope.run_id,
                plan=envelope.plan,
                origins=envelope.origins,
                steps=envelope.steps,
                budget=envelope.budget,
                tiers=envelope.tiers,
                unattended=(pair,),
            )
