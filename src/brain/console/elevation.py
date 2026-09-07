"""The break-glass surface: what somebody holding nothing sees, and what elevating them costs.

M33.7 is the *installing partner*, not the Super Admin. The work breakdown reads
`Installing partner / Break-glass`, and reading it as "the Super Admin holds nothing until
they elevate" is the mistake this module opens by naming, because the two claims are
architecturally different and only one of them is true here.

**What is true today, stated plainly.** Zero standing entitlement is a property of
`brain.core.principal.Employment.PARTNER` and never of `brain.identity.roles.Role.SUPER_ADMIN`.
`standing_entitlement` returns `NoStandingEntitlement` for a partner whatever the grant table
says, and returns an ordinary `EntitlementSet` for everybody else. A Super Admin therefore
holds exactly the capability grants somebody wrote for them as a principal: the role adds
none, which `NO_ROLE_IMPLIES_A_CAPABILITY` and `role_capability_leaks` enforce and
`brain.firstrun.first_administrator` demonstrates by returning a `RoleGrant` and no grants at
all, and the role removes none either. See
`ZERO_STANDING_ENTITLEMENT_IS_AN_EMPLOYMENT_AND_NEVER_A_ROLE`, and `landing`, which is that
sentence written as three test cases rather than as a paragraph.

**Almost none of the machinery is here.** The session, its ceiling, its closed reason
vocabulary and its notice are `brain.identity.roles`; the chain is `brain.audit.ledger`; the
external digest is `brain.audit.anchor`; the recording seam is `brain.audit.record`; the reach
during a session is `roles.reach_during`, which this module calls and never reimplements. What
is decided here is who may authorise one, who must be told, which chain the entry lands in,
and how one ends early.

**A landing page that lists what you could elevate to is the capability catalogue.** Somebody
holding nothing, looking at a screen offering to elevate them, is the one reader for whom a
list of available grants is most useful and most disclosing: it is the vocabulary, narrowed to
what an authoriser would be willing to write, which is
`brain.console.govern.A_CATALOGUE_FILTERED_TO_THE_READER_IS_THEIR_OWN_ENTITLEMENT_RELABELLED`
pointed at somebody with no reach to relabel. `ElevationLanding` carries three fields and
`elevation_gaps` refuses a fourth that could hold one.

**The authority to elevate somebody is the authority to grant.** A break-glass session is a
grant with a clock on it, so inventing a capability for it would put a grant into the system
from the console layer, where the administrator who reviews grants would never meet it. That
is `brain.console.govern.SESSION_CONTROL`'s argument about ending a session, reached
independently and answered the same way: `ELEVATION_CONTROL` is `approve:grant`, written out
and pinned against the Access review screen by a test rather than derived from it, so
repointing either one fails.

**A notice to the subject or to the authoriser tells nobody anything.**
`BreakGlassSession` already refuses an empty `notified` and refuses a self-authorised session.
Neither refuses `notify=[authorised_by]`, which passes every test asserting that a notice was
produced and informs the one person who already knew. `client_recipients` computes the
recipients from the standing Super Admin grants rather than accepting a list, so the caller
has nowhere to pass the wrong one, and it refuses when the set is empty. That is
`brain.console.reads.A_NOTICE_ADDRESSED_TO_THE_ACTOR_IS_A_LOG_LINE_WITH_A_STAMP` one surface
over.

**A second chain buys a separate head and no immutability at all, and saying so is the
deliverable.** `brain.audit.ledger.AuditChain` is append-only and hash-chained, its retention
class is `NEVER_EXPIRES`, and a second instance of that class has identical guarantees:
nothing about a break-glass entry is harder to edit for sitting in its own run of entries.
What separation actually buys is one thing, and it is the thing a hash chain cannot do for
itself. Truncation is invisible from inside the data, only an anchor recorded outside the
database catches it, and `brain.audit.anchor.Anchor` carries a `chain` name. Two chains are
two anchors, so a handful of elevation entries can be anchored and published on their own
cadence rather than depending on somebody anchoring the whole ledger often enough. See
`A_SECOND_CHAIN_IS_A_SECOND_ANCHOR_AND_NOT_A_STRONGER_LEDGER`.

**Rejected: a chain field on `AuditEntry`, or a chain-aware `append`.** Both are edits to the
ledger, both change `HASH_SCHEMA` or the routing underneath it, and neither is needed: an
`AuditRecorder` is already constructed per writer, so routing is a choice of writer at the
call site. `elevation_recorder` makes that choice once and `chain_findings` checks it against
two real chains, which is the claim tested rather than asserted.

**Revocation shortens the window and there is nowhere for it to lengthen one.** Expiry is
already enforced by the machinery that enforces a contractor's, because `to_entitlement` puts
`expires_at` on the returned set and `EntitlementSet.scope_for` refuses an expired one, so an
answer computed inside the window cannot be served after it. Ending a session early had
nothing: `SessionRegistry.end_session` is about a sign-in and `reach_during` reads the
session's own bound. So `revoke` returns the same session with `expires_at` moved back, and
the reach afterwards is `roles.reach_during` unchanged. A revocation that could move the bound
forward would be an extension wearing the word revoke, which is why the guard is on both
sides. See `REVOCATION_SHORTENS_THE_WINDOW_AND_HAS_NOWHERE_TO_LENGTHEN_IT`.

Scope: domain logic. Nothing here opens a connection, renders anything or reads a clock; `now`
and `at` are parameters, for the reason `brain.ops.limits` gives about policy that owns a
client being untestable at the boundary that matters. No console screen exists behind any of
this, exactly as `brain.console.screens` says of its own registry; what is claimed below is
the disclosure decision in each leaf, which is the whole content of four of the five.

Task ids: M33.7.1.1, M33.7.1.2, M33.7.1.3, M33.7.1.4, M33.7.1.5
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from brain.audit.anchor import Anchor
from brain.audit.ledger import AuditAction, AuditChain, AuditEntry
from brain.audit.record import AuditRecorder, LedgerWriter
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import Principal
from brain.identity.roles import (
    BREAK_GLASS_CHAIN,
    BREAK_GLASS_MAX,
    PARTNER_PROMPT,
    BreakGlassReason,
    BreakGlassSession,
    NoStandingEntitlement,
    Notification,
    RoleGrant,
    open_break_glass,
    standing_entitlement,
    standing_super_admins,
)
from brain.ops.halt import MINIMUM_REASON
from brain.ops.jobs import hidden_count_fields

# ------------------------------------------------------------------ written-down reasons
#: The answer to "does a Super Admin hold standing entitlement today".
ZERO_STANDING_ENTITLEMENT_IS_AN_EMPLOYMENT_AND_NEVER_A_ROLE: Final = (
    "brain.identity.roles.standing_entitlement returns NoStandingEntitlement for one input "
    "and one only, which is a principal whose employment is PARTNER, and it ignores their "
    "grant rows deliberately. Everybody else gets an ordinary EntitlementSet built from the "
    "rows they hold. So a Super Admin holds whatever capability grants somebody wrote for "
    "them: the role confers none, which role_capability_leaks enforces across the package "
    "and firstrun.first_administrator shows by returning a RoleGrant and no grants, and the "
    "role withholds none either. M33.7 is the installing partner rather than the Super "
    "Admin, and reading it the other way turns a true statement about a partner into a false "
    "one about an administrator."
)

#: Why the landing page offers no list of what a session could confer.
A_LANDING_THAT_LISTS_WHAT_YOU_COULD_ELEVATE_TO_IS_THE_CATALOGUE: Final = (
    "The one reader for whom a list of available capabilities is most useful is the one "
    "holding none, and they are also the reader it discloses most to: the list is the grant "
    "vocabulary, filtered to what somebody would be willing to authorise, on a screen that "
    "reaches nothing. brain.console.govern makes the same argument about a catalogue "
    "narrowed to the reader. ElevationLanding carries a principal, a sentence and a "
    "decision, and elevation_gaps refuses a fourth field a list could arrive in."
)

#: Why elevating somebody needs the grant capability rather than one invented here.
THE_AUTHORITY_TO_ELEVATE_IS_THE_AUTHORITY_TO_GRANT: Final = (
    "A break-glass session is a set of grants with a clock on it. Inventing admin:elevate "
    "for it would put a capability into the system from the console layer, where the "
    "administrator reviewing grants would never meet it, and there would then be two answers "
    "to who may widen somebody's reach. approve:grant is the capability the Access review "
    "screen already requires to keep or remove a grant, so it is the one asked here, in a "
    "scope that admits the row the subject sits in."
)

#: Why the recipients are computed rather than accepted.
A_NOTICE_TO_THE_SUBJECT_OR_THE_AUTHORISER_TELLS_NOBODY: Final = (
    "BreakGlassSession refuses an empty notified list and refuses a session somebody "
    "authorised for themselves. Neither refuses notifying only the person who authorised it, "
    "and that passes every test asserting a notice was produced while informing the one "
    "person who already knew. Loud means somebody else finds out, which is what "
    "brain.console.reads says about a steward notice, so the recipients are the standing "
    "Super Admins other than those two and there is no parameter a list could arrive through."
)

#: What a separate audit chain does and does not buy.
A_SECOND_CHAIN_IS_A_SECOND_ANCHOR_AND_NOT_A_STRONGER_LEDGER: Final = (
    "AuditChain is append-only and hash-chained and the audit retention class never expires, "
    "so a second instance of it is not more immutable than the first and an elevation entry "
    "is no harder to edit for sitting in its own run. The chain cannot see a truncated tail "
    "at all: only a digest recorded outside the database catches that, which is what Anchor "
    "is, and Anchor carries a chain name. Two chains are therefore two anchors, and a "
    "handful of elevation entries can be published on their own cadence instead of depending "
    "on somebody anchoring the whole ledger often enough to notice."
)

#: Why revocation is expressed as a shorter window.
REVOCATION_SHORTENS_THE_WINDOW_AND_HAS_NOWHERE_TO_LENGTHEN_IT: Final = (
    "Expiry is already enforced where it cannot be forgotten: to_entitlement puts expires_at "
    "on the set, scope_for refuses an expired one, and ent_hash covers not_after so a cached "
    "answer cannot be reached from the other side of it. Ending a session early had nothing, "
    "and the tempting shape is a revoked flag consulted by a new check. A flag is a negative "
    "row and this system has none. So a revocation returns the session with expires_at moved "
    "back, roles.reach_during decides the reach exactly as before, and the guard refuses an "
    "instant at or after the existing bound, because moving it forward is an extension."
)

#: Field names on the landing that would put the vocabulary back on it.
#:
#: Restated here rather than imported from `brain.ops.jobs`, whose list is about counts, on
#: `brain.console.govern.NAMES_THAT_WOULD_NAME_THE_THING`'s argument: the field that breaks
#: this surface is called `available` or `offered` rather than `hidden`. Both are checked.
NAMES_THAT_WOULD_LIST_THE_VOCABULARY: Final[frozenset[str]] = frozenset(
    {
        "available",
        "capabilities",
        "catalogue",
        "grants",
        "offered",
        "options",
        "reachable",
    }
)


class ElevationError(Exception):
    """A break-glass surface was asked for something that would not actually be break-glass.

    Outside `brain.core.errors` for the reason `brain.console.govern.GovernError` gives about
    itself: those five outcomes describe an answer given to somebody asking a question, and
    this is a refusal to assemble or record an elevation. Nobody asking a question sees one.
    """


# --------------------------------------------------------- zero standing entitlement (M33.7.1.1)
#: What is said to somebody who does hold standing grants. Names no capability.
#:
#: A second sentence rather than reusing `PARTNER_PROMPT`, because that one reads "this
#: account holds no standing access" and saying it to somebody who does is a false statement
#: on the one screen whose whole subject is what they hold.
ALREADY_HOLDS_PROMPT: Final = (
    "This account holds standing access of its own. A break-glass session replaces it for the "
    "window rather than adding to it."
)


def holds_nothing_standing(principal: Principal, grants: Sequence[object] = ()) -> bool:
    """Whether this principal reaches nothing at all with no session open (M33.7.1.1).

    `brain.identity.roles.standing_entitlement` is the one answer to that and this asks it.
    The test is on the *type* it returns rather than on a grant count, which is that
    module's own distinction: an `EntitlementSet` with no grants is a thing that can be
    intersected, cached and passed down a delegation chain, and `NoStandingEntitlement`
    cannot be any of those. A check written as `not entitlement.grants` would answer True for
    both and would go on answering True on the day somebody adds a default grant.

    `grants` is typed loosely because it is passed straight through and never read here; the
    signature exists so a caller cannot believe they narrowed something by omitting it.
    """
    # `standing_entitlement` takes a sequence of `Grant`; it is handed on unexamined, and the
    # cast is at a boundary where proving the element type buys nothing this function uses.
    reach = standing_entitlement(principal, grants)  # type: ignore[arg-type]
    return isinstance(reach, NoStandingEntitlement)


@dataclass(frozen=True)
class ElevationLanding:
    """What somebody arriving at the break-glass screen is shown (M33.7.1.1).

    Three fields. There is no list of what a session could confer, no count of the grants
    somebody might authorise, and nowhere to put either. See
    `A_LANDING_THAT_LISTS_WHAT_YOU_COULD_ELEVATE_TO_IS_THE_CATALOGUE`, which `elevation_gaps`
    asks of the type rather than of whoever edits it next.

    `prompt` is `brain.identity.roles.PARTNER_PROMPT` unchanged for somebody holding nothing,
    imported rather than restated so the sentence a partner reads is written once.
    """

    principal_id: str
    prompt: str
    holds_nothing_standing: bool


def landing(principal: Principal, *, grants: Sequence[object] = ()) -> ElevationLanding:
    """The break-glass screen for one principal, before any session exists (M33.7.1.1).

    Two prompts and no third. A partner reads that they hold no standing access, which is
    true of them and of nobody else; anybody with grants of their own reads that a session
    replaces what they hold rather than adding to it, which is `reach_during`'s behaviour
    stated on the screen that offers to open one. Neither names a capability.

    See `ZERO_STANDING_ENTITLEMENT_IS_AN_EMPLOYMENT_AND_NEVER_A_ROLE` for why a Super Admin
    lands on the second sentence and a partner on the first, whatever either of them holds
    on the platform.
    """
    nothing = holds_nothing_standing(principal, grants)
    return ElevationLanding(
        principal_id=principal.id,
        prompt=PARTNER_PROMPT if nothing else ALREADY_HOLDS_PROMPT,
        holds_nothing_standing=nothing,
    )


# ------------------------------------------------- time-boxed, with a stated reason (M33.7.1.2)
#: The capability that may authorise an elevation.
#:
#: The Access review screen's own requirement, written out here rather than read off the
#: registry so a test can compare the two: derived, the comparison would be a constant against
#: itself and repointing either would move both. `brain.console.govern.SESSION_CONTROL` and
#: `brain.console.reach_view.CEILING_DISCLOSURE` are pinned the same way.
#:
#: See `THE_AUTHORITY_TO_ELEVATE_IS_THE_AUTHORITY_TO_GRANT`.
ELEVATION_CONTROL: Final = Capability(value="approve:grant")


def may_authorise(
    entitlement: EntitlementSet,
    where: Mapping[str, str],
    now: datetime | None = None,
) -> bool:
    """Whether this reader may open a session for somebody sitting in this row (M33.7.1.2).

    `EntitlementSet.scope_for` followed by `Scope.matches`, which is the pair of public calls
    `brain.console.govern._in_reach` makes about a governance record and
    `brain.console.agent_output.may_see` makes about an artifact. Two calls rather than an
    intersection: `scope_for` decides what holding the capability means and refuses an expired
    principal, and `matches` decides whether the grant admits the place.
    """
    scope = entitlement.scope_for(ELEVATION_CONTROL, now)
    if scope is None:
        return False
    return scope.matches(dict(where))


def request_elevation(
    *,
    session_id: str,
    principal: Principal,
    reason: BreakGlassReason,
    grants: Sequence[object],
    authoriser: EntitlementSet,
    role_grants: Sequence[RoleGrant],
    where: Mapping[str, str],
    now: datetime,
    duration: timedelta = BREAK_GLASS_MAX,
) -> tuple[BreakGlassSession, Notification]:
    """Open a session from the console, or refuse (M33.7.1.2, M33.7.1.4).

    Four things are decided before `brain.identity.roles.open_break_glass` is called and none
    of them is repeated from it. The authoriser holds `ELEVATION_CONTROL` in a scope admitting
    the subject's row. The reason is a `BreakGlassReason` by signature, so free text cannot
    arrive and be redacted to nothing in the ledger afterwards. The recipients are computed
    rather than accepted, which is `client_recipients`. And the window is whatever the
    authoriser asked for, bounded by `BREAK_GLASS_MAX`, which `open_break_glass` enforces and
    this deliberately does not re-check: a second bound is a second place for the ceiling to
    be raised.

    The pair return comes straight back from `open_break_glass`, unopened. A function here
    that returned only the session would put the notice back in the hands of a caller
    handling an incident at two in the morning, which is the shape that module rejected.
    """
    if not may_authorise(authoriser, where, now):
        msg = (
            f"{authoriser.principal_id!r} may not open a break-glass session for "
            f"{principal.id!r}. {THE_AUTHORITY_TO_ELEVATE_IS_THE_AUTHORITY_TO_GRANT}"
        )
        raise ElevationError(msg)
    recipients = client_recipients(
        role_grants,
        subject_id=principal.id,
        authorised_by=authoriser.principal_id,
        now=now,
    )
    # `open_break_glass` takes a sequence of `Grant`; handed straight on, unexamined, for the
    # reason `holds_nothing_standing` gives about its own parameter.
    return open_break_glass(
        session_id=session_id,
        principal=principal,
        reason=reason,
        grants=grants,  # type: ignore[arg-type]
        authorised_by=authoriser.principal_id,
        notify=recipients,
        now=now,
        duration=duration,
    )


# --------------------------------------------------- client notification (M33.7.1.4)
def client_recipients(
    role_grants: Sequence[RoleGrant],
    *,
    subject_id: str,
    authorised_by: str,
    now: datetime | None = None,
) -> tuple[str, ...]:
    """Who the company is told through, for one elevation (M33.7.1.4).

    The standing Super Admins, other than the subject and other than the authoriser. See
    `A_NOTICE_TO_THE_SUBJECT_OR_THE_AUTHORISER_TELLS_NOBODY`.

    `brain.identity.roles.standing_super_admins` is what decides who those are, so a deputy
    covering somebody's annual leave is not a recipient here for the same reason they do not
    count towards the floor there: cover is not ownership, and a notice whose only reader is
    a thirty-day appointment ends when the appointment does.

    **Refuses rather than returning an empty tuple.** `BreakGlassSession` would refuse the
    empty list one frame later with a message about notification in general; refusing here
    says which install state produced it, which is the one that matters: nobody independent
    is left to tell. Sorted, so two readings of an unchanged role table are the same list and
    the ledger's `notified` detail does not move between recordings of one event.
    """
    holders = {
        one.principal_id
        for one in standing_super_admins(role_grants, now)
        if one.principal_id not in {subject_id, authorised_by}
    }
    if not holders:
        msg = (
            f"an elevation of {subject_id!r} authorised by {authorised_by!r} has nobody to "
            f"notify: no standing Super Admin remains who is neither. "
            f"{A_NOTICE_TO_THE_SUBJECT_OR_THE_AUTHORISER_TELLS_NOBODY}"
        )
        raise ElevationError(msg)
    return tuple(sorted(holders))


# ----------------------------------------------------- the separate chain (M33.7.1.3)
#: The chain elevation entries are written to.
#:
#: Written out rather than imported from `brain.identity.roles`, so a test can compare the two
#: against each other: imported, `ELEVATION_CHAIN == BREAK_GLASS_CHAIN` would be a constant
#: against itself and repointing either would move both. The session's own `audit_chain`
#: property names the same string, and `chain_findings` is what checks that the entries
#: actually went there.
ELEVATION_CHAIN: Final = "break_glass"

#: The one action that belongs in the elevation chain, and the only one.
#:
#: A frozen set rather than a bare member, because the check `chain_findings` performs is a
#: membership test in both directions and a single member expressed as an equality reads as
#: the weaker of the two.
ELEVATION_ACTIONS: Final[frozenset[AuditAction]] = frozenset({AuditAction.BREAK_GLASS})


def elevation_recorder(
    writer: LedgerWriter,
    session: BreakGlassSession,
    *,
    ent_hash: str,
    trace_id: str,
    clock: Callable[[], datetime],
) -> AuditRecorder:
    """A recorder bound to the elevation chain and to the person who authorised it (M33.7.1.3).

    **The actor is the authoriser and never the subject.** The act being recorded is the
    authorisation of an elevation, and `brain.console.reads.is_self_grant` recognises a
    self-grant as an entry whose subject names its own actor: recording the subject as actor
    would make every properly authorised break-glass entry read as one somebody made to
    themselves, and the detection that must never be defeated would fire on the case it was
    written to catch.

    The routing is a choice of writer and nothing else, which is what makes a separate chain
    cost one function rather than an edit to the ledger. See
    `A_SECOND_CHAIN_IS_A_SECOND_ANCHOR_AND_NOT_A_STRONGER_LEDGER`.
    """
    return AuditRecorder(
        writer,
        actor_id=session.authorised_by,
        ent_hash=ent_hash,
        trace_id=trace_id,
        clock=clock,
    )


def record_elevation(recorder: AuditRecorder, session: BreakGlassSession) -> AuditEntry:
    """Write one elevation entry through the recording seam (M33.7.1.3).

    `AuditRecorder.break_glass` builds the details, which is why the session is taken apart
    here rather than handed over whole: that module deliberately does not import the identity
    layer, so the direction of the dependency stays the right way up and this is the module
    that knows both types.

    Nothing is redacted or assembled here. The recorder hands the values to the ledger and
    the ledger redacts them, which is `brain.audit.record._write`'s own rule about the two
    places a redaction decision may live.
    """
    return recorder.break_glass(
        session_id=session.session_id,
        principal_id=session.principal_id,
        reason=session.reason,
        authorised_by=session.authorised_by,
        notified=session.notified,
    )


def chain_findings(*, main: AuditChain, elevation: AuditChain) -> tuple[str, ...]:
    """Everything about a two-chain arrangement that would make the separation a name only.

    Two checks and they are different failures. An elevation entry in the main chain is a
    recorder built with the wrong writer, which is the failure this whole leaf is about and
    is invisible on any screen: the entry exists, it verifies, and it is anchored with a
    million rows of routine traffic. Anything that is not an elevation in the elevation chain
    is the opposite mistake, and it matters because the value of the second chain is that its
    head moves only when somebody elevates.

    Takes both chains rather than reading a registry, on
    `brain.console.govern.govern_gaps`' argument about its own parameters: a diagnostic that
    found its own inputs could only be run against a healthy tree, so switching off either
    refusal would change nothing observable and both would survive a mutation.
    """
    findings: list[str] = []
    findings.extend(
        f"seq {one.seq} in the main chain is a {one.action.value} entry, so the elevation "
        f"chain is a name in a details field rather than a chain. "
        f"{A_SECOND_CHAIN_IS_A_SECOND_ANCHOR_AND_NOT_A_STRONGER_LEDGER}"
        for one in main.entries
        if one.action in ELEVATION_ACTIONS
    )
    findings.extend(
        f"seq {one.seq} in the {ELEVATION_CHAIN} chain is a {one.action.value} entry, so the "
        "chain's head moves for something that is not an elevation and comparing it says "
        "nothing about whether anybody elevated"
        for one in elevation.entries
        if one.action not in ELEVATION_ACTIONS
    )
    return tuple(findings)


def anchor_findings(anchors: Iterable[Anchor]) -> tuple[str, ...]:
    """Whether the elevation chain is anchored on its own (M33.7.1.3).

    The one thing a hash chain cannot do for itself is notice that its newest entries were
    removed, and the only fix is a digest recorded where the database administrator cannot
    reach it. `brain.audit.anchor.Anchor` carries a chain name precisely so there can be more
    than one of these, and an arrangement with two chains and one anchor has a second chain
    whose truncation nothing would catch.

    Reported rather than raised, because an install that has not yet run the pulling job is
    a state a deployment check should print and not a reason to refuse an elevation.
    """
    named = {one.chain for one in anchors}
    if ELEVATION_CHAIN in named:
        return ()
    return (
        f"no anchor names the {ELEVATION_CHAIN} chain, so its tail can be truncated and "
        f"nothing outside the database would disagree. "
        f"{A_SECOND_CHAIN_IS_A_SECOND_ANCHOR_AND_NOT_A_STRONGER_LEDGER}",
    )


# ------------------------------------------------- expiry and revocation (M33.7.1.5)
@dataclass(frozen=True)
class Revocation:
    """One session ended before its own expiry, by somebody, for a stated reason.

    `reason` is held to `brain.ops.halt.MINIMUM_REASON` rather than to a number written here,
    which anchors it to the length that module decided is the shortest thing that says
    anything, and for the same situation: whoever reads this afterwards is trying to work out
    whether the incident was handled or the session was closed by mistake.

    There is no field naming what the session conferred. That is on the session and in the
    ledger under its own redaction rules; copying it onto a revocation would put a capability
    into a record that travels to whoever is watching the console.
    """

    session_id: str
    by: str
    at: datetime
    reason: str

    def __post_init__(self) -> None:
        if not self.by.strip():
            msg = "a revocation by nobody leaves no one accountable for ending the session"
            raise ElevationError(msg)
        if self.at.tzinfo is None:
            msg = "a naive revocation time compares wrongly against an aware session bound"
            raise ElevationError(msg)
        if len(self.reason.strip()) < MINIMUM_REASON:
            msg = (
                f"{self.reason!r} is not a reason to end an authorised session early, and the "
                "next reader has nothing else to go on"
            )
            raise ElevationError(msg)


def revoke(session: BreakGlassSession, revocation: Revocation) -> BreakGlassSession:
    """The same session, ending now instead of when it was going to (M33.7.1.5).

    **Shortening the window is the whole mechanism.** See
    `REVOCATION_SHORTENS_THE_WINDOW_AND_HAS_NOWHERE_TO_LENGTHEN_IT`. What comes back is a
    `BreakGlassSession` through its own validators, so nothing about it can be less valid
    than the original, and `brain.identity.roles.reach_during` decides the reach afterwards
    exactly as it did before. There is no second place that knows a session can end.

    Three refusals. A revocation naming a different session is a caller who lost track of
    which one they were holding, and applying it would end the wrong elevation. An instant at
    or before `opened_at` cannot produce a session at all, because a window of zero length is
    refused by the model. And an instant at or after `expires_at` is a revocation of something
    that has already ended, which either does nothing or, if it were applied, would move the
    bound forward.
    """
    if revocation.session_id != session.session_id:
        msg = (
            f"revocation names {revocation.session_id!r} and this session is "
            f"{session.session_id!r}; applying it would end an elevation nobody revoked"
        )
        raise ElevationError(msg)
    if revocation.at <= session.opened_at:
        msg = (
            f"a revocation at {revocation.at.isoformat()} is at or before the session opened; "
            "a window of no length is not a session that was revoked, it is one that never ran"
        )
        raise ElevationError(msg)
    if revocation.at >= session.expires_at:
        msg = (
            f"this session already ends at {session.expires_at.isoformat()} and the "
            f"revocation is at {revocation.at.isoformat()}. "
            f"{REVOCATION_SHORTENS_THE_WINDOW_AND_HAS_NOWHERE_TO_LENGTHEN_IT}"
        )
        raise ElevationError(msg)
    return session.model_copy(update={"expires_at": revocation.at})


def expired_by(session: BreakGlassSession, now: datetime) -> bool:
    """Whether this session has run out on its own, with nobody doing anything (M33.7.1.5).

    `BreakGlassSession.is_open` is what decides, asked rather than compared against
    `expires_at` a second time here. The negation is not quite its complement and the
    difference is deliberate: a session whose `opened_at` is in the future is not open and has
    not expired either, so a caller reading "not open" as "expired" would report an elevation
    that has not started as one that finished.
    """
    return now >= session.expires_at


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of this surface is handed. Listed rather than discovered, following
#: `brain.console.govern.GOVERN_ROWS`: a type added here and not to this tuple is one the
#: checks below never see.
ELEVATION_SURFACE: Final[tuple[type, ...]] = (ElevationLanding, Revocation)


def elevation_gaps(
    *,
    rows: Sequence[type] = ELEVATION_SURFACE,
    landing_row: type = ElevationLanding,
    control: Capability = ELEVATION_CONTROL,
    chain: str = ELEVATION_CHAIN,
) -> tuple[str, ...]:
    """Everything about this surface that would show somebody more than they hold.

    Takes its inputs rather than reading the module's own constants, for the reason
    `brain.console.govern.govern_gaps` gives about its own parameters: a diagnostic that can
    only run against the healthy tree reports nothing today, so switching off any of its
    refusals changes nothing observable and every one survives a mutation. Calling it with no
    arguments is the deployment check and calling it with a constructed set is the test.

    Four checks. A hidden count on any row, a field on the landing that would carry the
    vocabulary, a control that is not the grant capability, and a chain name that has come
    apart from the identity layer's.
    """
    gaps: list[str] = []

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(rows)
    )
    gaps.extend(
        f"{landing_row.__name__}.{name} puts the grant vocabulary on a screen reached by "
        f"somebody holding nothing. "
        f"{A_LANDING_THAT_LISTS_WHAT_YOU_COULD_ELEVATE_TO_IS_THE_CATALOGUE}"
        for name in getattr(landing_row, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_LIST_THE_VOCABULARY
    )
    if control != screen("access_review").read.requires:
        gaps.append(
            f"the elevation control is {control.value} and the Access review screen requires "
            f"{screen('access_review').read.requires.value}, so there are two answers to who "
            f"may widen somebody's reach. {THE_AUTHORITY_TO_ELEVATE_IS_THE_AUTHORITY_TO_GRANT}"
        )
    if chain != BREAK_GLASS_CHAIN:
        gaps.append(
            f"this module writes to {chain!r} and brain.identity.roles names "
            f"{BREAK_GLASS_CHAIN!r}, so a session says it is chained somewhere its entries "
            "are not and the anchor for one of the two names an empty chain"
        )

    return tuple(gaps)
