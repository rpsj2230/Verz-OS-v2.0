"""The first routes under the versioned prefix, and the gate on them.

Until this module the application served liveness, readiness and the build documentation,
and nothing else. There was no route under `API_PREFIX` at all, which is why
`brain.api.COMMON_RESPONSES` described itself as attached to every route while being
attached to none, why `brain.openapi.DOCUMENTED_BEFORE_IT_IS_ENFORCED` had to say the
document was ahead of the code, and why the console's typed client was generated from a
schema describing health checks.

**A route is a lens, never a principal.** Nothing here holds a credential, opens a
connection, or reads a record on its own account. What a request may see is the caller's own
reach, narrowed by the channel it arrived on and by how strongly they are signed in, and the
narrowing is `brain.gate.admission.admit` rather than anything written here. That function
existed, was tested, and was called by nothing, so the ceiling it computes was a description
of what would happen rather than a thing that happened. See
`THE_ROUTE_ADDS_NOTHING_TO_WHAT_THE_CALLER_HOLDS`.

**One dependency decides the order, so no route can get it wrong.** `asking` authenticates,
resolves and narrows, in that order, and hands a route a caller and exactly one entitlement.
A route that assembled those itself would be a route that could resolve before it
authenticated, or answer at the nominal reach because the narrowed one was one variable away.
There is only ever one `EntitlementSet` in scope in this module.

**Every refusal is the same refusal.** An entity nothing classifies, an entity with no tool
registered, an entity whose tool this caller reaches no column of, and a record that simply
is not there all answer 404 with `brain.api.ErrorBody` and the same sentence. That is
`brain.core.redaction`'s record-level rule applied one level up, and it is worth applying
there because an installation's shape is as enumerable by asking as a client list is: a
caller who could tell "there is no price list here" from "you may not read it" could map
what this company runs by trying names. See `AN_ENTITY_IS_AS_ENUMERABLE_AS_A_RECORD`.

**No count of anything withheld leaves here.** `brain.api.Page` carries an optional `total`
and this route never sets it, deliberately and not for want of a cheap count: a total behind
a permission predicate is the "showing 3 of 47" leak with a different label on it. What a
caller gets instead is `truncated`, which says there is more without saying how much more.
See `A_TOTAL_IS_A_HIDDEN_ITEM_COUNT`.

**A filter is a question about a column's values, so it is bounded by what the caller may
read.** `?filter=sku:WEB-1001` is answered by which rows come back, and asked of a column the
response withholds it is a value oracle: `filter=cost:400` returning a row says the cost is
400, through a column the SELECT list was careful never to fetch. The bound is enforced where
the SELECT list is compiled, by `brain.knowledge.rows._compile_filters`, off the same
`compile_projection` output `read_rows` builds its SELECT from. This module supplies no list
of its own, and the list it happens to be holding is the wrong one: `classification.columns()`
is every column the entity classifies rather than the ones this caller reaches, so a check
written here against the one thing in reach would admit exactly the filter the projection
refuses. See `A_FILTER_IS_A_QUESTION_ABOUT_A_COLUMNS_VALUES`.

**The parameter is declared, because an undeclared one is dropped in silence.** FastAPI
ignores a query parameter no signature names, so a console sending a filter against a route
declaring only `limit` would be answered with unfiltered rows and nothing saying so.
`console/src/pages/recordsQuery.ts` refuses to render a filter box for that reason and reads
the declared names out of the generated document, so the grammar has to travel in the
document rather than in a convention. It does: one repeatable `filter`, each occurrence a
`column:value` term, with the term's shape declared as a pattern and both bounds as
`maxLength` and `maxItems`. See `AN_UNDECLARED_PARAMETER_IS_DROPPED_WITHOUT_A_WORD`.

Rejected: `filter.<column>=<value>`, which is the spelling the console named when it argued
itself out of sending one. FastAPI declares parameters from a signature, and which columns an
entity has is not known until the path parameter has been read, so such a name reaches no
document at all. A name that reaches no document is a name the console has already, correctly,
decided never to send.

Rejected: refusing a filter that names a column this caller may not read. A refusal is an
answer to "is there a column called that", which is the question the 404 above spends itself
preventing one level up. An unreadable column and an unknown one compile to the same
unsatisfiable predicate, skip the same fetch and produce the same empty page, and the only
place either is named is a log line an operator reads.

Rejected: prefix and membership operators beside equality. Both are safe under the same
argument, and neither is safe under the argument that matters, which is what happens the day
the projection bound regresses. With equality a leak costs one request per guessed value;
with a prefix the same leak is a binary search, and a column's contents fall out in the
length of the value rather than in the size of its domain. Equality is the operator a grid's
cell actually offers, so the narrower one is also the one somebody asked for.

**The redactor is the only path to a response body.** The handler produces a `TypedResult`,
`serialise_for_channel` turns it into a `ChannelPayload`, and `RecordPage` is built from that
payload and from nothing else. There is no branch here that reads a record, a trace or a
redaction reason directly, which is the shape `brain.core.redaction` enforces on channel
adapters by giving them nowhere to put one.

**What this cannot do yet, stated rather than implied.** The application registers no row
tool, because `brain.tools.startup` argues at length that wiring one changes the deployed
connection profile and deserves its own measurement. So on the deployed instance every
entity answers 404, uniformly, for everybody. That is the correct answer for an install with
no data plane and it is indistinguishable from a refusal, which is the property that matters;
what it is not is useful. The route reads `app.state.tools`, so the day somebody passes
`records=` to `build_registry` this answers without a line changing here.

Rejected: a `POST /ask` taking a question in words. There is no model wired into this
process, so such a route would either refuse everything or return whatever a keyword match
happened to find while presenting itself as an answer. A route that reads records is a
smaller claim and it is the one screen 3 is built on.

Rejected: projecting a catalogue through `brain.gate.invoke` for a request with no agent in
it. `invoke` assembles an agent run: it wants a ceiling, a leash and an injection
assessment, and a records read has none of the three. Inventing them so the call could be
made would put three fabricated values into the one place the platform's reach is decided.
The agent term of the invariant enters at `gate.invoke` and `gate.leash.decide`, and it is
deliberately absent here rather than faked.

**A service account is answered at its owner's live reach narrowed by its ceiling, and at nothing
it holds itself.** `asking` resolves the owner, never the account, and hands the result to
`brain.identity.sessions.reach_for`, the one function that intersects the two; the account's own
id is then what every route and the ledger see. The owner is resolved on this request through the
same cache every caller's reach goes through, keyed on the owner's grants version, so a grant taken
from the owner is gone from the account on the next request. See
`A_SERVICE_ACCOUNT_IS_ANSWERED_AT_ITS_OWNERS_REACH`.

Task ids: M31.1.4.1, M31.1.4.3, M31.1.4.4, M32.5.2.1, M1.1.7, M1.8.2
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Final, cast

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, JsonValue, StringConstraints

from brain.agents.model import AGENT_ID_CHARS
from brain.agents.template import config_hash
from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.audit.compliance import intercept
from brain.audit.record import DenyReason
from brain.core.department import gaps_for_question
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.core.errors import Absent, BrainError, Failed
from brain.core.field_policy import FieldPolicy
from brain.core.redaction import (
    ChannelPayload,
    LockedField,
    require_typed_result,
    serialise_for_channel,
)
from brain.core.scope import Clause, Op, Scope
from brain.gate.addressing import from_web
from brain.gate.admission import admit, second_factor_gives_back, verbs_withheld
from brain.gate.answer import answer_lane, frames_of
from brain.gate.answer_cache import AnswerStore
from brain.gate.caches import MAX_QUESTION_CHARS
from brain.gate.catalogue import AgentCeiling
from brain.gate.context import Channel, GateStep, open_trace
from brain.gate.fast_lane import RowReader
from brain.gate.finish import Origin, RequestRecorder
from brain.gate.front import AgentSetup, Caching, Choosing, run_front_half
from brain.gate.model_lane import PASSAGE_POLICY, DocumentSearchTool, ModelLane
from brain.gate.resolve import EntitlementCache, EntitlementStore, VersionSource, resolve
from brain.identity.bearer import Caller, TokenAuthority, authenticate
from brain.identity.oidc import TokenRefusal, TokenRefusedError, VerifiedClaims
from brain.identity.roles import NoStandingEntitlement
from brain.identity.sessions import reach_for
from brain.knowledge.document_tools import SEARCH_DOCUMENTS, KnowledgePassage
from brain.knowledge.rows import (
    DEFAULT_ROW_LIMIT,
    MAX_ROW_LIMIT,
    RowRequest,
    entity_capability,
    row_scope_for,
)
from brain.knowledge.search import KNOWLEDGE_READ
from brain.ops.denial_store import Denial, Denials, StoredDenials, record_beside
from brain.ops.model_service import ModelService
from brain.ops.sensitive_referral_store import SensitiveReferrals, StoredSensitiveReferrals
from brain.ops.trace_sink import CountingTraceSink
from brain.tools.registry import ToolRegistry
from brain.tools.startup import classification_for

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why the route computes reach rather than being handed it.
THE_ROUTE_ADDS_NOTHING_TO_WHAT_THE_CALLER_HOLDS: Final = (
    "A route that could see more than its caller defeats the whole system, and the way that "
    "happens is never a deliberate bypass: it is a handler reading a record to decide "
    "whether to show it, or a service credential used because the caller's own reach was "
    "inconvenient. So the entitlement passed to the reader and the entitlement passed to the "
    "redactor are the same object, computed once from the caller's grants and narrowed by "
    "gate.admission, and there is no other entitlement in scope for it to be confused with."
)

#: Why a service account's reach is computed from its owner on every request.
A_SERVICE_ACCOUNT_IS_ANSWERED_AT_ITS_OWNERS_REACH: Final = (
    "A service account holds no grant. Its reach is its owner's, resolved now, intersected with "
    "the capabilities it declared, and rebuilt under its own id. Resolving the account's own id "
    "would answer from grants nobody could write, and caching the pair would keep a revoked "
    "grant working for the length of the cache."
)

#: Why an unknown entity answers exactly as a forbidden one does.
AN_ENTITY_IS_AS_ENUMERABLE_AS_A_RECORD: Final = (
    "Whether this company runs a price list, an HR table or a finance ledger is a fact about "
    "the company, and a caller who can tell 'nothing here is called that' from 'you may not "
    "read it' learns it by trying names. So an unclassified entity, an unregistered one, an "
    "ambiguous one and one whose rows this caller reaches none of are one answer with one "
    "body, and the difference between them is a log line."
)

#: Why `total` is never populated on this route.
A_TOTAL_IS_A_HIDDEN_ITEM_COUNT: Final = (
    "A count computed behind a permission predicate tells the reader how many rows the "
    "predicate removed, because they can see the ones it kept. 'Showing 3 of 47' is 44 facts "
    "they did not have, and it is the same leak whether the number is called total, count or "
    "matches. `truncated` says there is more and says nothing about how much more, which is "
    "the whole of what a person paging through a list actually needs."
)

#: Why a caller may filter only on a column they could already read, and why this module
#: enforces none of it.
A_FILTER_IS_A_QUESTION_ABOUT_A_COLUMNS_VALUES: Final = (
    "A filter is answered by which rows come back, so a filter on a column the response "
    "withholds reads that column one comparison at a time: cost=400 returning a row says "
    "the cost is 400 without the figure ever being in the body. The bound is therefore the "
    "compiled projection and nothing else, applied where the projection is compiled, so a "
    "column that may be filtered on is exactly a column that may be selected. A second list "
    "here would be the wrong list: this route holds the entity's classification, which names "
    "every column the entity has rather than the ones this caller reaches, and a check "
    "against it would admit precisely the filter the projection refuses."
)

#: Why the filter travels as a declared parameter rather than as a name built per entity.
AN_UNDECLARED_PARAMETER_IS_DROPPED_WITHOUT_A_WORD: Final = (
    "FastAPI ignores a query parameter no signature names, and answers as though it had not "
    "been sent. A filter dropped that way is the worst failure available on a grid, because "
    "the rows still arrive and are read as the matching ones, and nothing on the screen or "
    "in the response says otherwise. So the parameter is declared, the declaration carries "
    "the grammar into the document, and the console decides what it may send by reading the "
    "document rather than by agreeing with this module out of band."
)


# ------------------------------------------------------- the asker's own filter

#: The wire spelling of the parameter one filter term arrives in, repeated once per term.
#: Singular because each occurrence carries one term. The Python parameter is `filters`,
#: because `filter` is a builtin and shadowing one in a signature is refused by the linter.
FILTER_PARAM: Final = "filter"

#: What separates the column from the value inside one term. A colon because
#: `brain.core.scope.Clause` constrains a field name to `[a-z][a-z0-9_.]*`, which cannot hold
#: one, so the split at the first colon is unambiguous and a value may carry as many more as
#: it likes. The same argument the console makes for its locked-cell separator, and it is a
#: property rather than a coincidence: a test splits every term the declared pattern admits.
FILTER_SEPARATOR: Final = ":"

#: The longest term this route accepts. An equality filter is a value somebody read off a
#: cell and typed back, so the bound is generous for a business identifier and far short of
#: the free text nobody filters on by equality.
MAX_FILTER_TERM_LENGTH: Final = 256

#: How many terms one request may carry. Every term is one more conjunct in the WHERE clause,
#: and a caller sending more of them than any table here has columns is probing rather than
#: filtering. Bounded rather than left open because a repeated parameter is otherwise a
#: statement whose size the caller chooses.
#:
#: A resource bound and not a permission one, which is why only its lower end is asserted:
#: it must admit every column of the widest entity this application ships, or it is a limit
#: on the product. Raising it survives every test in this section, deliberately, because
#: nothing about who may see what changes with the number.
MAX_FILTERS: Final = 16

#: The grammar of one term, declared on the parameter so it reaches the generated document
#: and a client can refuse a malformed one without spending a request.
#:
#: The field half is a subset of `Clause.field`'s own pattern, bounded at that model's own
#: 120 characters, so every term this admits builds a `Clause`; the bound is not copied into
#: a test, it is derived there by asking `Clause` what it accepts. The value half excludes
#: the two characters that would let one term span two lines in a log and admits everything
#: else, including further colons, because a value is data and is bound as a parameter.
FILTER_TERM_PATTERN: Final = r"^[a-z][a-z0-9_.]{0,119}:[^\r\n]+$"

#: One term as the parameter carries it. The constraints sit on the item rather than on the
#: sequence, because pydantic applies a pattern given to the sequence *to the sequence*, which
#: is a TypeError at request time rather than a validation failure.
FilterTerm = Annotated[
    str, StringConstraints(pattern=FILTER_TERM_PATTERN, max_length=MAX_FILTER_TERM_LENGTH)
]


def filter_scope(terms: Sequence[str]) -> Scope:
    """The asker's own narrowing, as the same `Scope` the system narrows with.

    A `Scope` rather than a filter type belonging to this route, and that is the safety
    argument rather than a convenience. A `Scope` is a conjunction of validated field names, a
    closed operator set and values `compile_where` binds as parameters, so there is no value a
    caller can send that becomes syntax; `RowRequest.filters` is already one, so nothing is
    translated on the way in and nothing can be lost in the translation. It also means the
    asker's narrowing and the system's narrowing compose through the one `and_` in
    `compile_row_query`, which is why a filter can only ever shrink the row scope.

    Every term is an equality, and two terms naming one column are two clauses on one field,
    which `is_unsatisfiable` reads as a contradiction and compiles to an empty page. That is
    the same answer two conflicting grants on one field get, and it is conjunction meaning
    what it means everywhere else in this system rather than a rule invented here.

    `partition` splits at the first separator, so a value may contain one and a field name
    cannot. Total over anything `FILTER_TERM_PATTERN` admits, and the parameter's declaration
    is what guarantees the input matched it: a malformed term is refused before this function
    is reached, which is also why a malformed term cannot be answered differently depending on
    which entity was asked for.
    """
    clauses: list[Clause] = []
    for term in terms:
        column, _, value = term.partition(FILTER_SEPARATOR)
        clauses.append(Clause(field=column, op=Op.EQ, value=value))
    return Scope(clauses=tuple(clauses))


# ------------------------------------------------------------------- the wiring


@dataclass(frozen=True)
class GateWiring:
    """Everything a request under this prefix needs that the process holds once.

    One object rather than four attributes on `app.state`, because the four are useless
    apart: a token authority with no entitlement store authenticates people and can tell them
    nothing, and a store with no authority is a reach nobody can be identified for. Bundling
    them means "is this application wired" is one question with one answer, and a half-wired
    process is unrepresentable rather than a combination somebody has to reason about.

    Built by `brain.app.lifespan`, through `brain.app.wirings_for`, on a process with a database
    and a usable `INSTALL_OIDC_ISSUER`, and absent on one without either. `brain.identity.bearer`
    argues why the absence refuses rather than waving requests through, and `brain.app` says on
    readiness which of the two is missing.
    """

    authority: TokenAuthority
    versions: VersionSource
    store: EntitlementStore
    cache: EntitlementCache


def wiring_of(request: Request) -> GateWiring | None:
    """The wiring this process was built with, or None.

    `getattr` rather than attribute access, because a test may construct a bare `FastAPI` to
    exercise one route and an `AttributeError` there would surface as a 500 that reads like a
    bug in the gate rather than like an application built without one.
    """
    found = getattr(request.app.state, "gate", None)
    return found if isinstance(found, GateWiring) else None


def channel_for(claims: VerifiedClaims) -> Channel:
    """Which channel ceiling this token is held to.

    A token carrying Keycloak's `sid` came from an interactive browser session, which is what
    the console is. One with no `sid` belongs to no session, which is what a service-account
    token looks like, and `gate.admission.CHANNEL_VERBS` gives `API` neither `approve` nor
    `admin` for exactly that reason: a client-credentials grant is a secret in a
    configuration file, and an approval from one is an approval attributable to a file.

    Read from the claims rather than from a request header, because a header naming the
    channel is a header a caller can set, and the caller would then be choosing their own
    ceiling.
    """
    return Channel.CONSOLE if claims.session_id else Channel.API


@dataclass(frozen=True)
class Asking:
    """One request's caller, and the single reach it will be answered at.

    `reach` is `E_admitted = E(caller) ∩ channel_ceiling ∩ assurance_ceiling` (M3.3.3,
    M3.3.4), and it is the only `EntitlementSet` a route ever sees. The nominal set the store
    returned is deliberately not carried alongside it: two entitlements in scope, one wider
    than the other, is one autocomplete away from an answer computed at the wrong one.
    """

    caller: Caller
    reach: EntitlementSet
    channel: Channel
    now: datetime
    #: The verbs of the caller's own grants this channel and sign-in withhold, and never the
    #: capabilities: see `brain.gate.admission.verbs_withheld`.
    withheld_verbs: tuple[str, ...] = ()
    #: Whether a sign-in with a second factor, on this channel, would give one of them back.
    second_factor_gives_back: bool = False


#: Where `asking` leaves the session's second-factor answer for the error handler to read.
SECOND_FACTOR_STATE: Final = "second_factor_needed"


def second_factor_needed(request: Request) -> bool:
    """Whether `asking` found, for this request, that a second factor would restore a verb.

    False for a request `asking` never ran for, such as an unmounted path, which is the direction
    to fail in: the ordinary refusal. See
    `brain.gate.admission.A_REFUSAL_TO_A_WEAK_SIGN_IN_IS_ABOUT_THE_SESSION`.
    """
    return getattr(request.state, SECOND_FACTOR_STATE, False) is True


async def asking(request: Request) -> Asking:
    """Authenticate, resolve, narrow. One dependency, in that order, for every route.

    Named as a dependency at each route rather than installed as middleware. Middleware reads
    better and fails open in the case that matters: a route mounted on a path the middleware
    did not match is a route with no authentication, and nothing about it looks different in
    review. A missing dependency is visible in the diff that adds the route, and
    `test_every_route_under_the_prefix_authenticates_its_caller` asserts over the mounted set
    rather than over anybody's habit.

    Both ceilings come from `gate.admission.admit`, which builds them out of the caller's own
    grants and is therefore structurally incapable of adding anything. Nothing here composes
    an entitlement by hand; see `THE_ROUTE_ADDS_NOTHING_TO_WHAT_THE_CALLER_HOLDS`.

    The agent term of the platform invariant is absent because there is no agent in this
    path, and it is absent rather than supplied as an identity ceiling. An identity ceiling
    would be a real `EntitlementSet` in scope narrowing nothing, sitting exactly where a real
    one belongs, and the next person to add an agent here would have somewhere plausible not
    to put it.
    """
    now = datetime.now(UTC)
    wiring = wiring_of(request)
    caller = await authenticate(
        wiring.authority if wiring is not None else None,
        request.headers.get("authorization"),
        now=now,
    )
    if wiring is None:
        # Unreachable: `authenticate` refuses a request on a process with no authority, and
        # an authority only exists inside a `GateWiring`. Written as a refusal rather than an
        # assertion because the one thing this function must never do is fall through to a
        # caller with no reach computed, which would then be an empty set that looks resolved.
        raise Failed("no gate wiring on this process")

    entitlements = await reach_of(caller, wiring, now)
    channel = channel_for(caller.claims)
    restore = second_factor_gives_back(entitlements, channel, caller.assurance)
    # Before any route reads anything, so a refusal later in this request is answered from the
    # session and never from what was asked for.
    setattr(request.state, SECOND_FACTOR_STATE, restore)
    return Asking(
        caller=caller,
        reach=admit(entitlements, channel, caller.assurance),
        channel=channel,
        now=now,
        withheld_verbs=verbs_withheld(entitlements, channel, caller.assurance),
        second_factor_gives_back=restore,
    )


async def reach_of(caller: Caller, wiring: GateWiring, now: datetime) -> EntitlementSet:
    """What the caller holds before any ceiling: their own grants, or an account's owner's.

    See `A_SERVICE_ACCOUNT_IS_ANSWERED_AT_ITS_OWNERS_REACH`. An account whose owner holds nothing
    is refused rather than answered at an empty reach, for `NoStandingEntitlement`'s reason.
    """
    account, owner = caller.service_account, caller.owner
    if account is None:
        own = await resolve(
            caller.principal_id,
            versions=wiring.versions,
            store=wiring.store,
            cache=wiring.cache,
            now=now,
        )
        return own.entitlements
    if owner is None:
        raise TokenRefusedError(TokenRefusal.OWNER_INACTIVE, account.client_id)
    owners = await resolve(
        owner.id, versions=wiring.versions, store=wiring.store, cache=wiring.cache, now=now
    )
    narrowed = reach_for(account, owner, owners.entitlements, now)
    if isinstance(narrowed, NoStandingEntitlement):
        raise TokenRefusedError(TokenRefusal.OWNER_INACTIVE, account.client_id)
    return narrowed


#: The dependency every route under this prefix takes. Spelled once so a new route cannot
#: acquire a subtly different one by copying an older signature.
Asked = Annotated[Asking, Depends(asking)]


# ------------------------------------------------------------------ the shapes


class CallerView(BaseModel):
    """Who the API thinks is asking. The caller's own facts and nobody else's.

    Deliberately carries no list of capabilities. It would be the caller's own list and
    therefore safe in the narrow sense, and it would also be the first thing cached in a
    browser and used to decide what to render, which is a permission model in the copy an
    attacker edits. What the console may show is decided by what the API answers, one request
    at a time.

    `assurance` is here because it is the one fact a person can act on: "sign in again with
    your second factor" is a thing they can do, and it is the difference between holding the
    approve verb and being able to exercise it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    display_name: str
    primary_department: str | None = None
    employment: str
    assurance: str
    channel: str
    #: The verbs this person's own grants hold that this channel and sign-in do not let them use.
    #: Verbs and never capabilities, so it says what a stronger sign-in gives back and nothing
    #: about which things the grants reach. Empty when nothing is withheld.
    withheld_verbs: list[str] = []
    #: True when signing in again with a second factor would give one of those verbs back. The
    #: console's banner and "sign in again" action read this and nothing else.
    second_factor_needed: bool = False
    #: Order-independent digest of the reach this request was computed at. Says nothing about
    #: what the reach contains, and is what a support conversation quotes beside a trace id
    #: when two people disagree about what they saw.
    ent_hash: str


class RecordPage(Page[dict[str, Any]]):
    """One page of records, already through the redactor.

    Built from a `ChannelPayload` and from nothing else, which is what makes "the serialiser
    is the only path to a channel" a shape here rather than a convention: there is no field
    on this model that a trace, a redaction reason or a dropped record could be assigned to.

    `next_cursor` is always null today and that is a fact about the row plane rather than
    about this route. `brain.core.scope.Op` has EQ, IN, PREFIX and ANY and no ordered
    comparison, so a keyset position cannot be expressed as a filter the query compiler will
    accept, and an offset would re-read and re-filter under a permission predicate, which is
    the failure `brain.api.Page` was written to avoid. `truncated` carries the only fact a
    caller needs in the meantime. The route takes `cursor` all the same, so it has the one page
    shape (`tests/unit/test_api_paging.py`), and refuses every value, since none was issued.

    `total` is inherited and never populated. See `A_TOTAL_IS_A_HIDDEN_ITEM_COUNT`.
    """

    #: Fields present on the record and withheld from this caller. The lock is the product,
    #: not an apology: screen 3 shows a record with its restricted columns marked, and the
    #: person holding the capability sees the figure in the same place.
    locked: tuple[LockedField, ...] = ()
    #: Suppressed when nothing survived, by the payload rather than by this route. A page
    #: that named the source it found nothing in would answer a question nobody may ask.
    source: str = ""
    fetched_at: str = ""
    #: There is more. Never how much more.
    truncated: bool = False


def page_from(payload: ChannelPayload) -> RecordPage:
    """The response, copied field by field off the payload.

    Written out rather than spread from a dump, so that a field added to `ChannelPayload`
    does not arrive in a response body because a copy loop was generous. Every field here is
    one somebody chose to publish.
    """
    return RecordPage(
        items=list(payload.records),
        next_cursor=None,
        locked=payload.locked,
        source=payload.source,
        fetched_at=payload.fetched_at,
        truncated=payload.truncated,
    )


# ------------------------------------------------------------------ the routes

router = APIRouter(prefix=API_PREFIX, tags=["gate"])


def denials_of(request: Request) -> Denials | None:
    """Where this process records a refusal: what a test installed, the database, or nowhere."""
    found = getattr(request.app.state, "denials", None)
    if isinstance(found, Denials):
        return found
    sessions = getattr(request.app.state, "db_sessions", None)
    return StoredDenials(sessions) if sessions is not None else None


def _bound_trace_id() -> str:
    """The id the trace middleware bound, or `untraced` where it bound none."""
    return str(structlog.contextvars.get_contextvars().get("trace_id", "")) or "untraced"


@router.get("/me", response_model=CallerView, responses=COMMON_RESPONSES)
async def me(asked: Asked) -> CallerView:
    """Who this token belongs to, and what it can be exercised at.

    The one route that answers something useful before a data plane exists, and the one that
    proves the whole authentication path end to end: a signature checked against a published
    key, an issuer and audience compared exactly, an expiry honoured, a subject mapped to a
    principal this company wrote down, and a reach narrowed by the channel and the sign-in.
    """
    return CallerView(
        principal_id=asked.caller.principal.id,
        display_name=asked.caller.principal.display_name,
        primary_department=asked.caller.principal.primary_department,
        employment=str(asked.caller.principal.employment),
        assurance=asked.caller.assurance.name.lower(),
        channel=str(asked.channel),
        withheld_verbs=list(asked.withheld_verbs),
        second_factor_needed=asked.second_factor_gives_back,
        ent_hash=asked.reach.ent_hash(),
    )


@router.get("/records/{entity}", response_model=RecordPage, responses=COMMON_RESPONSES)
async def records(
    request: Request,
    entity: str,
    asked: Asked,
    limit: Annotated[int, Query(ge=1, le=MAX_ROW_LIMIT)] = DEFAULT_ROW_LIMIT,
    filters: Annotated[
        tuple[FilterTerm, ...], Query(alias=FILTER_PARAM, max_length=MAX_FILTERS)
    ] = (),
    cursor: Annotated[str | None, Query(max_length=64)] = None,
) -> RecordPage:
    """Rows of one entity, at this caller's reach, narrowed by their own filter, redacted.

    The reader is handed the reach, which is what puts the scope predicate inside the query
    rather than around the result. The redactor is handed the same object again, which is
    what catches anything the reader let through. Two enforcement points and one entitlement.

    A caller who holds no grant over this entity is refused before either of them, with the
    answer an unknown entity gets. An empty page would be the friendlier response and it is
    the leak: it says the entity exists here, and a caller comparing an empty page against a
    404 maps the installation by trying names.

    The filter is turned into a scope before anything about the entity has been looked at,
    and that ordering is defence in depth rather than a live guard: moving the call below the
    404 changes no answer today and was measured doing so, because the grammar declared on the
    parameter makes `filter_scope` total over everything that reaches it. It is written here
    for the day the parse grows a refusal of its own, since a filter refused after the entity
    lookup would answer one status for an entity that exists and another for one that does
    not, which is the enumeration this route's single 404 exists to prevent. What holds that
    property up today is the declaration, and removing the pattern from it fails three tests.

    Nothing here checks the filter against the entity's columns. `classification` is in scope
    and would answer such a check, and the answer would be wrong: it names every column the
    entity classifies rather than the ones this caller reaches. See
    `A_FILTER_IS_A_QUESTION_ABOUT_A_COLUMNS_VALUES`.
    """
    if cursor is not None:
        # Refused before the entity is looked at, so the 422 is the same for every entity.
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "cursor"),
                    "msg": "malformed cursor",
                    "input": None,
                }
            ]
        )
    narrowing = filter_scope(filters)
    registry = getattr(request.app.state, "tools", None)
    if not isinstance(registry, ToolRegistry):
        # A process-level fault, identical for every caller and every entity, so it discloses
        # nothing about what exists. `brain.app.lifespan` builds one before it yields.
        raise Failed("no tool registry on this process")

    classification = classification_for(entity)
    matching = [d for d in registry.definitions() if d.entity == entity]
    # `row_scope_for` and never a check written here. It is the same function `read_rows`
    # consults, so "does this caller reach rows of this kind" has one answer; the difference
    # is only that a route has to turn None into a status while a reader turns it into FALSE.
    reaches = row_scope_for(entity, asked.reach, asked.now) is not None

    if classification is None or len(matching) != 1 or not reaches:
        # One refusal for four causes, on purpose. Answering an unreachable entity with an
        # empty page instead would be the leak: an empty list means "there is nothing here
        # for you to see", and a caller comparing an empty page against a 404 learns which
        # entities this installation carries by trying names. It is the same argument
        # `gate.catalogue` makes about tools, where a tool the caller cannot reach is absent
        # from the list rather than described and then refused.
        #
        # More than one match is a misconfigured install rather than a permission question,
        # and it is logged as one; answering it differently would tell a caller that two
        # systems here carry this entity.
        log.info(
            "entity not answerable",
            entity=entity,
            classified=classification is not None,
            tools=len(matching),
            reaches=reaches,
        )
        if classification is not None and len(matching) == 1 and not reaches:
            # The one cause that is a refusal rather than an absence: the entity is served and no
            # grant reaches it. Recorded beside the 404, never in its path; see
            # `brain.ops.denial_store`, which says why.
            record_beside(
                denials_of(request),
                Denial(
                    actor_id=asked.reach.principal_id,
                    ent_hash=asked.reach.ent_hash(),
                    trace_id=_bound_trace_id(),
                    subject_kind="entity",
                    subject_id=entity,
                    capability=entity_capability(entity),
                    reason=DenyReason.NO_GRANT,
                ),
            )
        raise Absent(f"{entity!r} is not answerable for this caller")

    handler = registry.get(matching[0].name).handler
    try:
        # Awaited directly. This was `asyncio.to_thread` until 2026-09-07, because the row
        # plane was synchronous and this process is not; making `RowSource` awaitable removed
        # the mismatch and the thread hop with it. A thread per concurrent row query was the
        # cheaper of the two things that hop cost: the other was that a reader could not use
        # the pool the application already had.
        #
        # Awaited through a check rather than a cast, because the registry holds handlers of
        # both kinds and will go on doing so: `brain.tools.run_skill.handler` is synchronous
        # and has no reason not to be, since it runs a script in a sandbox rather than
        # touching a pool. A row handler is awaitable and this is where that is established,
        # in the same register as `require_typed_result` below: a boundary check on what a
        # tool handed back, not an assumption about what it promised.
        answered = handler(
            RowRequest(filters=narrowing, limit=limit),
            entitlement=asked.reach,
            now=asked.now,
        )
        raw = await answered if inspect.isawaitable(answered) else answered
        # The boundary check rather than a cast. A handler that returned a dictionary is
        # refused here, where it is a contract violation by a tool, rather than being walked.
        result = require_typed_result(raw)
    except BrainError:
        # Already in the taxonomy, already has a public message, already maps to a status.
        # Re-wrapping would turn a refusal into a server fault.
        raise
    except Exception as exc:
        # Broad for the reason `gate.resolve` gives about its own: whatever a driver raises
        # would otherwise reach the response as FastAPI's default body, which is not
        # `ErrorBody`, or as a message with a connection string in it.
        raise Failed(f"reading {entity}: {type(exc).__name__}") from exc

    return page_from(
        serialise_for_channel(
            result, entitlement=asked.reach, policy=classification.policy(), now=asked.now
        )
    )


# ------------------------------------------------------- the answer lane (SSE)

#: The media type an event stream is served as. Not negotiable and not a preference: a
#: client reads frames by this type, and anything else makes the body one long string.
EVENT_STREAM: Final = "text/event-stream"

#: Why the question is in a body and not in the path or the query string.
A_QUESTION_IN_A_URL_IS_A_QUESTION_IN_EVERY_LOG: Final = (
    "A URL is written to the proxy access log, kept in browser history, sent as a referer by "
    "anything the page later links to, and shown in full by every screen-sharing tool. A "
    "question is the most sensitive part of a request here: it names the client, the invoice "
    "or the person somebody is asking about, and it does so before any entitlement has been "
    "applied to it. None of those destinations is governed by the reach the answer was "
    "computed at, so the question travels in the body, where it goes to the application and "
    "nowhere else. That is also why this is a POST for something that writes nothing: the "
    "verb follows where the question can safely live."
)

#: Why a streamed answer must not be stored by anything between here and the reader.
AN_ANSWER_IS_COMPUTED_FOR_ONE_REACH_AND_CACHED_BY_NOBODY: Final = (
    "Every answer here is computed at one caller's entitlements. A shared cache in front of "
    "this route would key on the URL and the body and serve one person's answer to the next "
    "person who asked the same question, which is the whole permission model defeated by an "
    "intermediary nobody configured. brain.gate.answer_cache exists and keys on the "
    "entitlement hash for exactly this reason; a proxy has no such key and must not try."
)


class Question(BaseModel):
    """One question, bounded the way the cache bounds one.

    The bound is `brain.gate.caches.MAX_QUESTION_CHARS` rather than a number chosen here, so
    a question this route accepts is one the cache could key, and there is no length that is
    answerable and uncacheable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: Annotated[
        str,
        StringConstraints(min_length=1, max_length=MAX_QUESTION_CHARS, strip_whitespace=True),
    ]
    #: The agent the person picked, by id, or None. Judged by `brain.gate.select.select_agent`
    #: against the agents this person may use, like any name; see `brain.gate.addressing`.
    agent: Annotated[str, StringConstraints(max_length=AGENT_ID_CHARS)] | None = None


def row_readers(registry: ToolRegistry) -> dict[tuple[str, str], RowReader]:
    """Every row tool this process registered, keyed the way the fast lane looks one up.

    **Every tool, not the ones this caller reaches.** Filtering here would be a second
    permission decision, taken in a route, about a question `compile_projection` already
    answers inside the query: a caller who reaches no column of an entity gets a statement the
    compiler knows is empty and no rows come back. A route that filtered as well would be a
    second answer to one question, and the day the two disagree the wrong one is whichever was
    easier to change.

    Both answers are the same sentence anyway. A rule excluded here matches nothing and a rule
    left in fetches nothing, and `brain.gate.answer` gives both the same frames.
    """
    readers: dict[tuple[str, str], RowReader] = {}
    for definition in registry.definitions():
        if not definition.entity or not definition.source:
            continue
        # A cast at a boundary the registry keeps deliberately loose. It holds handlers of
        # two shapes and will go on doing so: `brain.tools.run_skill.handler` is synchronous
        # because it runs a script in a sandbox, and a row handler is awaitable. What selects
        # the awaitable ones here is the pair of names above, which only a row tool sets, and
        # the failure mode if that ever stops being true is an `await` on something that is
        # not awaitable, which the broad except below turns into a refusal rather than into a
        # wrong answer. The records route establishes the same fact at its own boundary with
        # `inspect.isawaitable`; here the lane does the awaiting, so the check belongs there.
        readers[(definition.source, definition.entity)] = cast(
            RowReader, registry.get(definition.name).handler
        )
    return readers


def reachable_sources(registry: ToolRegistry, asked: Asking) -> tuple[str, ...]:
    """The sources this caller may be told about, for the scope statement.

    `row_scope_for` and never a check written here, for the reason the records route gives: it
    is the same function `read_rows` consults, so "does this caller reach rows of this kind"
    has one answer.

    Derived from reach and never from what answered, which is `SearchScope`'s own rule: a
    statement assembled from the sources that ran would vary with whether a record existed,
    and the variation is readable by asking the same question twice.
    """
    return tuple(
        sorted(
            {
                definition.source
                for definition in registry.definitions()
                if definition.entity
                and definition.source
                and row_scope_for(definition.entity, asked.reach, asked.now) is not None
            }
        )
    )


def field_policies(registry: ToolRegistry) -> dict[str, FieldPolicy]:
    """One field policy per classified entity, for the redaction the lane performs.

    A mapping built before the question is read, so a policy cannot be chosen to fit the rows
    that came back. `brain.gate.answer` takes a mapping rather than a callback for the same
    reason.
    """
    policies: dict[str, FieldPolicy] = {}
    for definition in registry.definitions():
        classification = classification_for(definition.entity) if definition.entity else None
        if classification is not None:
            policies[definition.entity] = classification.policy()
    return policies


def passage_search_for(registry: ToolRegistry) -> DocumentSearchTool | None:
    """The passage search the answer lane's model step reads through, or None without one.

    Over the handler `brain.tools.startup.build_registry` registered for
    `knowledge.search_documents`, which exists exactly when the registry was built over a row
    source. Built once, by `brain.app.lifespan`, beside the registry it reads.
    """
    if not registry.has(SEARCH_DOCUMENTS):
        return None
    # A cast at the registry's boundary, for the reason `row_readers` gives: the registry holds
    # handlers of more than one shape, and the name selects the one this is.
    handler = cast(
        Callable[..., Awaitable[TypedResult[KnowledgePassage]]],
        registry.get(SEARCH_DOCUMENTS).handler,
    )
    return DocumentSearchTool(handler=handler)


def model_lane_of(state: Any) -> ModelLane | None:
    """The model step this process hands the answer lane, or None where it has nothing to hand.

    Both halves are built by `brain.app.lifespan`: the model service on every process, and the
    passage search only on one with a database. A process missing either abstains on a question
    no rule answers, exactly as the lane did before it had a model step, rather than finding
    passages it cannot read to a model or asking a model with nothing to show it.
    """
    models = getattr(state, "models", None)
    search = getattr(state, "passage_search", None)
    if not isinstance(models, ModelService) or search is None:
        return None
    return ModelLane(search=search, model=models.calls)


#: The agent `/answer` answers as until an agent roster is read on this route: the person asking,
#: through every tool the process registered, with no side effect. See `default_agents`.
DEFAULT_AGENT: Final = "brain"


def default_agents(registry: ToolRegistry) -> dict[str, AgentSetup]:
    """The one agent the front half may select on `/answer`, keyed by its id.

    Its ceiling is every registered tool, so projection narrows by the caller's reach alone,
    and its side effect is NONE, so an answer can reach no write whatever is registered. The
    configuration hash covers the id and the tool names, so the answer cache stops matching the
    moment the registry a process answers with changes.
    """
    names = frozenset(one.name for one in registry.definitions())
    allowed: list[JsonValue] = [*sorted(names)]
    digest = config_hash({"agent_id": DEFAULT_AGENT, "allowed_tools": allowed})
    ceiling = AgentCeiling(agent_id=DEFAULT_AGENT, allowed_tools=names)
    return {DEFAULT_AGENT: AgentSetup(ceiling=ceiling, config_hash=digest)}


def policy_epoch_of(policies: Mapping[str, FieldPolicy]) -> int:
    """One number that moves whenever any field policy an answer is redacted under moves.

    The cache key takes an integer epoch and every `FieldPolicy` has a digest; this folds the
    entity policies and the passage policy into one, so an answer cached under one policy is
    never served under another. Sorted, for `FieldPolicy.epoch`'s own reason.
    """
    parts = sorted(f"{entity}={policy.epoch()}" for entity, policy in policies.items())
    blob = "|".join((*parts, f"passages={PASSAGE_POLICY.epoch()}"))
    return int(hashlib.sha256(blob.encode("utf-8")).hexdigest()[:15], 16)


def caching_of(
    state: Any, policies: Mapping[str, FieldPolicy], sources: Sequence[str]
) -> Caching | None:
    """The answer-cache lookup for this request, or None on a process with no answer store.

    `brain.app.lifespan` installs `ValkeyAnswerStore` only when a cache is configured. With
    none the front half still enters CACHE and misses, so the record says the step ran.
    `sources` is every source the reader reaches, so a volatile one makes the question
    uncacheable rather than a cached answer stale.
    """
    store: AnswerStore | None = getattr(state, "answer_store", None)
    if store is None:
        return None
    return Caching(
        store=store,
        policy_epoch=policy_epoch_of(policies),
        # No source records an epoch yet, so the key holds none and the TTL bounds staleness.
        source_epochs={},
        sources=frozenset(sources),
    )


def sensitive_referrals_of(request: Request) -> SensitiveReferrals | None:
    """Where this process files a referral: what a test installed, the database, or nowhere."""
    found = getattr(request.app.state, "sensitive_referrals", None)
    if isinstance(found, SensitiveReferrals):
        return found
    sessions = getattr(request.app.state, "db_sessions", None)
    return StoredSensitiveReferrals(sessions) if sessions is not None else None


async def referred(request: Request, asked: Asking, question: str) -> str | None:
    """The referral sentence for a sensitive question, filed first; None for any other question.

    A process with nowhere to file one refuses with the fault every caller gets for a missing
    store, rather than telling the asker a note went to somebody when it went nowhere.
    """
    decision = intercept(question, trace_id=_bound_trace_id())
    if decision.topic is None:
        return None
    store = sensitive_referrals_of(request)
    if store is None:
        raise Failed("no database on this process")
    await store.refer(
        asked_by=asked.reach.principal_id,
        topic=decision.topic,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_bound_trace_id(),
    )
    return decision.reply()


@router.post("/answer", responses=COMMON_RESPONSES)
async def answer(request: Request, asked: Asked, ask: Question) -> StreamingResponse:
    """One question, answered as a stream of events, at this caller's reach.

    **The first route in this application that answers a question rather than serving rows.**
    It runs `brain.gate.answer.answer_lane`, which had no caller, over
    `brain.gate.fast_lane`, which had none either, and writes the result through
    `brain.gate.streaming`, which had none either. A question no rule answers is handed to the
    lane's model step when this process has one, `model_lane_of`: see `brain.gate.model_lane`
    for what a model is shown and why nothing it says is read for references.

    A POST for something that writes nothing, because of where the question can safely live:
    `A_QUESTION_IN_A_URL_IS_A_QUESTION_IN_EVERY_LOG`.

    Every kind of nothing is one answer. No rule matched, two matched, the record does not
    exist, and the caller may not read the column all produce the same frames, and the lane
    rather than this route is where that is enforced.

    The response is uncacheable by anything in front of it, which is a permission requirement
    and not a performance note: see
    `AN_ANSWER_IS_COMPUTED_FOR_ONE_REACH_AND_CACHED_BY_NOBODY`.
    """
    registry = getattr(request.app.state, "tools", None)
    if not isinstance(registry, ToolRegistry):
        # A process-level fault, identical for every caller and every question, so it
        # discloses nothing about what exists. `brain.app.lifespan` builds one before it
        # yields.
        raise Failed("no tool registry on this process")

    rules = getattr(request.app.state, "fast_path_rules", ())
    sink = getattr(request.app.state, "trace_sink", None) or CountingTraceSink()
    # What a finished request owes, installed by `brain.app.lifespan` through
    # `request_recorders_for`. Empty on a process with no database, which has nowhere to hold
    # a record and nowhere a report could read one from.
    recorders: tuple[RequestRecorder, ...] = getattr(request.app.state, "request_recorders", ())
    # The id the trace middleware vouched for or minted, bound before identification ran. Read
    # from the log context rather than from the header, because the header is what the caller
    # proposed and the bound value is what this system decided.
    trace_id = str(structlog.contextvars.get_contextvars().get("trace_id", ""))
    # Built from what `asking` resolved and nothing the request carried: the principal came
    # from the directory and the channel from the token's claims. `Origin` refuses an id the
    # audit ledger would not accept, which is a process fault identical for every caller.
    origin = Origin(trace_id=trace_id, principal=asked.caller.principal, channel=asked.channel)
    # Before the front half and the lane, so before the cache and any model: a sensitive question
    # is routed to its topic's named person and recorded without what was asked, and the asker is
    # told one sentence whatever the topic (M24.2.2). See `brain.audit.compliance`.
    referral = await referred(request, asked, ask.question)

    # IDENTIFY and ENTITLE ran in `asking` before this handler could; they are entered here, in
    # order, so the front half's refusal to start before ENTITLE is a real check on this path.
    recorder = open_trace(trace_id, asked.now, asked.channel)
    recorder.principal_id = asked.caller.principal.id
    recorder.enter(GateStep.IDENTIFY)
    recorder.ent_hash = asked.reach.ent_hash()
    recorder.enter(GateStep.ENTITLE)
    address = from_web(ask.question, ask.agent)
    agents = default_agents(registry)
    policies = field_policies(registry)
    sources = reachable_sources(registry, asked)
    knowledge = asked.reach.scope_for(KNOWLEDGE_READ, asked.now)

    try:
        front = run_front_half(
            address.question,
            recorder=recorder,
            reach=asked.reach,
            channel=asked.channel,
            agents=agents,
            choosing=Choosing(
                visible_agents=frozenset(agents),
                default_agent=DEFAULT_AGENT,
                addressed=address.agent_id,
            ),
            registry=registry.definitions(),
            now=asked.now,
            # A referred question is looked up in no store: the step is entered and misses, as it
            # does on a process with none, so the request row reads as any other question's.
            caching=None
            if referral is not None
            else caching_of(request.app.state, policies, sources),
        )
        answered = await answer_lane(
            address.question,
            origin=origin,
            recorders=recorders,
            rules=rules,
            readers=row_readers(registry),
            entitlement=asked.reach,
            policies=policies,
            reachable_sources=sources,
            sink=sink,
            now=asked.now,
            # The completion instant, read by the lane once in its `finally`. The wall clock,
            # because `asked.now` was read from it at the top of `asking`, before
            # authentication, so the ledger's duration covers identifying, entitling and
            # answering, and ends before the frames are written.
            clock=lambda: datetime.now(UTC),
            cached=front.cached,
            # Only a request the front half routed to a tier may reach a model, so no model is
            # called before ROUTE and PROJECT: a fast-lane question answers or abstains.
            model=model_lane_of(request.app.state) if front.calls_a_model else None,
            front=front.record(),
            gaps=gaps_for_question(address.question, knowledge),
            referral=referral,
        )
    except BrainError:
        # Already in the taxonomy, already has a public message, already maps to a status.
        raise
    except Exception as exc:
        # Broad for the reason the records route gives about its own: whatever a driver raises
        # would otherwise reach the response as FastAPI's default body, which is not
        # `ErrorBody`, or as a message with a connection string in it.
        raise Failed(f"answering: {type(exc).__name__}") from exc

    # The reason, never the question and never the answer. An abstention reason is the audit
    # half of the outcome and a log is an audit surface; the question is the caller's and the
    # answer is theirs, and neither belongs in a stream governed by who can read logs.
    log.info(
        "answered",
        principal=asked.caller.principal.id,
        rules=len(rules),
        abstained=answered.abstention.reason.value if answered.abstention else None,
        from_cache=answered.from_cache,
    )

    return StreamingResponse(
        frames_of(answered),
        media_type=EVENT_STREAM,
        headers={
            # A permission requirement rather than a performance note. See the constant above.
            "Cache-Control": "no-store",
            # nginx buffers a proxied response by default, which turns a stream into one
            # delivery at the end and makes every progress step arrive after the wait it was
            # describing. Ignored by proxies that are not nginx, which is why it is a header
            # and not a deployment note.
            "X-Accel-Buffering": "no",
        },
    )
