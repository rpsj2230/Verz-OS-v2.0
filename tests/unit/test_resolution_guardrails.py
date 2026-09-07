"""The guardrails, held to what they must never say as much as to what they must never do.

Three groups. The blocklist and the caps stop a merge that would join unrelated companies. The
priority order stops a merge being made for a confident-sounding reason when the strongest
evidence available was contradictory. The review queue and the unresolved notice are where the
work could leak: both surfaces explain themselves to a person, and explaining is where a count
of hidden things and a value nobody may read arrive by helpfulness rather than by mistake.

Every refusal test here has a sibling proving the ordinary case still works, because a
blocklist that blocks everything and a queue that shows nothing pass every test about refusal.

Task ids: M14.6.1, M14.6.2, M14.6.3, M14.6.4, M14.6.5
"""

from __future__ import annotations

import inspect
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime

import pytest

from brain.resolution import guardrails
from brain.resolution.canonical import (
    EntityType,
    Identifier,
    IdentifierKind,
    SourceRef,
)
from brain.resolution.guardrails import (
    IDENTIFIER_CAPS,
    IDENTIFIER_PRIORITY,
    PLACEHOLDER_VALUES,
    PLAIN_LANGUAGE,
    SHARED_MAILBOX_LOCAL_PARTS,
    UNRESOLVED_TEXT,
    Blocked,
    BlockRule,
    CapBreach,
    Claim,
    CollisionOutcome,
    Evidence,
    ReviewItem,
    ReviewQueue,
    Strength,
    Unresolved,
    UnresolvedNotice,
    UnresolvedReason,
    blocked,
    cap_breaches,
    cap_for,
    guardrail_gaps,
    priority_of,
    resolve_collision,
    review_queue,
    strength_of,
    unresolved_for,
)

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)

#: A client name that appears in no blocklist and in no module, so a test asserting that a
#: report does not quote its input has something specific to look for.
SECRET = "kandangkerbauholdings"


def source(source_name: str = "freshdesk", record: str = "42") -> SourceRef:
    return SourceRef(source=source_name, entity="company", source_id=record)


def identifier(
    entity_id: str, kind: IdentifierKind, digest: str, *, record: str = "1"
) -> Identifier:
    return Identifier(
        entity_id=entity_id,
        kind=kind,
        key_hash=digest * 64,
        source=source(record=record),
        first_seen_at=NOW,
    )


# --------------------------------------------------- blocked values (M14.6.1)
def test_a_shared_mailbox_may_not_be_used_as_a_join_key() -> None:
    """**The cheapest way to merge a whole client list into one entity.**

    Twenty companies list `info@` on their contact record, and joining on the address makes
    those twenty one entity whose readers then see a view assembled out of all of them.

    The positive half is the one that stops the guard being satisfied by refusing everything: a
    named person at the same domain is not blocked, and if it were, the estate would have no
    email identifiers at all.

    Delete this and the blocklist can lose its mailbox rule and nothing fails until a merge has
    already happened, at which point the entity looks exactly like a correctly resolved one."""
    for role in ("info@acme.example", "Sales@Acme.Example", " no-reply@acme.example "):
        found = blocked(IdentifierKind.EMAIL, role)
        assert found is not None, f"{role} was admitted"
        assert found.rule is BlockRule.SHARED_MAILBOX

    assert blocked(IdentifierKind.EMAIL, "wei.ling@acme.example") is None
    assert blocked(IdentifierKind.EMAIL, "j.tan@acme.example") is None


def test_a_block_report_never_carries_the_value_it_refused() -> None:
    """A refusal travels into a log, a trace and an operator's screen. The value must not.

    Checked two ways, because one of them alone rots. The behaviour check says the sentence
    does not quote the address; the structural check says there is no field on `Blocked` for
    one, which is what stops the behaviour check being defeated by a new attribute nobody
    thought of as data.

    Delete this and a helpful f-string appears in the refusal path, and the first thing it puts
    into the operations log is a customer's contact address."""
    found = blocked(IdentifierKind.EMAIL, f"info@{SECRET}.example")

    assert found is not None
    assert SECRET not in found.reason
    assert SECRET not in repr(found)
    assert {one.name for one in dataclass_fields(Blocked)} == {"kind", "rule"}


def test_a_placeholder_is_recognised_after_normalisation_and_not_before() -> None:
    """ "N/A" arrives with capitals, spaces and a slash, and all three have to come off first.

    The blocklist is compared against `normalise.collapse`d text, so the entries can be written
    the way somebody types them. A comparison against the raw list lets " N/A " through, which
    is the spelling a spreadsheet export actually produces.

    The negative half matters: "NAB" collapses to something that is not in the list, and a
    substring rule would block it. So would blocking any value merely containing "na".

    Delete this and the blocklist matches only the exact lower-case spellings and misses every
    real one."""
    for junk in ("N/A", "  n/a  ", "Not Applicable", "TBC", "unknown"):
        found = blocked(IdentifierKind.TAX_ID, junk)
        assert found is not None, f"{junk!r} was admitted"
        assert found.rule is BlockRule.PLACEHOLDER

    assert blocked(IdentifierKind.TAX_ID, "NAB") is None
    assert blocked(IdentifierKind.TAX_ID, "201912345A") is None


def test_a_run_of_one_character_is_blocked_and_a_pair_is_not() -> None:
    """The rule that catches junk a list cannot enumerate, held at its boundary.

    There is no end to the strings made of one character repeated, so this is a shape and not
    an entry. Three is where it starts, because two is a doubled letter and occurs in ordinary
    initialisms and country codes, and a rule firing at two would refuse real short values.

    Delete this and either the shape rule disappears, letting a phone field of ten ones join
    every record filled in the same way, or the threshold drops to two and the rule starts
    refusing real identifiers."""
    for junk in ("yyy", "1111111111", "0000"):
        found = blocked(IdentifierKind.PHONE, junk)
        assert found is not None, f"{junk!r} was admitted"
        assert found.rule is BlockRule.ONE_CHARACTER_REPEATED

    assert blocked(IdentifierKind.PHONE, "yy") is None
    assert blocked(IdentifierKind.PHONE, "+65 6123 4567") is None


def test_a_value_with_no_letter_or_digit_in_it_is_blocked() -> None:
    """A hyphen in a required field is the commonest junk value in any CRM.

    Separate from the placeholder list on purpose: an entry of "-" in that list would collapse
    to the empty string and then compare equal to every value that collapses to nothing, which
    is a blocklist entry that blocks by accident rather than by rule.

    Delete this and a dash reaches `identifier_hash`, where it becomes a digest that joins
    every record whose field was filled in the same way."""
    for junk in ("-", "--", ".", "  "):
        found = blocked(IdentifierKind.DOMAIN, junk)
        assert found is not None, f"{junk!r} was admitted"
        assert found.rule is BlockRule.NOTHING_BUT_PUNCTUATION


def test_the_mailbox_rule_applies_to_an_address_and_to_nothing_else() -> None:
    """ "info" is a role in an email address and is not junk in a tax field.

    The rule reads the local part of an address, so it can only be applied to the kind that has
    one. Applying it to every kind would refuse a company whose registration happens to collapse
    to a word on the list.

    Delete this and the mailbox list becomes a general junk list, which is a different rule with
    different failures and no argument written for it."""
    assert blocked(IdentifierKind.EMAIL, "info@acme.example") is not None
    assert blocked(IdentifierKind.TAX_ID, "info") is None
    assert blocked(IdentifierKind.DOMAIN, "support") is None


def test_the_blocklists_hold_no_address_and_no_domain() -> None:
    """**The blocklist must never become a way to enumerate an installation's own data.**

    A blocklist that learnt from what it saw would be a list of this installation's real
    customer addresses in a file everybody with repository access can read, so reading it would
    say which of our clients use which shared mailbox. The shape that makes that impossible is
    that every entry is a generic term with no domain and no address in it.

    Checked structurally rather than by reading the entries, because a list is checked by eye
    once and then grows.

    Delete this and the first support incident where somebody works out that an address is
    shared ends with that address committed to this file."""
    for entry in SHARED_MAILBOX_LOCAL_PARTS | PLACEHOLDER_VALUES:
        assert "@" not in entry, f"{entry!r} is an address rather than a role"
        assert "." not in entry, f"{entry!r} carries a domain"
        assert entry == entry.lower(), f"{entry!r} is not written in the comparison form"


# ------------------------------------------------------------- caps (M14.6.2)
def test_one_entity_may_hold_one_registration_number_and_not_two() -> None:
    """A UEN names one registered company, so two of them on one entity is two companies.

    The figure is not a judgement about tidiness. M14.3.1 puts UEN in the stage that merges on
    a hard identifier alone, and an identifier strong enough to merge on by itself cannot
    honestly appear twice on one entity.

    The positive half proves the cap is not simply refusing: one UEN is fine.

    Delete this and the cap can be raised to two, which reads as tolerant, and the detector for
    the worst kind of bad merge stops firing."""
    one = [identifier("e1", IdentifierKind.UEN, "a")]
    two = [*one, identifier("e1", IdentifierKind.UEN, "b", record="2")]

    assert cap_breaches("e1", EntityType.COMPANY, one) == ()

    breaches = cap_breaches("e1", EntityType.COMPANY, two)
    assert len(breaches) == 1
    assert breaches[0].kind is IdentifierKind.UEN
    assert (breaches[0].cap, breaches[0].distinct, breaches[0].over_by) == (1, 2, 1)


def test_the_cap_counts_distinct_values_rather_than_rows() -> None:
    """Two sources asserting the same registration number is corroboration, not a breach.

    This is the case the obvious implementation gets wrong: counting `Identifier` rows makes an
    entity evidenced by three connectors look like an entity with three registration numbers,
    and the cap then fires hardest on the best-evidenced clients in the estate.

    Delete this and `len(identifiers)` replaces the set of digests, every other cap test still
    passes, and the review queue fills with the entities the resolver did best on."""
    same_value_twice = [
        identifier("e1", IdentifierKind.UEN, "a", record="1"),
        identifier("e1", IdentifierKind.UEN, "a", record="2"),
    ]

    assert cap_breaches("e1", EntityType.COMPANY, same_value_twice) == ()


def test_a_cap_check_ignores_identifiers_belonging_to_other_entities() -> None:
    """A caller may hand over a batch; the count is for one entity.

    Delete this and a batch containing a second entity's rows produces a breach against the
    first, which is a review item about a merge that never happened."""
    mixed = [
        identifier("e1", IdentifierKind.UEN, "a"),
        identifier("e2", IdentifierKind.UEN, "b", record="2"),
    ]

    assert cap_breaches("e1", EntityType.COMPANY, mixed) == ()


def test_an_email_on_a_company_is_deliberately_not_capped() -> None:
    """Capping a person-scale identifier caps how large a client may be.

    A company legitimately holds one address per contact, so any cap fires on the client with
    three hundred contacts and stays quiet on the merge that joined four small ones. Absent
    from the table means uncapped, not capped at some large number: a large number is a figure
    somebody has to defend and cannot.

    Delete this and a plausible-looking ceiling appears for EMAIL, and the first entity to
    cross it is the biggest account in the estate."""
    assert cap_for(EntityType.COMPANY, IdentifierKind.EMAIL) is None
    assert cap_for(EntityType.COMPANY, IdentifierKind.PHONE) is None

    many = [
        identifier("e1", IdentifierKind.EMAIL, format(n, "x"), record=str(n)) for n in range(1, 16)
    ]
    assert cap_breaches("e1", EntityType.COMPANY, many) == ()


def test_a_stronger_identifier_is_never_capped_higher_than_a_weaker_one() -> None:
    """The cap table and the priority order are two hand-written tables that must agree.

    The stronger an identifier is, the fewer distinct values of it one entity may legitimately
    hold. Neither table is derived from the other, so this is a real comparison rather than one
    that moves both sides at once, and it fails if either is edited alone.

    Delete this and the caps and the ranks drift apart, and the system ends up allowing more
    registration numbers on one entity than domains."""
    capped = [(kind, cap) for (_, kind), cap in IDENTIFIER_CAPS.items()]
    for left_kind, left_cap in capped:
        for right_kind, right_cap in capped:
            if priority_of(left_kind) < priority_of(right_kind):
                assert left_cap <= right_cap, f"{left_kind.value} outranks {right_kind.value}"

    assert cap_for(EntityType.COMPANY, IdentifierKind.UEN) == 1, "and the top of it is exactly one"


def test_a_cap_breach_carries_a_count_and_never_a_value() -> None:
    """The count is an operator's fact; the value would be a disclosure.

    The check runs over the whole identifier set, because a cap detects a merge that swept up
    unrelated records and half a set cannot show that. So the count is an estate-wide figure
    and belongs to the resolver and the audit trail, both of which already see everything, and
    the type has no render and no plain-language form to carry it anywhere else.

    It counts digests, so the module deciding an entity holds too many addresses has no way to
    read one.

    Delete this and a `values` field appears on the breach so a reviewer can see what they
    were, and the review queue starts showing contact details."""
    names = {one.name for one in dataclass_fields(CapBreach)}

    assert names == {"entity_id", "entity_type", "kind", "cap", "distinct"}
    assert not hasattr(CapBreach, "render")
    assert not hasattr(CapBreach, "explain")


# ------------------------------------------- priority for collisions (M14.6.3)
def test_the_strongest_identifier_present_decides_a_collision() -> None:
    """A registration number beats a domain, and the weaker one does not get a vote.

    Delete this and the order stops being applied at all, and whichever claim the resolver
    happened to read first becomes the answer."""
    verdict = resolve_collision(
        [Claim(IdentifierKind.DOMAIN, "e2"), Claim(IdentifierKind.UEN, "e1")]
    )

    assert verdict.outcome is CollisionOutcome.DECIDED
    assert verdict.entity_id == "e1"
    assert verdict.deciding_kind is IdentifierKind.UEN


def test_a_tie_on_the_strongest_identifier_is_not_broken_by_a_weaker_one() -> None:
    """**The sharpest rule in this module.**

    Two entities claiming one UEN is not a tie the domain name settles. It is two rows that
    cannot both be right, and the natural implementation walks down the order until something
    is unambiguous, which produces a merge carrying the reason "matched on domain" while the
    contradiction sitting above it goes unmentioned. A merge with a confident reason attached
    is the one nobody goes back and checks.

    The set-up is deliberately arranged so that falling through would succeed: the domain claim
    agrees with one of the two UEN claims, so a walk down the order returns "e2" and looks
    entirely reasonable.

    Delete this and that walk is written as an improvement, this file stays green, and the
    system starts merging companies on the evidence it was told to disregard."""
    verdict = resolve_collision(
        [
            Claim(IdentifierKind.UEN, "e1"),
            Claim(IdentifierKind.UEN, "e2"),
            Claim(IdentifierKind.DOMAIN, "e2"),
        ]
    )

    assert verdict.outcome is CollisionOutcome.TIED_AT_THE_TOP
    assert verdict.entity_id is None, "nothing here decides it"
    assert verdict.decided is False
    assert verdict.deciding_kind is IdentifierKind.UEN, "and the operator is told where the tie is"


def test_identifiers_that_all_agree_need_no_priority_at_all() -> None:
    """The ordinary case, and the one a guard tested only by its refusals would break.

    Delete this and `resolve_collision` can start returning a tie for everything, and every
    other collision test in this file still passes."""
    verdict = resolve_collision(
        [Claim(IdentifierKind.EMAIL, "e1"), Claim(IdentifierKind.PHONE, "e1")]
    )

    assert verdict.outcome is CollisionOutcome.AGREED
    assert verdict.entity_id == "e1"


def test_no_claims_at_all_is_not_a_collision() -> None:
    """An empty set is answered rather than raised on, and it decides nothing.

    Delete this and the empty case returns AGREED with None on it, or raises inside a backfill
    on the first record with no identifiers."""
    verdict = resolve_collision([])

    assert verdict.outcome is CollisionOutcome.NOTHING_TO_DECIDE
    assert verdict.entity_id is None


def test_every_identifier_kind_has_a_rank_and_an_unranked_one_is_refused() -> None:
    """A kind with no rank is refused rather than given a default.

    Both halves. The vocabulary is covered today, so the refusal branch is unreachable through
    ordinary use, and the way to test it is to take a rank away: an identifier kind added to
    `canonical` and not to the order would arrive exactly like this.

    The default a lazy implementation would pick is wrong in both directions. Strongest lets an
    unranked identifier decide a merge; weakest silently stops it ever deciding one.

    Delete this and `IDENTIFIER_PRIORITY.index` gains an `except ValueError: return 99`, which
    reads as defensive and quietly ranks a new identifier last for ever."""
    assert set(IDENTIFIER_PRIORITY) == set(IdentifierKind)
    assert len(IDENTIFIER_PRIORITY) == len(set(IDENTIFIER_PRIORITY)), "and no kind is ranked twice"

    original = IDENTIFIER_PRIORITY
    try:
        guardrails.IDENTIFIER_PRIORITY = (IdentifierKind.UEN,)
        with pytest.raises(ValueError, match="no rank"):
            priority_of(IdentifierKind.EMAIL)
    finally:
        guardrails.IDENTIFIER_PRIORITY = original


# ------------------------------------------------- the review queue (M14.6.4)
def test_evidence_has_nowhere_to_put_the_value_that_agreed() -> None:
    """A reviewer is shown which fields agreed, never what they said.

    It is `brain.gate.compose.Citation`'s rule on a harder surface, because a reviewer is being
    asked for a judgement and therefore wants every fact available. The type has two fields and
    the free-form one is held to a machine-name grammar, so the three shapes most likely to be
    pasted into it fail rather than render.

    Delete this and a `left_value`/`right_value` pair appears so a reviewer can compare, and
    the queue becomes a way to read records nobody asked whether they may see."""
    assert {one.name for one in dataclass_fields(Evidence)} == {"field", "weight"}

    for not_a_field in (f"info@{SECRET}.example", "Acme Pte Ltd", "+65 6123 4567", ""):
        with pytest.raises(ValueError, match="field name"):
            Evidence(field=not_a_field, weight=3.0)

    assert Evidence(field="registration_number", weight=3.0).field == "registration_number"
    assert Evidence(field="company.legal_name", weight=3.0).field == "company.legal_name"


def test_a_weight_reaches_a_reviewer_as_a_sentence_and_never_as_a_number() -> None:
    """Plain language, which is what M14.6.4 asks for and is also the safer surface.

    A reviewer shown 6.2 beside 4.9 does arithmetic, and the arithmetic is a threshold they
    invented on a scale nothing in this repository has calibrated: the weight table is M14.3.5
    and it does not exist.

    Delete this and the number goes into the rendering because it is right there on the
    object."""
    line = Evidence(field="registration_number", weight=11.5).render()

    assert line.startswith("registration_number ")
    assert not any(char.isdigit() for char in line), line
    assert "agreed" in line


def test_the_band_boundaries_say_what_they_mean_about_the_odds() -> None:
    """The three figures are statements about odds, so they are checked against the odds.

    A match weight is a log2 Bayes factor: a weight of w multiplies the odds of a match by
    two to the power w. Supporting is the least that is worth calling evidence, which is a
    doubling. Strong is sixteenfold. Decisive is more than a thousandfold, which is where one
    field agreeing is close to the whole answer.

    Anchored to the arithmetic rather than to the constants themselves, which would be green
    for every value they could hold.

    Delete this and the boundaries become three numbers somebody nudges to make a queue
    shorter."""
    assert 2**guardrails.SUPPORTING_WEIGHT == 2
    assert 2**guardrails.STRONG_WEIGHT == 16
    assert 2**guardrails.DECISIVE_WEIGHT > 1000

    assert strength_of(11.0) is Strength.DECISIVE
    assert strength_of(5.0) is Strength.STRONG
    assert strength_of(2.0) is Strength.SUPPORTING
    assert strength_of(0.5) is Strength.WEAK


def test_agreement_that_is_worth_nothing_is_not_shown_as_weak_support() -> None:
    """A weight of zero means the field agreeing told us nothing. That is not weak evidence.

    The odds are unchanged, so rendering it as weak support puts a line in front of a reviewer
    that reads as a small reason to merge two records. The boundary is therefore strictly above
    zero.

    Delete this and `weight >= 0` reads as tidier and turns every field that carries no
    information into a reason."""
    assert strength_of(0.0) is Strength.AGAINST
    assert strength_of(-4.0) is Strength.AGAINST
    assert "did not agree" in Evidence(field="phone", weight=-4.0).render()


def test_every_band_has_a_sentence_and_every_block_rule_has_a_reason() -> None:
    """The three exhaustiveness properties, asserted against the vocabularies directly.

    Not through `guardrail_gaps`, deliberately. That function returns nothing on a healthy
    tree, so an assertion that it returns nothing is an assertion about the tree rather than
    about the function: it stays green with every check inside it deleted. The next test is
    where the function itself is exercised.

    Delete this and a sixth band, a fifth block rule or a new identifier kind arrives with no
    sentence, no reason and no rank, and the first thing that notices is a `KeyError` in front
    of a reviewer."""
    assert set(PLAIN_LANGUAGE) == set(Strength)
    assert set(guardrails.BLOCK_REASONS) == set(BlockRule)
    assert set(IDENTIFIER_PRIORITY) == set(IdentifierKind)

    assert guardrail_gaps() == (), "and the tree itself is healthy"


def test_a_cap_that_contradicts_the_priority_order_is_reported() -> None:
    """**The detector, exercised with tables that actually disagree.**

    A mutation run found this gap. Disabling the cap-against-priority check survived every
    test, because the only assertion anybody had written was that `guardrail_gaps` returns
    nothing today, and it returns nothing today whether or not the check is still there. A
    detector can only be tested on the failure it detects.

    So the caps come in as a parameter, the way `brain.memory.tiers.tier_gaps` takes its
    changes, and this hands it a table where the strongest identifier is allowed more distinct
    values than a weaker one. That is the shape of a real edit: somebody raises the UEN cap to
    silence a noisy review queue and does not think about the rank.

    Delete this and the fourth check in `guardrail_gaps` can be removed and nothing fails."""
    contradictory = {
        (EntityType.COMPANY, IdentifierKind.UEN): 9,
        (EntityType.COMPANY, IdentifierKind.DOMAIN): 5,
    }

    gaps = guardrail_gaps(caps=contradictory)

    assert len(gaps) == 1
    assert "uen" in gaps[0]
    assert "domain" in gaps[0]

    agreeing = {
        (EntityType.COMPANY, IdentifierKind.UEN): 1,
        (EntityType.COMPANY, IdentifierKind.DOMAIN): 5,
    }
    assert guardrail_gaps(caps=agreeing) == (), "and a table that agrees reports nothing"


def test_an_item_is_absent_unless_the_reviewer_reaches_both_records() -> None:
    """**A review decides that two records are one thing, so one of them is not enough.**

    A reviewer who reaches one record cannot answer the question, and showing them the item
    tells them a record exists that they may not see, which is the disclosure
    `canonical.resolved_view` refuses one row at a time.

    The positive half is the whole point of a queue: a reviewer who reaches both gets the item.

    Delete this and the filter becomes a disjunction, which reads as more useful, and the queue
    starts naming records to people who cannot see them."""
    left, right = source("freshdesk", "42"), source("xero", "CON-99")
    item = ReviewItem(item_id="rq_1", left=left, right=right)

    both = review_queue([item], reviewer_id="p_alice", reaches=lambda member: True)
    one_only = review_queue([item], reviewer_id="p_bob", reaches=lambda member: member == left)
    neither = review_queue([item], reviewer_id="p_carol", reaches=lambda member: False)

    assert both.items == (item,)
    assert one_only.items == ()
    assert neither.items == ()


def test_a_queue_says_nothing_about_the_items_it_withheld() -> None:
    """No count, no total, no truncation flag, and nothing to subtract.

    A queue is a page and a page wants a figure at the top of it, and on a filtered list that
    figure is the number of things the reader may not see. Checked on the shape of the type,
    because behaviour today says nothing about whether a field can be added tomorrow.

    Delete this and `total` appears beside `items` so the page can render "showing 1 of 3"."""
    names = {one.name for one in dataclass_fields(ReviewQueue)}

    assert names == {"reviewer_id", "items"}

    visible = source("freshdesk", "42")
    items = [
        ReviewItem(item_id=f"rq_{n}", left=visible, right=source("xero", f"CON-{n}"))
        for n in range(3)
    ]
    narrow = review_queue(
        items, reviewer_id="p_bob", reaches=lambda member: member.source_id in {"42", "CON-0"}
    )

    assert len(narrow.items) == 1
    assert narrow.items[0].item_id == "rq_0"


def test_evidence_reaches_a_reviewer_strongest_first() -> None:
    """The order is a fixed function of the evidence, so two reviewers read the same lines.

    Sorted by band and then by field name rather than by the raw weight, so two fields in one
    band always appear in the same order whatever their exact figures are.

    Delete this and the order becomes whatever the cascade happened to append in, which differs
    between runs and reads to a reviewer as a ranking."""
    item = ReviewItem(
        item_id="rq_1",
        left=source("freshdesk", "42"),
        right=source("xero", "CON-99"),
        evidence=(
            Evidence(field="phone", weight=0.4),
            Evidence(field="registration_number", weight=11.0),
            Evidence(field="normalised_name", weight=4.5),
        ),
    )

    lines = item.explain()

    assert [line.split(" ")[0] for line in lines] == [
        "registration_number",
        "normalised_name",
        "phone",
    ]


def test_a_review_item_carries_no_total_score() -> None:
    """Per-field evidence and no sum, because a sum is a threshold waiting for a cutoff.

    `canonical.A_SCORE_IS_EVIDENCE_AND_NEVER_A_PERMISSION` makes the argument for the reach
    path; this is the same argument on the surface a person reads. A total on the item is the
    field a queue gets sorted and then filtered by.

    Delete this and `confidence` appears on the item, and the queue grows a "show me only the
    ones above 0.8" control."""
    names = {one.name for one in dataclass_fields(ReviewItem)}

    assert names == {"item_id", "left", "right", "evidence"}


# ------------------------------------------- unresolved behaviour (M14.6.5)
def test_an_unresolved_answer_carries_no_count_of_the_candidates() -> None:
    """**Two candidates and ninety-seven produce the same bytes.**

    "I found 4 matches" is a count of hidden items. Asserted by equality of the rendered
    strings rather than by looking for digits, because equality catches every way a number
    could arrive, including a word.

    Delete this and the count reaches the sentence as a helpful detail, and an asker learns how
    many records they may not see by reading a refusal."""
    two = unresolved_for(candidates=2, confident=False, review_ref="rq_1")
    many = unresolved_for(candidates=97, confident=False, review_ref="rq_1")

    assert two is not None and many is not None
    assert two.for_asker() == many.for_asker()
    assert two.for_asker().render() == many.for_asker().render()


def test_both_unresolved_reasons_reach_the_asker_as_one_sentence() -> None:
    """Several candidates and one unconvincing candidate are one answer to the person asking.

    "I found more than one match" carries no number and is still one observable state, where
    "the single match I found is not convincing" is another, and a caller who can produce both
    has learnt whether there was one candidate or more than one. That is a count of records
    they may not see, arrived at by comparing two answers.

    The sentence is one constant referenced from one place, so the property is checkable by
    identity rather than by two literals that agree today.

    Delete this and the two reasons get two sentences as a usability improvement, and the
    improvement is the disclosure."""
    several = Unresolved(reason=UnresolvedReason.SEVERAL_CANDIDATES, review_ref="rq_1")
    unconvinced = Unresolved(reason=UnresolvedReason.BELOW_CONFIDENCE, review_ref="rq_1")

    assert several.for_asker() == unconvinced.for_asker()
    assert several.for_asker().text is UNRESOLVED_TEXT
    assert {one.name for one in dataclass_fields(UnresolvedNotice)} == {"review_ref"}


def test_the_unresolved_signature_has_nowhere_a_candidate_could_arrive() -> None:
    """Never guess, expressed as a signature rather than as a rule to remember.

    A version taking the candidates themselves would work exactly as well and would put them
    one f-string away from a sentence a channel renders. Taking a count and a boolean means the
    candidates are not in scope at the only place this module could name one.

    Delete this and `unresolved_for(candidates=[...])` appears, because it is more convenient
    at the call site."""
    parameters = set(inspect.signature(unresolved_for).parameters)

    assert parameters == {"candidates", "confident", "review_ref"}
    for forbidden in ("candidate", "entities", "names", "score", "matches"):
        assert forbidden not in parameters


def test_one_confident_candidate_is_not_unresolved_and_neither_is_none() -> None:
    """The two positive cases, without which the function is satisfied by refusing everything.

    Exactly one candidate the cascade is confident about is resolved, and no candidates at all
    is not unresolved either: nothing matched, so the caller mints a new entity, and an
    `Unresolved` there would send a person a review item with nothing in it to review.

    Delete this and `unresolved_for` can start returning an `Unresolved` for every call, and
    every other test in this section stays green while nothing in the estate ever resolves."""
    assert unresolved_for(candidates=1, confident=True, review_ref="rq_1") is None
    assert unresolved_for(candidates=0, confident=False, review_ref="rq_1") is None

    unsure = unresolved_for(candidates=1, confident=False, review_ref="rq_1")
    assert unsure is not None
    assert unsure.reason is UnresolvedReason.BELOW_CONFIDENCE


def test_a_review_reference_is_held_to_a_grammar() -> None:
    """The reference is the only part of the notice a caller chooses, so it is bounded.

    A reference built by joining candidate ids would put them in front of somebody who may see
    none of them, which is the disclosure arriving through the one field that was not thought
    of as content. The grammar is not a proof, and it does refuse the shapes such a reference
    actually takes: a list, a query string, a sentence.

    Delete this and the review link becomes the place the candidate ids travel in."""
    assert UnresolvedNotice(review_ref="rq_1").render().endswith("rq_1")

    for smuggled in ("e_1,e_2,e_3", "queue?candidates=e_1&e_2", "e_1 and e_2", ""):
        with pytest.raises(ValueError, match="review reference"):
            UnresolvedNotice(review_ref=smuggled)


def test_a_negative_candidate_count_is_refused() -> None:
    """A count that cannot happen is refused rather than treated as zero.

    Delete this and a caller subtracting two figures to get a candidate count gets None back
    for a negative one, which reads as "resolved"."""
    with pytest.raises(ValueError, match="cannot be negative"):
        unresolved_for(candidates=-1, confident=True, review_ref="rq_1")
