"""What a member is attached to: the accounts they connect and the channels they answer on.

Two halves that look unrelated and are the same question asked twice. What has this person
attached to themselves, and what does attaching it change.

**Connecting an account never widens what somebody may see, and the whole design is arranged
so that it cannot.** This is the sentence M40.5.1.2 asks for in words, and words are the
weakest half of it. Somebody connects their own Google account and reasonably expects to see
more afterwards; the entitlement rule has no term for a connection at all. `E_run(caller,
agent) = E(caller) intersect agent_ceiling` is computed from grants and a ceiling, and a
personal connection is neither, so what a connection changes is what the system can **fetch
on their behalf** and never what they are entitled to. `reach_after_connecting` is that
stated as a function whose answer is independent of the connections handed to it, and
`connection_gaps` is the structural half: it runs `brain.identity.oidc.
assert_no_capability_from_claims` over `connect`, which refuses a function that could return
anything capability-shaped, one level into its own fields.

**That check is reused rather than restated, and the reuse is the point.** The rule it
encodes is "a fact asserted from outside this system must never confer a capability", written
for an identity provider's group claim. A connected account is the same fact from a different
outside, and a second copy of the check would be a second place for the list of
capability-shaped names to fall behind.

**Consent is per source and is compared, not recorded.** A consent naming one source does not
build a connection to another. That is the only interesting thing about consent as a data
structure: a record that is written and never read is a receipt, and a receipt is what a
consent screen produces when nobody wires the comparison.

**Disconnecting revokes before it removes, and refuses if the revocation fails.** The obvious
order is to drop the row and then call the provider, which reads better and loses the token
reference on the failure path: the record naming what to revoke is gone, so nothing can try
again, and the token stays live with nobody able to find it. So the revocation happens first
and a false answer leaves the connection in place, still listed, still disconnectable. See
`A_RECORD_DROPPED_BEFORE_THE_CREDENTIAL_IS_REVOKED_LEAVES_IT_LIVE_AND_UNFINDABLE`.

**A department-provided connection is shown and refused here.** Not hidden: hiding it would
make the person's own list disagree with what the system can reach on their behalf, which is
the disclosure a connections screen exists to make. Refused because the person did not attach
it and cannot answer for it, and the refusal names what to do rather than who did it.

**An approval routed to a channel that cannot approve is a notification nobody can act on.**
`brain.gate.admission.CHANNEL_VERBS` already decides which channels may carry an `approve`,
and it says no to WhatsApp, email, Slack, Telegram, Teams and the widget for reasons each
records. A routing preference is therefore checked against `verbs_for_channel` rather than
against a list written here, so a channel whose ceiling changes changes this at the same
moment. That is the one check in this module that would otherwise be discovered by somebody
missing an approval.

**Quiet hours cover digests and automations and deliberately not approvals.** The leaf names
the two, and the third is why the list is closed rather than an oversight:
`brain.gate.leash.DEFAULT_APPROVAL_WINDOW` is four hours, so an envelope raised at eleven at
night and held until seven has expired before the person is told it existed. Holding it would
turn a courtesy into a silent refusal, which is the worst shape a default can take. See
`AN_APPROVAL_HELD_UNTIL_MORNING_HAS_EXPIRED_BY_MORNING`.

**Rejected: a timezone on `QuietHours`.** Quiet hours are local by definition and this type
has no way to validate a zone name against anything, so a field for one would be a string
that looks checked. The datetime handed to `contains` is already in the person's own zone and
must be timezone-aware, which is the repository's rule everywhere else and is what makes the
requirement visible at the call site rather than assumed inside this file.

**Rejected: a preference for a channel the person is not bound on.** It reads harmless and it
is the shape that produces a person with notifications switched on for a channel that will
never deliver one, which is indistinguishable from a person who is being ignored. Every
channel named in a preference, in the primary and in the approval route is checked against
the bindings handed in.

Scope: domain logic. Nothing here opens a connection, revokes a token or reads a clock; the
revoker is a protocol and `at` is a parameter.

Task ids: M40.5.1.1, M40.5.1.2, M40.5.1.3, M40.5.1.4
Task ids: M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Final, Protocol

from brain.console.reads import audience
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import OBJECT_NAME_PATTERN
from brain.gate.admission import verbs_for_channel
from brain.gate.context import Channel
from brain.gate.ingress import Binding
from brain.identity.oidc import assert_no_capability_from_claims
from brain.identity.roles import IdentityError

# ------------------------------------------------------------------ written-down reasons
#: The copy M40.5.1.2 asks for, shown wherever an account can be connected.
#:
#: A constant rather than a string in a template, because the property it states is tested:
#: `reach_after_connecting` returns the caller's reach whatever connections it is handed, and
#: `connection_gaps` refuses a `connect` that could return anything capability-shaped. Copy
#: nobody can falsify is copy worth showing.
CONNECTING_AN_ACCOUNT_NEVER_WIDENS_WHAT_YOU_MAY_SEE: Final = (
    "Connecting an account lets the Brain fetch from it on your behalf. It does not change "
    "what you are allowed to see. Everything you can reach here comes from the access "
    "somebody granted you in this system, and connecting an account grants you nothing. If "
    "an answer leaves something out, connecting more accounts will not bring it back."
)

#: Why the revocation happens before the record is removed.
A_RECORD_DROPPED_BEFORE_THE_CREDENTIAL_IS_REVOKED_LEAVES_IT_LIVE_AND_UNFINDABLE: Final = (
    "Removing the connection first and revoking afterwards reads better and is wrong on the "
    "one path that matters. If the revocation fails, the record naming what to revoke has "
    "already gone, so nothing can retry and nothing can even report which token is still "
    "live. The revocation is therefore first, and a false answer leaves the connection in "
    "place: still listed, still attributed, still disconnectable by the person who owns it."
)

#: Why a department-provided connection is listed and not detachable.
AN_INHERITED_CONNECTION_IS_SOMEBODY_ELSES_DECISION_AND_STILL_THIS_PERSONS_BUSINESS: Final = (
    "A connection a department made on this person's behalf is shown, because a list of "
    "what the system can reach on your behalf that leaves some of it out is worse than no "
    "list. It is not disconnectable here, because the person did not attach it, cannot "
    "answer for what depends on it, and detaching it would silently change what their "
    "colleagues get. The refusal says where to go and never who set it up."
)

#: Why a routing preference is checked against the channel's verbs.
AN_APPROVAL_SENT_WHERE_APPROVE_IS_REFUSED_IS_A_MESSAGE_NOBODY_CAN_ANSWER: Final = (
    "brain.gate.admission decides which channels may carry an approve at all, and it says "
    "no to most of them: a message is not a signature, an email is spoofable and "
    "asynchronous, a button in a Slack channel is pressable by the channel. Routing an "
    "envelope to one of those produces a notification the person can read and cannot act "
    "on, and they find out by missing a deadline. The preference is checked against "
    "verbs_for_channel rather than a list here, so a channel's ceiling and this agree."
)

#: Why quiet hours stop short of an approval.
AN_APPROVAL_HELD_UNTIL_MORNING_HAS_EXPIRED_BY_MORNING: Final = (
    "brain.gate.leash raises an envelope with a four-hour window by default and twenty-four "
    "hours is its maximum, so an approval held from eleven at night until seven has lapsed "
    "before the person is told it existed. Quiet hours would then be a silent refusal "
    "wearing the shape of a courtesy, which is the worst thing a default can be. Digests "
    "and automations wait, because nothing expires while they do."
)

#: Why consent is compared rather than filed.
A_CONSENT_NOBODY_COMPARES_IS_A_RECEIPT: Final = (
    "Per-source consent means the consent for one source does not build a connection to "
    "another, and the only way that is true is if something compares the two. A consent "
    "record written at the moment somebody clicks and never read again is a receipt: it "
    "proves a screen was shown and stops nothing. connect compares the source and the "
    "principal, and refuses rather than recording a mismatch for somebody to find later."
)


class MemberConnectionError(Exception):
    """A member surface was asked to attach or detach something it may not.

    Outside `brain.core.errors` for `brain.console.own_things.OwnThingsError`'s reason: those
    five outcomes describe an answer given to somebody who asked a question, and this is a
    refusal to operate a control on a personal screen.

    Not called `ConnectionError`, which is a builtin and would shadow it for every caller in
    this package including the ones catching a genuine network failure.
    """


#: The grammar a source name follows, which is the one `brain.core.envelope` already sets for
#: the object a tool acts on. Reused rather than written again: a second pattern is a second
#: place for `Google Drive` to be accepted here and refused where it is looked up.
_SOURCE_RE: Final = re.compile(OBJECT_NAME_PATTERN)


class Provenance(enum.StrEnum):
    """Who attached a connection. Two members and there is no third.

    Nothing meaning "pending", "expired" or "revoked". A connection that is not usable is not
    a connection with a flag on it, it is a row that should not be there:
    `brain.channels.binding` records the same decision about a binding, and the reason is
    that a subtractive state has an evaluation order and this system has none.
    """

    #: This person connected it themselves and may disconnect it.
    PERSONAL = "personal"
    #: The department connected it for them. Shown here, detached elsewhere.
    DEPARTMENT = "department"


@dataclass(frozen=True)
class Consent:
    """What somebody agreed to, for one source, at one moment (M40.5.1.1).

    Carries the wording they were shown rather than a version number, following
    `brain.gate.leash.SuspendedAction.artefact`: a consent recorded against a version is a
    consent to whatever that version says today, and the thing a person agreed to is the
    sentence in front of them at the time.
    """

    principal_id: str
    source: str
    granted_at: datetime
    #: The words shown at the moment of consent, kept verbatim.
    wording: str

    def __post_init__(self) -> None:
        if not self.principal_id.strip():
            msg = "a consent naming nobody cannot be compared against anything"
            raise ValueError(msg)
        if not _SOURCE_RE.match(self.source):
            msg = (
                f"consent source {self.source!r} is not a source name, so it will match no "
                "connection and the comparison that makes consent per-source cannot run"
            )
            raise ValueError(msg)
        if not self.wording.strip():
            msg = (
                "a consent recording no wording records that a screen appeared and not what "
                "it said, which is the receipt this type exists not to be"
            )
            raise ValueError(msg)
        if self.granted_at.tzinfo is None:
            msg = "granted_at must be timezone-aware; a naive timestamp is a silent bug"
            raise ValueError(msg)


@dataclass(frozen=True)
class PersonalConnection:
    """One account attached to one person (M40.5.1.1).

    **No field here can hold a capability, a grant or an entitlement set**, and that is the
    structural half of `CONNECTING_AN_ACCOUNT_NEVER_WIDENS_WHAT_YOU_MAY_SEE`:
    `connection_gaps` runs the identity package's own check over `connect`, which walks one
    level into this type's fields looking for exactly that.

    `token_ref` is a handle to wherever the credential lives, never the credential.
    `brain.ops.openbao` holds the vault side; a token in this row would put a live credential
    into every listing, every export and every screenshot of a connections page.
    """

    principal_id: str
    source: str
    provenance: Provenance
    connected_at: datetime
    #: An opaque handle to the stored credential. Never the credential itself.
    token_ref: str

    def __post_init__(self) -> None:
        if not self.principal_id.strip():
            msg = "a connection belonging to nobody appears on everybody's page or on none"
            raise ValueError(msg)
        if not _SOURCE_RE.match(self.source):
            msg = f"connection source {self.source!r} is not a source name"
            raise ValueError(msg)
        if not self.token_ref.strip():
            msg = (
                "a connection with no token reference cannot be revoked, so disconnecting "
                "it would report success and leave the credential live"
            )
            raise ValueError(msg)
        if self.connected_at.tzinfo is None:
            msg = "connected_at must be timezone-aware; a naive timestamp is a silent bug"
            raise ValueError(msg)


def connect(
    *,
    principal_id: str,
    source: str,
    token_ref: str,
    consent: Consent,
    at: datetime,
) -> PersonalConnection:
    """Attach one account to one person, against the consent given for that source (M40.5.1.1).

    Three comparisons and each refuses rather than records. See
    `A_CONSENT_NOBODY_COMPARES_IS_A_RECEIPT`: consent for one source is not consent for
    another, consent given by one person is not consent for another's account, and a consent
    stamped after the moment it is being used at is a clock or a replay and neither is safe
    to guess between.

    Returns a `PersonalConnection` and nothing else. There is no second return value carrying
    what this now reaches, because the answer to that question is unchanged and a function
    that returned it would be the place somebody later made it change.
    """
    if consent.principal_id != principal_id:
        msg = (
            f"this consent was given by {consent.principal_id!r} and the connection is for "
            f"{principal_id!r}. {A_CONSENT_NOBODY_COMPARES_IS_A_RECEIPT}"
        )
        raise MemberConnectionError(msg)
    if consent.source != source:
        msg = (
            f"consent was given for {consent.source!r} and this connects {source!r}. "
            f"{A_CONSENT_NOBODY_COMPARES_IS_A_RECEIPT}"
        )
        raise MemberConnectionError(msg)
    if consent.granted_at > at:
        msg = (
            f"consent is stamped {consent.granted_at.isoformat()} and the connection is "
            f"being made at {at.isoformat()}, so one of the two is wrong and neither reading "
            "is safe to pick"
        )
        raise MemberConnectionError(msg)
    return PersonalConnection(
        principal_id=principal_id,
        source=source,
        provenance=Provenance.PERSONAL,
        connected_at=at,
        token_ref=token_ref,
    )


def reach_after_connecting(
    caller: EntitlementSet,
    agent_ceiling: EntitlementSet,
    connections: Sequence[PersonalConnection],
) -> EntitlementSet:
    """What this person may see once they have connected accounts (M40.5.1.2). The same as before.

    **The answer is `E(caller) intersect agent_ceiling` and the connections are not in it.**
    That is the whole function and it is written as a function rather than as a sentence
    because a sentence cannot be mutated and this can: change the body to widen anything and
    a test says so.

    `brain.console.reads.audience` is the intersection, called rather than performed here.
    There is one implementation of `EntitlementSet.intersect` in this repository, its call
    sites are pinned by an invariant test, and adding one for a member screen would be the
    central rule reimplemented on the surface with the least review on it.

    The connections are read, once, for the one thing that could be wrong about them: a
    connection belonging to somebody else has no business on this person's page, and a screen
    that showed one would be attributing an account to the wrong person while correctly
    reporting that it changes nothing.
    """
    wrong = sorted(
        {one.principal_id for one in connections if one.principal_id != caller.principal_id}
    )
    if wrong:
        msg = (
            f"connections belonging to {wrong} were handed to {caller.principal_id!r}'s own "
            "page, so an account would be attributed to the wrong person"
        )
        raise MemberConnectionError(msg)
    return audience(caller, agent_ceiling)


class TokenRevoker(Protocol):
    """Revokes one stored credential and says whether it is now dead.

    A protocol rather than a call into the vault, for the reason `brain.channels.binding.
    NonceLedger` is one: the policy here is an ordering and a refusal, and a module that
    opened a connection could not be tested at the boundary that matters, which is the
    revocation that fails.

    **Returns a bool rather than raising**, so the failure path is a value the caller has to
    handle rather than an exception it can forget to catch. An implementation that cannot
    reach the provider returns False, which is the honest answer: the token might be live.
    """

    def revoke(self, token_ref: str, *, at: datetime) -> bool: ...


@dataclass(frozen=True)
class Disconnection:
    """A connection removed and its credential revoked, in that order (M40.5.1.3).

    Carries no token reference. The handle was the one thing worth keeping until the
    revocation succeeded, and afterwards it names a credential that no longer exists.
    """

    principal_id: str
    source: str
    revoked_at: datetime


def disconnect(
    connection: PersonalConnection,
    *,
    revoker: TokenRevoker,
    at: datetime,
) -> Disconnection:
    """Disconnect one of this person's own accounts, revoking first (M40.5.1.3, M40.5.1.4).

    Order is the argument; see
    `A_RECORD_DROPPED_BEFORE_THE_CREDENTIAL_IS_REVOKED_LEAVES_IT_LIVE_AND_UNFINDABLE`. A
    revoker answering False leaves the connection exactly as it was, so the page still shows
    it and the control still works, rather than reporting a disconnection that removed a row
    and left a credential.

    A department-provided connection is refused before the revoker is reached, which matters
    beyond tidiness: revoking a shared credential from one person's page would detach
    everybody in the department, and the revocation is not undone by the refusal that would
    have followed it.
    """
    if connection.provenance is Provenance.DEPARTMENT:
        msg = (
            f"{connection.source} was connected for you by your department, so it is managed "
            "there rather than here. Ask your department administrator to remove it. "
            f"{AN_INHERITED_CONNECTION_IS_SOMEBODY_ELSES_DECISION_AND_STILL_THIS_PERSONS_BUSINESS}"
        )
        raise MemberConnectionError(msg)
    if not revoker.revoke(connection.token_ref, at=at):
        msg = (
            f"the credential for {connection.source} could not be revoked, so the connection "
            f"is still here and can be tried again. "
            f"{A_RECORD_DROPPED_BEFORE_THE_CREDENTIAL_IS_REVOKED_LEAVES_IT_LIVE_AND_UNFINDABLE}"
        )
        raise MemberConnectionError(msg)
    return Disconnection(
        principal_id=connection.principal_id,
        source=connection.source,
        revoked_at=at,
    )


def inherited(connections: Iterable[PersonalConnection]) -> tuple[PersonalConnection, ...]:
    """The department-provided connections on this person's page (M40.5.1.4).

    Listed rather than filtered out, and `disconnect` is what refuses them. Splitting the two
    that way means the screen shows everything the system can reach on this person's behalf,
    which is the disclosure the page exists to make, and the control is the only thing that
    knows the difference.

    Order follows `connections`, following `brain.console.screens.offerable`.
    """
    return tuple(one for one in connections if one.provenance is Provenance.DEPARTMENT)


def personally_connected(
    connections: Iterable[PersonalConnection],
) -> tuple[PersonalConnection, ...]:
    """The connections this person attached themselves (M40.5.1.4).

    The other half of `inherited`, written out rather than left to a caller's own comparison:
    two screens filtering the same tuple by hand is two places for the sense of the test to
    be inverted, and the inversion offers a disconnect control on a department's credential.
    """
    return tuple(one for one in connections if one.provenance is Provenance.PERSONAL)


# ------------------------------------------------------------------------ reachability
class NotificationKind(enum.StrEnum):
    """What the system might interrupt somebody with. Three members and the third is a rule.

    `APPROVAL` exists here to be excluded from quiet hours rather than to be configured: see
    `AN_APPROVAL_HELD_UNTIL_MORNING_HAS_EXPIRED_BY_MORNING`. Without it in the enumeration,
    quiet hours would apply to whatever a future caller passes and the exception would be a
    sentence in a docstring.
    """

    #: A periodic summary. Nothing in it expires.
    DIGEST = "digest"
    #: Something an automation finished or could not finish. Nothing in it expires.
    AUTOMATION = "automation"
    #: An envelope waiting on an answer. This one expires, so it is never held.
    APPROVAL = "approval"


#: The kinds quiet hours apply to (M40.5.2.4). The leaf names these two and no others.
QUIET_HOURS_APPLY_TO: Final[frozenset[NotificationKind]] = frozenset(
    {NotificationKind.DIGEST, NotificationKind.AUTOMATION}
)


@dataclass(frozen=True)
class QuietHours:
    """When only an approval may interrupt (M40.5.2.4).

    Two wall-clock times in the person's own zone, and no zone field; see the module
    docstring for why. The datetime handed to `contains` must already be in that zone and
    must be timezone-aware, which makes the conversion visible at the call site.

    Start is inclusive and end is exclusive, so a window ending at seven delivers at seven.
    A window whose two ends are equal is refused, because it reads as both "no quiet hours"
    and "quiet all day" and there is no way to tell which somebody meant.
    """

    start: time
    end: time

    def __post_init__(self) -> None:
        if self.start == self.end:
            msg = (
                f"quiet hours from {self.start} to {self.start} means either nothing or the "
                "whole day, and a setting with two readings is one somebody will read wrong"
            )
            raise ValueError(msg)
        for named, value in (("start", self.start), ("end", self.end)):
            if value.second or value.microsecond:
                msg = (
                    f"quiet hours {named} is {value}, and quiet hours are set to the minute; "
                    "seconds here would make a deferral land at a time nobody chose"
                )
                raise ValueError(msg)
            if value.tzinfo is not None:
                msg = (
                    f"quiet hours {named} carries a timezone, and this window is wall clock "
                    "in the person's own zone; the conversion belongs to the caller"
                )
                raise ValueError(msg)

    def wraps_midnight(self) -> bool:
        """True for the ordinary case, an evening start and a morning end."""
        return self.start > self.end

    def contains(self, at: datetime) -> bool:
        """Whether this moment is inside the window.

        Two arms because a night-time window is not an interval on a number line: 22:00 to
        07:00 is the union of two, and the version of this that compares `start <= t < end`
        is quiet for exactly the hours somebody did not ask for.
        """
        if at.tzinfo is None:
            msg = "quiet hours are compared against an aware datetime in the person's own zone"
            raise ValueError(msg)
        moment = at.timetz().replace(tzinfo=None)
        if self.wraps_midnight():
            return moment >= self.start or moment < self.end
        return self.start <= moment < self.end

    def deferred_until(self, at: datetime) -> datetime:
        """When something held by this window may be delivered.

        Returns `at` unchanged outside the window, so a caller can apply this unconditionally
        rather than asking twice and getting a different answer on the boundary.
        """
        if not self.contains(at):
            return at
        ending = at.replace(
            hour=self.end.hour,
            minute=self.end.minute,
            second=0,
            microsecond=0,
        )
        if ending <= at:
            ending += timedelta(days=1)
        return ending


def may_deliver(kind: NotificationKind, quiet: QuietHours | None, at: datetime) -> bool:
    """Whether this may be delivered now (M40.5.2.4).

    An approval is always deliverable and that is not a configuration:
    `AN_APPROVAL_HELD_UNTIL_MORNING_HAS_EXPIRED_BY_MORNING` is the argument, and the
    membership test is against `QUIET_HOURS_APPLY_TO` rather than an inequality, so a fourth
    kind added later is held by default rather than let through by default.
    """
    if quiet is None or kind not in QUIET_HOURS_APPLY_TO:
        return True
    return not quiet.contains(at)


@dataclass(frozen=True)
class ChannelPreference:
    """What this person wants on one channel (M40.5.2.2).

    A set of kinds rather than a boolean per kind, so a channel that wants nothing is an
    empty set rather than three fields that have to be read together. An empty set is
    allowed and means the channel is reachable and quiet, which is a real thing to want and
    is not the same as being unbound.
    """

    channel: Channel
    notify: frozenset[NotificationKind] = frozenset()


@dataclass(frozen=True)
class Reachability:
    """Where this person can be reached, and where an envelope should go (M40.5.2.1).

    Built by `reachability`, which is where every check lives, so this type can be loaded
    from a table without repeating them. That is the opposite of `brain.gate.leash.
    SuspendedAction`'s decision to enforce on the model as well, and the difference is what
    the row can do: a suspension that grants itself a year is dangerous on load, while a
    preference row naming a channel somebody has since unbound is stale rather than unsafe,
    and the honest repair is to re-run the builder rather than to refuse the load.
    """

    principal_id: str
    #: The channel this person is reached on when nothing says otherwise.
    primary: Channel
    preferences: tuple[ChannelPreference, ...]
    #: Where envelope approvals go. Always a channel that may carry an approve.
    approval_route: Channel
    quiet: QuietHours | None = None


def reachable_on(principal_id: str, bindings: Iterable[Binding]) -> tuple[Channel, ...]:
    """Every channel this person is bound on (M40.5.2.1), in the order the bindings arrive.

    Read off the bindings rather than off a preference row, because a preference is what
    somebody asked for and a binding is what was proved. A list built from preferences would
    show a channel nobody ever completed the binding for.
    """
    found: list[Channel] = []
    for one in bindings:
        if one.principal_id == principal_id and one.channel not in found:
            found.append(one.channel)
    return tuple(found)


def channels_that_may_approve(channels: Iterable[Channel]) -> tuple[Channel, ...]:
    """Which of these channels may carry an approval (M40.5.2.3).

    `brain.gate.admission.verbs_for_channel` decides, not a list here. That function matches
    on every member of `Channel` and calls `assert_never` on anything else, so a channel
    added to the system is a type error there rather than a silently permissive default here.
    """
    return tuple(one for one in channels if "approve" in verbs_for_channel(one))


def reachability(
    *,
    principal_id: str,
    bindings: Sequence[Binding],
    primary: Channel,
    preferences: Sequence[ChannelPreference] = (),
    approval_route: Channel | None = None,
    quiet: QuietHours | None = None,
) -> Reachability:
    """This person's channel settings, checked against what they are actually bound on.

    Five refusals, and every one of them is a setting that would otherwise look correct on
    the screen and deliver nothing.

    - A primary channel with no binding (M40.5.2.1). Being primarily reachable somewhere
      nobody proved you are is a default that fails on the first message.
    - A preference for a channel with no binding (M40.5.2.2). Indistinguishable, once saved,
      from a person nobody is writing to.
    - Two preferences for one channel (M40.5.2.2). One of them is dead and which one depends
      on the order a renderer happens to iterate in.
    - An approval route with no binding, and an approval route whose channel may not carry an
      approve (M40.5.2.3). See
      `AN_APPROVAL_SENT_WHERE_APPROVE_IS_REFUSED_IS_A_MESSAGE_NOBODY_CAN_ANSWER`.

    `approval_route` defaults to the primary rather than to a channel named here, because a
    default naming a channel would be a routing decision made by this module for everybody.
    Defaulting to the primary keeps the decision with the person, and the primary is then
    held to the approve check like any other route, which is how somebody whose primary is
    WhatsApp finds out at the moment they set it rather than at the moment they miss an
    envelope.
    """
    if not principal_id.strip():
        msg = "reachability for nobody is a preference row that matches every person or none"
        raise ValueError(msg)
    bound = reachable_on(principal_id, bindings)
    if primary not in bound:
        msg = (
            f"{primary.value} is set as the primary channel and this person has no binding "
            "on it, so every message sent by default goes nowhere"
        )
        raise MemberConnectionError(msg)

    seen: list[Channel] = []
    for one in preferences:
        if one.channel not in bound:
            msg = (
                f"there is a notification preference for {one.channel.value} and no binding "
                "on it, which saves as a working setting and delivers nothing"
            )
            raise MemberConnectionError(msg)
        if one.channel in seen:
            msg = (
                f"{one.channel.value} carries two notification preferences, so one of them "
                "is dead and which one depends on the order something iterates in"
            )
            raise MemberConnectionError(msg)
        seen.append(one.channel)

    route = approval_route if approval_route is not None else primary
    if route not in bound:
        msg = (
            f"approvals are routed to {route.value} and this person has no binding on it, "
            "so every envelope expires unanswered"
        )
        raise MemberConnectionError(msg)
    if "approve" not in verbs_for_channel(route):
        msg = (
            f"approvals are routed to {route.value}, which may not carry an approve. "
            f"{AN_APPROVAL_SENT_WHERE_APPROVE_IS_REFUSED_IS_A_MESSAGE_NOBODY_CAN_ANSWER}"
        )
        raise MemberConnectionError(msg)

    return Reachability(
        principal_id=principal_id,
        primary=primary,
        preferences=tuple(preferences),
        approval_route=route,
        quiet=quiet,
    )


def wants(settings: Reachability, channel: Channel, kind: NotificationKind) -> bool:
    """Whether this person wants this kind of message on this channel (M40.5.2.2).

    A channel with no preference row wants nothing, which is the quiet default and the one
    that cannot surprise somebody. The loud default would be to treat an absent row as "send
    everything", and the first person to discover that would discover it from their phone.
    """
    for one in settings.preferences:
        if one.channel is channel:
            return kind in one.notify
    return False


# -------------------------------------------------------------------------- the diagnostic
def connection_gaps(
    settings: Reachability | None = None,
) -> tuple[str, ...]:
    """Everything that would let a connection change what somebody may see (M40.5.1.2).

    **The first check is the load-bearing one and it is borrowed.**
    `brain.identity.oidc.assert_no_capability_from_claims` refuses a function whose return
    type could carry a `Capability`, a `Grant`, an `EntitlementSet` or a `PackAssignment`,
    looking one level into the fields of whatever it returns. That is exactly the rule this
    module needs about `connect`, arriving from the other direction: a fact asserted by
    something outside this system must not confer a capability, whether the outside is a
    directory or an account somebody linked.

    The second is about a settings object handed in rather than one built here, following
    `brain.console.reads.console_gaps`: a check that can only see a healthy input has nothing
    to report. A `Reachability` loaded from a table has been through no builder.
    """
    gaps: list[str] = []

    for one in (connect,):
        try:
            assert_no_capability_from_claims(one)
        except IdentityError as refused:
            gaps.append(
                f"{one.__name__} can return something capability-shaped, so connecting an "
                f"account could widen a reach. {refused}"
            )

    if settings is not None:
        if "approve" not in verbs_for_channel(settings.approval_route):
            gaps.append(
                f"approvals are routed to {settings.approval_route.value}, which may not "
                f"carry an approve. "
                f"{AN_APPROVAL_SENT_WHERE_APPROVE_IS_REFUSED_IS_A_MESSAGE_NOBODY_CAN_ANSWER}"
            )
        counted = [one.channel for one in settings.preferences]
        gaps.extend(
            f"{channel.value} carries two notification preferences, so one is dead"
            for channel in sorted(set(counted), key=lambda one: one.value)
            if counted.count(channel) > 1
        )

    return tuple(gaps)
