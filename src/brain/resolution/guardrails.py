"""The five rules that stop entity resolution merging things it should not, and one that
stops it explaining itself into a disclosure.

`brain.resolution.canonical` decides what a merge may show. `brain.resolution.normalise`
decides what two names have to look like before they count as equal. This is the layer between
them: which values may be used as join keys at all, how many of each one entity may hold, which
identifier wins when two disagree, what a human reviewer is shown, and what is said when
nothing resolved.

**A shared mailbox is the single cheapest way to merge an entire client list into one entity.**
Twenty companies list `info@` on their contact record. Joining on the email address makes those
twenty one company, and the merged entity then hands every reader of any one of them a view
assembled from the other nineteen. The blocklist is not data hygiene, it is the guard against
that. See `THE_BLOCKLIST_IS_WRITTEN_AND_NEVER_LEARNT` for the shape it has to have, which is
generic English words written by hand and never a value observed in the estate: a blocklist
that learnt from what it saw would be a list of this installation's real addresses, sitting in
a configuration file, readable as an enumeration of the customers who use them.

**A tie at the top of the priority order is not broken by a weaker identifier.** Two entities
claiming one UEN is not a question the domain name can settle. It is two rows that cannot both
be right, and falling through to the next rank produces a merge with a confident-sounding
reason attached to it, which is worse than no merge at all because it is the shape nobody goes
back and checks. See `A_TIE_AT_THE_TOP_IS_NOT_BROKEN_BY_A_WEAKER_IDENTIFIER`.

**The caps and the priority order are two tables that must agree, and neither is derived from
the other.** The stronger an identifier is, the fewer distinct values of it one entity may
legitimately hold: a UEN names one registered company, so two of them on one entity is two
companies. `guardrail_gaps` checks the two tables against each other rather than deriving one
from the other, for the reason `brain.memory.tiers.CHANGES_WHAT_ANYBODY_MAY_SEE` is written out
by hand: derived, they would agree by construction and the check would move both sides at once.

**The review queue shows which fields agreed and how strongly, and never what they said.** It
is `brain.gate.compose.Citation`'s rule applied to a different surface, and it matters more
here, because a review queue is read by somebody who is being asked to make a judgement and
therefore wants every fact available. `Evidence` has a field name, a weight and nowhere at all
to put a value, and the name is held to a machine-name grammar so that an address or a company
name pasted into it fails rather than renders. The weight reaches the reviewer as a sentence
rather than as a number: a number invites a reviewer to apply their own threshold, thresholds
are M14.3.3's and are calibrated offline in M14.3.5, and neither of those is built.

**An item nobody reaches both halves of is not in the queue.** A review decides that two
records are one thing. A reviewer who reaches one of them cannot make that decision and must
not be told the other exists, so the filter is a conjunction and it is applied to the item
rather than to its halves. The queue carries no count, no total and no "and others", for the
reason `canonical.A_VIEW_CARRIES_NO_COUNT_OF_WHAT_IT_WITHHELD` gives.

**An unresolved entity gets one sentence, and it is the same sentence for both reasons
(M14.6.5).** "I found more than one match" is count-free and correct on its own terms, and it
is still one observable state and "the one match I found is not convincing" is another, and the
difference between those two states is whether the number of candidates was one or more than
one. That is a count, arrived at by comparison rather than by subtraction, and it is a count of
things the asker may not see. So there is one `UNRESOLVED_TEXT`, both reasons render it, and
`UnresolvedNotice` has no reason field to render anything else from. That is
`brain.gate.abstain`'s construction, where `NOT_ENTITLED` and `NOTHING_RETRIEVED` share one
string by identity rather than by two literals that agree today.

Nothing here can guess. `unresolved_for` takes a count and a confidence and has no parameter a
candidate could arrive through, so naming one is not an omission this module made, it is a
value that is not in scope at the only place it could be named.

**What is not built, said plainly.** There is no blocked-values table, no cap table and no
review-queue table in `src/brain/tables/`, and no migration creates one; the tables named in
M14.6.1 are shapes and policies here, held in module constants. The weight table M14.3.5
exports from offline calibration does not exist, so `Evidence.weight` is whatever a caller
hands over and nothing here has calibrated it. The caps and the priority order are written for
companies; M14.7 applies the same cascade to people and projects and is not built, and caps for
an unbuilt cascade would be figures nobody can check. See `NOTHING_HERE_IS_PERSISTED`.

Scope: domain logic. Nothing here opens a connection, reads a clock, writes a row or renders a
page. `review_queue` is the data a page would be drawn from and not the page.

Task ids: M14.6.1, M14.6.2, M14.6.3, M14.6.4, M14.6.5
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.resolution.canonical import (
    EntityType,
    Identifier,
    IdentifierKind,
    MemberReach,
    SourceRef,
)
from brain.resolution.normalise import collapse

# ------------------------------------------------------------------ written-down reasons
#: Why the blocklist is a hand-written list of generic words and can never be a learnt one.
THE_BLOCKLIST_IS_WRITTEN_AND_NEVER_LEARNT = (
    "A shared mailbox links every company that uses one, so twenty clients listing info@ "
    "become one entity and every reader of any of them is handed a view built out of the "
    "other nineteen. The blocklist is the guard against that, and it has to be made of "
    "generic terms that exist independently of any customer: info, sales, noreply, test, "
    "unknown. The tempting version learns, appending whatever address turned out to be "
    "shared, and that version is a list of this installation's real customer addresses "
    "sitting in a file that everybody with repository access can read, so reading the "
    "blocklist becomes a way to enumerate which of our clients use which shared mailbox. "
    "There is no loader here and no table behind it: the list is a module constant, so "
    "appending an observed value is a source change in a review rather than a row somebody "
    "inserts."
)

#: Why a blocked value's report cannot contain the value.
A_BLOCK_REPORT_NAMES_THE_RULE_AND_NEVER_THE_VALUE = (
    "Blocked is a kind and a rule, and its sentence is looked up from the rule rather than "
    "stored, so there is nowhere on the type for a value and nowhere in the sentence for one "
    "to be interpolated. The reason is the one brain.gate.compose.Citation gives about "
    "carrying a field name and never a field value: a report travels further than the call "
    "that produced it, into a log, a trace and an operator's screen, and a refusal that "
    "quoted the address it refused would put contact details in all three."
)

#: Why the top rank of the priority order decides alone or nothing does.
A_TIE_AT_THE_TOP_IS_NOT_BROKEN_BY_A_WEAKER_IDENTIFIER = (
    "Two entities claiming one UEN is not a tie the domain name settles. It is two rows that "
    "cannot both be right, and the natural implementation walks down the priority order until "
    "something is unambiguous, which produces a merge carrying the reason 'matched on domain' "
    "and hides the contradiction that was sitting above it. A merge with a confident reason "
    "attached is the one nobody goes back and checks. So the strongest kind present decides "
    "when it names exactly one entity, and when it names two the answer is that nothing here "
    "decides and a person does."
)

#: Why a cap breach is an operator's fact rather than a reader's.
A_CAP_BREACH_IS_AN_OPERATOR_FACT_AND_NEVER_A_READER_FACT = (
    "The cap check runs over an entity's whole identifier set, because a cap is a detector "
    "for a merge that swept up unrelated records and half a set cannot show that. The count "
    "it produces is therefore an estate-wide figure, and putting it in front of a reader who "
    "reaches some of the entity's members is handing them a count of the members they do not "
    "reach. So CapBreach has no render, no plain-language form and no place in ReviewItem: it "
    "goes to the resolver and to the audit trail, both of which already see everything."
)

#: Why the cap check counts digests rather than values.
THE_CAP_CHECK_COUNTS_DIGESTS_SO_IT_CANNOT_READ_WHAT_IT_COUNTS = (
    "Distinctness is counted over Identifier.key_hash, which canonical constrains to a "
    "sha256 digest and which has no field holding the value it was made from. So the module "
    "that decides an entity holds too many email addresses has no way to read one, and a "
    "later author wanting to log 'which addresses' would have to change canonical.Identifier "
    "first. That is the same construction canonical uses to keep er.identifier from being a "
    "mailing list."
)

#: Why capping an identifier that identifies people caps the client instead.
CAPPING_A_PERSON_SCALE_IDENTIFIER_CAPS_THE_CLIENT = (
    "A company entity legitimately holds one email address per contact and one phone number "
    "per office, so a cap on either is a cap on how large a client may be, and the first "
    "entity to cross it is the biggest and most important one in the estate. It would fire on "
    "the client with three hundred contacts and stay quiet on the merge that joined four "
    "small ones. So EMAIL and PHONE are deliberately absent from the company cap table, and "
    "their absence means uncapped rather than capped at some large number: a large number is "
    "a figure somebody has to defend and cannot."
)

#: Why the review queue filters on both halves of an item.
BOTH_HALVES_OR_THE_ITEM_IS_NOT_THERE = (
    "A review item asks whether two records are the same thing. A reviewer who reaches only "
    "one of them cannot answer that, and showing them the item tells them a record exists "
    "that they may not see, which is the disclosure canonical.resolved_view refuses one row "
    "at a time. So the filter is a conjunction over the item rather than a filter over its "
    "halves, and an item that fails it is absent rather than partially rendered. The queue "
    "carries no count of what the filter removed, because the difference between the queue "
    "one reviewer sees and the queue another sees is exactly the set of records neither may "
    "learn about."
)

#: Why one sentence covers both unresolved reasons.
ONE_SENTENCE_FOR_EVERY_UNRESOLVED_REASON = (
    "'I found more than one match' names no candidate and carries no number, and it is still "
    "one observable state where 'the single match I found is not convincing' is another. A "
    "caller who can produce both has learnt whether the number of candidates was one or more "
    "than one, which is a count of records they may not see, reached by comparing two "
    "answers rather than by subtracting two numbers. So both reasons render UNRESOLVED_TEXT, "
    "the reason lives on the internal value for the audit trail, and UnresolvedNotice has no "
    "reason field for a channel adapter to helpfully render. This is brain.gate.abstain's "
    "construction, where NOT_ENTITLED and NOTHING_RETRIEVED share one string by identity."
)

#: The gap this module does not close, kept as a constant so it has to be deleted.
NOTHING_HERE_IS_PERSISTED = (
    "M14.6.1 says 'blocked values table' and there is no table. There is no cap table, no "
    "review-queue table and no migration creating any of them, and nothing in src/brain/"
    "tables declares one. Everything here is a module constant and a value returned from a "
    "function. The weight table M14.3.5 exports from offline calibration does not exist "
    "either, so Evidence.weight is whatever the caller hands over and nothing in this "
    "repository has calibrated it. The caps and the priority order are written for companies "
    "only, because M14.7 applies the cascade to people and projects and is not built, and a "
    "cap for an unbuilt cascade is a figure nobody can check."
)


# ------------------------------------------------------- blocked values (M14.6.1)
class BlockRule(enum.StrEnum):
    """Why a value may not be used as a join key.

    Four shapes rather than one blocklist, because the four reach an operator as different
    problems. A shared mailbox is a real address being used for the wrong thing. A placeholder
    is a form somebody filled in to get past a required field. Punctuation only and one
    character repeated are a keyboard, and they are separate from the placeholder list because
    a list cannot enumerate them: there is no end to the strings made of one character.
    """

    #: A role address: the mailbox belongs to a function and not to a company.
    SHARED_MAILBOX = "shared mailbox"
    #: A word people type when a field is required and they have nothing to put in it.
    PLACEHOLDER = "placeholder"
    #: Punctuation, whitespace and invisibles, with no letter or digit anywhere in it.
    NOTHING_BUT_PUNCTUATION = "nothing but punctuation"
    #: One character, repeated. A held-down key rather than a value.
    ONE_CHARACTER_REPEATED = "one character repeated"


#: The sentence each rule reaches an operator with.
#:
#: A mapping keyed by the rule rather than a string built at the point of refusal, which is
#: what makes `A_BLOCK_REPORT_NAMES_THE_RULE_AND_NEVER_THE_VALUE` a property of the type
#: instead of a habit: there is no f-string anywhere on this path for a value to be
#: interpolated into.
BLOCK_REASONS: Mapping[BlockRule, str] = MappingProxyType(
    {
        BlockRule.SHARED_MAILBOX: (
            "the local part of this address is a role rather than a person, so it is shared "
            "by whoever staffs that function; joining on it would make every company that "
            "uses the same role name one entity"
        ),
        BlockRule.PLACEHOLDER: (
            "this is what somebody types when a field is required and they have nothing to "
            "put in it, so every record that got the same treatment would join to this one"
        ),
        BlockRule.NOTHING_BUT_PUNCTUATION: (
            "there is no letter or digit here, so this identifies nothing and matches every "
            "other record whose field was filled in the same way"
        ),
        BlockRule.ONE_CHARACTER_REPEATED: (
            "one character repeated is a held-down key rather than a value, and every record "
            "holding a run of the same character would join to this one"
        ),
    }
)


#: Local parts that belong to a function rather than to a company.
#:
#: Generic English role names and nothing else. Not one entry here came from looking at an
#: installation's data, and none ever may: see `THE_BLOCKLIST_IS_WRITTEN_AND_NEVER_LEARNT`.
#: Written in the form somebody would type, and compared after `normalise.collapse`, so
#: "no-reply", "no_reply" and "No Reply" are one entry rather than three.
SHARED_MAILBOX_LOCAL_PARTS: frozenset[str] = frozenset(
    {
        "abuse",
        "accounts",
        "admin",
        "administrator",
        "billing",
        "careers",
        "contact",
        "enquiries",
        "enquiry",
        "finance",
        "hello",
        "help",
        "hr",
        "info",
        "information",
        "jobs",
        "mail",
        "marketing",
        "no-reply",
        "noreply",
        "office",
        "postmaster",
        "sales",
        "support",
        "team",
        "webmaster",
    }
)

#: Values people type to get past a required field.
#:
#: Deliberately holds nothing made only of punctuation. "-" and "." are caught by
#: `BlockRule.NOTHING_BUT_PUNCTUATION`, which is a shape rather than a list, and an entry here
#: would collapse to the empty string and then compare equal to every value that collapses to
#: nothing, which is a blocklist entry that blocks by accident.
PLACEHOLDER_VALUES: frozenset[str] = frozenset(
    {
        "asdf",
        "dummy",
        "example",
        "n/a",
        "na",
        "nil",
        "no email",
        "none",
        "not applicable",
        "not available",
        "null",
        "placeholder",
        "sample",
        "tba",
        "tbc",
        "tbd",
        "test",
        "testing",
        "unknown",
    }
)

#: The two blocklists in the form values are actually compared in.
#:
#: Collapsed once at import rather than per call, and collapsed rather than lower-cased,
#: because the value arriving from a source has been through the same function: comparing a
#: raw list against a collapsed value is how "N/A " gets through a blocklist containing "n/a".
_PLACEHOLDER_KEYS: Final = frozenset(collapse(one) for one in PLACEHOLDER_VALUES)
_SHARED_LOCAL_KEYS: Final = frozenset(collapse(one) for one in SHARED_MAILBOX_LOCAL_PARTS)

#: How many identical characters in a row make a value a held-down key rather than a value.
#:
#: Three. Two is a doubled letter, which occurs in ordinary initialisms and country codes, so a
#: rule firing at two would refuse real short identifiers. Three identical characters and
#: nothing else is not something anybody types on purpose, in any of the five identifier kinds.
REPEATED_CHARACTER_RUN: Final = 3


@dataclass(frozen=True)
class Blocked:
    """Why one value may not be used as a join key.

    There is no field for the value and no field for the part of it that matched, and the
    sentence is looked up from the rule rather than stored, so nothing on this type can carry a
    contact detail into a log. See `A_BLOCK_REPORT_NAMES_THE_RULE_AND_NEVER_THE_VALUE`.
    """

    kind: IdentifierKind
    rule: BlockRule

    @property
    def reason(self) -> str:
        return BLOCK_REASONS[self.rule]


def _local_part(value: str) -> str:
    """The part of an address before the last "@", collapsed.

    The *last* rather than the first, because a local part may itself contain a quoted "@" and
    the domain may not. Split before collapsing, because `normalise.collapse` turns "@" into a
    token boundary and the split would then have nothing to find.
    """
    local, _, domain = value.strip().rpartition("@")
    return collapse(local if domain else value)


def blocked(kind: IdentifierKind, value: str) -> Blocked | None:
    """Whether this value may be used as a join key at all (M14.6.1).

    Checked before the value reaches `canonical.identifier_hash`, because a digest of a shared
    mailbox is indistinguishable from a digest of anything else: once it is hashed there is no
    way to tell that a join is wrong, and the entity that results looks exactly like a
    correctly resolved one.

    Returns None for a value that may be used, which includes every value this module has no
    opinion about. A blocklist is not a validator: an address that is malformed, a phone number
    with the wrong number of digits and a domain nobody owns all pass here, because refusing
    them is a different job with a different failure mode.
    """
    text = value.strip()
    collapsed = collapse(text)
    squashed = collapsed.replace(" ", "")
    if not squashed:
        return Blocked(kind=kind, rule=BlockRule.NOTHING_BUT_PUNCTUATION)
    if collapsed in _PLACEHOLDER_KEYS:
        return Blocked(kind=kind, rule=BlockRule.PLACEHOLDER)
    if len(squashed) >= REPEATED_CHARACTER_RUN and len(set(squashed)) == 1:
        return Blocked(kind=kind, rule=BlockRule.ONE_CHARACTER_REPEATED)
    if kind is IdentifierKind.EMAIL and _local_part(text) in _SHARED_LOCAL_KEYS:
        return Blocked(kind=kind, rule=BlockRule.SHARED_MAILBOX)
    return None


# ------------------------------------------------- caps per identifier kind (M14.6.2)
#: How many distinct values of one kind one entity may hold before something is wrong.
#:
#: Only companies, and only the identifiers that identify the company rather than the people at
#: it. See `CAPPING_A_PERSON_SCALE_IDENTIFIER_CAPS_THE_CLIENT` for why EMAIL and PHONE are
#: absent, and `NOTHING_HERE_IS_PERSISTED` for why there is no PERSON or PROJECT row.
#:
#: The three figures, in the order they can be argued about:
#:
#: - UEN is one, and the one is not a judgement. M14.3.1 puts UEN in the stage that merges on a
#:   hard identifier alone, and `canonical.IdentifierKind.UEN` calls it the strongest identifier
#:   available. An identifier strong enough to merge on by itself cannot honestly appear twice
#:   on one entity: if it does, the merge rule joined two registered companies.
#: - TAX_ID is three, and it has to be more than one because
#:   `canonical.IdentifierKind.TAX_ID` says a tax number is not unique across jurisdictions. A
#:   client operating in three of them is a regional group; more than that is a multinational
#:   this estate does not serve, and is better explained by a bad merge. Arguable, and meant to
#:   be argued with.
#: - DOMAIN is five, and it has to be more than TAX_ID because a domain costs fifteen dollars
#:   and a tax registration costs a filing: a primary domain, a country domain or two, the
#:   domain left over from a rebrand and one bought for a campaign is five without anything
#:   being wrong. Also arguable.
IDENTIFIER_CAPS: Mapping[tuple[EntityType, IdentifierKind], int] = MappingProxyType(
    {
        (EntityType.COMPANY, IdentifierKind.UEN): 1,
        (EntityType.COMPANY, IdentifierKind.TAX_ID): 3,
        (EntityType.COMPANY, IdentifierKind.DOMAIN): 5,
    }
)


def cap_for(entity_type: EntityType, kind: IdentifierKind) -> int | None:
    """How many distinct values of this kind this sort of entity may hold, or None.

    None means uncapped and is a decision rather than a hole. Returning a large default instead
    would put a figure in front of an operator that nobody chose and nobody can defend, and the
    first thing anybody does with an unexplained ceiling is raise it.
    """
    return IDENTIFIER_CAPS.get((entity_type, kind))


@dataclass(frozen=True)
class CapBreach:
    """One entity holding more distinct values of one kind than a real entity would.

    Internal. There is no render and no plain-language form, and nothing here reaches a review
    queue or an asker: see `A_CAP_BREACH_IS_AN_OPERATOR_FACT_AND_NEVER_A_READER_FACT`. It
    carries a count because the resolver and the audit trail both already see the whole
    identifier set, and it carries no value at all because the count was taken over digests.
    """

    entity_id: str
    entity_type: EntityType
    kind: IdentifierKind
    cap: int
    distinct: int

    @property
    def over_by(self) -> int:
        return self.distinct - self.cap


def cap_breaches(
    entity_id: str, entity_type: EntityType, identifiers: Sequence[Identifier]
) -> tuple[CapBreach, ...]:
    """Every cap this entity's identifiers are over (M14.6.2).

    Distinctness is counted over `Identifier.key_hash`, so this function cannot read the values
    it is counting. See `THE_CAP_CHECK_COUNTS_DIGESTS_SO_IT_CANNOT_READ_WHAT_IT_COUNTS`.

    Reports and never removes. A cap breach is evidence that a merge went wrong, and the repair
    is to look at the merge, not to drop whichever identifier arrived last: dropping one leaves
    an entity that passes every check and is still two companies, which is the same wrong
    answer with the alarm switched off.

    Identifiers belonging to other entities are ignored rather than refused, so a caller may
    hand over a whole batch. A caller that handed over the wrong batch gets an empty result,
    which is the quiet failure worth naming here: this function cannot tell "no breaches" from
    "no rows for that entity", and nothing in a unit test can either.
    """
    seen: dict[IdentifierKind, set[str]] = {}
    for one in identifiers:
        if one.entity_id != entity_id:
            continue
        seen.setdefault(one.kind, set()).add(one.key_hash)
    breaches = [
        CapBreach(
            entity_id=entity_id,
            entity_type=entity_type,
            kind=kind,
            cap=cap,
            distinct=len(hashes),
        )
        for kind, hashes in seen.items()
        if (cap := cap_for(entity_type, kind)) is not None and len(hashes) > cap
    ]
    return tuple(sorted(breaches, key=lambda one: one.kind.value))


# ------------------------------------------------- priority for collisions (M14.6.3)
#: Which identifier wins when two of them disagree. Strongest first.
#:
#: The order is by how strongly two records sharing a value are the same *company*, and every
#: step down is a reason:
#:
#: - UEN: a register issues one per legal entity. Sharing one is being the same entity.
#: - TAX_ID: also register-issued, and not unique across jurisdictions, so two companies in two
#:   countries can share a number by coincidence.
#: - DOMAIN: a company controls its own domain, but free-mail domains are shared by everybody,
#:   which is why M14.3.7 asks for a blocklist rather than a low weight, and why a domain sits
#:   below a registration number rather than beside it.
#: - PHONE: a switchboard belongs to a company and a mobile belongs to a person, numbers are
#:   reassigned, and an agency's own number appears on its clients' records.
#: - EMAIL: identifies a person at best, and a shared mailbox identifies nobody at all.
#:
#: Written for companies. For a person the last two are arguably the other way round, because
#: an address is close to unique to somebody and a desk phone is shared; M14.7 is the leaf that
#: would settle it and it is not built, so this order is not applied to a person anywhere.
IDENTIFIER_PRIORITY: tuple[IdentifierKind, ...] = (
    IdentifierKind.UEN,
    IdentifierKind.TAX_ID,
    IdentifierKind.DOMAIN,
    IdentifierKind.PHONE,
    IdentifierKind.EMAIL,
)


def priority_of(kind: IdentifierKind) -> int:
    """Rank, zero being strongest. Refuses a kind with no rank rather than defaulting.

    A default would have to be chosen by somebody who has not seen the kind, and the only
    choices are "strongest", which lets an unranked identifier decide a merge, and "weakest",
    which silently stops it ever deciding one. Both are wrong in a way nothing reports, which
    is the argument `brain.memory.tiers.blast_radius` makes about an unclassified change.
    """
    if kind not in IDENTIFIER_PRIORITY:
        msg = (
            f"{kind.value!r} has no rank in the priority order, so nothing can say whether it "
            "beats another identifier; an unranked kind waits for somebody to rank it"
        )
        raise ValueError(msg)
    return IDENTIFIER_PRIORITY.index(kind)


class CollisionOutcome(enum.StrEnum):
    """What the priority order was able to say about a set of claims.

    `TIED_AT_THE_TOP` is the member that matters and it is deliberately not called `AMBIGUOUS`:
    the name says where the tie is, because the repair is to look at the two rows carrying the
    strongest identifier and not at the weaker evidence underneath them.
    """

    #: No claims at all. Not a collision.
    NOTHING_TO_DECIDE = "nothing to decide"
    #: Every claim names one entity. No priority was needed.
    AGREED = "agreed"
    #: The strongest kind present names exactly one entity, and that entity wins.
    DECIDED = "decided"
    #: The strongest kind present names more than one entity. Nothing here decides.
    TIED_AT_THE_TOP = "tied at the top"


@dataclass(frozen=True)
class Claim:
    """One identifier saying which entity a record belongs to.

    A kind and an entity, with no value and no digest. The collision is decided on rank and on
    which entity was named, and a value in scope at that call site is a value that ends up in
    the reason string explaining the decision.
    """

    kind: IdentifierKind
    entity_id: str

    def __post_init__(self) -> None:
        if not self.entity_id.strip():
            msg = "a claim naming no entity cannot win or lose a collision"
            raise ValueError(msg)


@dataclass(frozen=True)
class Collision:
    """What the priority order decided, and what it refused to decide.

    `entity_id` is None for everything except `AGREED` and `DECIDED`, so a caller that reads
    the field without reading the outcome gets nothing rather than a guess.
    """

    outcome: CollisionOutcome
    entity_id: str | None
    #: The strongest kind present, whether or not it decided anything. Carried on a tie as
    #: well, because "the tie is on the UEN" is the whole of what an operator needs.
    deciding_kind: IdentifierKind | None
    reason: str

    @property
    def decided(self) -> bool:
        return self.entity_id is not None


def resolve_collision(claims: Sequence[Claim]) -> Collision:
    """Which entity a set of disagreeing identifiers points at, or nothing (M14.6.3).

    **A tie at the top rank is not broken by a weaker identifier.** There is no loop down the
    order here and there is deliberately nowhere to put one: the strongest kind present is
    computed once, and if it names more than one entity the function returns
    `TIED_AT_THE_TOP` with no entity on it. See
    `A_TIE_AT_THE_TOP_IS_NOT_BROKEN_BY_A_WEAKER_IDENTIFIER`.

    Claims of weaker kinds that disagree with the winner are not reported and not counted. They
    are not evidence about anything once a stronger identifier has spoken, and a list of them
    would be read as one.
    """
    if not claims:
        return Collision(
            outcome=CollisionOutcome.NOTHING_TO_DECIDE,
            entity_id=None,
            deciding_kind=None,
            reason="no identifier claimed anything, so there is no collision to resolve",
        )
    strongest = min((one.kind for one in claims), key=priority_of)
    at_top = {one.entity_id for one in claims if one.kind is strongest}
    if len({one.entity_id for one in claims}) == 1:
        return Collision(
            outcome=CollisionOutcome.AGREED,
            entity_id=next(iter(at_top)),
            deciding_kind=strongest,
            reason="every identifier names the same entity, so no priority was needed",
        )
    if len(at_top) == 1:
        return Collision(
            outcome=CollisionOutcome.DECIDED,
            entity_id=next(iter(at_top)),
            deciding_kind=strongest,
            reason=(
                f"{strongest.value} is the strongest identifier present and it names one "
                "entity, so the weaker identifiers that disagree do not get a vote"
            ),
        )
    return Collision(
        outcome=CollisionOutcome.TIED_AT_THE_TOP,
        entity_id=None,
        deciding_kind=strongest,
        reason=(
            f"more than one entity claims the same {strongest.value}, which is the strongest "
            "identifier present; a weaker one cannot settle that, so a person does"
        ),
    )


# --------------------------------------------------- the review queue (M14.6.4)
class Strength(enum.IntEnum):
    """How much one field's agreement moves the answer, as a band rather than a number.

    An `IntEnum` and ordered, so "at least supporting" is a comparison, which is the shape
    `brain.memory.tiers.Tier` uses for the same reason. Bands rather than the weight itself
    because the number a reviewer would do arithmetic with is a threshold, thresholds belong to
    M14.3.3, and the calibration that would make a number mean anything is M14.3.5 and is not
    built. A band cannot be compared against a cutoff that does not exist.
    """

    #: The field disagreed, or agreeing on it is evidence for nothing.
    AGAINST = 0
    #: Agreed, and it barely moves the odds.
    WEAK = 1
    #: Agreed, and it at least doubles them.
    SUPPORTING = 2
    #: Agreed, and it multiplies them by more than ten.
    STRONG = 3
    #: Agreed, and on its own it is very nearly conclusive.
    DECISIVE = 4


#: The band boundaries, in log2 Bayes factors, which is the unit the Fellegi-Sunter model
#: M14.3.5 would calibrate produces: a weight of w multiplies the odds of a match by 2 ** w.
#:
#: Each figure is a statement about odds rather than a taste in numbers, which is what a test
#: can check it against:
#:
#: - one doubles the odds, which is the least that is worth calling evidence at all;
#: - four multiplies them by sixteen;
#: - ten multiplies them by more than a thousand, which is where one field agreeing is close
#:   to the whole answer.
SUPPORTING_WEIGHT: Final = 1.0
STRONG_WEIGHT: Final = 4.0
DECISIVE_WEIGHT: Final = 10.0


def strength_of(weight: float) -> Strength:
    """Which band a match weight falls in.

    Zero and below is `AGAINST` rather than `WEAK`, and the boundary is where it is because a
    weight of zero means the field agreeing told us nothing: the odds are unchanged, which is
    not weak evidence for a match, it is no evidence. Rendering it as weak support would put a
    row in front of a reviewer that reads as a small reason to merge.
    """
    if weight >= DECISIVE_WEIGHT:
        return Strength.DECISIVE
    if weight >= STRONG_WEIGHT:
        return Strength.STRONG
    if weight >= SUPPORTING_WEIGHT:
        return Strength.SUPPORTING
    if weight > 0.0:
        return Strength.WEAK
    return Strength.AGAINST


#: What each band says to a person. Exhaustive over `Strength` by test.
#:
#: Written as data rather than as a function with branches, for the reason
#: `brain.memory.tiers.BLAST_RADIUS` is: the property that matters is that every band has a
#: sentence, and that is visible here and would be buried in a match statement.
PLAIN_LANGUAGE: Mapping[Strength, str] = MappingProxyType(
    {
        Strength.DECISIVE: "agreed, and on its own that is very nearly the whole answer",
        Strength.STRONG: "agreed, and that counts heavily towards these being one thing",
        Strength.SUPPORTING: "agreed, and that supports these being one thing",
        Strength.WEAK: "agreed, and that barely moves it either way",
        Strength.AGAINST: "did not agree, and that counts against these being one thing",
    }
)

#: What a field name may look like. A machine name: lowercase, digits, underscores, and dots
#: for a qualified one.
#:
#: The same grammar as `brain.gate.abstain._STEP_RE`, and the same job. It is not a proof that
#: a value cannot be smuggled through the field slot, because "acme" is a legal field name; it
#: is what makes the three shapes most likely to be pasted there fail loudly instead of
#: rendering: an email address has an "@", a company name has spaces and capitals, a phone
#: number has digits at the front.
_FIELD_NAME_RE: Final = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")


@dataclass(frozen=True)
class Evidence:
    """One field, and how much its agreement or disagreement moves the answer.

    **There is no field for the value and adding one is the regression this type exists
    against.** It is `brain.gate.compose.Citation`'s rule: a name is a fact about the schema
    and a value is a fact about the record, and a reviewer is entitled to the first because
    they are being asked to judge the second without being shown it. A reviewer who could read
    the values in the queue would be reading records through a surface that never asked whether
    they may.
    """

    field: str
    #: A log2 Bayes factor. Positive is evidence for, negative is evidence against, zero is
    #: nothing. Not calibrated by anything in this repository; see `NOTHING_HERE_IS_PERSISTED`.
    weight: float

    def __post_init__(self) -> None:
        if not _FIELD_NAME_RE.match(self.field):
            msg = (
                f"{self.field!r} is not a field name. This slot is the only free-form string a "
                "reviewer is shown, so it is held to a machine-name grammar: an address, a "
                "company name or a number pasted here fails rather than rendering"
            )
            raise ValueError(msg)

    @property
    def strength(self) -> Strength:
        return strength_of(self.weight)

    def render(self) -> str:
        """The line a reviewer reads. A field name and a sentence, and no number.

        The weight is deliberately not in the output. A reviewer shown 6.2 next to 4.9 does
        arithmetic, and the arithmetic they do is a threshold they invented, on a scale nothing
        in this repository has calibrated.
        """
        return f"{self.field} {PLAIN_LANGUAGE[self.strength]}"


@dataclass(frozen=True)
class ReviewItem:
    """Two records a person is being asked to judge, and why the cascade could not.

    Both records are named, because a reviewer deciding whether two things are one thing has to
    know which two. That is exactly why `review_queue` admits an item only to somebody who
    reaches both: see `BOTH_HALVES_OR_THE_ITEM_IS_NOT_THERE`.

    No confidence and no score, for the reason `canonical.A_SCORE_IS_EVIDENCE_AND_NEVER_A_
    PERMISSION` gives. The per-field weights are here, which is where evidence belongs, and
    there is no total anywhere on the type for a caller to threshold on.
    """

    item_id: str
    left: SourceRef
    right: SourceRef
    evidence: tuple[Evidence, ...] = ()

    def explain(self) -> tuple[str, ...]:
        """Every line of evidence, strongest first, in plain language.

        Sorted by band and then by field name, so two reviewers looking at one item read the
        same lines in the same order and the order carries no information about anything else.
        """
        ordered = sorted(self.evidence, key=lambda one: (-int(one.strength), one.field))
        return tuple(one.render() for one in ordered)


@dataclass(frozen=True)
class ReviewQueue:
    """The items one reviewer may see, and nothing about the ones they may not.

    No count, no total, no truncation flag and no alarm carrying a number. The reason is
    `canonical.A_VIEW_CARRIES_NO_COUNT_OF_WHAT_IT_WITHHELD` and it applies harder to a queue
    than to a view, because a queue is a page and a page wants a total at the top of it.
    """

    reviewer_id: str
    items: tuple[ReviewItem, ...]


def review_queue(
    items: Sequence[ReviewItem], *, reviewer_id: str, reaches: MemberReach
) -> ReviewQueue:
    """The review queue as one person may see it (M14.6.4).

    `reaches` is `canonical.MemberReach`, the same protocol `resolved_view` filters members
    with, and it is called with a `SourceRef` and nothing else for the same reason: a reach
    decision must not be able to consult a weight. Both halves must pass. See
    `BOTH_HALVES_OR_THE_ITEM_IS_NOT_THERE`.

    Sorted by the records rather than by weight. Ordering a queue by how strong the evidence is
    would be useful and would also make the position of an item a statement about evidence the
    reviewer has not read yet; ordering by the record ids gives every reviewer the same order
    for the items they share.
    """
    visible = [one for one in items if reaches(one.left) and reaches(one.right)]
    return ReviewQueue(
        reviewer_id=reviewer_id,
        items=tuple(
            sorted(
                visible, key=lambda one: (one.left.sort_key(), one.right.sort_key(), one.item_id)
            )
        ),
    )


# ---------------------------------------------- unresolved behaviour (M14.6.5)
class UnresolvedReason(enum.StrEnum):
    """Why nothing was resolved. Recorded for the audit trail; never rendered.

    Two members and one public sentence. The pair is the whole point: a caller able to tell
    these apart from the outside has learnt whether there was one candidate or several. See
    `ONE_SENTENCE_FOR_EVERY_UNRESOLVED_REASON`.
    """

    #: More than one candidate survived the cascade.
    SEVERAL_CANDIDATES = "several candidates"
    #: One candidate, in the band between the thresholds M14.3.3 sets.
    BELOW_CONFIDENCE = "below confidence"


#: The one sentence every unresolved outcome renders.
#:
#: One constant referenced from one place rather than two literals that agree today, so the
#: property is checkable by identity, which is how `brain.gate.abstain.NOT_FOUND_TEXT` is
#: written. Two literals agree until somebody improves the wording of one of them, and that
#: improvement is a disclosure in a diff that reads as copy editing.
#:
#: It says what happened and offers the next step, and it carries no number and no name. "More
#: than one" would be true of one reason and false of the other, and a sentence that is true of
#: only one reason is a sentence that distinguishes them.
UNRESOLVED_TEXT: Final = "I could not tell which client this is, so I have not guessed."

#: What a review reference may look like. The same grammar as
#: `brain.gate.abstain._IDENTIFIER_RE`, because a reference somebody can be handed has to be
#: one an auditor can look up.
_REVIEW_REF_RE: Final = re.compile(r"^[A-Za-z0-9_.@-]{1,128}$")


@dataclass(frozen=True)
class UnresolvedNotice:
    """What the person who asked receives.

    **There is no reason field on this type**, in the same way and for the same reason as
    `brain.gate.abstain.AbstentionNotice`. A notice carrying why could be rendered by a channel
    adapter trying to be helpful, and the day it is, "several candidates" and "one unconvincing
    candidate" become two observable states. Two notices built from the two reasons are equal
    objects, which a test asserts in one line.

    The reference is quotable and carries no authority, like
    `brain.gate.compose.ComposedAnswer.trace_ref`: knowing it is not permission to open it, and
    entitlement decides who may. A reader who cannot open it sees a reference and no more,
    which is a real cost and is smaller than the alternative, which is a dead end.
    """

    review_ref: str

    def __post_init__(self) -> None:
        if not _REVIEW_REF_RE.match(self.review_ref):
            msg = (
                f"{self.review_ref!r} is not a review reference. The slot is held to a "
                "grammar because it is the only part of this notice a caller chooses, and a "
                "reference built by concatenating candidate ids would put them in front of "
                "somebody who may not see any of them"
            )
            raise ValueError(msg)

    @property
    def text(self) -> str:
        """The sentence. The same object for every notice, whatever produced it."""
        return UNRESOLVED_TEXT

    def render(self) -> str:
        return f"{UNRESOLVED_TEXT} A person can check it here: {self.review_ref}"


@dataclass(frozen=True)
class Unresolved:
    """The internal half: the notice, plus why, for the trace and the ledger.

    Not an exception. An unresolved entity is an outcome the resolver is supposed to produce,
    and raising it would put it on the failure path, get it caught by the failure handlers and
    counted in the failure metrics, which is the argument `brain.gate.abstain.Abstention`
    makes about itself.

    `detail` is read by an auditor and never rendered. It follows the same rule the rest of the
    system follows: names and reasons, never values.
    """

    reason: UnresolvedReason
    review_ref: str
    detail: str = ""

    def for_asker(self) -> UnresolvedNotice:
        """The only thing that may be said to the person who asked."""
        return UnresolvedNotice(review_ref=self.review_ref)


def unresolved_for(*, candidates: int, confident: bool, review_ref: str) -> Unresolved | None:
    """What to do when the cascade did not settle on one entity (M14.6.5).

    None means it settled: exactly one candidate, and the cascade was confident about it. Every
    other shape returns an `Unresolved`, which is the never-guess half of the leaf expressed as
    a return type rather than as a rule somebody has to remember.

    **The signature is the disclosure guard.** It takes a count and a boolean, so no candidate
    id, name or score is in scope at the only place this module could name one. A version
    taking the candidates themselves would work exactly as well and would put them one f-string
    away from the reason a channel renders.

    Zero candidates is not unresolved. Nothing matched, so the caller mints a new entity, and
    that is a decision this module has no part in. Returning an `Unresolved` for it would send
    a person a review item with nothing in it to review.
    """
    if candidates < 0:
        msg = "candidates counts candidates and cannot be negative"
        raise ValueError(msg)
    if candidates > 1:
        return Unresolved(
            reason=UnresolvedReason.SEVERAL_CANDIDATES,
            review_ref=review_ref,
            detail="more than one candidate survived the cascade",
        )
    if candidates == 1 and not confident:
        return Unresolved(
            reason=UnresolvedReason.BELOW_CONFIDENCE,
            review_ref=review_ref,
            detail="one candidate, in the band between the thresholds",
        )
    return None


# ------------------------------------------------------------------------- the gaps
def guardrail_gaps(
    caps: Mapping[tuple[EntityType, IdentifierKind], int] = IDENTIFIER_CAPS,
) -> tuple[str, ...]:
    """Every place the tables in this module disagree with each other or with the vocabulary.

    Four checks, and the fourth is the one worth having. The first three keep the maps and the
    enumerations in step. The fourth holds the cap table against the priority order: the
    stronger an identifier is, the fewer distinct values of it one entity may hold, and the two
    tables are written out separately so that changing one without the other fails here rather
    than agreeing by construction.

    `caps` is a parameter for the reason `brain.memory.tiers.tier_gaps` takes its changes as
    one. A detector that only fires when the tables disagree returns nothing on a healthy tree
    whether or not it is still doing anything, so on a healthy tree a test of it is a test of
    the tree. A mutation run found exactly that: disabling the fourth check survived, because
    the only assertion anybody had written was that this function returns nothing today. The
    parameter is how a test hands it two tables that do disagree.
    """
    gaps: list[str] = []

    for band in Strength:
        if band not in PLAIN_LANGUAGE:
            gaps.append(
                f"the {band.name.lower()} band has no sentence, so a reviewer would be shown a "
                "row with no explanation on it"
            )
    for rule in BlockRule:
        if rule not in BLOCK_REASONS:
            gaps.append(f"{rule.value} has no reason, so a refusal on it explains nothing")
    for kind in IdentifierKind:
        if kind not in IDENTIFIER_PRIORITY:
            gaps.append(
                f"{kind.value} has no rank, so nothing can say whether it beats another "
                "identifier in a collision"
            )

    capped = sorted(caps.items(), key=lambda pair: pair[0][1].value)
    for (left_type, left_kind), left_cap in capped:
        for (right_type, right_kind), right_cap in capped:
            if left_type is not right_type or left_kind is right_kind:
                continue
            if priority_of(left_kind) < priority_of(right_kind) and left_cap > right_cap:
                gaps.append(
                    f"{left_kind.value} outranks {right_kind.value} and is capped higher, so "
                    "the stronger identifier is allowed more distinct values than the weaker "
                    "one, which is the opposite of what a cap is for"
                )
    return tuple(gaps)
