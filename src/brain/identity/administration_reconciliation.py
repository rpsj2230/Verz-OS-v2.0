"""Granting an appointed first administrator what was added after they were appointed.

**`appoint` grants what `GRANTED_AT_APPOINTMENT` held on the day it ran, and never again.** On
2026-09-16 `admin:session`, `admin:credential`, `admin:retention` and `admin:legal_hold` were all
added in one day, and the administrator on the owner's staging install, appointed before any of
them, held none: the screens behind them refused the one person who could open them, and nothing
in the console could put it right, because granting a capability is itself behind a capability.
The same day `OVERSIGHT` was added, and every administrator already appointed lacked all of it.
Nothing about that was particular to one install. Every install appointed before a capability was
added has it, and every release that adds one would make it again.

**This grants the difference, and it is additive only.** Entitlements have no deny list, so the
only safe repair is an insert, and an insert of what the principal does not hold: a capability
held already, at any scope and by any route, pack or wildcard included, is left as it is, because
two grants of one capability intersect and a second one could only ever narrow it. See
`A_HELD_CAPABILITY_IS_NOT_GRANTED_AGAIN`.

**It never grants a capability first run has granted before, and that is the load-bearing
refusal.** Revocation is the retirement of a grant. A reconciliation that granted every missing
capability on every start would undo every revocation of a first administrator's capability at
the next restart, with nothing anywhere saying so. The retired row cannot be read to tell a
revocation from an absence: `0045`'s policy shows the application role live rows only. The ledger
can be read, and `0003`'s trigger recorded every grant first run ever wrote, by capability and by
actor. So a capability the ledger records first run granting is never granted by this again, and
the price is stated rather than hidden: on an install whose first administrator was replaced
through a second setup code, a capability revoked from the first is not reconciled onto the
second, who received every capability that existed at their own appointment anyway. See
`A_CAPABILITY_TAKEN_AWAY_IS_NOT_GIVEN_BACK_AT_THE_NEXT_START`.

**Who it grants to is the finishing screen's own test, narrowed to first run.** A principal with a
live `admin:sign_in` grant written by first run, live at this instant, and whose resolved reach
holds that authority over everything, which is `holds_everywhere`. An administrator somebody made
by hand or through a pack has the grants their maker chose, and this is not the place to second
guess them. One held over one department is not an administrator, and is left alone too.

**Audited by the grant trigger, attributed to first run.** Every row is written with
`granted_by` first run and a reason of its own, and `0003`'s trigger appends a `grant` entry for
each with the actor set explicitly, as `appoint` sets it, and a trace naming this start. The
ledger then says the first administrator was granted a capability at a start, by first run,
which is what happened.

**Where it runs: at startup, in the lifespan, after the migrations and the installation
settings.** The release that adds a capability is then the release that grants it, read from the
code that is running. It takes `FIRST_RUN_LOCK`, the appointment's own, so it cannot interleave
with an appointment, and two processes starting together take turns and the second finds nothing
to do. It costs one lock and three reads on a start with nothing to grant. A failure is logged and
never stops the process, because an administrator missing a capability is a screen that refuses
and a process that will not start is every screen.

Rejected: a migration. A migration is frozen when it is written and does not import live code,
for the reason `0009` gives, so it would carry a copy of today's list, and the next capability
added without a migration of its own, which is every one of today's four, is the same defect
again. It would also run as the owner the migrations connect as, which reads past row-level
security, where this is an ordinary application write made exactly as `appoint` makes one.

Rejected: at sign-in. It puts a write, a lock and a ledger read on the path of every sign-in to
repair something that changes once per release, and an administrator who is signed in when the
release lands goes on being refused until they sign in again.

Rejected: a control on the console. The administrator who needs it is the one the console refuses,
and the capability to grant capabilities is the kind of thing that gets added in a release.

**A sign-in bound before binding granted a workspace is granted one at the next start.** Since
2026-09-17 `brain.identity.sign_in_binding.SignInBindings.bind` writes the member surface over a
person's own things in the binding's transaction, and every binding made before that holds nothing
of it, the first administrator's included. `reconcile_member_grants` writes the same row for each
live binding of a live principal, through the same `member_grant` statement, so the id is derived
from the binding and the two paths cannot write two grants. It reads no ledger and no reach: the
insert writes nothing over a live grant of the member surface and nothing over the retired row of
this binding's own member grant, which is how a revocation survives every later start. See
`sign_in_binding.A_MEMBER_GRANT_TAKEN_AWAY_IS_NOT_GIVEN_BACK_FOR_THE_SAME_BINDING`.

The price, stated rather than hidden: a person whose hand-written member grant was revoked, and
who never had the product's own, is granted the product's own once at the next start, because
the row that would remember a revocation is the one that was never written. Every binding from
this release on has the product's own row from the moment it is bound.

No lock, which `reconcile_first_administrators` takes. Two starts writing the same derived id wait
on each other's insert and the second writes nothing, so the key is the serialisation, and a start
reports only the rows its own inserts returned.

Task ids: M41.2.4, M42.5.6
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.entitlement import Capability, EntitlementSet
from brain.core.scope import Scope
from brain.firstrun import GRANTED_BY
from brain.gate.entitlement_store import entitlements_from
from brain.identity.first_administrator import (
    FIRST_RUN_LOCK,
    GRANTED_AT_APPOINTMENT,
    SIGN_IN_AUTHORITY,
    holds_everywhere,
)
from brain.identity.principal_directory import SIGN_IN_CHANNEL
from brain.identity.principal_store import COLUMNS, readable
from brain.identity.sign_in_binding import member_grant
from brain.tables.audit import ACTOR_SETTING, TRACE_ID_SETTING
from brain.tables.gate import CapabilityGrantRow
from brain.tables.identity import PrincipalRow

log = structlog.get_logger(__name__)

# ------------------------------------------------------------ written-down reasons

#: Why a capability first run ever granted is never granted again by this.
A_CAPABILITY_TAKEN_AWAY_IS_NOT_GIVEN_BACK_AT_THE_NEXT_START: Final = (
    "Revocation is the retirement of a grant and there is no deny list, so a reconciliation that "
    "granted whatever is missing would undo every revocation of a first administrator's "
    "capability at the next restart. A retired row is invisible to the application role, and the "
    "ledger is not: a capability it records first run granting is never granted by this again."
)

#: Why a capability held at any scope is left alone.
A_HELD_CAPABILITY_IS_NOT_GRANTED_AGAIN: Final = (
    "Two grants of one capability intersect, so a second grant can only narrow the first, and the "
    "table refuses a second live direct grant anyway. A capability held through a pack, a "
    "wildcard or a department's grant is held, and whoever wrote that grant chose its scope."
)

# --------------------------------------------------------------------- the figures

#: The reason on every row this writes, so a grant made at a start reads differently from one
#: made at the appointment.
RECONCILED_REASON: Final = (
    "first administrator, granted a capability added to the product after the appointment"
)

#: The prefix of the trace every start's reconciliation carries. A start's own id follows it.
TRACE_PREFIX: Final = "startup.reconcile."

#: Who holds a live `admin:sign_in` written by first run. The policy hides retired rows.
_FIRST_RUN_SIGN_IN_HOLDERS: Final = text(
    "SELECT DISTINCT g.principal_id FROM gate.capability_grant AS g"
    " WHERE g.capability = :capability AND g.granted_by = :first_run AND g.deleted_at IS NULL"
    " ORDER BY g.principal_id"
)

#: Every capability `0003`'s trigger has recorded first run granting. See
#: `A_CAPABILITY_TAKEN_AWAY_IS_NOT_GIVEN_BACK_AT_THE_NEXT_START`.
_EVER_GRANTED_BY_FIRST_RUN: Final = text(
    "SELECT DISTINCT e.details ->> 'capability' FROM obs.audit_entry AS e"
    " WHERE e.action = 'grant' AND e.actor_id = :first_run"
    " AND e.details ->> 'source' = 'capability_grant'"
)

#: One principal's reach, from the one resolver.
_REACH: Final = text("SELECT gate.resolve_entitlements(:principal, :at)")

#: Who a start's member grants are attributed to: the start, and never a person or first run.
MEMBER_RECONCILED_BY: Final = "startup.reconcile"

#: The reason on every member grant a start writes, so it reads unlike one a binding wrote.
MEMBER_RECONCILED_REASON: Final = (
    "their own workspace, granted at a start because their sign-in was bound before binding "
    "granted it"
)

#: Every live sign-in binding, oldest first. The policy hides retired rows.
_LIVE_BINDINGS: Final = text(
    "SELECT pi.id, pi.principal_id FROM auth.principal_identity AS pi"
    " WHERE pi.channel = :channel AND pi.deleted_at IS NULL"
    " ORDER BY pi.bound_at, pi.principal_id"
)


@dataclass(frozen=True)
class Reconciled:
    """What one start granted one first administrator. Capability names, never a scope."""

    principal_id: str
    granted: tuple[str, ...]


# ------------------------------------------------------------------------ the decision


def to_grant(
    wanted: Sequence[str],
    *,
    reach: EntitlementSet,
    live: bool,
    ever_granted: Collection[str],
    now: datetime,
) -> tuple[str, ...]:
    """The capabilities to grant one principal, in `wanted`'s order, or none.

    None for a principal who is not live or does not hold `SIGN_IN_AUTHORITY` over everything.
    Otherwise every capability in `wanted` that the reach does not hold at any scope and that first
    run has never granted. See the two named reasons.
    """
    if not live or not holds_everywhere(reach, now):
        return ()
    return tuple(
        one
        for one in wanted
        if one not in ever_granted and reach.scope_for(Capability(value=one), now) is None
    )


# ------------------------------------------------------------------------- the write


def _set_config(name: str, value: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


async def _live(session: AsyncSession, principal_id: str, now: datetime) -> bool:
    row = (
        (await session.execute(select(*COLUMNS).where(PrincipalRow.id == principal_id)))
        .mappings()
        .one_or_none()
    )
    principal = None if row is None else readable(dict(row))
    return principal is not None and principal.is_active(now)


async def reconcile_first_administrators(
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    trace_id: str,
    wanted: Sequence[str] = GRANTED_AT_APPOINTMENT,
) -> tuple[Reconciled, ...]:
    """Grant each appointed first administrator what `wanted` holds and they do not. Idempotent.

    One transaction under `FIRST_RUN_LOCK`. Returns what was granted, principal by principal,
    leaving out anybody granted nothing, so a start with nothing to do returns an empty tuple and
    logs that it looked.
    """
    granted: list[Reconciled] = []
    async with sessions() as session, session.begin():
        await session.execute(_set_config(ACTOR_SETTING, GRANTED_BY))
        await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": FIRST_RUN_LOCK})
        holders = (
            (
                await session.execute(
                    _FIRST_RUN_SIGN_IN_HOLDERS,
                    {"capability": SIGN_IN_AUTHORITY.value, "first_run": GRANTED_BY},
                )
            )
            .scalars()
            .all()
        )
        ever_granted = frozenset(
            str(one)
            for one in (
                await session.execute(_EVER_GRANTED_BY_FIRST_RUN, {"first_run": GRANTED_BY})
            )
            .scalars()
            .all()
            if one
        )
        everything = Scope.unrestricted().model_dump(mode="json")
        for principal_id in holders:
            reach = entitlements_from(
                (await session.execute(_REACH, {"principal": principal_id, "at": now})).scalar_one()
            )
            capabilities = to_grant(
                wanted,
                reach=reach,
                live=await _live(session, principal_id, now),
                ever_granted=ever_granted,
                now=now,
            )
            if not capabilities:
                continue
            await session.execute(
                insert(CapabilityGrantRow)
                .values(
                    [
                        {
                            "principal_id": principal_id,
                            "capability": one,
                            "scope": everything,
                            "granted_by": GRANTED_BY,
                            "reason": RECONCILED_REASON,
                        }
                        for one in capabilities
                    ]
                )
                .on_conflict_do_nothing(
                    index_elements=["principal_id", "capability"],
                    index_where=text("deleted_at IS NULL"),
                )
            )
            granted.append(Reconciled(principal_id=principal_id, granted=capabilities))
    log.info(
        "first_administrator.reconciled",
        administrators=len(holders),
        granted={one.principal_id: list(one.granted) for one in granted},
        trace_id=trace_id,
    )
    return tuple(granted)


async def reconcile_member_grants(
    sessions: async_sessionmaker[AsyncSession], *, now: datetime, trace_id: str
) -> tuple[str, ...]:
    """Grant every live binding's live principal their own workspace, once per binding. Idempotent.

    One transaction. Returns the principals a row was written for, in binding order, so a start
    with nothing to do returns an empty tuple and logs that it looked. A principal who is not live
    is skipped, because a binding outliving its person is an offboarding still in progress and not
    somebody to let into a workspace.
    """
    granted: list[str] = []
    async with sessions() as session, session.begin():
        await session.execute(_set_config(ACTOR_SETTING, MEMBER_RECONCILED_BY))
        await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
        bindings = (await session.execute(_LIVE_BINDINGS, {"channel": SIGN_IN_CHANNEL.value})).all()
        for binding_id, principal_id in bindings:
            if not await _live(session, principal_id, now):
                continue
            written = await session.execute(
                member_grant(
                    binding_id,
                    principal_id,
                    granted_by=MEMBER_RECONCILED_BY,
                    reason=MEMBER_RECONCILED_REASON,
                )
            )
            if written.first() is not None:
                granted.append(principal_id)
    log.info("member_grants.reconciled", bindings=len(bindings), granted=granted, trace_id=trace_id)
    return tuple(granted)


# ------------------------------------------------ the Super Admin role (M1.3.2)
#: What a first administrator's role grant says it is for.
SUPER_ADMIN_REASON: Final = "first administrator, recorded as Super Admin when role grants began"

#: The principals first run ever recorded as Super Admin, read off the ledger, so one removed is
#: not appointed again: `A_CAPABILITY_TAKEN_AWAY_IS_NOT_GIVEN_BACK_AT_THE_NEXT_START` for roles.
_EVER_APPOINTED_BY_FIRST_RUN: Final = text(
    "SELECT DISTINCT e.subject FROM obs.audit_entry AS e"
    " WHERE e.action = 'grant' AND e.actor_id = :first_run"
    " AND e.details ->> 'source' = 'role_grant' AND e.details ->> 'role' = 'super_admin'"
)


async def reconcile_super_admin_roles(
    sessions: async_sessionmaker[AsyncSession], *, now: datetime, trace_id: str
) -> tuple[str, ...]:
    """Record each live first administrator as Super Admin, once, if nothing records them yet.

    An install appointed before `0102` has administrators and no role grant, so the Roles screen
    would list nobody and the floor would count nobody. The same holders and the same test as
    `reconcile_first_administrators`, under the same lock; a principal the ledger shows first run
    appointing before is never appointed again, so a removal stays removed.
    """
    # Imported here: `brain.tables.role_grant` imports `brain.identity.roles`.
    from brain.identity.roles import Role
    from brain.tables.role_grant import RoleGrantRow

    appointed: list[str] = []
    async with sessions() as session, session.begin():
        await session.execute(_set_config(ACTOR_SETTING, GRANTED_BY))
        await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": FIRST_RUN_LOCK})
        holders = (
            (
                await session.execute(
                    _FIRST_RUN_SIGN_IN_HOLDERS,
                    {"capability": SIGN_IN_AUTHORITY.value, "first_run": GRANTED_BY},
                )
            )
            .scalars()
            .all()
        )
        ever = {
            str(one)
            for one in (
                await session.execute(_EVER_APPOINTED_BY_FIRST_RUN, {"first_run": GRANTED_BY})
            )
            .scalars()
            .all()
        }
        standing = set(
            (
                await session.execute(
                    select(RoleGrantRow.principal_id).where(
                        RoleGrantRow.role == Role.SUPER_ADMIN.value,
                        RoleGrantRow.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for principal_id in holders:
            if principal_id in standing or f"principal:{principal_id}" in ever:
                continue
            reach = entitlements_from(
                (await session.execute(_REACH, {"principal": principal_id, "at": now})).scalar_one()
            )
            if not (await _live(session, principal_id, now) and holds_everywhere(reach, now)):
                continue
            await session.execute(
                insert(RoleGrantRow).values(
                    principal_id=principal_id,
                    role=Role.SUPER_ADMIN.value,
                    granted_by=GRANTED_BY,
                    reason=SUPER_ADMIN_REASON,
                )
            )
            appointed.append(principal_id)
    log.info("first_administrator.super_admin_recorded", appointed=appointed, trace_id=trace_id)
    return tuple(appointed)
