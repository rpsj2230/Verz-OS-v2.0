"""One counter, one capability, and a skill loader that prefers the API.

Three leaves about what a browser run is allowed to start as, and one about whether it should
have been a browser at all.

Task ids: M19.6.1, M19.6.5, M19.6.7, M19.7.1
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.browsing.sessions import (
    BROWSE_SURFACE,
    BROWSING_CAPABILITIES,
    READ_SURFACE,
    SurfaceReading,
    capability_gaps,
    concurrency_gaps,
    may_start,
    surface_scope,
    write_verbs_offered,
)
from brain.browsing.skill_gate import (
    MAX_EXEMPTION,
    Exemption,
    SkillGateError,
    available_api_tools,
    load_gaps,
    may_load,
)
from brain.browsing.targets import Surface, Target, Verb
from brain.core.entitlement import Capability
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.ops.admission import (
    Budget,
    CapacityState,
    RefusalKind,
    Resource,
    Verdict,
    seed_budgets,
)
from brain.ops.halt import in_force, stop_everything
from brain.tools.registry import ToolRegistry
from brain.tools.skills import Skill

READ = Capability(value="read:browser_surface")
WRITE = Capability(value="write:browser_surface")
ORIGIN = "https://books.example"
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def books(**changes: object) -> Target:
    fields: dict[str, object] = {
        "name": "books",
        "origins": frozenset({ORIGIN}),
        "surfaces": (
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
        "api_tools": (),
    }
    fields.update(changes)
    return Target(**fields)  # type: ignore[arg-type]


def browser_budget(limit: int = 2) -> tuple[Budget, ...]:
    return tuple(one for one in seed_budgets() if one.resource is Resource.BROWSER_SESSIONS) or (
        Budget(
            resource=Resource.BROWSER_SESSIONS,
            limit=limit,
            mean_service_seconds=60.0,
            reason="a browser session is hundreds of megabytes",
        ),
    )


# --------------------------------------------------------------------- concurrency


def test_a_browser_session_is_admitted_by_the_one_admission_controller() -> None:
    """M19.6.1. The positive case, and the whole design: this module does not count.

    Delete this and a tally in `sessions` looks like a reasonable thing to add, and the number
    on the operate screen stops being the number that admitted the work.
    """
    decision = may_start(
        trace_id="t-1",
        budgets=browser_budget(),
        state=CapacityState(),
        now=NOW,
    )

    assert decision.verdict is Verdict.ADMITTED
    assert decision.request.resource is Resource.BROWSER_SESSIONS
    assert decision.request.key == ""


def test_a_browser_session_is_refused_when_the_global_budget_is_full() -> None:
    """The refusal comes from admission's arithmetic and not from anything here.

    Delete this and `may_start` can stop passing the state through, which admits every session
    while still calling the controller.
    """
    budgets = browser_budget()
    full = CapacityState(used={(Resource.BROWSER_SESSIONS, ""): budgets[0].limit})

    decision = may_start(trace_id="t-1", budgets=budgets, state=full, now=NOW)

    assert decision.verdict is not Verdict.ADMITTED


def test_a_halt_on_everything_refuses_a_new_browser_session() -> None:
    """M19.6.5, the admission half. The other half, stopping a run already in flight, is in
    `test_browsing_enforcer.py`.

    A halt arrives as `RefusalKind.HALTED` rather than as a capacity refusal, because "add
    capacity" is the wrong thing to tell somebody who pressed the stop button themselves.

    Delete this and the stop button stops nothing that has not started, and a halted system
    keeps opening browser sessions.
    """
    halted = in_force([stop_everything(declared_by="sam", at=NOW, reason="portal misbehaving")])

    decision = may_start(
        trace_id="t-1",
        budgets=browser_budget(),
        state=CapacityState(),
        now=NOW,
        halts=halted,
    )

    assert decision.verdict is not Verdict.ADMITTED
    assert decision.halted
    assert decision.log_record()["refusal_kind"] == RefusalKind.HALTED.value
    assert "add capacity" not in decision.log_record()["operator_action"]


def test_browser_sessions_are_budgeted_once_globally_and_not_per_domain() -> None:
    """M19.6.2 is not delivered, and this is the structural reason rather than an opinion.

    `BROWSER_SESSIONS` is not in `admission.PER_CONNECTOR`, so an `AdmissionRequest` naming a
    domain raises. Asserted so that the gap is a fact about the code rather than a sentence in
    a report.

    Delete this and somebody closes M19.6.2 by adding a counter here, which is the second
    counter this module exists not to be.
    """
    from brain.core.lane import Lane
    from brain.gate.context import TrafficClass
    from brain.ops.admission import PER_CONNECTOR, AdmissionRequest

    assert Resource.BROWSER_SESSIONS not in PER_CONNECTOR

    with pytest.raises(ValueError, match="budgeted once globally"):
        AdmissionRequest(
            trace_id="t-1",
            lane=Lane.TASK,
            traffic_class=TrafficClass.AUTOMATION,
            resource=Resource.BROWSER_SESSIONS,
            key="books.example",
        )

    assert any("M19.6.2" in one for one in concurrency_gaps())
    assert any("M19.6.3" in one for one in concurrency_gaps())


# --------------------------------------------------------------------- read only first


def test_the_only_browsing_capability_that_ships_is_a_read() -> None:
    """M19.7.1 is a claim about what does not exist, so this is the test that fails on the
    day it starts existing.

    Delete this and a write capability can be added without anybody closing M19.7.2, which
    asks for it to sit behind envelope approval that nothing here builds.
    """
    assert BROWSING_CAPABILITIES == (BROWSE_SURFACE,)
    assert BROWSE_SURFACE.verb == "read"
    assert READ_SURFACE.side_effect is SideEffect.NONE
    assert capability_gaps() == ()


def test_a_write_capability_would_be_reported() -> None:
    """The positive case for the check: it has to be able to fail.

    Delete this and `capability_gaps` could return an empty tuple unconditionally, and the
    test above would pass for every capability list the package could ship.
    """
    gaps = capability_gaps(capabilities=(WRITE,))

    assert any("whose verb is 'write'" in one for one in gaps)

    with_effect = ToolDefinition(
        name="browser.submit_form",
        description="Submit a declared form on a declared surface.",
        entity="browser_surface",
        required_capability=WRITE.value,
        side_effect=SideEffect.WRITE,
        identity_mode=IdentityMode.SERVICE,
        source="browser",
    )

    reported = capability_gaps(definitions=(with_effect,))

    assert any("declares side effect write" in one for one in reported)


def test_the_read_tool_passes_every_registration_rule() -> None:
    """The definition is real rather than aspirational, and a registry says so.

    `ToolRegistry.register` applies the name grammar, the source agreement, the capability
    parse, the effect-versus-capability rule, the service scope requirement and the typed
    result contract. Registering it here is what distinguishes a shipped tool from a
    plausible-looking constant.

    Delete this and the definition can drift into something no registry would accept, which
    would be discovered by whoever wires the runner rather than by this suite.
    """

    def handler() -> TypedResult[SurfaceReading]:
        return TypedResult[SurfaceReading](records=())

    registry = ToolRegistry()
    registered = registry.register(
        READ_SURFACE,
        handler,
        scope=surface_scope(books()),
    )

    assert registered.capability == BROWSE_SURFACE
    assert registered.source == "browser"
    assert registry.has("browser.read_surface")


def test_a_service_tool_carries_a_scope_that_narrows_to_one_target() -> None:
    """A shared credential is not narrowed by the source, so an unrestricted scope is refused
    as firmly as a missing one.

    Delete this and `surface_scope` can start returning `Scope.unrestricted()`, which is a
    scope that satisfies "it has a scope" and reaches everything the credential reaches.
    """
    scope = surface_scope(books())

    assert not scope.is_unrestricted()
    assert scope.matches({"browser_target": "books"})
    assert not scope.matches({"browser_target": "ledger"})


def test_a_target_may_declare_write_surfaces_before_a_write_capability_exists() -> None:
    """The declaration is configuration and the capability is what has not shipped.

    Delete this and the registry becomes unable to describe a system fully until the write
    path exists, which pushes people to describe it wrongly instead.
    """
    assert write_verbs_offered(books()) == (Verb.SUBMIT,)
    assert capability_gaps() == ()


# --------------------------------------------------------------------- the skill loader


def browser_skill() -> Skill:
    return Skill(
        name="file-the-return",
        description="Drive the books portal to read the invoice totals.",
        tools=("browser.read_surface",),
    )


def registry_with(*names: str) -> ToolRegistry:
    def handler() -> TypedResult[SurfaceReading]:
        return TypedResult[SurfaceReading](records=())

    registry = ToolRegistry()
    for name in names:
        registry.register(
            ToolDefinition(
                name=name,
                description="An API tool that does this without a browser.",
                entity="browser_surface",
                required_capability=READ.value,
                side_effect=SideEffect.NONE,
                identity_mode=IdentityMode.DELEGATED,
            ),
            handler,
        )
    return registry


def test_a_browser_skill_loads_when_no_api_tool_does_the_job() -> None:
    """The positive case. Most of what this package is for is systems with no API.

    Delete this and the loader can be made to refuse every browser skill, which satisfies the
    refusal test below and makes the whole package unreachable.
    """
    assert may_load(browser_skill(), books(), registry_with(), now=NOW)
    assert load_gaps(browser_skill(), books(), registry_with(), now=NOW) == ()


def test_a_browser_skill_is_refused_where_a_registered_api_tool_exists() -> None:
    """M19.6.7. The browser is the worst way to talk to a system that has an API.

    Delete this and a skill drives a website for something a connector already does, with all
    the cost and none of the necessity.
    """
    target = books(api_tools=("books.read_invoices",))

    gaps = load_gaps(browser_skill(), target, registry_with("books.read_invoices"), now=NOW)

    assert any("already does this without one" in one for one in gaps)
    assert not may_load(browser_skill(), target, registry_with("books.read_invoices"), now=NOW)


def test_an_api_tool_that_is_only_planned_does_not_refuse_the_browser_route() -> None:
    """A declared name nothing registers is an intention, and refusing on it blocks the only
    working route to a system.

    Delete this and writing down a future connector name breaks the present one.
    """
    target = books(api_tools=("books.read_invoices",))

    assert may_load(browser_skill(), target, registry_with(), now=NOW)
    assert available_api_tools(target, registry_with()) == ()


def test_a_live_exemption_naming_an_approver_admits_the_browser_route() -> None:
    """The way out, and it is signed and dated.

    Delete this and there is no way out, which means the rule is switched off the first time
    somebody genuinely needs the browser for a system whose API cannot do the job.
    """
    target = books(api_tools=("books.read_invoices",))
    exemption = Exemption(
        skill="file-the-return",
        target="books",
        approver="sam",
        expires_at=NOW + timedelta(days=30),
        reason="the API cannot attach the supporting document",
    )

    assert may_load(
        browser_skill(),
        target,
        registry_with("books.read_invoices"),
        (exemption,),
        now=NOW,
    )


def test_an_expired_exemption_does_not_exempt_and_is_reported_as_expired() -> None:
    """An expired permission and an absent one are different conversations, and reporting them
    identically loses the one that has a person attached to it.

    Delete this and an exemption quietly stops working, and the author is told to use an API
    tool by a message that does not mention the approval they thought they had.
    """
    target = books(api_tools=("books.read_invoices",))
    stale = Exemption(
        skill="file-the-return",
        target="books",
        approver="sam",
        expires_at=NOW - timedelta(days=1),
        reason="the API cannot attach the supporting document",
    )

    gaps = load_gaps(
        browser_skill(), target, registry_with("books.read_invoices"), (stale,), now=NOW
    )

    assert not may_load(
        browser_skill(), target, registry_with("books.read_invoices"), (stale,), now=NOW
    )
    assert any("expired at" in one and "sam" in one for one in gaps)


def test_an_exemption_naming_no_approver_is_refused() -> None:
    """An exemption nobody signed is a flag somebody set, and there is nobody to ask when it
    is reviewed.

    Delete this and the way out becomes a boolean, which is the failure the named approver
    exists to prevent.
    """
    with pytest.raises(SkillGateError, match="names no approver"):
        Exemption(
            skill="file-the-return",
            target="books",
            approver="  ",
            expires_at=NOW + timedelta(days=30),
            reason="the API cannot attach the supporting document",
        )


def test_an_exemption_with_a_reason_too_short_to_review_is_refused() -> None:
    """Held to the same minimum a halt's reason is, deliberately, so the two do not drift.

    Delete this and "needed" becomes a reason, and whoever reviews the exemption in three
    months has nothing to go on.
    """
    with pytest.raises(SkillGateError, match="not a reason"):
        Exemption(
            skill="file-the-return",
            target="books",
            approver="sam",
            expires_at=NOW + timedelta(days=30),
            reason="needed",
        )


def test_an_exemption_running_longer_than_the_ceiling_is_reported() -> None:
    """A year is long enough for the person who signed it to have left.

    **The ceiling is pinned against a fixed duration rather than against itself.** Building the
    over-long exemption from `MAX_EXEMPTION` is green for every value the constant could hold,
    and a mutation raising it to ten years passed. A year must be too long; the constant must
    be no longer than a year.

    Delete this and an exemption can be written to expire far enough away that the expiry
    stops being a review and becomes a formality.
    """
    target = books(api_tools=("books.read_invoices",))
    forever = Exemption(
        skill="another-skill",
        target="books",
        approver="sam",
        expires_at=NOW + timedelta(days=365),
        reason="the API cannot attach the supporting document",
    )

    assert timedelta(days=365) >= MAX_EXEMPTION

    gaps = load_gaps(
        browser_skill(), target, registry_with("books.read_invoices"), (forever,), now=NOW
    )

    assert any(f"runs past {MAX_EXEMPTION.days} days" in one for one in gaps)


def test_an_exemption_naming_no_skill_or_no_target_is_refused() -> None:
    """An exemption is matched on both, so an empty either half matches whichever comes first.

    A skill-less exemption exempts whichever skill reads it, and a target-less one permits the
    browser route to every system rather than to the one that was argued about.

    Whitespace as well as empty, which is the validator survivor CLAUDE.md records; both were
    unreachable until this test existed.

    Delete this and an exemption row with a blank cell widens to everything it touches.
    """
    for bad in ("", "   "):
        with pytest.raises(SkillGateError, match="naming no skill"):
            Exemption(
                skill=bad,
                target="books",
                approver="sam",
                expires_at=NOW + timedelta(days=30),
                reason="the API cannot attach the supporting document",
            )

    for bad in ("", "   "):
        with pytest.raises(SkillGateError, match="names no target"):
            Exemption(
                skill="file-the-return",
                target=bad,
                approver="sam",
                expires_at=NOW + timedelta(days=30),
                reason="the API cannot attach the supporting document",
            )
