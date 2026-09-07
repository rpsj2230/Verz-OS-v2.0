"""What the console is allowed to be, which is a caller like any other and never a back door.

A reporting screen is the place a permission model gets quietly undone, and it happens for a
good reason every time: a report is aggregate, aggregates feel harmless, and the query that
produces one is faster written straight against the database than assembled through a tool
whose projection was compiled for one person. That query is a second data path with no
projection, no redactor and no audit row, and it is reached from a screen whose whole purpose
is to show a lot at once.

So the rule here is that the console holds nothing of its own. It reads what a tool returns,
at the reach the caller already had, tagged so the redactor can walk it, and it is the same
machinery an agent uses with a different renderer on the end.

**Three planes, and the ordering is the whole model** (M27.5.4). Knowing a thing exists,
knowing how it is configured, and reading what is inside it are three different disclosures
and they are routinely collapsed into one. An auditor needs the first two and must never have
the third; a connector administrator needs to install and bind and must never read a record;
a member reads their own content and has no business knowing what exists elsewhere.

The planes are ordered because each one contains the last: you cannot describe a thing's
configuration without disclosing that it exists, and you cannot show its content without
disclosing both. `Plane` is an `IntEnum` for that reason, and `admits` compares them, so a
grant of `CONFIGURATION` never confers `CONTENT` and a check written as `>=` cannot be
inverted by accident. What it deliberately does not do is let one capability cover two planes:
`plane_capability` gives each its own, so reaching content is a grant somebody made rather
than a consequence of being trusted with settings.

**A console read is a tool call and there is no other kind** (M27.5.1). `ConsoleRead` names a
tool and refuses to exist without a required capability, so a screen cannot be wired to
something the registry does not hold and cannot be wired to a tool that asks for nothing. The
rejected alternative was a reporting service with its own connection and a list of allowed
queries, which is faster and is the second data path this module exists to refuse.

**Every row is entity-tagged, because the redactor walks tags** (M27.5.2).
`brain.core.redaction` finds records by their `@entity` and `@id` keys; a report row without
them is a row the walker does not recognise, so it passes through untouched. Untouched is the
failure: it means a report shows a column the same caller would have been refused on the
record screen. `tagged` refuses an untagged row at the point it is built rather than leaving
it to be noticed by its absence from a redaction trace nobody reads.

**A report audience is an intersection and never a union** (M27.5.3). This is the invariant
in the surface where it is hardest to keep, because a report titled "Maintenance" reads as
though it should show the whole department, and the code that would do that is
`caller | department` rather than `caller & department`. `audience` calls
`EntitlementSet.intersect`, which is one of exactly two implementations in this repository and
a third is forbidden. There is no parameter here that could widen a reach and
`console_gaps` fails if one appears.

**A self-grant is a grant whose actor is its subject** (M27.5.5), and it is detected from the
entry rather than declared by whoever wrote it. A separate `AuditAction` member was the
obvious design and it is the wrong one: a member is a thing the next person to write a grant
path forgets to use, and the one grant that must never be missed is the one somebody made to
themselves. `AuditAction` is closed and pinned by an invariant test for good reasons; this
needs no member in it.

Loud means two things and both are enforced. The notice cannot be suppressed, because there is
no flag on it that could be, and it goes to a steward who is not the actor, because a
notification addressed to the person who acted is a log line with a stamp on it.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders anything. `now`
is a parameter and the rows are handed in, for the reason `brain.ops.limits` gives about
policy that owns a client being untestable at the boundary that matters.

Task ids: M27.5.1, M27.5.2, M27.5.3, M27.5.4, M27.5.5
"""

from __future__ import annotations

import enum
import inspect
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Any, Final

from brain.audit.ledger import AuditAction, AuditEntry
from brain.core.entitlement import Capability, EntitlementSet

#: Why a console screen may not have a data path of its own.
A_REPORT_QUERY_IS_A_SECOND_DATA_PATH_WITH_NO_REDACTOR: Final = (
    "A report is aggregate, aggregates feel harmless, and the query that produces one is "
    "faster written straight against the database than assembled through a tool whose "
    "projection was compiled for one caller. That query has no projection, no redactor and "
    "no audit row, and it is reached from the one screen built to show a lot at once. The "
    "console therefore holds nothing of its own: every read is a tool call with a required "
    "capability, which is the same machinery an agent uses with a different renderer on it."
)

#: Why an untagged row is worse than a missing one.
AN_UNTAGGED_ROW_IS_A_ROW_THE_REDACTOR_WALKS_PAST: Final = (
    "brain.core.redaction finds records by their @entity and @id keys. A report row without "
    "them is not refused, it is not recognised, so the walker leaves it alone and every "
    "column in it reaches the screen. The failure is a report showing a figure the same "
    "caller would have been refused on the record it came from, with nothing in the "
    "redaction trace to say so, because no redaction was attempted."
)

#: Why a report is an intersection.
A_REPORT_TITLED_FOR_A_DEPARTMENT_IS_STILL_READ_BY_ONE_PERSON: Final = (
    "A screen headed Maintenance reads as though it should show the whole department, and "
    "the line that would do that is caller | department rather than caller & department. "
    "The union is one character away and it hands a department's reach to whoever opened "
    "the page. The audience is E(caller) intersect E(report), computed by the same "
    "intersect the gate uses, and nothing here takes a parameter that could widen it."
)

#: Why the three planes are separate grants rather than one trust level.
KNOWING_A_THING_EXISTS_IS_A_DISCLOSURE_OF_ITS_OWN: Final = (
    "Existence, configuration and content are three different disclosures and are routinely "
    "collapsed into one called access. An auditor needs the first two and must never have "
    "the third; a connector administrator installs and binds and must never read a record. "
    "Each plane has its own capability, so reaching content is a grant somebody made rather "
    "than a consequence of being trusted with settings."
)

#: Why a self-grant is recognised rather than declared.
THE_GRANT_THAT_MUST_NOT_BE_MISSED_IS_THE_ONE_NOBODY_DECLARES: Final = (
    "A separate audit action for a self-grant is a member the next person to write a grant "
    "path forgets to use, and the one grant that must never be missed is the one somebody "
    "made to themselves. A self-grant is a GRANT whose subject names its own actor, which "
    "is a fact about the entry and needs nobody to remember anything. AuditAction stays "
    "closed, which is what its own invariant test is for."
)

#: Why the notice cannot be sent to the person it is about.
A_NOTICE_ADDRESSED_TO_THE_ACTOR_IS_A_LOG_LINE_WITH_A_STAMP: Final = (
    "Loud means somebody else finds out. A notification whose recipient is the principal who "
    "performed the act tells nobody anything, and it passes every test that checks a "
    "notification was produced. The steward is refused if they are the actor, and there is "
    "no field on the notice that could suppress it."
)

#: The prefix `brain.audit.record.subject` puts on a principal.
PRINCIPAL_SUBJECT: Final = "principal:"

#: The namespace the three plane capabilities live in.
#:
#: Held as a constant because two things read it: `plane_capability`, which builds them,
#: and `ConsoleRead`, which refuses one as a tool's requirement. A second spelling would
#: make the refusal stop firing with nothing failing, because the answer would be False.
CONSOLE_CAPABILITY_PREFIX: Final = "read:console."


class Plane(enum.IntEnum):
    """What a reader may see of a thing. Ordered, because each plane contains the last.

    `IntEnum` rather than `StrEnum`, and it is the one place in this package where the
    ordering is load-bearing: `admits` is a comparison, so a check cannot be written as an
    equality by somebody who then wonders why a content grant does not show a listing.

    Three members and deliberately no fourth. A middle plane for "summary" or "aggregate" is
    the one every reporting system grows, and it is where a figure derived from content ends
    up being classified as configuration.
    """

    #: That the thing is there. A name in a list, a count of nothing.
    EXISTENCE = 1
    #: How it is set up. A leash, a schedule, a ceiling, a binding.
    CONFIGURATION = 2
    #: What is inside it. Records, documents, answers, the values themselves.
    CONTENT = 3


def plane_capability(plane: Plane) -> Capability:
    """The capability a reader needs for one plane.

    One per plane rather than one that covers several, which is
    `KNOWING_A_THING_EXISTS_IS_A_DISCLOSURE_OF_ITS_OWN` made into grants. A single
    `read:console` covering all three would make an auditor's role indistinguishable from a
    super administrator's at the point it matters.
    """
    return Capability(value=f"{CONSOLE_CAPABILITY_PREFIX}{plane.name.lower()}")


def admits(held: Plane, wanted: Plane) -> bool:
    """Whether a reader at `held` may see something needing `wanted`.

    A comparison rather than an equality, because the planes nest: a reader who may see
    content may certainly see that the thing exists, and a screen that refused them the
    listing would be refusing a disclosure they already have.
    """
    return held >= wanted


def planes_reachable(entitlement: EntitlementSet, now: Any = None) -> tuple[Plane, ...]:
    """Every plane this caller holds a capability for, widest last.

    Derived from the grants rather than from a role, because a role is a bundle somebody
    edits and a grant is the thing the gate actually checks. A caller holding content and not
    existence is a configuration error rather than a state to honour, and it is reported by
    `console_gaps` rather than quietly repaired here: repairing it would mean this module
    deciding somebody reaches more than their grants say.
    """
    return tuple(
        plane for plane in Plane if entitlement.scope_for(plane_capability(plane), now) is not None
    )


@dataclass(frozen=True)
class ConsoleRead:
    """One screen's read, which is a tool call and cannot be anything else.

    Names the tool, the capability that tool requires, and the plane the screen is showing.
    There is no field for a query, a table, a statement or a connection, which is
    `A_REPORT_QUERY_IS_A_SECOND_DATA_PATH_WITH_NO_REDACTOR` expressed as a shape rather than
    as a rule somebody remembers.
    """

    #: The screen this read belongs to, for the audit row and for nothing else.
    screen: str
    #: The registered tool that answers it.
    tool: str
    #: What that tool requires. Never empty: see `__post_init__`.
    requires: Capability
    #: What the screen shows of the result.
    plane: Plane

    def __post_init__(self) -> None:
        if not self.screen or not self.tool:
            msg = "a console read with no screen or no tool names nothing anybody can audit"
            raise ValueError(msg)
        if self.requires.value.startswith(CONSOLE_CAPABILITY_PREFIX):
            msg = (
                f"{self.screen} requires {self.requires.value}, which is a plane capability "
                "rather than a grant over what it reads, so the console grant would be doing "
                "the work the tool's own grant should and anybody trusted with the console "
                "would reach it"
            )
            raise ValueError(msg)

        # There is no check here for an empty capability, and that is deliberate rather than
        # an omission. `Capability` refuses a value under three characters, so an empty one
        # cannot reach this constructor, and a second guard for it would be a branch no test
        # could exercise. It is the same thing `brain.connectors.manifest.ProjectedEntity`
        # records having removed: two enforcement points that are really one.


def permitted(read: ConsoleRead, entitlement: EntitlementSet, now: Any = None) -> bool:
    """Whether this caller may make this read, on both counts.

    Both, and the order does not matter because they are conjunctive: the tool's own
    capability, which is what an agent making the same call would need, and the plane's,
    which is what the console adds. A screen showing configuration of something the caller
    may only know exists is refused by the second even when the first passes.
    """
    if entitlement.scope_for(read.requires, now) is None:
        return False
    return any(admits(held, read.plane) for held in planes_reachable(entitlement, now))


def audience(caller: EntitlementSet, report: EntitlementSet) -> EntitlementSet:
    """The reach one person reads one report at: `E(caller) intersect E(report)`.

    The intersection, by the same `EntitlementSet.intersect` the gate uses. There are exactly
    two implementations of that in this repository and a third is forbidden, so this calls
    one rather than comparing grants itself.

    See `A_REPORT_TITLED_FOR_A_DEPARTMENT_IS_STILL_READ_BY_ONE_PERSON` for why the union is
    the mistake worth naming: it is one character away and it reads like the feature.
    """
    return caller.intersect(report)


def tagged(entity: str, record_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
    """One report row, in the shape the redactor recognises.

    The two reserved keys go on first and the values follow, so a row cannot be built without
    them. `brain.core.redaction` looks for exactly these; `brain.gate.compose` skips them when
    deriving citations, because "client 447: id" says nothing about the record.

    Refuses a values mapping that carries either reserved key, because a value called `@id`
    would silently replace the tag and produce a row the walker recognises and mis-identifies,
    which is worse than one it walks past.
    """
    if not entity or not record_id:
        msg = "a report row with no entity or no id cannot be redacted or cited"
        raise ValueError(msg)
    for reserved in ("@entity", "@id"):
        if reserved in values:
            msg = (
                f"a report row carries its own {reserved}, which would replace the tag and "
                "make the row claim to be a record it is not"
            )
            raise ValueError(msg)
    return {"@entity": entity, "@id": record_id, **values}


def untagged_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[int, ...]:
    """The positions of rows the redactor would walk past, for a diagnostic.

    Positions rather than the rows themselves, because a diagnostic that returned the
    offending rows would be a second copy of exactly the data that has not been redacted.
    """
    return tuple(
        index for index, row in enumerate(rows) if "@entity" not in row or "@id" not in row
    )


@dataclass(frozen=True)
class SelfGrant:
    """A grant somebody made to themselves, recognised from the ledger entry.

    Carries the entry's own identifiers and no capability value. What was granted is in the
    entry, under the ledger's own redaction rules; copying it here would put a capability
    into a notification that travels further than the ledger does.
    """

    #: The principal who both made and received the grant.
    principal_id: str
    #: The ledger entry this was recognised from, quotable and carrying no authority.
    entry_hash: str
    at: Any

    def __post_init__(self) -> None:
        if not self.principal_id or not self.entry_hash:
            msg = "a self-grant naming no principal or no entry cannot be followed up"
            raise ValueError(msg)


def is_self_grant(entry: AuditEntry) -> bool:
    """Whether one ledger entry is somebody granting themselves something.

    A `GRANT` whose subject names its own actor. Read off the entry rather than declared by
    the writer: see `THE_GRANT_THAT_MUST_NOT_BE_MISSED_IS_THE_ONE_NOBODY_DECLARES`.

    The subject grammar is `<kind>:<id>` from `brain.audit.record.subject`, and only the
    principal kind can name an actor, so a grant of something to an agent or an artifact is
    not a self-grant however it is worded.
    """
    if entry.action is not AuditAction.GRANT:
        return False
    if not entry.subject.startswith(PRINCIPAL_SUBJECT):
        return False
    return entry.subject[len(PRINCIPAL_SUBJECT) :] == entry.actor_id


def self_grants(entries: Iterable[AuditEntry]) -> tuple[SelfGrant, ...]:
    """Every self-grant in a run of ledger entries, oldest first.

    Oldest first because a reviewer works forwards through what happened, and because two
    self-grants in one sitting are a sequence rather than a set.
    """
    found = [one for one in entries if is_self_grant(one)]
    return tuple(
        SelfGrant(
            principal_id=one.actor_id,
            entry_hash=one.entry_hash,
            at=one.at,
        )
        for one in sorted(found, key=lambda one: (one.at, one.entry_hash))
    )


@dataclass(frozen=True)
class StewardNotice:
    """What the steward is told, and there is no way to not send it.

    **No field could suppress this.** No `enabled`, no `severity`, no `quiet`. A notification
    about somebody widening their own reach is the one that gets turned off first when a
    dashboard is noisy, so the type has nowhere to turn it off from.

    Carries no capability value for the same reason `SelfGrant` does not.
    """

    steward_id: str
    grant: SelfGrant

    def __post_init__(self) -> None:
        if not self.steward_id:
            msg = "a steward notice addressed to nobody is not a notice"
            raise ValueError(msg)
        if self.steward_id == self.grant.principal_id:
            msg = (
                "the steward is the principal who made the grant, so this notice tells "
                "nobody anything; loud means somebody else finds out"
            )
            raise ValueError(msg)

    def render(self) -> str:
        """The sentence a steward reads. Names who and when, and never what.

        What was granted is in the ledger under its own redaction rules. A notification
        carrying the capability would put it into whatever channel this is delivered on,
        which is a wider audience than the ledger has.
        """
        return (
            f"{self.grant.principal_id} granted themselves a capability. "
            f"Entry {self.grant.entry_hash[:12]} in the audit ledger has the detail."
        )


def notices_for(entries: Iterable[AuditEntry], *, steward_id: str) -> tuple[StewardNotice, ...]:
    """One notice per self-grant, addressed to the steward.

    Refuses the whole batch if the steward is the actor of any of them, rather than dropping
    that one and delivering the rest. A partial batch is the shape where the interesting
    notice is the one that went missing, and the caller who sees a shorter list than they
    expected has no way to tell which.
    """
    return tuple(StewardNotice(steward_id=steward_id, grant=one) for one in self_grants(entries))


def console_gaps(
    reads: Sequence[ConsoleRead] = (),
    entitlement: EntitlementSet | None = None,
) -> tuple[str, ...]:
    """Everything about a console wiring that would let a screen see more than it should.

    Four checks. The first two are about this module keeping its own shape; the third and
    fourth are about a wiring somebody hands in, which is why they take arguments rather than
    reading a registry: a diagnostic that found its own inputs would be one nobody could
    exercise with a broken wiring, which is the only interesting case.

    There is deliberately no check here for a read whose requirement is a plane capability.
    `ConsoleRead` refuses one at construction, so a diagnostic for it would be reporting a
    state that cannot exist, and the version of this that had one was written before the
    constructor did.
    """
    gaps: list[str] = []

    taken = set(inspect.signature(audience).parameters)
    for forbidden in ("union", "widen", "include", "extra", "also"):
        if forbidden in taken:
            gaps.append(
                f"audience takes {forbidden}, so a report can be computed at more than the "
                "caller's own reach and the screen decides how much more"
            )

    names = {one.name for one in fields(ConsoleRead)}
    for forbidden in ("query", "sql", "statement", "table", "connection", "dsn"):
        if forbidden in names:
            gaps.append(
                f"ConsoleRead carries {forbidden}, so a screen has a data path that is not a "
                "tool call and nothing projects or redacts what comes back"
            )

    for read in reads:
        if read.tool.startswith(("sql", "db", "query", "raw")):
            gaps.append(
                f"{read.screen} is wired to {read.tool}, which is named like a query rather "
                "than like a registered tool, so the row it returns went through no "
                "projection and reaches the redactor untagged"
            )

    if entitlement is not None:
        held = planes_reachable(entitlement)
        if Plane.CONTENT in held and Plane.EXISTENCE not in held:
            gaps.append(
                "this caller reaches content and not existence, which is a grant set nobody "
                "meant to write: the planes nest, so the wider one implies the narrower"
            )

    return tuple(gaps)
