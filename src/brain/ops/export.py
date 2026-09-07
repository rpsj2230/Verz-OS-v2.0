"""Getting data out of the system, which is the one act that leaves every guard behind.

An export is the widest permission act this platform performs. Everything else decides what
one caller may see for the length of one answer, and the decision is re-made on the next
question; an export produces a file that is read by whoever ends up holding it, for as long
as it exists, with no gate in front of it. Three properties follow from that, and each of
them is why one of the three functions below is shaped the way it is.

**An export is never re-checked, so a reference does not travel.** `brain.chat.turns.
RecordRef` says why it exists in those words: a reference the asker may no longer resolve
yields nothing on the next turn, where a copy of the record would still read perfectly after
the grant behind it was revoked. An export is precisely a thing that is never resolved
again, so the references come out. What travels is what the person was shown, as text.

**A conversation export must not count what it did not include.** `Turn.locked` carries the
fields withheld from records a turn showed, and `ShownAnswer.lock_count` is a count of them.
Neither may be exported: "47 messages, 3 locks" tells the reader there are three things they
were not shown, which is three facts they did not have, and the architecture's rule is that
DENIED and ABSENT are indistinguishable. The subtraction version is the one that gets past
review, so the exported turn carries no source ordinal and no source id either: a document
numbered 1, 2, 5, 6 has counted the missing ones out loud. See
`A_GAP_IN_A_SEQUENCE_COUNTS_WHAT_IS_MISSING`.

**A bulk export cannot be taken without a reason and cannot be taken quietly.** The reason
is a field on a frozen request object with no default, so there is no call that omits it;
validating a reason string would leave a function that can be called without one, and a
function that can be called without one is a function that will be, at 2am, by somebody
exporting a mailbox for a good cause. The audit row is a required member of the returned
object rather than something written on the side, so there is no path that produces the
export and not the row, and no flag anywhere that suppresses it. See
`THE_AUDIT_ROW_IS_PART_OF_THE_EXPORT_AND_NOT_A_SIDE_EFFECT`.

**A knowledge export carries its scope or it does not go.** An item that leaves the system
scoped to one department and comes back, or is read, as an unscoped document has been
laundered: the permission was not revoked, it was simply left behind in a format that has
nowhere to put it. So `ExportedKnowledge.visibility` has no default, `knowledge_export`
checks the exported scope predicate against the source's own before returning, and the
predicate compared is `brain.core.scope.Scope`, which is built by the knowledge layer rather
than by anything here.

What this module deliberately does not do is write to the audit ledger.
`brain.audit.ledger.AuditAction` is a closed vocabulary pinned by an invariant test, and it
has no member for an export; adding one is an edit to two files that belong to the audit
package and a decision somebody should make there rather than a side effect of this work. So
`ExportAudit` is the row, fully formed and required, and wiring it into
`brain.audit.record.AuditRecorder` is an open piece of work rather than an omission nobody
noticed.

Task ids: M25.3.1, M25.3.2, M25.3.3
"""

from __future__ import annotations

import enum
import inspect
from collections.abc import Mapping, Sequence
from dataclasses import MISSING, dataclass, fields
from datetime import datetime

from brain.chat.turns import Turn, TurnKind
from brain.core.scope import Scope
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.retention import Store


class ExportError(Exception):
    """Raised when an export would leave a guard behind rather than carry it."""


# ------------------------------------------------------------------ written-down reasons
#: Why a record reference is dropped from a conversation export.
AN_EXPORT_IS_NEVER_RE_CHECKED_SO_A_REFERENCE_DOES_NOT_TRAVEL = (
    "brain.chat.turns.RecordRef exists so that a reference cannot outlive the grant that "
    "justified it: it is re-checked on every later turn and yields nothing once the grant "
    "is gone. An export is the one artefact that is never checked again. Carrying the "
    "references into it would turn a structure designed to expire into a permanent list of "
    "which records an answer touched, readable by whoever holds the file, which is exactly "
    "what a copy of the record would have been and is why RecordRef holds no values."
)

#: Why an exported turn carries no ordinal and no source id.
A_GAP_IN_A_SEQUENCE_COUNTS_WHAT_IS_MISSING = (
    "An export of what somebody may see must not say how much they may not. The direct "
    "version is a lock count, and nobody ships that. The version that gets through review "
    "is an ordinal: turns numbered 1, 2, 5 and 6 have told the reader that two things sit "
    "between the second and the third, which is the same disclosure arrived at by "
    "subtraction. So the exported turn carries its time and its text and no position in "
    "anything, and there is no field on the model that could hold one."
)

#: Why the audit row is a member of the result rather than a call somebody makes after.
THE_AUDIT_ROW_IS_PART_OF_THE_EXPORT_AND_NOT_A_SIDE_EFFECT = (
    "An export is the widest permission act in the system and the audit row is the only "
    "thing that makes it reviewable afterwards. Written as a separate call it is a line "
    "somebody forgets, or wraps in a condition, or disables in the environment where the "
    "nightly job runs. So the row is a required field of the object the export function "
    "returns: there is no way to obtain the export without it, and no parameter anywhere "
    "that turns it off."
)

#: Why the reason is a field on a required object rather than a validated argument.
A_REASON_A_CALLER_CAN_OMIT_IS_A_REASON_NOBODY_GIVES = (
    "Validation catches an empty reason and does nothing about the call that never had a "
    "reason parameter to fill in. The reason is therefore structural: a bulk export takes "
    "one request object, the object has no default for its reason or for the reference to "
    "the written authorisation, and a frozen dataclass will not construct without both. "
    "The picklist is closed for the same reason brain.audit.compliance.LawfulBasis is: a "
    "free-text reason on an export record is where the name of the person being "
    "investigated ends up."
)

#: Why an export that drops scope is worse than one that refuses.
AN_EXPORT_THAT_FLATTENS_SCOPE_LAUNDERS_PERMISSION = (
    "Knowledge in this system is readable because a scope predicate says who reaches it. An "
    "export that emits the text without the scope has produced a document that is readable "
    "by whoever holds it, and when that document is re-imported, quoted or indexed it comes "
    "back with no scope at all. Nothing was granted and nothing was revoked; the "
    "restriction was simply left behind in a format with nowhere to put it. So the scope "
    "travels with the item, the exported predicate is compared against the source's before "
    "the export is returned, and an item that cannot carry its scope does not travel."
)


# --------------------------------------------------- M25.3.1  conversation export per user
@dataclass(frozen=True)
class ExportedTurn:
    """One turn as it leaves the system: when, who, what kind, and what was said.

    Read the fields against `brain.chat.turns.Turn`. Two of its members are missing and both
    are deliberate. `refs` is gone because an export is never re-checked; `locked` is gone
    because it is a count of what the reader was not shown. Neither has an attribute here to
    live in, so restoring either is an edit to a frozen model rather than a line in a mapping
    function.
    """

    kind: TurnKind
    at: datetime
    principal_id: str
    text: str


@dataclass(frozen=True)
class ConversationExport:
    """A conversation, as one person may see it.

    There is no total, no lock count and no ordinal anywhere on this model. `len(turns)` is
    a count of what is here, which is a fact about the document rather than about what was
    withheld: it can only be turned into a disclosure by comparing it against a number the
    reader does not have, and no part of this system gives them that number.
    """

    subject_id: str
    conversation_id: str
    at: datetime
    turns: tuple[ExportedTurn, ...]

    def __post_init__(self) -> None:
        for name in ("subject_id", "conversation_id"):
            if not getattr(self, name):
                msg = f"a conversation export with no {name} belongs to nobody"
                raise ExportError(msg)
        if self.at.tzinfo is None:
            msg = "a naive export time compares wrongly against an aware one"
            raise ExportError(msg)


def conversation_export(
    *,
    subject_id: str,
    conversation_id: str,
    at: datetime,
    turns: Sequence[Turn],
) -> ConversationExport:
    """Export a conversation for the person who took part in it (M25.3.1).

    `turns` is what this caller may see, decided before it gets here by the same entitlement
    intersection that decides everything else. There is no parameter for the turns they may
    not see and no return value describing them, which is the structural half of the rule:
    a function that never receives the withheld turns cannot report on them, by accident or
    otherwise.

    Order is preserved as given rather than re-sorted. A conversation whose turns were
    reordered by an export is a transcript that no longer records what was said, and the
    caller is the one holding the conversation's own ordering.
    """
    exported = tuple(
        ExportedTurn(kind=turn.kind, at=turn.at, principal_id=turn.principal_id, text=turn.text)
        for turn in turns
    )
    return ConversationExport(
        subject_id=subject_id,
        conversation_id=conversation_id,
        at=at,
        turns=exported,
    )


# -------------------------------------------------------- M25.3.2  bulk export for eDiscovery
class ExportReason(enum.StrEnum):
    """Why a bulk export is being taken. A closed picklist, not a text box.

    Closed for the reason `brain.audit.compliance.LawfulBasis` and
    `brain.audit.ledger.LegalHold.reason_code` are closed: a free-text reason on the record
    of an export is where the name of the person under investigation, the allegation and the
    complainant end up, in a row that is kept longer than the export itself and read by more
    people.

    Each member names a thing that actually happens rather than a category somebody
    imagined. `SUBJECT_ACCESS_REQUEST` is here because a subject access request assembled by
    `brain.ops.erasure` still has to leave the building, and it is a different act from an
    eDiscovery collection even though it moves the same bytes.
    """

    LEGAL_DISCOVERY = "legal_discovery"
    REGULATORY_REQUEST = "regulatory_request"
    INTERNAL_INVESTIGATION = "internal_investigation"
    SUBJECT_ACCESS_REQUEST = "subject_access_request"
    LITIGATION_HOLD_COLLECTION = "litigation_hold_collection"
    SYSTEM_MIGRATION = "system_migration"


@dataclass(frozen=True)
class BulkExportRequest:
    """Who is taking an export, over what, why, and where the authorisation is written down.

    Every field is required and none has a default that could stand in for a decision. That
    is the whole design: `A_REASON_A_CALLER_CAN_OMIT_IS_A_REASON_NOBODY_GIVES`.

    `all_subjects` is explicit for the reason `brain.audit.ledger.LegalHold` makes it
    explicit: the other reading of "no subjects named" is "everybody", and an export that
    covers everybody by accident is the largest possible version of this mistake.
    """

    requested_by: str
    reason: ExportReason
    #: Where the written authorisation lives: a ticket, a matter number, a signed request.
    #: A reference, never the authorisation itself, following
    #: `brain.audit.compliance.ProcessingRecord.basis_reference`.
    reason_reference: str
    stores: frozenset[Store]
    subjects: frozenset[str] = frozenset()
    all_subjects: bool = False

    def __post_init__(self) -> None:
        if not self.requested_by:
            msg = "a bulk export with no requester is one nobody can be asked about"
            raise ExportError(msg)
        if not self.reason_reference.strip():
            msg = (
                "a bulk export names a reason and no written authorisation; the reference "
                "is what somebody reviewing this in a year reads instead of guessing"
            )
            raise ExportError(msg)
        if not self.stores:
            msg = (
                "a bulk export naming no store covers nothing or everything depending on "
                "who reads it; name the stores"
            )
            raise ExportError(msg)
        if not (self.all_subjects or self.subjects):
            msg = (
                "a bulk export naming no subject and not setting all_subjects means "
                "everybody by accident; say which"
            )
            raise ExportError(msg)
        if self.all_subjects and self.subjects:
            msg = (
                "a bulk export cannot both cover everybody and name a shortlist; the "
                "shortlist would read as the scope and it is not"
            )
            raise ExportError(msg)


@dataclass(frozen=True)
class ExportAudit:
    """The row an export writes. Identifiers, a reason and counts, and nothing exported.

    Not written to `brain.audit.ledger` by this module: that vocabulary is closed and has no
    member for an export, and adding one belongs to the audit package. This is the row,
    complete, for whoever wires the two together.
    """

    export_id: str
    at: datetime
    requested_by: str
    reason: ExportReason
    reason_reference: str
    stores: tuple[Store, ...]
    #: The subjects covered, as identifiers. Empty when the export covers everybody, which
    #: `all_subjects` says rather than an empty tuple being read as "nobody".
    subjects: tuple[str, ...]
    all_subjects: bool
    items: int

    def __post_init__(self) -> None:
        if not self.export_id:
            msg = "an export audit row with no export id refers to nothing"
            raise ExportError(msg)
        if self.items < 0:
            msg = "an export cannot contain a negative number of items"
            raise ExportError(msg)
        if self.at.tzinfo is None:
            msg = "a naive audit time compares wrongly against an aware one"
            raise ExportError(msg)

    def line(self) -> str:
        """One line for an operator, naming the reason and the reference and no content."""
        over = "all subjects" if self.all_subjects else f"{len(self.subjects)} subject(s)"
        names = ", ".join(store.value for store in self.stores)
        return (
            f"export {self.export_id}: {self.requested_by} took {self.items} item(s) over "
            f"{over} from [{names}] for {self.reason.value} ({self.reason_reference})"
        )


@dataclass(frozen=True)
class ExportedStore:
    """How much one store contributed to an export. A count, and the store's name."""

    store: Store
    items: int

    def __post_init__(self) -> None:
        if self.items < 0:
            msg = f"{self.store.value} contributed a negative number of items"
            raise ExportError(msg)


@dataclass(frozen=True)
class BulkExport:
    """An export and the row recording it, which are one object on purpose.

    `audit` has no default and is not optional. That is the mechanism behind
    `THE_AUDIT_ROW_IS_PART_OF_THE_EXPORT_AND_NOT_A_SIDE_EFFECT`: obtaining the manifest
    means holding the audit row, so there is no code path that produces one and not the
    other and nothing to remember at a call site.
    """

    request: BulkExportRequest
    audit: ExportAudit
    manifest: tuple[ExportedStore, ...]

    @property
    def items(self) -> int:
        return sum(one.items for one in self.manifest)


def bulk_export(
    *,
    request: BulkExportRequest,
    export_id: str,
    at: datetime,
    counts: Mapping[Store, int],
) -> BulkExport:
    """Take a bulk export, and write the row that says it happened (M25.3.2).

    The signature is the argument. There is no `reason` string that could be empty, because
    the reason is on the request and the request will not construct without it. There is no
    `audit` flag, no `quiet`, and no way to receive the manifest on its own. A caller who
    wants an export without a row has to change this function, in a file whose docstring
    says why they should not.

    A count for a store the request did not name is refused rather than dropped. Dropping it
    would produce an export whose manifest disagrees with what was actually collected, and
    the manifest is the document somebody later checks the collection against.
    """
    if not export_id:
        msg = "a bulk export needs an id; a row nobody can cite records nothing"
        raise ExportError(msg)
    if outside := sorted(str(store) for store in set(counts) - request.stores):
        msg = (
            f"the export request does not cover {outside} and a count was reported for it; "
            "the manifest and the collection must be the same document"
        )
        raise ExportError(msg)
    manifest = tuple(
        ExportedStore(store=store, items=counts.get(store, 0))
        for store in sorted(request.stores, key=lambda store: store.value)
    )
    audit = ExportAudit(
        export_id=export_id,
        at=at,
        requested_by=request.requested_by,
        reason=request.reason,
        reason_reference=request.reason_reference,
        stores=tuple(one.store for one in manifest),
        subjects=tuple(sorted(request.subjects)),
        all_subjects=request.all_subjects,
        items=sum(one.items for one in manifest),
    )
    return BulkExport(request=request, audit=audit, manifest=manifest)


# ------------------------------------------------------- M25.3.3  knowledge export
@dataclass(frozen=True)
class ExportedKnowledge:
    """One knowledge item, with the visibility that decides who reaches it attached.

    `visibility` has no default. An item cannot be constructed without one, so there is no
    shape of this model that is the flattened version, and the scope predicate is derived
    from the visibility rather than stored beside it for the reason
    `brain.knowledge.item.KnowledgeItem` derives it: two fields that must agree are one
    field with a constructor, and the stored copy is the one that goes stale.
    """

    item_id: str
    title: str
    content: str
    visibility: KnowledgeVisibility
    owner_id: str
    state: KnowledgeState

    @property
    def scope(self) -> Scope:
        """The predicate deciding who reaches this. The same one the source item derives."""
        return self.visibility.scope()


def knowledge_export(items: Sequence[KnowledgeItem]) -> tuple[ExportedKnowledge, ...]:
    """Export knowledge items with their scope intact, or refuse (M25.3.3).

    The scope is not copied, it is carried: the exported item holds the source's own
    `KnowledgeVisibility` object, and the predicate is recomputed from it. Then the two
    predicates are compared before anything is returned, which is the check that catches the
    edit this leaf exists to prevent. Flattening does not look like vandalism when somebody
    writes it; it looks like `visibility=KnowledgeVisibility.company()` in a mapping
    function, added because an export was failing for a reader who lacked the department.

    Comparing rather than trusting is the same argument
    `brain.ops.canaries.compare_askers` makes: the property being asserted is about what came
    out, so it has to be read off what came out.
    """
    exported: list[ExportedKnowledge] = []
    for item in items:
        candidate = ExportedKnowledge(
            item_id=item.item_id,
            title=item.title,
            content=item.content,
            visibility=item.visibility,
            owner_id=item.owner_id,
            state=item.state,
        )
        if candidate.scope != item.scope:
            msg = (
                f"{item.item_id!r} would leave with a different scope from the one it has; "
                "see AN_EXPORT_THAT_FLATTENS_SCOPE_LAUNDERS_PERMISSION"
            )
            raise ExportError(msg)
        exported.append(candidate)
    return tuple(exported)


# ------------------------------------------------------------------ the structural checks
#: Field and parameter names that would put a count of withheld things into an export.
_WITHHELD_NAMES: frozenset[str] = frozenset(
    {
        "locked",
        "lock_count",
        "redacted",
        "redaction_count",
        "withheld",
        "hidden",
        "omitted",
        "excluded",
        "skipped",
        "total_turns",
        "ordinal",
        "sequence",
        "position",
        "turn_number",
        "message_index",
    }
)

#: Names that would let a caller take a bulk export without the row that records it.
_SUPPRESSION_NAMES: frozenset[str] = frozenset(
    {
        "audit",
        "skip_audit",
        "no_audit",
        "suppress_audit",
        "record_audit",
        "quiet",
        "silent",
        "dry_run",
    }
)


def withheld_names_on(model: type) -> tuple[str, ...]:
    """Fields on one model that would tell a reader how much they were not shown.

    Split out of `export_gaps` so it can be pointed at a model other than the four it
    guards. A scan that can only ever be run against models known to be clean has never been
    seen to produce a finding, and nobody knows whether it can; this one can be handed a
    dataclass with a `lock_count` on it and asked.
    """
    names = {f.name for f in fields(model)}
    found = sorted(names & _WITHHELD_NAMES)
    if "refs" in names:
        found.append("refs")
    return tuple(found)


#: The models a conversation export could grow a count of withheld things on.
CONVERSATION_MODELS: tuple[type, ...] = (ExportedTurn, ConversationExport)


def export_gaps(models: Sequence[type] | None = None) -> tuple[str, ...]:
    """Every way this module has started leaking, laundering or exporting unrecorded.

    Four checks, one per property the docstring argues for. Written as a scan over the
    models rather than as prose, because each of these rules dies the same way: one field
    added to a dataclass by somebody who needed it for a screen, in a change that reads as
    additive.
    """
    gaps: list[str] = []

    for model in CONVERSATION_MODELS if models is None else tuple(models):
        for forbidden in withheld_names_on(model):
            if forbidden == "refs":
                gaps.append(
                    f"{model.__name__} carries refs, and an export is never re-checked; "
                    "see AN_EXPORT_IS_NEVER_RE_CHECKED_SO_A_REFERENCE_DOES_NOT_TRAVEL"
                )
                continue
            gaps.append(
                f"{model.__name__} carries {forbidden}, which tells the reader how much "
                "they were not shown; see A_GAP_IN_A_SEQUENCE_COUNTS_WHAT_IS_MISSING"
            )

    taken = set(inspect.signature(conversation_export).parameters)
    for forbidden in sorted(taken & _WITHHELD_NAMES):
        gaps.append(
            f"conversation_export takes {forbidden}, so the function knows what was "
            "withheld and can be made to report it"
        )

    export_params = set(inspect.signature(bulk_export).parameters)
    for forbidden in sorted(export_params & _SUPPRESSION_NAMES):
        gaps.append(
            f"bulk_export takes {forbidden}, which is a way to take an export without the "
            "row that records it"
        )
    audit_field = next((f for f in fields(BulkExport) if f.name == "audit"), None)
    if audit_field is None:
        gaps.append("BulkExport has no audit row, so an export leaves no trace")
    elif "None" in str(audit_field.type) or audit_field.default is not MISSING:
        gaps.append(
            "BulkExport's audit row is optional, so there is a shape of an export that "
            "records nothing"
        )

    reason_fields = {f.name: f for f in fields(BulkExportRequest)}
    for name in ("reason", "reason_reference"):
        found = reason_fields.get(name)
        if found is None or found.default is not MISSING:
            gaps.append(
                f"BulkExportRequest can be built without {name}, so there is a bulk export "
                "nobody has to justify"
            )

    if "visibility" not in {f.name for f in fields(ExportedKnowledge)}:
        gaps.append("ExportedKnowledge does not carry a visibility, so knowledge leaves unscoped")
    return tuple(gaps)
