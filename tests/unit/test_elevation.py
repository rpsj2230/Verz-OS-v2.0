"""The break-glass surface held to what it may show, who may open one, and how one ends.

Five leaves are claimed and each is a decision somebody could remove without a screen looking
wrong. Zero standing entitlement is a property of an employment and never of a role, which is
three cases rather than a paragraph: a partner holds nothing even with grant rows on file, a
Super Admin holding no capability grants holds nothing because nobody granted them anything,
and a Super Admin holding one holds it (M33.7.1.1). A session is opened by somebody who holds
the grant capability in a scope admitting the subject, within a stated window and a closed
reason vocabulary (M33.7.1.2). The entry lands in its own chain rather than in the main ledger,
and the finding that a second chain adds a separate anchor and no immutability is asserted by
the diagnostic rather than left in prose (M33.7.1.3). The recipients are computed from the
standing Super Admins rather than accepted, so notifying only the authoriser cannot be
expressed (M33.7.1.4). And a session ends automatically at its bound and can be ended early by
shortening the window, which cannot lengthen one (M33.7.1.5).

Real `Principal`s, real `BreakGlassSession`s through their own validators, real `AuditChain`s
and a real `AuditRecorder` throughout. The chain test in particular writes through
`brain.audit.record.AuditRecorder` rather than appending by hand, because the claim being made
is about which writer a recorder was built with.

Task ids: M33.7.1.1, M33.7.1.2, M33.7.1.3, M33.7.1.4, M33.7.1.5
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.audit.anchor import Anchor, take_anchor
from brain.audit.ledger import AuditAction, AuditChain
from brain.console.elevation import (
    ALREADY_HOLDS_PROMPT,
    ELEVATION_ACTIONS,
    ELEVATION_CHAIN,
    ELEVATION_CONTROL,
    NAMES_THAT_WOULD_LIST_THE_VOCABULARY,
    ElevationError,
    ElevationLanding,
    Revocation,
    anchor_findings,
    chain_findings,
    client_recipients,
    elevation_gaps,
    elevation_recorder,
    expired_by,
    holds_nothing_standing,
    landing,
    may_authorise,
    record_elevation,
    request_elevation,
    revoke,
)
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.identity.roles import (
    BREAK_GLASS_CHAIN,
    BREAK_GLASS_MAX,
    PARTNER_PROMPT,
    BreakGlassReason,
    BreakGlassSession,
    NoStandingEntitlement,
    Role,
    RoleGrant,
    reach_during,
    standing_entitlement,
)
from brain.ops.halt import MINIMUM_REASON

#: A fixed moment, so an expiry test cannot pass because the machine's clock happened to sit
#: on the convenient side of a boundary. Everything below is built relative to it.
NOW = datetime(2027, 3, 9, 9, 0, tzinfo=UTC)

MAINTENANCE = "maintenance"
FINANCE = "finance"

#: The row the subject of every elevation below sits in.
WHERE = {"department": MAINTENANCE}

#: What a session confers in these tests. One capability, so a reader of a failure can see
#: which grant moved.
INSTALL_CAPABILITY = "admin:connector"


def a_principal(
    principal_id: str = "p_partner",
    *,
    employment: Employment = Employment.PARTNER,
    not_after: datetime | None = None,
) -> Principal:
    """One real principal. A partner by default, because that is the subject of M33.7."""
    bound = not_after
    if employment in {Employment.PARTNER, Employment.CONTRACTOR} and bound is None:
        bound = NOW + timedelta(days=90)
    return Principal(
        id=principal_id,
        kind=PrincipalKind.HUMAN,
        employment=employment,
        display_name="a person",
        not_after=bound,
    )


def holding(
    *capabilities: str,
    principal_id: str = "u_admin",
    department: str = MAINTENANCE,
    planes: tuple[Plane, ...] = (Plane.CONFIGURATION,),
) -> EntitlementSet:
    """A reader holding these capabilities in one department, plus the plane grants named."""
    where = Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),))
    grants = [Grant(capability=Capability(value=one), scope=where) for one in capabilities]
    grants += [Grant(capability=plane_capability(one), scope=where) for one in planes]
    return EntitlementSet(principal_id=principal_id, grants=tuple(grants))


def super_admins(*ids: str) -> tuple[RoleGrant, ...]:
    """Standing Super Admin grants, through `RoleGrant`'s own validators."""
    return tuple(
        RoleGrant(
            principal_id=one,
            role=Role.SUPER_ADMIN,
            granted_by="u_first",
            reason="written for this test",
            granted_at=NOW - timedelta(days=200),
        )
        for one in ids
    )


def a_session(
    *,
    principal_id: str = "p_partner",
    opened_at: datetime = NOW,
    duration: timedelta = timedelta(hours=1),
    authorised_by: str = "u_admin",
    notified: tuple[str, ...] = ("u_other",),
) -> BreakGlassSession:
    """One real session through its own validators."""
    return BreakGlassSession(
        session_id="bg_1",
        principal_id=principal_id,
        reason=BreakGlassReason.INSTALL,
        opened_at=opened_at,
        expires_at=opened_at + duration,
        grants=(
            Grant(capability=Capability(value=INSTALL_CAPABILITY), scope=Scope.unrestricted()),
        ),
        authorised_by=authorised_by,
        notified=notified,
    )


# --------------------------------------------------------- zero standing entitlement
def test_a_partner_holds_nothing_standing_even_with_grant_rows_on_file() -> None:
    """**M33.7.1.1, and the case that makes the claim mean something.** A partner who was
    once staff, or whose rows a migration wrote, must still reach nothing: the safe behaviour
    is to hold nothing whatever the grant table says, and a check written as
    `not entitlement.grants` would answer the same for an empty set and go on answering it
    the day somebody adds a default grant.

    Asserted on the type `standing_entitlement` returns rather than on a count, which is that
    module's own distinction between holding nothing and holding an empty set.

    Delete this and the partner path passes with a check that reads the number of rows, which
    is the one property that can be true by accident."""
    partner = a_principal(employment=Employment.PARTNER)
    rows = (Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),)

    assert holds_nothing_standing(partner, rows)
    assert isinstance(standing_entitlement(partner, rows), NoStandingEntitlement)


def test_a_super_admin_holds_exactly_the_grants_somebody_wrote_for_them() -> None:
    """**M33.7.1.1, and the finding.** The Super Admin role confers no capability and
    withholds none: a staff principal with a Super Admin role grant and no capability rows
    reaches nothing, and the same principal with one capability row reaches that one. Neither
    fact is about the role, which is why the role grant is built and then never passed to
    anything that decides.

    Both halves are needed. The first alone would pass for a system that zeroed a Super
    Admin, which is what M33.7.1.1 would ask for if it were about them; the second alone
    would pass for one that granted them everything.

    Delete this and the answer to whether an administrator holds standing entitlement is a
    paragraph again."""
    admin = a_principal("u_admin", employment=Employment.STAFF)
    role_grant = super_admins("u_admin")[0]
    assert role_grant.role is Role.SUPER_ADMIN

    with_nothing = standing_entitlement(admin, ())
    with_one = standing_entitlement(
        admin,
        (Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),),
    )

    assert not isinstance(with_nothing, NoStandingEntitlement)
    assert with_nothing.grants == ()
    assert not isinstance(with_one, NoStandingEntitlement)
    assert with_one.holds(Capability(value="read:client.name"), NOW)
    assert not holds_nothing_standing(admin, ())


def test_the_landing_says_which_of_the_two_and_names_no_capability() -> None:
    """**M33.7.1.1.** Two sentences and no third, and neither contains a capability string.
    A partner reads `PARTNER_PROMPT`, which is imported rather than restated so the words a
    partner reads are written once; anybody with grants of their own reads that a session
    replaces what they hold, which is `reach_during`'s behaviour rather than a reassurance.

    Delete this and the landing acquires a third sentence explaining what could be granted,
    which is the vocabulary."""
    partner = landing(a_principal(employment=Employment.PARTNER))
    staff = landing(
        a_principal("u_admin", employment=Employment.STAFF),
        grants=(
            Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),
        ),
    )

    assert partner.prompt == PARTNER_PROMPT
    assert partner.holds_nothing_standing
    assert staff.prompt == ALREADY_HOLDS_PROMPT
    assert not staff.holds_nothing_standing
    assert ":" not in partner.prompt.replace("access.", "access")
    assert set(ElevationLanding.__dataclass_fields__) == {
        "principal_id",
        "prompt",
        "holds_nothing_standing",
    }


def test_a_field_listing_what_could_be_granted_is_reported_by_the_diagnostic() -> None:
    """**M33.7.1.1.** The check is on the shape of the type rather than on a rule somebody
    remembers, because the field that breaks this is added by whoever is making the screen
    more useful. Run against a constructed row, so the refusal is exercised rather than
    asserted to be unreachable.

    Delete this and `ElevationLanding.available` arrives with a plausible default."""
    from dataclasses import make_dataclass

    leaky = make_dataclass("Leaky", [("principal_id", str), ("available", tuple)])
    counted = make_dataclass("Counted", [("principal_id", str), ("hidden", int)])

    assert elevation_gaps() == ()
    assert any("available" in one for one in elevation_gaps(landing_row=leaky))
    assert any("Counted.hidden" in one for one in elevation_gaps(rows=(counted,)))
    assert "available" in NAMES_THAT_WOULD_LIST_THE_VOCABULARY


# ----------------------------------------------------- time-boxed, with a stated reason
def test_the_authority_to_elevate_is_the_access_review_screens_own_capability() -> None:
    """**M33.7.1.2.** Pinned against the screen rather than derived from it: derived, this
    would compare a constant with itself and repointing either would move both, which is the
    mutation `brain.ops.mutation` was written to catch and CLAUDE.md records twice.

    Delete this and `ELEVATION_CONTROL` can become `admin:elevate`, which is a capability
    entering the system from the console layer where no grant reviewer would meet it."""
    assert screen("access_review").read.requires == ELEVATION_CONTROL
    assert Capability(value="approve:grant") == ELEVATION_CONTROL
    assert elevation_gaps(control=Capability(value="admin:elevate")) != ()


def test_an_elevation_is_opened_only_by_somebody_holding_the_grant_in_the_right_scope() -> None:
    """**M33.7.1.2.** Three readers and one row. Somebody holding the capability in the
    subject's department opens the session; somebody holding it in another department does
    not, because the scope is matched against the row the subject sits in and not merely
    checked for existence; somebody holding no capability at all does not.

    The positive case is the point of the first assertion: a guard tested only by refusals is
    satisfied by a function that refuses everything.

    Delete this and `may_authorise` can drop the `matches` call and pass every refusal
    test."""
    partner = a_principal()
    admins = super_admins("u_admin", "u_other", "u_third")

    session, notice = request_elevation(
        session_id="bg_1",
        principal=partner,
        reason=BreakGlassReason.INSTALL,
        grants=(
            Grant(capability=Capability(value=INSTALL_CAPABILITY), scope=Scope.unrestricted()),
        ),
        authoriser=holding("approve:grant"),
        role_grants=admins,
        where=WHERE,
        now=NOW,
        duration=timedelta(hours=2),
    )

    assert session.principal_id == partner.id
    assert session.expires_at == NOW + timedelta(hours=2)
    assert session.reason is BreakGlassReason.INSTALL
    assert notice.expires_at == session.expires_at

    assert not may_authorise(holding("approve:grant", department=FINANCE), WHERE, NOW)
    assert not may_authorise(holding("read:grant"), WHERE, NOW)
    with pytest.raises(ElevationError, match="may not open"):
        request_elevation(
            session_id="bg_2",
            principal=partner,
            reason=BreakGlassReason.INSTALL,
            grants=(Grant(capability=Capability(value=INSTALL_CAPABILITY), scope=Scope()),),
            authoriser=holding("approve:grant", department=FINANCE),
            role_grants=admins,
            where=WHERE,
            now=NOW,
        )


def test_the_window_is_bounded_by_the_ceiling_the_identity_layer_owns() -> None:
    """**M33.7.1.2.** The console asks for a window and does not re-check the ceiling, so
    there is one place a maximum could be raised. Asserted by asking for one minute more than
    `BREAK_GLASS_MAX` and reading the refusal, and by the default landing exactly on it.

    Anchored to `BREAK_GLASS_MAX` rather than to four hours written here, so changing the
    ceiling changes this test's expectation with it rather than leaving a number behind.

    Delete this and a second bound arrives in `request_elevation`, and the ceiling becomes
    something two modules have an opinion about."""
    partner = a_principal()
    args = {
        "principal": partner,
        "reason": BreakGlassReason.INCIDENT_RESPONSE,
        "grants": (Grant(capability=Capability(value=INSTALL_CAPABILITY), scope=Scope()),),
        "authoriser": holding("approve:grant"),
        "role_grants": super_admins("u_admin", "u_other"),
        "where": WHERE,
        "now": NOW,
    }

    default, _ = request_elevation(session_id="bg_1", **args)  # type: ignore[arg-type]
    assert default.expires_at - default.opened_at == BREAK_GLASS_MAX

    with pytest.raises(Exception, match="at most"):
        request_elevation(
            session_id="bg_2",
            duration=BREAK_GLASS_MAX + timedelta(minutes=1),
            **args,  # type: ignore[arg-type]
        )


# ------------------------------------------------------------ client notification
def test_the_recipients_are_the_standing_super_admins_and_never_the_two_who_already_know() -> None:
    """**M33.7.1.4.** The subject knows, because they asked; the authoriser knows, because
    they decided. A notice reaching only those two passes every test asserting a notice was
    produced and tells nobody anything, which is `brain.console.reads`' argument about a
    steward notice one surface over.

    A deputy is checked separately and is not a recipient: `standing_super_admins` excludes
    one, so a notice whose reader is a thirty-day appointment cannot be produced here.

    Delete this and `notify=[authorised_by]` becomes expressible again."""
    admins = super_admins("u_admin", "u_other", "p_partner")
    deputy = RoleGrant(
        principal_id="u_deputy",
        role=Role.SUPER_ADMIN,
        granted_by="u_admin",
        reason="cover for annual leave",
        granted_at=NOW - timedelta(days=1),
        not_after=NOW + timedelta(days=20),
        deputy_of="u_other",
    )

    assert client_recipients(
        (*admins, deputy), subject_id="p_partner", authorised_by="u_admin", now=NOW
    ) == ("u_other",)


def test_an_elevation_with_nobody_independent_left_to_tell_is_refused() -> None:
    """**M33.7.1.4.** An install whose only standing Super Admin is the authoriser cannot
    produce a notice anybody would read, and the safe answer is that the elevation does not
    happen rather than that it happens quietly.

    Refused here rather than one frame later in `BreakGlassSession`, so the message names the
    install state that produced it. The positive sibling is the test above.

    Delete this and the empty case falls through to a general message about notification and
    nobody learns that the role table is the reason."""
    with pytest.raises(ElevationError, match="nobody to notify"):
        client_recipients(super_admins("u_admin"), subject_id="p_partner", authorised_by="u_admin")

    with pytest.raises(ElevationError, match="nobody to notify"):
        request_elevation(
            session_id="bg_1",
            principal=a_principal(),
            reason=BreakGlassReason.LOCKOUT,
            grants=(Grant(capability=Capability(value=INSTALL_CAPABILITY), scope=Scope()),),
            authoriser=holding("approve:grant"),
            role_grants=super_admins("u_admin"),
            where=WHERE,
            now=NOW,
        )


# ------------------------------------------------------------- the separate chain
def test_an_elevation_entry_lands_in_its_own_chain_and_not_in_the_main_ledger() -> None:
    """**M33.7.1.3, and the whole content of the leaf.** Routing is a choice of writer, so
    the claim worth testing is that a recorder built by `elevation_recorder` appends to the
    elevation chain and leaves the main one untouched, and that the two heads move
    independently.

    Written through a real `AuditRecorder` rather than by appending an entry by hand, because
    a test that built the entry itself would prove nothing about which writer the recorder
    holds.

    Delete this and the separation becomes the string in a details field it was before."""
    main = AuditChain()
    elevation = AuditChain()
    session = a_session()
    before = elevation.head()

    recorder = elevation_recorder(
        elevation,
        session,
        ent_hash="0" * 32,
        trace_id="t_1",
        clock=lambda: NOW,
    )
    entry = record_elevation(recorder, session)

    assert entry.action is AuditAction.BREAK_GLASS
    assert entry.subject == session.audit_subject
    assert entry.actor_id == session.authorised_by
    assert len(elevation) == 1
    assert len(main) == 0
    assert elevation.head() != before
    assert main.head() == AuditChain().head()
    assert chain_findings(main=main, elevation=elevation) == ()


def test_the_actor_on_an_elevation_entry_is_the_authoriser_and_never_the_subject() -> None:
    """**M33.7.1.3.** `brain.console.reads.is_self_grant` reads a self-grant off the entry as
    one whose subject names its own actor. Recording the subject as the actor would make a
    properly authorised elevation indistinguishable from one somebody made for themselves, on
    the detection that must never be defeated.

    Delete this and the actor becomes the person the session is for, which reads more natural
    and is the failure."""
    session = a_session(principal_id="p_partner", authorised_by="u_admin")
    chain = AuditChain()

    entry = record_elevation(
        elevation_recorder(chain, session, ent_hash="0" * 32, trace_id="t_1", clock=lambda: NOW),
        session,
    )

    assert entry.actor_id == "u_admin"
    assert entry.actor_id != session.principal_id
    assert entry.details["principal"] == "p_partner"


def test_the_diagnostic_reports_an_elevation_entry_written_to_the_wrong_chain() -> None:
    """**M33.7.1.3.** The failure this leaf is really about is invisible: the entry exists,
    it verifies, it is anchored, and it sits among a million rows of routine traffic. Both
    directions are checked, because an ordinary entry in the elevation chain is the opposite
    mistake and it matters for the same reason: the value of the second head is that it moves
    only when somebody elevates.

    Run against constructed chains rather than the healthy pair, which is why `chain_findings`
    takes both as arguments.

    Delete this and switching off either check changes nothing any test can see."""
    session = a_session()
    misrouted = AuditChain()
    record_elevation(
        elevation_recorder(
            misrouted, session, ent_hash="0" * 32, trace_id="t_1", clock=lambda: NOW
        ),
        session,
    )
    ordinary = AuditChain()
    ordinary.append(
        action=AuditAction.GRANT,
        actor_id="u_admin",
        subject="principal:u_1",
        ent_hash="0" * 32,
        trace_id="t_1",
        at=NOW,
        details={"capability": "read:client.name"},
    )

    into_main = chain_findings(main=misrouted, elevation=AuditChain())
    into_elevation = chain_findings(main=AuditChain(), elevation=ordinary)

    assert len(into_main) == 1
    assert "main chain" in into_main[0]
    assert len(into_elevation) == 1
    assert ELEVATION_CHAIN in into_elevation[0]
    assert frozenset({AuditAction.BREAK_GLASS}) == ELEVATION_ACTIONS


def test_the_chain_name_is_the_identity_layers_and_is_anchored_separately() -> None:
    """**M33.7.1.3, and the honest half of it.** The name is compared against
    `brain.identity.roles.BREAK_GLASS_CHAIN` rather than imported from it, so repointing
    either fails; and the anchor check is what makes a second chain worth having at all,
    because a chain cannot see its own truncated tail and an anchor is the only thing that
    can.

    A second chain buys that and no additional immutability, which is why the assertion here
    is about the anchor rather than about the entries being harder to edit.

    Delete this and the module can write to a chain nothing anchors, which is the state the
    leaf reads as satisfied."""
    session = a_session()
    chain = AuditChain()
    record_elevation(
        elevation_recorder(chain, session, ent_hash="0" * 32, trace_id="t_1", clock=lambda: NOW),
        session,
    )

    assert ELEVATION_CHAIN == BREAK_GLASS_CHAIN
    assert session.audit_chain == ELEVATION_CHAIN
    assert elevation_gaps(chain="somewhere_else") != ()

    only_main = (take_anchor(AuditChain(), name="main", now=NOW),)
    assert anchor_findings(only_main) != ()
    both: tuple[Anchor, ...] = (*only_main, take_anchor(chain, name=ELEVATION_CHAIN, now=NOW))
    assert anchor_findings(both) == ()


# -------------------------------------------------------------- expiry and revocation
def test_a_session_stops_conferring_anything_at_its_own_bound_with_nobody_acting() -> None:
    """**M33.7.1.5, the automatic half.** Expiry is carried on the entitlement set rather
    than checked by a caller, so an answer computed inside the window cannot be served after
    it. Asserted through `reach_during`, which is the one function that decides what somebody
    may exercise, rather than by reading `expires_at`.

    The partner falls back to `NoStandingEntitlement` afterwards rather than to an empty set,
    which is the property that stops a lapsed session leaving a reach behind it.

    Delete this and expiry becomes a comparison somebody has to remember to make."""
    partner = a_principal()
    session = a_session(duration=timedelta(hours=1))

    inside = reach_during(partner, session, (), NOW + timedelta(minutes=59))
    outside = reach_during(partner, session, (), NOW + timedelta(hours=1))

    assert not isinstance(inside, NoStandingEntitlement)
    assert inside.holds(Capability(value=INSTALL_CAPABILITY), NOW)
    assert inside.not_after == session.expires_at
    assert isinstance(outside, NoStandingEntitlement)
    assert not expired_by(session, NOW + timedelta(minutes=59))
    assert expired_by(session, NOW + timedelta(hours=1))


def test_a_revocation_shortens_the_window_and_the_reach_ends_with_it() -> None:
    """**M33.7.1.5, the revocation half, and the positive case.** Ending a session early had
    nothing before this: `SessionRegistry.end_session` is about a sign-in and `reach_during`
    reads the session's own bound. So revocation moves the bound back and the reach afterwards
    is `reach_during` unchanged, which is what makes this not a second place that knows a
    session can end.

    Delete this and a revoked flag arrives, which is a negative row in a system that has
    none."""
    partner = a_principal()
    session = a_session(duration=timedelta(hours=3))
    at = NOW + timedelta(minutes=20)

    ended = revoke(
        session,
        Revocation(session_id="bg_1", by="u_other", at=at, reason="install finished early"),
    )

    assert ended.expires_at == at
    assert ended.opened_at == session.opened_at
    assert ended.grants == session.grants
    assert not isinstance(
        reach_during(partner, ended, (), at - timedelta(minutes=1)), NoStandingEntitlement
    )
    assert isinstance(reach_during(partner, ended, (), at), NoStandingEntitlement)
    assert isinstance(
        reach_during(partner, ended, (), NOW + timedelta(hours=2)), NoStandingEntitlement
    )


def test_a_revocation_has_nowhere_to_lengthen_a_window() -> None:
    """**M33.7.1.5.** The guard is on both sides and the far side is the one that matters: an
    instant at or after the existing bound would move it forward, which is an extension
    wearing the word revoke, and the function that produced it would be the one an
    administrator reached for to end something.

    The near side and the mismatched id are refused too, and all three are refusals of
    inputs a caller can actually produce.

    Delete this and `revoke` becomes a way of extending a break-glass session past the
    ceiling `BREAK_GLASS_MAX` was written to enforce."""
    session = a_session(duration=timedelta(hours=1))

    def revocation(at: datetime, session_id: str = "bg_1") -> Revocation:
        return Revocation(
            session_id=session_id, by="u_other", at=at, reason="the incident was handled"
        )

    with pytest.raises(ElevationError, match="already ends"):
        revoke(session, revocation(session.expires_at + timedelta(hours=1)))
    with pytest.raises(ElevationError, match="already ends"):
        revoke(session, revocation(session.expires_at))
    with pytest.raises(ElevationError, match="never ran"):
        revoke(session, revocation(session.opened_at))
    with pytest.raises(ElevationError, match="revocation names"):
        revoke(session, revocation(NOW + timedelta(minutes=5), session_id="bg_other"))


def test_a_revocation_carries_a_reason_long_enough_to_be_one() -> None:
    """**M33.7.1.5.** Anchored to `brain.ops.halt.MINIMUM_REASON` rather than to a number
    written here, which is the same situation that module's constant was decided for: whoever
    reads this later is working out whether the incident was handled or the session was closed
    by mistake. Comparing against a literal would be the constant compared with itself.

    Delete this and `reason="x"` is a revocation record."""
    short = "x" * (MINIMUM_REASON - 1)
    long_enough = "y" * MINIMUM_REASON

    with pytest.raises(ElevationError, match="not a reason"):
        Revocation(session_id="bg_1", by="u_other", at=NOW, reason=short)
    with pytest.raises(ElevationError, match="naive"):
        Revocation(
            session_id="bg_1",
            by="u_other",
            at=datetime(2027, 3, 9, 9, 0),
            reason=long_enough,
        )
    assert Revocation(session_id="bg_1", by="u_other", at=NOW, reason=long_enough).by == "u_other"
