"""How each connector's answer to a read becomes the answer to "did our write land".

`brain.ops.idempotency` says what a read-back settles and says nothing about how one is
read. `Verification` has three values, `FOUND`, `ABSENT` and `INCONCLUSIVE`, and the whole
safety argument of that module rests on the third being kept apart from the second: `ABSENT`
settles an operation as `FAILED`, which is terminal and means "definitely did not happen",
so somebody raises the intent again. An `ABSENT` that was really "could not look" is a
duplicated invoice. This module is where each connector's raw reply is turned into one of
the three, and it is the only place that is decided.

**One verdict, over the platform's outcome vocabulary, and one reading per connector.**
Every connector here already keeps a read's answers apart in its own words: Xero, HubSpot
and Laravel have a four-valued outcome, Freshdesk and both Lark connectors raise a refusal
and an unreachability as two types, and Drive has a third type for a 404. The obvious design
is a table per connector from those words to `Verification`, and it was rejected: seven
tables of one rule are seven places for it to be subtly wrong, and the copy that says a
refusal is an absence is the one nobody reviews. So each connector contributes a `Reading`,
built only from its own classifier, and `verdict` alone decides. See
`A_REFUSAL_IS_NOT_AN_ABSENCE`. Each reading lives in its connector's module, declared on its
`CONNECTOR` as a `ReadBack` (`brain.connectors.declaration`), because a reading is written in
the connector's own reply types and a table here importing every connector was a list a new
connector had to edit.

**Absence needs two facts, not one.** The source answered, and the answer was complete.
An empty first page of a walk that has more pages has not looked everywhere, and a page cut
short by a cap is the same. See `AN_UNFINISHED_LOOK_HAS_NOT_LOOKED`.

**A connector is found, not listed, and every one found is stated.** `connectors` walks
`brain.connectors` and counts as a connector any module that builds a `ConnectorManifest`,
which is a property of the code rather than of a list somebody typed, and
`brain.connectors.declaration.shipped` finds the declarations by a different property, the
`CONNECTOR` each module states. `read_back_gaps` holds the two to each other: it refuses a
connector with no read-back declared, and one that declares a write with no reading. A
connector without a read-back is therefore a named finding or a red test, never a silence.

**What is not built, and why it cannot be yet.** No tool on any connector in this repository
has a side effect. Every `ToolDeclaration` in `brain.connectors` is `SideEffect.NONE`, and
`declares_a_write` finds none, so `brain.ops.idempotency.issuable_tools` is empty for every
connector and nothing here is reached by a request. What exists is the half that can be written
and tested before a write exists: raw reply to `Verification`, driven by the recorded
exchanges. The other half, which request is sent to look, cannot be, for the reason
`THE_QUERY_HALF_IS_OWED_BY_THE_FIRST_WRITE` gives. The test that finds no connector
declaring a write is written to go red on the day one does.

Scope: domain logic. Nothing here opens a connection, reads a clock or holds a credential.

Task ids: M17.3.3
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType, ModuleType
from typing import Final, Protocol, assert_never

import brain.connectors
from brain.connectors.contract import ConnectorContractError
from brain.connectors.manifest import ConnectorManifest, ToolDeclaration
from brain.connectors.throttle import CallOutcome
from brain.connectors.transports import SourceRecord
from brain.core.envelope import TypedResult
from brain.ops.idempotency import Verification

# ------------------------------------------------------------------ written-down reasons
#: Why a refusal, a quota and an outage all read as "could not answer".
A_REFUSAL_IS_NOT_AN_ABSENCE: Final = (
    "A read-back that was refused has not looked. A 401, a 403, a Lark 91403 inside a 200 and "
    "a view the grant no longer covers all say something about our credential and nothing "
    "about whether the write landed, and a 429, a 5xx and a timeout say nothing about either. "
    "Reading any of them as ABSENT settles the operation as FAILED, which is terminal and "
    "invites a second attempt at a side effect that may already exist. So every outcome that "
    "is not an answer is INCONCLUSIVE, the record goes back to UNKNOWN, and it is asked again. "
    "Losing a permission is the case that most wants to read as absent, because an empty "
    "result and a forbidden one look alike to anything that only counts rows."
)

#: Why an answered read that did not reach the end proves nothing absent.
AN_UNFINISHED_LOOK_HAS_NOT_LOOKED: Final = (
    "ABSENT needs the source to have answered and the answer to be complete. An empty page "
    "with has_more set, a Drive listing carrying a nextPageToken and a read cut short by a "
    "row cap have each looked at part of the source. The record may be on the page nobody "
    "asked for, so an empty unfinished read is INCONCLUSIVE and a non-empty one is FOUND "
    "whether or not it finished."
)

#: Why a body in a shape the connector cannot read is not an empty result.
AN_UNREADABLE_ANSWER_IS_NOT_AN_ANSWER: Final = (
    "A body that disagrees with the connector's own specification, a Lark envelope with no "
    "has_more, and a listing whose items are not a list are all refused by the connector as "
    "contract errors. For a read-back each of them is a reply nothing could read, which is "
    "UNAVAILABLE and so INCONCLUSIVE. Letting one read as zero rows is how a proxy's error "
    "page becomes a verified absence."
)

#: What the other half of a read-back is, and why nothing here attempts it.
THE_QUERY_HALF_IS_OWED_BY_THE_FIRST_WRITE: Final = (
    "A read-back is a request and an interpretation. The interpretation is here. The request "
    "is shaped by the write: an invoice created with our key in its reference is looked for "
    "by that reference, a ticket by a tag, a record by a field somebody chose to hold the key. "
    "No connector in this repository issues a write, so there is no write to shape it, and "
    "brain.ops.idempotency.Operation carries the key, the tool and the intent but no natural "
    "identity to search by. A query written here would be a guess at a write nobody has "
    "designed. The first connector to declare a side effect owes it, together with the index "
    "freshness question in A_SEARCH_THAT_LAGS_A_WRITE_MANUFACTURES_AN_ABSENCE."
)

#: The risk carried by every read-back that looks through a search index.
A_SEARCH_THAT_LAGS_A_WRITE_MANUFACTURES_AN_ABSENCE: Final = (
    "A search endpoint answers from an index, and an index can be behind the record it "
    "indexes. A read-back sent moments after a write through such an endpoint can answer "
    "complete and empty about a record that exists, and verdict would call that ABSENT, "
    "because from the reply alone it is. How far behind each vendor's index runs has not been "
    "measured in this repository, so no connector here is recorded as safe or unsafe on it, "
    "and choosing a by-reference read over a search is part of the query half that the first "
    "write owes."
)

#: Why every connector found must appear in the table, even one with nothing to say.
A_CONNECTOR_IS_STATED_AND_NEVER_SKIPPED: Final = (
    "A table that lists the connectors somebody thought of is silent about the one they did "
    "not, and a silent connector reads exactly like one that was considered and needed "
    "nothing. So every module that builds a manifest must have an entry, an entry with no "
    "reading must say so as a finding, and a connector that declares a write must have a "
    "reading. A new connector fails the test by existing, rather than being noticed on the "
    "day an operation against it cannot leave UNKNOWN."
)

# ------------------------------------------------------------------ per-connector findings
#: Stated on an entry with no reading at all. No connector carries it today; the type
#: allows it so that a connector with no way to look is written down rather than left out.
NO_READ_BACK_PATH: Final = (
    "This connector has no read that could answer whether a write landed, so it may only ever "
    "be read-only. brain.ops.idempotency.NO_READ_BACK_MEANS_READ_ONLY is the rule."
)

#: Stated on an entry whose mapping rests on no recorded exchange.
NOTHING_IS_RECORDED: Final = (
    "No exchange with this source is recorded in tests/fixtures/cassettes/. The mapping is "
    "tested against the vendor's documented reply shape, which is what its author believed "
    "the source returns rather than what it was seen to return."
)


# ------------------------------------------------------------------ the reading
class ReadingError(ConnectorContractError):
    """A reading described in a shape that cannot be true of any reply.

    A contract error, like every other refusal in this package: it is a mistake by whoever
    wrote the reading for a connector, and nobody asking a question should see it.
    """


@dataclass(frozen=True)
class Reading:
    """What one read-back reply said, in the three facts `verdict` needs and nothing else.

    The constructor refuses the two combinations that would let a failure be read as an
    answer. A call that did not answer cannot carry matched rows or claim to be complete, and
    a truncated call cannot claim to be complete either.
    """

    outcome: CallOutcome
    #: Records the connector's own projection returned. Counted after the projection, so a
    #: row the connector drops is not counted as found.
    matched: int
    #: Whether the source said there was nothing further to read.
    complete: bool

    def __post_init__(self) -> None:
        if self.matched < 0:
            msg = f"a reading matched {self.matched} records, which no reply can"
            raise ReadingError(msg)
        answered = self.outcome in (CallOutcome.OK, CallOutcome.TRUNCATED)
        if not answered and (self.matched or self.complete):
            msg = (
                f"a {self.outcome} reading claims matched rows or completeness. "
                f"{A_REFUSAL_IS_NOT_AN_ABSENCE}"
            )
            raise ReadingError(msg)
        if self.outcome is CallOutcome.TRUNCATED and self.complete:
            msg = f"a truncated reading claims to be complete. {AN_UNFINISHED_LOOK_HAS_NOT_LOOKED}"
            raise ReadingError(msg)


def verdict(reading: Reading) -> Verification:
    """What a read-back reply settles. The one place in this repository it is decided.

    Exhaustive over `CallOutcome`, and written as arms so that the count of outcomes that can
    produce `ABSENT` is readable at a glance: one arm, and within it one line.
    """
    match reading.outcome:
        case CallOutcome.OK | CallOutcome.TRUNCATED:
            if reading.matched:
                return Verification.FOUND
            if reading.complete:
                return Verification.ABSENT
            return Verification.INCONCLUSIVE
        case CallOutcome.QUOTA | CallOutcome.UNAVAILABLE | CallOutcome.REJECTED:
            return Verification.INCONCLUSIVE
        case unreachable:
            assert_never(unreachable)


# ------------------------------------------------------------- what a connector's reading uses
class ClassifiedReply(Protocol):
    """A reply that already carries its call outcome and its rows: Xero, HubSpot, Laravel.

    Those three connectors' reply constructors are what make this sound. Each refuses rows on
    a failure and refuses a missing result on an answer, so `rows is None` here means the call
    did not answer and nothing else.
    """

    @property
    def call(self) -> CallOutcome: ...

    @property
    def rows(self) -> TypedResult[SourceRecord] | None: ...


def classified_reading(reply: ClassifiedReply) -> Reading:
    """A reading from `xero.interpret`, `hubspot.interpret` or `laravel.interpret`."""
    if reply.rows is None:
        return Reading(outcome=reply.call, matched=0, complete=False)
    return Reading(
        outcome=reply.call, matched=len(reply.rows.records), complete=not reply.rows.truncated
    )


def unreadable() -> Reading:
    """A reply nothing could read. See `AN_UNREADABLE_ANSWER_IS_NOT_AN_ANSWER`."""
    return Reading(outcome=CallOutcome.UNAVAILABLE, matched=0, complete=False)


# ------------------------------------------------------------------ the table
@dataclass(frozen=True)
class ReadBack:
    """One connector's read-back as it stands: how a reply is read, what it rests on, and
    what is not true of it.

    `recorded` names the cassettes the reading is driven by, so a claim that the mapping was
    tested against a real payload is a list a test can check rather than a sentence.
    """

    reading: Callable[..., Reading] | None
    recorded: tuple[str, ...]
    findings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.reading is None and NO_READ_BACK_PATH not in self.findings:
            msg = (
                "an entry with no reading must state it as a finding. "
                f"{A_CONNECTOR_IS_STATED_AND_NEVER_SKIPPED}"
            )
            raise ReadingError(msg)
        if not self.recorded and NOTHING_IS_RECORDED not in self.findings:
            msg = (
                "an entry resting on no recorded exchange must state it, or a mapping written "
                "from documentation reads as one checked against the source"
            )
            raise ReadingError(msg)


# ------------------------------------------------------------------ discovery
def builds_a_manifest(module: ModuleType) -> bool:
    """Whether this module defines a function that returns a `ConnectorManifest`.

    Read from the return annotation of functions defined in the module itself, so a module
    that only imports a factory is not counted twice. Modules here use postponed annotations,
    so the annotation is usually the string, and both spellings are accepted.
    """
    for _, member in inspect.getmembers(module, inspect.isfunction):
        if member.__module__ != module.__name__:
            continue
        returned = inspect.get_annotations(member).get("return")
        if returned is ConnectorManifest or returned == ConnectorManifest.__name__:
            return True
    return False


def _is_none_effect(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "NONE"
        and isinstance(node.value, ast.Name)
        and node.value.id == "SideEffect"
    )


def declares_a_write(source: str) -> bool:
    """Whether any `ToolDeclaration(...)` in this source could declare a side effect.

    Syntactic, so it needs no deployment values to build a manifest with. A call that passes
    `side_effect` as anything but `SideEffect.NONE`, or `verifies_write` as anything but
    `False`, or passes `**` keywords this cannot read, counts as a write. An argument nobody
    can read is not evidence of a read-only tool.
    """
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        if name != TOOL_DECLARATION:
            continue
        for keyword in node.keywords:
            if keyword.arg is None:
                return True
            if keyword.arg == "side_effect" and not _is_none_effect(keyword.value):
                return True
            if keyword.arg == "verifies_write" and not (
                isinstance(keyword.value, ast.Constant) and keyword.value.value is False
            ):
                return True
    return False


#: The class name the scan looks for. Taken from the class rather than typed, so a rename of
#: the declaration is a rename of what is scanned for.
TOOL_DECLARATION: Final = ToolDeclaration.__name__


def connectors(package: ModuleType = brain.connectors) -> Mapping[str, bool]:
    """Every connector module in the package, and whether it declares a write."""
    found: dict[str, bool] = {}
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        if builds_a_manifest(module):
            found[info.name] = declares_a_write(inspect.getsource(module))
    return MappingProxyType(dict(sorted(found.items())))


def read_back_gaps(
    discovered: Mapping[str, bool], table: Mapping[str, ReadBack]
) -> tuple[str, ...]:
    """Every way the declared read-backs and the connectors that exist disagree. Empty when none.

    `table` is `brain.connectors.declaration.read_backs()`, passed in rather than imported: every
    connector imports this module for `Reading`, so this module importing the declarations would
    be a cycle. See `A_CONNECTOR_IS_STATED_AND_NEVER_SKIPPED`.
    """
    gaps: list[str] = []
    for name, writes in discovered.items():
        entry = table.get(name)
        if entry is None:
            gaps.append(
                f"brain.connectors.{name} builds a manifest and has no read-back entry. "
                f"{A_CONNECTOR_IS_STATED_AND_NEVER_SKIPPED}"
            )
        elif writes and entry.reading is None:
            gaps.append(
                f"brain.connectors.{name} declares a write and has no reading, so an operation "
                f"against it could never leave UNKNOWN. {NO_READ_BACK_PATH}"
            )
    gaps.extend(
        f"a read-back is declared for {name!r}, which builds no manifest in this package, so its "
        "entry states a finding about nothing"
        for name in sorted(set(table) - set(discovered))
    )
    return tuple(gaps)
