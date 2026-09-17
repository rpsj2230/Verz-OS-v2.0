"""How each connector's answer to a read becomes the answer to "did our write land".

`brain.ops.idempotency` says what a read-back settles and says nothing about how one is
read. `Verification` has three values, `FOUND`, `ABSENT` and `INCONCLUSIVE`, and the whole
safety argument of that module rests on the third being kept apart from the second: `ABSENT`
settles an operation as `FAILED`, which is terminal and means "definitely did not happen",
so somebody raises the intent again. An `ABSENT` that was really "could not look" is a
duplicated invoice. This module is where each connector's raw reply is turned into one of
the three, and it is the only place that is decided.

**One verdict, over the platform's outcome vocabulary, and seven readings that feed it.**
Every connector here already keeps a read's answers apart in its own words: Xero, HubSpot
and Laravel have a four-valued outcome, Freshdesk and both Lark connectors raise a refusal
and an unreachability as two types, and Drive has a third type for a 404. The obvious design
is a table per connector from those words to `Verification`, and it was rejected: seven
tables of one rule are seven places for it to be subtly wrong, and the copy that says a
refusal is an absence is the one nobody reviews. So each connector contributes a `Reading`,
built only from its own classifier, and `verdict` alone decides. See
`A_REFUSAL_IS_NOT_AN_ABSENCE`.

**Absence needs two facts, not one.** The source answered, and the answer was complete.
An empty first page of a walk that has more pages has not looked everywhere, and a page cut
short by a cap is the same. See `AN_UNFINISHED_LOOK_HAS_NOT_LOOKED`.

**A connector is found, not listed, and every one found is stated.** `connectors` walks
`brain.connectors` and counts as a connector any module that builds a `ConnectorManifest`,
which is a property of the code rather than of a list somebody typed.
`tests/invariants/test_cassettes.py` has the typed list, and the test for this module
requires the two to agree. `read_back_gaps` then refuses a connector with no entry in
`READ_BACKS`, and refuses one that declares a write with no reading. A connector without a
read-back is therefore a named finding in this file or a red test, never a silence.

**What is not built, and why it cannot be yet.** No tool on any connector in this repository
has a side effect. Every `ToolDeclaration` in `brain.connectors` is `SideEffect.NONE`, and
`declares_a_write` finds none, so `brain.ops.idempotency.issuable_tools` is empty for all
seven and nothing here is reached by a request. What exists is the half that can be written
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
from brain.connectors import freshdesk, google_drive, lark_base, lark_wiki
from brain.connectors.contract import ConnectorContractError
from brain.connectors.manifest import ConnectorManifest, ToolDeclaration
from brain.connectors.rest import RestOperation
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
    "No exchange with this source is recorded in tests/fixtures/cassettes.py. The mapping is "
    "tested against the vendor's documented reply shape, which is what its author believed "
    "the source returns rather than what it was seen to return."
)

DRIVE_A_NOT_FOUND_CANNOT_PROVE_ABSENCE: Final = (
    "Drive answers 404 for a file that does not exist and for one this credential may not "
    "see, and google_drive.A_NOT_FOUND_DOES_NOT_SEPARATE_ABSENT_FROM_REFUSED keeps the two "
    "together. A read-back by file id can therefore answer FOUND or INCONCLUSIVE and never "
    "ABSENT; only a complete listing that does not contain the file can."
)

LARK_BASE_A_MISSING_RECORD_ARRIVES_AS_A_REFUSAL: Final = (
    "Lark reports a record that does not exist as a non-zero business code, which "
    "lark_base.read_record reads as a refusal rather than keep a table of the vendor's codes. "
    "A read-back by record id can therefore never answer ABSENT. Only the list endpoint, "
    "answered with code 0, no items and has_more false, can, and no such reply is recorded."
)

LARK_WIKI_THE_CREDENTIAL_IS_READ_ONLY: Final = (
    "lark_wiki.assert_read_only refuses a credential bound for writing, so no write can be "
    "issued through this connector as built. The reading exists so that the day that changes, "
    "the absence rule is already stated. It is driven by the wiki's own recorded listing and "
    "refusals and by Lark Base's, which share the envelope; a reply that does not say whether "
    "there is more, such as a single node read, is not a listing and never reads as absent."
)

LARAVEL_THE_CREDENTIAL_IS_READ_ONLY: Final = (
    "laravel_manifest binds its credential read-only and reads views, so no write can be "
    "issued through this connector as built. A view the grant no longer covers and a view "
    "that is gone are both REJECTED there, and so INCONCLUSIVE here: a withdrawn contract is "
    "not an absent row."
)

FRESHDESK_ABSENCE_IS_A_SHORT_PAGE: Final = (
    "A Freshdesk page carries no has_more, so the only end signal is a page shorter than "
    "the size asked for. An answered page with no rows is shorter than any size, which is why "
    "it is the one complete empty reading this connector can give. Its search endpoint is "
    "subject to A_SEARCH_THAT_LAGS_A_WRITE_MANUFACTURES_AN_ABSENCE."
)

HUBSPOT_THE_ONLY_RECORDED_ABSENCE: Final = (
    "HUBSPOT-200-empty is the only genuine absence in the recorded corpus, and it is a reply "
    "from the search endpoint, so it is subject to "
    "A_SEARCH_THAT_LAGS_A_WRITE_MANUFACTURES_AN_ABSENCE. The recorded rate limit and "
    "authentication failure both read as not having looked."
)

XERO_NO_ABSENCE_IS_RECORDED: Final = (
    "The Xero recordings are answered lists and two failures. An empty ledger is not "
    "recorded, so the ABSENT branch for this connector is driven by the recorded envelope "
    "with its list emptied."
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


# ------------------------------------------------------------- the seven connectors' readings
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


def _unreadable() -> Reading:
    """See `AN_UNREADABLE_ANSWER_IS_NOT_AN_ANSWER`."""
    return Reading(outcome=CallOutcome.UNAVAILABLE, matched=0, complete=False)


def freshdesk_reading(operation: RestOperation, reply: freshdesk.Reply) -> Reading:
    """One Freshdesk page, refused or projected in `freshdesk.read_page`'s order.

    See `FRESHDESK_ABSENCE_IS_A_SHORT_PAGE` for why an answered page is complete.
    """
    try:
        freshdesk.assert_answered(reply)
        rows = operation.project(reply.body)
    except (freshdesk.FreshdeskUnreachableError, freshdesk.FreshdeskRefusedError) as failure:
        return Reading(outcome=failure.call_outcome, matched=0, complete=False)
    except ConnectorContractError:
        return _unreadable()
    return Reading(outcome=CallOutcome.OK, matched=len(rows), complete=True)


def lark_base_reading(operation: RestOperation, reply: lark_base.LarkReply) -> Reading:
    """One Lark Base list page, complete only when the source said `has_more` is false.

    A single-record reply carries no `has_more`, so `envelope_of` refuses it and it reads as
    unreadable. See `LARK_BASE_A_MISSING_RECORD_ARRIVES_AS_A_REFUSAL`.
    """
    try:
        lark_base.assert_lark_answered(reply)
        rows = operation.project(reply.body)
        envelope = lark_base.envelope_of(reply.body)
    except (lark_base.LarkBaseUnreachableError, lark_base.LarkBaseRefusedError) as failure:
        return Reading(outcome=failure.call_outcome, matched=0, complete=False)
    except ConnectorContractError:
        return _unreadable()
    return Reading(outcome=CallOutcome.OK, matched=len(rows), complete=not envelope.has_more)


def lark_wiki_reading(reply: lark_wiki.LarkReply) -> Reading:
    """One Lark Wiki listing, complete only when `next_cursor` finds no further page.

    A reply whose payload does not state `has_more` is not a listing, and `next_cursor` would
    read its silence as the end: a node read replayed here came back ABSENT for a page that
    exists. It is unreadable instead, as `lark_base.envelope_of` treats the same silence.
    """
    try:
        lark_wiki.assert_answered(reply)
        if not isinstance(reply.data.get("has_more"), bool):
            return _unreadable()
        items = lark_wiki.items_of(reply.data)
        more = lark_wiki.next_cursor(reply.data)
    except (lark_wiki.LarkWikiUnreachableError, lark_wiki.LarkWikiRefusedError) as failure:
        return Reading(outcome=failure.call_outcome, matched=0, complete=False)
    except ConnectorContractError:
        return _unreadable()
    return Reading(outcome=CallOutcome.OK, matched=len(items), complete=more is None)


def drive_reading(operation: RestOperation, reply: google_drive.Reply) -> Reading:
    """One Drive listing. A 404 is `REJECTED` there and so never absent here.

    See `DRIVE_A_NOT_FOUND_CANNOT_PROVE_ABSENCE`.
    """
    try:
        google_drive.assert_answered(reply)
        rows = operation.project(reply.body)
    except (
        google_drive.DriveUnreachableError,
        google_drive.DriveRefusedError,
        google_drive.DriveNotFoundError,
    ) as failure:
        return Reading(outcome=failure.call_outcome, matched=0, complete=False)
    except ConnectorContractError:
        return _unreadable()
    return Reading(
        outcome=CallOutcome.OK, matched=len(rows), complete=not google_drive.next_cursor(reply)
    )


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


#: Every connector's read-back, keyed by the module name `connectors` discovers it under.
READ_BACKS: Final[Mapping[str, ReadBack]] = MappingProxyType(
    {
        "freshdesk": ReadBack(
            reading=freshdesk_reading,
            recorded=(
                "FRESH-200-search",
                "FRESH-429",
                "FRESH-200-search-full-page",
                "FRESH-200-ticket",
                "FRESH-200-contact",
                "FRESH-401",
            ),
            findings=(FRESHDESK_ABSENCE_IS_A_SHORT_PAGE,),
        ),
        "google_drive": ReadBack(
            reading=drive_reading,
            recorded=(
                "DRIVE-200-files-page",
                "DRIVE-200-file",
                "DRIVE-403-user-rate-limit",
                "DRIVE-429",
                "DRIVE-401",
                "DRIVE-404",
            ),
            findings=(DRIVE_A_NOT_FOUND_CANNOT_PROVE_ABSENCE,),
        ),
        "hubspot": ReadBack(
            reading=classified_reading,
            recorded=(
                "HUBSPOT-200-empty",
                "HUBSPOT-200-companies-page",
                "HUBSPOT-200-contacts",
                "HUBSPOT-200-deals",
                "HUBSPOT-200-associations",
                "HUBSPOT-429",
                "HUBSPOT-401",
            ),
            findings=(HUBSPOT_THE_ONLY_RECORDED_ABSENCE,),
        ),
        "laravel": ReadBack(
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
        "lark_base": ReadBack(
            reading=lark_base_reading,
            recorded=(
                "LARK-200-records",
                "LARK-200-code-permission",
                "LARK-200-record",
                "LARK-429",
            ),
            findings=(LARK_BASE_A_MISSING_RECORD_ARRIVES_AS_A_REFUSAL,),
        ),
        "lark_wiki": ReadBack(
            reading=lark_wiki_reading,
            recorded=(
                "LARK-200-records",
                "LARK-200-code-permission",
                "LARK-WIKI-200-node",
                "LARK-WIKI-200-nodes-page",
                "LARK-WIKI-200-code-permission",
                "LARK-WIKI-429",
            ),
            findings=(LARK_WIKI_THE_CREDENTIAL_IS_READ_ONLY,),
        ),
        "xero": ReadBack(
            reading=classified_reading,
            recorded=(
                "XERO-200-invoices",
                "XERO-429",
                "XERO-401-expired",
                "XERO-200-contacts",
                "XERO-200-invoices-full-page",
            ),
            findings=(XERO_NO_ABSENCE_IS_RECORDED,),
        ),
    }
)


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
    discovered: Mapping[str, bool], table: Mapping[str, ReadBack] = READ_BACKS
) -> tuple[str, ...]:
    """Every way the table and the connectors that exist disagree. Empty when they agree.

    See `A_CONNECTOR_IS_STATED_AND_NEVER_SKIPPED`.
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
        f"READ_BACKS names {name!r}, which is not a connector in this package, so its "
        "entry states a finding about nothing"
        for name in sorted(set(table) - set(discovered))
    )
    return tuple(gaps)
