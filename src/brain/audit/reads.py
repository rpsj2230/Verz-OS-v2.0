"""Which reads are written down, who may read that record, and how long it is kept.

Needs Rupash item 45, Option A. On 2026-09-09 he chose to answer "which agents have read my
HR record" for a narrow, high-sensitivity set rather than for everything, and this module is
that set and the three refusals around it.

**The set is his to widen and it starts here.** `WRITTEN_DOWN` holds two entries today,
personnel records and anything carrying a salary, which is the recommendation in the item and
which he did not narrow. It is declared data with an argument per entry rather than a branch,
for two reasons that pull the same way: widening it later is one `LoggedRead(...)` line
somebody can review the argument for, and the whole of what is being recorded about everybody
can be read in one place instead of being distributed over call sites. Option B in that item,
logging every read of every row, was rejected there, and the shape here is what stops it
arriving by accretion: there is no wildcard entry, no "or anything classified restricted",
and **no parameter anywhere by which a call site can widen the set**. `record_read` computes
membership from this table and refuses a read the table does not cover.

**A read log is itself a map of who is interested in whom.** That is the privacy cost item 45
names, and three decisions follow from it rather than from convenience. The set is two entries.
The log answers to its own capability and not to the audit trail's, so the people who can
already read the ledger do not acquire it by default; see
`THE_READ_LOG_ANSWERS_TO_ITS_OWN_NOUN_SO_NO_AUDIT_WILDCARD_REACHES_IT`. And its retention is
shorter than everything else in the ledger, argued below rather than inherited.

**An entry says that a record of a kind was read, by whom, and nothing about what was in it.**
`brain.audit.ledger` already refuses a value in `details`; this module adds the three refusals
that a names-only ledger does not give for free. Membership is decided on what was disclosed
rather than on what the record holds, so a masked salary is not written down as a salary read.
A read that was shown nothing is not a read at all, because writing one down would render a
refusal as a disclosure on the page of the person who was refused. And the entry names the kind
of record and nothing else about it, so every reader admitted to a personnel record leaves the
same row: **listing what one reader was shown, and equally listing which declarations matched,
tells the subject which fields the other reader was refused.** That second version was written
first and a test found it. See `WHAT_WAS_SHOWN_IS_THE_READ_AND_WHAT_THE_RECORD_HOLDS_IS_NOT`,
`A_RECORD_NOBODY_WAS_SHOWN_WAS_NOT_READ` and
`AN_ENTRY_NAMES_THE_RECORD_KIND_AND_NEVER_WHAT_ONE_READER_WAS_SHOWN`.

**What was measured before any of this was written**, because the item's own description is a
day out of date and building on it would have produced a wrong argument. `AuditAction` has
nine members today and not eight: `approval` was added on 2026-09-09. So `record_read` is the
tenth, and `brain.audit.ledger.AuditAction` carries the argument for it. The item also says
the ledger is kept five years; the five years is `brain.ops.retention.METADATA_LEDGER_
RETENTION_DAYS`, which governs the per-request metadata rows, and the hash chain's own class is
`NEVER_EXPIRES`. A read entry written into the chain today is therefore kept for ever, which is
worse than the item assumed and is why the retention paragraph below is the longest one.

Rejected: a subject kind for a personnel record. `SUBJECT_KINDS` is closed because the
client-visible view filters on it, `brain.identity.staff_sync` derives a department head's
grants from it, and widening it to make one action read better is how a closed set stops being
closed, which `brain.tables.audit.GRANT_SUBJECT_KIND` already declines to do for a pack
assignment. The subject of a read entry is `principal:<the person the record is about>`, which
is the index the question is asked by and which `brain.audit.view` already admits a person to
for their own entries. The cost is real and is stated rather than hidden: a personnel record
about somebody who is not a principal in this system has no subject to be filed under, so
`record_read` refuses a blank subject rather than filing under an empty principal.

Rejected: recording the read against the reading agent as the subject. The question is asked
by the person the record is about, not by the agent, and a subject of `agent:<id>` would make
"who read my record" a search of everything that ever happened to every agent. The agent rides
in the details, which is where a name that is not the index belongs;
`brain.audit.record.compose_change` puts a skill or connector reference there for the same
reason.

Scope: domain logic. Nothing here opens a connection, reads a clock or writes an entry.
`brain.audit.record.AuditRecorder.record_read` is the one writer and `brain.audit.view` is the
one reader.

Task ids: M40.4.2.4
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from brain.audit.ledger import AuditAction, AuditEntry
from brain.core.department import SLUG_PATTERN
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.field_policy import NAME_PATTERN

# ------------------------------------------------------------------ written-down reasons
#: Why the set is two entries rather than every record with a permission on it.
A_READ_LOG_IS_A_MAP_OF_WHO_IS_INTERESTED_IN_WHOM: Final = (
    "Needs Rupash item 45 states the cost of Option B plainly: a log of every read becomes "
    "the largest thing in the database and is itself a record of who is interested in whom, "
    "kept for as long as the ledger is. That cost does not disappear for a narrow set, it "
    "becomes proportionate to it, so the set has to stay small on purpose rather than grow "
    "one convenient entry at a time. Two entries is the whole of it, each with its own "
    "argument, and widening it is a decision somebody makes in this file and can be asked "
    "about later rather than a predicate somebody loosens at a call site."
)

#: Why membership is decided on what the reader was shown.
WHAT_WAS_SHOWN_IS_THE_READ_AND_WHAT_THE_RECORD_HOLDS_IS_NOT: Final = (
    "brain.core.redaction returns a record with the fields this caller may not see already "
    "removed, so the record a reader was handed and the record in the source are different "
    "objects. Deciding membership on the source would write down a salary read that never "
    "happened, and the person reading their own log would be told a colleague had seen their "
    "pay when the mask had taken it out. The error runs the other way as well and is worse: "
    "a log that over-reports is a log nobody believes, and the one it is written for is the "
    "person least able to check it."
)

#: Why an entry says only what kind of record was read.
AN_ENTRY_NAMES_THE_RECORD_KIND_AND_NEVER_WHAT_ONE_READER_WAS_SHOWN: Final = (
    "The house rule is that DENIED and ABSENT are indistinguishable and that no count of "
    "hidden items is emitted, including by subtraction. Within one row that is easy here, "
    "because a row carries no numbers at all. Across rows it is not, and this module got it "
    "wrong first: two entries about one person, one listing name and salary and the other "
    "listing name, say that the second reader was refused the salary, which is a fact about "
    "somebody else's reach handed to the person whose record it is. "
    "The first fix was to record the declared reasons that matched rather than the fields, "
    "and test_two_readers_shown_different_fields_leave_identical_entries found that this "
    "leaks in exactly the same shape: personnel,salary against personnel is the same "
    "subtraction with fewer words. Two rules were pulling against each other, because an "
    "entry that does not over-report has to vary with what was shown and an entry that "
    "cannot be compared must not. Only one thing satisfies both, which is that the entry "
    "names the kind of record and nothing else about it. Every reader who is shown enough of "
    "a personnel record to have read it leaves the same row, and a reader shown too little "
    "leaves none at all."
)

#: Why the read log has its own capability noun instead of joining the audit family.
THE_READ_LOG_ANSWERS_TO_ITS_OWN_NOUN_SO_NO_AUDIT_WILDCARD_REACHES_IT: Final = (
    "The obvious wrong answer is that whoever may read the audit trail may read this, and it "
    "is wrong because the rest of the ledger records who authorised what and this records who "
    "looked at whom. They are different disclosures and the second is the one people mind. "
    "The mechanism matters as much as the decision: brain.core.entitlement.Capability.covers "
    "expands a trailing .* over dotted children, so a capability named read:audit.read would "
    "be covered by read:audit.*, and every holder of the audit wildcard would have acquired "
    "the read log on the day it shipped without anybody granting it. read:audit_read is a "
    "different noun, no audit grant covers it, and the grammar admits no verb-level wildcard "
    "that could reach both. A person always sees the entries about themselves, which is what "
    "the feature is for and is the same rule brain.audit.view already applies to a subject "
    "access request."
)

#: Why the read log is kept for less time than anything else in the ledger.
THE_READ_LOG_IS_THE_PART_OF_THE_LEDGER_THAT_SHOULD_EXPIRE_FIRST: Final = (
    "Three numbers were available to inherit and all three are wrong for this. The trace's "
    "thirty days is too short: this log is read after something has happened, a grievance, a "
    "departure, a suspicion, and those surface in months. The metadata ledger's five years is "
    "an argument about statutory accounting records and says nothing about who looked at a "
    "personnel file. The hash chain's own class is NEVER_EXPIRES, which would make a map of "
    "who is interested in whom permanent, and that is the one outcome item 45 says it does "
    "not want. Two years is chosen against what the log is asked for: two full annual review "
    "cycles, so 'who was looking at my file around my last two appraisals' is answerable, and "
    "long enough that a dispute raised about one year and heard in the next is still covered. "
    "The direction of the error is the deciding argument. Every other class in the ledger "
    "gets longer when the right window is unclear, because the risk is that a question cannot "
    "be answered; this one gets shorter, because the risk is the record itself."
)

#: Why a read that was shown nothing is not a read.
A_RECORD_NOBODY_WAS_SHOWN_WAS_NOT_READ: Final = (
    "brain.core.redaction drops a record whose fields this caller may not see, so a read can "
    "end with nothing disclosed at all. Writing that down would put 'somebody read your "
    "personnel record' on the one page where it is least checkable, about somebody who was "
    "refused it, which is a denial rendered as a disclosure and is the exact inversion the "
    "DENIED and ABSENT rule exists to prevent. An entity declaration says every read of this "
    "record type is written down and a read of nothing is not one of them, so the emptiness "
    "is checked once here rather than in each declaration, where a later entry would have to "
    "remember it."
)

#: Why an ordinary read is refused rather than written as an empty entry.
AN_ORDINARY_READ_IS_REFUSED_AND_NEVER_WRITTEN_QUIETLY: Final = (
    "A recorder that returned None for a read the set does not cover would be a general read "
    "log with a filter in front of it, and the filter is what somebody widens. It would also "
    "be indistinguishable at the call site from a recorder that was never wired up, which is "
    "the failure brain.audit.record exists to make hard. So a read outside the set raises, "
    "and the caller asks written_down_because first. That reads as ceremony until you notice "
    "it is the only thing standing between Option A and Option B."
)


# --------------------------------------------------------------------- the declared set
class ReadLogError(Exception):
    """A read was offered to the log that the declared set does not cover, or a declaration
    in that set is not one.

    Outside `brain.core.errors` for the reason `brain.member_activity.MemberError` is: those
    five outcomes describe an answer given to somebody who asked a question, and this is a
    refusal to write a row.
    """


_NAME_RE: Final = re.compile(NAME_PATTERN)
_SLUG_RE: Final = re.compile(SLUG_PATTERN)


@dataclass(frozen=True)
class LoggedRead:
    """One declared reason a read is written down, and the argument for it.

    `because` is required prose and is not decoration. `brain.ops.retention.Horizon` and
    `brain.ops.storage.Bucket` both require one for the same reason and it applies harder
    here: an entry with no argument is one nobody can weigh when the next one is proposed,
    and a set that grows by entries nobody can weigh is Option B arrived at slowly.

    Exactly one of `entity` and `field`, because the two are different claims. An entity
    entry says every read of this record type is written down whatever it contained; a field
    entry says a read of any record is written down when this field was among the fields
    disclosed. A declaration setting both would be two rules sharing one argument, and a
    declaration setting neither would match every read ever made, which is the whole of
    Option B in a row that looks like a typo.
    """

    #: The token the ledger records. Field-name shaped, so it survives `redact_details`
    #: rather than being stored as the marker, which is `revoke`'s argument about a reason
    #: code applied to the one detail this entry carries.
    name: str
    because: str
    #: An entity type every disclosed read of which is written down. Empty for a field entry.
    entity: str = ""
    #: A field name whose disclosure writes down the read, whatever the entity. Empty for an
    #: entity entry.
    field: str = ""

    def __post_init__(self) -> None:
        if bool(self.entity) == bool(self.field):
            raise ReadLogError(
                f"{self.name!r} declares entity={self.entity!r} and field={self.field!r}; "
                "exactly one of them is the claim, and a declaration with neither matches "
                "every read there has ever been"
            )
        for label in ("name", "entity", "field"):
            value = str(getattr(self, label))
            if value and not _NAME_RE.match(value):
                raise ReadLogError(
                    f"{label}={value!r} is not a name; a declaration that is not "
                    "field-name shaped is one brain.audit.ledger stores as the marker, so "
                    "the ledger would record that a read happened and not why"
                )
        if not self.because.strip():
            raise ReadLogError(
                f"{self.name!r} states no reason for being in the set. "
                f"{A_READ_LOG_IS_A_MAP_OF_WHO_IS_INTERESTED_IN_WHOM}"
            )

    def covers(self, entity: str, disclosed: frozenset[str]) -> bool:
        """Whether this declaration writes down a read of `entity` that showed `disclosed`."""
        if self.entity:
            return self.entity == entity
        return self.field in disclosed


#: The whole of what a read gets written down for. Two entries, which is item 45's
#: recommendation and which he did not narrow.
#:
#: **This is the line somebody widens, and it is meant to be reviewable as a line.** A third
#: entry is a `LoggedRead(...)` with its own `because`, and nothing else in the system has to
#: change: `record_read` reads this tuple, the view's rule is per action rather than per
#: reason, and the retention is one number for the whole log.
WRITTEN_DOWN: Final[tuple[LoggedRead, ...]] = (
    LoggedRead(
        name="personnel",
        entity="personnel",
        because=(
            "the case the task actually names, and the one people ask about: a personnel "
            "record is about one person, that person is the one who asks who has been "
            "looking at it, and the set of people who may read it is small enough that the "
            "log stays short. Every field on it is high-sensitivity together, so an entry "
            "that says only that the record was read is still a useful answer, which is what "
            "makes the record type rather than its fields the right unit here"
        ),
    ),
    LoggedRead(
        name="salary",
        field="salary",
        because=(
            "pay travels outside the personnel record: it appears on payroll rows, on offer "
            "and promotion records, and on any budget line written per person, and a rule "
            "written only against the personnel type would miss every one of those while "
            "looking complete. It is declared as a field rather than as a list of the record "
            "types that carry one because that list is the thing nobody keeps up to date, "
            "and a record type added next year with a pay column would otherwise be read "
            "with no entry written. A company whose column is named something else declares "
            "that name here, as one more line with its own argument"
        ),
    ),
)


def written_down_because(
    entity: str,
    disclosed: Iterable[str],
    *,
    declared: Sequence[LoggedRead] = WRITTEN_DOWN,
) -> tuple[str, ...]:
    """The declared reasons this read is written down under, sorted. Empty means it is not.

    Takes `declared` rather than reading the module constant, which is the argument
    `brain.member_activity.member_gaps` makes about itself: a rule that can only ever be
    exercised against the healthy table is a rule whose behaviour on a different table nobody
    has seen, and a test that has to monkeypatch a constant to check widening is a test that
    has stopped testing the function.

    `disclosed` is what the reader was actually shown; see
    `WHAT_WAS_SHOWN_IS_THE_READ_AND_WHAT_THE_RECORD_HOLDS_IS_NOT`.

    **A read that was shown nothing matches nothing, whatever the declarations say.** The
    check is here rather than in `LoggedRead.covers` because an entity declaration would
    otherwise match a record the redactor dropped entirely, and every declaration written
    afterwards would have to remember the same thing. See
    `A_RECORD_NOBODY_WAS_SHOWN_WAS_NOT_READ`.

    Sorted and deduplicated, so two reads that matched the same declarations in a different
    order are the same answer. The result decides whether an entry is written and never what
    it says; see `AN_ENTRY_NAMES_THE_RECORD_KIND_AND_NEVER_WHAT_ONE_READER_WAS_SHOWN`.
    """
    shown = frozenset(disclosed)
    if not shown:
        return ()
    return tuple(sorted({one.name for one in declared if one.covers(entity, shown)}))


def read_details(reasons: Sequence[str], *, entity: str, agent_id: str = "") -> dict[str, object]:
    """The whole of what one read entry says. The kind of record, optionally an agent, and
    nothing else.

    **`reasons` decides and never appears.** It is what `written_down_because` returned, so an
    empty one is a read the declared set does not cover and is refused, per
    `AN_ORDINARY_READ_IS_REFUSED_AND_NEVER_WRITTEN_QUIETLY`; and a name that is not declared
    is refused too, so this cannot be called with an invented reason to force an entry for an
    ordinary read. What goes on the row is the record kind, which is a property of the record
    and not of what one reader was shown, and
    `AN_ENTRY_NAMES_THE_RECORD_KIND_AND_NEVER_WHAT_ONE_READER_WAS_SHOWN` is the whole argument
    for that including the version of this function that got it wrong.

    The entity is checked to be name-shaped rather than trusted, because a value that is not
    is stored by `redact_details` as the marker, and a row reading `record_kind: <redacted>`
    says a record of a kind somebody hid was read.

    The agent is attached only when there is one, and never as an empty string.
    `brain.audit.record._with_names` makes the argument: `redact_details` turns an empty
    value into the marker, and a detail reading `<redacted>` tells a reader that something was
    hidden, where a read performed by a person at a console hid nothing. Its absence is the
    honest way to say a person did this themselves.
    """
    if not reasons:
        raise ReadLogError(
            "a read the declared set does not cover has no entry to write. "
            f"{AN_ORDINARY_READ_IS_REFUSED_AND_NEVER_WRITTEN_QUIETLY}"
        )
    declared = {one.name for one in WRITTEN_DOWN}
    unknown = sorted(set(reasons) - declared)
    if unknown:
        raise ReadLogError(
            f"{unknown} are not declared reasons; the reasons are {sorted(declared)}, and a "
            "reason invented at a call site is an entry for a read nobody declared"
        )
    if not _NAME_RE.match(entity):
        raise ReadLogError(
            f"{entity!r} is not a record kind. A value that is not name-shaped is stored as "
            "the marker, so the row would say a record of a kind somebody hid was read"
        )
    if agent_id and not _SLUG_RE.match(agent_id):
        raise ReadLogError(
            f"{agent_id!r} is not an agent id. A value that is not slug-shaped is stored as "
            "the marker, so the row would read as an agent whose name was hidden rather than "
            "as the read it was"
        )
    details: dict[str, object] = {"record_kind": entity}
    if agent_id:
        details["agent"] = agent_id
    return details


# ------------------------------------------------------------- who may read the read log
#: The noun the read log answers to. Deliberately not a child of `audit`; see
#: `THE_READ_LOG_ANSWERS_TO_ITS_OWN_NOUN_SO_NO_AUDIT_WILDCARD_REACHES_IT`.
READ_LOG_NOUN: Final = "audit_read"

#: The one capability that reaches somebody else's read entries.
READ_LOG_CAPABILITY: Final = Capability(value=f"read:{READ_LOG_NOUN}")


def may_read_a_read_entry(
    entry: AuditEntry,
    *,
    reader: EntitlementSet,
    now: datetime,
    row: dict[str, Any],
) -> bool:
    """Whether this reader may see one read entry. Two ways in, and no third.

    **The entry is about the reader.** Somebody always sees who has read their own record,
    which is the whole of M40.4.2.4 and is the same rule `brain.audit.view` applies to a
    subject access request.

    **A grant of `read:audit_read` whose scope matches.** Not `read:audit.principal`, and not
    `read:audit.*`; see `THE_READ_LOG_ANSWERS_TO_ITS_OWN_NOUN_SO_NO_AUDIT_WILDCARD_REACHES_IT`.
    The scope is evaluated against the same four closed fields every other audit grant is
    evaluated against, so a read-log grant can be narrowed to named subjects or to named
    actors and cannot be narrowed on anything the ledger does not hold.

    `row` is passed rather than built here so that this and `brain.audit.view` evaluate one
    scope row rather than two. A second construction of it is a second answer to what an audit
    grant may be written against, and the wider copy is the one that ships.
    """
    if entry.action is not AuditAction.RECORD_READ:
        raise ReadLogError(
            f"{entry.action.value!r} is not a read entry, and answering for it here would put "
            "a second visibility rule beside brain.audit.view's for the rest of the ledger"
        )
    if entry.subject == f"principal:{reader.principal_id}":
        return True
    scope = reader.scope_for(READ_LOG_CAPABILITY, now)
    if scope is None:
        return False
    return scope.matches(row)


# ------------------------------------------------------------------------ how long it is kept
#: Two years. See `THE_READ_LOG_IS_THE_PART_OF_THE_LEDGER_THAT_SHOULD_EXPIRE_FIRST`.
#:
#: Asserted against `brain.ops.tracing`'s and `brain.ops.retention`'s own numbers rather than
#: against itself, in `tests/unit/test_audit_reads.py`. A test comparing this constant with an
#: import of this constant is green for every value it could hold, which CLAUDE.md records
#: three authors getting wrong in one afternoon.
READ_LOG_RETENTION_DAYS: Final[int] = 730


def read_log_gaps(
    *, chain_expires: bool, read_days: int = READ_LOG_RETENTION_DAYS
) -> tuple[str, ...]:
    """What is decided about this log and not yet enforced. Red today, and meant to be.

    Separate from a deployment check for the reason `brain.member_activity.member_notes` is
    separate from `member_gaps`: a check that is red on the day it lands is a check somebody
    switches off, so the honest thing is a function whose whole job is to say what is still
    owed.

    Takes `chain_expires` rather than reading `brain.ops.retention`, which keeps the audit
    package underneath the operational layer as `brain.audit.record` argues, and which makes
    the finding reachable in both directions: a caller passing True gets no finding, so this
    stops reporting on the day something actually removes an entry.
    """
    findings: list[str] = []
    if not chain_expires:
        findings.append(
            f"a read entry is declared to be kept {read_days} days and nothing removes it: "
            "brain.ops.retention puts the hash chain in a class that never expires and "
            "brain.tables.audit's trigger raises on any removal, for the owning role as much "
            "as for the application, so the declared window is a statement not a control"
        )
        findings.append(
            "pruning cannot express this window in any case: AuditChain.prune_before can only "
            "take a prefix, because removing an entry from the middle leaves the next one "
            "pointing at a digest that is gone, and read entries are interleaved with grants "
            "and revocations that are kept longer. Enforcing it means a table of its own with "
            "its own chain and its own migration, which is a decision rather than an edit"
        )
    return tuple(findings)
