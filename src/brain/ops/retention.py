"""How long each kind of thing is kept, and why a row never gets a say in it.

Retention is the policy that is quietly wrong for years. Nothing fails when a window is too
long: the bill grows, the blast radius of a future mistake grows with it, and the first
person to notice is whoever is reading a subject access request that came back with a
browser recording from 2024 in it. So the decisions are written down here, with the numbers
derived from where they are already declared rather than restated.

**The data class decides the horizon and a row cannot argue with it.** There is no
per-item override anywhere in this module, no `keep_until`, no exemption flag, and no
parameter that could carry one. A per-row override is not a feature, it is the mechanism by
which one payload lives forever: somebody sets it during an investigation, the investigation
ends, and the row is now the oldest copy of something in the estate with nothing pointing at
it. `horizon_for` takes a `DataClass` and nothing else, and `retention_policy_gaps` checks
that no public function here has grown an argument that would let a caller postpone a
window. See `THE_CLASS_DECIDES_AND_A_ROW_CANNOT_ARGUE`.

**The numbers are imported, not retyped.** The recordings window comes from
`brain.ops.storage.BUCKETS`, the trace window from `brain.ops.tracing.RETENTION`. A second
copy of "thirty days" here would be a second copy that drifts, and it would drift silently
in the direction that costs money, because the copy nobody looks at is the one that gets
raised. What this module adds is the *relations* between those windows, which is the part
nowhere else states: a payload must not outlive the trace that indexes it, a trace must not
outlive the metadata ledger, and the ledger is the longest bounded window in the system
because it is the only one holding no content.

**A store list assembled from memory is a store list that forgets one.** `Store` is the
single declaration of every place a person's data comes to rest, and it is checked against
two declarations that live elsewhere: every schema in `brain.db.SCHEMAS` must be claimed by
at least one store and every bucket in `brain.ops.storage.BUCKETS` by exactly one, or
`store_gaps` reports it. That is what makes "we looked everywhere" a checked claim rather
than a habit, and it is what makes adding a schema anywhere in the system a failing test
here rather than a store nobody searches. It is also why `brain.ops.erasure` and
`brain.ops.export` derive their store lists from this one instead of writing their own: a
subject access request that forgot a store is a subject access request that lied, and
nothing about it looks wrong.

**Nothing here reaches a store.** No client, no connection, no sweep loop. Every function
takes what an executor observed and returns what is wrong with it, the same split
`brain.ops.limits` and `brain.ops.limit_store` make, for the same reason: the case that is
always wrong is the boundary, and a boundary cannot be tested through a module that opens a
socket. `StoreSweeper` is the shape the executor must have. The executor itself is not
built, which is stated here rather than implied by the absence of a file.

Rejected: a single `retention_days` column on each table, set by whoever created the table.
It is cheaper and it is how every estate ends up with fourteen different windows nobody
chose, because a column default is a decision made by whoever was first rather than by
anybody weighing it. Rejected too: expressing retention as a bucket lifecycle rule alone,
which handles the object store and says nothing about the ten Postgres schemas where most
of a person actually lives.

Task ids: M25.1.1, M25.1.2, M25.1.3, M25.1.4, M25.1.5
"""

from __future__ import annotations

import enum
import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from typing import Final, Protocol, assert_never

from brain.audit.compliance import REGISTER_REVIEW_DAYS
from brain.db import SCHEMAS
from brain.ops.storage import BUCKETS, Bucket, bucket
from brain.ops.tracing import TraceRecord, retention_for


class RetentionError(Exception):
    """Raised when a horizon, a store declaration or a sweep result cannot be believed."""


# ------------------------------------------------------------------ written-down reasons
#: Why there is no per-row retention anywhere in this module.
THE_CLASS_DECIDES_AND_A_ROW_CANNOT_ARGUE = (
    "A horizon is a property of what a thing is, not of the row it happens to be in. The "
    "moment one row can carry its own window, the window it carries is longer, because "
    "nobody has ever set a per-row override to shorten something. It is set during an "
    "investigation by somebody who needs one more week, the investigation ends, and the "
    "row is now the oldest copy of a payload in the estate with no policy pointing at it "
    "and nothing that would ever find it again. So the class decides, there is no "
    "exemption field, and no function here takes an argument that could hold one."
)

#: Why a derived copy has no window of its own.
A_DERIVED_COPY_HAS_NO_LIFETIME_OF_ITS_OWN = (
    "A cache entry and an index row are not records, they are copies of records. Giving "
    "them a window of their own means picking a number, and any number other than 'as long "
    "as the source' is either a copy that outlives the thing it copied, which is a deleted "
    "record still answering questions, or a copy that expires early, which is a cache miss "
    "dressed up as policy. So they follow their source, and what a sweep looks for in them "
    "is not age but copies whose source is gone."
)

#: Why the metadata ledger is the longest bounded window in the system.
THE_LEDGER_IS_LONG_BECAUSE_IT_HOLDS_NO_CONTENT = (
    "Everything else on this list is kept short because it holds content, and content is "
    "what a mistake leaks. The metadata ledger holds who asked, when, through what, and how "
    "long it took, and no part of any answer. That is the whole reason it can be kept for "
    "years while the payloads from the same requests are gone in a month, and it is also "
    "why the length is not generosity: the ledger is what a question asked eighteen months "
    "ago is reconstructed from when somebody disputes what the system did."
)

#: Why a store missing from a sweep is a finding rather than a quiet pass.
A_SWEEP_THAT_SKIPS_A_STORE_KEEPS_IT_FOREVER = (
    "A retention run that reaches nine stores out of ten and reports success is a run that "
    "has told an operator the estate is clean while one store keeps everything forever. "
    "The absence of a result and a result of zero look identical in every report anybody "
    "writes, so they are separated here: a store with no census entry is reported as not "
    "reached, by name, and the report is not clean until every store has been reached."
)

#: Why the enforcement report carries counts and never identifiers.
A_RETENTION_REPORT_COUNTS_AND_NEVER_NAMES = (
    "A retention report is read by whoever runs the estate, which is not the same set of "
    "people as those entitled to what is in the stores. A count of rows past their horizon "
    "is a fact about volume; a list of the subjects those rows are about is a directory of "
    "who the system holds data on, assembled in a document that travels to a dashboard and "
    "an alert. So there is no field on any model here that can hold a subject, and the "
    "report is built from counts."
)


# ------------------------------------------------------------------------- data classes
class DataClass(enum.StrEnum):
    """What a thing is, which is the only input to how long it is kept.

    Closed, and deliberately coarser than the store list: two stores sharing a class is the
    normal case and is the point. A class per store would make "retention policy per data
    class" mean "retention policy per table", which is the arrangement where every table
    gets whatever window its author was thinking about that afternoon.
    """

    #: Rows we are the source of, and pointers to rows we are not: identity, grants,
    #: agents, projections, conversations. Kept while the thing they describe exists.
    BUSINESS_RECORD = "business_record"
    #: What the system worked out rather than was told: memory and knowledge.
    LEARNED = "learned"
    #: Who asked what, when, through what. No content, which is why it is the long one.
    METADATA_LEDGER = "metadata_ledger"
    #: Trace and observation rows: the shape of one run.
    TRACE = "trace"
    #: The inputs and outputs a run was given and produced. The short one.
    PAYLOAD = "payload"
    #: Screen and DOM capture from an automated browser run.
    RECORDING = "recording"
    #: A copy handed out, with the permissions of the original no longer attached.
    EXPORT = "export"
    #: A copy of everything above, as it was at the moment it was taken.
    BACKUP = "backup"
    #: Caches and indexes. No window of their own; see the constant above.
    DERIVED = "derived"
    #: The hash chain. The one class that outlives every policy in this module.
    AUDIT = "audit"


class Lifetime(enum.StrEnum):
    """The four shapes a horizon can have, so `days is None` never means three things.

    Written as a member rather than inferred from a null, because "kept while the record
    exists", "follows whatever it copied" and "never expires" are three different answers
    and a reader given `None` for all three cannot tell which one they are looking at. The
    difference matters at exactly one moment, which is when somebody is deciding whether a
    sweep may delete what it found.
    """

    #: `days` is set and the clock starts when the thing was written.
    FIXED_WINDOW = "fixed_window"
    #: No clock. It goes when the thing it describes goes.
    WHILE_THE_RECORD_EXISTS = "while_the_record_exists"
    #: No clock of its own. It goes when its source does.
    FOLLOWS_ITS_SOURCE = "follows_its_source"
    #: No clock and no removal. Only the audit chain.
    NEVER_EXPIRES = "never_expires"


@dataclass(frozen=True)
class Horizon:
    """How long one class is kept, and why that answer.

    `because` is required prose, for the reason `brain.ops.storage.Bucket.retention_reason`
    and `brain.ops.tracing.Retention.because` are: a window nobody can explain is a window
    that gets extended the first time somebody wants an older record, and the extension is
    permanent because nobody left behind what the original number was protecting.
    """

    data_class: DataClass
    lifetime: Lifetime
    #: Set if and only if the lifetime is a fixed window.
    days: int | None
    because: str

    def __post_init__(self) -> None:
        fixed = self.lifetime is Lifetime.FIXED_WINDOW
        if fixed and (self.days is None or self.days < 1):
            msg = (
                f"{self.data_class.value} declares a fixed window of {self.days} days, "
                "which is not a window"
            )
            raise RetentionError(msg)
        if not fixed and self.days is not None:
            # The combination that reads as a policy and is not one: a number sitting
            # beside a lifetime that says the number is not consulted. Whichever of the two
            # a future reader believes, half the callers believe the other.
            msg = (
                f"{self.data_class.value} is {self.lifetime.value} and also carries "
                f"{self.days} days; one of those is not true"
            )
            raise RetentionError(msg)
        if not self.because.strip():
            msg = f"{self.data_class.value} states no reason for its retention"
            raise RetentionError(msg)


def _expiring(candidate: Bucket) -> int:
    """A bucket's window, refusing the unbounded case.

    Takes the bucket rather than its name so the refusal can be exercised. A helper that
    could only ever be called with the four declared buckets is a helper whose guard has
    never been seen to fire, and `brain.ops.storage` already forbids an unbounded window on
    two of them, which means this branch would otherwise be unreachable by construction and
    still be the branch that matters on the day somebody relaxes that rule.
    """
    if candidate.retention_days is None:
        msg = (
            f"bucket {candidate.name!r} is kept until somebody deletes it, so there is no "
            "window to build a retention class from"
        )
        raise RetentionError(msg)
    return candidate.retention_days


#: The trace window, taken from where traces are declared. See `brain.ops.tracing.RETENTION`.
TRACE_RETENTION_DAYS: Final[int] = retention_for(TraceRecord.TRACE).days

#: M25.1.3, the payload store's thirty days. The thirty is not chosen here: it is the trace
#: window, because a payload is the content of a trace and a payload whose trace has expired
#: is unreachable and still billed. That is the same nesting argument
#: `brain.ops.tracing.retention_gaps` makes between a blob and its observation, applied one
#: level out. `horizon_gaps` checks the relation rather than trusting this line.
PAYLOAD_RETENTION_DAYS: Final[int] = TRACE_RETENTION_DAYS

#: M25.1.4's other half, from the bucket that holds them.
RECORDING_RETENTION_DAYS: Final[int] = _expiring(bucket("recordings"))

#: What makes a deletion incomplete for a while. See `brain.ops.erasure`.
BACKUP_RETENTION_DAYS: Final[int] = _expiring(bucket("backups"))

#: How long a produced export sits in the object store before it rotates out.
EXPORT_RETENTION_DAYS: Final[int] = _expiring(bucket("exports"))

#: M25.1.2, the long one. Five years, which is Singapore's statutory record-keeping period
#: for the accounts these questions are asked about, so a dispute about what the system did
#: in a financial year that is still open can be answered from the ledger rather than from
#: memory. It is affordable only because the ledger holds no content; see
#: `THE_LEDGER_IS_LONG_BECAUSE_IT_HOLDS_NO_CONTENT`. `horizon_gaps` pins it against
#: `brain.audit.compliance.REGISTER_REVIEW_DAYS`, because a processing register reviewed
#: once a year describes traffic the ledger must still be holding.
METADATA_LEDGER_RETENTION_DAYS: Final[int] = 5 * 365


HORIZONS: Final[tuple[Horizon, ...]] = (
    Horizon(
        data_class=DataClass.BUSINESS_RECORD,
        lifetime=Lifetime.WHILE_THE_RECORD_EXISTS,
        days=None,
        because=(
            "a projected row is a pointer at something in a source system and a grant is a "
            "statement about a person who still works here; both stop being true when the "
            "thing they point at goes, and neither has an age at which it becomes wrong"
        ),
    ),
    Horizon(
        data_class=DataClass.LEARNED,
        lifetime=Lifetime.WHILE_THE_RECORD_EXISTS,
        days=None,
        because=(
            "a memory going out of date is handled by decay and by "
            "brain.memory.correction, which mark rather than remove, and an age-based sweep "
            "over the same rows would delete the explanation of why the system stopped "
            "saying something while the mark that explains it was still being kept"
        ),
    ),
    Horizon(
        data_class=DataClass.METADATA_LEDGER,
        lifetime=Lifetime.FIXED_WINDOW,
        days=METADATA_LEDGER_RETENTION_DAYS,
        because=THE_LEDGER_IS_LONG_BECAUSE_IT_HOLDS_NO_CONTENT,
    ),
    Horizon(
        data_class=DataClass.TRACE,
        lifetime=Lifetime.FIXED_WINDOW,
        days=TRACE_RETENTION_DAYS,
        because=(
            "long enough to investigate anything a client reports in the month it happened, "
            "and declared in brain.ops.tracing where the trace ledger's own windows live"
        ),
    ),
    Horizon(
        data_class=DataClass.PAYLOAD,
        lifetime=Lifetime.FIXED_WINDOW,
        days=PAYLOAD_RETENTION_DAYS,
        because=(
            "the payload store is the one place a whole question and a whole answer sit "
            "together in the clear, so it is kept for exactly as long as the trace that "
            "indexes it and not one day past that"
        ),
    ),
    Horizon(
        data_class=DataClass.RECORDING,
        lifetime=Lifetime.FIXED_WINDOW,
        days=RECORDING_RETENTION_DAYS,
        because=(
            "a recording is a screen capture of everything the run could see, which is the "
            "widest single artefact this system holds; the window is the recordings "
            "bucket's own lifecycle rule and is not restated here"
        ),
    ),
    Horizon(
        data_class=DataClass.EXPORT,
        lifetime=Lifetime.FIXED_WINDOW,
        days=EXPORT_RETENTION_DAYS,
        because=(
            "an export is a flattened copy whose permissions no longer apply to it, kept "
            "long enough for the exchange that asked for it to conclude; the window is the "
            "exports bucket's own lifecycle rule"
        ),
    ),
    Horizon(
        data_class=DataClass.BACKUP,
        lifetime=Lifetime.FIXED_WINDOW,
        days=BACKUP_RETENTION_DAYS,
        because=(
            "one full monthly cycle plus a few days, from the backups bucket. This is the "
            "number that decides how long after a deletion the deleted data is still "
            "recoverable, which is why brain.ops.erasure reads it rather than a copy"
        ),
    ),
    Horizon(
        data_class=DataClass.DERIVED,
        lifetime=Lifetime.FOLLOWS_ITS_SOURCE,
        days=None,
        because=A_DERIVED_COPY_HAS_NO_LIFETIME_OF_ITS_OWN,
    ),
    Horizon(
        data_class=DataClass.AUDIT,
        lifetime=Lifetime.NEVER_EXPIRES,
        days=None,
        because=(
            "the audit chain is the one table that outlives every retention policy in the "
            "system, because a hash chain with a hole in the middle proves nothing and "
            "because the questions it answers are asked years later by people who were not "
            "here; brain.audit.ledger prunes only a verified prefix and only under its own "
            "rules, which are not these"
        ),
    ),
)


def horizon_for(data_class: DataClass) -> Horizon:
    """The window for one class. The only input is the class.

    `assert_never` for the reason `brain.ops.storage.bucket_for` uses it: a new data class
    cannot reach production without somebody deciding how long it is kept. A dictionary
    lookup with a default would hand it the default, and the default in every system that
    has one is the longest.

    Note the signature. There is no second parameter, and `retention_policy_gaps` asserts
    there never will be; see `THE_CLASS_DECIDES_AND_A_ROW_CANNOT_ARGUE`.
    """
    for entry in HORIZONS:
        if entry.data_class is data_class:
            return entry
    match data_class:  # pragma: no cover - unreachable while HORIZONS is complete
        case (
            DataClass.BUSINESS_RECORD
            | DataClass.LEARNED
            | DataClass.METADATA_LEDGER
            | DataClass.TRACE
            | DataClass.PAYLOAD
            | DataClass.RECORDING
            | DataClass.EXPORT
            | DataClass.BACKUP
            | DataClass.DERIVED
            | DataClass.AUDIT
        ):
            msg = f"{data_class.value} has no retention declared"
            raise RetentionError(msg)
        case _:
            assert_never(data_class)


def expires_at(data_class: DataClass, written_at: datetime) -> datetime | None:
    """When a thing of this class stops being kept, or None when age is not what ends it.

    None for the three lifetimes that are not clocks. A caller that treats None as "never"
    is right for the audit class and wrong for the other two, which is why `Lifetime` is on
    the horizon: the question "may this be swept" is answered by the lifetime, and this
    function only answers "when", for the classes where when is a date.
    """
    horizon = horizon_for(data_class)
    if horizon.lifetime is not Lifetime.FIXED_WINDOW or horizon.days is None:
        return None
    if written_at.tzinfo is None:
        msg = "a naive write time expires at whatever offset the machine happens to hold"
        raise RetentionError(msg)
    return written_at + timedelta(days=horizon.days)


def is_expired(data_class: DataClass, written_at: datetime, now: datetime) -> bool:
    """Whether age alone has ended this. False for every class without a clock."""
    due = expires_at(data_class, written_at)
    return due is not None and now >= due


def horizon_gaps(horizons: Sequence[Horizon] | None = None) -> tuple[str, ...]:
    """Every way a set of windows fails to hold together, in words an operator can act on.

    The windows are a parameter defaulting to the declared set, for the reason
    `brain.ops.tracing.retention_gaps` takes one: a check that can only ever run against the
    constant beside it cannot be shown to fail, and a check nobody has seen fail is a check
    nobody knows works.

    Four of the six rules are nesting rules and they all say one thing: nothing may outlive
    the record that makes it reachable. A payload whose trace is gone, a trace whose ledger
    row is gone, a trace blob whose payload class is gone: each of those is data with no
    route to it, still stored and still leakable, and the only thing that notices is the
    bill. The fifth pins the ledger against a figure from another module, so the long window
    cannot be quietly shortened below the review cycle that depends on it. The sixth says
    the audit class has no clock at all.
    """
    declared = HORIZONS if horizons is None else tuple(horizons)
    by_class = {entry.data_class: entry for entry in declared}
    findings: list[str] = []
    for data_class in DataClass:
        if data_class not in by_class:
            findings.append(f"{data_class.value}: no retention declared")
    if findings:
        return tuple(findings)

    def window(data_class: DataClass) -> int | None:
        return by_class[data_class].days

    payload, trace = window(DataClass.PAYLOAD), window(DataClass.TRACE)
    ledger = window(DataClass.METADATA_LEDGER)
    if payload is not None and trace is not None and payload > trace:
        findings.append(
            f"payloads are kept {payload} days and traces {trace}; a payload whose trace "
            "has expired is unreachable, still stored and still leakable"
        )
    if trace is not None and ledger is not None and trace > ledger:
        findings.append(
            f"traces are kept {trace} days and the metadata ledger {ledger}; a trace "
            "outliving the ledger row that indexes it cannot be found by anybody looking"
        )
    blob = retention_for(TraceRecord.BLOB).days
    if payload is not None and blob > payload:
        findings.append(
            f"trace blobs are kept {blob} days and the payload class {payload}; the blob "
            "store is where a payload too large to inline goes, so it cannot be the longer"
        )
    if ledger is not None:
        longest = max((entry.days for entry in declared if entry.days is not None), default=ledger)
        if ledger < longest:
            findings.append(
                f"the metadata ledger is kept {ledger} days and something else {longest}; "
                "the ledger holds no content and everything longer than it does"
            )
        if ledger < REGISTER_REVIEW_DAYS:
            findings.append(
                f"the metadata ledger is kept {ledger} days and a processing register is "
                f"reviewed every {REGISTER_REVIEW_DAYS}; a review would describe traffic "
                "the ledger no longer holds"
            )
    if by_class[DataClass.AUDIT].lifetime is not Lifetime.NEVER_EXPIRES:
        findings.append(
            f"the audit class is {by_class[DataClass.AUDIT].lifetime.value}; the chain is "
            "the one table that outlives every policy here and a window on it is a hole in "
            "the middle of a hash chain"
        )
    return tuple(findings)


# ------------------------------------------------------------------------------ stores
class Store(enum.StrEnum):
    """Every place a person's data comes to rest. Declared once, derived from everywhere.

    This enum is the reason `brain.ops.erasure` can claim to have looked everywhere.
    Assembling a subject access request from a list written by hand is how a store gets
    left out, and a store left out of a subject access request is not a bug anybody sees:
    the document comes back looking complete. So the list is here, once, it is checked
    against `brain.db.SCHEMAS` and `brain.ops.storage.BUCKETS`, and both consumers iterate
    it rather than naming members.

    Members are separated by *retention and reachability*, not by technology. `LEDGER` and
    `TRACE` are both rows in `obs` and are two members because they are kept for two very
    different lengths of time; `CACHE` and `INDEX` are two members because a deletion has to
    reach both and reaching one is not reaching the other.
    """

    #: Our own rows about the person: who they are, their sessions, their grants and scopes.
    ROWS = "rows"
    #: The agents, templates, skills, leashes and artifacts they own.
    AGENTS = "agents"
    #: Scheduled work running under their name, and their share of a budget.
    OPERATIONS = "operations"
    #: Conversations and the messages in them.
    CONVERSATION = "conversation"
    #: Projected connector fields and the entity resolution built on them.
    PROJECTION = "projection"
    #: Knowledge items, chunks and embeddings.
    KNOWLEDGE = "knowledge"
    #: The three memory kinds.
    MEMORY = "memory"
    #: The metadata ledger: who asked what, when, with no content.
    LEDGER = "ledger"
    #: Trace and observation rows.
    TRACE = "trace"
    #: The payload store: what a run was given and what it produced.
    PAYLOAD = "payload"
    #: Browser-run video and DOM capture.
    RECORDING = "recording"
    #: Files as they arrived and files an agent produced.
    ATTACHMENT = "attachment"
    #: Exports already produced, which are copies with the permissions stripped off.
    EXPORT = "export"
    #: Database dumps and configuration snapshots.
    BACKUP = "backup"
    #: The answer cache.
    CACHE = "cache"
    #: The retrieval index.
    INDEX = "index"
    #: The hash-chained audit ledger.
    AUDIT = "audit"


@dataclass(frozen=True)
class StoreFacts:
    """One store: what it holds, where it physically is, and which class governs it.

    `schemas` and `buckets` are what make the store list checkable against something outside
    itself. They are not used to reach anything; they are the claim that this member covers
    that schema, and `store_gaps` is what turns an unclaimed schema into a failure rather
    than into a silence.
    """

    store: Store
    data_class: DataClass
    #: Names from `brain.db.SCHEMAS`. Empty when the store is not in Postgres.
    schemas: frozenset[str]
    #: Names from `brain.ops.storage.BUCKETS`. Empty when the store is not in object storage.
    buckets: frozenset[str]
    #: What a reader of a subject access request would call this, in one line.
    holds: str

    def __post_init__(self) -> None:
        if not self.holds.strip():
            msg = f"store {self.store.value} says nothing about what it holds"
            raise RetentionError(msg)


STORES: Final[tuple[StoreFacts, ...]] = (
    StoreFacts(
        store=Store.ROWS,
        data_class=DataClass.BUSINESS_RECORD,
        schemas=frozenset({"auth", "gate"}),
        buckets=frozenset(),
        holds="who they are, the sessions they held, and every grant and scope they carry",
    ),
    StoreFacts(
        store=Store.AGENTS,
        data_class=DataClass.BUSINESS_RECORD,
        schemas=frozenset({"agent"}),
        buckets=frozenset(),
        holds="the agents they own, the skills and templates they wrote, and the leash history",
    ),
    StoreFacts(
        store=Store.OPERATIONS,
        data_class=DataClass.BUSINESS_RECORD,
        schemas=frozenset({"ops"}),
        buckets=frozenset(),
        holds="work scheduled to run under their name, and their share of a budget",
    ),
    StoreFacts(
        store=Store.CONVERSATION,
        data_class=DataClass.BUSINESS_RECORD,
        schemas=frozenset({"chat"}),
        buckets=frozenset(),
        holds="the conversations they took part in and the messages in them",
    ),
    StoreFacts(
        store=Store.PROJECTION,
        data_class=DataClass.BUSINESS_RECORD,
        schemas=frozenset({"proj", "er"}),
        buckets=frozenset(),
        holds="projected pointers at records in source systems, and names resolved to them",
    ),
    StoreFacts(
        store=Store.KNOWLEDGE,
        data_class=DataClass.LEARNED,
        schemas=frozenset({"know"}),
        buckets=frozenset(),
        holds="knowledge items they wrote or own, and the chunks and embeddings built from them",
    ),
    StoreFacts(
        store=Store.MEMORY,
        data_class=DataClass.LEARNED,
        schemas=frozenset({"mem"}),
        buckets=frozenset(),
        holds="what the system learnt from them and recalls on later questions",
    ),
    StoreFacts(
        store=Store.LEDGER,
        data_class=DataClass.METADATA_LEDGER,
        schemas=frozenset({"obs"}),
        buckets=frozenset(),
        holds="one row per request they made: when, through what, how long, and no content",
    ),
    StoreFacts(
        store=Store.TRACE,
        data_class=DataClass.TRACE,
        schemas=frozenset({"obs"}),
        buckets=frozenset(),
        holds="the shape of each of their runs: the model calls, tool calls and retrievals",
    ),
    StoreFacts(
        store=Store.PAYLOAD,
        data_class=DataClass.PAYLOAD,
        schemas=frozenset({"obs"}),
        buckets=frozenset(),
        holds="what their questions said and what the answers said, in the clear",
    ),
    StoreFacts(
        store=Store.RECORDING,
        data_class=DataClass.RECORDING,
        schemas=frozenset(),
        buckets=frozenset({"recordings"}),
        holds="video and DOM capture of automated browser runs made on their behalf",
    ),
    StoreFacts(
        store=Store.ATTACHMENT,
        data_class=DataClass.BUSINESS_RECORD,
        schemas=frozenset(),
        buckets=frozenset({"assets"}),
        holds="files they uploaded as they arrived, and files an agent produced for them",
    ),
    StoreFacts(
        store=Store.EXPORT,
        data_class=DataClass.EXPORT,
        schemas=frozenset(),
        buckets=frozenset({"exports"}),
        holds="exports already produced that included them, with permissions no longer attached",
    ),
    StoreFacts(
        store=Store.BACKUP,
        data_class=DataClass.BACKUP,
        schemas=frozenset(),
        buckets=frozenset({"backups"}),
        holds="database dumps taken before now, holding whatever the database held then",
    ),
    StoreFacts(
        store=Store.CACHE,
        data_class=DataClass.DERIVED,
        schemas=frozenset(),
        buckets=frozenset(),
        holds="answers computed for them and kept so the same question is not asked twice",
    ),
    StoreFacts(
        store=Store.INDEX,
        data_class=DataClass.DERIVED,
        schemas=frozenset(),
        buckets=frozenset(),
        holds="retrieval index entries pointing at knowledge and records about them",
    ),
    StoreFacts(
        store=Store.AUDIT,
        data_class=DataClass.AUDIT,
        schemas=frozenset({"obs"}),
        buckets=frozenset(),
        holds="the hash-chained record of what was granted, refused and changed about them",
    ),
)


def facts_for(store: Store) -> StoreFacts:
    """What is known about one store. `assert_never`, for the usual reason.

    A member added to `Store` with no entry in `STORES` is a store that a subject access
    request would iterate over and find nothing to say about, which is exactly the silent
    omission this whole arrangement exists to prevent. Here it is a raise, and in
    `store_gaps` it is a finding, and in the type checker it is an error.
    """
    for entry in STORES:
        if entry.store is store:
            return entry
    match store:  # pragma: no cover - unreachable while STORES is complete
        case (
            Store.ROWS
            | Store.AGENTS
            | Store.OPERATIONS
            | Store.CONVERSATION
            | Store.PROJECTION
            | Store.KNOWLEDGE
            | Store.MEMORY
            | Store.LEDGER
            | Store.TRACE
            | Store.PAYLOAD
            | Store.RECORDING
            | Store.ATTACHMENT
            | Store.EXPORT
            | Store.BACKUP
            | Store.CACHE
            | Store.INDEX
            | Store.AUDIT
        ):
            msg = f"store {store.value} has no declaration"
            raise RetentionError(msg)
        case _:
            assert_never(store)


def data_class_of(store: Store) -> DataClass:
    return facts_for(store).data_class


def horizon_of(store: Store) -> Horizon:
    """The window governing one store, through its class. Never through the store itself."""
    return horizon_for(data_class_of(store))


def stores_in_class(data_class: DataClass) -> tuple[Store, ...]:
    return tuple(entry.store for entry in STORES if entry.data_class is data_class)


def store_gaps(facts: Sequence[StoreFacts] | None = None) -> tuple[str, ...]:
    """Every way the store list has stopped describing the system.

    **This is the check that makes "we looked everywhere" a claim rather than a habit.**
    Four rules. Every member of `Store` is declared. Every schema in `brain.db.SCHEMAS` is
    claimed by at least one store and every bucket in `brain.ops.storage.BUCKETS` by exactly
    one, so adding a schema or a bucket anywhere in the system fails here until somebody
    decides which store it is part of. And nothing here claims a schema or bucket that does
    not exist, which is what catches a rename: a store still pointing at a schema that has
    gone would otherwise look like a store that is being swept.

    The two rules differ on purpose, and `obs` is why. A schema holds many tables with many
    lifetimes: the metadata ledger, the traces, the payloads and the audit chain are all in
    `obs` and are kept for five years, thirty days, thirty days and forever respectively, so
    requiring one store per schema would force those four into one horizon and the longest
    would win. A bucket is the opposite: a bucket has exactly one lifecycle rule, so two
    stores over one bucket is two horizons over one rule, and the shorter one wins by
    accident rather than by anybody choosing it.
    """
    declared = STORES if facts is None else tuple(facts)
    by_store = {entry.store: entry for entry in declared}
    findings: list[str] = []
    for store in Store:
        if store not in by_store:
            findings.append(f"{store.value}: no declaration, so nothing would look in it")
    if findings:
        return tuple(findings)

    for entry in declared:
        for schema in sorted(entry.schemas - set(SCHEMAS)):
            findings.append(
                f"{entry.store.value} claims schema {schema!r}, which brain.db.SCHEMAS does "
                "not declare; a sweep pointed at a schema that is not there reports nothing "
                "and reads as clean"
            )
        for name in sorted(entry.buckets - {b.name for b in BUCKETS}):
            findings.append(
                f"{entry.store.value} claims bucket {name!r}, which brain.ops.storage does "
                "not declare"
            )

    claimed_schemas = {schema for entry in declared for schema in entry.schemas}
    for schema in sorted(set(SCHEMAS) - claimed_schemas):
        findings.append(
            f"schema {schema!r} is declared in brain.db.SCHEMAS and no store claims it, so "
            "a subject access request would not look in it and nothing would say so"
        )
    claimed_buckets = {name for entry in declared for name in entry.buckets}
    for name in sorted({b.name for b in BUCKETS} - claimed_buckets):
        findings.append(
            f"bucket {name!r} is declared in brain.ops.storage and no store claims it, so a "
            "deletion would not reach it and nothing would say so"
        )
    for name in sorted(claimed_buckets):
        owners = sorted(e.store.value for e in declared if name in e.buckets)
        if len(owners) > 1:
            findings.append(
                f"bucket {name!r} is claimed by {owners}; two stores over one bucket is two "
                "horizons over one lifecycle rule and the shorter wins by accident"
            )
    return tuple(findings)


# ---------------------------------------------------------------- automated enforcement
class StoreSweeper(Protocol):
    """What an executor must offer for a retention run to happen at all.

    A protocol and not an implementation. **The executor half of M25.1.5 is not built**, and
    saying so here is more useful than leaving it to be inferred from the absence of a file:
    everything in this module decides and reports, and something with a database connection
    and an S3 client has to do the removing. That split is the one
    `brain.ops.limits` and `brain.ops.limit_store` make, and the reason is the same: the
    interesting case in a retention run is the store that could not be reached, and a module
    that opened its own connections could not be tested for it.
    """

    def census(self, store: Store, now: datetime) -> StoreCensus:
        """How much in this store is past its horizon, and how much of that is held."""
        ...

    def expire(self, store: Store, now: datetime) -> int:
        """Remove what is past its horizon and not held. Returns how many."""
        ...


@dataclass(frozen=True)
class StoreCensus:
    """What one store reported when asked. Counts, never subjects.

    `beyond_horizon` means whatever the store's lifetime makes it mean, and the three
    readings are all the same question asked of a different clock: for a fixed window it is
    items written longer ago than the window; for a record-lifetime store it is rows whose
    subject record is gone; for a derived store it is copies whose source is gone. Each is
    "things that should not still be here", which is the only number an enforcement run
    needs.
    """

    store: Store
    beyond_horizon: int
    #: How many of those are under an active legal hold and were therefore not removed.
    held: int = 0
    #: Age of the oldest item, where the store can say. Reported so a window that is not
    #: being applied at all is visible as an age rather than only as a count.
    oldest_days: int | None = None

    def __post_init__(self) -> None:
        if self.beyond_horizon < 0 or self.held < 0:
            msg = f"{self.store.value} reported a negative count"
            raise RetentionError(msg)
        if self.held > self.beyond_horizon:
            msg = (
                f"{self.store.value} reports {self.held} held out of {self.beyond_horizon} "
                "past their horizon, which is more held than there are"
            )
            raise RetentionError(msg)
        if self.oldest_days is not None and self.oldest_days < 0:
            msg = f"{self.store.value} reports an oldest item with a negative age"
            raise RetentionError(msg)

    @property
    def due(self) -> int:
        """How many a sweep may actually remove. Held items are not due; they are held."""
        return self.beyond_horizon - self.held


@dataclass(frozen=True)
class SweptStore:
    """One line of the enforcement report.

    `reached` is the field the whole report is arranged around. A store that returned no
    census is not a store with nothing in it, and the two must not render the same way; see
    `A_SWEEP_THAT_SKIPS_A_STORE_KEEPS_IT_FOREVER`.
    """

    store: Store
    data_class: DataClass
    lifetime: Lifetime
    days: int | None
    reached: bool
    beyond_horizon: int
    held: int
    oldest_days: int | None

    @property
    def due(self) -> int:
        return self.beyond_horizon - self.held

    def line(self) -> str:
        """One line, carrying no identifier. See `A_RETENTION_REPORT_COUNTS_AND_NEVER_NAMES`."""
        if not self.reached:
            return f"{self.store.value}: not reached, so nothing in it was considered"
        window = f"{self.days}d" if self.days is not None else self.lifetime.value
        age = "" if self.oldest_days is None else f", oldest {self.oldest_days}d"
        return (
            f"{self.store.value} ({self.data_class.value}, {window}): "
            f"{self.due} due, {self.held} held{age}"
        )


@dataclass(frozen=True)
class RetentionReport:
    """What an enforcement run produced, and whether it may be believed.

    There is no subject anywhere on this model and no field that could hold one. The report
    goes to a dashboard and an alert, and both are read by people who run the estate rather
    than by people entitled to what is in it.
    """

    at: datetime
    swept: tuple[SweptStore, ...]
    findings: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """Whether every store was reached. Not whether everything was clean."""
        return all(one.reached for one in self.swept)

    @property
    def due(self) -> int:
        """How many items across the estate a sweep may remove."""
        return sum(one.due for one in self.swept if one.reached)

    def unreached(self) -> tuple[Store, ...]:
        return tuple(one.store for one in self.swept if not one.reached)

    def lines(self) -> tuple[str, ...]:
        """The report, one line per store, in a fixed order, followed by the findings."""
        return tuple(one.line() for one in self.swept) + self.findings


def enforcement_report(*, now: datetime, census: Sequence[StoreCensus]) -> RetentionReport:
    """Turn what the executor saw into a report that cannot omit a store.

    Built by iterating `Store` rather than by iterating the census, which is the whole
    difference between this and the report anybody writes first. Iterating the census
    produces a document listing what was looked at; iterating the enum produces a document
    listing what exists, with the ones that were not looked at named. Only the second can
    say the run was incomplete.

    Ordering is the enum's declaration order, so two runs of an unchanged estate produce the
    same text and a diff between two mornings is readable.
    """
    seen: dict[Store, StoreCensus] = {}
    findings: list[str] = []
    for entry in census:
        if entry.store in seen:
            findings.append(
                f"{entry.store.value}: reported twice in one run, so the counts cannot be "
                "added and neither reading can be trusted"
            )
            continue
        seen[entry.store] = entry

    swept: list[SweptStore] = []
    for store in Store:
        horizon = horizon_of(store)
        found = seen.get(store)
        swept.append(
            SweptStore(
                store=store,
                data_class=horizon.data_class,
                lifetime=horizon.lifetime,
                days=horizon.days,
                reached=found is not None,
                beyond_horizon=0 if found is None else found.beyond_horizon,
                held=0 if found is None else found.held,
                oldest_days=None if found is None else found.oldest_days,
            )
        )
    findings.extend(enforcement_gaps(census))
    return RetentionReport(at=now, swept=tuple(swept), findings=tuple(findings))


def enforcement_gaps(census: Sequence[StoreCensus]) -> tuple[str, ...]:
    """Everything wrong with a run, beyond the counts themselves.

    Three findings, and the first is the one that matters. A store with no census entry is
    reported by name, because the alternative is a run that quietly covers every store but
    one and reads exactly like a run that covered all of them.

    The third is the one that catches a sweep believing something it should not: a store
    whose class never expires cannot have anything past its horizon, so a census claiming it
    does is a sweep about to prune the audit chain.
    """
    findings: list[str] = []
    reported = {entry.store for entry in census}
    for store in Store:
        if store not in reported:
            findings.append(
                f"{store.value}: no census, so nothing looked in it and the run cannot be "
                "called clean"
            )
    for entry in census:
        horizon = horizon_of(entry.store)
        if horizon.lifetime is Lifetime.NEVER_EXPIRES and entry.beyond_horizon > 0:
            findings.append(
                f"{entry.store.value}: {entry.beyond_horizon} item(s) reported past a "
                f"horizon that does not exist, because {horizon.data_class.value} never "
                "expires; a sweep acting on this would cut a hash chain"
            )
        if entry.held > 0 and entry.due == 0:
            findings.append(
                f"{entry.store.value}: everything past its horizon is under legal hold, so "
                "the window is not being applied here and will not be until the hold lifts"
            )
    return tuple(findings)


# ------------------------------------------------------- the absence of an override
#: Argument names that would let a caller postpone or extend a window from a call site.
#: Scanned for rather than trusted, because the way this rule dies is one helpful keyword
#: argument added during an incident and never taken out again.
_OVERRIDE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "keep_until",
        "retain_until",
        "expires_at_override",
        "override",
        "exempt",
        "extend",
        "extra_days",
        "retention_days",
        "grace",
        "forever",
    }
)


#: The functions a per-row override would have to arrive through. Named as a constant so
#: the scan below has something to be run against other than itself.
POLICY_SURFACE: Final[tuple[Callable[..., object], ...]] = (
    horizon_for,
    horizon_of,
    expires_at,
    is_expired,
    enforcement_report,
    enforcement_gaps,
)

#: The models a per-row window could arrive on instead.
POLICY_MODELS: Final[tuple[type, ...]] = (
    Horizon,
    StoreFacts,
    StoreCensus,
    SweptStore,
    RetentionReport,
)


def retention_policy_gaps(
    functions: Sequence[Callable[..., object]] | None = None,
    models: Sequence[type] | None = None,
) -> tuple[str, ...]:
    """Everything about this module that would let one row outlive its class.

    The signature scan is the same mechanism `brain.memory.correction.correction_gaps` uses
    against a postponable demotion, and it is here for the same reason: a rule that lives
    only in a docstring holds until somebody has a bad afternoon. `horizon_for` taking
    exactly one parameter is the property; anything else it grew would be the way out.

    The model scan is the other half. A `keep_until` column on `StoreCensus` would be a
    per-row window arriving through the report rather than through the policy, which is the
    same hole with a longer path to it.

    Both surfaces are parameters defaulting to this module's own, for the reason
    `brain.ops.tracing.retention_gaps` takes one: a scan that can only ever be pointed at
    code known to be clean is a scan nobody has seen produce a finding, and nobody knows
    whether it can.
    """
    gaps: list[str] = []

    taken = set(inspect.signature(horizon_for).parameters)
    if taken != {"data_class"}:
        gaps.append(
            f"horizon_for takes {sorted(taken)}; the class is the only input to a horizon "
            "and anything else is a way for one row to be kept longer than its kind"
        )

    checked = POLICY_SURFACE if functions is None else tuple(functions)
    for function in checked:
        names = set(inspect.signature(function).parameters)
        for forbidden in sorted(names & _OVERRIDE_NAMES):
            gaps.append(
                f"{function.__name__} takes a {forbidden}, so a caller can keep one thing "
                "past the window its class declares and nothing in the policy records that"
            )

    for model in POLICY_MODELS if models is None else tuple(models):
        names = {f.name for f in fields(model)}
        for forbidden in sorted(names & _OVERRIDE_NAMES):
            gaps.append(
                f"{model.__name__} carries {forbidden}, which is a per-item window arriving "
                "through the report rather than through the policy"
            )
        for forbidden in sorted(names & {"subject", "subject_id", "principal_id", "subjects"}):
            gaps.append(
                f"{model.__name__} carries {forbidden}, so a retention report names who the "
                "rows are about; see A_RETENTION_REPORT_COUNTS_AND_NEVER_NAMES"
            )
    return tuple(gaps)
