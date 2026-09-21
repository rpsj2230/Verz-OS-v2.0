"""Which identity-provider group confers which role, and what the sync has written, over HTTP.

The Roles screen's third section. An administrator maps a group, as the identity provider spells
it, to one of the six roles with a scope by name when the role needs one; `brain.identity.
group_sync` applies the rules at each sign-in and deletes what a retired rule conferred. Every
write runs `brain.govern_routes.attribution` first, so `0109`'s trigger names who changed the
mapping, at what reach, in which request.

**Mapping a group to a role is appointing everybody in it, so it takes the same authority.**
`brain.console.scoped_authority.within_reach` over `REACH_AUTHORITY` at the rule's scope, read as
the unrestricted scope for a company-wide role, exactly as `may_appoint_role` reads an
appointment. And never about oneself: a caller whose own token carries the group is refused,
for the reason `may_appoint_role` refuses an appointment of oneself.

**A group maps to a role and never to a pack.** A pack confers capabilities, and a capability
from the identity provider is what `brain.identity.oidc.CLAIMS_NEVER_GRANT` refuses; the body
has no field a pack fits into. The owner's task named "roles/packs", and that narrowing is put
to him as a question rather than decided here.

**Every refusal is one refusal**, the rule `brain.govern_routes` argues for grants, except the
duplicate group, which is said only to a caller who could otherwise have written the rule.

Task ids: M1.1.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.console.govern import Placed, role_holders
from brain.console.reads import permitted
from brain.console.scoped_authority import REACH_AUTHORITY, within_reach
from brain.console.screens import screen
from brain.core.department import ScopeRecord
from brain.core.errors import Absent, Failed
from brain.core.scope import Scope
from brain.core.scope_sql import PredicateRefusedError
from brain.govern_routes import REASON_CHARS, ROLES_SCREEN, attribution, one_live_scope
from brain.identity.group_sync import (
    SYNC_ACTOR,
    GroupRuleRecords,
    StoredGroupRules,
    rule_of,
)
from brain.identity.oidc import ClaimMapping, GroupRoleRule, map_claims
from brain.identity.roles import Role, RoleGrant
from brain.routing_routes import sessions_of
from brain.tables.group_role_rule import GROUP_CHARS
from brain.tables.identity import DirectoryRoleGrantRow

log = structlog.get_logger()

#: How many synced rows one answer is loaded from. A role is held by a handful of people.
MAX_SYNCED: Final = 500

#: Said to a caller who holds the authority and asked for a group that is already mapped.
ALREADY_MAPPED: Final = "that group already maps to a role; retire its rule first"


class RuleView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    idp_group: str
    role: str
    scope: dict[str, Any] | None
    created_by: str
    created_at: datetime


class SyncedView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    role: str
    source_group: str
    first_seen_at: datetime
    last_seen_at: datetime


class GroupRules(BaseModel):
    """The rules, and the synced grants this reader may see. No count of anybody left out."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rules: tuple[RuleView, ...]
    synced: tuple[SyncedView, ...]
    #: Whether this caller may change the mapping at all. Presentation only.
    editable: bool = False


class NewRule(BaseModel):
    """One group, one role, a scope by name when the role needs one, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    idp_group: str = Field(min_length=1, max_length=GROUP_CHARS)
    role: Role
    scope_slug: str | None = Field(default=None, min_length=2, max_length=60)
    reason: str = Field(min_length=1, max_length=REASON_CHARS)


class RuleRetirement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: uuid.UUID


class RuleChanged(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    change: str
    at: datetime


def _no_rule_change_here() -> Absent:
    return Absent("that group mapping is not writable by this caller")


def group_rules_of(request: Request) -> GroupRuleRecords:
    """`app.state.group_rules` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "group_rules", None)
    if isinstance(found, GroupRuleRecords):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredGroupRules(factory)


def may_map(rule: GroupRoleRule, asked: Asking) -> bool:
    """Whether this caller may add or retire a rule: the appointment authority, never oneself."""
    own = map_claims(asked.caller.claims, ClaimMapping()).groups
    if rule.group in own:
        return False
    return within_reach(asked.reach, REACH_AUTHORITY, rule.scope or Scope.unrestricted(), asked.now)


def rule_view(row: Any) -> RuleView:
    return RuleView(
        id=str(row.id),
        idp_group=row.idp_group,
        role=row.role,
        scope=row.scope,
        created_by=row.created_by,
        created_at=row.created_at,
    )


def synced_grant(row: DirectoryRoleGrantRow, rules: dict[str, GroupRoleRule]) -> RoleGrant | None:
    """A synced row as the grant it confers, with the scope from its rule, or None without one."""
    rule = rules.get(row.source_group)
    if rule is None or rule.role.value != row.role:
        return None
    return RoleGrant(
        principal_id=row.principal_id,
        role=rule.role,
        scope=rule.scope,
        granted_by=SYNC_ACTOR,
        reason=f"member of {row.source_group}",
        granted_at=row.created_at,
    )


router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get("/govern/roles/group-rules", response_model=GroupRules, responses=COMMON_RESPONSES)
async def group_rules(request: Request, asked: Asked) -> GroupRules:
    """The mapping, and the synced grants narrowed by `role_holders` over where each holder sits."""
    if not permitted(screen(ROLES_SCREEN).read, asked.reach, asked.now):
        raise Absent(f"the {ROLES_SCREEN} screen is not answerable for this caller")
    store = group_rules_of(request)
    rows = await store.rules()
    by_group: dict[str, GroupRoleRule] = {}
    for row in rows:
        try:
            by_group[row.idp_group] = rule_of(row)
        except (ValueError, ValidationError):
            log.warning("group rule does not construct", rule=str(row.id))
    placed: list[tuple[DirectoryRoleGrantRow, Placed[RoleGrant]]] = []
    for synced, department in await store.synced(MAX_SYNCED):
        grant = synced_grant(synced, by_group)
        if grant is None:
            continue
        where = {} if department is None else {"department": department}
        placed.append((synced, Placed(record=grant, where=where)))
    shown = {id(one) for one in role_holders([p for _, p in placed], asked.reach, asked.now)}
    return GroupRules(
        rules=tuple(rule_view(row) for row in rows if row.idp_group in by_group),
        synced=tuple(
            SyncedView(
                principal_id=row.principal_id,
                role=row.role,
                source_group=row.source_group,
                first_seen_at=row.created_at,
                last_seen_at=row.last_seen_at,
            )
            for row, one in placed
            if id(one) in shown
        ),
        editable=asked.reach.scope_for(REACH_AUTHORITY, asked.now) is not None,
    )


async def _scope_named(request: Request, slug: str | None) -> Scope | None:
    if slug is None:
        return None
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        row = (await session.execute(one_live_scope(slug))).scalar_one_or_none()
    if row is None:
        raise _no_rule_change_here()
    try:
        return ScopeRecord.from_predicate(
            row.slug, row.predicate, is_department=row.is_department, label=row.label
        ).scope
    except (ValueError, PredicateRefusedError):
        raise _no_rule_change_here() from None


@router.post(
    "/govern/roles/group-rules",
    response_model=RuleChanged,
    responses=COMMON_RESPONSES,
    status_code=201,
)
async def add_group_rule(request: Request, body: NewRule, asked: Asked) -> RuleChanged:
    """Map one group to one role. The sync applies it at each member's next sign-in."""
    if asked.reach.scope_for(REACH_AUTHORITY, asked.now) is None:
        raise _no_rule_change_here()
    scope = await _scope_named(request, body.scope_slug)
    try:
        rule = GroupRoleRule(group=body.idp_group.strip(), role=body.role, scope=scope)
    except (ValueError, ValidationError):
        raise _no_rule_change_here() from None
    if not rule.group or not may_map(rule, asked):
        raise _no_rule_change_here()
    stored = await group_rules_of(request).add(
        rule,
        reason=body.reason,
        created_by=asked.caller.principal.id,
        attributed=attribution(asked),
    )
    if stored is None:
        raise Absent(ALREADY_MAPPED, public_message=f"Nothing was changed: {ALREADY_MAPPED}")
    return RuleChanged(id=str(stored.id), change="mapped", at=stored.created_at)


@router.post(
    "/govern/roles/group-rules/retirement",
    response_model=RuleChanged,
    responses=COMMON_RESPONSES,
)
async def retire_group_rule(request: Request, body: RuleRetirement, asked: Asked) -> RuleChanged:
    """Retire one rule, and with it every synced grant it conferred."""
    if asked.reach.scope_for(REACH_AUTHORITY, asked.now) is None:
        raise _no_rule_change_here()
    store = group_rules_of(request)
    row = await store.one(body.rule_id)
    if row is None:
        raise _no_rule_change_here()
    try:
        rule = rule_of(row)
    except (ValueError, ValidationError):
        raise _no_rule_change_here() from None
    if not may_map(rule, asked):
        raise _no_rule_change_here()
    retired = await store.retire(body.rule_id, attributed=attribution(asked))
    if retired is None:
        raise _no_rule_change_here()
    at, _removed = retired
    return RuleChanged(id=str(body.rule_id), change="retired", at=at)
