"""Merging, held to the permission event it is rather than to the rows it moves.

Four groups. The money boundary is the sharpest, because it is the one where a merge hands a
department somebody's contract value and every part of it looks like an improvement. The
pointer move is next, and it is tested as an absence: there is nowhere in the outcome to put a
rewritten source record. Then the pre-image and the unmerge, which are one property and are
tested as one, including the case a recompute gets wrong. Then the invalidation, which is
tested on the id nobody was asking with.

Every refusal here has a sibling proving an ordinary merge still happens. A merge function that
refused everything would satisfy the money tests, the pointer tests and the audit tests, and
would be useless.

Task ids: M14.5.1, M14.5.2, M14.5.3, M14.5.4, M14.5.5, M14.5.6
"""

from __future__ import annotations

import importlib.util
import inspect
from dataclasses import MISSING, replace
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime

import pytest

from brain.memory.tiers import BLAST_RADIUS, CHANGES_WHAT_ANYBODY_MAY_SEE, Change, Tier
from brain.resolution.canonical import (
    Alias,
    CanonicalEntity,
    EntityType,
    Identifier,
    IdentifierKind,
    Link,
    ResolutionError,
    SourceRef,
    current_id,
)
from brain.resolution.cascade import CascadeResult, Decision, Feature, Observation, Stage, cascade
from brain.resolution.guardrails import Evidence, review_queue
from brain.resolution.merge import (
    ENTITIES_WRITTEN_BY_ONE_MERGE,
    FIELDS_WRITTEN_BY_ONE_MERGE,
    MONEY_ANSWERS_THAT_ADMIT_AN_AUTOMATIC_MERGE,
    MONEY_ANSWERS_THAT_REFUSE_AN_AUTOMATIC_MERGE,
    SURFACE_MODULES,
    AutomaticMerge,
    InvalidatedSurface,
    Invalidation,
    MergeAudit,
    MergeOutcome,
    MoneyBearing,
    MoneyCheck,
    PreImage,
    Restoration,
    ReviewedMerge,
    capture_pre_image,
    invalidations_for,
    merge,
    merge_gaps,
    money_review_item,
    unmerge,
)
from brain.resolution.normalise import normalise_name

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 8, 9, 30, tzinfo=UTC)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64

#: The one name both sides observed, which is the case a recompute cannot untangle.
SHARED_NAME = "Kandang Kerbau Holdings Pte Ltd"

NO_MONEY = MoneyCheck(
    left=MoneyBearing.NO_FINANCIAL_RECORDS_FOUND, right=MoneyBearing.NO_FINANCIAL_RECORDS_FOUND
)


def source(name: str = "freshdesk", record: str = "1") -> SourceRef:
    return SourceRef(source=name, entity="company", source_id=record)


def entity(entity_id: str, *, entity_type: EntityType = EntityType.COMPANY) -> CanonicalEntity:
    return CanonicalEntity(
        entity_id=entity_id,
        entity_type=entity_type,
        created_at=NOW,
        created_by="a-backfill",
        created_from=source(record=entity_id),
    )


def matched_result() -> CascadeResult:
    """A real cascade match, so an automatic merge is built from what the cascade produced."""
    left = Observation(
        record=source("freshdesk", "1"),
        name=normalise_name("Acme Trading Pte Ltd"),
        identifiers={IdentifierKind.UEN: DIGEST_A},
    )
    right = Observation(
        record=source("xero", "2"),
        name=normalise_name("Acme Trading Pte Ltd"),
        identifiers={IdentifierKind.UEN: DIGEST_A},
    )
    result = cascade(left, right)
    assert result.decision is Decision.MATCHED
    return result


def automatic(money: MoneyCheck = NO_MONEY) -> AutomaticMerge:
    return AutomaticMerge(decision=matched_result(), money=money, performed_by="resolver-job")


def reviewed(money: MoneyCheck = NO_MONEY) -> ReviewedMerge:
    return ReviewedMerge(
        reviewer_id="rupash",
        review_ref="rev-2026-09-07-11",
        money=money,
        evidence=(Evidence(field="uen", weight=10.0),),
    )


# --------------------------------------------------- the money boundary (M14.5.6)
def test_an_entity_carrying_money_is_never_merged_automatically_at_any_confidence() -> None:
    """**The refusal is a constructor and not a threshold, so there is no figure to raise.**

    Merging two entities merges two permission surfaces, and when one carries financial records
    the surface being widened is somebody's contract value. Being more certain the two records
    are one client does not bound that exposure: the confidence is a belief about identity and
    the exposure is a fact about access.

    Tested at the highest confidence the system can express, which is the stage-one match a
    hard identifier produces, because that is the value somebody wanting an exception would
    reach for. The refusal does not read it.

    Delete this and the money rule can become `if money and confidence < 0.99`, which reads as
    a reasonable tuning change and hands a department a client's contract value."""
    certain = matched_result()
    assert certain.stage is Stage.HARD_IDENTIFIER
    assert certain.confidence == 1.0

    for money in (
        MoneyCheck(
            left=MoneyBearing.CARRIES_FINANCIAL_RECORDS,
            right=MoneyBearing.NO_FINANCIAL_RECORDS_FOUND,
        ),
        MoneyCheck(
            left=MoneyBearing.NO_FINANCIAL_RECORDS_FOUND,
            right=MoneyBearing.CARRIES_FINANCIAL_RECORDS,
        ),
    ):
        with pytest.raises(ResolutionError):
            AutomaticMerge(decision=certain, money=money, performed_by="resolver-job")

    admitted = AutomaticMerge(decision=certain, money=NO_MONEY, performed_by="resolver-job")
    assert admitted.confidence == 1.0


def test_the_automatic_path_has_no_parameter_a_money_override_could_arrive_through() -> None:
    """The structural half: "auto-merge with money above 0.99" is not an expression.

    The behaviour test above proves the refusal fires. This proves there is nowhere to write
    the exception: `AutomaticMerge` has three fields, none of them a threshold, an override or
    a force flag, and it has no confidence field at all because the confidence is read off a
    cascade result that had to be a match.

    Delete this and a `minimum_confidence` field appears on the automatic path, defaulted to
    something reassuring, and the constructor refusal becomes a comparison."""
    names = {one.name for one in dataclass_fields(AutomaticMerge)}
    assert names == {"decision", "money", "performed_by"}

    forbidden = ("threshold", "override", "force", "confidence", "minimum", "allow")
    for name in names:
        assert not any(word in name for word in forbidden), name

    parameters = set(inspect.signature(merge).parameters)
    for name in parameters:
        assert not any(word in name for word in forbidden), name


def test_a_money_answer_nobody_gave_refuses_exactly_as_money_itself_does() -> None:
    """**A boolean has no way to say that nobody looked, and False is what it says instead.**

    A caller who has not wired up the financial connector passes False on every entity in the
    estate, the guard is off everywhere, and nothing reports it. `NOT_CHECKED` is a member, and
    it refuses.

    The positive half is that a checked answer of "no money" is admitted, without which a type
    that refused every merge would pass.

    Delete this and `MoneyBearing` can be replaced by a boolean, which is the change that looks
    like simplification and turns the sharpest guard in the package off by default."""
    unchecked = MoneyCheck(left=MoneyBearing.NOT_CHECKED, right=MoneyBearing.NOT_CHECKED)
    assert unchecked.permits_automatic is False

    with pytest.raises(ResolutionError):
        AutomaticMerge(decision=matched_result(), money=unchecked, performed_by="resolver-job")

    assert MoneyBearing.NOT_CHECKED in MONEY_ANSWERS_THAT_REFUSE_AN_AUTOMATIC_MERGE
    assert MoneyBearing.NOT_CHECKED not in MONEY_ANSWERS_THAT_ADMIT_AN_AUTOMATIC_MERGE
    assert NO_MONEY.permits_automatic is True


def test_a_person_may_merge_across_the_money_boundary_and_is_named_for_it() -> None:
    """The rule is that nothing merges money unattended, not that money can never be merged.

    A reviewed merge carries the money answers and does not check them, and the audit records
    who decided and which review they decided it from. That is the whole difference between the
    two authorities, and without this test the money rule would read as a prohibition and the
    system would have no way to merge a real client with an invoice.

    Delete this and the reviewed path grows the automatic path's refusal, and two records for
    one paying client can never be joined by anybody."""
    carries = MoneyCheck(
        left=MoneyBearing.CARRIES_FINANCIAL_RECORDS,
        right=MoneyBearing.CARRIES_FINANCIAL_RECORDS,
    )
    authority = reviewed(carries)

    graph = {"e1": entity("e1"), "e2": entity("e2")}
    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=authority,
        at=NOW,
        merge_id="mg-1",
        reason="the finance team confirmed one client",
    )

    assert outcome.audit.decided_by == "rupash"
    assert outcome.audit.automatic is False
    assert outcome.audit.confidence is None
    assert outcome.merged.merged_into == "e1"


def test_a_pair_the_money_boundary_refused_reaches_a_person_through_the_queue() -> None:
    """A rule that refuses and offers nowhere to go is a rule somebody deletes.

    `cascade.CascadeResult.review_item` refuses anything the cascade decided, and a
    money-blocked pair is decided by that test: the cascade settled the identity question. So
    the routing needs its own door, and it opens onto `guardrails.review_queue`, which is where
    the reach filter lives. Nothing here filters by reach, and the reviewer who reaches only one
    of the two records is not shown the item at all.

    Both refusals matter. A pair the money answers would have admitted has nothing to review,
    and a pair the cascade did not match was not stopped by money.

    Delete this and M14.5.6 becomes a wall with no gate, and the first queue of real clients
    that stops resolving is the argument for taking the wall down."""
    carries = MoneyCheck(
        left=MoneyBearing.CARRIES_FINANCIAL_RECORDS,
        right=MoneyBearing.NO_FINANCIAL_RECORDS_FOUND,
    )
    result = matched_result()
    item = money_review_item(result, carries, item_id="rev-money-1")

    assert item.left == result.left
    assert item.right == result.right
    assert item.evidence == result.evidence

    reaches_one = review_queue(
        [item], reviewer_id="alice", reaches=lambda member: member.source == "freshdesk"
    )
    assert reaches_one.items == ()
    reaches_both = review_queue([item], reviewer_id="rupash", reaches=lambda member: True)
    assert reaches_both.items == (item,)

    with pytest.raises(ResolutionError):
        money_review_item(result, NO_MONEY, item_id="rev-money-2")

    queued = cascade(
        Observation(record=source("freshdesk", "1"), name=normalise_name("Peters")),
        Observation(record=source("xero", "2"), name=normalise_name("Peterson")),
    )
    with pytest.raises(ResolutionError):
        money_review_item(queued, carries, item_id="rev-money-3")


def test_the_money_rule_agrees_with_the_tier_the_learning_system_puts_it_at() -> None:
    """The rule is anchored to another module's classification rather than to its own wording.

    `brain.memory.tiers` already classifies `Change.MONEY_BOUNDARY_MERGE` as `Tier.GATED` and
    lists it among the changes that alter who may see what. Gated means a person decides, and
    this module is where that classification becomes a shape. Asserting the two agree is what
    makes the rule anchored to something outside itself: if the tier were lowered, or the
    refusal here removed, the two halves of the system would be saying different things about
    the same event and one of them would be wrong in production.

    Delete this and the two can drift, and the console can show a money-boundary merge as
    automatic while the resolver refuses it, or the other way round."""
    assert BLAST_RADIUS[Change.MONEY_BOUNDARY_MERGE] is Tier.GATED
    assert Change.MONEY_BOUNDARY_MERGE in CHANGES_WHAT_ANYBODY_MAY_SEE

    carries = MoneyCheck(
        left=MoneyBearing.CARRIES_FINANCIAL_RECORDS,
        right=MoneyBearing.NO_FINANCIAL_RECORDS_FOUND,
    )
    assert carries.permits_automatic is False


def test_a_pair_the_cascade_did_not_match_cannot_be_merged_automatically() -> None:
    """The automatic path carries a cascade result, so there is no number to invent.

    A caller reading `confidence` off a `TO_REVIEW` result and passing it as a float would have
    merged a pair the cascade handed to a person. There is no float parameter, and the result
    it does take is refused unless the decision is MATCHED.

    Delete this and the automatic path takes a number again, and the review band stops meaning
    anything the moment somebody writes a loop over candidates."""
    queued = cascade(
        Observation(record=source("freshdesk", "1"), name=normalise_name("Peters")),
        Observation(record=source("xero", "2"), name=normalise_name("Peterson")),
    )
    assert queued.decision is Decision.TO_REVIEW

    with pytest.raises(ResolutionError):
        AutomaticMerge(decision=queued, money=NO_MONEY, performed_by="resolver-job")

    assert (
        AutomaticMerge(
            decision=matched_result(), money=NO_MONEY, performed_by="resolver-job"
        ).decision.decision
        is Decision.MATCHED
    )


def test_the_gap_detector_reports_a_money_answer_that_admits_an_automatic_merge() -> None:
    """M14.5.6 inverted is one set membership, and the detector has to be able to see it.

    Both sets are parameters, which is the only way a test can hand the detector tables that
    disagree. A detector that only fires when the tables disagree returns nothing on a healthy
    tree whether or not it is still doing anything, which is the defect
    `guardrails.guardrail_gaps` records finding in itself.

    Three shapes: money on the admitting side, a member on neither side, and a member on both.

    Delete this and the two sets can be edited into agreement with each other and disagreement
    with the leaf, and nothing anywhere reports it."""
    assert merge_gaps() == ()

    inverted = frozenset(
        {MoneyBearing.NO_FINANCIAL_RECORDS_FOUND, MoneyBearing.CARRIES_FINANCIAL_RECORDS}
    )
    gaps = merge_gaps(admitting=inverted)
    assert any("M14.5.6 inverted" in gap for gap in gaps)

    undecided = merge_gaps(refusing=frozenset({MoneyBearing.CARRIES_FINANCIAL_RECORDS}))
    assert any("neither side" in gap for gap in undecided)

    both = merge_gaps(admitting=frozenset(MoneyBearing), refusing=frozenset(MoneyBearing))
    assert any("both admits and refuses" in gap for gap in both)


# --------------------------------------------- a pointer move and nothing else (M14.5.2)
def test_a_merge_writes_one_pointer_and_leaves_every_other_field_the_object_it_was() -> None:
    """**The source system's record is not ours to edit, and this counts what was written.**

    A merge changes which records are gathered under one id, never what any of them says. The
    check is a field-by-field difference between the entity as the pre-image captured it and
    the entity the outcome writes, and the difference has to be exactly the two halves of the
    forwarding pointer. Every other field is asserted to be the same object, not merely an
    equal one, so a merge that rebuilt a value would fail here.

    Delete this and a merge can start writing a name, a timestamp or a provenance field onto
    the entity it merges, and the audit question "what did this look like before" loses its
    answer."""
    graph = {"e1": entity("e1"), "e2": entity("e2")}
    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=automatic(),
        at=NOW,
        merge_id="mg-1",
    )

    before = outcome.pre_image.merged
    after = outcome.merged
    changed = {
        field.name
        for field in dataclass_fields(CanonicalEntity)
        if getattr(before, field.name) != getattr(after, field.name)
    }

    assert changed == FIELDS_WRITTEN_BY_ONE_MERGE
    assert "merged_into" in FIELDS_WRITTEN_BY_ONE_MERGE
    assert "merged_at" in FIELDS_WRITTEN_BY_ONE_MERGE
    assert len(FIELDS_WRITTEN_BY_ONE_MERGE) == 2
    for field in dataclass_fields(CanonicalEntity):
        if field.name not in changed:
            assert getattr(before, field.name) is getattr(after, field.name), field.name


def test_a_merge_outcome_has_nowhere_to_put_a_rewritten_source_record() -> None:
    """The absence is the guard, because a rule about not rewriting rows is a rule to forget.

    `MergeOutcome` carries one changed entity, the pre-image, the audit and the invalidations.
    There is no field for a link, an alias, an identifier or a source record outside the
    pre-image, and no survivor either, because a merge does not change the surviving entity and
    handing it back would invite a caller to write a row that had not changed.

    Counted as well as named, so "one entity is written" is a figure rather than a sentence.

    Delete this and a `links` field appears on the outcome because a caller found it
    convenient, and the next author writes them back."""
    names = {one.name for one in dataclass_fields(MergeOutcome)}
    assert names == {"merged", "pre_image", "audit", "invalidations"}
    assert "survivor" not in names

    entities_written = sum(
        1
        for field in dataclass_fields(MergeOutcome)
        if field.type in {"CanonicalEntity", CanonicalEntity}
    )
    assert entities_written == ENTITIES_WRITTEN_BY_ONE_MERGE


def test_the_links_aliases_and_identifiers_that_go_in_come_out_untouched() -> None:
    """A merge rewrites no child row, and the same objects prove it rather than equal ones.

    `er.alias`, `er.identifier` and `er.link` go on naming the entity they were attached to.
    That is what makes an id issued before a merge still resolve, and it is what gives an
    unmerge something to restore from.

    Delete this and the child rows can be repointed at the survivor, which is faster to read
    and destroys the only copy of where each row came from."""
    graph = {"e1": entity("e1"), "e2": entity("e2")}
    link = Link(entity_id="e2", source=source("xero", "9"), confidence=0.9, linked_at=NOW)
    alias = Alias(entity_id="e2", name=SHARED_NAME, source=source("xero", "9"), first_seen_at=NOW)
    identifier = Identifier(
        entity_id="e2",
        kind=IdentifierKind.UEN,
        key_hash=DIGEST_A,
        source=source("xero", "9"),
        first_seen_at=NOW,
    )

    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=automatic(),
        at=NOW,
        merge_id="mg-1",
        links=[link],
        aliases=[alias],
        identifiers=[identifier],
    )

    assert outcome.pre_image.links[0] is link
    assert outcome.pre_image.aliases[0] is alias
    assert outcome.pre_image.identifiers[0] is identifier
    assert link.entity_id == "e2"
    assert alias.entity_id == "e2"
    assert identifier.entity_id == "e2"


def test_an_id_issued_before_a_merge_resolves_to_the_survivor_after_it() -> None:
    """The positive half of the pointer move, checked through `canonical` rather than restated.

    A merge that wrote a pointer nothing could follow would pass every test above: they check
    what was not written. This checks that the one thing that was written does its job, using
    the resolution function that already exists rather than a second walk written here.

    Delete this and a merge can write a pointer to an id that does not resolve, and the tests
    about what a merge does not change would all still pass."""
    graph = {"e1": entity("e1"), "e2": entity("e2")}
    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=automatic(),
        at=NOW,
        merge_id="mg-1",
    )

    after = {**graph, "e2": outcome.merged}
    assert current_id("e2", after) == "e1"
    assert current_id("e1", after) == "e1"
    assert outcome.merged.is_current is False


def test_a_merge_that_would_leave_the_graph_unrecoverable_is_refused() -> None:
    """Four shapes, and each is a graph an unmerge could not put back.

    Merging an entity into itself is a one-hop cycle. Merging into a stub resolves past the
    entity the audit names. Merging a stub writes a second pointer over the first and destroys
    an earlier merge, leaving that merge's pre-image describing a graph that no longer exists.
    Merging two types gives every one of the loser's records the survivor's type.

    The positive half is at the end, and without it a merge function that refused everything
    would pass this test.

    Delete this and a resolver walking a candidate list merges a stub into its own survivor,
    and the first unmerge anybody attempts restores a state two merges old."""
    merged_away = replace(entity("e3"), merged_into="e1", merged_at=NOW)
    graph = {
        "e1": entity("e1"),
        "e2": entity("e2"),
        "e3": merged_away,
        "p1": entity("p1", entity_type=EntityType.PERSON),
    }

    def attempt(survivor: str, merged: str) -> MergeOutcome:
        return merge(
            survivor_id=survivor,
            merged_id=merged,
            entities=graph,
            authority=automatic(),
            at=LATER,
            merge_id="mg-1",
        )

    for survivor, merged in (("e1", "e1"), ("e3", "e2"), ("e1", "e3"), ("e1", "p1")):
        with pytest.raises(ResolutionError):
            attempt(survivor, merged)

    with pytest.raises(ResolutionError):
        merge(
            survivor_id="e1",
            merged_id="missing",
            entities=graph,
            authority=automatic(),
            at=LATER,
            merge_id="mg-1",
        )

    assert attempt("e1", "e2").merged.merged_into == "e1"


# ------------------------------------- the pre-image and the unmerge are one (M14.5.1, M14.5.3)
def test_a_merge_followed_by_an_unmerge_returns_exactly_the_pre_image() -> None:
    """**Including the case the two entities shared an alias, which is what a recompute loses.**

    Two systems holding one client usually hold one name for it, so a shared observed name is
    the ordinary case. A recompute keyed on the name sees one name and cannot say which of the
    two rows belonged to which entity; a recompute that gathers the family attaches both to the
    survivor. The restoration hands back two rows with two sources and two entity ids, and they
    are the same objects the pre-image captured rather than equal ones.

    The entities come back too, with the loser's pointer cleared, because it was captured
    before the pointer was written and restoring means giving that object back.

    Delete this and an unmerge can start recomputing, and the first merge of two records that
    shared a name becomes irreversible with nothing reporting it."""
    graph = {"e1": entity("e1"), "e2": entity("e2")}
    left_alias = Alias(
        entity_id="e1", name=SHARED_NAME, source=source("freshdesk", "1"), first_seen_at=NOW
    )
    right_alias = Alias(
        entity_id="e2", name=SHARED_NAME, source=source("xero", "9"), first_seen_at=NOW
    )
    links = [
        Link(entity_id="e1", source=source("freshdesk", "1"), confidence=1.0, linked_at=NOW),
        Link(entity_id="e2", source=source("xero", "9"), confidence=0.9, linked_at=NOW),
    ]
    identifiers = [
        Identifier(
            entity_id="e1",
            kind=IdentifierKind.UEN,
            key_hash=DIGEST_A,
            source=source("freshdesk", "1"),
            first_seen_at=NOW,
        ),
        Identifier(
            entity_id="e2",
            kind=IdentifierKind.UEN,
            key_hash=DIGEST_A,
            source=source("xero", "9"),
            first_seen_at=NOW,
        ),
    ]

    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=automatic(),
        at=NOW,
        merge_id="mg-1",
        links=links,
        aliases=[left_alias, right_alias],
        identifiers=identifiers,
    )

    after_merge = {**graph, "e2": outcome.merged}
    restored = unmerge(
        outcome.pre_image,
        entities=after_merge,
        merge_id=outcome.audit.merge_id,
        unmerge_id="un-1",
        at=LATER,
        performed_by="rupash",
        reason="the finance team said these are two clients",
    )

    assert restored.aliases == outcome.pre_image.aliases
    assert restored.links == outcome.pre_image.links
    assert restored.identifiers == outcome.pre_image.identifiers
    for restored_row, captured in zip(restored.aliases, outcome.pre_image.aliases, strict=True):
        assert restored_row is captured

    # The shared alias, restored as two rows rather than one: one observed name, two entities.
    assert len(restored.aliases) == 2
    assert {one.name for one in restored.aliases} == {SHARED_NAME}
    assert {one.entity_id for one in restored.aliases} == {"e1", "e2"}
    assert {one.source for one in restored.aliases} == {
        source("freshdesk", "1"),
        source("xero", "9"),
    }

    restored_by_id = {one.entity_id: one for one in restored.entities}
    assert restored_by_id["e2"] is outcome.pre_image.merged
    assert restored_by_id["e2"].merged_into == ""
    assert restored_by_id["e2"].merged_at is None
    assert current_id("e2", {**after_merge, "e2": restored_by_id["e2"]}) == "e2"


def test_the_unmerge_has_no_parameter_a_current_row_could_arrive_through() -> None:
    """The structural half: recomputing is not declined, it has no inputs.

    `unmerge` takes the pre-image and the entity graph. There is no `links`, `aliases` or
    `identifiers` parameter, so a version of this function that walked the current rows and
    worked out where they belonged could not be written without changing the signature, which
    is visible in review. That is `guardrails.unresolved_for`'s construction applied to a
    different failure.

    `entities` is present for exactly one purpose and the test below proves it is used for
    that and nothing else.

    Delete this and a `current_aliases` parameter appears as an optimisation, and the shared
    alias case is lost the first time somebody prefers the fresher data."""
    parameters = set(inspect.signature(unmerge).parameters)

    assert parameters == {
        "pre_image",
        "entities",
        "merge_id",
        "unmerge_id",
        "at",
        "performed_by",
        "reason",
    }
    for name in ("links", "aliases", "identifiers", "rows", "current"):
        assert name not in parameters

    restoration_fields = {one.name for one in dataclass_fields(Restoration)}
    assert restoration_fields == {
        "entities",
        "links",
        "aliases",
        "identifiers",
        "audit",
        "invalidations",
    }


def test_an_unmerge_refuses_to_reverse_a_merge_that_is_not_the_one_in_force() -> None:
    """Clearing a pointer somebody else wrote restores a state two merges ago.

    The pre-image describes one merge. If the entity has since been merged somewhere else, or
    is no longer in the graph at all, reversing from this pre-image would undo a merge it does
    not describe and leave the graph in a state nothing recorded.

    The positive half is the ordinary reversal, without which a function that refused every
    unmerge would pass.

    Delete this and an unmerge run twice, or run against a graph that moved on, silently
    rewrites a merge nobody asked about."""
    graph = {"e1": entity("e1"), "e2": entity("e2"), "e3": entity("e3")}
    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=automatic(),
        at=NOW,
        merge_id="mg-1",
    )

    elsewhere = {**graph, "e2": replace(entity("e2"), merged_into="e3", merged_at=LATER)}
    with pytest.raises(ResolutionError):
        unmerge(
            outcome.pre_image,
            entities=elsewhere,
            merge_id="mg-1",
            unmerge_id="un-1",
            at=LATER,
            performed_by="rupash",
            reason="wrong graph",
        )

    with pytest.raises(ResolutionError):
        unmerge(
            outcome.pre_image,
            entities={"e1": entity("e1")},
            merge_id="mg-1",
            unmerge_id="un-1",
            at=LATER,
            performed_by="rupash",
            reason="entity is gone",
        )

    in_force = {**graph, "e2": outcome.merged}
    restored = unmerge(
        outcome.pre_image,
        entities=in_force,
        merge_id="mg-1",
        unmerge_id="un-1",
        at=LATER,
        performed_by="rupash",
        reason="two clients after all",
    )
    assert restored.audit.restored_id == "e2"


def test_the_pre_image_covers_the_whole_family_and_not_just_the_two_entities() -> None:
    """Either side may already be a survivor, and its rows still name the entity they were on.

    A merge rewrites nothing, so an alias written against an entity that was merged away three
    weeks ago still names that entity. Capturing only rows naming the two ids in the merge
    would miss it, and the unmerge would restore an entity with a hole in it.

    `canonical.family_of` is the walk, imported rather than repeated, so there is one rule for
    what an entity's rows are.

    Delete this and the pre-image quietly stops covering the rows of any entity that was merged
    before, which is every entity the system has ever merged twice."""
    already_merged = replace(entity("e0"), merged_into="e1", merged_at=NOW)
    graph = {"e0": already_merged, "e1": entity("e1"), "e2": entity("e2")}
    old_alias = Alias(
        entity_id="e0",
        name="Acme Trading Pte Ltd",
        source=source("hubspot", "7"),
        first_seen_at=NOW,
    )
    other_alias = Alias(
        entity_id="e9", name="Somebody Else Ltd", source=source("hubspot", "8"), first_seen_at=NOW
    )

    pre_image = capture_pre_image(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        aliases=[old_alias, other_alias],
    )

    assert old_alias in pre_image.aliases
    assert other_alias not in pre_image.aliases
    assert "e0" in pre_image.entity_ids


def test_a_merge_cannot_be_produced_without_the_pre_image_it_would_be_reversed_from() -> None:
    """M14.5.1 as a required field, which is what "before any change" means for a pure function.

    A merge whose pre-image was optional would be produced without one on the path where
    somebody was in a hurry, and that merge is the one nobody can undo. The field is required,
    so there is no `MergeOutcome` without a `PreImage`, and the outcome's own checks tie the
    pointer it writes to the audit that explains it.

    Delete this and the pre-image becomes an optional extra, defaulted to empty, and the
    unmerge has nothing to restore from for exactly the merges nobody watched."""
    required = {
        one.name
        for one in dataclass_fields(MergeOutcome)
        if one.default is MISSING and one.default_factory is MISSING
    }
    assert "pre_image" in required
    assert required == {"merged", "pre_image", "audit", "invalidations"}

    graph = {"e1": entity("e1"), "e2": entity("e2")}
    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=automatic(),
        at=NOW,
        merge_id="mg-1",
    )
    assert isinstance(outcome.pre_image, PreImage)

    with pytest.raises(ResolutionError):
        MergeOutcome(
            merged=replace(entity("e2"), merged_into="e1", merged_at=NOW),
            pre_image=outcome.pre_image,
            audit=MergeAudit(
                merge_id="mg-1",
                survivor_id="e9",
                merged_id="e2",
                decided_at=NOW,
                authority=automatic(),
            ),
            invalidations=(),
        )


# --------------------------------------------------------- the audit (M14.5.4)
def test_the_audit_names_who_merged_when_and_on_what_evidence() -> None:
    """Three questions, and the evidence half is the one a pointer and a timestamp do not cover.

    Who is read off the authority rather than passed beside it, so an audit cannot name
    somebody the authority does not. The evidence is `guardrails.Evidence`, which has a field
    name and a weight and nowhere to put what the field said, so a merge audit is readable by
    an auditor without being a copy of the two records.

    Delete this and the audit becomes a pointer and a timestamp, which is exactly what
    `canonical.NOTHING_HERE_RECORDS_WHO_MERGED_OR_ON_WHAT_EVIDENCE` says was missing."""
    graph = {"e1": entity("e1"), "e2": entity("e2")}
    authority = automatic()
    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=authority,
        at=NOW,
        merge_id="mg-1",
        reason="both records carry the same uen",
    )

    audit = outcome.audit
    assert audit.decided_by == "resolver-job"
    assert audit.decided_at == NOW
    assert audit.evidence == authority.decision.evidence
    assert audit.evidence
    assert audit.reason
    assert audit.automatic is True
    assert {one.name for one in dataclass_fields(Evidence)} == {"field", "weight"}


def test_an_automatic_merge_with_no_evidence_cannot_be_built() -> None:
    """A merge nobody can explain afterwards, which is the half M14.5.4 asks for.

    A pointer and a timestamp say that something happened. The evidence says why, and it is the
    only part an auditor asking "should this have happened" can use.

    The positive half is that a real cascade result carries evidence, so the requirement costs
    a caller nothing they do not already have.

    Delete this and the automatic path can merge on a result with an empty evidence tuple, and
    the audit trail records a decision with no reasoning attached."""
    real = matched_result()
    assert real.evidence

    stripped = replace(real, evidence=())
    with pytest.raises(ResolutionError):
        AutomaticMerge(decision=stripped, money=NO_MONEY, performed_by="resolver-job")


def test_an_unmerge_is_recorded_with_a_person_and_a_reason() -> None:
    """An entity coming back with nobody's name on it is the audit question in reverse.

    The merge was recorded with its evidence. An unmerge that recorded neither who nor why
    would leave a graph where an entity reappeared and nothing said it was deliberate, and the
    obvious reading of that is a bug.

    Delete this and an unmerge can be run anonymously, and the merge audit becomes a record of
    something that may or may not still be true."""
    graph = {"e1": entity("e1"), "e2": entity("e2")}
    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=automatic(),
        at=NOW,
        merge_id="mg-1",
    )
    in_force = {**graph, "e2": outcome.merged}

    for performed_by, reason in (("", "a reason"), ("rupash", "   ")):
        with pytest.raises(ResolutionError):
            unmerge(
                outcome.pre_image,
                entities=in_force,
                merge_id="mg-1",
                unmerge_id="un-1",
                at=LATER,
                performed_by=performed_by,
                reason=reason,
            )

    restored = unmerge(
        outcome.pre_image,
        entities=in_force,
        merge_id="mg-1",
        unmerge_id="un-1",
        at=LATER,
        performed_by="rupash",
        reason="two clients after all",
    )
    assert restored.audit.performed_by == "rupash"
    assert restored.audit.merge_id == "mg-1"
    assert restored.audit.reversed_at == LATER


def test_a_merge_authority_with_nobody_behind_it_is_refused() -> None:
    """Both authorities have to name something, or the audit attributes the merge to nothing.

    A blank `performed_by` on the automatic path is a job nobody can find afterwards. A blank
    reviewer on the reviewed path is the automatic path wearing the other type's name, which is
    how the money rule would be got round without touching either constructor.

    Delete this and the audit's "who" becomes an empty string on the paths where it matters
    most."""
    with pytest.raises(ResolutionError):
        AutomaticMerge(decision=matched_result(), money=NO_MONEY, performed_by="  ")

    with pytest.raises(ResolutionError):
        ReviewedMerge(reviewer_id=" ", review_ref="rev-1", money=NO_MONEY)

    with pytest.raises(ResolutionError):
        ReviewedMerge(reviewer_id="rupash", review_ref="", money=NO_MONEY)

    assert reviewed().decided_by == "rupash"
    assert automatic().decided_by == "resolver-job"


# --------------------------------------------------------- invalidation (M14.5.5)
def test_the_id_that_stopped_being_current_is_invalidated_as_well_as_the_survivor() -> None:
    """**The natural implementation invalidates the one id nobody is asking with.**

    A merge moves a pointer and rewrites nothing, which is what makes an id issued before one
    go on resolving afterwards. That is exactly why the loser's id is still a live cache key: an
    entry keyed on it answers from before the merge, and it answers confidently.

    Delete this and the invalidation covers what the merge wrote rather than what it changed
    the meaning of, and every reader holding the old id keeps the old answer."""
    graph = {"e1": entity("e1"), "e2": entity("e2")}
    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=automatic(),
        at=NOW,
        merge_id="mg-1",
    )

    invalidated = {one.entity_id for one in outcome.invalidations}
    assert invalidated == {"e1", "e2"}

    surfaces = {one.surface for one in outcome.invalidations}
    assert surfaces == set(InvalidatedSurface)


def test_every_id_in_a_longer_chain_is_invalidated_and_not_only_the_two_named() -> None:
    """A merge into a survivor that already gathered somebody makes that id's entries stale too.

    Whoever holds the id of an entity merged away last month resolves through the survivor, so
    a merge that changes what the survivor gathers changes what their id answers with. The
    family is the set, and `canonical.family_of` is the walk.

    Delete this and the invalidation stops at the two ids in the merge, and the readers holding
    the oldest ids are the ones served stale answers longest."""
    older = replace(entity("e0"), merged_into="e1", merged_at=NOW)
    graph = {"e0": older, "e1": entity("e1"), "e2": entity("e2")}

    invalidations = invalidations_for(survivor_id="e1", merged_id="e2", entities=graph)

    assert {one.entity_id for one in invalidations} == {"e0", "e1", "e2"}


def test_an_invalidation_names_a_surface_and_an_id_and_carries_no_count() -> None:
    """A count of what a merge invalidated is a count of what somebody had cached.

    The instruction carries a surface and an entity id. There is no field for how many entries
    it will drop, which would be a fact about another reader's cache, and no field for a record
    value, because this is an instruction rather than a payload.

    Delete this and an `entries` count appears for a log line, and the log line becomes a
    statement about what other people were reading."""
    names = {one.name for one in dataclass_fields(Invalidation)}
    assert names == {"surface", "entity_id"}

    for word in ("count", "total", "entries", "size", "value"):
        assert not any(word in name for name in names), word

    with pytest.raises(ResolutionError):
        Invalidation(surface=InvalidatedSurface.CACHE, entity_id="  ")


def test_every_invalidated_surface_names_a_module_that_exists() -> None:
    """A surface naming nothing is an instruction with no addressee, and it reads like a live one.

    The three surfaces are anchored to the import system rather than to their own spelling:
    `brain.cache`, `brain.memory` and `brain.connectors.projection` are where a resolved view is
    actually held. A fourth surface added without a module, or a module renamed underneath one,
    is a merge that leaves a stale answer somewhere with nothing reporting it.

    The gap detector takes the table as a parameter, which is the only way a test can hand it
    one that is missing an entry.

    Delete this and the surfaces become three words somebody chose, and one of them can stop
    corresponding to anything."""
    for surface in InvalidatedSurface:
        module = SURFACE_MODULES[surface]
        assert importlib.util.find_spec(module) is not None, module

    fewer: dict[InvalidatedSurface, str] = {
        surface: path
        for surface, path in SURFACE_MODULES.items()
        if surface is not InvalidatedSurface.MEMORY
    }
    gaps = merge_gaps(surfaces=fewer)
    assert any("names no module" in gap for gap in gaps)


def test_an_unmerge_invalidates_the_same_surfaces_the_merge_did() -> None:
    """Putting an entity back changes what an id answers with exactly as taking it away did.

    An unmerge is a merge run backwards as far as any cache is concerned: the survivor gathers
    less than it did and the restored id resolves to itself again. A restoration that carried
    no invalidations would leave every reader holding the merged answer.

    Delete this and an unmerge is invisible to the cache, and the entity comes back everywhere
    except where anybody is reading."""
    graph = {"e1": entity("e1"), "e2": entity("e2")}
    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=automatic(),
        at=NOW,
        merge_id="mg-1",
    )
    in_force = {**graph, "e2": outcome.merged}

    restored = unmerge(
        outcome.pre_image,
        entities=in_force,
        merge_id="mg-1",
        unmerge_id="un-1",
        at=LATER,
        performed_by="rupash",
        reason="two clients after all",
    )

    assert {one.entity_id for one in restored.invalidations} == {"e1", "e2"}
    assert {one.surface for one in restored.invalidations} == set(InvalidatedSurface)


def test_nothing_a_merge_produces_reports_how_much_was_hidden_or_gathered() -> None:
    """DENIED and ABSENT stay indistinguishable, and a merge is a place a count would arrive.

    A merge knows the whole family, which is more than any reader reaches, so a count on
    anything it produces is a count of records the reader may not see. The audit, the outcome,
    the pre-image and the restoration all carry rows and ids and no totals.

    Delete this and a `member_count` appears on the audit for the console, and the console
    shows a reader how much of the entity they are not being shown."""
    forbidden = ("count", "total", "others", "truncated", "hidden")

    for kind in (MergeOutcome, MergeAudit, PreImage, Restoration, Invalidation):
        for field in dataclass_fields(kind):
            assert not any(word in field.name for word in forbidden), (
                f"{kind.__name__}.{field.name}"
            )

    for function in (merge, unmerge, capture_pre_image, invalidations_for):
        for parameter in inspect.signature(function).parameters:
            assert not any(word in parameter for word in forbidden), parameter


def test_the_evidence_on_a_merge_audit_carries_no_value_from_either_record() -> None:
    """A merge audit travels into an operations log, and a client's fields must not go with it.

    The evidence is field names and weights. `guardrails.Evidence` holds the name to a
    machine-name grammar, so a company name or an address pasted into the slot fails rather
    than rendering, and there is no second slot for what the field said.

    Delete this and a merge audit becomes the one surface in the resolution package that
    carries record values, and it is the surface that is kept forever."""
    graph = {"e1": entity("e1"), "e2": entity("e2")}
    outcome = merge(
        survivor_id="e1",
        merged_id="e2",
        entities=graph,
        authority=automatic(),
        at=NOW,
        merge_id="mg-1",
    )

    fields = {one.field for one in outcome.audit.evidence}
    assert fields
    assert fields <= {one.value for one in Feature}

    with pytest.raises(ValueError, match="not a field name"):
        Evidence(field="Kandang Kerbau Holdings Pte Ltd", weight=1.0)


def test_merging_is_not_called_by_anything_in_the_running_system() -> None:
    """Said in a constant so that claiming otherwise means deleting it.

    No route, worker or job calls `merge` or `unmerge`. There is no merge audit table, no
    pre-image is persisted anywhere, and no cache has ever been cleared by an `Invalidation`
    this module produced. The call site that would have to exist is a resolver service holding
    the entity graph, calling the cascade over a candidate pair, handing the result to
    `AutomaticMerge` and writing the outcome's one pointer inside a transaction with the audit
    row.

    Delete this and the gap stops being written down, and the next reader assumes the money
    rule is protecting something."""
    from brain.resolution import merge as merge_module

    assert merge_module.NOTHING_HERE_IS_CALLED_BY_THE_RUNNING_SYSTEM
    assert "resolver service" in merge_module.NOTHING_HERE_IS_CALLED_BY_THE_RUNNING_SYSTEM
