"""The data steward: the named person every read of the company's data on an install begins with.

**The bootstrap this closes.** `brain.console.scoped_authority.may_grant` lets nobody grant a
capability they do not hold, and the first administrator holds every `admin:` capability and no
data or content capability, on purpose: see
`brain.identity.first_administrator.AN_ADMINISTRATOR_GOVERNS_THE_SYSTEM_AND_READS_NO_DATA`. Both
rules are right, and together they meant that on every install nobody could ever be given
`read:client.*`, `read:console.content` or anything a connected source declares, by any path.
`docs/admin-console-architecture.md` Part 6.1 put three options to the owner and on 2026-09-17 he
chose A: a data steward named in setup. See `DATA_ACCESS_BEGINS_WITH_A_NAMED_STEWARD`.

**What a steward holds.** `approve:grant` and the console's content plane over everything, from
the moment of appointment, and every capability a connected source declares, over everything,
from the moment the source is connected or the steward appointed, whichever is later. Everybody
else's data reach is then granted by the steward, or by somebody the steward granted, through the
People screen's grant route and `may_grant` like every other grant.

**An appointment, and not a relaxation of `may_grant`.** Whoever appoints a steward, first run or
an administrator, grants reach they do not hold themselves, which is the one thing `may_grant`
exists to refuse. It is the same kind of act as appointing the first administrator: the product
naming a role-holder once, recorded in the ledger against a named actor, and not a grant one
person makes to another. So the rows are written with `granted_by` `STEWARD_GRANTOR` rather than
with the actor's id, which would make the People screen say an administrator granted a data read
they cannot hold, and the ledger's actor is set explicitly to whoever made the appointment. Every
grant anybody makes afterwards, the steward included, is bounded by what they hold. See
`AN_APPOINTMENT_IS_THE_PRODUCT_S_ACT_AND_NOBODY_GRANTS_PAST_THEIR_OWN_REACH`.

**The administrator is the steward too only when somebody says so, and "administrator" is one
test.** The steward is judged an administrator by `first_administrator.holds_everywhere` over the
reach the resolver returns inside the appointing transaction, and an appointment whose stated
choice disagrees with that judgement is refused either way round. The setup wizard asks the
question separately from the name and the address and refuses the administrator's own address
without it. See `THE_SAME_PERSON_IS_A_CHOICE_SAID_OUT_LOUD`.

**Once per install, and the grant row is the record.** The steward's content-plane grant is
written under one fixed id, `APPOINTMENT_GRANT_ID`, with a conflict on the key writing nothing. A
second appointment therefore meets the first one's row whether that row is live or retired, which
`0045`'s policy hides from the application role and a unique key does not. Who the steward is
reads the principal off that row while it is live. See `A_STEWARD_IS_APPOINTED_ONCE`.

Rejected: a table naming the steward. It is a migration, a policy, a model and a second record of
a fact the grant row already carries, and it would still need the grant rows beside it. The row
that confers the content plane is the appointment, in the way `sign_in_binding.member_grant_id`
makes the binding's grant the record that a workspace was granted.

**A source's declarations reach the steward in the connection's transaction.** The connect store
takes `STEWARD_LOCK` before it writes the connection's row, and grants what the source's manifest
declares after it, so a connection that fails writes no grant and an appointment racing a
connection sees either the connection or the steward. With no steward yet, a connection grants
nothing, and the appointment grants the declarations of every source connected by then. See
`A_CONNECTION_GRANTS_THE_STEWARD_WHAT_THE_SOURCE_DECLARES`.

**One lock, and always before the ledger's.** Every grant row appends a ledger entry under the
ledger's own advisory lock, held to commit. An appointment holds `STEWARD_LOCK` while it writes
grants, so a connection that took the ledger's lock first and then asked for this one would wait on
an appointment waiting on it. Every path here takes this lock before its first write. See
`THE_STEWARD_S_LOCK_COMES_BEFORE_THE_LEDGER_S`.

**Disconnecting retires nothing.** Entitlements are additive, and revocation is somebody deleting a
grant on purpose. See `DISCONNECTING_A_SOURCE_TAKES_NOTHING_FROM_THE_STEWARD`.

**A capability taken from the steward is not given back.** Every steward grant's id is derived
from the principal and the capability, and every insert writes nothing on any conflict, so a grant
somebody retired stays retired when the same source is connected again or another source declares
the same entity. See `A_CAPABILITY_TAKEN_FROM_THE_STEWARD_IS_NOT_GIVEN_BACK`.

**A source declares reads, and never a write.** `declared_capabilities` is each entity a manifest's
tools or projections reach, as the row capability and every field of it. A tool with a side effect
needs a write binding, which `brain.connectors.manifest` calls a separate deliberate grant, and it
is not handed out by connecting anything. See `A_SOURCE_DECLARES_ITS_READS_AND_NEVER_A_WRITE`.

**Nothing grants an agent anything.** A steward is a live human principal; an agent is not a
principal at all, and a service principal is refused.

Not here: replacing a steward. See `A_STEWARD_IS_APPOINTED_ONCE`.

Task ids: M27.9.9
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.contract import ConnectorContractError
from brain.connectors.manifest import ConnectorManifest
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.entitlement_store import entitlements_from
from brain.identity.first_administrator import holds_everywhere
from brain.identity.principal_store import COLUMNS, readable
from brain.identity.roles import IdentityError
from brain.ops.connectable import NotConnectableError, manifest_for
from brain.tables.audit import attributed_to
from brain.tables.connector_connection import ConnectorConnectionRow
from brain.tables.gate import CapabilityGrantRow
from brain.tables.identity import PrincipalRow

log = structlog.get_logger(__name__)

# ------------------------------------------------------------ written-down reasons

#: The rule the whole module serves.
DATA_ACCESS_BEGINS_WITH_A_NAMED_STEWARD: Final = (
    "Nobody may grant what they do not hold, and the first administrator holds no data, so every "
    "read of the company's data has to begin with somebody. That somebody is one person, named in "
    "setup or by an administrator where setup named nobody, holding approve:grant, the content "
    "plane and every connected source's declared reads over everything, and recorded in the ledger "
    "against whoever named them. It is never the administrator by default."
)

#: Why appointing a steward does not break `may_grant`.
AN_APPOINTMENT_IS_THE_PRODUCT_S_ACT_AND_NOBODY_GRANTS_PAST_THEIR_OWN_REACH: Final = (
    "Appointing the steward grants reach the appointer does not hold, as appointing the first "
    "administrator does. Both are the product naming a role-holder once, and neither is a grant "
    "one person makes to another, so the rows name the appointment as their grantor and the "
    "ledger names the person who made it. Every grant made afterwards, by the steward or anybody "
    "else, goes through may_grant and is bounded by what its granter holds."
)

#: Why the same person must be said.
THE_SAME_PERSON_IS_A_CHOICE_SAID_OUT_LOUD: Final = (
    "The widest governance and the widest data reach in one account is a choice some companies "
    "make and nobody should make by accident. So an appointment says whether the steward is an "
    "administrator, that statement is checked against the one test of an administrator, and a "
    "statement either way that the resolver contradicts writes nothing."
)

#: Why there is one steward and the console does not replace one.
A_STEWARD_IS_APPOINTED_ONCE: Final = (
    "Replacing the data steward is not something this release does. It would have to decide what "
    "becomes of everything the first steward holds and everything they granted, and a replacement "
    "that quietly kept both would leave two roots of data access where the ledger names one. So an "
    "install appoints one steward, a second appointment writes nothing, and a steward whose "
    "appointment grant was retired is not replaced either."
)

#: Why a connection grants in its own transaction.
A_CONNECTION_GRANTS_THE_STEWARD_WHAT_THE_SOURCE_DECLARES: Final = (
    "A source connected with nobody able to grant its data is a source nobody can read, so what "
    "its manifest declares is granted to the steward, over everything, in the transaction that "
    "records the connection. A connection that fails grants nothing, and with no steward "
    "appointed a connection grants nothing and the appointment grants what every connected "
    "source declares."
)

#: Why the lock order is fixed.
THE_STEWARD_S_LOCK_COMES_BEFORE_THE_LEDGER_S: Final = (
    "Every grant row appends a ledger entry under the ledger's advisory lock, held to commit, and "
    "an appointment writes grants while holding the steward's lock. A connection that took the "
    "ledger's lock first and asked for the steward's second would wait for an appointment that "
    "waits for it, so every path takes the steward's lock before it writes anything."
)

#: Why disconnecting a source takes nothing away.
DISCONNECTING_A_SOURCE_TAKES_NOTHING_FROM_THE_STEWARD: Final = (
    "Entitlements are additive and revocation is the deliberate deletion of a grant. A "
    "disconnection that retired the steward's reads would be a second, silent path to revocation, "
    "and it would take away the reads somebody else was granted through the steward's authority "
    "only in the sense that the steward could no longer grant them again. So disconnecting retires "
    "nothing, and removing the steward's reads is done on the People screen, by a person."
)

#: Why a retired steward grant stays retired.
A_CAPABILITY_TAKEN_FROM_THE_STEWARD_IS_NOT_GIVEN_BACK: Final = (
    "A steward grant's id is derived from the steward and the capability, and every insert writes "
    "nothing on a conflict, so the retired row of a capability somebody took from the steward "
    "conflicts with the next attempt to grant it. Connecting a source again, or connecting another "
    "that declares the same entity, does not undo a revocation."
)

#: Why a manifest declares reads alone.
A_SOURCE_DECLARES_ITS_READS_AND_NEVER_A_WRITE: Final = (
    "Each entity a source's tools or projections reach is declared as the row capability and "
    "every field of it, which is what reading that entity takes. A write needs a write binding, "
    "which the manifest calls a separate deliberate grant naming somebody, and connecting a source "
    "is not that grant."
)

# --------------------------------------------------------------------- the figures

#: Who every steward grant names as its grantor: the appointment, and never a person. See
#: `AN_APPOINTMENT_IS_THE_PRODUCT_S_ACT_AND_NOBODY_GRANTS_PAST_THEIR_OWN_REACH`.
STEWARD_GRANTOR: Final = "data-steward-appointment"

#: The reason on the grants an appointment writes.
APPOINTMENT_REASON: Final = "data steward, appointed so this install's data access begins with them"

#: The reason on the grants a connected source's declarations write.
DECLARED_REASON: Final = "data steward, granted what a connected source declares"

#: The authority to grant, `brain.console.scoped_authority.REACH_AUTHORITY`. Written out because
#: this package must not import the console; a test holds the two equal.
GRANT_AUTHORITY: Final = "approve:grant"

#: The console's content plane, `brain.console.reads.plane_capability(Plane.CONTENT)`. Written out
#: for the same reason, and held equal by the same test.
CONTENT_PLANE: Final = "read:console.content"

#: What every steward holds from the moment of appointment, the content plane first.
APPOINTED_WITH: Final[tuple[str, ...]] = (CONTENT_PLANE, GRANT_AUTHORITY)

#: The namespace a steward grant's id is derived in. A constant of this product, never an install's.
STEWARD_GRANT_NAMESPACE: Final = uuid.UUID("f42229a1-1168-4be0-a400-e929a8607210")

#: The id of the steward's content-plane grant, the same on every install. The appointment's
#: record: see `A_STEWARD_IS_APPOINTED_ONCE`.
APPOINTMENT_GRANT_ID: Final = uuid.uuid5(STEWARD_GRANT_NAMESPACE, "the data steward's appointment")

#: The advisory lock every appointment and every connection takes before it writes. Its own number,
#: not the ledger's, first run's or an unlink's. See `THE_STEWARD_S_LOCK_COMES_BEFORE_THE_LEDGER_S`.
STEWARD_LOCK: Final = 8274419190

#: One principal's reach, from the one resolver.
_REACH: Final = text("SELECT gate.resolve_entitlements(:principal, :at)")


class StewardRefusal(enum.StrEnum):
    """Why no steward was appointed. Nothing was written for any of them."""

    #: A steward is appointed, or was and their appointment grant was retired.
    ALREADY_APPOINTED = "already_appointed"
    #: The person named is not a live human principal.
    NO_LIVE_PERSON = "no_live_person"
    #: The person named is an administrator, and the appointment did not say so.
    SAME_PERSON_UNSAID = "same_person_unsaid"
    #: The appointment said the steward is an administrator, and they are not one.
    NOT_AN_ADMINISTRATOR = "not_an_administrator"
    #: The person already holds part of a steward's reach narrower than everything, and two
    #: grants of one capability intersect, so they would be a steward who is not one.
    HOLDS_PART_ALREADY = "holds_part_already"


class StewardRefusedError(IdentityError):
    """No steward was appointed, for `reason`. The message names nobody."""

    def __init__(self, reason: StewardRefusal) -> None:
        self.reason = reason
        super().__init__(f"no data steward was appointed: {reason.value}")


@dataclass(frozen=True)
class NamedSteward:
    """Who an appointment names: a principal, the name a new one is written with, and the choice.

    `display_name` is what a new person is written with, which is a person setup or the console
    minted an id for, and is blank for somebody who must already be here: nothing is written for
    them, and an id nobody holds is refused. `same_as_administrator` is the separately stated
    choice `THE_SAME_PERSON_IS_A_CHOICE_SAID_OUT_LOUD` is about.
    """

    principal_id: str
    display_name: str
    same_as_administrator: bool


@dataclass(frozen=True)
class Appointed:
    """Who was appointed, and every capability the appointment wrote, in the order written."""

    principal_id: str
    granted: tuple[str, ...]


# ------------------------------------------------------------------------ the decisions


def declared_capabilities(manifest: ConnectorManifest) -> tuple[str, ...]:
    """What reading this source takes: each entity reached, as its row and every field, sorted.

    The row capability is `brain.knowledge.rows.entity_capability`'s spelling, which a test holds
    this to, and the field capability is its trailing wildcard, which `Capability.covers` expands
    to every field and never to the row. See `A_SOURCE_DECLARES_ITS_READS_AND_NEVER_A_WRITE`.
    """
    entities = {one.entity for one in manifest.tools} | {one.entity for one in manifest.projections}
    return tuple(
        sorted(value for entity in entities for value in (f"read:{entity}", f"read:{entity}.*"))
    )


def steward_grant_id(principal_id: str, capability: str) -> uuid.UUID:
    """The id of one steward grant. See `A_CAPABILITY_TAKEN_FROM_THE_STEWARD_IS_NOT_GIVEN_BACK`.

    The content plane's is the appointment's own, `APPOINTMENT_GRANT_ID`, whoever the steward is.
    """
    if capability == CONTENT_PLANE:
        return APPOINTMENT_GRANT_ID
    return uuid.uuid5(STEWARD_GRANT_NAMESPACE, f"{principal_id}\n{capability}")


def not_held_everywhere(
    reach: EntitlementSet, wanted: Iterable[str], now: datetime
) -> tuple[str, ...]:
    """Each capability in `wanted` this reach does not hold over everything, in `wanted`'s order."""
    missing: list[str] = []
    for one in wanted:
        scope = reach.scope_for(Capability(value=one), now)
        if scope is None or not scope.is_unrestricted():
            missing.append(one)
    return tuple(missing)


def refusal_for(*, administrator: bool, same_as_administrator: bool) -> StewardRefusal | None:
    """The refusal a stated choice earns against the resolver's judgement, or None when they agree.

    See `THE_SAME_PERSON_IS_A_CHOICE_SAID_OUT_LOUD`.
    """
    if administrator and not same_as_administrator:
        return StewardRefusal.SAME_PERSON_UNSAID
    if same_as_administrator and not administrator:
        return StewardRefusal.NOT_AN_ADMINISTRATOR
    return None


# ------------------------------------------------------------------- the statements


def steward_lock() -> Any:
    """The transaction lock every steward write takes first."""
    return text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=STEWARD_LOCK)


def grants_for(principal_id: str, capabilities: Sequence[str], *, reason: str) -> Any:
    """The insert of one steward's grants over everything, writing nothing on any conflict.

    Returns the capabilities written. `ON CONFLICT DO NOTHING` with no target, for the two
    conflicts `sign_in_binding.member_grant` names: a live grant of the capability, whose scope
    whoever wrote it chose, and the retired row of this steward's own grant of it.
    """
    everything = Scope.unrestricted().model_dump(mode="json")
    return (
        insert(CapabilityGrantRow)
        .values(
            [
                {
                    "id": steward_grant_id(principal_id, one),
                    "principal_id": principal_id,
                    "capability": one,
                    "scope": everything,
                    "granted_by": STEWARD_GRANTOR,
                    "reason": reason,
                }
                for one in capabilities
            ]
        )
        .on_conflict_do_nothing()
        .returning(CapabilityGrantRow.capability)
    )


async def steward_in(session: AsyncSession) -> str | None:
    """The appointed steward's principal id, or None. The policy hides a retired appointment."""
    found = await session.execute(
        select(CapabilityGrantRow.principal_id).where(
            CapabilityGrantRow.id == APPOINTMENT_GRANT_ID, CapabilityGrantRow.deleted_at.is_(None)
        )
    )
    return found.scalar_one_or_none()


async def declared_by_connections_in(session: AsyncSession) -> tuple[str, ...]:
    """What every live connection's manifest declares today, sorted and once each.

    A connection whose manifest this release cannot rebuild declares nothing here and is logged,
    for the reason `brain.console.connector_trust.connected_rows` shows it as unreadable rather
    than guessing at what it was connected as.
    """
    rows = (
        await session.execute(
            select(ConnectorConnectionRow.connector, ConnectorConnectionRow.settings).where(
                ConnectorConnectionRow.disconnected_at.is_(None)
            )
        )
    ).all()
    found: set[str] = set()
    for connector, settings in rows:
        given: Mapping[str, str] = {str(key): str(value) for key, value in dict(settings).items()}
        try:
            manifest = manifest_for(connector, given)
        except (NotConnectableError, ConnectorContractError) as unreadable:
            log.warning(
                "data_steward.declaration_unreadable",
                connector=connector,
                error=type(unreadable).__name__,
            )
            continue
        found.update(declared_capabilities(manifest))
    return tuple(sorted(found))


async def grant_declared_in(session: AsyncSession, declared: Sequence[str]) -> tuple[str, ...]:
    """Grant the steward what a source declares, in the caller's transaction, and say what was.

    Nothing with no steward appointed and nothing for an empty declaration. The caller has set who
    is acting, and has taken `steward_lock` before its own first write: see
    `THE_STEWARD_S_LOCK_COMES_BEFORE_THE_LEDGER_S`. Taken again here, which PostgreSQL grants at
    once to the transaction already holding it, so a caller that forgot still serialises.
    """
    await session.execute(steward_lock())
    steward = await steward_in(session)
    if steward is None or not declared:
        return ()
    written = await session.execute(grants_for(steward, declared, reason=DECLARED_REASON))
    return tuple(str(one) for one in written.scalars().all())


async def appoint_in(session: AsyncSession, named: NamedSteward, *, now: datetime) -> Appointed:
    """Appoint `named` as the data steward in the caller's transaction, or raise and write nothing.

    The caller owns the transaction and has set who is acting; a refusal raises, and the caller's
    transaction rolling back is what makes it write nothing, the principal a new person was given
    included. In order: the lock, a steward already live, the principal written when named with a
    name and read back live and human under a row lock, the stated choice against the resolver,
    then the appointment's row under its fixed id, every other grant, and the reach checked over
    everything.
    """
    await session.execute(steward_lock())
    if await steward_in(session) is not None:
        raise StewardRefusedError(StewardRefusal.ALREADY_APPOINTED)
    if named.display_name.strip():
        await session.execute(
            insert(PrincipalRow)
            .values(
                id=named.principal_id,
                kind=PrincipalKind.HUMAN.value,
                employment=Employment.STAFF.value,
                display_name=named.display_name.strip(),
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
    row = (
        (
            await session.execute(
                select(*COLUMNS).where(PrincipalRow.id == named.principal_id).with_for_update()
            )
        )
        .mappings()
        .one_or_none()
    )
    person: Principal | None = None if row is None else readable(dict(row))
    if person is None or person.kind is not PrincipalKind.HUMAN or not person.is_active(now):
        raise StewardRefusedError(StewardRefusal.NO_LIVE_PERSON)
    reach = entitlements_from(
        (await session.execute(_REACH, {"principal": named.principal_id, "at": now})).scalar_one()
    )
    refused = refusal_for(
        administrator=holds_everywhere(reach, now),
        same_as_administrator=named.same_as_administrator,
    )
    if refused is not None:
        raise StewardRefusedError(refused)
    declared = await declared_by_connections_in(session)
    appointment = await session.execute(
        grants_for(named.principal_id, (CONTENT_PLANE,), reason=APPOINTMENT_REASON)
    )
    granted = [str(one) for one in appointment.scalars().all()]
    if await steward_in(session) != named.principal_id:
        # Written nothing: a retired appointment holds the fixed id, or this person already holds
        # the content plane at a scope of its own.
        held = await session.execute(
            select(CapabilityGrantRow.id).where(
                CapabilityGrantRow.principal_id == named.principal_id,
                CapabilityGrantRow.capability == CONTENT_PLANE,
                CapabilityGrantRow.deleted_at.is_(None),
            )
        )
        if held.first() is not None:
            raise StewardRefusedError(StewardRefusal.HOLDS_PART_ALREADY)
        raise StewardRefusedError(StewardRefusal.ALREADY_APPOINTED)
    rest = (GRANT_AUTHORITY, *declared)
    written = await session.execute(grants_for(named.principal_id, rest, reason=APPOINTMENT_REASON))
    granted.extend(str(one) for one in written.scalars().all())
    after = entitlements_from(
        (await session.execute(_REACH, {"principal": named.principal_id, "at": now})).scalar_one()
    )
    if not_held_everywhere(after, (*APPOINTED_WITH, *declared), now):
        raise StewardRefusedError(StewardRefusal.HOLDS_PART_ALREADY)
    log.info("data_steward.appointed", principal=named.principal_id, granted=granted)
    return Appointed(principal_id=named.principal_id, granted=tuple(granted))


# ------------------------------------------------------------------------ the store


@dataclass(frozen=True)
class Steward:
    """The appointed steward as an administrator is told of them: an id and the name they go by."""

    principal_id: str
    display_name: str


@dataclass(frozen=True)
class DataStewards:
    """The console's appointment, for an install whose setup named no steward, and who it named."""

    sessions: async_sessionmaker[AsyncSession]

    async def steward(self) -> Steward | None:
        """Who the steward is, or None where nobody is appointed or the appointment was retired."""
        async with self.sessions() as session, session.begin():
            principal_id = await steward_in(session)
            if principal_id is None:
                return None
            name = (
                await session.execute(
                    select(PrincipalRow.display_name).where(PrincipalRow.id == principal_id)
                )
            ).scalar_one_or_none()
        return Steward(principal_id=principal_id, display_name=name or principal_id)

    async def appoint(
        self, named: NamedSteward, *, actor: str, ent_hash: str, trace_id: str, now: datetime
    ) -> Appointed:
        """Appoint in one transaction attributed to `actor`, or raise `StewardRefusedError`."""
        async with self.sessions() as session, session.begin():
            # The lock before the attribution and everything after it. See
            # `THE_STEWARD_S_LOCK_COMES_BEFORE_THE_LEDGER_S`.
            await session.execute(steward_lock())
            for statement in attributed_to(actor_id=actor, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            return await appoint_in(session, named, now=now)
