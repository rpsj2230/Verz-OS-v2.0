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

**Retiring is not built here, because the application role cannot do it.** Measured, not
assumed: `0002`'s `principal_identity_live` policy is `USING (deleted_at IS NULL) WITH CHECK
(true)`, and PostgreSQL checks the new row of an UPDATE whose WHERE reads the table against the
USING expression as well, so setting `deleted_at` as `brain_app` is refused as a row-level
security violation whatever `WITH CHECK` says. `0003`'s comment believes the `WITH CHECK`
clause avoids exactly that, and it does not. So a binding is retired today by an operator's
statement, which fails closed: a principal refused a second subject stays refused until
somebody with the database does it. See `THE_APPLICATION_ROLE_CANNOT_RETIRE_A_LIVE_ROW`.

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

Not built here: the console route, which belongs in `brain.api_routes` behind the
administrator capability and must append the audit entry, since `principal_identity` has no
column recording who bound it. Not built either: the first administrator's binding. The setup
wizard appoints a principal with no Keycloak session in hand, so nobody can yet bind that
principal and nobody can sign in to bind anybody else. That is the owner's decision, and the
options are in the commit message that introduced this module.

Task ids: M1.2.2
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.principal import Principal
from brain.identity.keycloak_tokens import jwks_url_for
from brain.identity.principal_directory import SIGN_IN_CHANNEL, subject_digest
from brain.identity.principal_store import COLUMNS, PRINCIPAL_SETTING, readable
from brain.identity.roles import IdentityError
from brain.install import value_of
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

#: Why this module writes bindings and does not retire them.
THE_APPLICATION_ROLE_CANNOT_RETIRE_A_LIVE_ROW: Final = (
    "The live policy hides a retired row with USING (deleted_at IS NULL), and PostgreSQL "
    "applies that expression to the new row of an UPDATE that reads the table, so brain_app "
    "setting deleted_at is refused. A retire written here would pass every test that retires "
    "as the superuser and fail on the first real offboarding. The fix is a policy or a "
    "definer function, and it belongs to every soft-deleted table rather than to this one."
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

    async def bind(
        self, subject: str, *, principal_id: str, bound_by: str, now: datetime
    ) -> Binding:
        """Bind this subject at the configured issuer to this principal, or raise why not."""
        digest = subject_digest(self.issuer, subject)
        async with self.sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, principal_id))
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
