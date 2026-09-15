"""An automation runs as the person who owns it, and stops when that person does.

`docs/needs-rupash.md` item 56 was answered Option A: a step an automation takes is taken as
its owner, narrowed by the automation's own declared limit, so it can never do more than the
owner may do and never more than it declares. `brain.ops.automation.flow_reach` already
computed that narrowing and took the person as a parameter. This module is who the person is,
and what an automation is when the person has gone.

**The owner's reach is resolved on every call and never stored.** A registration holds the
owner's id and the automation's ceiling, and nothing else about what the owner holds. Removing
a permission here is deleting a grant, which bumps the grants version, so the next call
resolves the smaller set: the automation loses the permission at the moment the owner does,
because there is no second copy of the owner's grants anywhere to forget. See
`AN_AUTOMATION_HOLDS_NOTHING_OF_ITS_OWNER_BETWEEN_CALLS`.

**The credential names an automation and never a person.** `bap.<automation id>.<secret>`,
issued once, kept as a digest. It proves which automation is calling, and the automation's
registration then says whose reach that is. A person's session token is refused on the same
route, and an automation credential presented anywhere a person signs in is not a token at
all. See `A_CREDENTIAL_PROVES_AN_AUTOMATION_AND_THE_REGISTRATION_NAMES_THE_OWNER`.

Rejected: `brain.channels.api_keys` and `brain.identity.sessions.reach_for`, which already
narrow an owner's live reach by a ceiling. `reach_for` rebuilds the result under the service
account's own id, deliberately, so an integration's actions are recorded as the integration's.
Item 56 chose the other attribution: the answer to "who is responsible for what this automation
did" is a person, and `brain.ops.automation_piece.plan_piece_call` reads the principal off the
reach precisely so a step runs as that person. Reusing `reach_for` would make every automation
step a step taken by an account, which is Option C under another name. The digest and the
constant-time comparison are the three lines this module shares with `api_keys` in substance,
and its argument for SHA-256 over a password hash holds here word for word.

**An automation whose owner has gone is awaiting an owner, and that is derived rather than
stored.** `Standing` is worked out from the owner's principal record at the moment it is asked,
which is the moment a call arrives. A `state` column beside the principal's own standing would
be two facts that disagree for the length of whatever job reconciles them, and during that
window a leaver's automation would still be running. `brain.ops.jobs` makes the same argument
about a schedule. See `AN_OWNERLESS_AUTOMATION_STOPS_AND_WAITS`.

**A gone owner is answered exactly as an unknown automation is.** Whoever holds the credential
is told one sentence whichever of five things went wrong: a malformed credential, no such
automation, a wrong secret, an owner who is disabled or has gone, and an owner whose engagement
has ended. The reason is a closed vocabulary for the operator's log. A call refused for any of
them writes nothing, and the route has nothing to write on this path.

**Adoption is the one way out of waiting, and it does not happen by itself.** `adopt` refuses an
automation whose owner is still here: moving a running automation between two present people is
a transfer both of them should see, and it is not what "the owner has gone" asks for. It refuses
a new owner who is not live, because an adoption by somebody already leaving is a second
orphaning scheduled for later.

**What it may reach is read-only until writes can be suspended.** `plan_piece_call` defaults the
side-effect ceiling to NONE and the registration carries no field to raise it. A write from an
automation is exactly the action `brain.gate.leash` suspends for a person to approve, and the
suspension path has no automation in it yet: an approval card raised by nobody present, decided
by somebody, resumed at the owner's reach as it is then. Until that exists, a registration that
could declare a write would be a write nobody approves. See
`AN_AUTOMATION_READS_UNTIL_ITS_WRITES_CAN_BE_SUSPENDED`.

Not claimed: who may register an automation or adopt one is a console decision, and there is no
console surface for either. `brain.console.agent_automations` is where the owner reads their
automations, and it reads nothing from `gate.automation_owner` yet.

Task ids: none
"""

from __future__ import annotations

import enum
import hashlib
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final, Protocol

from brain.core.entitlement import EntitlementSet
from brain.core.principal import Principal
from brain.gate.admission import Assurance, admit
from brain.gate.context import Channel
from brain.gate.resolve import EntitlementCache, EntitlementStore, VersionSource, resolve
from brain.identity.roles import assert_not_a_role

# ------------------------------------------------------------ written-down reasons

#: Item 56, stated where a reader meets it.
AN_AUTOMATION_RUNS_AS_ITS_OWNER: Final = (
    "A step an automation takes is taken as the person who owns it, at that person's reach "
    "narrowed by the automation's declared ceiling. It can never do more than its owner may "
    "do and never more than it declares, and the answer to who is responsible for what it did "
    "is a person."
)

#: Why nothing about the owner's grants is kept on the registration.
AN_AUTOMATION_HOLDS_NOTHING_OF_ITS_OWNER_BETWEEN_CALLS: Final = (
    "The owner's entitlements are resolved when a call arrives and discarded when it ends. "
    "Revocation here is the deletion of a grant, so a copy of the owner's reach kept beside "
    "the automation would be a grant that survived its own deletion, and the automation would "
    "keep a permission its owner had lost."
)

#: Why the credential and the owner are two facts.
A_CREDENTIAL_PROVES_AN_AUTOMATION_AND_THE_REGISTRATION_NAMES_THE_OWNER: Final = (
    "The credential says which automation is calling and nothing about who it runs as. A "
    "credential bound to a person would be that person's session with no expiry and no "
    "sign-in, copied into a flow; one bound to the automation stops working for the owner the "
    "moment the registration names somebody else, without anybody rotating anything."
)

#: Why a gone owner stops the automation rather than leaving it to run at an empty reach.
AN_OWNERLESS_AUTOMATION_STOPS_AND_WAITS: Final = (
    "An automation whose owner is disabled, deleted or past the end of their engagement is "
    "awaiting an owner, and every call it makes is refused. Letting it run at an empty reach "
    "instead would look like a healthy flow producing nothing, which is the failure nobody "
    "sees. The standing is derived from the owner's record when it is asked, so there is no "
    "window between the owner leaving and the automation stopping."
)

#: Why one refusal covers every way an automation's call fails before a tool is chosen.
A_GONE_OWNER_IS_ANSWERED_AS_AN_UNKNOWN_AUTOMATION: Final = (
    "A malformed credential, an unknown automation, a wrong secret and a gone owner are one "
    "answer to whoever holds the credential and four reasons in the operator's log. Telling "
    "them apart would tell somebody holding a copied credential which part to fix next, and "
    "would tell anybody who can trigger a flow that its owner has left."
)

#: Why the registration has no side-effect field.
AN_AUTOMATION_READS_UNTIL_ITS_WRITES_CAN_BE_SUSPENDED: Final = (
    "A write is what the leash suspends for a person to approve, and no suspension path "
    "exists for work with nobody present. A registration that could declare a write would be "
    "a write nobody approves, so the ceiling on side effects stays at none and there is no "
    "field in which to raise it."
)

# --------------------------------------------------------------------- the credential

#: Marks the string as an automation credential, so one pasted into the wrong field is
#: recognisable in a support ticket without anybody trying it. Not `brn`, which is an API key
#: speaking for a service account: the two resolve to different principals, and a credential
#: that could be read as either is one somebody eventually reads as the wrong one.
CREDENTIAL_PREFIX: Final = "bap"

#: Bytes of randomness in the secret. 256 bits, which is why the digest needs no key
#: derivation function; see `brain.channels.api_keys` for the whole argument.
SECRET_BYTES: Final = 32

#: An automation id. A subset of `brain.gate.leash.IDENTIFIER`, because the id is also the
#: flow id `plan_piece_call` hands `invoke` as an agent id, without the full stop or the at
#: sign, because a full stop is the credential's separator and a separator has to be a
#: character the parts cannot contain. `brain.channels.api_keys.KEY_RE` records that mistake
#: being made twice in one day.
AUTOMATION_ID: Final = r"^[A-Za-z0-9_-]{1,128}$"

#: `bap.<automation id>.<secret>`, anchored at both ends.
CREDENTIAL_RE: Final = re.compile(r"^bap\.([A-Za-z0-9_-]{1,128})\.([A-Za-z0-9_-]{20,128})$")

#: A SHA-256 digest in hex.
DIGEST: Final = r"^[0-9a-f]{64}$"

_AUTOMATION_ID_RE: Final = re.compile(AUTOMATION_ID)
_DIGEST_RE: Final = re.compile(DIGEST)

#: Which channel ceiling an automation's call is held to. `API`, whose verbs are read, write
#: and invoke, so `brain.gate.admission` withholds approve and admin from an automation
#: whatever its owner holds: an approval taken by a flow is an approval nobody took.
AUTOMATION_CHANNEL: Final = Channel.API

#: How strongly the caller is known. `BOUND` is "bound to a principal on the strength of that
#: binding alone", which is exactly what a credential is: evidence about which automation this
#: is and about nobody's presence. It admits `read` and nothing else, which is also what
#: `AN_AUTOMATION_READS_UNTIL_ITS_WRITES_CAN_BE_SUSPENDED` requires, reached a second way.
AUTOMATION_ASSURANCE: Final = Assurance.BOUND


class AutomationRefusal(enum.StrEnum):
    """Why an automation's call was refused. For the operator's log, never for the caller."""

    MALFORMED = "malformed"
    UNKNOWN_AUTOMATION = "unknown_automation"
    MISMATCHED_CREDENTIAL = "mismatched_credential"
    OWNER_GONE = "owner_gone"


class AutomationRefusedError(Exception):
    """An automation may not call. One type, and the caller is told one sentence.

    See `A_GONE_OWNER_IS_ANSWERED_AS_AN_UNKNOWN_AUTOMATION`.
    """

    def __init__(self, reason: AutomationRefusal, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


class RegistrationError(ValueError):
    """A registration or an adoption is described in a way nothing should be built from."""


class Standing(enum.StrEnum):
    """Whether an automation may run. Closed, and derived; see `standing_of`."""

    RUNNING = "running"
    #: Its owner is disabled, deleted or past the end of their engagement.
    AWAITING_OWNER = "awaiting_owner"


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Registration:
    """One automation: its id, its owner, its credential's digest and its ceiling.

    **There is no secret here and no side-effect ceiling, and there must be neither.** The
    first for the reason `brain.channels.api_keys.ApiKeyRecord` gives; the second for
    `AN_AUTOMATION_READS_UNTIL_ITS_WRITES_CAN_BE_SUSPENDED`.

    **The ceiling is held under the automation's own id.** It is not a person's reach and it
    must not be mistakable for one: a set whose `principal_id` named the owner would be a set
    somebody could hand the gate as the owner's entitlements, and it would narrow nothing.
    """

    automation_id: str
    owner_principal_id: str
    credential_digest: str
    declared_tools: frozenset[str]
    ceiling: EntitlementSet

    def __post_init__(self) -> None:
        if not _AUTOMATION_ID_RE.fullmatch(self.automation_id):
            msg = f"automation id {self.automation_id!r} is not one a credential can carry"
            raise RegistrationError(msg)
        if not self.owner_principal_id.strip():
            msg = "an automation needs an owner; one owned by nobody runs as nobody"
            raise RegistrationError(msg)
        assert_not_a_role(self.owner_principal_id)
        if self.owner_principal_id == self.automation_id:
            msg = "an automation cannot own itself; its owner is the person answerable for it"
            raise RegistrationError(msg)
        if not _DIGEST_RE.fullmatch(self.credential_digest):
            msg = "a credential digest is a SHA-256 in hex, and this is not one"
            raise RegistrationError(msg)
        if not self.declared_tools:
            msg = (
                f"automation {self.automation_id!r} declares no tool; an empty set would either "
                "reach nothing or, the day somebody reads it as unset, everything"
            )
            raise RegistrationError(msg)
        if self.ceiling.principal_id != self.automation_id:
            msg = (
                f"automation {self.automation_id!r} carries a ceiling held under "
                f"{self.ceiling.principal_id!r}; a ceiling named for a person is a set somebody "
                "can hand the gate as that person's reach"
            )
            raise RegistrationError(msg)
        if self.ceiling.not_after is not None:
            msg = (
                f"automation {self.automation_id!r} carries a ceiling with an expiry. An "
                "automation stops when its owner does, and flow_reach judges a ceiling's expiry "
                "against the process clock rather than the call's instant, so a date here would "
                "be decided at the wrong moment"
            )
            raise RegistrationError(msg)


@dataclass(frozen=True)
class IssuedCredential:
    """A registration to store and the credential to show once. Two fields, as `IssuedKey`."""

    registration: Registration
    credential: str


def register(
    *,
    automation_id: str,
    owner: Principal,
    declared_tools: frozenset[str],
    ceiling: EntitlementSet,
    now: datetime,
) -> IssuedCredential:
    """A new automation owned by this person, and its credential.

    The owner must be live now. An automation registered to somebody already leaving is
    awaiting an owner from the moment it is made, and the person registering it would see it
    refuse every call with nothing on their screen saying why.
    """
    if not owner.is_active(now):
        msg = f"{owner.id} is not a live principal, so an automation cannot start out as theirs"
        raise RegistrationError(msg)
    secret = secrets.token_urlsafe(SECRET_BYTES)
    registration = Registration(
        automation_id=automation_id,
        owner_principal_id=owner.id,
        credential_digest=_digest(secret),
        declared_tools=declared_tools,
        ceiling=ceiling,
    )
    return IssuedCredential(
        registration=registration, credential=f"{CREDENTIAL_PREFIX}.{automation_id}.{secret}"
    )


def automation_id_of(presented: str) -> str:
    """The automation a presented credential names, for looking its registration up.

    Parsed before anything is read, so a malformed string is refused without a lookup.
    """
    match = CREDENTIAL_RE.fullmatch(presented)
    if match is None:
        raise AutomationRefusedError(AutomationRefusal.MALFORMED, "not an automation credential")
    return match.group(1)


def verify(presented: str, registration: Registration) -> Registration:
    """Check a presented credential against the registration it was looked up by.

    Returns the registration rather than a boolean, for the reason `api_keys.verify` returns
    the account: the only thing a caller can then act on is the thing that was checked.
    """
    match = CREDENTIAL_RE.fullmatch(presented)
    if match is None:
        raise AutomationRefusedError(AutomationRefusal.MALFORMED, "not an automation credential")
    automation_id, secret = match.group(1), match.group(2)
    if not secrets.compare_digest(automation_id, registration.automation_id):
        raise AutomationRefusedError(
            AutomationRefusal.UNKNOWN_AUTOMATION,
            f"credential for {automation_id} was checked against {registration.automation_id}",
        )
    # Constant time, because `==` on a digest leaks its prefix to anyone willing to measure.
    if not secrets.compare_digest(_digest(secret), registration.credential_digest):
        raise AutomationRefusedError(
            AutomationRefusal.MISMATCHED_CREDENTIAL,
            f"secret does not match {registration.automation_id}",
        )
    return registration


def loggable(presented: str) -> str:
    """What may be written down about a presented credential: the automation, never the secret."""
    try:
        return f"{CREDENTIAL_PREFIX}.{automation_id_of(presented)}"
    except AutomationRefusedError:
        return "<not an automation credential>"


# ----------------------------------------------------------------------- the owner


class PrincipalRecords(Protocol):
    """Who exists here now, by principal id.

    `None` for a principal who was never here, who has been deleted, or who is disabled. A
    disabled principal is not returned as a `Principal` with a flag, for the reason
    `brain.identity.oidc.principal_for` returns `UnmappedSubject` for a leaver: a real
    principal object on a code path is one somebody computes a reach for.
    """

    def live_principal(self, principal_id: str) -> Principal | None: ...


def standing_of(registration: Registration, owner: Principal | None, now: datetime) -> Standing:
    """Whether this automation may run now, from its owner's record as it is now.

    See `AN_OWNERLESS_AUTOMATION_STOPS_AND_WAITS`. A principal record for somebody other than
    the registered owner is a wiring fault and raises, because answering it would compute
    whether one person's automation runs from another person's standing.
    """
    if owner is None:
        return Standing.AWAITING_OWNER
    if owner.id != registration.owner_principal_id:
        msg = (
            f"automation {registration.automation_id!r} is owned by "
            f"{registration.owner_principal_id!r}, and was asked about {owner.id!r}"
        )
        raise RegistrationError(msg)
    if not owner.is_active(now):
        return Standing.AWAITING_OWNER
    return Standing.RUNNING


def awaiting_owner(
    registrations: Iterable[Registration], *, principals: PrincipalRecords, now: datetime
) -> tuple[str, ...]:
    """Every automation here that has stopped and is asking for a new owner, sorted.

    Keyed on the owner's standing and on nothing the automation reaches, for the reason
    `brain.identity.lifecycle.automations_to_stop` gives: an automation owned by a leaver that
    still reaches something and one that reaches nothing are both stopped.
    """
    return tuple(
        sorted(
            one.automation_id
            for one in registrations
            if standing_of(one, principals.live_principal(one.owner_principal_id), now)
            is Standing.AWAITING_OWNER
        )
    )


def owner_of(
    registration: Registration, *, principals: PrincipalRecords, now: datetime
) -> Principal:
    """The live owner this automation runs as, or the one refusal.

    Asked of `principals` on every call and never cached here. See
    `AN_AUTOMATION_HOLDS_NOTHING_OF_ITS_OWNER_BETWEEN_CALLS`.
    """
    owner = principals.live_principal(registration.owner_principal_id)
    if owner is None or standing_of(registration, owner, now) is not Standing.RUNNING:
        raise AutomationRefusedError(
            AutomationRefusal.OWNER_GONE,
            f"{registration.automation_id} is awaiting an owner",
        )
    return owner


def owner_reach(
    owner: Principal,
    *,
    versions: VersionSource,
    store: EntitlementStore,
    cache: EntitlementCache,
    now: datetime,
) -> EntitlementSet:
    """The owner's reach now, narrowed by the channel and assurance an automation is held to.

    `brain.gate.resolve.resolve`, so the grants version decides whether a cached set may be
    served and a revoked grant is gone on the next call. `brain.gate.admission.admit` with
    `AUTOMATION_CHANNEL` and `AUTOMATION_ASSURANCE`, so an owner holding approve or admin does
    not lend either to a flow. What this returns is the left-hand side of `flow_reach`; the
    automation's ceiling is applied there and nowhere here.
    """
    resolved = resolve(owner.id, versions=versions, store=store, cache=cache, now=now)
    return admit(resolved.entitlements, AUTOMATION_CHANNEL, AUTOMATION_ASSURANCE)


def adopt(
    registration: Registration,
    *,
    current_owner: Principal | None,
    new_owner: Principal,
    now: datetime,
) -> Registration:
    """The same automation under a new owner, if it is awaiting one.

    `current_owner` is the registered owner's record as it is now, from `PrincipalRecords`.
    See the module docstring on why a running automation is refused and why a new owner who
    is not live is refused. The credential and the ceiling are kept: the credential proves the
    automation rather than a person, and the ceiling is what the new owner is taking on, which
    they see before they adopt it rather than after.
    """
    if standing_of(registration, current_owner, now) is Standing.RUNNING:
        msg = (
            f"automation {registration.automation_id!r} still has a live owner; adoption is "
            "for an automation whose owner has gone, and moving a running one is a transfer"
        )
        raise RegistrationError(msg)
    if not new_owner.is_active(now):
        msg = f"{new_owner.id} is not a live principal, so they cannot adopt an automation"
        raise RegistrationError(msg)
    return replace(registration, owner_principal_id=new_owner.id)
