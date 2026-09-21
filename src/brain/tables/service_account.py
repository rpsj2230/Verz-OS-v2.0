"""`auth.service_account` and `auth.api_key`: the API caller that is not a person, and its keys.

`brain.identity.sessions.ServiceAccount` has been a type since M1.1.7 was first written, and
`brain.channels.api_keys` a complete issue-verify-revoke module, and neither had anywhere to put a
row, so no install could ever authenticate a caller that was not a person. These two tables are
that somewhere. `migrations/versions/0095_service_accounts_and_partner_reach.py` builds them.

**No capability is granted to a service account, and there is no column that could hold one.**
`ceiling` is the list of capabilities it may exercise *if its owner holds them*, and it is only
ever intersected with the owner's live reach by `brain.identity.sessions.reach_for`. A service
account is not an `auth.principal`, so `gate.capability_grant`'s foreign key refuses a grant naming
one: holding no grant of its own is enforced by the database's referential integrity rather than by
a rule somebody has to remember. See `A_SERVICE_ACCOUNT_IS_NOT_A_PRINCIPAL`.

**The id carries its own prefix, and registering one a principal already holds is refused**
(`brain.identity.service_account_store`), so an account's id and a person's are never the same
string. The entitlement cache and the audit ledger both key on the id, and an integration recorded
under its owner's id, or a person resolved as an integration, is the confusion `reach_for` rebuilds
its answer under the account's own id to avoid.

**The owner is a foreign key and the expiry is not optional.** A service account owned by nobody is
one nobody reviews, and one with no end date is the credential made for one integration in 2026
still working in 2031. `ServiceAccount.not_after` is required on the type; the column says so too.

**A key is stored as a digest, and there is no column for the secret.** `ApiKeyRecord` argues it:
the secret is 256 bits shown once, the digest is sha256, and the comparison is constant time.

**Revocation is retirement.** Both tables carry `deleted_at`, and row-level security hides a retired
row from the application exactly as it hides a retired grant, so a revoked key is not found and a
retired account is not found, and the rows stay for whoever asks later what existed.

Task ids: M1.1.7, M1.8.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base, SoftDeleteMixin, TimestampMixin
from brain.tables.identity import DISPLAY_NAME_CHARS, PRINCIPAL_ID_CHARS

#: Why an account is its own table and never a principal row.
A_SERVICE_ACCOUNT_IS_NOT_A_PRINCIPAL: Final = (
    "A grant names a principal through a foreign key, so an account that is not a principal "
    "cannot be granted anything. Its reach is its owner's, narrowed by its ceiling, computed on "
    "each request; there is no row anywhere that could widen it."
)

#: Every service account id starts with this.
SERVICE_ACCOUNT_PREFIX: Final = "svc_"

#: `svc_` then a lower-case slug with no full stop or hyphen, so the id is also a segment of the
#: credential slot its ledger entries name (`brain.audit.record.CREDENTIAL_SLOT`). Anchored.
CLIENT_ID_PATTERN: Final = r"^svc_[a-z0-9][a-z0-9_]{1,62}$"

#: The widest a client id may be; the pattern bounds it well inside `PRINCIPAL_ID_CHARS`.
CLIENT_ID_CHARS: Final = PRINCIPAL_ID_CHARS

#: `ServiceAccount.subject` is `Field(max_length=200)`.
SUBJECT_CHARS: Final = 200

#: `Capability.value` is `Field(max_length=200)`, and so is `gate.capability_grant.capability`.
CAPABILITY_CHARS: Final = 200

#: A key's handle: `secrets.token_urlsafe(8)` is 11 characters; `KEY_RE` admits 6 to 32.
HANDLE_CHARS: Final = 32
HANDLE_PATTERN: Final = r"^[A-Za-z0-9_-]{6,32}$"

#: A sha256 in hex, which is `brain.channels.api_keys._digest`.
DIGEST_PATTERN: Final = r"^[0-9a-f]{64}$"

#: Free text an operator writes so an account or a key is identifiable in a list.
LABEL_CHARS: Final = DISPLAY_NAME_CHARS


class ServiceAccountRow(TimestampMixin, SoftDeleteMixin, Base):
    """`auth.service_account`. Mirrors `brain.identity.sessions.ServiceAccount` (M1.1.7)."""

    __tablename__ = "service_account"

    client_id: Mapped[str] = mapped_column(String(CLIENT_ID_CHARS), primary_key=True)
    #: The identity provider subject of the client's service-account user, when the account
    #: also authenticates with a client-credentials token. Null for an account used only through
    #: an API key, which is the one an administrator can make without touching the realm.
    subject: Mapped[str | None] = mapped_column(String(SUBJECT_CHARS), nullable=True)
    owner_principal_id: Mapped[str] = mapped_column(
        String(PRINCIPAL_ID_CHARS), ForeignKey("auth.principal.id"), nullable=False, index=True
    )
    ceiling: Mapped[list[str]] = mapped_column(ARRAY(String(CAPABILITY_CHARS)), nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    label: Mapped[str] = mapped_column(
        String(LABEL_CHARS), nullable=False, server_default=text("''")
    )
    created_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint(f"client_id ~ '{CLIENT_ID_PATTERN}'", name="client_id_shape"),
        CheckConstraint("cardinality(ceiling) > 0", name="ceiling_declared"),
        CheckConstraint("client_id <> owner_principal_id", name="not_its_own_owner"),
        CheckConstraint(
            "subject IS NULL OR length(btrim(subject)) > 0", name="subject_present_or_null"
        ),
        # One live account per identity provider subject, so a token names at most one.
        Index(
            "uq_service_account_live_subject",
            "subject",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND subject IS NOT NULL"),
        ),
        {"schema": "auth"},
    )


class ApiKeyRow(TimestampMixin, SoftDeleteMixin, Base):
    """`auth.api_key`. Mirrors `brain.channels.api_keys.ApiKeyRecord` (M1.8.2)."""

    __tablename__ = "api_key"

    handle: Mapped[str] = mapped_column(String(HANDLE_CHARS), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        String(CLIENT_ID_CHARS),
        ForeignKey("auth.service_account.client_id"),
        nullable=False,
        index=True,
    )
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    label: Mapped[str] = mapped_column(
        String(LABEL_CHARS), nullable=False, server_default=text("''")
    )
    created_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint(f"handle ~ '{HANDLE_PATTERN}'", name="handle_shape"),
        CheckConstraint(f"digest ~ '{DIGEST_PATTERN}'", name="digest_is_a_digest"),
        CheckConstraint("not_after > issued_at", name="lapses_after_issue"),
        {"schema": "auth"},
    )
