"""Laravel: the client's own MySQL, read through views they control and nothing else.

Every other connector in this repository talks to a vendor's API, where somebody else has
already decided what a caller may see and the worst we can do is ask too often. This one
connects straight to **the client's production database**, and both halves of that sentence
are the design.

**A view is a contract and a table is not.** The application owns this schema. A table can
gain a column in next Tuesday's migration, and a connector holding SELECT on the table sees
it immediately: unclassified, unmapped, and travelling through this process and into a trace
before anybody has decided whether it should exist here at all. A view is the client's own
statement of what we may read, changed only when they change it, reviewable by them without
reading any of our code. So the reachable set is a closed tuple of view names matched by
string equality (`transports.DatabaseTransport.plan`, M11.1.4, imported rather than
reimplemented), the entity-to-view mapping is total and frozen, and a name that does not
read as a view is refused at connect. See `A_VIEW_IS_A_CONTRACT_AND_A_TABLE_IS_NOT`, and see
`THE_GRANT_IS_THE_HALF_WE_CANNOT_SEE` for what this module honestly does not enforce.

**Nothing here becomes SQL, because nothing here is a string that could.** The transport
takes a view name and filters and hands back a `ViewRead`; whoever executes builds the
statement from those, with every value bound. `brain.knowledge.rows` already argues this at
length and already carries the two checks, so this module satisfies them rather than
restating them: `assert_takes_no_sql` runs on the fetch closure beside
`contract.assert_fetches_only`, and `assert_builds_no_sql` runs
`assert_no_sql_is_built_by_interpolation` over this module's own parsed source.

**A runaway read cannot corrupt anything, which is not the risk.** A read-only credential
cannot write a row, and that is the reassurance everybody offers before the incident. What a
long SELECT does to InnoDB is quieter: it takes no locks, so it does not block their writers
directly, but it pins a read view for as long as it runs, purge cannot advance past it and
the undo history grows behind it, while a scan through a view evicts the pages the client's
own queries were using out of the buffer pool. The visible symptom is the client's
application getting slower, on the client's hardware, with nothing in the client's logs
naming us. So every read this module produces carries a row cap and a time bound, and
`BoundedRead` cannot be constructed without both: there is no value anywhere in this module
that expresses an unbounded read. `DatabaseTransport.plan` permits `limit=0`, which means no
limit, and zero is precisely the value this connector must never hand it. See
`AN_UNBOUNDED_READ_IS_A_QUERY_AGAINST_SOMEBODY_ELSES_BUSINESS`.

**A Laravel `users` table is the sharpest thing in this database.** It carries a display
name, an email, usually a phone number, and next to them a bcrypt hash, a remember token and
a two-factor secret. The platform denylist in `brain.core.projection` stops none of the last
three: `password_hash` is not on it, is not matched by any of its patterns, and declared as
a label with a hot use it passes all five clauses of `manifest.projectability`. So the
refusal lives here, by name, and it refuses **selection** rather than only projection.
Refusing to store a password hash we have already fetched into this process is not a
control; refusing to put it in the column list is. `contract.CREDENTIAL_ATTRIBUTE_RE` is the
pattern, imported, because that rule already exists for connector attributes and a credential
column is the same mistake one layer out.

**Absent, refused and unreachable are three answers and stay three.** Zero rows from a view
is a fact about the client's business. A grant that no longer covers the view, or a view that
is no longer there, is the contract having been withdrawn: reporting that as "no rows" tells
somebody their client has no projects when what happened is that a migration dropped
`v_project` last night. A timeout or a dead connection is the database not answering.
`LaravelReply` refuses at construction to carry rows or a read time on a failure, so
answering from the last good read is not something a caller can express. What a *person* is
told is the same sentence for a refusal and for an outage, because which of our systems is
unwell is not a fact obtainable by typing a question; the trace keeps the difference.

**An unknown view is a refusal, never an absence.** This is the one classification in the
module that is worth arguing on its own, because the tempting reading is the opposite: the
view is not there, so there is nothing to return, so return nothing. That produces a
confident empty answer out of a broken installation, nobody files a bug because an empty list
is a plausible answer, and the projection quietly stops being refreshed at the same time.

**Its ceiling is this product's own pace, and says so.** No vendor publishes a rate for a
company's own database, and `brain.ops.limits` records a figure for this source that is ours: a
conservative number of bounded reads a minute across the worker and every question together, so
twenty concurrent agent runs are not twenty concurrent reads of the company's database. The
manifest names it, `throttle.limits_for` admits each read against it, and the note beside the
figure says it is not a vendor's. See `THERE_IS_NO_MEASURED_CEILING_HERE`.

**The time bound is enforced where the statement runs, not here.** `BoundedRead` names the
seconds so a read cannot be issued without somebody having chosen a number, and the executor
(`brain.ops.laravel_reader`) sets the driver's timeouts and the session's own bound from it.
`transports.THE_SANDBOX_IS_NOT_IN_THIS_MODULE` draws the same line about its sandbox profile.

**Where the database is, is a setting, and a private address is refused unless the connection
says it is on a private network.** The host and the port are typed on the form and have no
default, because no two companies' databases are in the same place. Each read resolves the host
and connects to the address it checked, through the REST sources' own rule
(`brain.tools.fetch.assert_fetchable`), so a name that answers inside this server's network is
refused like any other source's. A connection whose database is on a private network, reached
directly or through a tunnel the operator runs, says so in its own setting, and only that
connection may name a private address. See `A_PRIVATE_ADDRESS_IS_THE_CONNECTION_S_OWN_DECISION`.

**This connector reads, on a schedule and while somebody waits (M11.6.1).** `LaravelReading` is
the worker's `ViewReading`: one bounded read of each view per run, written into the minimal index.
`LaravelLiveLookup` narrows the same read to one record's id while somebody waits. Both run the
read through `connector_fetch`, so the two checks on the fetch closure hold for every read this
product makes of the company's database, and both open the executor only when a read happens,
so importing this module imports no driver.

Rejected, and worth stating:

*Reading the tables and filtering in the connector.* It is less work for the client's DBA and
it moves every column they have ever added into this process, where "we dropped it before
rendering" becomes a claim about every code path rather than a property of the query. It is
the same argument `brain.knowledge.rows` makes about its SELECT list, one system further out.

*Accepting a view name from the caller and validating it.* A validator is a parser, and a
parser that disagrees with MySQL's own is a bypass. The entity-to-view mapping is total and
the allowlist is matched by equality, which has no dialect.

*Treating the recorded HTTP 500 as this connector's failure shape.* The one recorded Laravel
exchange is a 500 from the application's own internal endpoint, not a database error, because
that is the exchange somebody recorded. It is still this source failing and it still gets the
same classification, so `ViewReply.app_status` is the narrow seam that lets the recording be
interpreted here without anybody inventing a MySQL error code to carry it.

Scope: domain logic. Nothing here opens a connection, imports a driver, holds a DSN or reads
a clock. The reader is a protocol, the one that opens a socket is imported from
`brain.ops.laravel_reader` inside the function that makes a read, `fetched_at` and `checked_at`
are parameters, and `assert_holds_no_credential` runs on the connection at construction.

**This connector keeps a minimal index and reads every value live.** What it keeps of a
client and a staff record is their ids, names, status, department, manager and when they
changed (`PROJECTED_FIELDS`); a contract value, and every column a view carries beyond its
declared contract, is read live and never stored, which the canary planted in the recorded
contract value proves on every build. It is declared as `CONNECTOR` at the foot of this
module (`brain.connectors.declaration`).

Task ids: M11.6.1, M38.4.1.1, M11.7.7
"""

from __future__ import annotations

import enum
import ipaddress
import re
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, Protocol

from brain.connectors.change_signal import ChangeSubscription, DeletionCheck
from brain.connectors.contract import (
    CREDENTIAL_ATTRIBUTE_RE,
    UNBOUNDED_SELECTORS,
    AccessMode,
    ConnectorContractError,
    ConnectorHealth,
    ConnectorScope,
    CredentialBinding,
    FetchRequest,
    HealthState,
    TransportKind,
    assert_fetches_only,
    assert_holds_no_credential,
)
from brain.connectors.declaration import (
    CREDENTIAL_ASK,
    ConnectorDeclaration,
    ConsoleForm,
    CredentialShape,
    DatabaseLogin,
    PageReply,
    Recorded,
    Setting,
    SettingRefusedError,
)
from brain.connectors.federation import FailureReason, PartialAnswer, SourceFailure
from brain.connectors.manifest import (
    ChangeSignal,
    ConnectorManifest,
    FieldShape,
    HotUse,
    ProjectedEntity,
    ProjectedField,
    ToolDeclaration,
)
from brain.connectors.projection import ProjectedRecord, ProjectedValue, RefreshPromise
from brain.connectors.throttle import CallOutcome, classify
from brain.connectors.transports import (
    DatabaseTransport,
    SourceRecord,
    TransportError,
    ViewRead,
    assert_scope_covers,
    normalise,
)
from brain.connectors.write_verification import ReadBack, classified_reading
from brain.core.envelope import IdentityMode, SideEffect, TypedResult
from brain.core.errors import Degraded
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.core.projection import ProjectionRefusedError
from brain.core.scope import Clause, Op, Scope
from brain.gate.provenance import Freshness, StalenessHorizon, assess_freshness
from brain.knowledge.rows import assert_takes_no_sql
from brain.ops.connect_steps import GuideStep, LineKind, Sketch, SketchLine, keyed
from brain.ops.secrets import SecretRef
from brain.tools.fetch import Resolver, UnsafeAddressError, assert_fetchable

# ------------------------------------------------------------------ written-down reasons
#: Why the reachable set is views and never tables.
A_VIEW_IS_A_CONTRACT_AND_A_TABLE_IS_NOT = (
    "The client's application owns this database and we are a guest in it. A table is "
    "whatever their next migration makes it: a connector holding SELECT on one sees a column "
    "added on Tuesday on Tuesday, unclassified and unreviewed, and the first anybody here "
    "hears of it is when it turns up in a trace. A view is the client's own written statement "
    "of what we may read, it changes only when they change it, and they can review it without "
    "reading a line of our code. So the reachable set is a closed tuple matched by string "
    "equality, and the entity-to-view mapping is total: an entity nobody declared has no view "
    "to be read from rather than a name somebody can supply."
)

#: What this module does and does not enforce about the boundary above.
THE_GRANT_IS_THE_HALF_WE_CANNOT_SEE = (
    "Nothing in this process can tell a view from a table: only the server knows, and it "
    "answers a SELECT on either identically. The real restriction is the grant, and "
    "ops/openbao/credential-slots.md records it as SELECT on the allowlisted views only, "
    "with tables named as the thing to refuse. What this module adds is that a name which "
    "does not read as a view is refused at connect, in front of whoever typed it, rather "
    "than discovered later by working. That is a spelling check on a declaration and it is "
    "not the boundary; saying otherwise would be the worst possible place to be vague."
)

#: Why every read carries a row cap and a time bound, and why zero is the dangerous value.
AN_UNBOUNDED_READ_IS_A_QUERY_AGAINST_SOMEBODY_ELSES_BUSINESS = (
    "A read-only credential cannot corrupt a row, which is the reassurance offered before "
    "every incident of this kind. A long SELECT on InnoDB takes no locks and blocks no "
    "writer, and it pins a read view for as long as it runs: purge cannot advance past it, "
    "the undo history grows behind it, and a scan evicts the pages the client's own queries "
    "were using. Their application gets slower, on their hardware, with nothing in their logs "
    "naming us. DatabaseTransport.plan refuses a negative limit and permits zero, and zero "
    "means no limit, so zero is exactly the value this connector must never produce. "
    "BoundedRead refuses to exist without a positive row cap and a positive time bound."
)

#: Why a password hash is refused from the column list rather than from the projection.
A_CREDENTIAL_COLUMN_IS_REFUSED_BEFORE_IT_IS_FETCHED = (
    "A Laravel users table carries a bcrypt hash, a remember token and a two-factor secret "
    "next to the display name. None of the three is on brain.core.projection's denylist and "
    "none is matched by its patterns, so declared as a label with a hot use each passes all "
    "five clauses of the projectability test. Refusing to store one we have already fetched "
    "is not a control: it is in this process, in a trace, in whatever a retry path held. The "
    "refusal is therefore on the column list, which is the only place it costs nothing. The "
    "pattern is contract.CREDENTIAL_ATTRIBUTE_RE, imported rather than restated, because a "
    "credential column and a credential attribute are one mistake at two layers."
)

#: Why a view that is gone is a refusal rather than an empty result.
A_MISSING_VIEW_IS_A_WITHDRAWN_CONTRACT = (
    "The tempting reading is that the view is not there, so there is nothing to return, so "
    "return nothing. That turns a broken installation into a confident empty answer: somebody "
    "is told their client has no projects when a migration dropped the view last night, "
    "nobody files a bug because an empty list is plausible, and the projection stops being "
    "refreshed at the same moment with the same silence. A view that is not there is the "
    "contract having been withdrawn, which is a job for whoever owns the connection and the "
    "client's DBA, and it is not a fact about the client's business."
)

#: Why a column the declaration does not name never arrives, even if the view returns it.
WHAT_THE_DECLARATION_DOES_NOT_NAME_DOES_NOT_ARRIVE = (
    "The column list goes into the statement, so a column nobody declared is never fetched, "
    "and the record is then built from the declared names rather than copied from the row "
    "that came back. Both halves are needed. The first is what makes an added column cost "
    "nothing; the second is what stops an executor that ran a wider statement of its own "
    "widening the answer. brain.knowledge.rows makes the same argument about its SELECT "
    "list, and the failure mode it names is the one here: SELECT * plus a filter afterwards "
    "means today's safety depends on nobody adding a column tomorrow."
)

#: Why a filter naming an undeclared column is refused rather than dropped.
A_DROPPED_FILTER_WIDENS_A_READ = (
    "A filter narrows, so dropping one widens the read, and widening a read of somebody "
    "else's production database is the direction this module exists to prevent. "
    "brain.knowledge.rows compiles an unreachable filter to nothing rather than dropping it, "
    "for the same refusal to widen, and answers a different question: there the filter is the "
    "asker's and a refusal would confirm a column exists. Here the filters arrive from the "
    "gate, which has already decided what may be seen, so an undeclared name is a mistake by "
    "whoever wired the tool and belongs in front of them at build time."
)

#: What this connector's ceiling is instead of a measured one, said plainly.
THERE_IS_NO_MEASURED_CEILING_HERE = (
    "No vendor publishes a rate for a company's own database, so the figure brain.ops.limits "
    "records for this source is this product's own pace and not a measurement: a conservative "
    "number of bounded reads a minute across the worker and every question together, admitted "
    "read by read like any source's ceiling. It is not raisable by buying anything, because "
    "nobody sells it; it changes when a release of this product changes it. The per-read bound "
    "limits what one read can cost the database, and the ceiling limits how many there are."
)

#: Why a private address is refused unless this connection says its database is on one.
A_PRIVATE_ADDRESS_IS_THE_CONNECTION_S_OWN_DECISION = (
    "A host that resolves inside this server's network is refused by the rule every REST source "
    "passes through, so a connection cannot be used to reach the server's own infrastructure. A "
    "company whose database is on a private network, reached directly or through a tunnel the "
    "operator runs, says so in this connection's own setting, and only that connection may then "
    "name a private address. The setting is off unless yes is typed, and with it on nothing else "
    "about the read changes: the same user, the same views, the same bounds."
)

#: Why a view's rule is one value.
A_RULE_THE_INDEX_CANNOT_CARRY_IS_REFUSED = (
    "A view's rule is stored on every record the view keeps, so the index can test a reader's "
    "grant against it, and a record holds one value in a field. A rule listing several values "
    "would be connected and never read, so it is refused where it is typed."
)

#: What the source's own permission model is, said plainly rather than implied by a blank.
THE_VIEW_IS_THE_UNIT_OF_ACCESS = (
    "MySQL grants SELECT on a view, not on a row of one: everybody who can read "
    "portal.v_client can read every row of it, and the row filtering is inside the view "
    "definition where the client wrote it. So there is no per-record ACL here to store a "
    "predicate from, and this module refuses to invent one. The predicate is supplied by "
    "whoever installs the connector, having read the view, and it is checked against the "
    "declared fields: a predicate over a column the view does not expose matches nothing, "
    "for ever, and looks exactly like a client with no records."
)


# ------------------------------------------------------------------------------- names
CONNECTOR_NAME: Final = "laravel"

#: The row of `brain.ops.limits.SOURCE_CEILINGS` every read of this connector is admitted by.
#: This connector's own name, held equal to it by a test. See `THERE_IS_NO_MEASURED_CEILING_HERE`.
CEILING_NAME: Final = "laravel"

MANIFEST_VERSION: Final = "1.0.0"

ENTITY_CLIENT: Final = "client"
ENTITY_USER: Final = "user"

#: Every record's own identifier, and Laravel's own convention. Always in the column list and
#: never one of the projected fields: `ProjectedRecord.source_id` carries it, and declaring it
#: again would spend one of the twelve on a value that is already the key.
ID_COLUMN: Final = "id"

#: The column a cursor advances on. Laravel's `timestamps()` puts it on nearly every model,
#: which is what makes an updated-since subscription possible at all here.
CURSOR_COLUMN: Final = "updated_at"

#: What a person is told, and what an operator is told. Every one is a constant: a detail
#: assembled from a driver's error string would carry a filter value, and therefore a client's
#: name, into a health row and a trace with a different audience from the answer they describe.
#: A MySQL error message also quotes the statement, which is the last thing a console needs.
DETAIL_ANSWERED: Final = "answering"
DETAIL_CAPPED: Final = "answered up to this connector's row cap"
DETAIL_ACCESS_DENIED: Final = "the database declined this connector's grant on the view"
DETAIL_VIEW_MISSING: Final = "a view this connector was installed against is no longer there"
DETAIL_TIMED_OUT: Final = "the read passed this connector's own time bound and was stopped"
DETAIL_UNAVAILABLE: Final = "the database did not answer"
DETAIL_APPLICATION_FAILED: Final = "the application answered with a failure of its own"
DETAIL_NEVER_PROBED: Final = "nothing has probed this connector since it was installed"


class LaravelError(ConnectorContractError):
    """This connector was declared, or asked, for something it cannot hold.

    A `ConnectorContractError` for the reason that class gives: every refusal here is a
    mistake by whoever wrote or wired the connector, it should stop the connector rather than
    degrade somebody's answer, and nobody asking a question should ever see it. A request for
    an entity this connector does not read is that kind of mistake and not an outcome, so
    there is no reply shape for one.
    """


class LaravelDegraded(Degraded):
    """The database did not answer, or would not.

    One class rather than two, and the difference from `brain.connectors.freshdesk` is
    deliberate rather than an oversight. There, a refusal and an outage are separate types so
    a caller can `except` on the difference. Here neither is retryable in a way that differs
    (`throttle.is_retryable` says no to a rejection and the row cap has already been spent on
    a timeout), and the only consumers of the distinction are the trace and the health row,
    which read it off the two attributes below. Keeping one class is what makes "the person is
    told the same sentence whichever of our systems failed" structural rather than a
    coincidence of two classes happening to share a `public_message`.

    Both attributes are spelled out rather than reusing `BrainError.outcome`, which is the
    user-facing taxonomy and is DEGRADED here whatever the database did. Two different
    questions ("what is the person told" and "what actually happened") sharing one attribute
    is how the second one ends up rendered to somebody, which is the argument
    `brain.connectors.freshdesk` makes about its own; the type checker makes the same point
    less politely, because the base class already owns the name.
    """

    def __init__(
        self,
        detail: str = "",
        *,
        read_outcome: LaravelOutcome,
        call_outcome: CallOutcome,
    ) -> None:
        super().__init__(detail)
        self.read_outcome = read_outcome
        self.call_outcome = call_outcome


# ----------------------------------------------------------- the views (M11.1.4, M11.2.3)
#: What a view object may be called: `v_` and then a name. Not a security boundary and not
#: presented as one (`THE_GRANT_IS_THE_HALF_WE_CANNOT_SEE`); it is what stops `portal.clients`
#: reaching a manifest, which is the mistake somebody actually makes, and it is refused in
#: front of them rather than discovered by working.
VIEW_PREFIX: Final = "v_"

#: The schema, which in MySQL is the database name. Deliberately no looser than the schema
#: half of `transports._VIEW_RE`, so a name accepted here is accepted there; a test asserts
#: that every view this module can produce is one `DatabaseTransport` will hold.
_SCHEMA_MAX: Final = 63
_OBJECT_MAX: Final = 63

#: Entity to view object, total and frozen. Total because an entity absent from it has no view
#: to be read from at all, which is a stronger statement than a lookup that misses; frozen
#: because a module-level dict is a table any importer can edit, which is
#: `brain.ops.limits`'s argument about its own registries.
VIEW_OBJECT_FOR: Final[Mapping[str, str]] = MappingProxyType(
    {ENTITY_CLIENT: "v_client", ENTITY_USER: "v_user"}
)

ENTITIES: Final[tuple[str, ...]] = (ENTITY_CLIENT, ENTITY_USER)


def _is_name(value: str, *, limit: int) -> bool:
    """A lower-case identifier the server and the manifest will both read the same way.

    Written out rather than matched against another module's compiled pattern, because the
    pattern there is for a qualified name and this is one half of one. The relationship that
    matters is asserted rather than assumed: a test builds every view this module can produce
    and hands it to `DatabaseTransport`.
    """
    if not value or len(value) > limit:
        return False
    if not value[0].isalpha() or not value[0].islower():
        return False
    return all(c.islower() or c.isdigit() or c == "_" for c in value)


def assert_is_a_view(name: str) -> None:
    """Refuse a name that does not read as a schema-qualified view.

    Three refusals, and the third is the one this leaf is about.

    **Unqualified.** An unqualified name resolves against whatever database the connection was
    left set to, which is a property of the session rather than of the manifest.

    **Not a lower-case identifier.** Anything else is a name the server would need quoting to
    accept, and a quoted identifier is a place a second statement can start.

    **Not prefixed `v_`.** The house convention for a view here, and this is the check that
    catches `portal.clients` in a manifest. It is a spelling check and not a boundary: see
    `THE_GRANT_IS_THE_HALF_WE_CANNOT_SEE`.
    """
    schema, _, obj = name.partition(".")
    if not obj:
        msg = (
            f"view {name!r} is not schema-qualified; an unqualified name resolves against "
            "whatever database the connection was left set to rather than what the manifest "
            "says"
        )
        raise LaravelError(msg)
    if not _is_name(schema, limit=_SCHEMA_MAX) or not _is_name(obj, limit=_OBJECT_MAX):
        msg = (
            f"view {name!r} is not a lower-case identifier the server would take unquoted; a "
            "name that needs quoting is a name a second statement can start inside"
        )
        raise LaravelError(msg)
    if not obj.startswith(VIEW_PREFIX):
        msg = (
            f"{name!r} does not read as a view, and this connector reads views only. "
            f"{A_VIEW_IS_A_CONTRACT_AND_A_TABLE_IS_NOT}"
        )
        raise LaravelError(msg)


# -------------------------------------------------------------- the columns (M11.4.5)
@dataclass(frozen=True)
class RefusedColumn:
    """One column this connector never selects, and why, in the author's own words.

    A tuple of these rather than a mapping keyed by column name, so the reason travels beside
    the name in one value and a reviewer reads them together. `brain.connectors.freshdesk`
    keeps the same list for the same purpose about its own payload fields.
    """

    name: str
    reason: str


#: Columns a Laravel schema offers that this connector refuses to put in a column list at all.
#: Distinct from `contract.CREDENTIAL_ATTRIBUTE_RE`, which catches the credential-shaped names
#: by pattern; these are the ones that are not credential-shaped and are refused anyway. Every
#: one of them is on `brain.core.projection`'s denylist too, so nothing here could be stored.
#: What this adds is that none of them is ever *fetched*, which is a different and stronger
#: claim: a value that never enters this process cannot be logged, traced or held by a retry.
NEVER_SELECTED: Final[tuple[RefusedColumn, ...]] = (
    RefusedColumn(
        name="email",
        reason=(
            "on the permanent denylist, and the field somebody wants most: it is the join key "
            "between this database, Keycloak and Lark. Identity resolution belongs to "
            "brain.identity, which already holds that mapping from the directory, and a "
            "second copy arriving through a business-data connector would be a second store "
            "of everybody's email with no retention story of its own"
        ),
    ),
    RefusedColumn(
        name="phone",
        reason="on the permanent denylist, at any size, under any configuration",
    ),
    RefusedColumn(
        name="mobile",
        reason="the same value under the name a Laravel schema more often gives it",
    ),
    RefusedColumn(
        name="address",
        reason="on the permanent denylist; nothing in the fast lane filters or counts on one",
    ),
    RefusedColumn(
        name="nric",
        reason=(
            "on the permanent denylist, and the local case worth naming: a Singapore staff "
            "record routinely carries one, and it identifies a person completely and for life"
        ),
    ),
    RefusedColumn(
        name="date_of_birth",
        reason=(
            "not on the denylist and refused anyway: it is a personal identifier wearing a "
            "timestamp's shape, and declared as a TIMESTAMP with a sort use it would pass "
            "every clause of the projectability test"
        ),
    ),
    RefusedColumn(
        name="salary",
        reason="on the permanent denylist; it is also the field the company canaries protect",
    ),
)

_REFUSED_BY_NAME: Final[Mapping[str, str]] = MappingProxyType(
    {column.name: column.reason for column in NEVER_SELECTED}
)


def assert_columns_are_selectable(entity: str, columns: Iterable[str]) -> None:
    """Refuse a column list that would fetch a credential or a refused field (M11.4.4).

    Two rules, reported together rather than one at a time, which is the argument
    `brain.core.projection.check_projection` makes about its own violations: one at a time
    turns writing a connector into a guessing game where each fix reveals the next objection.

    **A credential-shaped name.** `password`, `remember_token`, `two_factor_secret`, an api
    key column somebody added. Matched by `contract.CREDENTIAL_ATTRIBUTE_RE`, imported, for
    the reason that module gives about matching a name rather than a type: a stored credential
    is always a string, so a rule looking at anything else would pass every one of them. See
    `A_CREDENTIAL_COLUMN_IS_REFUSED_BEFORE_IT_IS_FETCHED`.

    **A name on `NEVER_SELECTED`.** Personal detail that this connector has no question to
    answer with. Each carries its own reason, so the refusal says what to do instead rather
    than inviting a rename.

    A `ProjectionRefusedError` rather than an error of this module's own, because it is that
    refusal reaching one layer further out: the platform list and this one are one rule in two
    vocabularies, and a caller catching one should not have to know about the other.
    """
    problems: list[str] = []
    for column in columns:
        folded = column.casefold()
        if CREDENTIAL_ATTRIBUTE_RE.search(folded):
            problems.append(
                f"  - {column} is named for a credential; a Laravel users row holds a bcrypt "
                "hash, a remember token and a two-factor secret, and none of the three is on "
                "the platform denylist"
            )
            continue
        refused = _REFUSED_BY_NAME.get(folded)
        if refused is not None:
            problems.append(f"  - {column} is {refused}")
    if not problems:
        return
    listed = "\n".join(problems)
    msg = (
        f"{entity} would be read with columns this connector never selects:\n{listed}\n"
        f"{A_CREDENTIAL_COLUMN_IS_REFUSED_BEFORE_IT_IS_FETCHED}"
    )
    raise ProjectionRefusedError(msg)


#: What is kept locally about a client, and nothing else. Five of the twelve, and the room
#: left over is not thrift: every projected column is a column the client's DBA has to keep in
#: the view contract for ever, and a projection that fills its cap has nowhere to go when a
#: real need arrives. The record id is absent because `ProjectedRecord.source_id` carries it.
CLIENT_PROJECTED: Final[tuple[ProjectedField, ...]] = (
    ProjectedField(name="name", shape=FieldShape.LABEL, uses=(HotUse.IDENTIFY, HotUse.JOIN)),
    ProjectedField(name="status", shape=FieldShape.STATUS, uses=(HotUse.FILTER, HotUse.COUNT)),
    ProjectedField(name="department", shape=FieldShape.STATUS, uses=(HotUse.FILTER, HotUse.COUNT)),
    ProjectedField(name="manager_id", shape=FieldShape.JOIN_KEY, uses=(HotUse.JOIN, HotUse.FILTER)),
    ProjectedField(
        name=CURSOR_COLUMN, shape=FieldShape.TIMESTAMP, uses=(HotUse.SORT, HotUse.FILTER)
    ),
)

#: A staff record, projected down to what an answer needs to name a person and no further.
#: `display_name` is the one label: a person's name is what a person is called in a sentence,
#: it is not a way of reaching them, and there is no second label because two labels are a
#: payload arriving in instalments. Everything else a Laravel users row holds is refused
#: above, by name, with the reason attached.
USER_PROJECTED: Final[tuple[ProjectedField, ...]] = (
    ProjectedField(name="display_name", shape=FieldShape.LABEL, uses=(HotUse.IDENTIFY,)),
    ProjectedField(name="department", shape=FieldShape.STATUS, uses=(HotUse.FILTER, HotUse.COUNT)),
    ProjectedField(name="status", shape=FieldShape.STATUS, uses=(HotUse.FILTER,)),
    ProjectedField(name=CURSOR_COLUMN, shape=FieldShape.TIMESTAMP, uses=(HotUse.SORT,)),
)

PROJECTED_FIELDS: Final[Mapping[str, tuple[ProjectedField, ...]]] = MappingProxyType(
    {ENTITY_CLIENT: CLIENT_PROJECTED, ENTITY_USER: USER_PROJECTED}
)

#: Columns fetched on every read and never stored. One of them, and it is the money.
#: `contract_value` is on `brain.core.projection.NEVER_PROJECT` already, so the platform
#: refuses to store it whatever this module says; what this list does is state that it is
#: still *selected*, because a person holding `read:client.contract_value` is asking a
#: question that has to be answered from the ledger of the moment rather than from a copy.
#: The company canaries hold `CANARY-CONTRACT-7Q4XZ` in this field for exactly this test.
LIVE_ONLY: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {ENTITY_CLIENT: ("contract_value",), ENTITY_USER: ()}
)


def columns_for(entity: str) -> tuple[str, ...]:
    """Every column one read of this entity selects: the id, the projected, the live.

    The id first and the rest sorted, so two reads of the same entity produce the same column
    list in the same order. `brain.knowledge.rows` sorts its own for the same reason: a
    statement that differs between two identical questions is one nobody can compare.

    Checked here rather than at declaration only, because this is the function whose result
    becomes the column list in a statement, and the check that matters is the one on the value
    that travels.
    """
    projected = PROJECTED_FIELDS.get(entity)
    live = LIVE_ONLY.get(entity)
    if projected is None or live is None:
        msg = (
            f"this connector reads {sorted(PROJECTED_FIELDS)} and was asked for {entity!r}; an "
            "entity nothing declares has no view to be read from"
        )
        raise LaravelError(msg)
    rest = sorted({f.name for f in projected} | set(live))
    columns = (ID_COLUMN, *rest)
    assert_columns_are_selectable(entity, columns)
    return columns


def selected_columns(entity: str) -> tuple[str, ...]:
    """The column list without the id, which is what a field policy has rules for.

    The id is structural rather than classified: `SourceRecord` carries it as the record's
    name and no field policy rule governs it anywhere in this system.
    """
    return tuple(c for c in columns_for(entity) if c != ID_COLUMN)


# ------------------------------------------------------ the bound on one read (M11.6.1)
#: The largest row cap anybody may declare. A judgement rather than a measurement, and worth
#: saying what it is judging: a read this size is already a report rather than an answer to a
#: question, and a bound somebody can set to a million is not a bound. A backfill that needs
#: more takes more reads, which is what the cursor is for.
MAX_ROWS_EVER: Final = 5_000

#: The longest time bound anybody may declare. Thirty seconds is longer than any interactive
#: question waits and long enough for a report over a well-indexed view; past it the read has
#: stopped being a query and started being a load test on somebody else's afternoon.
MAX_TIMEOUT_SECONDS: Final = 30.0


@dataclass(frozen=True)
class ReadBounds:
    """How much of the client's database one read may spend. Required, never defaulted.

    No default anywhere, and that is the enforcement rather than an inconvenience: the right
    row cap is a property of one client's database and hardware, and a module-level default
    applied on a caller's behalf would be an inference presented as a declaration.
    `projection.RefreshPromise` refuses a defaulted interval for the same reason.

    Both bounds are capped as well as required, because a bound that can be set to anything is
    a bound in name. See `AN_UNBOUNDED_READ_IS_A_QUERY_AGAINST_SOMEBODY_ELSES_BUSINESS`.
    """

    max_rows: int
    timeout_seconds: float

    def __post_init__(self) -> None:
        if self.max_rows <= 0:
            msg = (
                f"a row cap of {self.max_rows} is not a cap; zero is what "
                "DatabaseTransport.plan reads as no limit at all, which on the client's "
                "production database is the whole view"
            )
            raise LaravelError(msg)
        if self.max_rows > MAX_ROWS_EVER:
            msg = (
                f"a row cap of {self.max_rows} is past the {MAX_ROWS_EVER} this connector "
                "will declare; a read that size is a report rather than an answer, and it "
                "belongs in a paced backfill"
            )
            raise LaravelError(msg)
        if self.timeout_seconds <= 0:
            msg = (
                f"a time bound of {self.timeout_seconds} is not a bound. "
                f"{AN_UNBOUNDED_READ_IS_A_QUERY_AGAINST_SOMEBODY_ELSES_BUSINESS}"
            )
            raise LaravelError(msg)
        if self.timeout_seconds > MAX_TIMEOUT_SECONDS:
            msg = (
                f"a time bound of {self.timeout_seconds}s is past the {MAX_TIMEOUT_SECONDS}s "
                "this connector will declare; past it the read has stopped being a query"
            )
            raise LaravelError(msg)


@dataclass(frozen=True)
class BoundedRead:
    """One read of one view: which columns, which rows, and what it may spend.

    The value the executor is handed, and deliberately the only one. It cannot be constructed
    without a positive row cap, so there is no moment at which an unbounded read of the
    client's database exists as a value in this process, which is the shape
    `projection.ProjectedRecord` uses about its own twelve-field cap and for the same reason:
    a check that runs afterwards runs after the thing existed.

    `timeout_seconds` is carried and not enforced. Whoever executes sets the driver's timeout
    from it, and naming it here means a read cannot be issued without somebody having chosen a
    number. `transports.THE_SANDBOX_IS_NOT_IN_THIS_MODULE` draws the same line, and it matters
    more here: this is the bound that protects a database we do not own.
    """

    entity: str
    plan: ViewRead
    columns: tuple[str, ...]
    timeout_seconds: float

    def __post_init__(self) -> None:
        if self.plan.limit <= 0:
            msg = (
                f"a read of {self.plan.view} carries limit {self.plan.limit}, which is the "
                "whole view. "
                f"{AN_UNBOUNDED_READ_IS_A_QUERY_AGAINST_SOMEBODY_ELSES_BUSINESS}"
            )
            raise LaravelError(msg)
        if self.timeout_seconds <= 0:
            msg = (
                f"a read of {self.plan.view} carries no time bound; a query with a row cap "
                "and no time bound still scans the whole view to find the first rows"
            )
            raise LaravelError(msg)
        if not self.columns:
            msg = (
                f"a read of {self.plan.view} names no columns; an empty column list is how a "
                "statement ends up selecting everything the view offers"
            )
            raise LaravelError(msg)


# ----------------------------------------------------------- the connection (M11.2.3)
#: The longest host name DNS carries, and the pattern of one of its labels (RFC 1123).
_HOST_MAX: Final = 253
_HOST_LABEL: Final = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

#: The highest port a TCP address has.
MAX_PORT: Final = 65_535


def _address_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The address a host is written as, or None for a name."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_host(host: str) -> bool:
    """A lower-case host name of RFC 1123 labels, or an address, and nothing else.

    Nothing else means no scheme, no port, no user and no path: a host setting that carried
    `user@` or `:3306` would be a second place for what the port and the credential settings say,
    and the one read first would decide.
    """
    if _address_literal(host) is not None:
        return True
    if not host or len(host) > _HOST_MAX:
        return False
    return all(_HOST_LABEL.match(label) for label in host.split("."))


def _url_for(host: str, port: int) -> str:
    """The host and port as `brain.tools.fetch.assert_fetchable` reads an address, and only that.

    The scheme is the rule's and nothing is ever sent to this URL: a database is not reached over
    HTTPS. It is how the rule every REST source passes through is asked about this host too,
    rather than written a second time for a database.
    """
    literal = _address_literal(host)
    authority = f"[{host}]" if isinstance(literal, ipaddress.IPv6Address) else host
    return f"https://{authority}:{port}/"


class _NoNames:
    """A resolver that answers nothing, for a host written as an address, which needs none."""

    def resolve(self, host: str) -> tuple[str, ...]:
        del host
        return ()


@dataclass(frozen=True)
class LaravelConnection:
    """One database server, one schema, one set of views, one bound on a read. Decided at connect.

    No driver, no DSN, no session and no credential. `assert_holds_no_credential` runs on the
    class at construction rather than being promised in a comment, so an attribute called
    `password` or `dsn_with_password` fails the first time anybody builds one; see
    `contract.ROTATION_NEEDS_NO_REDEPLOY` for what that buys. A DSN is worth naming
    separately, because it is the ordinary way a database credential ends up in a connector:
    it is a string, it is called a URL, and it has the password in the middle of it.

    The scope and the transport are both built from one declaration, so the two lists
    `assert_scope_covers` compares cannot disagree. That check is still run at connect: it is
    what catches the future edit that gives them separate sources, which is exactly the
    edit that would not look like a permission change in a diff.

    `host` and `port` are where the server is, with no default, because no two companies'
    databases are in the same place. A host written as an address inside a private network is
    refused here unless `private_network` says the database is on one; a host written as a name
    is checked when each read resolves it (`checked_address`). See
    `A_PRIVATE_ADDRESS_IS_THE_CONNECTION_S_OWN_DECISION`.
    """

    schema: str
    bounds: ReadBounds
    host: str
    port: int
    private_network: bool

    def __post_init__(self) -> None:
        assert_holds_no_credential(type(self))
        if not _is_host(self.host):
            msg = (
                f"host {self.host!r} is not a server name or address; it is where the database "
                "is and nothing else, with no scheme, port or user in it"
            )
            raise LaravelError(msg)
        if not 1 <= self.port <= MAX_PORT:
            msg = f"port {self.port} is not a TCP port"
            raise LaravelError(msg)
        if _address_literal(self.host) is not None and not self.private_network:
            try:
                assert_fetchable(_url_for(self.host, self.port), _NoNames())
            except UnsafeAddressError as inside:
                msg = (
                    f"host {self.host!r} is an address inside a private network, and this "
                    "connection does not say its database is on one. "
                    f"{A_PRIVATE_ADDRESS_IS_THE_CONNECTION_S_OWN_DECISION}"
                )
                raise LaravelError(msg) from inside
        for view in self.views():
            assert_is_a_view(view)
        # Constructing both is the check. `ConnectorScope` refuses a selector that narrows
        # nothing and `DatabaseTransport` refuses an unqualified name; restating either rule
        # here would be a second opinion about what those words mean.
        assert_scope_covers(self.transport(), self.scope())

    def view_for(self, entity: str) -> str:
        """The one view this entity is read from, qualified by this connection's schema."""
        obj = VIEW_OBJECT_FOR.get(entity)
        if obj is None:
            msg = (
                f"this connector reads {sorted(VIEW_OBJECT_FOR)} and was asked for {entity!r}. "
                f"{A_VIEW_IS_A_CONTRACT_AND_A_TABLE_IS_NOT}"
            )
            raise LaravelError(msg)
        return f"{self.schema}.{obj}"

    def views(self) -> tuple[str, ...]:
        """Every view this connection reaches, sorted. The allowlist and the scope alike."""
        return tuple(sorted(self.view_for(entity) for entity in VIEW_OBJECT_FOR))

    def scope(self) -> ConnectorScope:
        """What this connector was connected to: these views, named, and nothing else."""
        return ConnectorScope(resource_kind="view", selectors=self.views())

    def transport(self) -> DatabaseTransport:
        """The allowlist, as the transport that refuses everything else by string equality."""
        return DatabaseTransport(views=self.views())

    def admits(self, view: str) -> bool:
        """Whether this connection reaches one view. Exact membership, never a prefix."""
        return self.scope().admits(view)


def checked_address(connection: LaravelConnection, *, resolver: Resolver) -> str:
    """The address one read connects to, resolved now and checked (M11.6.1).

    Without `private_network`, the answer is `brain.tools.fetch.assert_fetchable`'s: every address
    the host resolves to is checked and the first is handed back, so the read connects to what was
    checked rather than resolving the name a second time. With it, the host is resolved and the
    first answer taken, whatever network it is in; a host that resolves to nothing is refused
    either way. Raises `UnsafeAddressError`, which the worker records as the address refused. See
    `A_PRIVATE_ADDRESS_IS_THE_CONNECTION_S_OWN_DECISION`.

    What the setting admits that the rule would not, and why that is enough: a MySQL client waits
    for the server to speak first, so a connection pointed at a web service on a private address
    sends that service nothing but a TCP handshake and times out.
    """
    if not connection.private_network:
        return assert_fetchable(_url_for(connection.host, connection.port), resolver).address
    if _address_literal(connection.host) is not None:
        return connection.host
    answers = tuple(resolver.resolve(connection.host))
    if not answers:
        msg = f"{connection.host!r} resolves to nothing"
        raise UnsafeAddressError(msg)
    return answers[0]


def read_plan(
    connection: LaravelConnection,
    entity: str,
    *,
    filters: tuple[tuple[str, str], ...] = (),
    limit: int = 0,
) -> BoundedRead:
    """One bounded read of one allowlisted view, or a refusal (M11.1.4, M11.6.1).

    Three things happen and the order is the argument.

    **The entity resolves to a view through a total mapping.** There is no path here that
    takes a view name from a caller, so the equality check in `DatabaseTransport.plan` is
    reached with a string this module produced.

    **Every filter names a declared column.** Refused rather than dropped: see
    `A_DROPPED_FILTER_WIDENS_A_READ`.

    **The limit is clamped rather than refused.** A caller asking for more than the cap is not
    making a mistake, they are asking for something this connector will not do to somebody
    else's production database, and the result comes back marked `truncated`, which is the
    same shape a source-side ceiling produces and which the abstention path already reads.
    Refusing instead would teach callers to ask for exactly the cap, which produces the
    identical read with nothing saying it was cut short. A limit of zero means the caller did
    not say, and takes the cap; a negative limit is left to `DatabaseTransport.plan`, which
    already refuses it, so there is one refusal rather than two.
    """
    columns = columns_for(entity)
    unknown = sorted({key for key, _ in filters} - set(columns))
    if unknown:
        msg = (
            f"a read of {entity} filters on {unknown}, which this connector does not select. "
            f"{A_DROPPED_FILTER_WIDENS_A_READ}"
        )
        raise LaravelError(msg)
    capped = connection.bounds.max_rows if limit == 0 else min(limit, connection.bounds.max_rows)
    plan = connection.transport().plan(connection.view_for(entity), filters=filters, limit=capped)
    return BoundedRead(
        entity=entity,
        plan=plan,
        columns=columns,
        timeout_seconds=connection.bounds.timeout_seconds,
    )


# ----------------------------------------------------- the projection (M11.4.2, M11.4.3)
def projection_for(entity: str, *, visibility: Scope) -> ProjectedEntity:
    """What is kept locally about one entity kind, and who the source says may read it.

    `visibility` has no default and this module refuses to invent one. See
    `THE_VIEW_IS_THE_UNIT_OF_ACCESS`: MySQL grants on a view rather than on a row of one, the
    row filtering is inside the view definition where the client wrote it, and the predicate
    that reproduces it can only come from whoever read that definition.
    `manifest.ProjectedEntity` already refuses an unrestricted predicate, because a projection
    stored with none has discarded the source's permission model rather than narrowed it.

    One refusal is added on top, and it is the one a database makes possible. A predicate over
    a column this connector does not project compiles to a lookup on a field that never
    arrives, which matches nothing, for ever, and reads exactly like a client with no records.
    That is not hypothetical here: the column names come from a view definition the client
    maintains, and a renamed column is the ordinary way it happens. The rule is general and
    lives here rather than in `manifest` because this is the connector it bites; if a second
    one needs it, it moves.
    """
    declared = PROJECTED_FIELDS.get(entity)
    if declared is None:
        msg = f"this connector projects {sorted(PROJECTED_FIELDS)} and was asked for {entity!r}"
        raise LaravelError(msg)
    assert_columns_are_selectable(entity, (f.name for f in declared))
    names = {f.name for f in declared}
    outside = sorted({clause.field for clause in visibility.clauses} - names)
    if outside:
        msg = (
            f"{entity}'s visibility predicate tests {outside}, which this connector does not "
            f"project; a predicate over a column that never arrives matches nothing for ever "
            f"and reads as a client with no records. {THE_VIEW_IS_THE_UNIT_OF_ACCESS}"
        )
        raise LaravelError(msg)
    return ProjectedEntity(
        entity=entity,
        fields=declared,
        change_signal=ChangeSignal.UPDATED_SINCE,
        visibility=visibility,
    )


def subscription(*, notify_within: timedelta, reconcile_every: timedelta) -> ChangeSubscription:
    """How this source tells us a row moved, declared honestly (M11.4.6).

    `UPDATED_SINCE` and not `CDC`, though a database is the one source where change data
    capture is technically available. Reading the binary log needs `REPLICATION SLAVE` on the
    client's server, which is not a grant anybody gives a reporting integration, and declaring
    a mechanism we were not granted would put a promise in the manifest that nothing keeps.
    The cursor is `updated_at`, which Laravel's `timestamps()` puts on nearly every model.

    `DeletionCheck.ID_SWEEP`, and the argument is worse here than the general one. A cursor
    cannot see a deletion anywhere, because a removed row is one it never mentions again. In a
    Laravel schema it is doubly hidden: `SoftDeletes` sets `deleted_at` rather than removing
    the row, so a view filtering `deleted_at IS NULL` turns a soft delete into exactly the
    same silence as a hard one, and the row's `updated_at` moved at the moment we stopped
    being able to see it. So the only way a removal is ever learned is enumerating the ids the
    views still return, which is the one option a read-only credential has.

    Both intervals are required, matching `ChangeSubscription`'s own refusal to default them:
    a defaulted reconciliation interval is a projection nobody argued for.
    """
    return ChangeSubscription(
        source=CONNECTOR_NAME,
        entity=ENTITY_CLIENT,
        kind=ChangeSignal.UPDATED_SINCE,
        notify_within=notify_within,
        reconcile_every=reconcile_every,
        deletion_check=DeletionCheck.ID_SWEEP,
    )


def refresh_promise(*, reconcile_every: timedelta) -> RefreshPromise:
    """What the source has undertaken, at the interval the reconciliation pass keeps.

    The pass and not the cursor's period, which is `ChangeSubscription.promise`'s rule read
    off rather than restated: `last_seen_at` moves when a record is seen, a cursor does not
    mention a row nobody edited, so the full pass is the only thing that refreshes a quiet
    row.
    """
    return RefreshPromise(signal=ChangeSignal.UPDATED_SINCE, interval=reconcile_every)


def projected_record(
    entity: str, row: Mapping[str, Any], *, last_seen_at: datetime
) -> ProjectedRecord | None:
    """One projected row, built from what was declared rather than copied from what arrived.

    A fresh mapping over the declared fields, which is the second half of
    `WHAT_THE_DECLARATION_DOES_NOT_NAME_DOES_NOT_ARRIVE`. `contract_value` is selected on
    every client read and cannot land here even so, because a build cannot carry what it does
    not name and a copy would carry it the day somebody adds a column.

    A declared field the row does not hold contributes nothing rather than a null, and a row
    with no id returns None, mirroring `transports.normalise`: a record that cannot be named
    cannot be refreshed, cited or matched to itself on the next pass.
    """
    declared = PROJECTED_FIELDS.get(entity)
    if declared is None:
        msg = f"this connector projects {sorted(PROJECTED_FIELDS)} and was asked for {entity!r}"
        raise LaravelError(msg)
    raw_id = row.get(ID_COLUMN)
    if not isinstance(raw_id, str | int) or not str(raw_id).strip():
        return None
    fields: dict[str, ProjectedValue] = {}
    for field in declared:
        if field.name not in row:
            continue
        # Passed through rather than coerced. A value that is not a pointer is refused by
        # `ProjectedRecord` with the argument attached, and stringifying it here would turn a
        # nested object into a short label and defeat `A_NESTED_OBJECT_IS_NOT_ONE_FIELD`.
        fields[field.name] = row[field.name]
    return ProjectedRecord(
        source=CONNECTOR_NAME,
        entity=entity,
        source_id=str(raw_id),
        last_seen_at=last_seen_at,
        fields=fields,
    )


# --------------------------------------------------------- the classifications (M4.2.1)
#: Every column this connector can return, and the capability that reaches it.
#:
#: `contract_value` is RESTRICTED and is the point of the table: it is money, it is what the
#: company canaries protect, and it is returnable live to somebody holding
#: `read:client.contract_value` while never being storable.
#:
#: `manager_id` is INTERNAL rather than CONFIDENTIAL. It names which member of staff owns the
#: relationship, which is the ordinary content of a project conversation, and classifying it
#: higher would withhold the join that makes "who looks after this client" answerable at all.
#:
#: Nothing classifies an email, a phone number or a password hash, and that is the answer
#: rather than an omission: they are not selected, so there is nothing to classify, and
#: default-deny would withhold them from everybody even if a row arrived carrying one.
LARAVEL_FIELD_RULES: Final[tuple[FieldRule, ...]] = (
    FieldRule.of(ENTITY_CLIENT, "name", "read:client.name", Classification.INTERNAL),
    FieldRule.of(ENTITY_CLIENT, "status", "read:client.status", Classification.INTERNAL),
    FieldRule.of(ENTITY_CLIENT, "department", "read:client.department", Classification.INTERNAL),
    FieldRule.of(ENTITY_CLIENT, "manager_id", "read:client.manager_id", Classification.INTERNAL),
    FieldRule.of(ENTITY_CLIENT, CURSOR_COLUMN, "read:client.updated_at", Classification.INTERNAL),
    FieldRule.of(
        ENTITY_CLIENT,
        "contract_value",
        "read:client.contract_value",
        Classification.RESTRICTED,
    ),
    FieldRule.of(ENTITY_USER, "display_name", "read:user.display_name", Classification.INTERNAL),
    FieldRule.of(ENTITY_USER, "department", "read:user.department", Classification.INTERNAL),
    FieldRule.of(ENTITY_USER, "status", "read:user.status", Classification.INTERNAL),
    FieldRule.of(ENTITY_USER, CURSOR_COLUMN, "read:user.updated_at", Classification.INTERNAL),
)


def laravel_field_policy() -> FieldPolicy:
    """What this connector's columns require, as a policy fragment somebody merges."""
    return FieldPolicy(rules=LARAVEL_FIELD_RULES)


def assert_declarations_agree() -> None:
    """The column list, the projection and the policy, checked against each other (M11.4.5).

    Three lists edited by three different people at three different times, and every
    disagreement between them is invisible in review and silent at runtime. A selected column
    nothing classifies is withheld from everybody by default-deny, which is safe and pointless:
    it crosses the wire out of the client's database and travels into a trace for nothing. A
    projected field nothing selects is a column that never arrives, so a filter on it silently
    matches nothing, which reads as a client with no records.
    """
    policy = laravel_field_policy()
    problems: list[str] = []
    for entity in ENTITIES:
        selected = set(selected_columns(entity))
        projected = {f.name for f in PROJECTED_FIELDS[entity]}
        unclassified = sorted(name for name in selected if not policy.governs(entity, name))
        if unclassified:
            problems.append(
                f"  - {entity} selects {unclassified}, which nothing classifies; default-deny "
                "withholds them from everybody, so they leave the client's database for nothing"
            )
        unselected = sorted(projected - selected)
        if unselected:
            problems.append(
                f"  - {entity} projects {unselected}, which nothing selects; the column never "
                "arrives, so a filter on it silently matches nothing"
            )
    if problems:
        listed = "\n".join(problems)
        msg = f"this connector's declarations disagree:\n{listed}"
        raise LaravelError(msg)


# ------------------------------------------------------------------ the manifest (M11.1.7)
LARAVEL_TOOLS: Final[tuple[ToolDeclaration, ...]] = (
    ToolDeclaration(
        name="laravel.read_clients",
        description=(
            "Clients in the portal database: name, status, servicing department, account "
            "manager and when the record last changed. Read-only, through views the client "
            "controls, and the contract value is fetched live rather than stored."
        ),
        entity=ENTITY_CLIENT,
        side_effect=SideEffect.NONE,
        identity_mode=IdentityMode.SERVICE,
    ),
    ToolDeclaration(
        name="laravel.read_users",
        description=(
            "Staff records in the portal database: display name, department, status and when "
            "the record last changed. Read-only, and no contact details, identity numbers or "
            "credentials of any kind."
        ),
        entity=ENTITY_USER,
        side_effect=SideEffect.NONE,
        identity_mode=IdentityMode.SERVICE,
    ),
)


def laravel_manifest(
    connection: LaravelConnection,
    *,
    ref: SecretRef,
    visibility: Mapping[str, Scope],
    version: str = MANIFEST_VERSION,
) -> ConnectorManifest:
    """Everything this connector declares, in one value that can be hashed and pinned.

    `IdentityMode.SERVICE` rather than the DELEGATED default, and it is the honest declaration
    rather than a preference: a database connection is one credential, and nobody in this
    company has a personal MySQL login that maps to their principal. The consequence is stated
    in `brain.tools.registry`, which refuses a SERVICE tool registered without a scope
    predicate, because the source will not narrow it for us. The predicates here are the ones
    the projections store.

    The binding is read-only by not saying otherwise, which is `CredentialBinding`'s default
    and the whole of `A_WRITE_GRANT_NAMES_SOMEBODY`. There is no version of this connector
    that writes: the credential slot is a database user with SELECT on views, and a view is
    generally not writable anyway, so a write tool here would fail at the source during
    somebody's request having looked installable all along.

    `ceiling` names this connector, whose figure in `brain.ops.limits` is this product's own
    pace rather than a vendor's. See `THERE_IS_NO_MEASURED_CEILING_HERE`.
    """
    assert_declarations_agree()
    missing = sorted(set(ENTITIES) - set(visibility))
    if missing:
        msg = (
            f"no visibility predicate was supplied for {missing}; the view is the unit of "
            f"access here and only whoever read its definition can state the predicate. "
            f"{THE_VIEW_IS_THE_UNIT_OF_ACCESS}"
        )
        raise LaravelError(msg)
    return ConnectorManifest(
        name=CONNECTOR_NAME,
        version=version,
        transport=TransportKind.DATABASE,
        scope=connection.scope(),
        credential=CredentialBinding(ref=ref, mode=AccessMode.READ_ONLY),
        tools=LARAVEL_TOOLS,
        projections=tuple(
            projection_for(entity, visibility=visibility[entity]) for entity in ENTITIES
        ),
        ceiling=CEILING_NAME,
    )


# ------------------------------------------------------ what one read produced (M11.5.5)
class DatabaseFault(enum.StrEnum):
    """What a read of a view can fail as. Four, and they are not four HTTP statuses.

    Named for what the server actually does rather than mapped onto somebody else's
    vocabulary, because the two that matter here have no HTTP equivalent: a grant that no
    longer covers a view and a view that is no longer there are both "the contract moved", and
    neither is a 404 in any useful sense.
    """

    #: The grant does not cover this view, MySQL 1142 and 1143, or the user's password is no
    #: longer the one the vault holds, MySQL 1045: the database declining this connector either way.
    ACCESS_DENIED = "access_denied"
    #: The view is not there: dropped, renamed, or never created. MySQL 1146.
    UNKNOWN_VIEW = "unknown_view"
    #: Our own time bound fired and the read was stopped.
    TIMED_OUT = "timed_out"
    #: No connection, too many connections, the server went away.
    UNAVAILABLE = "unavailable"


#: What each fault means in the platform's own outcome vocabulary. Total on purpose, and a
#: test asserts it covers the enum: a `dict.get` with a default would let a fifth fault be
#: added and classified as whatever the default said, which for "is this the source's health
#: or our installation" is the answer that pages the wrong person at three in the morning.
#:
#: `UNKNOWN_VIEW` is REJECTED and never an absence. See `A_MISSING_VIEW_IS_A_WITHDRAWN_CONTRACT`.
OUTCOME_FOR_FAULT: Final[Mapping[DatabaseFault, CallOutcome]] = MappingProxyType(
    {
        DatabaseFault.ACCESS_DENIED: CallOutcome.REJECTED,
        DatabaseFault.UNKNOWN_VIEW: CallOutcome.REJECTED,
        DatabaseFault.TIMED_OUT: CallOutcome.UNAVAILABLE,
        DatabaseFault.UNAVAILABLE: CallOutcome.UNAVAILABLE,
    }
)

#: What the trace records for each fault. `NOT_SERVING` for both refusals because
#: `FailureReason` has no member for "the source withdrew the contract", and inventing one in
#: another module's enum is not this connector's decision: this connector is not serving
#: requests until somebody restores the grant or the view, which is the nearest true
#: statement, and `detail` carries which of the two it was.
REASON_FOR_FAULT: Final[Mapping[DatabaseFault, FailureReason]] = MappingProxyType(
    {
        DatabaseFault.ACCESS_DENIED: FailureReason.NOT_SERVING,
        DatabaseFault.UNKNOWN_VIEW: FailureReason.NOT_SERVING,
        DatabaseFault.TIMED_OUT: FailureReason.TIMEOUT,
        DatabaseFault.UNAVAILABLE: FailureReason.TRANSPORT,
    }
)

DETAIL_FOR_FAULT: Final[Mapping[DatabaseFault, str]] = MappingProxyType(
    {
        DatabaseFault.ACCESS_DENIED: DETAIL_ACCESS_DENIED,
        DatabaseFault.UNKNOWN_VIEW: DETAIL_VIEW_MISSING,
        DatabaseFault.TIMED_OUT: DETAIL_TIMED_OUT,
        DatabaseFault.UNAVAILABLE: DETAIL_UNAVAILABLE,
    }
)


#: Why an error number this connector does not recognise is read as the database not answering.
AN_UNRECOGNISED_DATABASE_ERROR_IS_NOT_AN_ANSWER: Final = (
    "An error number outside the table below is neither of the two withdrawn contracts, "
    "which have documented numbers of their own, and it is never an empty view. It is read "
    "as the database not answering this read: DOWN, like both refusals, so nobody is paged "
    "less for it, and no rows can be reported from it."
)

#: MySQL's documented error numbers for the four faults, from the server and client error
#: references. 1142 and 1143 are the grant; 1045 is the login refused, which is the password the
#: vault holds no longer being the user's; 1146 is the view gone; 3024 is our own
#: `max_execution_time`, and 1969 is MariaDB's own number for its `max_statement_time`, which
#: `brain.ops.laravel_reader` sets on a server that has no `max_execution_time`; the rest are a
#: connection that could not be made or was lost.
MYSQL_ERRNO_FAULTS: Final[Mapping[int, DatabaseFault]] = MappingProxyType(
    {
        1142: DatabaseFault.ACCESS_DENIED,
        1143: DatabaseFault.ACCESS_DENIED,
        1045: DatabaseFault.ACCESS_DENIED,
        1146: DatabaseFault.UNKNOWN_VIEW,
        3024: DatabaseFault.TIMED_OUT,
        1969: DatabaseFault.TIMED_OUT,
        1040: DatabaseFault.UNAVAILABLE,
        2002: DatabaseFault.UNAVAILABLE,
        2003: DatabaseFault.UNAVAILABLE,
        2006: DatabaseFault.UNAVAILABLE,
        2013: DatabaseFault.UNAVAILABLE,
    }
)


def fault_for_mysql_error(errno: int) -> DatabaseFault:
    """The fault a MySQL error number is, so a reader hands over a `ViewReply` and not a guess.

    The one translation between a driver's exception and this module's vocabulary, written
    here so a live reader and a recording replayed in a test go through the same table. See
    `AN_UNRECOGNISED_DATABASE_ERROR_IS_NOT_AN_ANSWER` for the number nobody listed.
    """
    return MYSQL_ERRNO_FAULTS.get(errno, DatabaseFault.UNAVAILABLE)


class LaravelOutcome(enum.StrEnum):
    """The four answers a read can produce, and they stay four.

    `ABSENT` is a fact about the client's business. `REFUSED` is the database declining, which
    is a job for whoever owns the connection and the client's DBA. `UNREACHABLE` is the
    database not answering. A person is told the same thing for the last two, because which of
    our systems is unwell is not theirs to act on, and the trace keeps the difference.
    """

    PRESENT = "present"
    ABSENT = "absent"
    REFUSED = "refused"
    UNREACHABLE = "unreachable"

    @property
    def answered(self) -> bool:
        """Whether the database answered at all. The only place the four collapse to two."""
        return self in (LaravelOutcome.PRESENT, LaravelOutcome.ABSENT)


@dataclass(frozen=True)
class ViewReply:
    """What one read produced, as a value this module never constructs.

    The shape a reader hands back, deliberately holding raw rows rather than records, so that
    every rule below is testable without a driver, a socket or a database. `freshdesk.Reply`
    is the same idea against a recorded HTTP exchange.

    `app_status` is the narrow seam described in the module docstring. The one recorded
    Laravel exchange is a 500 from the application's own internal endpoint rather than a
    database error, and it is still this source failing; carrying the status here lets that
    recording be interpreted without anybody inventing a MySQL error code for it. It is
    refused below 400 because this connector does not read the application's HTTP surface: a
    status here is only ever how a failure was recorded.
    """

    rows: tuple[Mapping[str, Any], ...] = ()
    fault: DatabaseFault | None = None
    app_status: int | None = None

    def __post_init__(self) -> None:
        if self.fault is not None and self.app_status is not None:
            msg = (
                "a reply carries both a database fault and an application status, which are "
                "two accounts of one read; whichever was checked second would decide"
            )
            raise LaravelError(msg)
        if self.rows and (self.fault is not None or self.app_status is not None):
            msg = (
                "a failed reply carries rows; rows that arrived before a failure are a "
                "partial read of somebody's database being reported as an answer"
            )
            raise LaravelError(msg)
        if self.app_status is not None and self.app_status < 400:
            msg = (
                f"a reply carries application status {self.app_status}; this connector reads "
                "views and not the application's HTTP surface, so a status here is only ever "
                "how a failure was recorded"
            )
            raise LaravelError(msg)


@dataclass(frozen=True)
class LaravelReply:
    """One read's result: what it was, and rows only where there are rows.

    The constructor is the guarantee. A failed reply cannot carry rows and cannot carry a read
    time, so "answer the outage from the last good read" is not something a caller can express
    here rather than something they are asked not to do. A read time on a failure would be
    worse than the rows: `assess_freshness` would date it and report the answer as current.
    """

    outcome: LaravelOutcome
    call: CallOutcome
    rows: TypedResult[SourceRecord] | None = None
    fetched_at: str = ""
    reason: FailureReason | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if self.outcome.answered:
            self._assert_answered_consistently()
            return
        if self.rows is not None or self.fetched_at:
            msg = (
                f"a {self.outcome} reply was given rows or a read time; 'nothing is owing' and "
                "'I could not read it' are opposite answers and only one of them is "
                "actionable"
            )
            raise LaravelError(msg)
        if self.reason is None:
            msg = (
                f"a {self.outcome} reply names no failure reason; the trace is the only place "
                "a refusal and an outage stay distinguishable, and it is assembled from this"
            )
            raise LaravelError(msg)

    def _assert_answered_consistently(self) -> None:
        """Present and absent are decided by what came back, and a capped read says so."""
        if self.rows is None:
            msg = (
                f"a {self.outcome} reply carries no rows; an answered read produces a result "
                "even when the result is empty, and None here would make an absence "
                "indistinguishable from a failure"
            )
            raise LaravelError(msg)
        has_records = bool(self.rows.records)
        if has_records is not (self.outcome is LaravelOutcome.PRESENT):
            msg = (
                f"a {self.outcome} reply holds {len(self.rows.records)} record(s); a mismatch "
                "here is an empty result being reported as a full one or the reverse"
            )
            raise LaravelError(msg)
        if self.rows.truncated and self.call is not CallOutcome.TRUNCATED:
            msg = (
                "a reply whose rows were cut short by the row cap is reported as a complete "
                "read; the abstention path branches on TRUNCATED, and a capped read that does "
                "not carry it is a partial answer summarised as all of them"
            )
            raise LaravelError(msg)

    def freshness(self, *, horizon: StalenessHorizon, now: datetime) -> Freshness:
        """How old this is, in `brain.gate.provenance`'s vocabulary and not a second one.

        Unconditional: a failed reply has no read time, so `assess_freshness` returns UNSTATED
        by its own rule about a time it cannot date. A branch here would be a second
        implementation of that rule, and the constructor above is what makes this one enough.
        """
        return assess_freshness(self.fetched_at, horizon=horizon, now=now)

    def failure(self) -> SourceFailure | None:
        """This reply as the federation layer's failure record, or None when it answered."""
        if self.outcome.answered or self.reason is None:
            return None
        return SourceFailure(connector=CONNECTOR_NAME, reason=self.reason, detail=self.detail)

    def notice(self, *, disclosable: frozenset[str]) -> str:
        """What the asker is told. Names this source only if their catalogue already did.

        Delegated whole to `federation.PartialAnswer.notice`, so a database outage produces
        exactly the sentence every other unreachable source produces and the two are
        indistinguishable to somebody probing. Restating it here would be a second disclosure
        rule, and the generous copy is the one that gets read.
        """
        failure = self.failure()
        if failure is None:
            return ""
        return PartialAnswer(failed=(failure,)).notice(disclosable=disclosable)

    def trace_line(self) -> str:
        """The full statement, for an auditor. Keeps what the notice drops.

        Safe for the reason `federation.PartialAnswer.trace_lines` is safe: a trace is read by
        somebody already entitled to know what this system connects to, and nothing here can
        put this string into a channel payload. It carries no value from the database either:
        every detail is a constant in this module, so a client's name cannot arrive in one by
        way of a filter, and neither can the statement a MySQL error would have quoted.
        """
        count = len(self.rows.records) if self.rows is not None else 0
        return f"{CONNECTOR_NAME}: {self.outcome} ({self.call}), {count} record(s), {self.detail}"


def _kept(columns: tuple[str, ...], row: Mapping[str, Any]) -> Mapping[str, Any]:
    """One row rebuilt from the declared columns. A build, never a copy.

    See `WHAT_THE_DECLARATION_DOES_NOT_NAME_DOES_NOT_ARRIVE`. The column list already went
    into the statement, so in production there is usually nothing to drop; this is what makes
    that a property of the value rather than a claim about the executor.
    """
    return {name: row[name] for name in columns if name in row}


def interpret(read: BoundedRead, reply: ViewReply, *, fetched_at: str) -> LaravelReply:
    """One read, as an answer, keeping absent, refused and unreachable apart (M11.5.5).

    The projection happens only on the success branch, deliberately. Building records first
    would run the column list over a failure that has no rows, and an empty build would then
    be indistinguishable from an empty view, which is the whole failure this function exists
    to prevent.

    Truncation is decided by the row cap rather than by `throttle.classify`, and that is not a
    second classifier: `classify` answers what the *source* did, and the cap is ours. The word
    is the same one Freshdesk's hard ceiling gets, because the shape is the same, and using it
    means the abstention path that already branches on `TRUNCATED` does the right thing here
    without learning anything about databases.
    """
    outcome = _call_outcome(reply)
    if outcome is not CallOutcome.OK:
        return _failed(reply, outcome)
    kept = tuple(_kept(read.columns, row) for row in reply.rows)
    truncated = len(reply.rows) >= read.plan.limit
    rows = normalise(
        read.entity,
        kept,
        source=CONNECTOR_NAME,
        fetched_at=fetched_at,
        id_field=ID_COLUMN,
        truncated=truncated,
    )
    return LaravelReply(
        outcome=LaravelOutcome.PRESENT if rows.records else LaravelOutcome.ABSENT,
        call=CallOutcome.TRUNCATED if truncated else CallOutcome.OK,
        rows=rows,
        fetched_at=fetched_at,
        detail=DETAIL_CAPPED if truncated else DETAIL_ANSWERED,
    )


def _call_outcome(reply: ViewReply) -> CallOutcome:
    """What this reply was, in the platform's vocabulary, from whichever half carried it.

    The application status goes through `throttle.classify` rather than through a branch of
    this module's own, so a 500 recorded against our own system is classified by exactly the
    rule every other connector's failures are classified by. Being in-house is not a reason to
    trust an error response, and it is not a reason to interpret one differently either.
    """
    if reply.fault is not None:
        return OUTCOME_FOR_FAULT[reply.fault]
    if reply.app_status is not None:
        return classify(status=reply.app_status)
    return CallOutcome.OK


def _failed(reply: ViewReply, outcome: CallOutcome) -> LaravelReply:
    """A failure as a reply, with the reason and the detail the trace keeps."""
    if reply.fault is not None:
        reason = REASON_FOR_FAULT[reply.fault]
        detail = DETAIL_FOR_FAULT[reply.fault]
    else:
        reason = FailureReason.QUOTA if outcome is CallOutcome.QUOTA else FailureReason.TRANSPORT
        detail = DETAIL_APPLICATION_FAILED
    return LaravelReply(
        outcome=(
            LaravelOutcome.REFUSED
            if outcome is CallOutcome.REJECTED
            else LaravelOutcome.UNREACHABLE
        ),
        call=outcome,
        reason=reason,
        detail=detail,
    )


# ------------------------------------------------------------------ the fetch (M11.1.1)
class ViewReader(Protocol):
    """Whatever runs one bounded read and hands back what came out.

    A protocol rather than a connection, so this module holds no client, no driver import and
    no DSN. The split is the one `brain.ops.limits` and `brain.knowledge.rows` are both built
    on, and the cases that matter here are the ones that cannot be arranged against a real
    database: a view that was dropped this morning, a grant that was narrowed, a read that
    passed its bound.
    """

    def rows(self, read: BoundedRead) -> ViewReply: ...


def connector_fetch(
    connection: LaravelConnection,
    entity: str,
    *,
    reader: ViewReader,
    fetched_at: str,
) -> Callable[[FetchRequest], TypedResult[SourceRecord]]:
    """This connection's read side, as the one shape a connector's fetch may take (M11.1.1).

    Two rules from two modules are asserted on the closure, both by reading its signature and
    neither by trusting its body. `contract.assert_fetches_only` refuses a fetch that could be
    handed the caller's grants, so no permission question can be answered here.
    `rows.assert_takes_no_sql` refuses a fetch that could be handed a fragment, so there is
    nothing for an interpolation to interpolate. The second is unusual on a connector and is
    exactly right on this one: this is the connector that reaches a database.

    The entity is bound at construction and a request naming a different one is refused before
    a plan exists, so nothing is read from the wrong view. Refused rather than answered from
    the bound entity, which is the tempting version and is worse: it returns the wrong records
    under the name of the ones that were asked for, and every test passes because the rows are
    real.

    A failed read raises rather than returning an empty result. `ConnectorFetch` returns a
    `TypedResult`, and an empty one is what an empty view produces, so a failure that returned
    one would collapse the distinction this module spends its length keeping.
    """

    def _fetch(request: FetchRequest) -> TypedResult[SourceRecord]:
        if request.entity != entity:
            msg = (
                f"this fetch reads {entity!r} and was asked for {request.entity!r}; the view "
                "is chosen at construction, and answering from the bound one would return the "
                "wrong records under the name of the ones that were asked for"
            )
            raise LaravelError(msg)
        read = read_plan(connection, entity, filters=request.filters, limit=request.limit)
        reply = interpret(read, reader.rows(read), fetched_at=fetched_at)
        if reply.rows is None:
            raise LaravelDegraded(
                reply.trace_line(), read_outcome=reply.outcome, call_outcome=reply.call
            )
        return reply.rows

    assert_fetches_only(_fetch)
    assert_takes_no_sql(_fetch)
    return _fetch


# ------------------------------------------------------------------- health (M11.1.1)
#: What the last read means for whether this connector may be routed to. Total over
#: `CallOutcome`, so a new member fails the build here rather than being classified by a
#: default.
#:
#: **A refusal is DOWN.** The grant was narrowed or the view was dropped: it was working this
#: morning, somebody has to talk to the client's DBA today, and it cannot answer meanwhile.
#: UNCONFIGURED would file it as an installation task and it would sit in a backlog.
#:
#: **A timeout is DOWN and not DEGRADED.** DEGRADED is usable, which is right for a source
#: that is merely slow. This is somebody else's production database and the last thing we did
#: to it was start a query it could not finish inside our own bound; the safe direction is to
#: stop asking until a person has looked.
#:
#: **QUOTA cannot happen here** and is mapped anyway, because the mapping is total. A database
#: has no rate limiter, and `THERE_IS_NO_MEASURED_CEILING_HERE` is the honest version of that.
HEALTH_FOR_CALL: Final[Mapping[CallOutcome, HealthState]] = MappingProxyType(
    {
        CallOutcome.OK: HealthState.OK,
        CallOutcome.TRUNCATED: HealthState.DEGRADED,
        CallOutcome.QUOTA: HealthState.DEGRADED,
        CallOutcome.REJECTED: HealthState.DOWN,
        CallOutcome.UNAVAILABLE: HealthState.DOWN,
    }
)


def health(reply: LaravelReply | None, *, checked_at: datetime) -> ConnectorHealth:
    """What the last probe found, as a fact with a time on it.

    `checked_at` is a parameter and the state is a fact rather than a live reading, which is
    `ConnectorHealth`'s own argument: a health page showing OK with no time on it keeps
    showing OK after the prober itself has stopped.

    No probe at all is UNCONFIGURED rather than DOWN: a connector nobody has called yet is a
    job for whoever installed it, and DOWN would page somebody about a database that is
    perfectly healthy.

    Every detail is a constant from this module. A health row assembled from a driver's error
    string would carry the statement MySQL quotes back, and therefore a filter value and a
    client's name, into a console with a different audience and a different retention from the
    answer it described.
    """
    if reply is None:
        return ConnectorHealth(
            connector=CONNECTOR_NAME,
            state=HealthState.UNCONFIGURED,
            checked_at=checked_at,
            detail=DETAIL_NEVER_PROBED,
        )
    return ConnectorHealth(
        connector=CONNECTOR_NAME,
        state=HEALTH_FOR_CALL[reply.call],
        checked_at=checked_at,
        detail=reply.detail,
    )


# ------------------------------------------------------------- no statement is composed
def assert_builds_no_sql() -> None:
    """Refuse this module if any statement in it were composed out of a formatted string.

    Runs `brain.knowledge.rows.assert_no_sql_is_built_by_interpolation` over this module's own
    parsed syntax tree. Over the tree and not the text, which is that function's own argument
    and matters here more than anywhere: two tests in this repository have been satisfied by
    their own docstrings, and a module about SQL safety is exactly the one whose prose
    contains every string a text search would look for.

    Callable at registration rather than only from a test, so the refusal happens where the
    connector is installed. The import is inside the function deliberately: the check belongs
    to the row plane, which brings SQLAlchemy and the projection table with it, and a
    connector should not acquire that import graph for the sake of a self-check it passes.
    """
    from brain.knowledge.rows import assert_no_sql_is_built_by_interpolation

    assert_no_sql_is_built_by_interpolation(sys.modules[__name__])


def assert_views_are_holdable(connection: LaravelConnection) -> None:
    """Every view this connection can produce is one the transport will hold (M11.1.4).

    The relationship this module depends on and does not restate: `assert_is_a_view` is
    stricter than `transports._VIEW_RE` and the two have to stay that way round. If the
    transport's rule ever became the stricter one, a name this module accepted would be
    refused at the seam, during somebody's request, by a module they were not reading.
    """
    try:
        DatabaseTransport(views=connection.views())
    except TransportError as exc:
        msg = (
            f"this connection produces view names the transport will not hold: {exc}; the "
            "check here is meant to be the stricter of the two"
        )
        raise LaravelError(msg) from exc


# ------------------------------------------------------------------ what this connector declares
#: Why a reading exists for a connector that can issue no write.
LARAVEL_THE_CREDENTIAL_IS_READ_ONLY: Final = (
    "laravel_manifest binds its credential read-only and reads views, so no write can be "
    "issued through this connector as built. A view the grant no longer covers and a view "
    "that is gone are both REJECTED there, and so INCONCLUSIVE here: a withdrawn contract is "
    "not an absent row."
)


# ------------------------------------------------- connecting from the console (M11.7.7)
#: The settings Connectors asks for: the database the views live in, where its server is and
#: whether that is a private network, each view's visibility rule and the bound on one read, which
#: `ReadBounds` refuses to default.
SCHEMA_SETTING: Final = "schema"
HOST_SETTING: Final = "host"
PORT_SETTING: Final = "port"
PRIVATE_NETWORK_SETTING: Final = "private_network"
CLIENT_RULE_SETTING: Final = "client_rule"
USER_RULE_SETTING: Final = "user_rule"
MAX_ROWS_SETTING: Final = "max_rows"
TIMEOUT_SETTING: Final = "timeout_seconds"

#: What the private network setting takes, in words, and nothing else. `yes` turns it on.
PRIVATE_NETWORK_ANSWERS: Final[Mapping[str, bool]] = MappingProxyType({"yes": True, "no": False})

#: The port MySQL listens on when nobody chose another. Said in the form's words and never filled
#: in for the person: every setting on this form is typed, so a connection is where somebody said.
MYSQL_PORT: Final = 3306

#: Each view's rule, by the entity it keeps.
RULE_SETTING_FOR: Final[Mapping[str, str]] = MappingProxyType(
    {ENTITY_CLIENT: CLIENT_RULE_SETTING, ENTITY_USER: USER_RULE_SETTING}
)

#: How a view's visibility rule is written on the form, and the whole of the grammar.
A_VIEW_RULE_IS_ONE_FIELD_AND_ITS_VALUES: Final = (
    "A view's visibility rule is one field the view keeps and the value a reader's own scope must "
    "hold for it: department = sales. One clause, because that is what a person reading a view's "
    "definition can check against it, and a field the view does not keep is refused, because a "
    "rule over a column that never arrives matches nothing for ever and reads as a company with no "
    "records."
)

_RULE_EQ: Final = re.compile(r"^\s*([a-z][a-z0-9_]{0,59})\s*=\s*(.+?)\s*$")
_RULE_IN: Final = re.compile(r"^\s*([a-z][a-z0-9_]{0,59})\s+in\s+(.+?)\s*$")
_RULE_VALUE: Final = re.compile(r"^[A-Za-z0-9_.@-]{1,120}$")


def rule_of(text: str) -> Scope:
    """One view's visibility rule, as the form writes it, or `LaravelError` when it is not one.

    See `A_VIEW_RULE_IS_ONE_FIELD_AND_ITS_VALUES`. Whether the field is one the view keeps is
    `projection_for`'s refusal, not a second one here, and whether the index can carry the rule is
    `built_from_the_console`'s (`A_RULE_THE_INDEX_CANNOT_CARRY_IS_REFUSED`). A list (`department
    in sales, marketing`) is still read as one, so that refusal can say what it refused.
    """
    listed = _RULE_IN.match(text)
    equal = None if listed is not None else _RULE_EQ.match(text)
    found = listed or equal
    if found is None:
        msg = f"a rule is a field, = or in, and values. {A_VIEW_RULE_IS_ONE_FIELD_AND_ITS_VALUES}"
        raise LaravelError(msg)
    field, rest = found.groups()
    values = tuple(one.strip() for one in rest.split(",")) if listed else (rest.strip(),)
    if not all(_RULE_VALUE.match(one) for one in values):
        msg = f"a view rule's values are names or codes. {A_VIEW_RULE_IS_ONE_FIELD_AND_ITS_VALUES}"
        raise LaravelError(msg)
    clause = (
        Clause(field=field, op=Op.IN, value=values)
        if listed
        else Clause(field=field, op=Op.EQ, value=values[0])
    )
    return Scope(clauses=(clause,))


def _whole(settings: Mapping[str, str], name: str, *, most: int) -> int:
    """A positive whole number no greater than `most`, or the refusal naming its setting."""
    given = settings.get(name, "").strip()
    if not given.isdigit() or not 1 <= int(given) <= most:
        raise SettingRefusedError(f"not a whole number from 1 to {most}", setting=name)
    return int(given)


def connection_of(settings: Mapping[str, str]) -> LaravelConnection:
    """The connection these settings name, or the refusal naming the setting that was wrong.

    What `built_from_the_console` builds its manifest over and what a read connects with, so the
    connection a person was told is saved and the one the worker reads are one value. The host is
    lower-cased and an IPv6 address may be typed in brackets, because both are how an address is
    ordinarily written; nothing else is adjusted.
    """
    schema = settings.get(SCHEMA_SETTING, "").strip()
    if schema.casefold() in UNBOUNDED_SELECTORS:
        # A database called `all` is a legal name and reads as everything to whoever reads the
        # connection afterwards, so it is refused in front of the person connecting it.
        raise SettingRefusedError("reads as everything", setting=SCHEMA_SETTING)
    answer = settings.get(PRIVATE_NETWORK_SETTING, "").strip().lower()
    private = PRIVATE_NETWORK_ANSWERS.get(answer)
    if private is None:
        raise SettingRefusedError("not yes or no", setting=PRIVATE_NETWORK_SETTING)
    host = settings.get(HOST_SETTING, "").strip().lower().removeprefix("[").removesuffix("]")
    if not _is_host(host):
        raise SettingRefusedError("not a server name or address", setting=HOST_SETTING)
    port = _whole(settings, PORT_SETTING, most=MAX_PORT)
    bounds = ReadBounds(
        max_rows=_whole(settings, MAX_ROWS_SETTING, most=MAX_ROWS_EVER),
        timeout_seconds=float(_whole(settings, TIMEOUT_SETTING, most=int(MAX_TIMEOUT_SECONDS))),
    )
    try:
        return LaravelConnection(
            schema=schema, bounds=bounds, host=host, port=port, private_network=private
        )
    except ConnectorContractError as refused:
        if _address_literal(host) is not None and not private:
            raise SettingRefusedError("a private address", setting=HOST_SETTING) from refused
        raise SettingRefusedError("not a database name", setting=SCHEMA_SETTING) from refused


def built_from_the_console(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
    """The manifest a connection made on the Connectors screen declares (M11.7.7).

    Each setting is judged by the rule the connection already holds it to and a refusal names the
    setting: the server and the database by `connection_of`, each rule by `rule_of`,
    `projection_for` and `A_RULE_THE_INDEX_CANNOT_CARRY_IS_REFUSED`, and the bound by `ReadBounds`,
    which refuses a figure past its cap. Then the manifest is built, which is the check that they
    agree.
    """
    connection = connection_of(settings)
    visibility: dict[str, Scope] = {}
    for entity, name in RULE_SETTING_FOR.items():
        try:
            visibility[entity] = rule_of(settings.get(name, ""))
            projection_for(entity, visibility=visibility[entity])
        except (ConnectorContractError, ValueError) as refused:
            raise SettingRefusedError("not a rule over the view", setting=name) from refused
        if any(clause.op is not Op.EQ for clause in visibility[entity].clauses):
            raise SettingRefusedError(A_RULE_THE_INDEX_CANNOT_CARRY_IS_REFUSED, setting=name)
    return laravel_manifest(connection, ref=ref, visibility=visibility)


# ------------------------------------------------------------ reading it (M11.6.1, M11.9.2)
#: How often the worker reads each view into the index, which is the interval its freshness is
#: judged by. Xero's reconciliation interval, for the same reason: every value is read live when a
#: question needs it, so the index only has to know which records exist and what they are called.
REFRESH_EVERY: Final = timedelta(hours=1)

#: What a record's id may be when it is read live: Laravel's auto-increment integer, or a UUID or
#: ULID. It is bound as a parameter either way; the shape is refused first so a value that is not
#: an id never reaches the database at all.
LIVE_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9-]{1,64}$")

#: What opens one reader for one read: the checked address, the port and the login.
ViewReaderOpener = Callable[[str, int, DatabaseLogin], ViewReader]


def open_mysql(address: str, port: int, login: DatabaseLogin) -> ViewReader:
    """The executor, opened for one read. Imported here so importing this module imports no driver.

    See `brain.ops.laravel_reader`, which is the only module that imports the driver, and the
    module docstring's scope: this module decides, and that one runs the statement.
    """
    from brain.ops.laravel_reader import MySqlViewReader

    return MySqlViewReader(address=address, port=port, login=login)


@dataclass(frozen=True)
class LaravelReading:
    """This connector's `brain.connectors.declaration.ViewReading`: one bounded read per view.

    Holds the opener it is handed and nothing else, so no login outlives the read it was handed
    for: `read` builds the connection from the settings, checks the address, opens one reader and
    runs the read through `connector_fetch`, and the reader goes out of scope when `read` returns.
    A test or an install check hands it an opener over a recorded driver; the shipped declaration
    hands it `open_mysql`.
    """

    opener: ViewReaderOpener = open_mysql

    def entities(self) -> tuple[str, ...]:
        return ENTITIES

    def refresh_interval(self) -> timedelta:
        return REFRESH_EVERY

    def read(
        self,
        request: FetchRequest,
        *,
        settings: Mapping[str, str],
        login: DatabaseLogin,
        resolver: Resolver,
        fetched_at: str,
    ) -> PageReply:
        connection = connection_of(settings)
        address = checked_address(connection, resolver=resolver)
        fetch = connector_fetch(
            connection,
            request.entity,
            reader=self.opener(address, connection.port, login),
            fetched_at=fetched_at,
        )
        try:
            rows = fetch(request)
        except LaravelDegraded as failed:
            return PageReply(call=failed.call_outcome, rows=None)
        return PageReply(call=CallOutcome.TRUNCATED if rows.truncated else CallOutcome.OK, rows=rows)

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        return projected_record(entity, row, last_seen_at=seen_at)


class LaravelLiveLookup:
    """One client or staff record, read from its view while somebody waits (M11.9.2).

    The service's credentials, declared: a database connection is one user, and nobody here has a
    MySQL login of their own that maps to their principal. The read is the scheduled read's,
    narrowed to the record's id, so the same view, columns, row cap and time bound apply.
    """

    def entities(self) -> tuple[str, ...]:
        return ENTITIES

    def identity_mode(self, entity: str) -> IdentityMode:
        del entity
        return IdentityMode.SERVICE

    def arguments_for(self, entity: str, source_id: str) -> Mapping[str, str]:
        if entity not in ENTITIES:
            msg = f"this connector reads {sorted(ENTITIES)} live and was asked for {entity!r}"
            raise LaravelError(msg)
        if not LIVE_ID_PATTERN.match(source_id):
            msg = "a record's id is a number, a UUID or a ULID, and this is none of them"
            raise LaravelError(msg)
        return {ID_COLUMN: source_id}


#: What the Connectors screen asks for. The credential is the read-only user, as a name and a
#: password, kept together in the vault.
CONSOLE: Final = ConsoleForm(
    settings=(
        Setting(
            name=SCHEMA_SETTING,
            label="Database holding the views",
            hint=(
                "The name of the database the two views are in, as your database lists it. The "
                f"views are named {VIEW_OBJECT_FOR[ENTITY_CLIENT]} for clients and "
                f"{VIEW_OBJECT_FOR[ENTITY_USER]} for staff, and nothing else there is read."
            ),
            refused=(
                "That is not a database name. Use lower-case letters, digits and underscores, "
                "as your database lists it."
            ),
        ),
        Setting(
            name=HOST_SETTING,
            label="Database server's address",
            hint=(
                "The name or address this system's server reaches your database at, such as "
                "db.example.com, with no port. If you run a tunnel, its local end, such as "
                "127.0.0.1. There is no default: every company's database is somewhere else."
            ),
            refused=(
                "That is not an address this system may reach. Type a server name such as "
                "db.example.com or an address, with no port; an address inside a private network "
                "is taken only when the database is on a private network."
            ),
        ),
        Setting(
            name=PORT_SETTING,
            label="Database server's port",
            hint=(
                f"The port your database listens on. MySQL's own is {MYSQL_PORT}, so type "
                f"{MYSQL_PORT} unless your database or your tunnel says another. Nothing is "
                "filled in for you."
            ),
            refused=f"Type a port from 1 to {MAX_PORT}.",
        ),
        Setting(
            name=PRIVATE_NETWORK_SETTING,
            label="Database on a private network",
            hint=(
                "Type yes only if your database is on a private network that this system's server "
                "reaches directly or through a tunnel, so its address may be a private one. "
                "Otherwise type no, and a private address is refused, so this connection can "
                "never be used to reach this server's own network."
            ),
            refused="Type yes or no.",
        ),
        Setting(
            name=CLIENT_RULE_SETTING,
            label="Who may be told a client",
            hint=(
                "The rule the client view is kept under, read from its definition: one field it "
                "keeps and its value, such as department = sales. The fields are "
                + ", ".join(one.name for one in CLIENT_PROJECTED)
                + "."
            ),
            refused=(
                "That is not a rule over the client view. Write one field it keeps, =, and one "
                "value, such as department = sales."
            ),
        ),
        Setting(
            name=USER_RULE_SETTING,
            label="Who may be told a staff record",
            hint=(
                "The rule the staff view is kept under, in the same words. The fields are "
                + ", ".join(one.name for one in USER_PROJECTED)
                + "."
            ),
            refused=(
                "That is not a rule over the staff view. Write one field it keeps, =, and one "
                "value, such as department = operations."
            ),
        ),
        Setting(
            name=MAX_ROWS_SETTING,
            label="Most rows one read may return",
            hint=(
                f"A whole number up to {MAX_ROWS_EVER}. Every read of your database stops there, "
                "so a question can never scan it whole."
            ),
            refused=f"Type a whole number from 1 to {MAX_ROWS_EVER}.",
        ),
        Setting(
            name=TIMEOUT_SETTING,
            label="Longest one read may take, in seconds",
            hint=(
                f"A whole number up to {int(MAX_TIMEOUT_SECONDS)}. A read that takes longer is "
                "stopped, so your application is never slowed by a question."
            ),
            refused=f"Type a whole number of seconds from 1 to {int(MAX_TIMEOUT_SECONDS)}.",
        ),
    ),
    credential_label="The read-only database user",
    credential_hint=(
        "The name and password of the database user with SELECT on the allowlisted views only: no "
        "SELECT on tables and no write. They are kept in the vault together and never shown again."
    ),
    build=built_from_the_console,
    credential_shape=CredentialShape.DATABASE_USER,
)


#: The screens that prepare your own database for this system, ending with the form that connects
#: it: where the server is, the database, each view's rule, the bound on a read and the read-only
#: user (M11.7.7). The third is how this system's server reaches the database at all (M11.6.1).
GUIDE: Final = keyed(
    (
        GuideStep(
            key="views",
            title="Write a view for each thing to read",
            text=(
                "In your application's database, create one view for each thing this system should "
                "read, holding only the columns it may see. A view is your own statement of what "
                "may be read, and it changes only when you change it."
            ),
            sketch=Sketch(
                place="Your database",
                heading="Views",
                lines=(
                    SketchLine(LineKind.ITEM, "One view per thing to read", mark=True),
                    SketchLine(LineKind.TEXT, "Only the columns it may see"),
                ),
            ),
        ),
        GuideStep(
            key="user",
            title="Create a read-only database user",
            text=(
                "Create a database user with SELECT on those views only: not on tables, and no "
                "write. A table can gain a column in the next migration, and a grant on it would "
                "read that column the same day."
            ),
            sketch=Sketch(
                place="Your database",
                heading="Users",
                lines=(
                    SketchLine(LineKind.ITEM, "SELECT on the views", mark=True),
                    SketchLine(LineKind.ITEM, "No grant on any table"),
                    SketchLine(LineKind.ITEM, "No write"),
                ),
            ),
        ),
        GuideStep(
            key="reach",
            title="Let this system's server reach the database",
            text=(
                "Your database must accept a connection from this system's server, on its port "
                "only. The usual way is to allow the server's own address, as your hosting "
                "provider lists it, in the database's firewall or security group. Where the "
                "database is on a private network instead, run an SSH tunnel from this system's "
                "server to a machine that reaches it, and type the tunnel's local end as the "
                "server's address with private network set to yes. The tunnel is yours to run and "
                "keep up: this system does not start one."
            ),
            sketch=Sketch(
                place="Your database's firewall",
                heading="Inbound rules",
                lines=(
                    SketchLine(LineKind.ITEM, "Allow this system's server", mark=True),
                    SketchLine(LineKind.TEXT, "On the database's port only"),
                    SketchLine(LineKind.TEXT, "Or an SSH tunnel you run"),
                ),
            ),
        ),
        GuideStep(
            key="connect",
            title="Say where the database is, write each view's rule and give the user here",
            text=(
                "Type the database server's address and port and whether it is on a private "
                "network, the database the views are in, the rule each view is kept under as its "
                "definition says, and the most rows and seconds one read may take, then the "
                "read-only user's name and password, and press Connect Laravel database views."
            ),
            sketch=Sketch(
                place="Company Brain",
                heading="Connect Laravel database views",
                lines=(
                    SketchLine(LineKind.FIELD, "Database", "portal", mark=True),
                    SketchLine(LineKind.FIELD, "Server and port", "db.example.com, 3306", mark=True),
                    SketchLine(LineKind.FIELD, "Private network", "no", mark=True),
                    SketchLine(LineKind.FIELD, "Clients", "department = sales", mark=True),
                    SketchLine(LineKind.FIELD, "Staff", "department = operations", mark=True),
                    SketchLine(LineKind.FIELD, "Most rows, seconds", "500, 10", mark=True),
                    SketchLine(LineKind.FIELD, "User and password", "********", mark=True),
                ),
                button="Connect Laravel database views",
            ),
            asks=(
                SCHEMA_SETTING,
                HOST_SETTING,
                PORT_SETTING,
                PRIVATE_NETWORK_SETTING,
                CLIENT_RULE_SETTING,
                USER_RULE_SETTING,
                MAX_ROWS_SETTING,
                TIMEOUT_SETTING,
                CREDENTIAL_ASK,
            ),
        ),
    )
)


CONNECTOR: Final = ConnectorDeclaration(
    name=CONNECTOR_NAME,
    label="Laravel database views",
    guide=GUIDE,
    console=CONSOLE,
    read_back=ReadBack(
        reading=classified_reading,
        recorded=(
            "LARAVEL-500",
            "LARAVEL-rows-clients",
            "LARAVEL-rows-users",
            "LARAVEL-rows-at-cap",
            "LARAVEL-1142",
            "LARAVEL-1146",
            "LARAVEL-3024",
            "LARAVEL-2006",
        ),
        findings=(LARAVEL_THE_CREDENTIAL_IS_READ_ONLY,),
    ),
    recorded=Recorded(tested=True),
    reading=LaravelReading(),
    live=LaravelLiveLookup(),
)
