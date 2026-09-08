"""One row per request, holding names and counts, and no part of any answer.

A request nobody can reconstruct is the failure this module exists to prevent, and it is a
failure that only ever shows up months later, in an argument. Somebody says the system told
them one thing, somebody else says it told them another, and the only way to settle it is a
row saying who asked, at what reach, through which lane, and what came back. That row has to
survive longer than the answer did, which is exactly why it may not contain the answer.

**The id is minted before anybody is identified, and `mint_trace_id` has nowhere to put a
principal.** An id minted after authentication does not exist for the request that failed to
authenticate, and a refused request is the one somebody actually needs to trace. So the
function takes no arguments at all: not a principal, not a caller, not a token, not a
request. There is no ordering of the pipeline in which it could be given one, because there
is no parameter to give. `brain.gate.context.open_trace` already takes an id at ingress and
`brain.app` already mints one in a middleware that runs before the gate, and neither of them
is a function anything can assert about; this is.

**Every field is a name, a count, a hash or a duration, and that is checked rather than
intended.** `M27.1.5`'s list is long on purpose and every entry on it happens to be one of
those four things. `_NAME_FIELDS`, `_COUNT_FIELDS`, `_DURATION_FIELDS` and `_FLAG_FIELDS`
partition the declared list, and a test asserts the partition is exact, so a nineteenth field
holding a sentence cannot be added without the partition failing first.

**The value rule is `brain.ops.tracing`'s and there is no second one here.** `_would_be_masked`
asks `tracing.mask` what it would do with a value under an allowlisted key, rather than
carrying a copy of `VALUE_TOKEN_RE`. A second grammar would drift, and it would drift in the
direction of admitting more, because the person loosening it is always the person whose
identifier was refused. Refusal is at construction: a record carrying a value rather than a
name cannot be built, so there is no window in which one exists and has to be caught later.

**One field is pinned to a shape as well, and a shape is not a second value rule.**
`entitlement_hash` is what a support conversation quotes beside a trace id when two people
disagree about what they saw, and the value rule cannot make it one: `"abc"` is system
vocabulary, so `tracing.mask` keeps it and a five-year row stores a hash identifying no
reach. `_ENT_HASH_RE` is `brain.audit.ledger.ENT_HASH`, imported for the same reason
`_TRACE_ID_RE` is, and it only ever narrows, because every hash it admits the value rule
admitted already.

**Where the value rule costs something, it is named rather than left to be found.** That
rule was written about system vocabulary and a principal identifier is not system
vocabulary, so a directory handing over `U_WeiLing` or an email address gets audit entries
and no ledger row at all.
`A_PRINCIPAL_THE_TRACE_GRAMMAR_REFUSES_HAS_NO_LEDGER_ROW_AT_ALL` says so where somebody
hitting it will read it, and a test pins it, so the day it changes is a day somebody decided
to change it rather than a day somebody widened a regular expression.

**The ledger row and the span are two different artefacts, and the existing allowlist is
what separates them.** The row carries `principal`, because the metadata ledger is ours,
entitlement-controlled and holds no content; the span does not, because
`tracing.SAFE_ATTRIBUTES` deliberately omits `principal_id` so that an operator with access
to a trace store cannot reconstruct a person's movements. That difference is not a rule
written here. It falls out of running the row through `tracing.mask`, which is the only way
anything in this module produces a span.

**Thirteen of the eighteen fields are None today, and the reasons are declared rather than
implied.** `UNFILLABLE_TODAY` names each one and says what is missing. There is no model call
anywhere in this repository, so there is no provider, no time to first token and no token
count; there is no agent on the one live request path, so there is no agent version; nothing
counts or times a tool call. Those fields are optional and default to None, and the fields
that can be filled honestly today are required and have no default, so the difference is
enforced by the dataclass rather than by a comment.

`redaction_count` is the one worth naming separately, because a plausible value exists and it
would be wrong. `brain.gate.answer._redacted` builds a `RedactionTrace` with an empty
redaction list and says so in its own docstring: the lane was never told what was withheld, so
an empty list is that lane's ignorance and not a measurement. Recording zero would put a
measured-looking figure in a five-year table, and the figure would be false on exactly the
requests where something was withheld.

**Traffic class has no default, and there is no value a default could be.** `TrafficClass`
has four members and none of them means "unknown", so `open_request` cannot be given a
sensible default even by somebody trying. The parameter is keyword-only with no default, which
makes an omission a type error under strict mypy and a `TypeError` at run time, and
`telemetry_gaps` scans the surface for a traffic class that has acquired one, the way
`brain.ops.retention.retention_policy_gaps` scans for an argument that would postpone a
window. The point of the declaration is that machine traffic can be excluded from the numbers
about people, which is what `brain.ops.limits.counts_towards_metrics` does with it, and a
class that defaults is a class nobody sets.

**A payload read checks the role, writes the audit row, then reads.** The order is the whole
of `read_payload_with_role`, and only the middle step is this module's: the row and the read
are `tracing.read_payload`, which already argues why recording first is the correct trade.
What is added here is that the role check cannot be skipped by a caller who reached for the
lower-level function, because there is one function that does both.

Rejected: assembling the record inside a `brain.gate.compose.TraceSink`. That is tempting and
it is the wrong place. A sink is the one point today where the policy epoch, the entitlement
hash and the redaction counts are all in scope for one request, and it is reached only when
the lane answered, because `compose` is called on the answer path and nowhere else. A ledger
built there would hold every successful request and no refused one, which is precisely the
failure the first paragraph of this docstring is about.

Rejected: defaulting an unfillable field to zero. Zero is a measurement and None is an
absence, and a report that cannot tell them apart reads "no retries happened" off a system
that does not count retries.

Rejected: widening `tracing.SAFE_ATTRIBUTES` so that the counts survive into a span. They
would be safe there, and that is not the question: the allowlist is closed, it is argued for
at length where it lives, and this module has no business editing another module's closed set
to make its own output prettier. The consequence is stated plainly rather than worked around:
a span built from one of these records carries `model`, `trace_id` and `traffic_class` and a
mask token for everything else, and the counts live in the ledger instead.

Rejected: a status vocabulary that separates DENIED from ABSENT. `status_for` maps both to one
member, referenced once rather than written twice, for the reason `brain.core.errors` gives
about messages and `brain.api_routes` gives about totals: a per-principal count of refusals is
a count of things that exist and are hidden, and it is the same leak whether it arrives in a
sentence or in a dashboard. UNRESOLVED keeps a member of its own because the asker was already
told their name matched more than one thing, so counting it discloses nothing they do not
have.

Rejected: writing the payload-read row through `brain.audit.record`. There is no `AuditAction`
member that fits, the enum is closed and pinned by an invariant test, and `brain.ops.tracing`
has already refused to widen it with the reason: every holder of `read:audit.*` would start
seeing trace-payload reads in the client-facing audit view. Deciding it differently here would
leave two answers to one question in one package.

What is not built, said rather than left to be inferred. There is **no ledger table**: `obs`
holds the audit chain and nothing else, and no migration in this repository creates a
metadata-ledger row. There is **no payload store**: `brain.ops.trace_sink` drops the payload
because there is nowhere with the right permissions to put it. And **nothing calls any of
this**, which is more than a matter of this module owning no route.

`brain.api_routes.answer` is the one live request path, and it can read three of the five
required fields off what it already holds: `principal` from `asked.caller.principal.id`,
`entitlement_hash` from `asked.reach.ent_hash()`, and `cache_hit` from `Answered.from_cache`.
The other two it cannot. Nothing on that path carries a `Lane`: `api_routes.Asking` has no
field for one and no `GateContext` is built there, so a `lane` would be an assertion about
which lane ran rather than a reading. And `status_for` is unreachable from it, because
`Answered` carries a `brain.gate.abstain.Abstention` whose `AbstentionReason` deliberately
shares no value with `Outcome` and has no mapping onto one, so only the answered case has a
status at all. The ingress is buildable there and **not through `open_request`**:
`brain.app.trace` has already minted an id into structlog's context variables before the gate
runs, which `brain.api` reads back, so a route calling `open_request` would mint a second id
for a request that already has one and file half its evidence under each.

Task ids: M27.1.1, M27.1.2, M27.1.3, M27.1.4, M27.1.5, M27.1.6
"""

from __future__ import annotations

import enum
import inspect
import re
import secrets
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import MISSING, dataclass, fields
from datetime import datetime
from types import MappingProxyType
from typing import Final, assert_never, get_type_hints

from brain.audit.ledger import ENT_HASH, TRACE_ID
from brain.core.errors import Outcome
from brain.core.lane import Lane
from brain.gate.context import TrafficClass
from brain.ops.retention import DataClass, Lifetime, horizon_for
from brain.ops.tracing import (
    SAFE_ATTRIBUTES,
    TRACE_ENVIRONMENTS,
    PayloadRead,
    Span,
    mask,
    may_read_payloads,
    read_payload,
)


class TelemetryError(Exception):
    """Raised when a request record would carry a value, a negative count or no window."""


#: The grammar a trace id has to satisfy. `brain.audit.ledger.TRACE_ID`, imported rather than
#: retyped, so a minted id is by construction one an audit entry for the same request can
#: carry. A second spelling of it here would drift, and the drift would only be discovered by
#: an audit entry refusing an id that the ledger row it belongs beside had already accepted.
_TRACE_ID_RE: Final = re.compile(TRACE_ID)

#: The shape an entitlement hash has, from `brain.audit.ledger.ENT_HASH`, which is where the
#: estate already declares it and which the audit entry for this same request is validated
#: against.
#:
#: Needed as well as the value rule rather than instead of it, and the difference is the point.
#: `tracing.mask` asks whether a string is system vocabulary, and `"abc"` is: it would be kept
#: unmasked and stored for five years in a column a support conversation quotes beside a trace
#: id when two people disagree about what they saw. Quoting it would be quoting nothing. The
#: value rule is what stops a sentence getting in; this is what makes the field the thing it
#: is named after, and it only ever narrows, because every hash it admits is thirty-two
#: lowercase hex characters and `VALUE_TOKEN_RE` admits all of those already.
_ENT_HASH_RE: Final = re.compile(ENT_HASH)


# ------------------------------------------------------------------ written-down reasons

#: Why the minting function takes nothing at all.
AN_ID_MINTED_AFTER_IDENTIFY_CANNOT_BE_QUOTED_IN_A_REFUSAL: Final = (
    "The request worth tracing is the one that went wrong, and the ones that go wrong "
    "earliest are the ones that never got past identification. An id minted once a "
    "principal is known does not exist for those, so the refusal a person is shown carries "
    "nothing they can quote and the operator has nothing to look up. Minting takes no "
    "arguments, which is stronger than minting early: a function with a principal parameter "
    "acquires a caller that has one, and then the mint has quietly moved after identify "
    "without anything in the diff saying so."
)

#: Why the ledger can be kept for years while the payloads cannot.
THE_LEDGER_HOLDS_NAMES_AND_COUNTS_AND_NEVER_A_VALUE: Final = (
    "Every field on a request record is a name, an identifier, a hash, a count or a "
    "duration. None of them is a thing somebody said or a thing the system answered, and "
    "that is what makes a five-year window affordable rather than reckless. The moment one "
    "field can hold a sentence, the ledger becomes the longest-lived copy of the business, "
    "held under the permissions of whoever reads dashboards rather than the permissions of "
    "whoever could read the record."
)

#: What the value rule costs, said here rather than discovered on somebody's deployment.
A_PRINCIPAL_THE_TRACE_GRAMMAR_REFUSES_HAS_NO_LEDGER_ROW_AT_ALL: Final = (
    "The value rule is brain.ops.tracing's, and that rule was written about system "
    "vocabulary: lowercase tokens, no capitals and no at-sign. A principal identifier is not "
    "system vocabulary. brain.core.principal.Principal.id is any string a client's directory "
    "hands over, and brain.audit.ledger.IDENTIFIER admits capitals and an at-sign because "
    "real ids in this system have them. So a directory whose ids look like U_WeiLing, or an "
    "email address, can have its audit entries written and cannot have a ledger row written "
    "at all, which is the reconstruction this module's first paragraph is about, lost to the "
    "guard that exists to protect it. It fails closed, which is the right direction to fail, "
    "and it is a gap rather than a design: closing it means deciding whether this ledger may "
    "hold an identifier the trace masker would refuse, and that is a decision about a "
    "five-year table rather than a line to widen in passing."
)

#: Why a status may not tell a refusal from an absence.
A_STATUS_THAT_SEPARATES_DENIED_FROM_ABSENT_IS_A_HIDDEN_ITEM_COUNT: Final = (
    "DENIED and ABSENT are one outcome to everybody outside the audit chain, and a count is "
    "not an exception to that. Thirty refusals against one principal in a month is thirty "
    "facts about things that exist and are hidden from them, and it is the same disclosure "
    "as 'showing 3 of 47' with a longer path to it. The audit ledger records the real reason "
    "and is entitlement-filtered; this ledger goes to a usage report and must not."
)

#: Why an unfillable field is None and never zero.
A_FIELD_NOBODY_MEASURES_IS_NONE_AND_NEVER_ZERO: Final = (
    "Zero is a measurement. None is the absence of one. A report reading zero retries off a "
    "system that does not count retries is worse than a report reading nothing, because the "
    "first is believed. So a field nothing can fill today carries None, the reason it cannot "
    "be filled is declared beside it in UNFILLABLE_TODAY, and filling it means deleting an "
    "entry from that mapping rather than quietly changing a default."
)

#: Why the role is checked before the audit row and the row before the read.
THE_ROLE_COMES_FIRST_AND_THE_ROW_COMES_BEFORE_THE_READ: Final = (
    "Three steps in one function so a caller cannot perform two of them. The role is checked "
    "first, because PayloadRead is the record of a read that happened and a table mixing "
    "reads with refused attempts cannot be counted for either. The row is written before the "
    "fetch, because a read that failed halfway still happened and is the read most worth "
    "having a row for. A refused attempt is therefore not recorded anywhere, which is a real "
    "gap: it belongs in the audit chain and no AuditAction member fits it."
)

#: Why the traffic class is a required argument rather than a defaulted one.
A_TRAFFIC_CLASS_WITH_A_DEFAULT_IS_A_TRAFFIC_CLASS_NOBODY_SETS: Final = (
    "The class exists so machine traffic can be told from human traffic and excluded from "
    "the numbers about people. A default is set once by whoever wrote the first channel and "
    "inherited silently by every channel after it, and the metric it distorts is the one "
    "nobody checks, because it looks plausible. TrafficClass has no member meaning unknown, "
    "so there is no honest default available even to somebody looking for one, and the "
    "parameter carries none."
)


# ------------------------------------------------------------------- the id (M27.1.1)

#: Bytes of randomness behind a minted id. Sixteen gives thirty-two hex characters, which is
#: what `brain.app` already mints with `uuid.uuid4().hex` and what `brain.audit.ledger.TRACE_ID`
#: and the sixty-four character `trace_id` column in `brain.db.AuditMixin` both admit.
#:
#: Random rather than sequential or time-ordered, and that is a permission decision rather
#: than a style one. A trace reference is quotable and grants nothing, which means it gets
#: handed to whoever was refused; a countable id would let that person walk to the traces
#: either side of their own.
_TRACE_ID_BYTES: Final = 16


def mint_trace_id() -> str:
    """A trace id, minted from nothing. This function takes no arguments and never will.

    See `AN_ID_MINTED_AFTER_IDENTIFY_CANNOT_BE_QUOTED_IN_A_REFUSAL`. The emptiness of the
    signature is the property, and it is asserted rather than described: there is no
    principal parameter, no request parameter and no context parameter, so there is no
    ordering of the gate in which minting could come to depend on knowing who is asking.
    """
    return secrets.token_hex(_TRACE_ID_BYTES)


# --------------------------------------------------------------- the ingress (M27.1.6)


@dataclass(frozen=True)
class Ingress:
    """What is known before identification: an id, a declared traffic class, and a clock.

    Deliberately three fields and deliberately not four. There is no principal here, no
    channel-derived guess and no place to put either, so an `Ingress` constructed at the top
    of a request is complete rather than partially filled in, and a request that is refused
    one line later still has one.
    """

    trace_id: str
    #: Declared by whoever accepted the request. No default; see
    #: `A_TRAFFIC_CLASS_WITH_A_DEFAULT_IS_A_TRAFFIC_CLASS_NOBODY_SETS`.
    traffic_class: TrafficClass
    received_at: datetime

    def __post_init__(self) -> None:
        # `fullmatch` rather than `match`, and the difference is one character of input.
        # `TRACE_ID` ends in `$`, which matches before a trailing newline as well as at the
        # end of the string, so `match` admits an id ending in one: a log line pretending to
        # be two, in the field every log line and every ledger row is keyed on. Stricter than
        # the ledger by exactly that case, which is the safe direction, and refuses nothing a
        # real caller can send, because a header cannot carry a raw newline.
        if not _TRACE_ID_RE.fullmatch(self.trace_id):
            msg = (
                f"trace id {self.trace_id!r} is not one the audit ledger would accept, so a "
                "request recorded under it could never be joined to its audit entries"
            )
            raise TelemetryError(msg)
        if self.received_at.tzinfo is None:
            # The same rule the payload-read row and the deployment chain hold: two
            # operators in two timezones produce a sequence nothing can order, and the
            # ordering is most of what a ledger is read for.
            msg = "an ingress time with no timezone cannot be ordered against another one"
            raise TelemetryError(msg)


def open_request(*, traffic_class: TrafficClass, received_at: datetime) -> Ingress:
    """Mint the id and open the record, before anything knows who is asking.

    Keyword-only and with no defaults, so a call site reads as a declaration rather than as
    two positional values in an order somebody has to remember. The traffic class is an
    argument rather than something derived here from a channel, because
    `brain.gate.context.traffic_class_for` is where that derivation lives and a second copy
    of it would be a second answer to one question. What this function guarantees is only
    that no record can be opened without one.
    """
    return Ingress(trace_id=mint_trace_id(), traffic_class=traffic_class, received_at=received_at)


# ------------------------------------------------------------- the value rule (M27.1.4)

#: The environment a probe span is tagged with. `Span` refuses an unknown environment, so a
#: probe needs a real one; it is taken from `tracing.TRACE_ENVIRONMENTS` rather than written
#: out, and the probe is discarded rather than sent, so nothing is ever filed under it.
_PROBE_ENVIRONMENT: Final = TRACE_ENVIRONMENTS[0]

#: The allowlisted key a candidate value is filed under while it is being asked about. It
#: has to be on `tracing.SAFE_ATTRIBUTES` or the question being asked changes from "is this
#: value system vocabulary" to "is this key allowlisted", and everything would be refused.
#: `telemetry_gaps` reports it if the allowlist ever drops the key.
_PROBE_KEY: Final = "tool"

#: The name a probe span carries. Never sent; see `_would_be_masked`.
_PROBE_SPAN_NAME: Final = "telemetry.probe"


def _would_be_masked(value: str) -> bool:
    """Whether `tracing.mask` would replace this value with a shape.

    Asked of `mask` rather than answered here, and that is the whole point of the function.
    A copy of `VALUE_TOKEN_RE` and `SAFE_VALUE_MAX_CHARS` in this module would be a second
    rule about what counts as system vocabulary, and two such rules disagree eventually: the
    one that gets loosened is whichever module the person was looking at when their
    identifier was refused. Here there is nothing to loosen.

    The probe is constructed and thrown away. It never reaches a sink, which is why filing a
    candidate under `tool` in the `development` environment costs nothing and discloses
    nothing.
    """
    probe = Span(
        name=_PROBE_SPAN_NAME,
        environment=_PROBE_ENVIRONMENT,
        attributes={_PROBE_KEY: value},
    )
    return mask(probe).attributes[_PROBE_KEY] != value


# ---------------------------------------------------------------- the status vocabulary


class RequestStatus(enum.StrEnum):
    """How a request ended, in the coarsest vocabulary that is still useful.

    Coarse on purpose. Every member has to be countable per principal and per department in a
    usage report without the count itself disclosing anything, which rules out any member
    that would separate a refusal from an absence. See
    `A_STATUS_THAT_SEPARATES_DENIED_FROM_ABSENT_IS_A_HIDDEN_ITEM_COUNT`.
    """

    #: The lane produced an answer. Not an outcome in `brain.core.errors`, because an answer
    #: is not an error, which is why `status_for` cannot produce this one.
    ANSWERED = "answered"
    #: Nothing came back. A record that does not exist, a record this caller may not see, a
    #: question no rule matched: one member for all of them.
    NOTHING_RETURNED = "nothing_returned"
    #: The name matched more than one thing. Its own member because the asker was told so.
    UNRESOLVED = "unresolved"
    #: A source could not be reached and nothing stale was substituted for it.
    DEGRADED = "degraded"
    #: A fault. Ours, not theirs.
    FAILED = "failed"


def status_for(outcome: Outcome) -> RequestStatus:
    """The status one error outcome is recorded as.

    `DENIED` and `ABSENT` return the same member, written once rather than as two literals
    that happen to agree, which is the construction `brain.gate.abstain.PUBLIC_TEXT` uses for
    the same pair of outcomes. The property a test can hold this to is not "two names look
    alike" but "two outcomes share a status exactly when they share a public message", and
    `brain.core.errors` is where those messages are declared.

    `assert_never` for the reason `brain.ops.retention.horizon_for` uses it: a sixth outcome
    cannot reach production without somebody deciding whether it is countable, and a
    dictionary lookup with a default would decide it for them.
    """
    match outcome:
        case Outcome.DENIED | Outcome.ABSENT:
            return RequestStatus.NOTHING_RETURNED
        case Outcome.UNRESOLVED:
            return RequestStatus.UNRESOLVED
        case Outcome.DEGRADED:
            return RequestStatus.DEGRADED
        case Outcome.FAILED:
            return RequestStatus.FAILED
        case _:  # pragma: no cover - unreachable while Outcome has five members
            assert_never(outcome)


# ------------------------------------------------------------ the request record (M27.1.5)

#: Exactly the fields M27.1.5 names, in the order the leaf names them, declared once.
#:
#: The test that checks the record reads this tuple rather than restating the names, because
#: a list restated in a test is a list that agrees with itself while disagreeing with the
#: leaf. A field silently missing from here is a request nobody can reconstruct, and the
#: reconstruction is the only reason the row is kept for five years.
TELEMETRY_FIELDS: Final[tuple[str, ...]] = (
    "principal",
    "agent_version",
    "policy_epoch",
    "entitlement_hash",
    "lane",
    "model",
    "provider",
    "time_to_first_token_ms",
    "tokens_in",
    "tokens_out",
    "tool_count",
    "tool_latency_ms",
    "connector",
    "cache_hit",
    "redaction_count",
    "fallback_count",
    "retry_count",
    "status",
)

#: The fields holding a name, an identifier or a hash. Checked against `tracing.mask` before
#: a record exists, so none of them can hold a sentence.
_NAME_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "principal",
        "agent_version",
        "policy_epoch",
        "entitlement_hash",
        "lane",
        "model",
        "provider",
        "connector",
        "status",
    }
)

#: The fields holding a count. Never negative, and never a total of anything withheld: every
#: one of these counts something this request did rather than something it was refused.
_COUNT_FIELDS: Final[frozenset[str]] = frozenset(
    {"tokens_in", "tokens_out", "tool_count", "redaction_count", "fallback_count", "retry_count"}
)

#: The fields holding a duration in milliseconds.
_DURATION_FIELDS: Final[frozenset[str]] = frozenset({"time_to_first_token_ms", "tool_latency_ms"})

#: The one field holding a flag.
_FLAG_FIELDS: Final[frozenset[str]] = frozenset({"cache_hit"})

#: Every field nothing in this repository can fill today, and what is missing.
#:
#: A mapping rather than a paragraph, so the claim is machine-readable: a test asserts that
#: exactly these fields are optional on the record and that every other declared field is
#: required. Filling one means deleting its entry here, which fails that test until the
#: dataclass is changed to match, so the two cannot drift.
UNFILLABLE_TODAY: Final[Mapping[str, str]] = MappingProxyType(
    {
        "agent_version": (
            "no agent runs on the one live request path. brain.api_routes.asking argues that "
            "the agent term of the invariant is deliberately absent there rather than faked, "
            "so there is no agent and therefore no version of one to record"
        ),
        "policy_epoch": (
            "the epoch is computed inside brain.gate.answer.answer_lane and travels to the "
            "trace sink in a RedactionTrace. Answered carries no field holding it, so a "
            "route cannot read it back, and the entity it belongs to is deliberately not "
            "disclosed to the route either"
        ),
        "model": (
            "no model is called anywhere in this repository. See "
            "brain.models.driver.CONCRETE_ADAPTER_NOT_BUILT: what exists is the protocol, "
            "the per-lane call policy and the router, and nothing that speaks to a provider"
        ),
        "provider": (
            "the same absence as model. A provider is which pool answered, and no pool has "
            "been asked anything"
        ),
        "time_to_first_token_ms": (
            "there is no first token, because there is no model call to stream one. A figure "
            "here today could only be the time to the first frame, which is a different "
            "measurement wearing this one's name"
        ),
        "tokens_in": "nothing counts tokens, because nothing sends any",
        "tokens_out": "nothing counts tokens, because nothing produces any",
        "tool_count": (
            "brain.gate.fast_lane has nowhere to put a tool and says so, and the row read the "
            "answer path performs is not counted by anything between the reader and the route"
        ),
        "tool_latency_ms": (
            "nothing times the row read. brain.gate.answer takes now as a parameter and reads "
            "no clock, deliberately, so the lane cannot time itself"
        ),
        "connector": (
            "the answer path reaches a row reader rather than a connector, and on a deployed "
            "instance brain.tools.startup registers no row tool at all, so no connector is "
            "reached by anybody"
        ),
        "redaction_count": (
            "zero would be wrong rather than merely unknown. brain.gate.answer._redacted "
            "builds a RedactionTrace with an empty redaction list because the lane was never "
            "told what was withheld, and its own docstring says an empty list is not a claim "
            "that nothing was redacted. Recording zero would be false on exactly the requests "
            "where something was"
        ),
        "fallback_count": (
            "a fallback is a decision about a model chain. brain.models.routing declares the "
            "rules and nothing invokes them, so there is no ladder to have stepped down"
        ),
        "retry_count": (
            "the same absence as fallback_count. brain.models.adapter pins num_retries and "
            "makes one transport call, and no transport call has been made"
        ),
    }
)


@dataclass(frozen=True, kw_only=True)
class RequestTelemetry:
    """One request, as the metadata ledger holds it. Names and counts, and no content.

    Keyword-only, because eighteen positional fields is an ordering nobody can hold in their
    head and a swapped pair of counts is a silent wrong number rather than an error.

    Fields are declared in the order M27.1.5 names them, and `TELEMETRY_FIELDS` is that order
    written once. The five with no default are the five a caller can fill honestly today;
    the thirteen defaulting to None are `UNFILLABLE_TODAY`, and a test pins the two sets
    against each other so the mapping cannot describe a record that no longer matches it.

    Every string field is checked against `tracing.mask` at construction, so a record
    carrying a person's name rather than their identifier does not exist to be written. See
    `THE_LEDGER_HOLDS_NAMES_AND_COUNTS_AND_NEVER_A_VALUE`.
    """

    #: The ingress facts, carried as one object rather than spread across three fields, so
    #: that "was this request recorded from the start" is one question with one answer.
    ingress: Ingress

    principal: str
    agent_version: str | None = None
    policy_epoch: str | None = None
    entitlement_hash: str
    lane: Lane
    model: str | None = None
    provider: str | None = None
    time_to_first_token_ms: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    tool_count: int | None = None
    tool_latency_ms: float | None = None
    connector: str | None = None
    cache_hit: bool
    redaction_count: int | None = None
    fallback_count: int | None = None
    retry_count: int | None = None
    status: RequestStatus

    def __post_init__(self) -> None:
        for name in sorted(_NAME_FIELDS):
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, str) or _would_be_masked(value):
                msg = (
                    f"{name} holds {value!r}, which brain.ops.tracing would mask rather than "
                    "keep, so it is a value and not a name; the metadata ledger is retained "
                    f"for {LEDGER_RETENTION_DAYS} days and holds no values"
                )
                raise TelemetryError(msg)
        if not _ENT_HASH_RE.fullmatch(self.entitlement_hash):
            # The loop above has already said this is not a sentence. It cannot say it is a
            # hash: `"abc"` is system vocabulary and would be kept. See `_ENT_HASH_RE`.
            msg = (
                f"entitlement_hash holds {self.entitlement_hash!r}, which is not the "
                "thirty-two hex characters brain.core.entitlement.EntitlementSet.ent_hash "
                "produces, so it identifies no reach and a row written under it can never be "
                "compared with the audit entries for the same request"
            )
            raise TelemetryError(msg)
        for name in sorted(_COUNT_FIELDS | _DURATION_FIELDS):
            measured = getattr(self, name)
            if measured is not None and measured < 0:
                # A negative count is a subtraction that went the wrong way, and the usual
                # source of one is a figure derived from something withheld. It is refused
                # here rather than stored and puzzled over in a report.
                msg = f"{name} is {measured}, and a count or a duration cannot be negative"
                raise TelemetryError(msg)

    def ledger_row(self) -> Mapping[str, object]:
        """The row as the ledger stores it: the ingress facts and every declared field.

        Built by walking `TELEMETRY_FIELDS` rather than by writing the eighteen names out
        again, and that is the opposite of the choice `brain.api_routes.page_from` makes
        about a response body, deliberately. A response body must not gain a field because a
        copy loop was generous; a ledger row must not lose one because somebody forgot a
        line, since the row is the only reconstruction of the request that will exist. The
        two-way test between this tuple and the dataclass is what keeps the generosity safe.
        """
        row: dict[str, object] = {
            "trace_id": self.ingress.trace_id,
            "traffic_class": self.ingress.traffic_class,
            "received_at": self.ingress.received_at,
        }
        for name in TELEMETRY_FIELDS:
            row[name] = getattr(self, name)
        return MappingProxyType(row)


# ------------------------------------------------------------ the masked span (M27.1.4)

#: The name a request span carries. A constant because `tracing.mask` does not mask a span's
#: name, so a name built by interpolating anything about the request would be the one part of
#: the span that never went through the allowlist.
SPAN_NAME: Final = "request"


def span_for(record: RequestTelemetry, *, environment: str) -> Span:
    """The span this record becomes, masked before it is returned.

    **There is no function in this module that returns an unmasked span.** That is the whole
    of M27.1.4 as it applies here: the masking is not a step a caller performs on the way
    out, it is the only way to obtain the object at all, so there is no window in which an
    unmasked span exists and could be handed to a client by somebody in a hurry.

    What comes back is far less than `ledger_row` holds, and that is the existing allowlist
    working rather than a loss. `tracing.SAFE_ATTRIBUTES` names twelve keys and three of them
    appear here, so `model`, `trace_id` and `traffic_class` survive and everything else
    arrives as a shape. `principal` is masked in particular, because a trace store is read by
    operators who cannot read the records underneath it and a person's movements must not be
    reconstructable there. The ledger row keeps it; the span does not; neither of those is
    decided in this file.
    """
    return mask(Span(name=SPAN_NAME, environment=environment, attributes=record.ledger_row()))


# ------------------------------------------------------------- the payload read (M27.1.3)


def read_payload_with_role(
    *,
    realm_roles: Iterable[str],
    at: datetime,
    actor: str,
    trace_id: str,
    reason: str,
    record: Callable[[PayloadRead], None],
    fetch: Callable[[], str],
) -> str:
    """Check the role, write the audit row, then read. See
    `THE_ROLE_COMES_FIRST_AND_THE_ROW_COMES_BEFORE_THE_READ`.

    One function rather than three calls a caller composes, because a caller composing them
    can compose two. `tracing.may_read_payloads` and `tracing.read_payload` both exist and
    both are correct, and what was missing was anything making it impossible to reach the
    second without the first.

    The role is a realm role in the identity provider and not a `brain.identity.roles.Role`,
    which is `tracing.PAYLOAD_ROLE`'s own argument: reading raw payloads is something an
    operator is granted for an afternoon during an incident and loses again, and adding a
    seventh member to the platform's role enum would make it a permanent identity instead.
    """
    if not may_read_payloads(realm_roles):
        # Raised before the recorder is called, so no PayloadRead row exists for a read that
        # did not happen. The cost is that a refused attempt is recorded nowhere; that gap is
        # named in the module docstring rather than closed by putting a refusal in a table
        # whose rows mean "somebody read this".
        msg = "these roles do not admit reading a stored trace payload"
        raise TelemetryError(msg)
    return read_payload(
        PayloadRead(at=at, actor=actor, trace_id=trace_id, reason=reason), record, fetch
    )


# ------------------------------------------------------------- the ledger window (M27.1.2)


def _fixed_window(data_class: DataClass) -> int:
    """The declared window for a class, refusing one that has no clock.

    Takes the class rather than being inlined at the one call site, for the reason
    `brain.ops.retention._expiring` gives about its own guard: a helper that can only ever be
    called with a value known to be fine is a helper whose refusal has never been seen to
    fire, and it is still the branch that matters on the day somebody changes the horizon.
    """
    horizon = horizon_for(data_class)
    if horizon.lifetime is not Lifetime.FIXED_WINDOW or horizon.days is None:
        msg = (
            f"{data_class.value} is {horizon.lifetime.value}, so it declares no number of "
            "days and there is no window to record a ledger row against"
        )
        raise TelemetryError(msg)
    return horizon.days


#: The class the metadata ledger belongs to. Named rather than inlined so a mutation of it is
#: visible, and pinned by a test against the longest fixed window `brain.ops.retention`
#: declares: the ledger is the long one precisely because it holds no content, and pointing
#: this at any other class would silently shorten it to a window sized for something that does.
LEDGER_DATA_CLASS: Final = DataClass.METADATA_LEDGER

#: How long a request record is kept. Not a number chosen here. It is
#: `brain.ops.retention.horizon_for(DataClass.METADATA_LEDGER)`, which is itself pinned
#: against the processing-register review cycle and against every shorter window in the
#: estate, so the one figure lives in one place.
LEDGER_RETENTION_DAYS: Final[int] = _fixed_window(LEDGER_DATA_CLASS)


# ------------------------------------------------------------------ the absence of defaults

#: The functions a traffic class could arrive at with a default attached.
TELEMETRY_SURFACE: Final[tuple[Callable[..., object], ...]] = (open_request,)

#: The models it could arrive on instead.
TELEMETRY_MODELS: Final[tuple[type, ...]] = (Ingress, RequestTelemetry)


def telemetry_gaps(
    functions: Sequence[Callable[..., object]] | None = None,
    models: Sequence[type] | None = None,
) -> tuple[str, ...]:
    """Every way this module has stopped requiring a traffic class to be declared.

    The scan is the same mechanism `brain.ops.retention.retention_policy_gaps` uses against a
    per-row retention override, and it is here for the same reason: a rule that lives only in
    a docstring holds until somebody has a bad afternoon and adds one helpful default. A
    required keyword argument is the enforcement; this is what notices when it stops being
    one, on a surface that will grow more functions than it has today.

    Both surfaces are parameters defaulting to this module's own, for the reason
    `brain.ops.tracing.retention_gaps` takes one: a check that can only ever be pointed at
    code known to be clean is a check nobody has watched produce a finding, and nobody knows
    whether it can.

    The probe key is checked here too. It is not a permission rule, it is the difference
    between `_would_be_masked` asking about a value and asking about a key: if
    `tracing.SAFE_ATTRIBUTES` ever loses the key, every identifier is refused and no request
    can be recorded at all. That fails closed, loudly, and this says why.
    """
    findings: list[str] = []

    for function in TELEMETRY_SURFACE if functions is None else tuple(functions):
        hints = get_type_hints(function)
        for name, parameter in inspect.signature(function).parameters.items():
            if hints.get(name) is TrafficClass and parameter.default is not inspect.Parameter.empty:
                findings.append(
                    f"{function.__name__} defaults {name} to {parameter.default!r}, so a "
                    "channel that declares nothing is filed as whatever that is"
                )

    for model in TELEMETRY_MODELS if models is None else tuple(models):
        hints = get_type_hints(model)
        for declared in fields(model):
            if hints.get(declared.name) is not TrafficClass:
                continue
            if declared.default is not MISSING or declared.default_factory is not MISSING:
                findings.append(
                    f"{model.__name__}.{declared.name} carries a default traffic class, which "
                    "is the same omission arriving through the record rather than the call"
                )

    if _PROBE_KEY not in SAFE_ATTRIBUTES:
        findings.append(
            f"{_PROBE_KEY!r} is no longer in brain.ops.tracing.SAFE_ATTRIBUTES, so the value "
            "probe asks whether the key is allowlisted rather than whether the value is "
            "system vocabulary, and every identifier is refused"
        )
    return tuple(findings)
