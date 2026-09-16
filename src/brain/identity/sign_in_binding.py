"""Writing the row that lets a Keycloak subject sign in as a principal, and only on purpose.

`brain.identity.principal_directory.StoredDirectory` reads `auth.principal_identity` under
`SIGN_IN_CHANNEL` and nothing wrote a row there, so the day the token gate is wired every valid
token is refused as `NO_PRINCIPAL`. This module is the write, and it is the smallest one that
cannot hand a person to the wrong account: **an explicit binding of one subject at the configured
issuer to one live principal, made by somebody other than that principal, which never moves an
existing binding and never gives a principal a second one.**

**Why not bind at first sign-in by a verified email.** It is the shape most products ship, and
it was measured against this repository rather than assumed, and it fails three ways here.
There is nothing to match: `auth.principal` has no address column, and the realm's only client
scope, `brain-identity`, maps `groups` and `department` and deliberately no `email` claim
(`ops/keycloak/realm-export.json` records why). Building it means a migration adding a join of
addresses to principals, which `principal_identity` was written specifically not to hold. And
the match is the takeover `brain.identity.staff_address` already argues against in
`A_REISSUED_ADDRESS_INHERITS_WHOEVER_HELD_IT`: a leaver's address reissued to a joiner, with
the leaver's principal not yet offboarded, is a verified address matching exactly one live
principal, and the joiner signs in holding everything the leaver held. `email_verified` does
not help, because it proves the new holder receives mail at the address, which is exactly
what a reissue arranges, and because a realm administrator can set it by hand. See
`AN_ADDRESS_IS_NOT_A_SIGN_IN`.

**Why not bind when the directory sync creates the Keycloak user.** Nothing here creates
Keycloak users. The realm has `registrationAllowed` false and no process holds credentials for
Keycloak's admin API, and giving the application those credentials to do this would make every
defect in the application a way to mint accounts in the identity provider. Recorded as
rejected, not deferred: if the product ever provisions users, the subject Keycloak returns is
the input to `SignInBindings.bind`, and the rule below does not change.

**What remains is an administrator binding a subject they were given.** The subject is the
opaque uuid `bearer` records on every `NO_PRINCIPAL` refusal ("why can Priya not sign in" is
answered by that log line) and the user id Keycloak's own console shows. The subject is
compared exactly, because `subject_digest` does not fold and must not, so a padded or empty
subject is refused rather than trimmed into somebody else's. See
`A_SUBJECT_IS_BOUND_EXACTLY_AS_PRESENTED`.

**A binding never moves.** A subject already bound to one principal is refused for any other,
and a principal that already signs in is refused a second subject. Moving either is two
deliberate acts instead: retire the old binding, then bind the new one. The first refusal is
the one that matters, since a silent move is somebody signing in as whoever was bound last. The
second covers
a Keycloak account deleted and re-created, which gets a new `sub`; without it that is an
additional way in that nobody retires, and the old account's subject keeps working if the old
account comes back. See `A_BINDING_NEVER_MOVES`.

**Retiring was not built here until `0045`, because the application role could not do it.**
`0002`'s `principal_identity_live` policy hid a retired row with a USING that PostgreSQL also
checks against the new row of an UPDATE whose WHERE reads the table, so `brain_app` setting
`deleted_at` was refused whatever `WITH CHECK` said. `0045` repaired it for every soft-deleted
table, and `retire` is the store's half: it stamps the row with the retiring statement's own
instant, which is the one retired row the repaired read policy admits. See
`A_RETIREMENT_IS_STAMPED_BY_ITS_OWN_STATEMENT`.

**The issuer is not a parameter of the write.** `sign_in_bindings` reads `INSTALL_OIDC_ISSUER`
through `brain.install.value_of`, the same reader `keycloak_tokens.keycloak_authority` uses,
and refuses it through `keycloak_tokens.jwks_url_for`, the same check. So the issuer a binding
is written at is the issuer tokens are validated against, and a binding at another realm's
issuer cannot be written by a caller who has one to hand. See
`THE_BINDING_IS_MADE_AT_THE_CONFIGURED_ISSUER_ONLY`.

**Nobody binds their own sign-in.** The one who gains a way in is not the one who writes it,
for the reason `lifecycle.A_JOINER_IS_PROVISIONED_BY_SOMEBODY_ELSE` gives. It is a check on the
caller's word about who they are, and the route that calls this is where that word is proved.

**It decides in a pure function and writes under a lock.** `decide` holds every rule and no
connection. `SignInBindings.bind` reads the principal `FOR UPDATE`, so two binds for one
principal are serialised and cannot both see it unbound, and inserts with `ON CONFLICT DO
NOTHING` on the live-row unique index, so two binds of one subject to two principals cannot
both land: the second writes nothing and is refused as bound elsewhere. See
`THE_RACE_IS_LOST_BY_WRITING_NOTHING`.

**What a refusal says.** An administrator is told that a subject is held and never by whom:
the refusal names no principal but the one asked about. That is the DENIED-and-ABSENT
discipline applied to the one screen where the reader is entitled to most of the answer.

**Who did it is written by the database, in the same transaction.** `principal_identity` has no
column naming who bound a subject, and adding one would record it only for writes that go
through this module. `0047` puts a trigger on the table instead, which appends a `sign_in`
entry to `obs.audit_entry` for every sign-in binding and every retirement, from whatever wrote
it, and this module names the actor for it by setting `brain.actor_id` beside the write. A
binding that names nobody is refused by the database; a retirement that names nobody is
recorded as unattributed and never refused. See `A_WAY_IN_NAMES_WHO_MADE_IT` and
`A_WAY_OUT_IS_NEVER_REFUSED_FOR_WANT_OF_A_NAME`.

**Unlinking the last administrator who can sign in is refused, and the count is taken under a
lock.** M27.7.11 puts an unlink control on the Sign-in links screen. A binding is the only way
into a principal, and binding one needs an administrator signed in, so retiring the last binding
held by anybody who holds `SIGN_IN_AUTHORITY` over everything leaves an install nobody can sign
in to in order to link anybody, the person who pressed it included, with the setup wizard's
finishing screen long closed. `decide_unlink` is that rule and `SignInBindings.unlink` takes a
transaction-scoped advisory lock before it counts, so two administrators unlinking each other at
once are one unlink and one refusal rather than two unlinks and nobody. The count is
`first_administrator.holds_everywhere` over the one resolver's answer for every principal with a
live binding, which is `FirstAdministrators`' own argument for resolving rather than reading the
grant table. See `THE_LAST_WAY_IN_FOR_AN_ADMINISTRATOR_IS_NOT_TAKEN_AWAY`.

The callers are `brain.sign_in_routes`: an administrator's route, and the setup wizard's
finishing screen, which binds the first administrator's sign-in once and is the answer to how
anybody signs in to bind anybody at all; and `brain.session_routes`, which lists the bindings on
the Sign-in links screen and unlinks one.

Task ids: M1.2.2, M27.7.11
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.principal import Principal
from brain.gate.entitlement_store import entitlements_from
from brain.identity.first_administrator import holds_everywhere
from brain.identity.keycloak_tokens import jwks_url_for
from brain.identity.principal_directory import SIGN_IN_CHANNEL, subject_digest
from brain.identity.principal_store import COLUMNS, PRINCIPAL_SETTING, readable
from brain.identity.roles import IdentityError
from brain.install import value_of
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.identity import PrincipalIdentityRow, PrincipalRow

log = structlog.get_logger(__name__)

# ------------------------------------------------------------ written-down reasons

#: Why an address match at first sign-in is not how a subject is bound.
AN_ADDRESS_IS_NOT_A_SIGN_IN: Final = (
    "Companies reissue addresses on purpose. A leaver's address handed to a joiner is a "
    "verified address matching exactly one live principal, the leaver's, and binding on it "
    "signs the joiner in holding everything the leaver held. email_verified proves the new "
    "holder receives the mail, which is what a reissue arranges. And there is nothing to match "
    "here: auth.principal holds no address and the realm mints no email claim."
)

#: Why the subject is refused rather than trimmed.
A_SUBJECT_IS_BOUND_EXACTLY_AS_PRESENTED: Final = (
    "subject_digest compares a subject exactly, as validate_token compares the issuer. A "
    "subject that is empty or carries surrounding whitespace was not copied from a token, and "
    "trimming it binds a string that a token might carry for somebody else."
)

#: Why neither side of an existing binding is overwritten.
A_BINDING_NEVER_MOVES: Final = (
    "A subject bound to one principal is refused for another, and a principal that signs in is "
    "refused a second subject. Moving either is two acts, retire and then bind, so a binding "
    "cannot change hands as a side effect of somebody binding what they thought was unbound."
)

#: Why the issuer is read here rather than passed in.
THE_BINDING_IS_MADE_AT_THE_CONFIGURED_ISSUER_ONLY: Final = (
    "The issuer a binding is written at has to be the issuer tokens are validated against, and "
    "two values that must agree are one value read by one reader. A write taking the issuer as "
    "an argument is one wiring mistake from binding a subject at a realm this installation "
    "does not trust, which is a binding no token here can use today and one a second realm can "
    "use the day somebody configures it."
)

#: Why a retirement is stamped with `statement_timestamp()` and never `now()`.
A_RETIREMENT_IS_STAMPED_BY_ITS_OWN_STATEMENT: Final = (
    "0045's read policy admits a retired row only when deleted_at equals the running "
    "statement's start, which is how the retiring UPDATE passes the read check PostgreSQL "
    "applies to its new row. now() is the transaction's start, and a retirement stamped with it "
    "is refused as a row-level security violation."
)

#: Why a lost race is a refusal and not a fault or a second row.
THE_RACE_IS_LOST_BY_WRITING_NOTHING: Final = (
    "Two administrators binding one subject to two principals at once both read it unbound. The "
    "live-row unique index lets one insert land, and the other inserts nothing and is refused "
    "as bound elsewhere, which is what it would have been told a moment later."
)

#: Why the person gaining a sign-in is not the person writing it.
NOBODY_BINDS_THEIR_OWN_SIGN_IN: Final = (
    "A binding is a way into a principal. Written by that principal it is somebody vouching "
    "for their own second account, and a stolen administrator session could attach the thief's "
    "Keycloak account to the administrator's own principal without anybody else being asked."
)

#: Why the database refuses a binding with no actor named.
A_WAY_IN_NAMES_WHO_MADE_IT: Final = (
    "A binding is a new way into a principal, and the audit entry is the only record of who "
    "made it, because principal_identity has no column for that. A binding nobody is named "
    "for is the one an audit exists to find, so 0047's trigger refuses it, and an operator "
    "binding by hand sets brain.actor_id in the same transaction first."
)

#: Why the database never refuses a retirement with no actor named.
A_WAY_OUT_IS_NEVER_REFUSED_FOR_WANT_OF_A_NAME: Final = (
    "A retirement takes a way in away. Refusing an offboarding at midnight because a setting "
    "was not typed leaves the leaver signing in, which is the failure in the wrong direction, "
    "so it is recorded under the actor 'unattributed' and allowed."
)


#: Why an administrator's last way in is kept.
THE_LAST_WAY_IN_FOR_AN_ADMINISTRATOR_IS_NOT_TAKEN_AWAY: Final = (
    "A sign-in link is the only way into a principal, and making one needs an administrator "
    "signed in. Unlinking the last administrator who can sign in leaves nobody able to sign in to "
    "link anybody, including that administrator, and the setup wizard's finishing screen that "
    "made the first link closed the moment it did. So it is refused, the refusal says so, and "
    "the way round it is to link a second administrator first."
)

#: The advisory lock every unlink takes before it counts. Its own number, not the ledger's or
#: first run's.
UNLINK_LOCK: Final = 8274419102

#: Every principal with a live sign-in link, and the one resolver's answer for each.
_LINKED_REACHES: Final = text(
    "SELECT pi.principal_id, gate.resolve_entitlements(pi.principal_id, :at) "
    "FROM auth.principal_identity AS pi "
    "WHERE pi.channel = :channel AND pi.deleted_at IS NULL"
)


class BindingRefusal(enum.StrEnum):
    """Why a binding was not written. For the administrator and the log, never for a token."""

    SUBJECT_NOT_EXACT = "subject_not_exact"
    OWN_SIGN_IN = "own_sign_in"
    NO_LIVE_PRINCIPAL = "no_live_principal"
    SUBJECT_BOUND_ELSEWHERE = "subject_bound_elsewhere"
    PRINCIPAL_ALREADY_SIGNS_IN = "principal_already_signs_in"


class Binding(enum.StrEnum):
    """What a binding that was not refused amounted to."""

    BOUND = "bound"
    #: The same subject was already bound to the same principal. Nothing written, and not a
    #: refusal, so an administrator retrying a request that timed out is not told it failed.
    ALREADY_BOUND = "already_bound"


class SignInBindingRefusedError(IdentityError):
    """A binding refused for a named reason, with nothing in the message naming another person."""

    def __init__(self, reason: BindingRefusal, principal_id: str) -> None:
        self.reason = reason
        super().__init__(f"no sign-in bound to {principal_id!r}: {reason.value}")


def decide(
    subject: str,
    *,
    principal_id: str,
    bound_by: str,
    principal: Principal | None,
    subject_holder: str | None,
    principal_signs_in: bool,
    now: datetime,
) -> Binding:
    """Whether this subject may be bound to this principal, given what is bound already.

    `principal` is the live principal read for `principal_id`, or None. `subject_holder` is the
    principal the subject is bound to now, or None. `principal_signs_in` is whether the
    principal already holds a live sign-in binding. Raises `SignInBindingRefusedError`.

    The order is the argument. The subject's shape and the self-binding check need nothing
    read. Liveness comes before idempotence, so a retry for somebody disabled in between is
    told so rather than told all is well. And the subject's holder comes before the principal's
    own binding, so a subject that is somebody else's is always reported as that.
    """
    if not subject or subject != subject.strip():
        raise SignInBindingRefusedError(BindingRefusal.SUBJECT_NOT_EXACT, principal_id)
    if bound_by == principal_id:
        raise SignInBindingRefusedError(BindingRefusal.OWN_SIGN_IN, principal_id)
    if principal is None or not principal.is_active(now):
        raise SignInBindingRefusedError(BindingRefusal.NO_LIVE_PRINCIPAL, principal_id)
    if subject_holder is not None and subject_holder != principal_id:
        raise SignInBindingRefusedError(BindingRefusal.SUBJECT_BOUND_ELSEWHERE, principal_id)
    if subject_holder == principal_id:
        return Binding.ALREADY_BOUND
    if principal_signs_in:
        raise SignInBindingRefusedError(BindingRefusal.PRINCIPAL_ALREADY_SIGNS_IN, principal_id)
    return Binding.BOUND


class Unlinked(enum.StrEnum):
    """What asking to unlink a principal's sign-in came to."""

    UNLINKED = "unlinked"
    #: The principal holds no live sign-in link. Nothing written.
    NOT_LINKED = "not_linked"
    #: See `THE_LAST_WAY_IN_FOR_AN_ADMINISTRATOR_IS_NOT_TAKEN_AWAY`. Nothing written.
    LAST_ADMINISTRATOR = "last_administrator"


@dataclass(frozen=True)
class SignInLink:
    """One live sign-in link, as the Sign-in links screen lists it.

    No subject and no digest. The subject is not stored, which is this module's first rule, and
    the digest identifies nothing a person can check: it is a hash over the issuer and an
    account id, so showing it would be a column of noise that reads as though it were the
    account.
    """

    principal_id: str
    display_name: str
    department: str | None
    bound_at: datetime


def decide_unlink(
    principal_id: str, *, linked: Iterable[str], administrators: Iterable[str]
) -> Unlinked:
    """Whether this principal's link may be retired, given who is linked and who administers.

    `linked` is every principal with a live link and `administrators` those of them who hold
    `SIGN_IN_AUTHORITY` over everything. Pure, and taken under `UNLINK_LOCK` by the caller.
    A principal who is not linked is `NOT_LINKED` before anything else, so a stale press on a row
    already unlinked is told nothing was there rather than told it is the last administrator.
    """
    if principal_id not in set(linked):
        return Unlinked.NOT_LINKED
    held = set(administrators)
    if principal_id in held and not held - {principal_id}:
        return Unlinked.LAST_ADMINISTRATOR
    return Unlinked.UNLINKED


def _set_config(name: str, value: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


def _live_sign_ins() -> Any:
    return select(PrincipalIdentityRow.principal_id).where(
        PrincipalIdentityRow.channel == SIGN_IN_CHANNEL.value,
        PrincipalIdentityRow.deleted_at.is_(None),
    )


@dataclass(frozen=True)
class SignInBindings:
    """`auth.principal_identity` under `SIGN_IN_CHANNEL`, written. Build with `sign_in_bindings`."""

    sessions: async_sessionmaker[AsyncSession]
    issuer: str

    async def _holder(self, session: AsyncSession, digest: str) -> str | None:
        """The principal this digest is bound to now, or None."""
        query = _live_sign_ins().where(PrincipalIdentityRow.identity_hash == digest)
        return (await session.execute(query)).scalars().one_or_none()

    async def sign_ins(self) -> int:
        """How many live sign-in bindings this install holds.

        For the setup wizard's finishing screen, which is open only while this is zero, and
        never for a person to read: see `brain.sign_in_routes`.
        """
        async with self.sessions() as session, session.begin():
            counted = select(func.count()).select_from(_live_sign_ins().subquery())
            return int((await session.execute(counted)).scalar_one())

    async def bind(
        self,
        subject: str,
        *,
        principal_id: str,
        bound_by: str,
        now: datetime,
        ent_hash: str = "",
        trace_id: str = "",
    ) -> Binding:
        """Bind this subject at the configured issuer to this principal, or raise why not.

        `bound_by`, `ent_hash` and `trace_id` are set on the transaction for `0047`'s trigger,
        which writes the audit entry. An empty `ent_hash` or `trace_id` is recorded as the
        ledger's sentinel, as a grant's is. See `A_WAY_IN_NAMES_WHO_MADE_IT`.
        """
        digest = subject_digest(self.issuer, subject)
        async with self.sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, principal_id))
            await session.execute(_set_config(ACTOR_SETTING, bound_by))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            # Held to the end of the transaction, so a second bind for this principal waits
            # and then sees the first one's row.
            row = (
                (
                    await session.execute(
                        select(*COLUMNS).where(PrincipalRow.id == principal_id).with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            principal = None if row is None else readable(dict(row))
            signs_in = (
                await session.execute(
                    _live_sign_ins().where(PrincipalIdentityRow.principal_id == principal_id)
                )
            ).first() is not None
            outcome = decide(
                subject,
                principal_id=principal_id,
                bound_by=bound_by,
                principal=principal,
                subject_holder=await self._holder(session, digest),
                principal_signs_in=signs_in,
                now=now,
            )
            if outcome is Binding.BOUND:
                written = await session.execute(
                    insert(PrincipalIdentityRow)
                    .values(
                        channel=SIGN_IN_CHANNEL.value,
                        identity_hash=digest,
                        principal_id=principal_id,
                        bound_at=now,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["channel", "identity_hash"],
                        index_where=PrincipalIdentityRow.deleted_at.is_(None),
                    )
                    .returning(PrincipalIdentityRow.id)
                )
                if written.first() is None:
                    # See THE_RACE_IS_LOST_BY_WRITING_NOTHING.
                    raise SignInBindingRefusedError(
                        BindingRefusal.SUBJECT_BOUND_ELSEWHERE, principal_id
                    )
        log.info("sign_in.bound", principal=principal_id, bound_by=bound_by, outcome=outcome.value)
        return outcome

    async def links(self, *, limit: int) -> tuple[tuple[SignInLink, ...], bool]:
        """Every live sign-in link, by name, bounded, and whether the load came back full."""
        query = (
            select(
                PrincipalIdentityRow.principal_id,
                PrincipalRow.display_name,
                PrincipalRow.primary_department,
                PrincipalIdentityRow.bound_at,
            )
            .join(PrincipalRow, PrincipalRow.id == PrincipalIdentityRow.principal_id)
            .where(
                PrincipalIdentityRow.channel == SIGN_IN_CHANNEL.value,
                PrincipalIdentityRow.deleted_at.is_(None),
            )
            .order_by(PrincipalRow.display_name, PrincipalIdentityRow.principal_id)
            .limit(limit)
        )
        async with self.sessions() as session, session.begin():
            rows = (await session.execute(query)).all()
        return (
            tuple(
                SignInLink(
                    principal_id=principal_id,
                    display_name=display_name,
                    department=department,
                    bound_at=bound_at,
                )
                for principal_id, display_name, department, bound_at in rows
            ),
            len(rows) >= limit,
        )

    async def _linked_administrators(
        self, session: AsyncSession, now: datetime
    ) -> tuple[frozenset[str], frozenset[str]]:
        """Every linked principal, and those of them who administer, from the one resolver."""
        rows = (
            await session.execute(_LINKED_REACHES, {"at": now, "channel": SIGN_IN_CHANNEL.value})
        ).all()
        linked = frozenset(principal_id for principal_id, _ in rows)
        administrators = frozenset(
            principal_id
            for principal_id, payload in rows
            if holds_everywhere(entitlements_from(payload), now)
        )
        return linked, administrators

    async def administrators_linked(self, now: datetime) -> frozenset[str]:
        """Who among the linked principals holds `SIGN_IN_AUTHORITY` over everything, now."""
        async with self.sessions() as session, session.begin():
            _, administrators = await self._linked_administrators(session, now)
        return administrators

    async def unlink(
        self,
        principal_id: str,
        *,
        unlinked_by: str,
        now: datetime,
        ent_hash: str = "",
        trace_id: str = "",
    ) -> Unlinked:
        """Retire this principal's sign-in link, unless it is the last administrator's.

        Counted and written in one transaction under `UNLINK_LOCK`; see
        `THE_LAST_WAY_IN_FOR_AN_ADMINISTRATOR_IS_NOT_TAKEN_AWAY`. The actor, the reach's digest
        and the trace id are set for `0047`'s trigger, which writes the `sign_in` entry with the
        change `retired`. Stamped by the statement, for
        `A_RETIREMENT_IS_STAMPED_BY_ITS_OWN_STATEMENT`.
        """
        async with self.sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, principal_id))
            await session.execute(_set_config(ACTOR_SETTING, unlinked_by))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": UNLINK_LOCK})
            linked, administrators = await self._linked_administrators(session, now)
            outcome = decide_unlink(principal_id, linked=linked, administrators=administrators)
            if outcome is not Unlinked.UNLINKED:
                log.info("sign_in.unlink_refused", principal=principal_id, outcome=outcome.value)
                return outcome
            written = await session.execute(
                update(PrincipalIdentityRow)
                .where(
                    PrincipalIdentityRow.channel == SIGN_IN_CHANNEL.value,
                    PrincipalIdentityRow.principal_id == principal_id,
                    PrincipalIdentityRow.deleted_at.is_(None),
                )
                .values(deleted_at=func.statement_timestamp())
                .returning(PrincipalIdentityRow.id)
            )
            if written.first() is None:
                # Unreachable while the count above ran under the lock in this transaction: a
                # link it saw cannot have been retired by an unlink in between. A refusal rather
                # than an assertion, so a change to the lock fails as nothing written.
                return Unlinked.NOT_LINKED
        log.info("sign_in.unlinked", principal=principal_id, unlinked_by=unlinked_by)
        return Unlinked.UNLINKED

    async def retire(self, principal_id: str, *, retired_by: str) -> bool:
        """Retire this principal's sign-in binding, or return False when it has none.

        Whoever retires it is logged and not refused: a retirement takes a way in away, so the
        principal retiring their own is not the vouching `NOBODY_BINDS_THEIR_OWN_SIGN_IN` refuses.
        See `A_RETIREMENT_IS_STAMPED_BY_ITS_OWN_STATEMENT` for the stamp.
        """
        async with self.sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, principal_id))
            await session.execute(_set_config(ACTOR_SETTING, retired_by))
            written = await session.execute(
                update(PrincipalIdentityRow)
                .where(
                    PrincipalIdentityRow.channel == SIGN_IN_CHANNEL.value,
                    PrincipalIdentityRow.principal_id == principal_id,
                    PrincipalIdentityRow.deleted_at.is_(None),
                )
                .values(deleted_at=func.statement_timestamp())
                .returning(PrincipalIdentityRow.id)
            )
            retired = written.first() is not None
        log.info("sign_in.retired", principal=principal_id, retired_by=retired_by, retired=retired)
        return retired


def sign_in_bindings(
    sessions: async_sessionmaker[AsyncSession], *, env: Mapping[str, str] | None = None
) -> SignInBindings:
    """The bindings writer for this installation's issuer.

    See `THE_BINDING_IS_MADE_AT_THE_CONFIGURED_ISSUER_ONLY`. Raises for an unset issuer, and
    for one `jwks_url_for` refuses, so a writer that could only produce bindings no token will
    ever match is never built. `env` is for tests.
    """
    issuer = value_of("INSTALL_OIDC_ISSUER", env)
    jwks_url_for(issuer)
    return SignInBindings(sessions=sessions, issuer=issuer)
