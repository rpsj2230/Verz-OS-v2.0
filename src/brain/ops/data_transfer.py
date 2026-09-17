"""What can be imported and exported from the console, what can run today, and the one that does.

An administrator asks two things of an import and export screen: what data can come in or go out,
and can I do it now. The machinery for most of the first answer exists in this repository as
decisions with no runner, and a screen that listed those as buttons would be a row of controls
reaching nothing. So `CATALOGUE` names every data set the code knows how to move, says for each
whether it can run on an install today, and for the ones that cannot says why in words a person
can act on. The one that can run is the audit trail, and this module is its decisions.

**The audit trail is the export that runs, because its builder exists and its data exists.**
`brain.audit.export` renders a contiguous window of the ledger with the recipe a stranger needs to
verify it, and `brain.audit.readable_export` renders the entries of a window one reader may read.
The ledger has rows on every install from the first grant. Every other export builder here either
reads a store nothing on an install fills (`know.item`) or waits for a reader per store that is not
built (a subject access request, an eDiscovery collection).

**Taking an export needs `admin:export` over everything and what the audit trail's own screen
needs, and nothing more.** `EXPORT_AUTHORITY` because taking a copy out is an administrative act,
and `AUDIT_TRAIL_READ`, the Activity screen's read that `brain.audit_routes` asks before it shows
anybody an entry, because the export is that screen's rows taken away. Until M27.9.4 the second
half was the reach to read every entry the ledger could hold, and a fresh install's only
administrator does not hold it, so the audit trail could be read on a screen and not exported.
See `AN_EXPORT_CARRIES_WHAT_THE_AUDIT_TRAIL_SHOWS_ITS_EXPORTER`. It is also narrower in one case,
stated rather than hidden: a person holding every audit kind and the read log without the screen's
own read could export before and cannot now. That grant is the one
`brain.console.govern_surfaces.READ_AUDIT_OPENS_THE_PAGE_AND_READ_AUDIT_DOT_KIND_FILLS_IT` calls
written halfway, and an export is not a way into the audit trail around its screen.

**The form is decided from grants and never from the window.** `form_for` asks
`reads_the_whole_ledger`: every capability `brain.audit.view.CAPABILITY_BY_KIND` names and the read
log's own `brain.audit.reads.READ_LOG_CAPABILITY`, each over everything, which is the condition
under which `AuditView` shows a reader every entry. That reader gets the chain, exactly as before,
and `everything_is_visible` still asks the view about the entries loaded, so the one decision still
decides. Anybody else gets the readable form, and what it holds is the view's decision entry by
entry, through `shown`. Decided from what was loaded, the form itself would say whether the window
held anything withheld. See `THE_FORM_IS_DECIDED_BEFORE_THE_WINDOW_IS_READ`.

**The limits count what the document carries.** The empty-window refusal and `MAX_EXPORT_ENTRIES`
are judged on readable entries, and the store reads in chunks until it holds one more than the
ceiling or the window ends, dropping what the reader may not read as it goes. Judged on rows, "more
than fifty thousand entries" would tell somebody who may read ten that the rest exist. See
`THE_LIMITS_COUNT_ONLY_WHAT_THE_EXPORTER_MAY_READ`.

**Both halves of access are asked before anything is read, and the refusal is one sentence.** A
window is only ever loaded for somebody who may take an export, so nothing about a window's contents
can be learned by being refused.

**What is not held constant is time.** A window thick with entries the exporter may not read takes
longer to read than one without them, as a page of the audit screen does. That is a timing channel,
bounded by the window a person chooses and open only to a holder of `admin:export`, and it is named
here rather than claimed closed.

**The document is handed over once and not kept.** The record keeps how many entries it holds, the
window and whether the chain verified when it is a chain, and the sha256 of the exact bytes, which
is what lets a copy turning up later be matched to the person who took it. Keeping the document too
would be a second copy of the ledger with none of its protections.

Task ids: M27.8.16, M27.9.4
"""

from __future__ import annotations

import enum
import hashlib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.audit.export import ExportRefusedError, build_export, verify_document
from brain.audit.ledger import AuditChain, AuditEntry
from brain.audit.readable_export import build_readable_export, verify_readable_document
from brain.audit.reads import READ_LOG_CAPABILITY
from brain.audit.view import CAPABILITY_BY_KIND, MAX_PAGE_SIZE, AuditRow, AuditView
from brain.audit_routes import AUDIT_SCREEN
from brain.console.reads import ConsoleRead, permitted
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.ops.export import ExportReason
from brain.tables.data_export import REFERENCE_PATTERN, ExportDataSet, ExportForm

# ------------------------------------------------------------ written-down reasons

#: Who may take an export.
AN_EXPORT_CARRIES_WHAT_THE_AUDIT_TRAIL_SHOWS_ITS_EXPORTER: Final = (
    "An export of the audit trail is taken by somebody holding the export capability over the "
    "whole company who may open the audit trail, and it carries the entries of the window the "
    "audit trail would show them. Asking for the whole ledger instead refused every administrator "
    "who reads part of it, including the first one on every install, while the screen showed "
    "them the same entries the export would have carried."
)

#: Why the form is decided before the window is loaded.
THE_FORM_IS_DECIDED_BEFORE_THE_WINDOW_IS_READ: Final = (
    "Whether an export is a chain or the entries its exporter may read is decided from the "
    "exporter's grants before the window is loaded. Decided from what the window held, the form "
    "would change on the day an entry the exporter may not read was written into it, and the "
    "document's own first line would say so."
)

#: Why the limits count only readable entries.
THE_LIMITS_COUNT_ONLY_WHAT_THE_EXPORTER_MAY_READ: Final = (
    "An empty window and a window over the ceiling are judged on the entries the exporter may "
    "read, never on the rows the window holds. A refusal saying a window holds too many entries, "
    "given to somebody who may read ten of them, is a count of the rest; and a window refused as "
    "empty for one reader and served for another says what the first could not see."
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
    "The document is handed to you once and is not kept on the server. Its record keeps how many "
    "entries it holds, the window and whether the chain verified when it is a chain, and a digest "
    "of the exact file, so a copy found later can be matched to this export."
)

#: What an audit trail export proves, in a person's words, for a reader who takes the chain.
AN_AUDIT_EXPORT_CAN_BE_CHECKED_WITHOUT_THIS_SYSTEM: Final = (
    "The audit trail export carries, beside the entries, the recipe for recomputing every link in "
    "the chain, so whoever receives it can check nothing in the window was edited without running "
    "anything of ours. It cannot show that entries after the window were not removed; the "
    "document says so itself."
)

#: What an audit trail export carries, for a reader who takes the entries they may read.
A_READABLE_EXPORT_CARRIES_WHAT_YOU_MAY_READ: Final = (
    "Your export carries the entries of the window you may read, as the audit trail shows them to "
    "you, and says nothing about any other entry. It is not a chain and cannot be checked as one "
    "without this system; the document says so itself."
)

#: The catalogue's sentence for the audit trail, the same for every reader.
AN_AUDIT_TRAIL_EXPORT_TAKES_THE_FORM_ITS_EXPORTER_MAY_READ: Final = (
    "Whoever may read the whole audit trail takes a window as a chain, with the recipe for "
    "checking it without this system. Anybody else takes the entries of the window they may read, "
    "which is not a chain and says nothing about any other entry."
)

# ----------------------------------------------------------------------- the figures

#: Taking an export. An `admin:` verb, over everything.
EXPORT_AUTHORITY: Final = Capability(value="admin:export")

#: What the audit trail's own screen asks of a reader, and so what an export asks beside
#: `EXPORT_AUTHORITY`. Read from the registry by the key `brain.audit_routes` opens it with.
AUDIT_TRAIL_READ: Final[ConsoleRead] = screen(AUDIT_SCREEN).read

#: The most entries one export may carry. A document for a regulator, not a backup of the ledger:
#: a larger window is several exports, each complete on its own.
MAX_EXPORT_ENTRIES: Final = 50_000

#: What the screen tells a reader who may export about the form they will take.
FORM_TOLD: Final[Mapping[ExportForm, str]] = MappingProxyType(
    {
        ExportForm.CHAIN: AN_AUDIT_EXPORT_CAN_BE_CHECKED_WITHOUT_THIS_SYSTEM,
        ExportForm.READABLE: A_READABLE_EXPORT_CARRIES_WHAT_YOU_MAY_READ,
    }
)

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
            "A window of the audit trail: the grants, removals, sign-ins, approvals and exports in "
            "it that you may read."
        ),
        runs=True,
        told=AN_AUDIT_TRAIL_EXPORT_TAKES_THE_FORM_ITS_EXPORTER_MAY_READ,
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
            "Not available here yet. A SKILL.md pasted or uploaded on the Skills screen is stored "
            "for somebody else to review before it can be assigned, and nothing on this install "
            "fetches a skill from a repository or a link."
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


def reads_the_audit_trail(reach: EntitlementSet, now: datetime) -> bool:
    """Whether the audit trail's screen opens for this reach: `AUDIT_TRAIL_READ`, as it asks it."""
    return permitted(AUDIT_TRAIL_READ, reach, now)


def reads_the_whole_ledger(reach: EntitlementSet, now: datetime) -> bool:
    """Whether `AuditView` would show this reach every entry the ledger could hold.

    Every per-kind audit capability and the read log's, each over everything. See the module
    docstring on why this decides the form and `everything_is_visible` still asks the view.
    """
    for capability in (*CAPABILITY_BY_KIND.values(), READ_LOG_CAPABILITY):
        scope = reach.scope_for(capability, now)
        if scope is None or not scope.is_unrestricted():
            return False
    return True


def may_take_audit_export(reach: EntitlementSet, now: datetime) -> bool:
    """Both halves. See `AN_EXPORT_CARRIES_WHAT_THE_AUDIT_TRAIL_SHOWS_ITS_EXPORTER`."""
    return may_export(reach, now) and reads_the_audit_trail(reach, now)


def form_for(reach: EntitlementSet, now: datetime) -> ExportForm:
    """The chain for a whole-ledger reader, the readable entries for anybody else.

    See `THE_FORM_IS_DECIDED_BEFORE_THE_WINDOW_IS_READ`.
    """
    if reads_the_whole_ledger(reach, now):
        return ExportForm.CHAIN
    return ExportForm.READABLE


def shown(entry: AuditEntry, reader: EntitlementSet, now: datetime) -> AuditRow | None:
    """The row `AuditView` shows this reader for this entry, or None when it shows none.

    Asked one entry at a time through the view's own page, so the answer is the view's decision and
    never a copy of `_may_see`. The view decides each entry on that entry alone, so asking it one at
    a time is the same decision it makes over a window.
    """
    rows = AuditView((entry,), reader=reader, now=now).page(limit=1).rows
    if not rows:
        return None
    return rows[0]


def readable_entries(
    entries: Sequence[AuditEntry], reader: EntitlementSet, now: datetime
) -> tuple[AuditEntry, ...]:
    """The entries the view shows this reader, in the order given."""
    return tuple(one for one in entries if shown(one, reader, now) is not None)


def kept_by(
    form: ExportForm, reader: EntitlementSet, now: datetime
) -> Callable[[Sequence[AuditEntry]], tuple[AuditEntry, ...]]:
    """What the store keeps of each chunk it reads: every entry of a chain, readable ones otherwise.

    A chain keeps everything because a chain with an entry dropped is not a chain, and
    `produce_audit_export` then asks the view about all of it. See
    `THE_LIMITS_COUNT_ONLY_WHAT_THE_EXPORTER_MAY_READ` for the readable form.
    """
    if form is ExportForm.CHAIN:
        return tuple

    def readable(entries: Sequence[AuditEntry]) -> tuple[AuditEntry, ...]:
        return readable_entries(entries, reader, now)

    return readable


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
    shown_count = 0
    cursor: str | None = None
    while True:
        page = view.page(limit=MAX_PAGE_SIZE, cursor=cursor)
        shown_count += len(page.rows)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    return shown_count == len({one.entry_hash for one in entries})


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
    """One rendered audit trail export, and what its record keeps about it.

    `first_seq`, `last_seq` and `verified` are a chain's, and None for a readable export; see
    `brain.tables.data_export.A_READABLE_EXPORT_NAMES_NO_WINDOW`.
    """

    document: str
    digest: str
    form: ExportForm
    first_seq: int | None
    last_seq: int | None
    entries: int
    verified: bool | None


class AuditExportRefusedError(Exception):
    """The window cannot be exported as it stands. The message says what to do."""


#: What a person taking the chain is told when the window is empty, too large, or not a chain.
EMPTY_WINDOW: Final = "Nothing was recorded in this window. Choose a window with entries in it."
TOO_LARGE_WINDOW: Final = (
    f"This window holds more than {MAX_EXPORT_ENTRIES} entries. Export it as several shorter "
    "windows, each of which verifies on its own."
)
NOT_A_CHAIN: Final = (
    "The entries in this window do not follow one another without a gap, so they cannot be "
    "exported as a chain. Choose a window that starts or ends at a different time."
)

#: What a person taking the readable form is told, in words true whatever was withheld.
NOTHING_YOU_MAY_READ: Final = (
    "This window holds no entries you may read. Choose a window with entries in it."
)
TOO_MANY_YOU_MAY_READ: Final = (
    f"This window holds more than {MAX_EXPORT_ENTRIES} entries you may read. Export it as several "
    "shorter windows."
)


def produce_audit_export(
    entries: Sequence[AuditEntry],
    *,
    reader: EntitlementSet,
    reason: ExportReason,
    trace_id: str,
    at: datetime,
    since: datetime,
    until: datetime,
) -> Produced:
    """Render the window in the form this reader's grants decide, verify it, and describe it.

    See `form_for`. `since` and `until` are the window as asked for, which the readable document
    names; the chain names its own sequence range instead.
    """
    if form_for(reader, at) is ExportForm.CHAIN:
        return _produce_chain(entries, reader=reader, reason=reason, trace_id=trace_id, at=at)
    return _produce_readable(
        entries,
        reader=reader,
        reason=reason,
        trace_id=trace_id,
        at=at,
        since=since,
        until=until,
    )


def _produce_chain(
    entries: Sequence[AuditEntry],
    *,
    reader: EntitlementSet,
    reason: ExportReason,
    trace_id: str,
    at: datetime,
) -> Produced:
    """A window the reader may read whole, rendered as a chain.

    Refuses an empty window, one over `MAX_EXPORT_ENTRIES`, and one that is not a contiguous run of
    the chain, each with the sentence a person acts on. Raises `PermissionError` for entries the
    view would not show this reader, which `form_for` has already made impossible; it is the view
    deciding once more, not a second rule.
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
        form=ExportForm.CHAIN,
        first_seq=built.manifest.first_seq,
        last_seq=built.manifest.last_seq,
        entries=built.manifest.entry_count,
        verified=built.manifest.verified,
    )


def _produce_readable(
    entries: Sequence[AuditEntry],
    *,
    reader: EntitlementSet,
    reason: ExportReason,
    trace_id: str,
    at: datetime,
    since: datetime,
    until: datetime,
) -> Produced:
    """The entries the view shows this reader, rendered as `brain.audit.readable_export`.

    Every limit is judged after the view has decided, on what the document would carry; see
    `THE_LIMITS_COUNT_ONLY_WHAT_THE_EXPORTER_MAY_READ`. An entry the reader may not read is
    dropped here the way the view drops it, never refused, because a refusal would say it exists.
    """
    rows = tuple(row for row in (shown(one, reader, at) for one in entries) if row is not None)
    if not rows:
        raise AuditExportRefusedError(NOTHING_YOU_MAY_READ)
    if len(rows) > MAX_EXPORT_ENTRIES:
        raise AuditExportRefusedError(TOO_MANY_YOU_MAY_READ)
    built = build_readable_export(
        rows,
        exported_by=reader.principal_id,
        trace_id=trace_id,
        reason_code=reason.value,
        at=at,
        since=since,
        until=until,
    )
    document = built.render()
    whole, why = verify_readable_document(document)
    if not whole:
        msg = f"the rendered export does not match its own manifest: {why}"
        raise RuntimeError(msg)
    return Produced(
        document=document,
        digest=hashlib.sha256(document.encode("utf-8")).hexdigest(),
        form=ExportForm.READABLE,
        first_seq=None,
        last_seq=None,
        entries=built.manifest.entry_count,
        verified=None,
    )
