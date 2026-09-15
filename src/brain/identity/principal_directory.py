"""Who a verified token names, read from `auth.principal_identity` joined to `auth.principal`.

`brain.identity.bearer.TokenAuthority` needs an `oidc.PrincipalDirectory` and nothing implemented
one, so no deployed process could build `app.state.gate` even with a verifier for the signature.
This is that implementation. It holds the SQL and decides nothing about a token: by the time it
is asked, `oidc.validate_token` has already accepted the issuer, and whether an ended engagement
may sign in is `oidc.principal_for`'s, at the request's own instant.

**The subject is stored the way every other channel identity is: as a digest, under a channel.**
`principal_identity` has no issuer column and no subject column, and it was written that way on
purpose: its module refuses to hold a raw identity at all, and its check constraint pins the
column to sixty-four hex characters. So a sign-in identity is bound under `SIGN_IN_CHANNEL` with
the digest of its issuer and subject. Rejected: a migration adding `issuer` and `subject`
columns, which would make this the one row in the table holding the identity itself, and a
change to a table owned elsewhere for a lookup the existing columns already answer. Rejected: a
new `Channel` member, which every channel ceiling, traffic class and both check constraints
would have to learn, for something that is not a channel a message arrives on.

**The digest is not `ingress.identity_hash`, because that function casefolds.** A phone number or
an email address is the same identity in any case, and `identity_hash` is right to fold them.
An OIDC `sub` is a case-sensitive string by specification, and `validate_token` compares the
issuer exactly, so folding either would make two subjects one binding: a principal-confusion
defect that looks like a lookup working. See `A_SUBJECT_IS_COMPARED_EXACTLY`. The issuer is in
the digest, so a binding made for one issuer is not found for another, and the three parts are
length-prefixed so that no issuer and subject can be forged into a different pair.

**Every way of not being here is `None`, and the caller cannot tell them apart.** An unknown
subject, a subject bound at another issuer, a retired binding, a disabled principal and a
deleted one all return `None`, which `oidc.principal_for` turns into one `UnmappedSubject` and
`bearer` into one refusal. A directory that raised for a disabled account and returned `None`
for a stranger would let anybody holding a valid token for somebody else's old account learn
that the account exists here.

**Retired and deleted are decided in the query and by `principal_from`, not left to the policy.**
`0002`'s policies hide a retired binding and a deleted principal from the application role, and
a connection that is not that role bypasses both, so the query filters the binding's
`deleted_at` itself and the row goes through `principal_store.principal_from`, which refuses a
disabled or deleted principal whatever role read it.

**The transaction is not told a principal.** `principal_store` and `entitlement_store` set
`app.principal_id` so that a policy narrowing to the principal named lands without a store
change. This read is how a request learns which principal it is, so there is nobody to name
yet; see `THE_LOOKUP_THAT_FINDS_THE_PRINCIPAL_NAMES_NOBODY`.

Not built here: writing a binding. Provisioning a sign-in identity is
`brain.identity.lifecycle`'s, and until something writes rows under `SIGN_IN_CHANNEL` every
valid token is refused as an unmapped subject, which is the fail-closed direction.

Task ids: M1.2.2
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.principal import Principal
from brain.gate.context import Channel
from brain.identity.principal_store import COLUMNS, readable
from brain.tables.identity import PrincipalIdentityRow, PrincipalRow

# ------------------------------------------------------------ written-down reasons

#: Why the digest is not `ingress.identity_hash`.
A_SUBJECT_IS_COMPARED_EXACTLY: Final = (
    "An OIDC subject is case-sensitive and the issuer is compared exactly by validate_token. "
    "ingress.identity_hash casefolds, which is right for a phone number or an address and wrong "
    "here: two subjects differing only in case would share one binding, and whichever person "
    "was bound first would be signed in as whoever holds the other."
)

#: Why this read sets no principal on the transaction.
THE_LOOKUP_THAT_FINDS_THE_PRINCIPAL_NAMES_NOBODY: Final = (
    "The stores that set app.principal_id know whose rows they read. This one is asked who a "
    "subject is, so any value it set would be a guess, and a guess such as the subject itself "
    "is a principal id nobody has. A policy that narrowed principal_identity to the principal "
    "named would refuse every sign-in, and that should be found here rather than worked around."
)

# --------------------------------------------------------------------- the figures

#: The channel a sign-in identity is bound under. The console is where a person signs in to the
#: identity provider; a token without a session is the same person on `Channel.API`, and it is
#: the same binding, because the channel ceiling is `api_routes.channel_for`'s to decide and not
#: the directory's.
SIGN_IN_CHANNEL: Final = Channel.CONSOLE


def subject_digest(issuer: str, subject: str) -> str:
    """The `identity_hash` a subject at an issuer is bound under.

    Length-prefixed over the channel, the issuer and the subject, and never normalised. See
    `A_SUBJECT_IS_COMPARED_EXACTLY`. Whatever writes a binding must use this function, or it
    writes a row this directory will never find.
    """
    parts = (SIGN_IN_CHANNEL.value, issuer, subject)
    blob = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredDirectory:
    """`auth.principal_identity` joined to `auth.principal`, as an `oidc.PrincipalDirectory`."""

    sessions: async_sessionmaker[AsyncSession]

    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        """The live principal this subject at this issuer is bound to, or None."""
        query = (
            select(*COLUMNS)
            .select_from(PrincipalRow)
            .join(PrincipalIdentityRow, PrincipalIdentityRow.principal_id == PrincipalRow.id)
            .where(PrincipalIdentityRow.channel == SIGN_IN_CHANNEL.value)
            .where(PrincipalIdentityRow.identity_hash == subject_digest(issuer, subject))
            .where(PrincipalIdentityRow.deleted_at.is_(None))
        )
        async with self.sessions() as session, session.begin():
            # At most one row: `uq_principal_identity_channel_identity_hash_live` holds one live
            # binding per channel identity, so a second would be a fault and raises here.
            row = (await session.execute(query)).mappings().one_or_none()
        return None if row is None else readable(dict(row))
