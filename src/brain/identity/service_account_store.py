"""`auth.service_account` and `auth.api_key`: registering an integration, its keys, and finding one.

`brain.identity.sessions` decides what a service account may reach and `brain.channels.api_keys`
how a key is minted and checked. This holds the SQL between them and the request, and decides
nothing either decides, for the split CLAUDE.md names: nothing that decides policy owns a client.

**Every account belongs to the person who registered it, and every change is theirs.** The owner
column is the caller, never a field in a request: an account's reach is its owner's live reach
narrowed by its ceiling, so registering one in somebody else's name would be lending their reach
without asking them. The listing, a key, a revocation and a retirement all name the owner in the
statement's WHERE clause, so an account another person owns is not found, which is the same answer
as an account that does not exist. See `AN_ACCOUNT_IS_ITS_OWNERS_AND_NOBODY_ELSES`.

**Registering an account and issuing a key each leave a `credential` entry in the ledger.** The row
is `ops.credential_write`, whose `0054` trigger appends the entry in the same transaction, with the
slot `service_accounts/<client id>` and the writer on the row. A key's secret is never in either.

**A third live key is refused under the account's lock.** `api_keys.issue` refuses it given the
live keys, and the keys are read after the account row is locked, so two presses at once cannot each
see one key and each add a second.

Task ids: M1.1.7, M1.8.2
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import Select, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.channels.api_keys import ApiKeyError, ApiKeyRecord, IssuedKey, issue
from brain.core.entitlement import Capability
from brain.identity.sessions import ServiceAccount
from brain.ops.credential_write_store import written
from brain.tables.audit import ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.identity import PrincipalRow
from brain.tables.service_account import ApiKeyRow, ServiceAccountRow

#: Why the owner is the caller and is named in every statement.
AN_ACCOUNT_IS_ITS_OWNERS_AND_NOBODY_ELSES: Final = (
    "A service account acts at its owner's reach, so only its owner may make it, give it a key, "
    "take a key away or retire it. The owner is whoever registered it, and every statement names "
    "them, so another person's account is not found rather than refused."
)

#: The ledger slot an account's writes are recorded under. `brain.audit.record.CREDENTIAL_SLOT`.
SLOT_FAMILY: Final = "service_accounts"


def slot_for(client_id: str) -> str:
    """The credential slot the ledger names for this account."""
    return f"{SLOT_FAMILY}/{client_id}"


class Registered(enum.StrEnum):
    """What came of registering an account."""

    REGISTERED = "registered"
    #: The id or the identity provider subject is already somebody's, a principal's or an account's.
    TAKEN = "taken"


@dataclass(frozen=True)
class AccountListed:
    """One account its owner may see, with the handles and lapses of its live keys."""

    account: ServiceAccount
    label: str
    created_at: datetime
    keys: tuple[ApiKeyRecord, ...]


def account_from(row: Mapping[str, Any]) -> ServiceAccount:
    """A row as the type every rule is written against. Raises if the row does not construct."""
    return ServiceAccount(
        client_id=row["client_id"],
        subject=row["subject"] or row["client_id"],
        owner_principal_id=row["owner_principal_id"],
        ceiling=tuple(Capability(value=value) for value in row["ceiling"]),
        not_after=row["not_after"],
    )


def key_from(row: Mapping[str, Any]) -> ApiKeyRecord:
    return ApiKeyRecord(
        handle=row["handle"],
        client_id=row["client_id"],
        digest=row["digest"],
        issued_at=row["issued_at"],
        not_after=row["not_after"],
        label=row["label"],
    )


_ACCOUNT_COLUMNS: Final = (
    ServiceAccountRow.client_id,
    ServiceAccountRow.subject,
    ServiceAccountRow.owner_principal_id,
    ServiceAccountRow.ceiling,
    ServiceAccountRow.not_after,
    ServiceAccountRow.label,
    ServiceAccountRow.created_at,
)

_KEY_COLUMNS: Final = (
    ApiKeyRow.handle,
    ApiKeyRow.client_id,
    ApiKeyRow.digest,
    ApiKeyRow.issued_at,
    ApiKeyRow.not_after,
    ApiKeyRow.label,
)


def account_by_subject(subject: str) -> Select[Any]:
    """The live account an identity provider subject belongs to."""
    return select(*_ACCOUNT_COLUMNS).where(
        ServiceAccountRow.subject == subject, ServiceAccountRow.deleted_at.is_(None)
    )


def key_by_handle(handle: str) -> Select[Any]:
    """The live key with this handle and its live account, joined."""
    return (
        select(*_KEY_COLUMNS, *(c.label(f"account_{c.key}") for c in _ACCOUNT_COLUMNS))
        .join(ServiceAccountRow, ServiceAccountRow.client_id == ApiKeyRow.client_id)
        .where(
            ApiKeyRow.handle == handle,
            ApiKeyRow.deleted_at.is_(None),
            ServiceAccountRow.deleted_at.is_(None),
        )
    )


def owned_account(client_id: str, owner: str, *, lock: bool = False) -> Select[Any]:
    """One live account, only when this owner owns it; locked for a write when asked."""
    query = select(*_ACCOUNT_COLUMNS).where(
        ServiceAccountRow.client_id == client_id,
        ServiceAccountRow.owner_principal_id == owner,
        ServiceAccountRow.deleted_at.is_(None),
    )
    return query.with_for_update() if lock else query


def live_keys_of(client_ids: tuple[str, ...]) -> Select[Any]:
    return (
        select(*_KEY_COLUMNS)
        .where(ApiKeyRow.client_id.in_(client_ids), ApiKeyRow.deleted_at.is_(None))
        .order_by(ApiKeyRow.issued_at)
    )


def _set_config(name: str, value: str) -> Any:
    # Transaction-local, for `0054`'s trigger, as `brain.ops.credential_write_store` sets them.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


@dataclass(frozen=True)
class StoredServiceAccounts:
    """The two tables over this install's database, as the application role."""

    sessions: async_sessionmaker[AsyncSession]

    # -- the request path ---------------------------------------------------------------
    async def by_subject(self, subject: str) -> ServiceAccount | None:
        """The live account a client-credentials token's subject names, or None."""
        async with self.sessions() as session, session.begin():
            row = (await session.execute(account_by_subject(subject))).mappings().one_or_none()
        return None if row is None else account_from(dict(row))

    async def by_key(self, handle: str) -> tuple[ApiKeyRecord, ServiceAccount] | None:
        """The live key with this handle and the live account it speaks for, or None."""
        async with self.sessions() as session, session.begin():
            row = (await session.execute(key_by_handle(handle))).mappings().one_or_none()
        if row is None:
            return None
        found = dict(row)
        account = account_from({c.key: found[f"account_{c.key}"] for c in _ACCOUNT_COLUMNS})
        return key_from(found), account

    # -- the owner's own ----------------------------------------------------------------
    async def owned(self, owner: str, *, limit: int) -> tuple[tuple[AccountListed, ...], bool]:
        """The owner's live accounts, newest first, each with its live keys; and whether full."""
        async with self.sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(*_ACCOUNT_COLUMNS)
                        .where(
                            ServiceAccountRow.owner_principal_id == owner,
                            ServiceAccountRow.deleted_at.is_(None),
                        )
                        .order_by(ServiceAccountRow.created_at.desc())
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
            ids = tuple(row["client_id"] for row in rows)
            keys = (await session.execute(live_keys_of(ids))).mappings().all() if ids else []
        by_account: dict[str, list[ApiKeyRecord]] = {}
        for key in keys:
            by_account.setdefault(key["client_id"], []).append(key_from(dict(key)))
        listed = tuple(
            AccountListed(
                account=account_from(dict(row)),
                label=row["label"],
                created_at=row["created_at"],
                keys=tuple(by_account.get(row["client_id"], ())),
            )
            for row in rows
        )
        return listed, len(rows) >= limit

    async def register(
        self,
        account: ServiceAccount,
        *,
        subject: str | None,
        label: str,
        ent_hash: str,
        trace_id: str,
    ) -> Registered:
        """Write the account, owned by `account.owner_principal_id`, and its ledger entry.

        An id a principal already holds is taken, and so is one an account holds or a subject a
        live account holds; the database's key and index decide the last two under concurrency.
        """
        try:
            async with self.sessions() as session, session.begin():
                clash = await session.execute(
                    select(func.count())
                    .select_from(PrincipalRow)
                    .where(PrincipalRow.id == account.client_id)
                )
                if clash.scalar_one():
                    return Registered.TAKEN
                await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
                await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
                await session.execute(
                    insert(ServiceAccountRow).values(
                        client_id=account.client_id,
                        subject=subject,
                        owner_principal_id=account.owner_principal_id,
                        ceiling=[one.value for one in account.ceiling],
                        not_after=account.not_after,
                        label=label,
                        created_by=account.owner_principal_id,
                    )
                )
                await session.execute(
                    written(slot_for(account.client_id), account.owner_principal_id)
                )
        except IntegrityError:
            return Registered.TAKEN
        return Registered.REGISTERED

    async def issue_key(
        self,
        client_id: str,
        *,
        owner: str,
        not_after: datetime,
        label: str,
        now: datetime,
        ent_hash: str,
        trace_id: str,
    ) -> IssuedKey | None:
        """Mint a key for an account this owner owns, or None when it is not theirs or not live.

        Raises `ApiKeyError` for a third live key or a lapse already past, with the sentence
        `api_keys.issue` wrote, which the route answers as a 409 the owner can act on.
        """
        async with self.sessions() as session, session.begin():
            row = (
                (await session.execute(owned_account(client_id, owner, lock=True)))
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            account = account_from(dict(row))
            existing = (await session.execute(live_keys_of((client_id,)))).mappings().all()
            minted = issue(
                account,
                now=now,
                not_after=not_after,
                label=label,
                existing=tuple(key_from(dict(one)) for one in existing),
            )
            record = minted.record
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            await session.execute(
                insert(ApiKeyRow).values(
                    handle=record.handle,
                    client_id=record.client_id,
                    digest=record.digest,
                    issued_at=record.issued_at,
                    not_after=record.not_after,
                    label=record.label,
                    created_by=owner,
                )
            )
            await session.execute(written(slot_for(client_id), owner))
        return minted

    async def revoke_key(self, handle: str, *, owner: str) -> bool:
        """Retire one live key of an account this owner owns. False when there was none."""
        owned = select(ServiceAccountRow.client_id).where(
            ServiceAccountRow.owner_principal_id == owner,
            ServiceAccountRow.deleted_at.is_(None),
        )
        async with self.sessions() as session, session.begin():
            done = await session.execute(
                update(ApiKeyRow)
                .where(
                    ApiKeyRow.handle == handle,
                    ApiKeyRow.deleted_at.is_(None),
                    ApiKeyRow.client_id.in_(owned),
                )
                .values(deleted_at=func.statement_timestamp())
                .returning(ApiKeyRow.handle)
            )
            return done.first() is not None

    async def retire(self, client_id: str, *, owner: str) -> bool:
        """Retire an account this owner owns, and every live key it has. False when none."""
        async with self.sessions() as session, session.begin():
            row = (
                (await session.execute(owned_account(client_id, owner, lock=True)))
                .mappings()
                .one_or_none()
            )
            if row is None:
                return False
            await session.execute(
                update(ApiKeyRow)
                .where(ApiKeyRow.client_id == client_id, ApiKeyRow.deleted_at.is_(None))
                .values(deleted_at=func.statement_timestamp())
            )
            await session.execute(
                update(ServiceAccountRow)
                .where(ServiceAccountRow.client_id == client_id)
                .values(deleted_at=func.statement_timestamp())
            )
        return True


__all__ = [
    "AN_ACCOUNT_IS_ITS_OWNERS_AND_NOBODY_ELSES",
    "SLOT_FAMILY",
    "AccountListed",
    "ApiKeyError",
    "Registered",
    "StoredServiceAccounts",
    "account_from",
    "key_from",
    "slot_for",
]
