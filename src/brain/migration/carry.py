"""What actually moves: the export, the re-embed, the entity seeds and the archive.

`brain.migration.inventory` decides what happens to each thing the old system holds. This is
the half that happens afterwards, and it is four separate answers because the four kinds of
content fail differently.

**A vector is the one thing that must not be carried, and the reason it gets carried anyway is
that it looks free.** Re-embedding a corpus costs money and hours; the vectors are sitting in
the export; the column here is the same width. Every one of those is true and the conclusion
is still wrong, because an embedding is only meaningful against the model that produced it.
Carried across, a vector from another model lands in a column of the right width and search
returns confident nonsense: not an error, not an empty result, a nearest neighbour that is
near in a space nobody is using any more. **A matching width is not a matching model**, and
width is the check somebody reaches for because it is the one the database can do. Two models
of the same dimension are ordinary. So `Export` records what produced its vectors, nothing
here ever reads them, and `carried_vectors` names every export that shipped some, because the
honest handling of an unusable artefact is to say it was received and discarded. See
`A_MATCHING_WIDTH_IS_NOT_A_MATCHING_MODEL`.

**An entity seed is a proposal and never a grant.** The old system's client records are the
best list of entities anybody has, and they arrive with the old system's access attached to
them. `EntitySeed` has no field for that on purpose: there is nowhere to put it, so nothing
can carry it by accident, and entitlements are granted here by `brain.identity` in the
ordinary way after somebody has decided. What the seed does carry is the record it came from,
because an entity nobody can trace back to a source record is an entity somebody typed.

Two seeds that normalise to the same key are a collision, and they are reported rather than
merged. `brain.resolution.normalise_name` is the one implementation of what "the same name"
means here, so this asks it rather than comparing strings: merging two client records because
their names collapse together is a decision with a person's contract on the other end of it,
and the whole of `brain.resolution` exists because that decision is not a string comparison.
See `TWO_RECORDS_THAT_COLLAPSE_TOGETHER_ARE_A_QUESTION_AND_NOT_A_MERGE`.

**History is archived and an import is an artefact.** A conversation from the old system holds
answers that system produced under its own permission model, so importing one as knowledge
imports content nobody's entitlements were ever checked against, and it then answers questions
here. The leaf allows an import with a stated reason, and this is what a stated reason buys:
the conversation is kept, attributed, and not searchable. `Archive.searchable` is empty by
construction and there is no parameter that fills it, which is the difference between a rule
and a default. See `AN_IMPORTED_ANSWER_WAS_NEVER_JUDGED_BY_THE_RULES_HERE`.

What was rejected. Re-parsing from the old system's extracted text rather than from its
original files. It is faster and it inherits every parsing decision the old system made,
including the ones nobody knew it was making, and the whole reason to re-parse is that those
decisions are not this system's. `Export.content_digest` is the digest of the original bytes
for that reason: a re-parse can be shown to have used what was handed over.

Nothing here opens a connection. The export arrives from a plugin and the archive is written
by a caller, and the interesting case in each is a gap, which a module holding a session
could not produce in a test.

Task ids: M37.1.2.1, M37.1.2.2, M37.1.2.3, M37.1.2.4
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from brain.migration.inventory import Agreed, Disposition, Holding, MigrationError
from brain.resolution.normalise import normalise_name

# ------------------------------------------------------------------ written-down reasons
#: Why a vector is never carried, whatever its width.
A_MATCHING_WIDTH_IS_NOT_A_MATCHING_MODEL: Final = (
    "An embedding is meaningful only against the model that produced it, and the column here "
    "cannot tell one model's vectors from another's: two models of the same dimension are "
    "ordinary. So a carried vector lands in a column of the right width and search returns a "
    "nearest neighbour in a space nobody is using any more, which is confident nonsense "
    "rather than an error or an empty result. Width is the check somebody reaches for because "
    "it is the one the database can do, and passing it proves nothing at all. Everything is "
    "re-parsed from the original bytes and re-embedded by the model this install serves."
)

#: Why two seeds that normalise together are reported rather than merged.
TWO_RECORDS_THAT_COLLAPSE_TOGETHER_ARE_A_QUESTION_AND_NOT_A_MERGE: Final = (
    "Two client records whose names collapse to one key may be one client with two rows or "
    "two clients with similar names, and the difference has somebody's contract on the other "
    "end of it. Merging them at seed time is a decision taken by whoever wrote the import, "
    "invisibly, at the point where the least is known. They are reported as a collision and "
    "brain.resolution answers the question the way it answers it for every other pair."
)

#: Why an imported conversation is not searchable.
AN_IMPORTED_ANSWER_WAS_NEVER_JUDGED_BY_THE_RULES_HERE: Final = (
    "A conversation from the old system holds answers that system produced under its own "
    "permission model, for people whose reach was decided somewhere else. Imported as "
    "knowledge it answers questions here, and what it answers with was never checked against "
    "anybody's entitlements. The leaf permits an import with a stated reason, and what the "
    "reason buys is that the conversation is kept and attributed. It does not buy retrieval."
)


class CarryError(MigrationError):
    """Raised when something would be carried across that cannot be."""


# ------------------------------------------------------- what the old system handed over
@dataclass(frozen=True)
class Export:
    """One item as it arrived, including anything about it that will not be used.

    `content_digest` is of the original bytes rather than of extracted text, so a re-parse can
    be shown to have used what was handed over. `vector_count`, `vector_width` and
    `embedded_by` are recorded and never read: an unusable artefact that arrived is worth
    saying out loud, and a field that is silently dropped is a field somebody adds a use for.
    """

    item_id: str
    content_digest: str
    vector_count: int = 0
    vector_width: int | None = None
    embedded_by: str = ""

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            msg = "an export names no item, so nothing can be carried against it"
            raise CarryError(msg)
        if not self.content_digest.strip():
            msg = f"{self.item_id!r} arrived with no digest, so no re-parse can be shown to"
            raise CarryError(msg)
        if self.vector_count < 0:
            msg = f"{self.item_id!r} arrived with {self.vector_count} vectors"
            raise CarryError(msg)
        if self.vector_count and not self.embedded_by.strip():
            msg = (
                f"{self.item_id!r} arrived with vectors and no record of what produced them, "
                "which is the one fact about them worth keeping"
            )
            raise CarryError(msg)
        if self.vector_width is not None and self.vector_width < 1:
            msg = f"{self.item_id!r} declares a vector width of {self.vector_width}"
            raise CarryError(msg)


def export_gaps(agreed: Agreed, exports: Sequence[Export]) -> tuple[str, ...]:
    """Where the export and the agreed register disagree (M37.1.2.1).

    Both directions. An item promised and not delivered is the visible half, and it is found
    the day somebody looks for it. An export for an item decided retire is the invisible half:
    it is content nobody agreed to take, arriving with everything else, and the register says
    it was retired.
    """
    exported = [one.item_id for one in exports]
    findings: list[str] = []
    for item in agreed.catalogue.items:
        carried = agreed.disposition_of(item.item_id) is Disposition.MIGRATE
        if carried and item.item_id not in exported:
            findings.append(f"{item.item_id}: decided migrate and nothing was exported for it")
        if not carried and item.item_id in exported:
            findings.append(
                f"{item.item_id}: exported and decided "
                f"{agreed.disposition_of(item.item_id).value}, so nobody agreed to take it"
            )
    known = {one.item_id for one in agreed.catalogue.items}
    findings.extend(
        f"{one}: exported and not in the catalogue at all"
        for one in sorted({one for one in exported if one not in known})
    )
    findings.extend(
        f"{one}: exported more than once"
        for one in sorted({one for one in exported if exported.count(one) > 1})
    )
    return tuple(findings)


# ------------------------------------------------------------ re-parse and re-embed (M37.1.2.2)
@dataclass(frozen=True)
class Reparse:
    """One item to be read again from its original bytes and embedded again here.

    There is no field for a carried vector, and that is the enforcement. See
    `A_MATCHING_WIDTH_IS_NOT_A_MATCHING_MODEL`.
    """

    item_id: str
    content_digest: str


def carried_vectors(exports: Sequence[Export]) -> tuple[str, ...]:
    """Every export that shipped embeddings, named with what produced them, sorted.

    Not a refusal. The export is what it is and nobody here controls it; what matters is that
    the vectors are discarded knowingly rather than quietly reused by the next person who
    notices the widths agree.
    """
    return tuple(
        f"{one.item_id}: {one.vector_count} vector(s) from {one.embedded_by!r}, discarded"
        for one in sorted(exports, key=lambda e: e.item_id)
        if one.vector_count
    )


def reparse_plan(exports: Sequence[Export]) -> tuple[Reparse, ...]:
    """Every export, to be re-read and re-embedded, in export order.

    Every one, with no shortcut for an export whose vector width matches this column. That
    shortcut is the defect this module is about and it is the one a reader will propose.
    """
    return tuple(Reparse(item_id=one.item_id, content_digest=one.content_digest) for one in exports)


# --------------------------------------------------------- seeding the registry (M37.1.2.3)
@dataclass(frozen=True)
class EntitySeed:
    """One entity proposed from an old client record.

    There is deliberately no field for what the old system let anybody see. Entitlements are
    granted here, by `brain.identity`, after somebody decides. A seed that could carry access
    is a seed that carries it by default on the day somebody is in a hurry.
    """

    external_id: str
    name: str
    source_record: str

    def __post_init__(self) -> None:
        if not self.external_id.strip():
            msg = "an entity seed has no id in the system it came from"
            raise CarryError(msg)
        if not self.name.strip():
            msg = f"{self.external_id!r} seeds an entity with no name"
            raise CarryError(msg)
        if not self.source_record.strip():
            msg = (
                f"{self.external_id!r} names no source record, so it is an entity somebody "
                "typed rather than one the old system held"
            )
            raise CarryError(msg)


def seed_gaps(seeds: Sequence[EntitySeed]) -> tuple[str, ...]:
    """Seeds a person has to look at before any of them becomes an entity (M37.1.2.3).

    Two kinds. A name `brain.resolution.normalise_name` will not match on reaches a reviewer
    as its own question, and the verdict is carried through rather than restated. Two seeds
    that collapse to one key are a collision and are reported rather than merged, for the
    reason in `TWO_RECORDS_THAT_COLLAPSE_TOGETHER_ARE_A_QUESTION_AND_NOT_A_MERGE`.
    """
    findings: list[str] = []
    keyed: dict[str, list[str]] = {}
    for one in seeds:
        normalised = normalise_name(one.name)
        key = normalised.match_key
        if key is None:
            findings.append(f"{one.external_id}: {normalised.verdict.value}, {normalised.reason}")
            continue
        keyed.setdefault(key, []).append(one.external_id)
    findings.extend(
        f"{key}: seeded by {' and '.join(sorted(ids))}, which is one entity or two"
        for key, ids in sorted(keyed.items())
        if len(ids) > 1
    )
    return tuple(findings)


# ----------------------------------------------------------- history is archived (M37.1.2.4)
@dataclass(frozen=True)
class ConversationImport:
    """A stated reason for keeping one conversation, and who stated it.

    Both are required. "There is a stated reason" is the leaf's wording and a reason with
    nobody's name on it is a sentence in a spreadsheet.
    """

    item_id: str
    because: str
    stated_by: str

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            msg = "a conversation import names no conversation"
            raise CarryError(msg)
        if not self.because.strip():
            msg = f"{self.item_id!r} is imported with no stated reason"
            raise CarryError(msg)
        if not self.stated_by.strip():
            msg = f"{self.item_id!r} is imported for a reason nobody put their name to"
            raise CarryError(msg)


@dataclass(frozen=True)
class Archive:
    """What happens to the old system's history.

    `searchable` is a field that is always empty, and that is the point rather than an
    oversight: it makes the rule visible to a reader of the type instead of leaving it in a
    function nobody opens. See `AN_IMPORTED_ANSWER_WAS_NEVER_JUDGED_BY_THE_RULES_HERE`.
    """

    archived: tuple[str, ...]
    imported: tuple[ConversationImport, ...]
    searchable: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.searchable:
            msg = (
                f"{len(self.searchable)} imported conversation(s) would be searchable. "
                f"{AN_IMPORTED_ANSWER_WAS_NEVER_JUDGED_BY_THE_RULES_HERE}"
            )
            raise CarryError(msg)


def archive(agreed: Agreed, imports: Sequence[ConversationImport] = ()) -> Archive:
    """Every catalogued conversation, archived, with the stated ones also kept as artefacts.

    An import for something that is not a conversation is refused rather than ignored, because
    the wrong id in that list is a document being kept out of retrieval by a rule written for
    conversations, and nothing would ever say so.
    """
    conversations = [
        one.item_id for one in agreed.catalogue.items if one.holding is Holding.CONVERSATION
    ]
    for one in imports:
        if one.item_id not in conversations:
            msg = f"{one.item_id!r} is not a conversation in this catalogue"
            raise CarryError(msg)
    return Archive(archived=tuple(conversations), imported=tuple(imports))
