"""What can be imported and exported from the console, what can run today, and the one that does.

An administrator asks two things of an import and export screen: what data can come in or go out,
and can I do it now. The machinery for most of the first answer exists in this repository as
decisions with no runner, and a screen that listed those as buttons would be a row of controls
reaching nothing. So `CATALOGUE` names every data set the code knows how to move, says for each
whether it can run on an install today, and for the ones that cannot says why in words a person
can act on. The one that can run is the audit trail, and this module is its decisions.

**The audit trail is the export that runs, because its builder exists and its data exists.**
`brain.audit.export` renders a contiguous window of the ledger with the recipe a stranger needs to
verify it, and nothing called it. The ledger has rows on every install from the first grant. Every
other export builder here either reads a store nothing on an install fills (`know.item`) or waits
for a reader per store that is not built (a subject access request, an eDiscovery collection).

**An export is a copy of company data, so it takes the strongest capability that applies, twice
over.** `EXPORT_AUTHORITY`, `admin:export`, held over everything, because taking a copy out is an
administrative act; and the reach to read every entry the ledger could hold, because the copy is
the ledger and a filtered chain does not verify. The second is `reads_the_whole_ledger`: every
capability `brain.audit.view.CAPABILITY_BY_KIND` names and the read log's own
`brain.audit.reads.READ_LOG_CAPABILITY`, each over everything. That is the condition under which
`AuditView` shows a reader every entry, derived from the same two tables it reads, and
`everything_is_visible` then asks `AuditView` itself about the entries actually loaded, so the one
decision still decides. See `A_WHOLE_LEDGER_READER_IS_ASKED_BEFORE_THE_LEDGER_IS`.

**Both are asked before anything is read, and the refusal is one sentence.** A reader who held the
export capability and not the reach would otherwise learn, from whether an empty window was
refused, whether anything had happened in it. Asking first means a window is only ever loaded for
somebody entitled to every entry in it, so nothing about a window's contents can be learned by
being refused.

**The document is handed over once and not kept.** The record of the export keeps its window, its
entry count, whether it verified and the sha256 of the exact bytes, which is what lets a copy
turning up later be matched to the person who took it. Keeping the document too would be a second
copy of the ledger with none of its protections, in a store nothing on an install connects to.

Task ids: M27.8.16
"""

from __future__ import annotations

import enum
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.audit.export import ExportRefusedError, build_export, verify_document
from brain.audit.ledger import AuditChain, AuditEntry
from brain.audit.reads import READ_LOG_CAPABILITY
from brain.audit.view import CAPABILITY_BY_KIND, MAX_PAGE_SIZE, AuditView
from brain.core.entitlement import Capability, EntitlementSet
from brain.ops.export import ExportReason
from brain.tables.data_export import REFERENCE_PATTERN, ExportDataSet

# ------------------------------------------------------------ written-down reasons

#: Why the whole-ledger reach is asked before a window is loaded.
A_WHOLE_LEDGER_READER_IS_ASKED_BEFORE_THE_LEDGER_IS: Final = (
    "An export of the audit trail is refused unless the person may read every entry the ledger "
    "could hold, and that is asked before anything is loaded. Asked afterwards, a person holding "
    "the export capability and a partial audit grant would be refused for a window holding an "
    "entry they may not see and served for one that holds none, and the difference would tell "
    "them what happened in a window they were never shown."
)

#: What an export is, served beside the control.
AN_EXPORT_IS_A_COPY_THAT_LEAVES_EVERY_GUARD_BEHIND: Final = (
    "An export is a copy of the company's records that is read by whoever holds the file, for as "
    "long as it exists, with nothing checking who they are. It is recorded in the audit trail "
    "under your name with the reason and reference you give, and the reason is chosen from a "
    "fixed list so that nobody's name has to be written into the record."
)

#: What happens to the document.
THE_DOCUMENT_IS_HANDED_OVER_ONCE: Final = (
    "The document is handed to you once and is not kept on the server. Its record keeps the "
    "window, how many entries it holds, whether the chain verified and a digest of the exact file, "
    "so a copy found later can be matched to this export."
)

#: What an audit trail export proves, in a person's words.
AN_AUDIT_EXPORT_CAN_BE_CHECKED_WITHOUT_THIS_SYSTEM: Final = (
    "The audit trail export carries, beside the entries, the recipe for recomputing every link in "
    "the chain, so whoever receives it can check nothing in the window was edited without running "
    "anything of ours. It cannot show that entries after the window were not removed; the "
    "document says so itself."
)

# ----------------------------------------------------------------------- the figures

#: Taking an export. An `admin:` verb, over everything.
EXPORT_AUTHORITY: Final = Capability(value="admin:export")

#: The most entries one export may carry. A document for a regulator, not a backup of the ledger:
#: a larger window is several exports, each verifiable on its own.
MAX_EXPORT_ENTRIES: Final = 50_000

_REFERENCE_RE: Final = re.compile(REFERENCE_PATTERN)


class Direction(enum.StrEnum):
    """Which way a data set moves."""

    EXPORT = "export"
    IMPORT = "import"


@dataclass(frozen=True)
class DataSet:
    """One thing the code knows how to move, and whether an install can move it today."""

    key: str
    label: str
    direction: Direction
    carries: str
    runs: bool
    told: str


#: Everything the code knows how to bring in or take out, in the order the screen lists them.
CATALOGUE: Final[tuple[DataSet, ...]] = (
    DataSet(
        key=ExportDataSet.AUDIT_TRAIL.value,
        label="Audit trail",
        direction=Direction.EXPORT,
        carries=(
            "A window of the audit trail: every grant, removal, sign-in, approval and export in "
            "it, with the recipe to verify the chain."
        ),
        runs=True,
        told=AN_AUDIT_EXPORT_CAN_BE_CHECKED_WITHOUT_THIS_SYSTEM,
    ),
    DataSet(
        key="knowledge",
        label="Knowledge",
        direction=Direction.EXPORT,
        carries="Knowledge items with the scope that says who may read each one.",
        runs=False,
        told=(
            "Not available yet. The export is written and keeps each item's scope with it, and "
            "nothing on this install stores a knowledge item for it to read, because documents "
            "cannot be brought in yet either."
        ),
    ),
    DataSet(
        key="subject_access",
        label="Everything held about one person",
        direction=Direction.EXPORT,
        carries="What the system holds about one person, for a subject access request.",
        runs=False,
        told=(
            "Not available yet. What to gather from each store is decided, and the part that "
            "reads each store for one person is not built, so a request cannot be answered from "
            "here."
        ),
    ),
    DataSet(
        key="bulk_collection",
        label="Collection for a legal or regulatory request",
        direction=Direction.EXPORT,
        carries="Records from named stores for named people, with the reason and its reference.",
        runs=False,
        told=(
            "Not available yet. The record such a collection must leave is decided, and nothing "
            "reads the stores it would collect from."
        ),
    ),
    DataSet(
        key="conversation_history",
        label="A person's own conversations",
        direction=Direction.EXPORT,
        carries="One person's conversations, as they were shown to them.",
        runs=False,
        told=(
            "Not taken from here. A person's conversation history is theirs to export from their "
            "own workspace rather than an administrator's to take in bulk, and that export is not "
            "served yet."
        ),
    ),
    DataSet(
        key="documents",
        label="Documents into knowledge",
        direction=Direction.IMPORT,
        carries="Files and links, checked and scanned, read into knowledge with a scope.",
        runs=False,
        told=(
            "Not available yet. An upload can be received and checked, and nothing reads what "
            "arrives into knowledge, and nothing on this install connects to the object store "
            "where the original would be kept."
        ),
    ),
    DataSet(
        key="skills",
        label="Skills",
        direction=Direction.IMPORT,
        carries="A skill from a repository, a link or an upload, held for review before any use.",
        runs=False,
        told=(
            "Not available yet. A skill can be fetched, unpacked and checked, and nothing on this "
            "install stores an imported skill for somebody to review."
        ),
    ),
    DataSet(
        key="procedures",
        label="Written procedures",
        direction=Direction.IMPORT,
        carries="A procedure from a word processor or a wiki, turned into a draft skill.",
        runs=False,
        told=(
            "Not available yet. A procedure's text can be turned into a draft, and there is "
            "nowhere to keep the draft for review."
        ),
    ),
    DataSet(
        key="staff",
        label="People from a staff directory",
        direction=Direction.IMPORT,
        carries="Who works here, their department and their manager.",
        runs=False,
        told=(
            "Brought in from a staff source rather than from here: the Staff sources screen shows "
            "each source and runs a trial of what it would change."
        ),
    ),
    DataSet(
        key="previous_system",
        label="Knowledge from the system this replaces",
        direction=Direction.IMPORT,
        carries=(
            "What carries across from a previous system: knowledge only, read again, and never "
            "its vectors."
        ),
        runs=False,
        told=(
            "Not run from a screen. What may carry across and what may not is decided, and a move "
            "from a previous system is planned and run with whoever looks after the install."
        ),
    ),
)


# ------------------------------------------------------------------ the decisions


def may_export(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach holds `EXPORT_AUTHORITY` over everything, at this instant."""
    scope = reach.scope_for(EXPORT_AUTHORITY, now)
    return scope is not None and scope.is_unrestricted()


def reads_the_whole_ledger(reach: EntitlementSet, now: datetime) -> bool:
    """Whether `AuditView` would show this reach every entry the ledger could hold.

    Every per-kind audit capability and the read log's, each over everything. See the module
    docstring on why this is asked before a window is loaded and `everything_is_visible` after.
    """
    for capability in (*CAPABILITY_BY_KIND.values(), READ_LOG_CAPABILITY):
        scope = reach.scope_for(capability, now)
        if scope is None or not scope.is_unrestricted():
            return False
    return True


def may_take_audit_export(reach: EntitlementSet, now: datetime) -> bool:
    """Both halves. See `A_WHOLE_LEDGER_READER_IS_ASKED_BEFORE_THE_LEDGER_IS`."""
    return may_export(reach, now) and reads_the_whole_ledger(reach, now)


def everything_is_visible(
    entries: Sequence[AuditEntry], reader: EntitlementSet, now: datetime
) -> bool:
    """Whether `AuditView` shows this reader every one of these entries.

    Walked page by page through the view's own cursor and counted, so the answer is the view's
    decision about each entry and never a copy of it. A count is enough because the entries are
    distinct and the view only ever withholds: it cannot show a row it was not given. The count
    stays in this function and is never shown to anybody.
    """
    view = AuditView(entries, reader=reader, now=now)
    shown = 0
    cursor: str | None = None
    while True:
        page = view.page(limit=MAX_PAGE_SIZE, cursor=cursor)
        shown += len(page.rows)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    return shown == len({one.entry_hash for one in entries})


class ExportField(enum.StrEnum):
    """The fields an export request carries, as a problem names them."""

    DATA_SET = "data_set"
    REASON = "reason"
    REFERENCE = "reason_reference"
    WINDOW = "window"


@dataclass(frozen=True)
class ExportProblem:
    """One thing wrong with an export request: which field, a stable code, and what to do."""

    field: ExportField
    code: str
    message: str


def request_problems(
    *, data_set: str, reason: str, reason_reference: str, since: datetime, until: datetime
) -> tuple[ExportProblem, ...]:
    """Every problem with an export request, in field order. Empty means it may be taken."""
    found: list[ExportProblem] = []
    runnable = {one.key for one in CATALOGUE if one.runs and one.direction is Direction.EXPORT}
    if data_set not in runnable:
        found.append(
            ExportProblem(
                ExportField.DATA_SET,
                "not_available",
                "Choose a data set this screen says can be exported now.",
            )
        )
    if reason not in {one.value for one in ExportReason}:
        found.append(
            ExportProblem(ExportField.REASON, "unknown", "Choose the reason from the list.")
        )
    if not _REFERENCE_RE.fullmatch(reason_reference):
        found.append(
            ExportProblem(
                ExportField.REFERENCE,
                "not_a_reference",
                "Give the reference of the written request or authorisation, such as a ticket or "
                "matter number: up to 64 letters, digits, dots, slashes, hashes, hyphens and "
                "underscores, with no spaces. Never a person's name.",
            )
        )
    if since.tzinfo is None or until.tzinfo is None:
        found.append(
            ExportProblem(
                ExportField.WINDOW, "no_timezone", "Give both ends of the window with a timezone."
            )
        )
    elif since >= until:
        found.append(
            ExportProblem(ExportField.WINDOW, "backwards", "The window must start before it ends.")
        )
    return tuple(found)


@dataclass(frozen=True)
class Produced:
    """One rendered audit trail export, and what its record keeps about it."""

    document: str
    digest: str
    first_seq: int | None
    last_seq: int | None
    entries: int
    verified: bool


class AuditExportRefusedError(Exception):
    """The window cannot be exported as it stands. The message says what to do."""


#: What a person is told when the window is empty, too large, or not a chain.
EMPTY_WINDOW: Final = "Nothing was recorded in this window. Choose a window with entries in it."
TOO_LARGE_WINDOW: Final = (
    f"This window holds more than {MAX_EXPORT_ENTRIES} entries. Export it as several shorter "
    "windows, each of which verifies on its own."
)
NOT_A_CHAIN: Final = (
    "The entries in this window do not follow one another without a gap, so they cannot be "
    "exported as a chain. Choose a window that starts or ends at a different time."
)


def produce_audit_export(
    entries: Sequence[AuditEntry],
    *,
    reader: EntitlementSet,
    reason: ExportReason,
    trace_id: str,
    at: datetime,
) -> Produced:
    """Render a window the reader may read whole, verify the document, and describe it.

    Refuses an empty window, one over `MAX_EXPORT_ENTRIES`, and one that is not a contiguous run of
    the chain, each with the sentence a person acts on. Raises `PermissionError` for entries the
    view would not show this reader, which the caller has already made impossible by asking
    `may_take_audit_export` first; it is the view deciding once more, not a second rule.
    """
    if not entries:
        raise AuditExportRefusedError(EMPTY_WINDOW)
    if len(entries) > MAX_EXPORT_ENTRIES:
        raise AuditExportRefusedError(TOO_LARGE_WINDOW)
    if not everything_is_visible(entries, reader, at):
        msg = "the audit view does not show this reader every entry in the window"
        raise PermissionError(msg)
    ordered = sorted(entries, key=lambda one: one.seq)
    chain = AuditChain(ordered, start_hash=ordered[0].prev_hash)
    try:
        built = build_export(
            chain,
            exported_by=reader.principal_id,
            trace_id=trace_id,
            reason_code=reason.value,
            at=at,
        )
    except ExportRefusedError as refused:
        raise AuditExportRefusedError(NOT_A_CHAIN) from refused
    document = built.render()
    whole, why = verify_document(document)
    if not whole:
        msg = f"the rendered export does not match its own manifest: {why}"
        raise RuntimeError(msg)
    return Produced(
        document=document,
        digest=hashlib.sha256(document.encode("utf-8")).hexdigest(),
        first_seq=built.manifest.first_seq,
        last_seq=built.manifest.last_seq,
        entries=built.manifest.entry_count,
        verified=built.manifest.verified,
    )
