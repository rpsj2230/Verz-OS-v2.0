"""The identity provider's groups turned into synced role grants, and the rules that say how.

`auth.directory_role_grant` (`0006`) was built for a sync and nothing ever wrote it, and the
mapping from a group to a role (`brain.identity.oidc.GroupRoleRule`) existed only as a type
nobody configured. This module is both halves: the rules an administrator keeps on the Roles
screen (`auth.group_role_rule`, `0109`), and the sync that applies them to the groups a person's
verified token carries when they sign in.

**Entitlements are additive only, and this can only ever add.** A synced row is a second source
of a role beside `gate.role_grant`, and `brain.identity.directory.roles_held` unions the two. So
the sync writes and deletes rows in its own table and nowhere else: leaving a group deletes the
row that group conferred, and whether the person still holds the role is decided by whether any
other row says so. There is no deny row, no flag and no subtraction anywhere here. See
`ENTITLEMENTS_FROM_GROUPS_ARE_ADDITIVE_ONLY`.

**Revocation is the deletion of the synced grant, and it happens two ways.** When the person next
signs in without the group, `plan_for` is `directory.reconcile` over that person's rows, so the
delete set is a subset of what was read and nothing else. And when an administrator retires a
rule, every row that rule conferred is deleted in the same transaction, because a rule that no
longer exists asserts nothing for anybody, signed in or not. See
`RETIRING_A_RULE_REMOVES_WHAT_IT_CONFERRED`.

**The source is the token, read at sign-in, rather than a nightly read of the directory.** The
token is the identity provider's own signed statement of this person's groups at this moment, it
needs no second credential into the provider, and it is already verified by the time anything
here sees it. The cost, stated: somebody removed from a group who never signs in again keeps the
synced row until a rule retirement or their principal's removal takes it, and `last_seen_at`
on the Roles screen is how an administrator sees a row the sync has not confirmed lately. A
per-person run is the shape `directory.reconcile` rejects as the *only* sync, and it is not the
only one here: the rule retirement is the whole-set half.

**A token with no groups claim is a person in no group.** See
`A_SIGN_IN_WITHOUT_GROUPS_IS_A_PERSON_IN_NO_GROUP`.

**Nothing here decides who may change a rule.** That is the route's, through
`brain.console.scoped_authority`; this holds the statements, the lock and the plan.

Task ids: M1.1.5
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final, Protocol, runtime_checkable

import structlog
from sqlalchemy import TextClause, delete, func, insert, null, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.scope import Scope
from brain.identity.directory import DirectoryAssertion, Reconciliation, reconcile
from brain.identity.oidc import GroupRoleRule
from brain.identity.roles import IdentityError, Role
from brain.tables.audit import UNSUPPLIED_ENT_HASH, attributed_to
from brain.tables.group_role_rule import GroupRoleRuleRow
from brain.tables.identity import DirectoryRoleGrantRow, PrincipalRow

log = structlog.get_logger()

#: Who the ledger names for a row the sync wrote at somebody's sign-in. Nobody asked for it:
#: the directory asserted it. Held equal to `0109`'s copy by `tests/unit/test_group_sync.py`.
SYNC_ACTOR: Final = "directory_sync"

#: The advisory lock every write to the rules or the synced rows takes, so a sign-in applying a
#: rule and an administrator retiring it cannot interleave. Its own number.
GROUP_LOCK: Final = 8274419109

#: How long a person's unchanged groups are trusted before the sync reads the rules again. A
#: rule added on the Roles screen reaches somebody already signed in within this.
REFRESH_EVERY: Final = timedelta(minutes=5)

ENTITLEMENTS_FROM_GROUPS_ARE_ADDITIVE_ONLY: Final = (
    "A group adds a role and never takes one away. The sync writes and deletes rows in "
    "auth.directory_role_grant, which only it writes, and a hand-made grant in gate.role_grant "
    "is out of its reach by construction: no function here takes or returns one. Leaving a "
    "group deletes the row that group conferred, and the person keeps the role exactly when "
    "some other row still confers it."
)

RETIRING_A_RULE_REMOVES_WHAT_IT_CONFERRED: Final = (
    "A rule that no longer exists asserts nothing for anybody, so retiring it deletes every "
    "synced row carrying its group in the same transaction. Waiting for each person's next "
    "sign-in would leave the role with everybody who does not sign in again, which is the "
    "people a removal most needs to reach."
)

A_SIGN_IN_WITHOUT_GROUPS_IS_A_PERSON_IN_NO_GROUP: Final = (
    "The product's realm carries the groups mapper on every token (ops/keycloak/realm-export."
    "json), and the provider omits the claim for somebody in no group. Reading an absent claim "
    "as 'the provider said nothing' would mean leaving your last group never removes anything, "
    "which is the one failure this sync exists to prevent."
)


def rule_of(row: GroupRoleRuleRow) -> GroupRoleRule:
    """A stored rule as the type the mapping is written against."""
    return GroupRoleRule(
        group=row.idp_group,
        role=Role(row.role),
        scope=None if row.scope is None else Scope.model_validate(row.scope),
    )


def assertion_of(row: DirectoryRoleGrantRow) -> DirectoryAssertion:
    return DirectoryAssertion(
        principal_id=row.principal_id, role=Role(row.role), source_group=row.source_group
    )


def assertions_for(
    principal_id: str, groups: Iterable[str], rules: Sequence[GroupRoleRule]
) -> frozenset[DirectoryAssertion]:
    """What the rules say this person's groups confer. Compared exactly, as `GroupRoleRule` says."""
    by_group = {rule.group: rule for rule in rules}
    return frozenset(
        DirectoryAssertion(principal_id=principal_id, role=by_group[g].role, source_group=g)
        for g in set(groups)
        if g in by_group
    )


def plan_for(
    principal_id: str,
    groups: Iterable[str],
    rules: Sequence[GroupRoleRule],
    held: Iterable[DirectoryAssertion],
) -> Reconciliation:
    """What one person's sign-in should insert, delete and confirm.

    `held` must be this person's rows and nobody else's, and a row naming somebody else is
    refused rather than filtered: a caller that passed the whole table would otherwise propose
    deleting every other person's grants, since none of them is asserted by this token.
    """
    mine = frozenset(held)
    strangers = sorted({one.principal_id for one in mine if one.principal_id != principal_id})
    if strangers:
        msg = f"a sign-in reconciles one person's rows; these belong to {strangers}"
        raise IdentityError(msg)
    return reconcile(assertions_for(principal_id, groups, rules), mine)


def conferred_by(
    rule_group: str, held: Iterable[DirectoryAssertion]
) -> frozenset[DirectoryAssertion]:
    """The synced rows a rule for this group conferred, which its retirement deletes."""
    return frozenset(one for one in held if one.source_group == rule_group)


# ------------------------------------------------------------------ statements
def live_rules() -> Any:
    return (
        select(GroupRoleRuleRow)
        .where(GroupRoleRuleRow.deleted_at.is_(None))
        .order_by(GroupRoleRuleRow.idp_group)
    )


def synced_rows(limit: int) -> Any:
    """Every synced row and the department its holder sits in, for the Roles screen."""
    return (
        select(DirectoryRoleGrantRow, PrincipalRow.primary_department)
        .join(
            PrincipalRow,
            (PrincipalRow.id == DirectoryRoleGrantRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .order_by(DirectoryRoleGrantRow.role, DirectoryRoleGrantRow.principal_id)
        .limit(limit)
    )


def adding_rule(rule: GroupRoleRule, *, reason: str, created_by: str) -> Any:
    return (
        insert(GroupRoleRuleRow)
        .values(
            idp_group=rule.group,
            role=rule.role.value,
            # `null()`, not None, for `brain.identity.role_store.adding`'s reason.
            scope=null() if rule.scope is None else rule.scope.model_dump(mode="json"),
            created_by=created_by,
            reason=reason,
        )
        .returning(GroupRoleRuleRow)
    )


def retiring_rule(rule_id: uuid.UUID) -> Any:
    """`deleted_at` stamped by its own statement, which `0109`'s update policy requires."""
    return (
        update(GroupRoleRuleRow)
        .where(GroupRoleRuleRow.id == rule_id, GroupRoleRuleRow.deleted_at.is_(None))
        .values(deleted_at=func.statement_timestamp())
        .returning(GroupRoleRuleRow.deleted_at)
    )


def removing(one: DirectoryAssertion) -> Any:
    return delete(DirectoryRoleGrantRow).where(
        DirectoryRoleGrantRow.principal_id == one.principal_id,
        DirectoryRoleGrantRow.role == one.role.value,
        DirectoryRoleGrantRow.source_group == one.source_group,
    )


# ------------------------------------------------------------------ the store
@runtime_checkable
class GroupRuleRecords(Protocol):
    """What the Roles routes need, so a test can hand them one without a server."""

    async def rules(self) -> list[GroupRoleRuleRow]: ...

    async def synced(self, limit: int) -> list[tuple[DirectoryRoleGrantRow, str | None]]: ...

    async def one(self, rule_id: uuid.UUID) -> GroupRoleRuleRow | None: ...

    async def add(
        self,
        rule: GroupRoleRule,
        *,
        reason: str,
        created_by: str,
        attributed: Sequence[TextClause],
    ) -> GroupRoleRuleRow | None: ...

    async def retire(
        self, rule_id: uuid.UUID, *, attributed: Sequence[TextClause]
    ) -> tuple[datetime, int] | None: ...


@dataclass(frozen=True)
class StoredGroupRules:
    """`auth.group_role_rule` and `auth.directory_role_grant` over the application's pool."""

    sessions: async_sessionmaker[AsyncSession]

    async def _open(self, session: AsyncSession, attributed: Sequence[TextClause]) -> None:
        for statement in attributed:
            await session.execute(statement)
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": GROUP_LOCK})

    async def rules(self) -> list[GroupRoleRuleRow]:
        async with self.sessions() as session:
            return list((await session.execute(live_rules())).scalars())

    async def synced(self, limit: int) -> list[tuple[DirectoryRoleGrantRow, str | None]]:
        async with self.sessions() as session:
            return [(row, dept) for row, dept in await session.execute(synced_rows(limit))]

    async def one(self, rule_id: uuid.UUID) -> GroupRoleRuleRow | None:
        async with self.sessions() as session:
            found: GroupRoleRuleRow | None = (
                await session.execute(
                    select(GroupRoleRuleRow).where(
                        GroupRoleRuleRow.id == rule_id, GroupRoleRuleRow.deleted_at.is_(None)
                    )
                )
            ).scalar_one_or_none()
            return found

    async def add(
        self,
        rule: GroupRoleRule,
        *,
        reason: str,
        created_by: str,
        attributed: Sequence[TextClause],
    ) -> GroupRoleRuleRow | None:
        """Write one rule, or None when a live rule already maps this group."""
        try:
            async with self.sessions() as session, session.begin():
                await self._open(session, attributed)
                stored: GroupRoleRuleRow = (
                    await session.execute(adding_rule(rule, reason=reason, created_by=created_by))
                ).scalar_one()
                return stored
        except (IntegrityError, DBAPIError):
            return None

    async def retire(
        self, rule_id: uuid.UUID, *, attributed: Sequence[TextClause]
    ) -> tuple[datetime, int] | None:
        """Retire one rule and delete every synced row it conferred, in one transaction.

        Returns when it was retired and how many synced rows went with it, or None when there
        was no live rule. See `RETIRING_A_RULE_REMOVES_WHAT_IT_CONFERRED`.
        """
        async with self.sessions() as session, session.begin():
            await self._open(session, attributed)
            row = (
                await session.execute(
                    select(GroupRoleRuleRow)
                    .where(GroupRoleRuleRow.id == rule_id, GroupRoleRuleRow.deleted_at.is_(None))
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            held = [
                assertion_of(one)
                for one in (
                    await session.execute(
                        select(DirectoryRoleGrantRow).where(
                            DirectoryRoleGrantRow.source_group == row.idp_group
                        )
                    )
                ).scalars()
            ]
            gone = conferred_by(row.idp_group, held)
            for one in sorted(gone, key=_ordering):
                await session.execute(removing(one))
            at: datetime | None = (await session.execute(retiring_rule(rule_id))).scalar_one()
            if at is None:
                return None
            return at, len(gone)

    async def apply(
        self, principal_id: str, groups: Iterable[str], *, trace_id: str = ""
    ) -> Reconciliation:
        """Bring one person's synced rows into line with the groups their token carries.

        The rules and the person's rows are read under the lock, so a rule retired a moment ago
        is not re-applied from a stale read. The ledger names `SYNC_ACTOR`.
        """
        attributed = attributed_to(
            actor_id=SYNC_ACTOR, ent_hash=UNSUPPLIED_ENT_HASH, trace_id=trace_id
        )
        async with self.sessions() as session, session.begin():
            await self._open(session, attributed)
            rules = [rule_of(one) for one in (await session.execute(live_rules())).scalars()]
            held = [
                assertion_of(one)
                for one in (
                    await session.execute(
                        select(DirectoryRoleGrantRow).where(
                            DirectoryRoleGrantRow.principal_id == principal_id
                        )
                    )
                ).scalars()
            ]
            plan = plan_for(principal_id, groups, rules, held)
            for one in sorted(plan.to_delete, key=_ordering):
                await session.execute(removing(one))
            for one in sorted(plan.to_insert, key=_ordering):
                await session.execute(
                    insert(DirectoryRoleGrantRow).values(
                        principal_id=one.principal_id,
                        role=one.role.value,
                        source_group=one.source_group,
                        last_seen_at=func.now(),
                    )
                )
            if plan.unchanged:
                await session.execute(
                    update(DirectoryRoleGrantRow)
                    .where(
                        DirectoryRoleGrantRow.principal_id == principal_id,
                        DirectoryRoleGrantRow.source_group.in_(
                            sorted({one.source_group for one in plan.unchanged})
                        ),
                    )
                    .values(last_seen_at=func.now())
                )
            return plan


def _ordering(one: DirectoryAssertion) -> tuple[str, str, str]:
    """Statements in a fixed order, so two concurrent runs take row locks the same way round."""
    return (one.principal_id, one.role.value, one.source_group)


# ------------------------------------------------------------ at sign-in
class Applies(Protocol):
    async def apply(
        self, principal_id: str, groups: Iterable[str], *, trace_id: str = ""
    ) -> Reconciliation: ...


@dataclass
class GroupSync:
    """What `brain.identity.bearer.TokenAuthority` tells about each interactive sign-in.

    Remembers, per person, the groups last applied and when, so an unchanged token does not
    open a transaction on every request. A change of groups is applied at once; unchanged
    groups are applied again after `REFRESH_EVERY`, which is how a newly added rule reaches
    somebody already signed in. The memory is per process and holds group names only.
    """

    store: Applies
    trace: Callable[[], str] = lambda: ""
    seen: dict[str, tuple[frozenset[str], datetime]] = field(default_factory=dict)

    async def observe(self, principal_id: str, groups: Sequence[str], *, now: datetime) -> None:
        current = frozenset(groups)
        last = self.seen.get(principal_id)
        if last is not None and last[0] == current and now < last[1] + REFRESH_EVERY:
            return
        plan = await self.store.apply(principal_id, current, trace_id=self.trace())
        self.seen[principal_id] = (current, now)
        if not plan.is_empty:
            log.info(
                "group_sync.applied",
                principal=principal_id,
                added=len(plan.to_insert),
                removed=len(plan.to_delete),
            )
