"""What moves: the export, the re-embed, the entity seeds and the archive."""

from __future__ import annotations

import pytest

from brain.core.entitlement import Capability
from brain.migration.carry import (
    Archive,
    CarryError,
    ConversationImport,
    EntitySeed,
    Export,
    Reparse,
    archive,
    carried_vectors,
    export_gaps,
    reparse_plan,
    seed_gaps,
)
from brain.migration.inventory import (
    Agreed,
    Catalogue,
    Decision,
    Disposition,
    Holding,
    Item,
    PermissionMapping,
    agree,
)

ALL_KINDS = frozenset(Holding)


def an_item(item_id: str = "k1", holding: Holding = Holding.KNOWLEDGE) -> Item:
    return Item(item_id=item_id, holding=holding, name=f"{item_id} the thing")


def an_agreed(*pairs: tuple[Item, Disposition]) -> Agreed:
    """A register with every item decided and nothing outstanding."""
    return agree(
        Catalogue(surveyed=ALL_KINDS, items=tuple(item for item, _ in pairs)),
        tuple(
            Decision(item_id=item.item_id, disposition=how, because="decided in the workshop")
            for item, how in pairs
        ),
        (),
    )


def an_export(item_id: str = "k1", **kw: object) -> Export:
    fields: dict[str, object] = {"item_id": item_id, "content_digest": f"sha256:{item_id}"}
    fields.update(kw)
    return Export(**fields)  # type: ignore[arg-type]


# ------------------------------------------------------------------------- the export
def test_an_export_naming_no_item_is_refused() -> None:
    """An export nothing can be matched to is content with no decision attached, which is the
    state the register exists to prevent.

    Delete this and the blank branch is unreachable."""
    with pytest.raises(CarryError, match="names no item"):
        an_export(item_id="  ")


def test_an_export_with_no_digest_is_refused() -> None:
    """The digest is of the original bytes, so a re-parse can be shown to have used what was
    handed over. Without one the re-parse is a claim.

    Delete this and an export arrives with nothing to check the re-read against."""
    with pytest.raises(CarryError, match="no digest"):
        Export(item_id="k1", content_digest=" ")


def test_a_negative_vector_count_is_refused() -> None:
    """Counted things are not negative, and `carried_vectors` tests the count for truth, so a
    negative one reports as though vectors arrived while the arithmetic behind it is wrong.

    Delete this and a subtraction upstream produces an export that reports discarded vectors
    that never existed."""
    with pytest.raises(CarryError, match="arrived with -1 vectors"):
        an_export(vector_count=-1)


def test_vectors_arriving_with_no_record_of_what_made_them_are_refused() -> None:
    """**The producing model is the one fact about a carried vector worth keeping**, because it
    is the fact that says the vector is unusable. An export that ships vectors and cannot say
    what made them reports as `''`, which reads as a formatting bug rather than as a finding.

    Delete this and `carried_vectors` prints an empty pair of quotes and the reader ignores
    the line."""
    with pytest.raises(CarryError, match="no record of what produced them"):
        an_export(vector_count=12)


def test_a_vector_width_of_zero_is_refused() -> None:
    """A width is a measurement of something that arrived. Zero is what an unset field
    serialises to, and it would sit in the record looking like a measurement.

    Delete this and an absent width and a measured one become the same value."""
    with pytest.raises(CarryError, match="vector width of 0"):
        an_export(vector_count=1, embedded_by="some-model", vector_width=0)


def test_an_export_with_vectors_and_a_producer_is_accepted() -> None:
    """The positive case. Vectors arriving is ordinary and is not an error; discarding them
    quietly is the error.

    Delete this and the guards above can be tightened until no real export is representable."""
    export = an_export(vector_count=12, embedded_by="text-embedding-3-small", vector_width=1536)

    assert export.vector_count == 12
    assert export.embedded_by == "text-embedding-3-small"


# ------------------------------------------------------- the export against the register
def test_an_item_decided_migrate_with_no_export_is_a_finding() -> None:
    """M37.1.2.1 is the export, and this is the half of it that is found the day somebody
    looks for the document.

    Delete this and a migration completes with an item everybody agreed to move and nobody
    moved."""
    agreed = an_agreed((an_item("k1"), Disposition.MIGRATE))

    assert export_gaps(agreed, ()) == ("k1: decided migrate and nothing was exported for it",)


def test_an_export_for_an_item_nobody_agreed_to_take_is_a_finding() -> None:
    """**The invisible half.** Content decided retire, arriving with everything else, while the
    register says it was retired. Nothing downstream would ever ask.

    Delete this and the export becomes the decision, which makes the whole register
    decorative."""
    agreed = an_agreed((an_item("k1"), Disposition.RETIRE))

    assert export_gaps(agreed, (an_export("k1"),)) == (
        "k1: exported and decided retire, so nobody agreed to take it",
    )


def test_an_export_for_something_not_in_the_catalogue_is_a_finding() -> None:
    """Different from the case above and it reaches a different person: this is content the
    survey never saw, so no decision about it was ever taken by anybody.

    Delete this and an exporter can add content to the migration that the catalogue does not
    know exists."""
    agreed = an_agreed((an_item("k1"), Disposition.MIGRATE))

    assert export_gaps(agreed, (an_export("k1"), an_export("k404"))) == (
        "k404: exported and not in the catalogue at all",
    )


def test_the_same_item_exported_twice_is_a_finding() -> None:
    """Two exports for one item means two sets of bytes claiming to be the same thing, and
    `reparse_plan` would re-embed both, so the corpus holds it twice and search returns it
    twice.

    Delete this and a merged export from two sources silently duplicates its overlap."""
    agreed = an_agreed((an_item("k1"), Disposition.MIGRATE))

    assert export_gaps(agreed, (an_export("k1"), an_export("k1"))) == (
        "k1: exported more than once",
    )


def test_an_export_matching_the_register_has_no_findings() -> None:
    """The positive case for all four.

    Delete this and `export_gaps` can be written to report every item."""
    agreed = an_agreed(
        (an_item("k1"), Disposition.MIGRATE),
        (an_item("p1", Holding.PROMPT), Disposition.REBUILD),
    )

    assert export_gaps(agreed, (an_export("k1"),)) == ()


# ------------------------------------------------------------ the vectors are not carried
def test_every_export_is_re_read_and_re_embedded_whatever_its_vectors_look_like() -> None:
    """**M37.1.2.2 and the rule the module exists for.** An export whose vectors are the same
    width as this install's column is the one somebody proposes carrying, because the width is the
    check the database can do, and two models of one dimension are ordinary. The plan has one
    entry per export and no shortcut, and `Reparse` has nowhere to put a vector.

    Delete this and the obvious optimisation reappears: the widths match, so carry them, and
    search returns a nearest neighbour in a space nobody is using any more.
    """
    exports = (
        an_export("k1", vector_count=40, embedded_by="another-model", vector_width=1024),
        an_export("k2"),
    )

    assert reparse_plan(exports) == (
        Reparse(item_id="k1", content_digest="sha256:k1"),
        Reparse(item_id="k2", content_digest="sha256:k2"),
    )
    assert not hasattr(Reparse(item_id="k1", content_digest="d"), "vectors")


def test_vectors_that_arrived_are_named_and_said_to_be_discarded() -> None:
    """Discarding them knowingly is the point. A silent drop is what makes the next person
    notice the widths agree and propose the shortcut.

    Delete this and an unusable artefact arrives, is thrown away and appears in no record."""
    exports = (
        an_export("k2"),
        an_export("k1", vector_count=40, embedded_by="another-model"),
    )

    assert carried_vectors(exports) == ("k1: 40 vector(s) from 'another-model', discarded",)


def test_an_export_with_no_vectors_is_not_named() -> None:
    """The positive case, and the reason the list is worth reading: it names what arrived, not
    every export.

    Delete this and `carried_vectors` can be written to name everything, which makes the
    finding invisible in its own list."""
    assert carried_vectors((an_export("k1"), an_export("k2"))) == ()


# ------------------------------------------------------------------ the entity seeds
def test_a_seed_with_no_external_id_is_refused() -> None:
    """Without the id in the system it came from, nothing can be reconciled later against the
    record it was seeded from.

    Delete this and the blank branch is unreachable."""
    with pytest.raises(CarryError, match="no id in the system"):
        EntitySeed(external_id=" ", name="Acme", source_record="clients/1")


def test_a_seed_with_no_name_is_refused() -> None:
    """A nameless entity cannot be normalised, reviewed or recognised.

    Delete this and a blank name reaches `normalise_name`, which answers "nothing left" and
    turns a broken record into a review item."""
    with pytest.raises(CarryError, match="no name"):
        EntitySeed(external_id="c1", name="", source_record="clients/1")


def test_a_seed_with_no_source_record_is_refused() -> None:
    """**An entity nobody can trace back to a record is an entity somebody typed.** The
    provenance is what makes the seed evidence rather than an assertion.

    Delete this and the registry can be seeded from a list somebody wrote in a meeting."""
    with pytest.raises(CarryError, match="names no source record"):
        EntitySeed(external_id="c1", name="Acme", source_record="   ")


def test_a_seed_has_nowhere_to_carry_the_old_system_s_access() -> None:
    """**The enforcement is the absence of a field.** The old system's client records arrive
    with its access attached, and a seed that could hold it would hold it on the day somebody
    is in a hurry. Entitlements are granted here, afterwards, by somebody deciding.

    Asserted on the type rather than on an instance, because an instance with the field unset
    is what a default produces and would pass either way.

    Delete this and a permissions field can be added with every other test still green."""
    assert set(EntitySeed.__dataclass_fields__) == {"external_id", "name", "source_record"}


def test_a_name_that_cannot_be_matched_on_reaches_a_reviewer_as_its_own_question() -> None:
    """M37.1.2.3 seeds the registry from the old system's records, and this is what a seed
    has to survive first. `brain.resolution.normalise_name` is the one implementation of what
    "the same name" means, and its verdict is carried through rather than restated here.

    Delete this and a name made only of a legal form is seeded as an entity called "Pte Ltd"
    that every later record collapses onto."""
    findings = seed_gaps((EntitySeed(external_id="c1", name="Pte Ltd", source_record="clients/1"),))

    assert len(findings) == 1
    assert findings[0].startswith("c1: entirely a suffix")


def test_two_records_that_collapse_to_one_key_are_reported_and_not_merged() -> None:
    """**Two client records with one key may be one client or two, and somebody's contract is
    on the other end of it.** Merged at seed time the decision is taken by whoever wrote the
    import, invisibly, at the point where the least is known.

    Delete this and the collision resolves silently to whichever row was read first."""
    findings = seed_gaps(
        (
            EntitySeed(external_id="c1", name="Acme Pte Ltd", source_record="clients/1"),
            EntitySeed(external_id="c2", name="ACME", source_record="crm/88"),
        )
    )

    assert findings == ("acme: seeded by c1 and c2, which is one entity or two",)


def test_seeds_that_normalise_apart_have_no_findings() -> None:
    """The positive case.

    Delete this and `seed_gaps` can report every pair of seeds as a collision."""
    findings = seed_gaps(
        (
            EntitySeed(external_id="c1", name="Acme Pte Ltd", source_record="clients/1"),
            EntitySeed(external_id="c2", name="Borealis Limited", source_record="clients/2"),
        )
    )

    assert findings == ()


# ------------------------------------------------------------------------- the archive
def test_a_conversation_import_naming_no_conversation_is_refused() -> None:
    """Delete this and the blank branch is unreachable."""
    with pytest.raises(CarryError, match="names no conversation"):
        ConversationImport(item_id="", because="the audit needs it", stated_by="u_priya")


def test_a_conversation_import_with_no_stated_reason_is_refused() -> None:
    """The leaf allows an import "unless there is a stated reason", so the reason is the whole
    of the permission.

    Delete this and every conversation can be imported by leaving a field blank."""
    with pytest.raises(CarryError, match="no stated reason"):
        ConversationImport(item_id="c1", because="  ", stated_by="u_priya")


def test_a_reason_nobody_put_their_name_to_is_refused() -> None:
    """A reason with no name on it is a sentence in a spreadsheet, and the point of a stated
    reason is that somebody stated it.

    Delete this and the reason column fills itself in from a template."""
    with pytest.raises(CarryError, match="nobody put their name to"):
        ConversationImport(item_id="c1", because="the dispute file needs it", stated_by="")


def test_an_imported_conversation_is_never_searchable() -> None:
    """**A conversation holds answers the old system produced under its own permission model**,
    for people whose reach was decided somewhere else. Imported as knowledge it answers
    questions here with content nobody's entitlements were ever checked against.

    The field exists and is always empty on purpose: the rule is then visible to a reader of
    the type rather than buried in a function nobody opens.

    Delete this and the constructor accepts a searchable import, which is the one shape of
    this record that leaks."""
    with pytest.raises(CarryError, match="would be searchable"):
        Archive(archived=("c1",), imported=(), searchable=("c1",))


def test_every_catalogued_conversation_is_archived_and_the_stated_ones_are_also_kept() -> None:
    """M37.1.2.4, the positive case, and the shape of the answer: archiving is not a choice,
    and an import is a second thing that happens to the same conversation.

    Delete this and archiving can be written as the branch taken when nothing was stated,
    which loses the history of every conversation somebody argued for."""
    agreed = an_agreed(
        (an_item("c1", Holding.CONVERSATION), Disposition.RETIRE),
        (an_item("c2", Holding.CONVERSATION), Disposition.RETIRE),
        (an_item("k1"), Disposition.MIGRATE),
    )
    kept = ConversationImport(item_id="c1", because="named in the dispute file", stated_by="u_x")

    result = archive(agreed, (kept,))

    assert result.archived == ("c1", "c2")
    assert result.imported == (kept,)
    assert result.searchable == ()


def test_an_import_naming_something_that_is_not_a_conversation_is_refused() -> None:
    """The wrong id in that list keeps a document out of retrieval under a rule written for
    conversations, and nothing anywhere would say so.

    Delete this and a mistyped id silently removes a knowledge item from search."""
    agreed = an_agreed((an_item("k1"), Disposition.MIGRATE))
    wrong = ConversationImport(item_id="k1", because="the audit asked", stated_by="u_x")

    with pytest.raises(CarryError, match="not a conversation in this catalogue"):
        archive(agreed, (wrong,))


def test_a_catalogue_with_no_conversations_archives_nothing_and_that_is_not_an_error() -> None:
    """Zero conversations is a real answer, and `brain.migration.inventory` is where the
    difference between "none" and "nobody looked" is kept.

    Delete this and `archive` can be written to require at least one."""
    agreed = an_agreed((an_item("k1"), Disposition.MIGRATE))

    assert archive(agreed).archived == ()


def test_a_permission_mapping_still_travels_with_the_register() -> None:
    """`Agreed` carries the mapping and this module reads the catalogue through it, so a
    register built with mappings is the one that arrives here.

    Delete this and nothing in this file would notice `agree` dropping its mappings."""
    agreed = agree(
        Catalogue(
            surveyed=ALL_KINDS, items=(Item("k1", Holding.KNOWLEDGE, "Policy", ("editor",)),)
        ),
        (Decision(item_id="k1", disposition=Disposition.MIGRATE, because="current"),),
        (
            PermissionMapping(
                old="editor",
                capabilities=(Capability(value="read:client.name"),),
                because="they could open every client record and nothing else",
            ),
        ),
    )

    assert export_gaps(agreed, (an_export("k1"),)) == ()
    assert agreed.capabilities_for("editor") == (Capability(value="read:client.name"),)
