"""The four govern screens over HTTP, and the two writes that put a grant in or take it out.

`brain.console.govern` ends with the sentence this module exists to make false: "No console
screen exists behind any of the eighteen." `brain.console.govern_surfaces` and
`brain.console.govern_estate` say the same of their own. So the disclosure decisions for
People, Roles, Capabilities and Scopes were written, argued and tested, and nothing outside
the process could reach one of them: `brain.ops.console_screens` counted them among
twenty-four console reads with no screen in a browser, which is its
`A_READ_NOBODY_CAN_OPEN_IS_A_SCREEN_NOBODY_HAS` measured rather than asserted.

**Nothing here decides who may see what, and that is the whole shape of the module.** Every
listing below is a load, a call into `brain.console`, and a projection of what came back.
`govern.people` decides which subjects appear and whether their capabilities may be named,
`govern.catalogue` decides whether the vocabulary is answered whole or not at all,
`govern_surfaces.scope_rows` and `govern_surfaces.departments_offered` decide which
predicates and which department names a reader may be shown, `scoped_authority.write_grant`
decides whether a grant may be written, and `govern.certify` decides whether one may be
removed. A route that filtered a row itself would be a second answer to a question those
modules already answer, and the second answer is the one nobody keeps in step. See
`THE_SCREEN_DECIDES_NOTHING_AND_THE_CONSOLE_MODULE_DECIDES_EVERYTHING`.

**Whether a screen opens is `brain.console.reads.permitted` and never a capability check of
this module's own.** That function asks two questions at once: the screen's tool capability,
which is what an agent making the same call would need, and the console plane, which is what
the console adds on top. A route asking only `reach.holds(...)` would answer an existence-only
reader a configuration screen, which is the distinction `Plane` exists to draw and the one a
hand-written check drops. `brain.routing_routes` checks a bare capability because the routing
matrix is not a registered console screen; these four are.

**The capability is checked before the database is looked at, and the order is the property.**
Straight from `brain.routing_routes`, restated because it is worth restating: a caller holding
no grant is refused identically on an instance with a database and on one without, so nobody
can read this deployment's state off the difference between a 404 and a 500. Every route below
asks its screen's question first and reaches for a session second, and
`test_a_caller_with_no_grant_cannot_tell_whether_this_process_has_a_database` moves the two
lines past each other.

**A grant listing that ignored pack assignments would be a screen that says somebody holds
nothing while they hold twelve things.** `gate.capability_pack_assignment` confers capabilities
exactly as `gate.capability_grant` does, and `brain.identity.packs.expand` is the only route
from a pack to the grants it means. So the People load reads both tables and expands the
second through that function rather than reading `capabilities` out of the pack row itself. A
screen built on the direct grants alone is the one an administrator grants against twice. See
`A_PEOPLE_SCREEN_BLIND_TO_PACKS_INVITES_THE_GRANT_THAT_IS_ALREADY_THERE`.

**This is not a second resolver and must never become one.** `brain.gate.entitlement_store`
says what one is and why there is exactly one: `gate.resolve_entitlements` answers "what does
this person hold", the audit trigger asks it on every entitlement write, and an assembly in
Python would be the copy that misses the next rule. What the People screen lists is *rows*,
which is a different question with a different answer: a lapsed grant is a row somebody wrote
and `govern.people` drops it, a disabled principal's row is still a row, and the resolver's
document has no subject on it to list. The load here is therefore deliberately a listing and
is never consulted about reach. See `LISTING_THE_GRANT_ROWS_IS_NOT_RESOLVING_A_REACH`.

**A grant is removed and never deleted, and the verb says so.** `brain.identity.packs.revoke`
is explicit that access goes away by the row that conferred it going away, and `SoftDeleteMixin`
is explicit that a row is retired rather than removed. The console's own `api/client.ts` has
no DELETE in its closed set of verbs and gives the reason: "nothing in this system hard-deletes
and a verb with no route behind it is a verb somebody eventually points at one." So removal is
`POST /govern/grants/removal`, which sets `deleted_at` and nothing else.

**And it names a subject and a capability rather than a row id, because the only screen that
lists grants has no id on it.** `govern.people` collapses a subject's grants on to one row and
argues for it: a capability granted twice appears once, since repeating it would say how many
grants stand behind it. A removal keyed on a row id would therefore be a write no browser could
reach, which is the same failure as a console read with no screen, arriving from the other
direction. The pair is what `brain.identity.packs.revoke_capability` matches on, exactly, and
the match is on the capability's own value rather than on `covers`: revoking `read:client.name`
must not delete a `read:client.*` grant that happens to imply it.

**The audit entry is written by a trigger, and this module's job is to be attributable rather
than to write one.** `migrations/versions/0003` creates `gate.record_entitlement_change` and
attaches it to `gate.capability_grant` for INSERT and UPDATE: an insert of a live row is
recorded as `grant`, an update that sets `deleted_at` is recorded as `revoke`, and the entry
carries what the resolver says the subject holds afterwards. The one thing the trigger cannot
work out is who did it, because `granted_by` is the granter and nothing on the row names the
remover; `brain.tables.audit.ACTOR_SETTING` is the session setting the application sets so it
does not have to guess. Both writes below set it, transaction-locally, in the same transaction
as the write. See `THE_TRIGGER_WRITES_THE_ENTRY_AND_THE_ROUTE_SAYS_WHO`.

**A grant is proposed at a named scope and never as a typed predicate.** The body carries a
`gate.scope` slug, which is resolved to that row's predicate; there is no field a browser can
put a clause list in. Two reasons and the second is the one that matters. A predicate typed
into a form is a predicate nobody named, so the review that reads it later has a clause list
and no word for it, which is
`govern_surfaces.A_SCOPE_NAME_IS_THE_PREDICATE_SPELLED_IN_WORDS` used in the direction it was
written for. And a slug is the same vocabulary the Scopes screen shows, so what a grantor may
choose from is a listing they have already been shown rather than a shape they invent. It
narrows nothing on its own: `scoped_authority.may_grant` is what refuses a scope wider than
the granter's, and a slug naming a scope out of their reach is refused there.

**Every refusal over a grant is one refusal.** A caller who may not write grants at all, a
grant id that is not there, a grant already retired, a scope slug nothing matches, a principal
who does not exist, and a subject who already holds the capability: six outcomes, one answer,
one sentence. The last two are the ones worth naming, because they are the ones a database
constraint would otherwise answer for us. `scoped_authority.write_grant` says it exactly:
the refusal "names nothing about the subject: whether the subject already holds this, whether
they exist, and whether somebody else has written the same grant are three facts about other
people and none of them changed the answer." An `IntegrityError` carrying a constraint name is
that disclosure arriving through the driver, so it is caught and answered as the same refusal.
See `A_CONSTRAINT_VIOLATION_IS_A_FACT_ABOUT_SOMEBODY_ELSE`.

Rejected: a route listing who holds each role. `brain.console.govern.role_holders` is written
and correct and there is no table behind it: `RoleGrant`'s own docstring says "the table is not
written here", `migrations/versions/0006` says `role_grant` is M1.3.2 and builds only
`auth.directory_role_grant`, and that migration's own docstring refuses to let the directory
table stand in for it. Building the holder listing out of what the directory asserts would put
a different fact under the same heading, and `RoleGrant` cannot honestly be constructed from a
directory row at all: there is no `granted_by` and no `reason` on one, and both are required
precisely so that a role grant is reviewable. So the Roles screen answers the catalogue, which
is the half that exists, and says nothing about holders rather than saying something else.

Rejected: a route listing who belongs to each team. `gate.team` exists and
`brain.identity.teams` builds the membership; what M27.7.4 also asks for is who belongs to
each, and a membership listing is a directory of people that `govern_surfaces.
A_LISTING_OF_DEPARTMENTS_IS_AN_ORG_CHART_A_REFUSAL_HANDED_OVER` would have to be argued about
separately, per member, against a reader's scope. The Scopes screen below answers the
predicates and the department names, which is M27.3.2's own decision made reachable. The
membership half is not built and is named here rather than implied.

Rejected: a `total` on any page. Inherited from `brain.api.Page` and never populated, for the
reason every list endpoint here gives, and it matters more on these than anywhere else: every
one of these listings *is* filtered per caller, so a count would be the subtraction `CLAUDE.md`
names. `truncated` says a page came back full, which is a fact with no arithmetic in it.

Rejected: mounting these on `brain.api_routes`. Its rules are about entities and enumeration.
The dependency is imported from there rather than re-declared, so there is one spelling of
`asking` and a route here cannot acquire a subtly different one.

**What has never run.** This repository has no PostgreSQL, so none of the statements below has
been executed against one. What is tested is the statement each one compiles to, every refusal
each route can produce, and the order the checks happen in. The insert's and the update's
success paths, and the audit entry the trigger writes behind them, are unverified and are the
first thing to exercise against a real database.

Task ids: M27.7.3, M27.7.4, M27.7.5, M27.7.6, M27.7.7
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Insert, Select, Update, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.api_routes import Asked
from brain.console.govern import (
    VOCABULARY_SCREEN,
    Decision,
    GovernError,
    Placed,
    catalogue,
    certify,
    people,
    role_catalogue,
)
from brain.console.govern_surfaces import SCOPES_SCREEN, departments_offered, scope_rows
from brain.console.read_replica import StalenessBanner
from brain.console.reads import permitted
from brain.console.scoped_authority import (
    REACH_AUTHORITY,
    AuthorityError,
    write_grant,
)
from brain.console.screens import screen
from brain.core.department import ScopeRecord
from brain.core.entitlement import CAPABILITY_RE, Capability
from brain.core.errors import Absent, Failed
from brain.core.scope import Scope
from brain.core.scope_sql import PredicateRefusedError
from brain.identity.packs import CapabilityPack, PackAssignment, SubjectGrant, expand
from brain.identity.roles import RoleSpec
from brain.identity.teams import PrincipalSubject
from brain.ops.replica_store import ConsoleReads
from brain.routing_routes import sessions_of
from brain.tables.audit import ACTOR_SETTING
from brain.tables.gate import (
    CapabilityGrantRow,
    CapabilityPackAssignmentRow,
    CapabilityPackRow,
    CapabilityRegistryRow,
    DepartmentRow,
    ScopeRow,
)
from brain.tables.identity import PrincipalRow

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why every route here is a load and a projection with no filtering of its own.
THE_SCREEN_DECIDES_NOTHING_AND_THE_CONSOLE_MODULE_DECIDES_EVERYTHING: Final = (
    "Which rows a governance screen shows is decided in brain.console, in a module with no "
    "connection, against a reader's own entitlement. Every route here loads rows, hands them "
    "to that decision and renders what comes back. A filter written in a route would be a "
    "second answer to the question the console module exists to answer, and the two would "
    "agree until somebody changed one of them; the copy that ships is the one in production."
)

#: Why the People load reads two tables rather than the obvious one.
A_PEOPLE_SCREEN_BLIND_TO_PACKS_INVITES_THE_GRANT_THAT_IS_ALREADY_THERE: Final = (
    "A pack assignment confers capabilities exactly as a direct grant does, and "
    "brain.identity.packs.expand is the only route from a pack to the grants it means. A "
    "People screen reading gate.capability_grant alone shows a person holding nothing when "
    "they hold everything their pack carries, and the administrator looking at that screen "
    "writes the grant again. So both tables are read and the assignments are expanded through "
    "that function, rather than the pack row's own array being read a second time here."
)

#: Why reading the grant tables here is not the second resolver this repository forbids.
LISTING_THE_GRANT_ROWS_IS_NOT_RESOLVING_A_REACH: Final = (
    "gate.resolve_entitlements answers what a principal holds and is the only thing that "
    "does; brain.gate.entitlement_store calls it and says why a Python assembly would be the "
    "copy that misses the next rule. This load answers a different question: which grant rows "
    "exist, written by whom, over what. A row is not a reach. Nothing here is consulted about "
    "whether anybody may do anything, and the day it is, it has become the second resolver."
)

#: Why the trigger writes the audit row and the route sets one session variable.
THE_TRIGGER_WRITES_THE_ENTRY_AND_THE_ROUTE_SAYS_WHO: Final = (
    "migrations/versions/0003 attaches gate.record_entitlement_change to gate.capability_grant "
    "for insert and update, so the audit entry is written by the database on every entitlement "
    "write however the write arrived, which is what a route-side append could never promise. "
    "The one fact the trigger cannot derive is the actor of a removal, because the row records "
    "who granted and nothing records who revoked; brain.tables.audit.ACTOR_SETTING is where the "
    "application says so. Set transaction-locally, because a session setting on a pooled "
    "connection is inherited by whoever borrows that connection next."
)

#: Why a driver-level integrity error is answered as the ordinary refusal.
A_CONSTRAINT_VIOLATION_IS_A_FACT_ABOUT_SOMEBODY_ELSE: Final = (
    "A foreign key refusing an unknown principal and a unique index refusing a capability the "
    "subject already holds live are both facts about another person, arriving through the "
    "driver with a constraint name attached. scoped_authority.write_grant refuses to disclose "
    "either in its own message and a 500 carrying the constraint name would disclose both. So "
    "an IntegrityError is answered with the same sentence a caller with no authority gets, and "
    "the difference between the six ways a grant write can fail stays inside the process."
)

#: Why one unreadable row is skipped rather than taking a whole screen away.
A_ROW_THE_TYPE_REFUSES_IS_A_ROW_AND_NOT_THE_END_OF_THE_SCREEN: Final = (
    "Two tables here admit rows the types that read them refuse: gate.scope holds a predicate "
    "ScopeRecord can reject as unsatisfiable, and gate.capability_pack.name is checked against "
    "a looser grammar than CapabilityPack.slug. Either is a configuration fault, and answering "
    "500 for one would hide every other row behind it from the person who came to fix it. The "
    "row is skipped, the log says which, and the response says nothing at all about it: a note "
    "reading one row was skipped is a count of what this reader was not shown, and it would be "
    "on the response whether the skip was a fault or a refusal."
)

#: Why a deep link resolves against the page rather than against a route of its own.
A_DEEP_LINK_RESOLVED_AGAINST_THE_PAGE_CANNOT_BE_AN_ORACLE: Final = (
    "A route answering one subject by id would answer, for anybody able to type one, whether "
    "that subject holds a grant this reader may not see, unless its refusal for out of reach "
    "and its refusal for not there were identical in every particular. The listing routes here "
    "have no such id to probe: a deep link is a segment the browser resolves against the page "
    "it already has, so a subject withheld and a subject that was never there produce one "
    "sentence about this page, written from rows the reader was already shown."
)

#: Why the removal route offers one decision and not both of a review round's.
ONLY_THE_HALF_OF_A_ROUND_THAT_HAS_A_ROW_TO_WRITE: Final = (
    "brain.console.govern.Decision has two members and this route accepts one. A KEEP is a "
    "decision somebody made and there is no certification table for it to be recorded in, so a "
    "route accepting one would answer 200 to a person who believes a round is now on the "
    "record when nothing was written anywhere. A REMOVE retires the row, which is a fact the "
    "database keeps and the audit trigger records. The missing half is a table, and it is M27.3.6."
)


# ----------------------------------------------------------------- the screens

#: The screen whose grant decides whether the people listing may be opened at all.
#:
#: A key rather than a capability spelled out, so that this cannot drift from the registry, and
#: the key is what `govern.people` itself asks `screen()` for when it narrows the rows.
PEOPLE_SCREEN: Final = "people"

#: The screen the role catalogue belongs to, on the same argument.
ROLES_SCREEN: Final = "roles"


# ------------------------------------------------------------------ the bounds

#: How many grant rows one page of the People screen carries at most. A resource bound rather
#: than a permission one: what a caller may see is decided per row by `govern.people`, and this
#: is only what one statement may ask the database for.
MAX_PEOPLE_PER_PAGE: Final = 500

#: What a caller gets when they do not say.
DEFAULT_PEOPLE_PER_PAGE: Final = 200

#: The same pair for the scopes listing. Lower, because a scope is written by a person and an
#: install with five hundred of them has a different problem from a paging one.
MAX_SCOPES_PER_PAGE: Final = 200
DEFAULT_SCOPES_PER_PAGE: Final = 100

#: The same pair for the vocabulary. Higher than the others, because the catalogue is answered
#: whole or not at all and a truncated whole is the one shape it must not take: see
#: `capabilities` below, which refuses rather than truncating.
MAX_CAPABILITIES_PER_PAGE: Final = 2000

#: How many department names a filter may be offered. `departments_offered` returns no count of
#: what it dropped, so this is a bound on the load and never on the answer.
MAX_DEPARTMENTS: Final = 500

#: The longest reason a grant may carry. The same bound `brain.identity.packs.SubjectGrant`
#: declares, restated so a body over it is a 422 naming the field rather than a `ValidationError`
#: from inside the model arriving as a 500. `test_govern_routes.py` holds the two together.
REASON_CHARS: Final = 500

#: How much of a pack's description becomes its label when a stored pack is read as a
#: `CapabilityPack`. `CapabilityPack.label` is bounded at this and `gate.capability_pack.
#: description` is unbounded `Text`, so a long description would otherwise refuse to construct
#: and take the whole People screen down over a sentence somebody wrote in a pack.
PACK_LABEL_CHARS: Final = 120


# ------------------------------------------------------------------- the shapes


class PersonView(BaseModel):
    """One grant subject and what this reader may be told they hold.

    The two fields `brain.console.govern.PersonRow` carries and no third. There is deliberately
    nothing saying whether the capabilities were withheld or absent: that module's
    `A_LIST_OF_SOMEBODY_ELSES_CAPABILITIES_IS_A_LIST_OF_CAPABILITIES` is explicit that a flag
    reading "withheld" would say this subject holds something, which is the disclosure the
    withholding was for.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    capabilities: tuple[str, ...]


class PeoplePage(Page[PersonView]):
    """The subjects this reader may see, as one page.

    `total` is inherited and never populated. This collection is filtered per caller, so a
    count would be exactly the subtraction the disclosure rule forbids, and the field is
    inherited rather than removed so that no page in this application answers one.
    """

    #: There is more. Never how much more.
    truncated: bool = False
    #: Whether this caller may write a grant at all. Presentation only; see
    #: `brain.routing_routes.AN_EDITABLE_FLAG_IS_PRESENTATION`, which this is a second use of.
    editable: bool = False
    #: How far behind the copy this page was read from is. Null when the primary answered.
    staleness: StalenessBanner | None = None


class RoleView(BaseModel):
    """One of the six roles, as the registry describes it.

    Every field is `brain.identity.roles.RoleSpec`'s, copied one at a time rather than dumped,
    for the reason `brain.routing_routes.view_of` gives about its own: a field added to the
    spec would otherwise arrive in a response because a copy loop was generous.

    There is no capability list here, in any arrangement. `govern.GOVERN_SURFACES` says why for
    this exact screen: "no role implies a capability and a table that put the two side by side
    would be read as though one did."
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: str
    #: `RoleSpec.exists_to`, under its own name rather than renamed to `purpose`. The registry
    #: owns the vocabulary, and a response renaming a field is a third word for one fact after
    #: the constant and the screen.
    exists_to: str
    #: How many people usually hold it. Prose from the same constant, and the reason it is worth
    #: carrying is that "one or two" beside Super Admin is the sentence that makes a reader
    #: notice there are nine.
    typical_count: str
    scope_required: bool


class RoleCatalogue(BaseModel):
    """The six roles, whole, or this response was never sent.

    No page, no cursor and no truncation flag. The catalogue is a constant of the product with
    six members, so a bound on it would be a bound on a literal, and `truncated` would be a
    field that is false in every install for ever.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    roles: tuple[RoleView, ...]
    #: What this screen says about who holds each role, which is nothing. See the module
    #: docstring: `role_grant` is M1.3.2 and the table does not exist.
    holders_are_not_recorded_yet: bool = True


class CapabilityView(BaseModel):
    """One capability of the vocabulary, and what holding it reaches.

    `description` is `gate.capability_registry.description`, which that table requires for the
    reason a grant's reason is required: an undescribed permission is one nobody can review.
    It is carried only for the capabilities `govern.catalogue` returned, so the decision about
    what may be named is still that function's and this adds nothing to its answer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: str
    description: str


class CapabilityCatalogue(BaseModel):
    """Everything that can be granted at all, or nothing at all.

    Whole or empty and never narrowed to what the reader holds, which is `govern.catalogue`'s
    decision and `A_CATALOGUE_FILTERED_TO_THE_READER_IS_THEIR_OWN_ENTITLEMENT_RELABELLED`'s
    argument. A reader without the grant gets an empty tuple rather than a refusal, because
    `navigation` has already left the screen out of their menu.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    capabilities: tuple[CapabilityView, ...]
    staleness: StalenessBanner | None = None


class ScopeView(BaseModel):
    """One named scope, whole, predicate included.

    Whole or absent, with no row carrying a blanked predicate: see
    `govern_surfaces.A_SCOPE_NAME_IS_THE_PREDICATE_SPELLED_IN_WORDS`. The predicate is passed
    through in `Scope.model_dump()`'s own shape rather than rendered into a sentence, which is
    `brain.routing_routes.RungView.scope`'s choice for the same reason: the structure already
    has a vocabulary and a second one would be this module inventing words for it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    label: str
    is_department: bool
    scope: dict[str, Any]


class ScopePage(Page[ScopeView]):
    """The scopes this reader may see, and the department names a filter may offer."""

    truncated: bool = False
    #: What `departments_offered` returned. A listing like any other, with no count of what it
    #: dropped, which is `brain.console.screens.offerable`'s rule rather than this module's.
    departments: tuple[str, ...] = ()
    staleness: StalenessBanner | None = None


class GrantProposal(BaseModel):
    """What a console may ask to be granted. Five fields, and no clause list among them.

    `extra="forbid"`, which is what turns "the console does not send a predicate" from a habit
    into an answer: a body carrying `scope`, `clauses` or `granted_by` is refused with a 422
    naming the key rather than accepted and quietly ignored. `granted_by` is the caller, taken
    from the token, and a body that could set it would be a grant attributable to whoever the
    browser named.

    `scope_slug` rather than a predicate. See the module docstring; the slug is resolved
    against `gate.scope` and the result is what `scoped_authority.may_grant` judges.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str = Field(min_length=1, max_length=128)
    #: Validated against the grammar here so a malformed one is a 422 naming the field rather
    #: than a `ValidationError` from inside `Capability` arriving as a 500.
    capability: str = Field(pattern=CAPABILITY_RE.pattern)
    scope_slug: str = Field(min_length=2, max_length=60)
    reason: str = Field(min_length=1, max_length=REASON_CHARS)
    #: When it lapses. Null is an unbounded grant, which `may_grant` permits only from a
    #: granter whose own reach is unbounded: see `scoped_authority._outlives`.
    not_after: datetime | None = None


class GrantView(BaseModel):
    """One grant row, as it now stands in the database.

    Returned from the stored row rather than echoed from the request, which is
    `brain.routing_routes.apply_edit`'s argument: `granted_at` is the database's clock and the
    id is the database's, and a console trusting its own request would render neither.

    There is no `holds` field and no summary of what the subject now reaches. That is the
    resolver's answer, the audit entry the trigger wrote carries it, and putting it on this
    response would be the second resolver arriving as a convenience.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    principal_id: str
    capability: str
    scope: dict[str, Any]
    granted_by: str
    reason: str
    granted_at: datetime
    not_after: datetime | None


class GrantRemoval(BaseModel):
    """Which grant to take away: a subject and a capability, and nothing else.

    `extra="forbid"`, so a body carrying a scope or a reason is refused rather than ignored.
    Neither is a thing a removal can carry: the scope is the stored row's and a reason has
    nowhere to be written, because there is no certification table. See
    `ONLY_THE_HALF_OF_A_ROUND_THAT_HAS_A_ROW_TO_WRITE`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str = Field(min_length=1, max_length=128)
    capability: str = Field(pattern=CAPABILITY_RE.pattern)


class GrantRemoved(BaseModel):
    """What a removal answers: what was retired, and when.

    The pair that was asked for, read back, and the instant the database wrote. Not the row. A
    retired grant rendered back to the person who retired it is a grant on a screen, and the
    next thing anybody builds on that is a listing of retired grants, which is a history of what
    other people used to be able to see.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    capability: str
    removed_at: datetime


# ---------------------------------------------------------------- the projections


def person_view(subject: str, capabilities: Sequence[str]) -> PersonView:
    """One row of `govern.people`, copied field by field."""
    return PersonView(subject=subject, capabilities=tuple(capabilities))


def role_view(spec: RoleSpec) -> RoleView:
    """One `RoleSpec`, copied field by field. See `RoleView` on why not a dump."""
    return RoleView(
        role=str(spec.role.value),
        exists_to=spec.exists_to,
        typical_count=spec.typical_count,
        scope_required=spec.scope_required,
    )


def scope_view(record: ScopeRecord) -> ScopeView:
    """One `ScopeRecord`, copied field by field."""
    return ScopeView(
        slug=record.slug,
        label=record.label,
        is_department=record.is_department,
        scope=record.scope.model_dump(),
    )


def grant_view(row: CapabilityGrantRow) -> GrantView:
    """One stored grant row, copied field by field.

    `created_at` is the grant's `granted_at`, because the table has no separate column for one
    and `TimestampMixin` is explicit that the value comes from the database's clock rather than
    from whichever container handled the write.
    """
    return GrantView(
        id=str(row.id),
        principal_id=row.principal_id,
        capability=row.capability,
        scope=row.scope,
        granted_by=row.granted_by,
        reason=row.reason,
        granted_at=row.created_at,
        not_after=row.not_after,
    )


# ---------------------------------------------------------------- the statements


def live_grants(limit: int) -> Select[tuple[CapabilityGrantRow, str | None]]:
    """Every live grant row and the department its subject sits in, at most `limit` of them.

    The department comes from `auth.principal.primary_department` and is what
    `govern.Placed.where` is built from: a grant carries a capability and a scope and says
    nothing about where its subject sits, which is exactly the gap `Placed` exists to fill.

    An outer join, so a grant whose principal row is missing is still a row. It arrives with no
    department, `govern.NOWHERE` is the empty mapping, and `Clause.matches` refuses a field that
    is not in the row, so such a grant reaches only a reader whose grant is company-wide. That
    is the fail-closed direction and it is the one `NOWHERE`'s own comment argues for; an inner
    join would drop the row instead, which fails closed in a way nobody can see.

    `deleted_at IS NULL` on both sides, written here as well as in the row-level policy, for the
    reason `brain.routing_routes.live_rungs` gives: a statement whose correctness depends on a
    policy being installed is wrong on a database restored without one.

    Ordered by principal then capability, so two readings of an unchanged table are the same
    page. `govern.people` sorts its own output, so this order is about which rows fall off the
    end of a truncated page rather than about what the screen shows.
    """
    return (
        select(CapabilityGrantRow, PrincipalRow.primary_department)
        .join(
            PrincipalRow,
            (PrincipalRow.id == CapabilityGrantRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .where(CapabilityGrantRow.deleted_at.is_(None))
        .order_by(CapabilityGrantRow.principal_id, CapabilityGrantRow.capability)
        .limit(limit)
    )


def live_assignments(
    limit: int,
) -> Select[tuple[CapabilityPackAssignmentRow, CapabilityPackRow, str | None]]:
    """Every live pack assignment, its pack, and the department its subject sits in.

    An inner join to the pack, unlike the principal join above, and the asymmetry is deliberate.
    `capability_pack_assignment.pack_id` is a foreign key with `ondelete="RESTRICT"`, so an
    assignment whose pack is gone cannot exist; a live assignment pointing at a *retired* pack
    can, and it is dropped here, because `expand` would otherwise produce grants from a bundle
    somebody withdrew. `principal_id` is a foreign key too, so the outer join above is about a
    soft-deleted principal rather than a missing one, and a retired person's grant row is still
    a row an access review has to see.
    """
    return (
        select(
            CapabilityPackAssignmentRow,
            CapabilityPackRow,
            PrincipalRow.primary_department,
        )
        .join(
            CapabilityPackRow,
            (CapabilityPackRow.id == CapabilityPackAssignmentRow.pack_id)
            & (CapabilityPackRow.deleted_at.is_(None)),
        )
        .join(
            PrincipalRow,
            (PrincipalRow.id == CapabilityPackAssignmentRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .where(CapabilityPackAssignmentRow.deleted_at.is_(None))
        .order_by(
            CapabilityPackAssignmentRow.principal_id,
            CapabilityPackAssignmentRow.pack_id,
        )
        .limit(limit)
    )


def live_scopes(limit: int) -> Select[tuple[ScopeRow]]:
    """Every live scope, in slug order, at most `limit` of them."""
    return (
        select(ScopeRow).where(ScopeRow.deleted_at.is_(None)).order_by(ScopeRow.slug).limit(limit)
    )


def live_departments(limit: int) -> Select[tuple[str]]:
    """Every live department's slug, in slug order.

    The slug rather than the name, because the slug is the value a `department` clause carries
    and therefore the value `admits_department` asks its satisfiability question about. Offering
    the display name would offer a word no scope, no grant and no query uses.
    """
    return (
        select(DepartmentRow.slug)
        .where(DepartmentRow.deleted_at.is_(None))
        .order_by(DepartmentRow.slug)
        .limit(limit)
    )


def live_capabilities(limit: int) -> Select[tuple[CapabilityRegistryRow]]:
    """Every registered capability, in capability order.

    `gate.capability_registry` rather than a list assembled from the grants, because that table
    is the statement that a capability was meant to exist: its own docstring says a typo in a
    grant and a permission somebody deliberately created are otherwise the same row. A
    catalogue built from what people hold would be a catalogue of typos.
    """
    return (
        select(CapabilityRegistryRow)
        .where(CapabilityRegistryRow.deleted_at.is_(None))
        .order_by(CapabilityRegistryRow.capability)
        .limit(limit)
    )


def one_live_scope(slug: str) -> Select[tuple[ScopeRow]]:
    """The live scope with this slug, or nothing.

    `uq_scope_slug_live` makes this at most one row, and the `deleted_at IS NULL` here is what
    makes that index the relevant one: a retired slug may have been reused.
    """
    return select(ScopeRow).where(ScopeRow.slug == slug, ScopeRow.deleted_at.is_(None)).limit(1)


def one_live_grant(
    principal_id: str, capability: str
) -> Select[tuple[CapabilityGrantRow, str | None]]:
    """One live grant and the department its subject sits in, for a removal to judge.

    **Named by subject and capability rather than by row id, and the reason is the screen.**
    `govern.people` builds a row per subject with the capabilities collapsed on to it, and its
    docstring says why a capability granted twice appears once: repeating it would say how many
    grants stand behind it, which is a count of rows the reader was never shown one at a time.
    So the only listing of grants a person can open carries no grant id, and a removal keyed on
    one would be a write nothing could reach: the same shape as the console read with no screen
    that this whole module is answering. The pair is also exactly what
    `brain.identity.packs.revoke_capability` matches on, so the two spellings of "remove this
    person's grant of this capability" agree.

    Exact on the capability and never `covers`, which is that function's rule and worth
    restating: revoking `read:client.name` must not delete a `read:client.*` grant that happens
    to imply it, because those are different decisions made by possibly different people.

    `uq_capability_grant_principal_id_capability_live` makes this at most one row. The same
    outer join and the same fail-closed argument as `live_grants`. A grant already retired
    matches nothing, which is what makes a second removal the same refusal as a first one
    against a pair nobody holds.
    """
    return (
        select(CapabilityGrantRow, PrincipalRow.primary_department)
        .join(
            PrincipalRow,
            (PrincipalRow.id == CapabilityGrantRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .where(
            CapabilityGrantRow.principal_id == principal_id,
            CapabilityGrantRow.capability == capability,
            CapabilityGrantRow.deleted_at.is_(None),
        )
        .limit(1)
    )


def add_grant(proposed: SubjectGrant, principal_id: str) -> Insert:
    """The INSERT for one grant, naming only what the row holds.

    `granted_at` is not among the values. The column does not exist: `TimestampMixin.created_at`
    is the grant's instant and it is `func.now()`, from the database's clock. Passing the
    request's `now` would be the application's clock landing in a column an audit reads, which
    is the drift that mixin exists to prevent.

    `returning` the row, so the response is what the database holds rather than what was asked
    for, which is `apply_edit`'s argument one route across and matters more here: the id and the
    instant are both the database's and neither is in the request.

    `principal_id` is passed separately rather than read off `proposed.subject`, because
    `SubjectGrant.subject` is a `GrantSubject` and may be a team, and `gate.capability_grant`
    has no column for one. The caller is what narrows it to a principal; see `proposal_from`.
    """
    return (
        insert(CapabilityGrantRow)
        .values(
            principal_id=principal_id,
            capability=proposed.capability.value,
            scope=proposed.scope.model_dump(),
            granted_by=proposed.granted_by,
            reason=proposed.reason,
            not_after=proposed.not_after,
        )
        .returning(CapabilityGrantRow)
    )


def retire_grant(principal_id: str, capability: str, at: datetime) -> Update:
    """The UPDATE that removes one grant. `deleted_at`, and nothing else.

    The same pair `one_live_grant` selects on and for its reasons, including the exact match on
    the capability rather than `covers`.

    `deleted_at IS NULL` in the WHERE clause as well, so a second removal writes nothing and is
    answered identically to a first one against a pair nobody holds. Without it the second would
    update zero rows anyway and the trigger would fire on a row whose `deleted_at` was already
    set, which `gate.record_entitlement_change` skips, so the audit ledger would be right and
    this route's answer would be a guess about why.

    `returning` the instant, so the answer is the row the database retired. Nothing else is
    returned: see `GrantRemoved`.
    """
    return (
        update(CapabilityGrantRow)
        .where(
            CapabilityGrantRow.principal_id == principal_id,
            CapabilityGrantRow.capability == capability,
            CapabilityGrantRow.deleted_at.is_(None),
        )
        .values(deleted_at=at)
        .returning(CapabilityGrantRow.deleted_at)
    )


def actor_is(principal_id: str) -> Any:
    """Tell this transaction who is making the entitlement write.

    `set_config(..., true)` is transaction-local, which is the trap
    `brain.gate.suspension_store._set_config` records: a session setting on a pooled connection
    is inherited by whoever borrows the connection next, and an audit entry attributed to the
    previous borrower is worse than one attributed to nobody.

    A bind parameter rather than interpolation, for `brain.cache`'s reason: a value going into
    SQL text for no reason.

    See `THE_TRIGGER_WRITES_THE_ENTRY_AND_THE_ROUTE_SAYS_WHO`.
    """
    return text("SELECT set_config(:name, :value, true)").bindparams(
        name=ACTOR_SETTING, value=principal_id
    )


# ------------------------------------------------------------------ the loading


def placed_grant(row: CapabilityGrantRow, department: str | None) -> Placed[SubjectGrant]:
    """One stored grant row, as the pair `govern.people` narrows.

    `granted_at` comes from `created_at`; see `grant_view`. `where` is the empty mapping when
    the principal row carried no department, which fails closed: see `live_grants`.
    """
    return Placed(
        record=SubjectGrant(
            subject=PrincipalSubject(principal_id=row.principal_id),
            capability=Capability(value=row.capability),
            scope=Scope.model_validate(row.scope),
            granted_by=row.granted_by,
            reason=row.reason,
            granted_at=row.created_at,
            not_after=row.not_after,
        ),
        where={} if department is None else {"department": department},
    )


def placed_assignment(
    row: CapabilityPackAssignmentRow,
    pack: CapabilityPackRow,
    department: str | None,
) -> tuple[Placed[SubjectGrant], ...]:
    """One stored pack assignment, as the grants it means, each paired with its subject's row.

    `expand` is what turns the pack into grants and there is no second way to do it: reading
    `pack.capabilities` here and building a `SubjectGrant` per member would be a second
    implementation of what a pack means, which is the thing that module's docstring says the
    function exists to prevent.

    `pack.name` becomes the pack's slug and `pack.description` its label, because
    `gate.capability_pack` names its columns that way and `CapabilityPack` names its fields the
    other way. The mapping is stated here rather than in a loader somewhere else so that a
    reader comparing the table with the type has one place to look.
    """
    bundle = CapabilityPack(
        slug=pack.name,
        label=pack.description[:PACK_LABEL_CHARS],
        capabilities=tuple(Capability(value=one) for one in pack.capabilities),
    )
    assignment = PackAssignment(
        subject=PrincipalSubject(principal_id=row.principal_id),
        pack_slug=pack.name,
        scope=Scope.model_validate(row.scope),
        granted_by=row.granted_by,
        reason=row.reason,
        granted_at=row.created_at,
        not_after=row.not_after,
    )
    where = {} if department is None else {"department": department}
    return tuple(Placed(record=one, where=where) for one in expand(bundle, assignment))


def proposal_from(
    body: GrantProposal, record: ScopeRecord, granted_by: str, at: datetime
) -> SubjectGrant:
    """The grant a body and a named scope amount to, before anybody has judged it.

    Constructed rather than validated in pieces, because `SubjectGrant`'s own validator is what
    refuses an unsatisfiable scope, a non-conjunctive one and a `not_after` that is not after
    the grant. A route checking those itself would be a second copy of three rules.

    `granted_by` is the caller and never the body; see `GrantProposal`.
    """
    return SubjectGrant(
        subject=PrincipalSubject(principal_id=body.principal_id),
        capability=Capability(value=body.capability),
        scope=record.scope,
        granted_by=granted_by,
        reason=body.reason,
        granted_at=at,
        not_after=body.not_after,
    )


# ------------------------------------------------------------------- the wiring


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    """The factory, or a process-level fault.

    `sessions_of` is imported from `brain.routing_routes` rather than written again: it is one
    `getattr` and one `isinstance` against `app.state`, and two spellings of "the factory this
    process was built with" is two places for the isinstance check to drift.

    A `Failed` rather than an `Absent`, on that module's argument: an instance with no pool is
    broken rather than empty, and only a caller who already holds the screen's grant reaches
    this line.
    """
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _require_console_reads(request: Request) -> ConsoleReads:
    """Where a page is read from: `app.state.console_reads`, or the primary."""
    found = getattr(request.app.state, "console_reads", None)
    if isinstance(found, ConsoleReads):
        return found
    return ConsoleReads(_require_sessions(request))


def _not_answerable(what: str) -> Absent:
    """The refusal a govern screen makes. One shape, four screens.

    `what` names the screen and never the row, the capability or the caller. The screen names
    are the console's own menu, identical in every install and already listed to everybody by
    `console/src/layout/Shell.tsx`, so naming one discloses nothing about this company; naming
    what was withheld would disclose everything the withholding was for.
    `brain.app.handle_brain_error` sends `Absent.public_message`, and this string reaches a log.
    """
    return Absent(f"the {what} screen is not answerable for this caller")


def _no_grant_here() -> Absent:
    """The one refusal every write over a grant makes.

    Named rather than raised inline in six places, so the six are the same refusal. See
    `A_CONSTRAINT_VIOLATION_IS_A_FACT_ABOUT_SOMEBODY_ELSE`.
    """
    return Absent("that grant is not writable by this caller")


# -------------------------------------------------------------------- the routes

router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get("/govern/people", response_model=PeoplePage, responses=COMMON_RESPONSES)
async def people_page(
    request: Request,
    asked: Asked,
    limit: Annotated[int, Query(ge=1, le=MAX_PEOPLE_PER_PAGE)] = DEFAULT_PEOPLE_PER_PAGE,
) -> PeoplePage:
    """Who holds what, at this reader's reach.

    The screen's question first and the database second; see the module docstring on the order.

    Two loads and one decision. `govern.people` receives the direct grants and the expanded
    pack assignments as one sequence and decides all of it, which is what keeps the two tables
    from being two policies: a subject reached through a pack is narrowed by the same row
    question and named by the same vocabulary grant as one reached directly.

    `truncated` is the page having come back full, and it is deliberately computed against what
    was loaded rather than against what `govern.people` returned. The second would be a count of
    what the decision withheld, spelled as a boolean.

    **A row that does not construct is skipped rather than raised on, and the gap it comes
    through is real.** `gate.capability_pack.name` is checked against
    `brain.core.field_policy.NAME_PATTERN` and `CapabilityPack.slug` against
    `brain.core.department.SLUG_PATTERN`, and the first admits names the second refuses: a
    trailing underscore and a doubled one both pass the column and fail the type. So a pack
    somebody named that way would take the whole People screen down for everybody, which is the
    screen an administrator opens to find out what is wrong. It is skipped, loudly in the log
    and silently on the response, because a count of skipped rows is a count of rows this reader
    was not shown. The same shape as the scopes screen's skip and for the same reason. See
    `A_ROW_THE_TYPE_REFUSES_IS_A_ROW_AND_NOT_THE_END_OF_THE_SCREEN`.
    """
    if not permitted(screen(PEOPLE_SCREEN).read, asked.reach, asked.now):
        log.info("people screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable(PEOPLE_SCREEN)

    reads = _require_console_reads(request)

    async def load(session: AsyncSession) -> tuple[list[Placed[SubjectGrant]], bool]:
        direct = (await session.execute(live_grants(limit))).all()
        assigned = (await session.execute(live_assignments(limit))).all()
        holdings: list[Placed[SubjectGrant]] = [
            placed_grant(row, department) for row, department in direct
        ]
        for row, pack, department in assigned:
            try:
                holdings.extend(placed_assignment(row, pack, department))
            except (ValueError, PredicateRefusedError):
                log.warning("pack assignment does not construct", pack=pack.name)
        return holdings, len(direct) >= limit or len(assigned) >= limit

    served = await reads.read(load, now=asked.now)
    holdings, full = served.value

    return PeoplePage(
        items=[
            person_view(one.subject, one.capabilities)
            for one in people(holdings, asked.reach, asked.now)
        ],
        next_cursor=None,
        truncated=full,
        editable=asked.reach.scope_for(REACH_AUTHORITY, asked.now) is not None,
        staleness=served.banner,
    )


@router.get("/govern/roles", response_model=RoleCatalogue, responses=COMMON_RESPONSES)
async def roles(asked: Asked) -> RoleCatalogue:
    """The six roles and what each one is for.

    No database and no session, because there is nothing stored to read: `ROLE_SPECS` is a
    constant of the product and `govern.role_catalogue` returns it in `Role`'s own declaration
    order. That is the same shape `brain.classification_routes` has and states about itself.

    Whole or refused. `role_catalogue` takes no entitlement at all, and its docstring says that
    absence is the statement: what a role is for is product documentation and a function that
    cannot see a reader cannot make a decision about one. So the whole decision on this screen
    is whether it opens, and it is `permitted`'s.
    """
    if not permitted(screen(ROLES_SCREEN).read, asked.reach, asked.now):
        log.info("roles screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable(ROLES_SCREEN)
    return RoleCatalogue(roles=tuple(role_view(one) for one in role_catalogue()))


@router.get("/govern/capabilities", response_model=CapabilityCatalogue, responses=COMMON_RESPONSES)
async def capabilities(request: Request, asked: Asked) -> CapabilityCatalogue:
    """Everything that can be granted at all, whole, or nothing at all.

    There is no `limit` parameter and that is the point of the route. `govern.catalogue`
    answers the vocabulary whole or empty, so a page of it would be a third answer the
    decision does not have, and a truncated catalogue is the shape that makes a reader believe
    the vocabulary is smaller than it is, which is exactly the mistake
    `A_CATALOGUE_FILTERED_TO_THE_READER_IS_THEIR_OWN_ENTITLEMENT_RELABELLED` names one cause of.
    `MAX_CAPABILITIES_PER_PAGE` bounds the statement and a registry larger than it is a `Failed`
    rather than a short answer: an install with that many registered capabilities is broken in
    a way this screen cannot render honestly.

    A reader without the grant is answered an empty catalogue rather than refused, because that
    is what `catalogue` returns and its docstring says why: `navigation` has already left the
    screen out of their menu, and a lock rendered on a screen they cannot open is a lock nobody
    sees. That is the one route here that does not refuse, and it is the console module's
    decision rather than this module's.

    **And it is answered before the database is opened, which is the whole reason the same
    question is asked twice.** `catalogue` asks `may_name_capabilities`, which is `permitted`
    over this screen's own read, and it asks it *after* being handed the vocabulary. Loading
    first and deciding afterwards would give an unentitled caller an empty catalogue on an
    instance with a database and a `Failed` on one without, which is the deployment's state
    readable by anybody who can reach the port: the ordering property every other route here
    keeps, lost on the one route whose refusal is an empty answer. So the early return is not a
    second decision, it is the same decision asked early enough to be free; the answer it
    produces is the answer `catalogue` would have produced, and `catalogue` still decides on
    every path where a row exists.
    """
    if not permitted(screen(VOCABULARY_SCREEN).read, asked.reach, asked.now):
        log.info("capability catalogue not named", principal=asked.caller.principal.id)
        return CapabilityCatalogue(capabilities=())

    reads = _require_console_reads(request)

    async def load(session: AsyncSession) -> list[CapabilityRegistryRow]:
        return list(
            (await session.execute(live_capabilities(MAX_CAPABILITIES_PER_PAGE + 1)))
            .scalars()
            .all()
        )

    served = await reads.read(load, now=asked.now)
    rows = served.value
    if len(rows) > MAX_CAPABILITIES_PER_PAGE:
        raise Failed("the capability registry is larger than this screen can answer whole")

    described = {one.capability: one.description for one in rows}
    named = catalogue((Capability(value=one.capability) for one in rows), asked.reach, asked.now)
    return CapabilityCatalogue(
        capabilities=tuple(
            CapabilityView(capability=one, description=described.get(one, "")) for one in named
        ),
        staleness=served.banner,
    )


@router.get("/govern/scopes", response_model=ScopePage, responses=COMMON_RESPONSES)
async def scopes(
    request: Request,
    asked: Asked,
    limit: Annotated[int, Query(ge=1, le=MAX_SCOPES_PER_PAGE)] = DEFAULT_SCOPES_PER_PAGE,
) -> ScopePage:
    """The row predicates a grant can carry, and the departments they are written over.

    Two decisions, both somebody else's. `scope_rows` narrows the predicates by
    `scoped_authority.within_reach`, which is containment rather than the row question, and
    `departments_offered` narrows the filter list by `admits_department` and then by
    `screens.offerable`. Neither returns a count of what it dropped and neither is helped here.

    A scope row that does not construct is skipped rather than raised on. `ScopeRecord` refuses
    a predicate that can match nothing, on the argument that dead configuration looks exactly
    like a permission bug from the far end of a query; a row like that in the table is a
    configuration fault and answering 500 for it would take the whole screen away from somebody
    who came to fix it. The skip is silent on the response and loud in the log, because a count
    of skipped rows on the page would be a count of rows this reader was not shown.
    """
    if not permitted(screen(SCOPES_SCREEN).read, asked.reach, asked.now):
        log.info("scopes screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable(SCOPES_SCREEN)

    reads = _require_console_reads(request)

    async def load(session: AsyncSession) -> tuple[list[ScopeRow], list[str], bool]:
        rows = list((await session.execute(live_scopes(limit))).scalars().all())
        names = list((await session.execute(live_departments(MAX_DEPARTMENTS))).scalars().all())
        return rows, names, len(rows) >= limit

    served = await reads.read(load, now=asked.now)
    rows, names, full = served.value

    records: list[ScopeRecord] = []
    for row in rows:
        try:
            records.append(
                ScopeRecord.from_predicate(
                    row.slug,
                    row.predicate,
                    is_department=row.is_department,
                    label=row.label,
                )
            )
        except (ValueError, PredicateRefusedError):
            log.warning("scope row does not construct", slug=row.slug)

    return ScopePage(
        items=[scope_view(one) for one in scope_rows(records, asked.reach, asked.now)],
        next_cursor=None,
        truncated=full,
        departments=departments_offered(names, asked.reach, asked.now),
        staleness=served.banner,
    )


@router.post(
    "/govern/grants", response_model=GrantView, responses=COMMON_RESPONSES, status_code=201
)
async def grant(request: Request, body: GrantProposal, asked: Asked) -> GrantView:
    """Write one grant, at a scope this caller holds and never wider.

    The order is four steps and each one is a refusal that looks like the others.

    The authority first, before any statement, so a caller who may not write grants cannot
    learn whether this process has a database. `may_grant` asks the same question again with
    the proposal's own scope, which is the narrower form; this is the cheap half, and it is
    here for the ordering rather than for the decision.

    Then the scope slug, resolved against `gate.scope`. A slug nothing matches is the same
    refusal as a slug out of reach, which is what stops this route being a way to enumerate the
    scopes somebody may not see, one POST at a time.

    Then `scoped_authority.write_grant`, which is the decision. It is asked here as well as by
    whatever listed the scopes, and that is not belt and braces: the listing decides what a
    screen offers and this decides what a submitted form may do, and a form is submitted by
    whatever was posted rather than by what was offered.

    Then the write, with the actor named to the transaction so the trigger's entry is
    attributable, and `IntegrityError` answered as the same refusal as everything above.
    """
    if asked.reach.scope_for(REACH_AUTHORITY, asked.now) is None:
        log.info("grant not writable", principal=asked.caller.principal.id)
        raise _no_grant_here()

    factory = _require_sessions(request)
    async with factory() as session:
        row = (await session.execute(one_live_scope(body.scope_slug))).scalar_one_or_none()
        if row is None:
            await session.rollback()
            log.info("grant names no live scope", slug=body.scope_slug)
            raise _no_grant_here()
        try:
            record = ScopeRecord.from_predicate(
                row.slug, row.predicate, is_department=row.is_department, label=row.label
            )
            proposed = proposal_from(body, record, asked.caller.principal.id, asked.now)
            written = write_grant(proposed, asked.reach, asked.now)
        except (ValueError, PredicateRefusedError, AuthorityError):
            # One `except` over three raises, and they are three refusals with one answer: a
            # scope row that does not construct, a proposal the type refuses, and a grant this
            # caller may not write. Telling them apart on the response would say which of the
            # three the caller got wrong, and the third is the one that must not be knowable.
            await session.rollback()
            log.info("grant refused", principal=asked.caller.principal.id)
            raise _no_grant_here() from None

        await session.execute(actor_is(asked.caller.principal.id))
        try:
            stored = (
                await session.execute(add_grant(written, body.principal_id))
            ).scalar_one_or_none()
        except IntegrityError:
            await session.rollback()
            log.info("grant refused by a constraint", principal=asked.caller.principal.id)
            raise _no_grant_here() from None
        if stored is None:
            await session.rollback()
            log.info("grant wrote no row", principal=asked.caller.principal.id)
            raise _no_grant_here()
        await session.commit()
        return grant_view(stored)


@router.post(
    "/govern/grants/removal",
    response_model=GrantRemoved,
    responses=COMMON_RESPONSES,
)
async def remove_grant(request: Request, body: GrantRemoval, asked: Asked) -> GrantRemoved:
    """Take one grant away. A retired row, and an audit entry the trigger writes.

    **Named by subject and capability rather than by an id, because that is what the screen
    holds.** See `one_live_grant`: the People screen's row is a subject with its capabilities
    collapsed on to it and carries no grant id, by `govern.people`'s own decision, so a removal
    keyed on one would be a write nothing in a browser could reach. The pair is also what
    `brain.identity.packs.revoke_capability` matches on.

    **A capability that arrived through a pack is not removable here, and is refused in the
    same words as everything else.** There is no grant row for it: `packs.expand` produces the
    grants an assignment means without writing any, so the row this looks for is genuinely not
    there. Removing it is removing the assignment, which takes away every other capability in
    the pack at the same time, and that is a different act somebody should perform deliberately
    rather than discover. It is a real gap on this screen and it is named rather than papered
    over; the refusal is the ordinary one because saying "that one came from a pack" would tell
    a caller which of somebody else's capabilities did.

    `govern.certify` is the decision and it is not restated here. It asks `may_certify`, which
    is three questions: the review authority against the row the grant sits in, the review
    authority against the scope the grant confers, and the grant's own capability against that
    scope. And `Certification` refuses a self-certification in its constructor, which is the
    one this route could not have asked on its own: `A_CERTIFICATION_OF_YOUR_OWN_GRANT_IS_A_
    SELF_GRANT_WITH_A_ROUND_ATTACHED`.

    `Decision.REMOVE` is the only decision this route offers. See
    `ONLY_THE_HALF_OF_A_ROUND_THAT_HAS_A_ROW_TO_WRITE`.

    The authority is asked cheaply before the row is loaded, on the ordering argument every
    route here shares, and then properly by `certify` once there is a row to ask about.
    """
    if asked.reach.scope_for(REACH_AUTHORITY, asked.now) is None:
        log.info("grant not removable", principal=asked.caller.principal.id)
        raise _no_grant_here()

    factory = _require_sessions(request)
    async with factory() as session:
        found = (await session.execute(one_live_grant(body.principal_id, body.capability))).all()
        if not found:
            await session.rollback()
            log.info("grant not there", principal=asked.caller.principal.id)
            raise _no_grant_here()
        row, department = found[0]
        try:
            certify(
                placed_grant(row, department),
                asked.reach,
                Decision.REMOVE,
                by=asked.caller.principal.id,
                at=asked.now,
                now=asked.now,
            )
        except (ValueError, GovernError):
            await session.rollback()
            log.info("grant removal refused", principal=asked.caller.principal.id)
            raise _no_grant_here() from None

        await session.execute(actor_is(asked.caller.principal.id))
        retired = (
            await session.execute(retire_grant(body.principal_id, body.capability, asked.now))
        ).one_or_none()
        if retired is None:
            await session.rollback()
            log.info("grant removal wrote no row", principal=asked.caller.principal.id)
            raise _no_grant_here()
        await session.commit()
        return GrantRemoved(
            principal_id=body.principal_id, capability=body.capability, removed_at=retired[0]
        )
