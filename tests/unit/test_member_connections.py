"""Connecting an account changes what can be fetched and never what may be seen.

The file is written around one claim (M40.5.1.2) and it is asserted twice, in two different
ways, because either alone is weak. The **property**: the reach before connecting and the
reach after are the same object, hash included, and the connections are handed to the
function that computes it so a body that used them would be caught. The **shape**:
`brain.identity.oidc.assert_no_capability_from_claims`, which refuses a function whose return
type could carry a capability one level into its own fields, is run over `connect`, and the
test drives that check against a function that breaks it so it is not satisfied by one
answering empty.

The rest is per-source consent that is compared rather than filed (M40.5.1.1), a disconnect
that revokes before it removes and refuses when the revocation fails (M40.5.1.3), a
department-provided connection that is listed and not detachable (M40.5.1.4), and the
reachability settings: bindings, a primary, per-channel preferences, an approval route held
to `brain.gate.admission.verbs_for_channel`, and quiet hours that hold a digest and never an
approval (M40.5.2.1 to M40.5.2.4).

Real `Binding`s, real `EntitlementSet`s, a real `Channel`. The revoker is a recording object
behind the protocol, which is what that protocol is for: the case worth testing is the
revocation that fails, and it cannot be reached through anything that opens a connection.

Task ids: M40.5.1.1, M40.5.1.2, M40.5.1.3, M40.5.1.4
Task ids: M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.gate.ingress import Binding
from brain.gate.leash import DEFAULT_APPROVAL_WINDOW, MAX_APPROVAL_WINDOW
from brain.identity.oidc import assert_no_capability_from_claims
from brain.identity.roles import IdentityError
from brain.member.connections import (
    CONNECTING_AN_ACCOUNT_NEVER_WIDENS_WHAT_YOU_MAY_SEE,
    QUIET_HOURS_APPLY_TO,
    ChannelPreference,
    Consent,
    MemberConnectionError,
    NotificationKind,
    PersonalConnection,
    Provenance,
    QuietHours,
    channels_that_may_approve,
    connect,
    connection_gaps,
    disconnect,
    inherited,
    may_deliver,
    personally_connected,
    reach_after_connecting,
    reachability,
    reachable_on,
    wants,
)

#: A fixed moment, so a window test cannot pass because the machine's clock sat on the
#: convenient side of a boundary.
NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)

ME = "u_me"
THEM = "u_them"
DRIVE = "google_drive"
CALENDAR = "google_calendar"


# ------------------------------------------------------------------------- fixtures
class Revoker:
    """A recording revoker behind the protocol, with a switch for the failure path."""

    def __init__(self, *, succeeds: bool = True) -> None:
        self.succeeds = succeeds
        self.asked: list[tuple[str, datetime]] = []

    def revoke(self, token_ref: str, *, at: datetime) -> bool:
        self.asked.append((token_ref, at))
        return self.succeeds


def consent_for(source: str = DRIVE, *, principal_id: str = ME, at: datetime = NOW) -> Consent:
    return Consent(
        principal_id=principal_id,
        source=source,
        granted_at=at,
        wording=CONNECTING_AN_ACCOUNT_NEVER_WIDENS_WHAT_YOU_MAY_SEE,
    )


def connection_for(
    source: str = DRIVE,
    *,
    principal_id: str = ME,
    provenance: Provenance = Provenance.PERSONAL,
) -> PersonalConnection:
    return PersonalConnection(
        principal_id=principal_id,
        source=source,
        provenance=provenance,
        connected_at=NOW,
        token_ref="vault/ref/1",
    )


def entitlement(*values: str, principal_id: str = ME) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted()) for one in values
        ),
    )


def binding_for(channel: Channel, principal_id: str = ME) -> Binding:
    return Binding(
        channel=channel,
        identity_hash=f"{ord(channel.value[0]):064d}",
        principal_id=principal_id,
        bound_at=NOW - timedelta(days=30),
    )


BOTH = (binding_for(Channel.LARK), binding_for(Channel.EMAIL))


@dataclass(frozen=True)
class Widened:
    """A connection type that could confer something, for the check below to refuse.

    At module scope rather than inside the test, because `assert_no_capability_from_claims`
    resolves the annotation with `eval_str=True` against the function's own module globals,
    and a class defined inside a function is not in them.
    """

    granted: tuple[Grant, ...]


def connect_and_grant() -> Widened:
    """What `connect` must never be allowed to become."""
    return Widened(granted=())


# --------------------------------------- M40.5.1.2 connecting widens nothing, two ways
def test_the_reach_after_connecting_is_the_reach_before_it() -> None:
    """**The leaf as a property.** Somebody connects their own account and expects to see
    more; `E_run(caller, agent) = E(caller) intersect agent_ceiling` has no term for a
    connection, so the answer is the same set and the same hash.

    The connections are handed to the function that computes the reach on purpose, so a body
    that consulted them could be caught here rather than by a reviewer noticing.

    Delete this and the copy stays on the screen while the code stops matching it, which is
    the worst version of this leaf: a promise nobody re-reads."""
    caller = entitlement("read:client.name")
    ceiling = entitlement("read:client.name", "read:invoice.amount", principal_id="ag_helper")

    before = reach_after_connecting(caller, ceiling, ())
    after = reach_after_connecting(caller, ceiling, (connection_for(), connection_for(CALENDAR)))

    assert after.ent_hash() == before.ent_hash()
    assert after.grants == before.grants
    assert after.principal_id == ME


def test_a_connection_cannot_add_a_capability_the_caller_does_not_hold() -> None:
    """The direction somebody actually expects to work: the agent's ceiling admits invoices,
    the caller does not hold them, and connecting an accounting source changes nothing.

    Delete this and the test above is satisfied by a ceiling that never mattered."""
    caller = entitlement("read:client.name")
    ceiling = entitlement("read:client.name", "read:invoice.amount", principal_id="ag_helper")

    after = reach_after_connecting(caller, ceiling, (connection_for("xero"),))

    assert after.holds(Capability(value="read:client.name"))
    assert not after.holds(Capability(value="read:invoice.amount"))


def test_connect_cannot_return_anything_capability_shaped() -> None:
    """**The leaf as a shape**, borrowed from the identity package rather than restated. The
    rule there is that a fact asserted from outside this system must never confer a
    capability, written for a directory's group claim; a connected account is the same fact
    from a different outside.

    Delete this and `PersonalConnection` can grow a `granted` field, at which point the
    property test above keeps passing because nothing calls the new field yet."""
    assert connection_gaps() == ()


def test_the_capability_shape_check_is_one_that_can_fail() -> None:
    """The test for the test. `connection_gaps() == ()` over a healthy module proves nothing
    about a check that answers empty for everything, which is the shape CLAUDE.md records as
    the source of almost every surviving mutation here.

    Exercised through the borrowed function directly, because `connection_gaps` reads
    `connect` by name and cannot be handed another.

    Delete this and the borrowed check could be replaced by `pass`."""
    assert_no_capability_from_claims(connect)
    with pytest.raises(IdentityError, match="Grant"):
        assert_no_capability_from_claims(connect_and_grant)


def test_the_copy_says_what_the_property_says() -> None:
    """The leaf asks for explicit copy, and copy that contradicts the code is worse than
    none. The two sentences it must carry are that a connection lets the system fetch, and
    that it changes nothing about what may be seen.

    Delete this and the constant can be softened into marketing that overstates the feature,
    which is exactly the reading the leaf exists to refuse."""
    said = CONNECTING_AN_ACCOUNT_NEVER_WIDENS_WHAT_YOU_MAY_SEE

    assert "on your behalf" in said
    assert "does not change" in said
    assert "grants you nothing" in said


def test_somebody_elses_connection_on_this_page_is_refused() -> None:
    """The one thing `reach_after_connecting` reads the connections for. A page showing a
    colleague's connected account attributes it to the wrong person while correctly
    reporting that it changes nothing, which reads as a feature.

    Delete this and the connections parameter is unread, and a mutation removing it survives."""
    with pytest.raises(MemberConnectionError, match="wrong person"):
        reach_after_connecting(
            entitlement(),
            entitlement(principal_id="ag_helper"),
            (connection_for(principal_id=THEM),),
        )


# ------------------------------------------------------ M40.5.1.1 consent, per source
def test_consent_for_one_source_does_not_connect_another() -> None:
    """**The whole of per-source consent.** A consent record nobody compares is a receipt: it
    proves a screen appeared and stops nothing.

    Delete this and one consent click connects every source the installation offers."""
    with pytest.raises(MemberConnectionError, match="consent was given for"):
        connect(
            principal_id=ME,
            source=CALENDAR,
            token_ref="vault/ref/1",
            consent=consent_for(DRIVE),
            at=NOW,
        )


def test_one_persons_consent_does_not_connect_another_persons_account() -> None:
    """The second comparison. Without it a shared consent row, or a form posting a consent
    id, attaches an account under somebody else's name.

    Delete this and the source check above passes while the principal is unread."""
    with pytest.raises(MemberConnectionError, match="was given by"):
        connect(
            principal_id=ME,
            source=DRIVE,
            token_ref="vault/ref/1",
            consent=consent_for(DRIVE, principal_id=THEM),
            at=NOW,
        )


def test_a_consent_stamped_after_the_connection_is_refused() -> None:
    """Either a clock is wrong or a record is being replayed, and neither reading is safe to
    guess between.

    Delete this and a consent recorded tomorrow authorises a connection made today."""
    with pytest.raises(MemberConnectionError, match="stamped"):
        connect(
            principal_id=ME,
            source=DRIVE,
            token_ref="vault/ref/1",
            consent=consent_for(DRIVE, at=NOW + timedelta(minutes=1)),
            at=NOW,
        )


def test_a_matching_consent_connects_the_account_as_this_persons_own() -> None:
    """The positive half. A guard tested only by its refusals is satisfied by a function that
    refuses everything, and this one is the only way an account is ever attached.

    Delete this and `connect` can be made to raise unconditionally."""
    made = connect(
        principal_id=ME,
        source=DRIVE,
        token_ref="vault/ref/1",
        consent=consent_for(DRIVE),
        at=NOW,
    )

    assert made.principal_id == ME
    assert made.source == DRIVE
    assert made.provenance is Provenance.PERSONAL
    assert made.connected_at == NOW


def test_a_consent_with_no_wording_or_a_blank_principal_is_refused() -> None:
    """A space rather than only an empty string, because a space is what a form posts when
    somebody submits an empty field and `" "` passes a bare falsiness check.

    A consent recording no wording records that a screen appeared and not what it said, which
    is the receipt this type exists not to be.

    Delete this and a consent row proves a click and nothing else."""
    with pytest.raises(ValueError, match="naming nobody"):
        Consent(principal_id=" ", source=DRIVE, granted_at=NOW, wording="Words.")
    with pytest.raises(ValueError, match="no wording"):
        Consent(principal_id=ME, source=DRIVE, granted_at=NOW, wording=" ")
    with pytest.raises(ValueError, match="not a source name"):
        Consent(principal_id=ME, source="Google Drive", granted_at=NOW, wording="Words.")
    with pytest.raises(ValueError, match="timezone-aware"):
        Consent(
            principal_id=ME,
            source=DRIVE,
            granted_at=datetime(2027, 5, 4, 10, 0),
            wording="Words.",
        )


def test_a_connection_with_no_credential_reference_is_refused() -> None:
    """A connection that cannot be revoked would report a successful disconnection and leave
    the credential live, which is the failure the whole ordering below exists to prevent.

    A space as well as an empty string, for the reason above.

    Delete this and a row with a blank reference disconnects cleanly and revokes nothing."""
    with pytest.raises(ValueError, match="no token reference"):
        PersonalConnection(
            principal_id=ME,
            source=DRIVE,
            provenance=Provenance.PERSONAL,
            connected_at=NOW,
            token_ref=" ",
        )
    with pytest.raises(ValueError, match="belonging to nobody"):
        PersonalConnection(
            principal_id=" ",
            source=DRIVE,
            provenance=Provenance.PERSONAL,
            connected_at=NOW,
            token_ref="vault/ref/1",
        )
    with pytest.raises(ValueError, match="not a source name"):
        PersonalConnection(
            principal_id=ME,
            source="Google Drive",
            provenance=Provenance.PERSONAL,
            connected_at=NOW,
            token_ref="vault/ref/1",
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        PersonalConnection(
            principal_id=ME,
            source=DRIVE,
            provenance=Provenance.PERSONAL,
            connected_at=datetime(2027, 5, 4, 10, 0),
            token_ref="vault/ref/1",
        )


# ------------------------------------------------- M40.5.1.3 disconnect revokes first
def test_disconnecting_revokes_the_credential_before_it_reports_success() -> None:
    """The ordering is the leaf. "Immediate" means the revocation is part of the
    disconnection rather than a sweep that runs later.

    Delete this and disconnecting becomes a row removal with a promise attached."""
    revoker = Revoker()

    gone = disconnect(connection_for(), revoker=revoker, at=NOW)

    assert revoker.asked == [("vault/ref/1", NOW)]
    assert gone.source == DRIVE
    assert gone.revoked_at == NOW
    assert gone.principal_id == ME


def test_a_revocation_that_fails_leaves_the_connection_where_it_was() -> None:
    """**The path the obvious ordering gets wrong.** Removing the row first and revoking
    afterwards loses the reference on exactly this branch, so nothing can retry and nothing
    can even say which credential is still live.

    Delete this and a provider outage silently converts a disconnection into an orphaned
    live credential."""
    revoker = Revoker(succeeds=False)

    with pytest.raises(MemberConnectionError, match="could not be revoked"):
        disconnect(connection_for(), revoker=revoker, at=NOW)

    assert revoker.asked == [("vault/ref/1", NOW)]


def test_a_disconnection_carries_no_credential_reference() -> None:
    """The handle was worth keeping until the revocation succeeded and afterwards names
    something that no longer exists, so carrying it forward puts a dead reference into
    whatever the disconnection is rendered or logged into.

    Delete this and the confirmation screen quotes a vault path."""
    named = set(disconnect(connection_for(), revoker=Revoker(), at=NOW).__dict__)

    assert named == {"principal_id", "source", "revoked_at"}


# --------------------------------------- M40.5.1.4 a department connection is inherited
def test_a_department_provided_connection_cannot_be_disconnected_here() -> None:
    """And the refusal happens before the revoker is reached, which matters beyond
    tidiness: revoking a shared credential from one person's page detaches everybody in the
    department, and the refusal that would have followed does not undo it.

    Delete this and one person's tidy-up breaks their colleagues' agents."""
    revoker = Revoker()

    with pytest.raises(MemberConnectionError, match="connected for you by your department"):
        disconnect(
            connection_for(provenance=Provenance.DEPARTMENT),
            revoker=revoker,
            at=NOW,
        )

    assert revoker.asked == []


def test_an_inherited_connection_is_still_listed() -> None:
    """Listed rather than hidden, because a list of what the system can reach on your behalf
    that leaves some of it out is worse than no list at all. The two halves are separate
    functions so one screen shows everything and only the control knows the difference.

    Delete this and the page understates what is connected, which is the disclosure it
    exists to make."""
    rows = (
        connection_for(DRIVE),
        connection_for(CALENDAR, provenance=Provenance.DEPARTMENT),
    )

    assert [one.source for one in inherited(rows)] == [CALENDAR]
    assert [one.source for one in personally_connected(rows)] == [DRIVE]
    assert len(inherited(rows)) + len(personally_connected(rows)) == len(rows)


# ------------------------------------------- M40.5.2.1 and M40.5.2.2 where to reach you
def test_the_channel_list_is_read_off_the_bindings_and_not_off_a_preference() -> None:
    """A preference is what somebody asked for and a binding is what was proved. A list built
    from preferences shows a channel nobody ever finished binding.

    Delete this and the page lists channels that will never deliver."""
    rows = (*BOTH, binding_for(Channel.LARK, THEM))

    assert reachable_on(ME, rows) == (Channel.LARK, Channel.EMAIL)
    assert reachable_on(THEM, rows) == (Channel.LARK,)


def test_a_primary_channel_with_no_binding_is_refused() -> None:
    """Being primarily reachable somewhere nobody proved you are is a default that fails on
    the first message and looks correct on the settings page forever.

    Delete this and a saved preference silently sends everything nowhere."""
    with pytest.raises(MemberConnectionError, match="primary channel"):
        reachability(principal_id=ME, bindings=BOTH, primary=Channel.WHATSAPP)


def test_a_notification_preference_for_an_unbound_channel_is_refused() -> None:
    """Once saved it is indistinguishable from a person nobody is writing to.

    Delete this and somebody switches notifications on for a channel they never bound and
    concludes the system is ignoring them."""
    with pytest.raises(MemberConnectionError, match="no binding on it"):
        reachability(
            principal_id=ME,
            bindings=BOTH,
            primary=Channel.LARK,
            preferences=(ChannelPreference(channel=Channel.WHATSAPP),),
        )


def test_two_preferences_for_one_channel_are_refused() -> None:
    """One of them is dead and which one depends on the order something iterates in, so the
    settings page and the delivery path can disagree with nothing failing.

    Delete this and the answer to "does she want digests on Lark" depends on a dict order."""
    with pytest.raises(MemberConnectionError, match="two notification preferences"):
        reachability(
            principal_id=ME,
            bindings=BOTH,
            primary=Channel.LARK,
            preferences=(
                ChannelPreference(channel=Channel.LARK, notify=frozenset()),
                ChannelPreference(
                    channel=Channel.LARK, notify=frozenset({NotificationKind.DIGEST})
                ),
            ),
        )


def test_reachability_with_no_principal_is_refused() -> None:
    """A space as well as an empty string. A preference row for nobody matches every person
    or none, depending on how it is later joined.

    Delete this and a blank form field saves a settings row nothing can attribute."""
    with pytest.raises(ValueError, match="reachability for nobody"):
        reachability(principal_id=" ", bindings=BOTH, primary=Channel.LARK)


def test_a_channel_with_no_preference_row_wants_nothing() -> None:
    """The quiet default, which is the one that cannot surprise somebody. The loud default
    would be to read an absent row as "send everything", and the first person to discover
    that discovers it from their phone.

    Delete this and adding a channel starts a stream of notifications nobody asked for."""
    settings = reachability(
        principal_id=ME,
        bindings=BOTH,
        primary=Channel.LARK,
        preferences=(
            ChannelPreference(channel=Channel.LARK, notify=frozenset({NotificationKind.DIGEST})),
        ),
    )

    assert wants(settings, Channel.LARK, NotificationKind.DIGEST)
    assert not wants(settings, Channel.LARK, NotificationKind.AUTOMATION)
    assert not wants(settings, Channel.EMAIL, NotificationKind.DIGEST)


# ------------------------------------------------------- M40.5.2.3 the approval route
def test_an_approval_cannot_be_routed_to_a_channel_that_may_not_approve() -> None:
    """**The check that would otherwise be discovered by somebody missing an approval.**
    `brain.gate.admission` refuses an approve on email, and an envelope routed there is a
    notification the person can read and cannot act on.

    Asked of `verbs_for_channel` rather than of a list here, so a channel whose ceiling
    changes changes this in the same moment.

    Delete this and the routing page offers every channel somebody is bound on."""
    with pytest.raises(MemberConnectionError, match="may not carry an approve"):
        reachability(
            principal_id=ME,
            bindings=BOTH,
            primary=Channel.LARK,
            approval_route=Channel.EMAIL,
        )


def test_an_approval_route_defaults_to_the_primary_and_is_still_checked() -> None:
    """The default is the person's own primary rather than a channel named in this module,
    because a default naming one would be a routing decision made here for everybody. It is
    then held to the same check, which is how somebody whose primary cannot approve finds
    out when they set it rather than when they miss an envelope.

    Delete this and the default route escapes the check the explicit one is held to."""
    settings = reachability(principal_id=ME, bindings=BOTH, primary=Channel.LARK)
    assert settings.approval_route is Channel.LARK

    with pytest.raises(MemberConnectionError, match="may not carry an approve"):
        reachability(
            principal_id=ME,
            bindings=(binding_for(Channel.EMAIL),),
            primary=Channel.EMAIL,
        )


def test_an_approval_route_with_no_binding_is_refused() -> None:
    """A route nobody is bound on means every envelope expires unanswered, which is the
    stated default doing exactly what it says and nobody wanting it.

    Delete this and the console offers a route that silently lapses everything."""
    with pytest.raises(MemberConnectionError, match="no binding on it"):
        reachability(
            principal_id=ME,
            bindings=(binding_for(Channel.EMAIL),),
            primary=Channel.EMAIL,
            approval_route=Channel.LARK,
        )


def test_only_the_two_channels_the_gate_trusts_may_carry_an_approval() -> None:
    """Read out of `verbs_for_channel` over the whole enumeration rather than asserted as a
    list, so a channel added to the system appears here without anybody editing this file.

    The pair is worth naming: the console and the tenant identity provider's own chat client,
    which is exactly what M40.6.1.4 means by "from Lark and from the web".

    Delete this and a widening of a channel ceiling passes unnoticed."""
    may = channels_that_may_approve(Channel)

    assert set(may) == {Channel.CONSOLE, Channel.LARK}


# ------------------------------------------------------------- M40.5.2.4 quiet hours
def test_a_night_time_quiet_window_covers_both_sides_of_midnight() -> None:
    """The arithmetic that is wrong in every naive implementation. Ten at night to seven is
    the union of two intervals, and `start <= t < end` is quiet for precisely the hours
    nobody asked for.

    Delete this and quiet hours are loud all night and silent all day."""
    quiet = QuietHours(start=time(22, 0), end=time(7, 0))

    assert quiet.wraps_midnight()
    assert quiet.contains(NOW.replace(hour=23, minute=30))
    assert quiet.contains(NOW.replace(hour=2, minute=0))
    assert not quiet.contains(NOW.replace(hour=12, minute=0))


def test_a_daytime_quiet_window_is_the_ordinary_interval() -> None:
    """The other arm, without which the wrap test above is satisfied by an implementation
    that always wraps.

    Delete this and somebody asking for quiet through the working day gets the opposite."""
    quiet = QuietHours(start=time(9, 0), end=time(17, 0))

    assert not quiet.wraps_midnight()
    assert quiet.contains(NOW.replace(hour=12, minute=0))
    assert not quiet.contains(NOW.replace(hour=20, minute=0))


def test_the_start_of_a_quiet_window_is_inside_it_and_the_end_is_not() -> None:
    """Stated so the boundary cannot drift. A window ending at seven delivers at seven,
    which is what somebody means when they set it.

    **Both windows, and a mutation is why.** `contains` has two arms and only the wrapping
    one was exercised at its boundary, so changing `<=` to `<` in the daytime arm survived:
    the assertions all ran through the other branch. A boundary test on a two-armed function
    has to touch both arms or it is a boundary test on one of them.

    Delete this and a deferral lands one window later, on a day nobody can reproduce."""
    overnight = QuietHours(start=time(22, 0), end=time(7, 0))
    daytime = QuietHours(start=time(9, 0), end=time(17, 0))

    assert overnight.contains(NOW.replace(hour=22, minute=0))
    assert not overnight.contains(NOW.replace(hour=7, minute=0))
    assert daytime.contains(NOW.replace(hour=9, minute=0))
    assert not daytime.contains(NOW.replace(hour=17, minute=0))


def test_a_digest_inside_quiet_hours_waits_until_the_window_ends() -> None:
    """Across midnight, which is the case a same-day calculation gets wrong by twenty-four
    hours in the direction nobody notices until the next morning.

    Delete this and a digest held at half past eleven arrives that same morning at seven,
    or a day late, depending on which side of midnight it was."""
    quiet = QuietHours(start=time(22, 0), end=time(7, 0))

    late = NOW.replace(hour=23, minute=30)
    early = NOW.replace(hour=2, minute=0)

    assert quiet.deferred_until(late) == NOW.replace(hour=7, minute=0) + timedelta(days=1)
    assert quiet.deferred_until(early) == NOW.replace(hour=7, minute=0)


def test_a_moment_outside_quiet_hours_is_not_deferred_at_all() -> None:
    """So a caller can apply the deferral unconditionally rather than asking twice and
    getting a different answer on the boundary.

    Delete this and every delivery is pushed to the end of a window it was never in."""
    quiet = QuietHours(start=time(22, 0), end=time(7, 0))
    noon = NOW.replace(hour=12, minute=0)

    assert quiet.deferred_until(noon) == noon


def test_quiet_hours_hold_a_digest_and_an_automation_and_never_an_approval() -> None:
    """**The leaf and the exception in one assertion.** The two kinds the leaf names wait;
    the third does not, because an envelope's default window is four hours and an eight-hour
    night outlives it, so holding one would turn a courtesy into a silent refusal.

    The window is compared against `brain.gate.leash`'s own constants rather than against a
    number written here, which is what makes the argument checkable rather than asserted.

    Delete this and an approval raised at eleven at night lapses before anybody is told."""
    quiet = QuietHours(start=time(22, 0), end=time(7, 0))
    night = NOW.replace(hour=23, minute=30)

    assert not may_deliver(NotificationKind.DIGEST, quiet, night)
    assert not may_deliver(NotificationKind.AUTOMATION, quiet, night)
    assert may_deliver(NotificationKind.APPROVAL, quiet, night)

    assert {NotificationKind.DIGEST, NotificationKind.AUTOMATION} == QUIET_HOURS_APPLY_TO
    assert timedelta(hours=8) > DEFAULT_APPROVAL_WINDOW
    assert timedelta(hours=24) >= MAX_APPROVAL_WINDOW


def test_everything_is_deliverable_when_no_quiet_hours_are_set() -> None:
    """The positive half. A rule tested only by what it suppresses is satisfied by an
    implementation that suppresses everything.

    Delete this and quiet hours can default to always on."""
    for kind in NotificationKind:
        assert may_deliver(kind, None, NOW.replace(hour=23, minute=30))


def test_a_quiet_window_whose_ends_are_equal_is_refused() -> None:
    """It reads as both "no quiet hours" and "quiet all day", and a setting with two readings
    is one somebody will read the wrong way.

    Delete this and a slider dragged to the same value on both ends saves as silence."""
    with pytest.raises(ValueError, match="either nothing or the"):
        QuietHours(start=time(22, 0), end=time(22, 0))


def test_a_quiet_window_carrying_seconds_or_a_timezone_is_refused() -> None:
    """Seconds would make a deferral land at a time nobody chose, and a timezone on the
    window would be a second answer to a question the caller has already answered by handing
    in a datetime in the person's own zone.

    Delete this and the two ways of saying where the person is can disagree."""
    with pytest.raises(ValueError, match="set to the minute"):
        QuietHours(start=time(22, 0, 30), end=time(7, 0))
    with pytest.raises(ValueError, match="carries a timezone"):
        QuietHours(start=time(22, 0, tzinfo=UTC), end=time(7, 0))


def test_quiet_hours_refuse_a_naive_datetime() -> None:
    """The repository's rule everywhere else, and here it is what makes the conversion to the
    person's own zone visible at the call site rather than assumed inside this module.

    Delete this and a naive timestamp is compared against a local window and is quiet or loud
    by whatever the server's clock happens to be set to."""
    quiet = QuietHours(start=time(22, 0), end=time(7, 0))

    with pytest.raises(ValueError, match="aware datetime"):
        quiet.contains(datetime(2027, 5, 4, 23, 30))


# -------------------------------------------------------------------- the diagnostic
def test_connection_gaps_reports_a_settings_row_that_no_builder_checked() -> None:
    """A `Reachability` loaded from a table has been through no builder, which is the only
    state this half of the diagnostic has anything to say about.

    Constructed directly rather than through `reachability`, because the builder refuses
    exactly what is being tested, and a diagnostic that can only see healthy inputs is a
    decoration.

    Delete this and switching off either check changes nothing observable."""
    from brain.member.connections import Reachability

    stale = Reachability(
        principal_id=ME,
        primary=Channel.LARK,
        preferences=(
            ChannelPreference(channel=Channel.LARK),
            ChannelPreference(channel=Channel.LARK, notify=frozenset({NotificationKind.DIGEST})),
        ),
        approval_route=Channel.EMAIL,
    )

    found = connection_gaps(stale)

    assert any("may not carry an approve" in one for one in found)
    assert any("two notification preferences" in one for one in found)


def test_a_settings_row_the_builder_produced_has_no_gaps() -> None:
    """The positive half, without which the diagnostic above is satisfied by one that
    reports everything.

    Delete this and `connection_gaps` can be made to complain about correct settings, and
    the deployment check becomes noise somebody switches off."""
    settings = reachability(
        principal_id=ME,
        bindings=BOTH,
        primary=Channel.LARK,
        preferences=(
            ChannelPreference(channel=Channel.EMAIL, notify=frozenset({NotificationKind.DIGEST})),
        ),
        quiet=QuietHours(start=time(22, 0), end=time(7, 0)),
    )

    assert connection_gaps(settings) == ()
    assert settings.approval_route is Channel.LARK
    assert settings.quiet is not None
