"""One cascade over three kinds of entity, and the comparisons each kind may not be given.

The load-bearing claim of M14.7 is not that people and projects can be resolved. It is that
they are resolved by the *same* cascade, so the stage ordering that makes a hard identifier
impossible to outvote is one implementation rather than three. Everything a profile does is
subtract, and the tests below are mostly about what each type cannot be merged on.

**The privacy leaf is two walls and only one of them is in this module.**
`brain.core.projection.NEVER_PROJECT` refuses to store an email address, a telephone number or
an address, so a projected record cannot carry one and a profile cannot name a field that
would; that refusal is asserted here against the real denylist rather than against a list of
our own. The second wall is that `observe` returns a type with nowhere to put a value.

Task ids: M14.7.1, M14.7.2, M14.7.3
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.connectors import freshdesk, hubspot, laravel, lark_base, xero
from brain.connectors.projection import ProjectedRecord
from brain.core.projection import NEVER_PROJECT, is_forbidden
from brain.resolution.canonical import EntityType, IdentifierKind, ResolutionError
from brain.resolution.cascade import Decision, Feature, Observation, Stage
from brain.resolution.entities import (
    COMPANY_PROFILE,
    PERSON_PROFILE,
    PROFILES,
    PROJECT_PROFILE,
    EntityProfile,
    observe,
    profile_for,
    profile_gaps,
    resolve_pair,
    sources_named,
)

NOW = datetime(2026, 9, 7, tzinfo=UTC)
PEPPER = "a-deployment-secret"

#: Every connector name this repository declares, read from the connector modules rather than
#: retyped, so a profile naming a source that does not exist fails here.
CONNECTOR_NAMES = frozenset(
    {
        hubspot.CONNECTOR_NAME,
        xero.CONNECTOR_NAME,
        laravel.CONNECTOR_NAME,
        freshdesk.FRESHDESK,
        lark_base.LARK_BASE,
    }
)


def record(source: str, source_id: str, **fields: Any) -> ProjectedRecord:
    return ProjectedRecord(
        source=source,
        entity="contact",
        source_id=source_id,
        last_seen_at=NOW,
        fields=fields,
    )


def strings_on(observation: Observation) -> set[str]:
    """Every string anywhere on an observation, so a raw value has nowhere to hide.

    Walked rather than listed field by field, because a field added later would not be in a
    list and the whole point of the assertion is that nothing anywhere on the type holds a
    contact detail.
    """
    found: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(key)
                walk(item)
        elif isinstance(value, list | tuple | set | frozenset):
            for item in value:
                walk(item)
        else:
            declared = getattr(value, "__dataclass_fields__", {})
            for name in declared:
                walk(getattr(value, name))

    walk(observation)
    return found


# ---------------------------------------------------------- a profile only subtracts
def test_a_profile_can_only_take_comparisons_away() -> None:
    """**The property that makes one cascade over three types safe.**

    A profile that could add a comparison would be a second way to decide a match, sitting
    beside the cascade and reviewed less carefully. Every profile is therefore held to being a
    subset of the company one on all three axes, and `profile_gaps` is the check rather than
    this test's own arithmetic, so the same check runs anywhere the profiles are read.

    The control is the widened profile below: a check that has only ever been seen to pass is a
    check nobody has tested.

    A fourth check was added after two mutations survived: a profile that admits a comparison
    and names no source for it reads as the decision and is inert until somebody adds the
    source. Both widenings are exercised below.

    Delete this and a person profile grows a domain digest because somebody wanted more
    matches, and a company's staff become one person."""
    assert profile_gaps() == ()
    for profile in PROFILES.values():
        assert profile.identifiers <= COMPANY_PROFILE.identifiers
        assert profile.fields <= COMPANY_PROFILE.fields
        assert profile.auto_merge_stages <= COMPANY_PROFILE.auto_merge_stages
        assert profile.identifiers <= set(profile.identifier_fields) | profile.live_identifiers
        assert profile.fields <= set(profile.field_sources)

    inert = profile_gaps(
        {
            **PROFILES,
            EntityType.PROJECT: replace(PROJECT_PROFILE, fields=COMPANY_PROFILE.fields),
        }
    )
    assert any("names no source" in one for one in inert)

    widened = EntityProfile(
        entity_type=EntityType.PERSON,
        identifiers=frozenset(IdentifierKind),
        fields=frozenset(),
        auto_merge_stages=frozenset({Stage.HUMAN_REVIEW}),
        sources=("hubspot",),
        name_field="name",
        live_identifiers=frozenset(IdentifierKind),
    )
    findings = profile_gaps({EntityType.PERSON: widened})
    assert any("auto-merge stage" in one for one in findings)
    assert any("company" in one and "no profile" in one for one in findings)


def test_a_type_with_no_profile_is_refused_rather_than_given_the_widest_one() -> None:
    """The convenient thing to pass for an unprofiled type is the company profile, which is the
    widest, so the default has to be a refusal.

    The mapping is a parameter precisely so this can be shown: every declared type has a
    profile, so a check written against the constant alone could never be seen to fail.

    Delete this and the next entity type added resolves with every comparison the cascade
    has."""
    with pytest.raises(ResolutionError, match="no profile"):
        profile_for(EntityType.PERSON, {EntityType.COMPANY: COMPANY_PROFILE})

    for entity_type in EntityType:
        assert profile_for(entity_type).entity_type is entity_type


def test_every_source_a_profile_names_is_a_connector_that_exists() -> None:
    """A misspelled connector name is a type that silently never resolves records from the
    source it was written for, and nothing reports it: the profile is right, the records arrive
    under a different string, and the two never meet.

    Held against the connector modules' own constants rather than a list retyped here, which is
    what makes it a check rather than a second copy.

    Delete this and `lark` in place of `lark_base` costs one of M14.7.1's three sources."""
    assert set(sources_named()) <= CONNECTOR_NAMES
    assert set(PERSON_PROFILE.sources) == {
        hubspot.CONNECTOR_NAME,
        freshdesk.FRESHDESK,
        lark_base.LARK_BASE,
    }


# ------------------------------------------------------------------- people (M14.7.1)
def test_a_person_carries_no_domain_so_two_colleagues_do_not_become_one_person() -> None:
    """**The single most expensive mistake available here.**

    Twenty people at one company share one domain. A person profile admitting a domain digest
    would merge a company's whole staff into one entity, readable by everybody who reaches any
    of them. The repair is that the digest is never computed, so there is no weight to tune and
    no branch to widen.

    The sibling is the company profile over the same record, which does carry the domain: this
    is a narrowing for one type and not a decision that domains are worthless.

    Delete this and the person profile can be given a domain to improve its recall, which is
    what somebody will want the first time the review queue is long."""
    left = record("hubspot", "1", name="Tan Wei Ming", domain="acme.com")
    right = record("freshdesk", "2", name="Tan Wei Ming", domain="acme.com")

    person = observe(left, PERSON_PROFILE, pepper=PEPPER)
    assert IdentifierKind.DOMAIN not in person.observation.identifiers

    other = observe(right, PERSON_PROFILE, pepper=PEPPER)
    decided = resolve_pair(person.observation, other.observation, PERSON_PROFILE)
    assert decided.decision is Decision.TO_REVIEW

    company = observe(left, COMPANY_PROFILE, pepper=PEPPER)
    assert IdentifierKind.DOMAIN in company.observation.identifiers


def test_a_person_verified_by_a_source_still_carries_only_what_the_profile_admits() -> None:
    """`verified` is a fact the connector asserts, so it is a parameter, and a parameter is a
    way in. Intersecting it with the profile is what stops it being one.

    Without that intersection a connector could mark a domain verified for a contact and the
    person would carry a verified employer domain, which is stage one deciding on exactly the
    comparison the profile removed.

    Delete this and `verified` becomes the way round every profile in the module."""
    contact = record("hubspot", "1", name="Tan Wei Ming", domain="acme.com")

    observed = observe(
        contact,
        PERSON_PROFILE,
        pepper=PEPPER,
        verified=frozenset({IdentifierKind.DOMAIN, IdentifierKind.EMAIL}),
    )

    assert observed.observation.verified == frozenset()
    assert observed.observation.is_hard(IdentifierKind.DOMAIN) is False


def test_two_people_who_merely_look_alike_go_to_a_person_and_two_companies_merge() -> None:
    """Stage three assumes two similar names are one thing spelled twice. That holds for
    registered companies and fails for people, because many people share a name and the
    similarity between two spellings of a common name is indistinguishable from the similarity
    between two people who have it.

    The same pair of names is run under both profiles, so this is a statement about the profile
    rather than about the names: the company profile merges them and the person profile asks.

    Delete this and a person is merged on a name similarity, which is the merge nobody goes
    back and checks because it looks so plausible."""
    left = observe(
        record("hubspot", "1", name="Tan Ah Kow Trading"), PERSON_PROFILE, pepper=PEPPER
    ).observation
    right = observe(
        record("freshdesk", "2", name="Tan Ah Kow Tradings"), PERSON_PROFILE, pepper=PEPPER
    ).observation

    as_company = resolve_pair(left, right, COMPANY_PROFILE)
    assert as_company.decision is Decision.MATCHED
    assert as_company.stage is Stage.SIMILARITY

    as_person = resolve_pair(left, right, PERSON_PROFILE)
    assert as_person.decision is Decision.TO_REVIEW
    assert as_person.stage is Stage.HUMAN_REVIEW
    assert as_person.confidence is None
    assert as_person.evidence == as_company.evidence
    assert Stage.SIMILARITY not in PERSON_PROFILE.auto_merge_stages
    assert PERSON_PROFILE.fields == frozenset(), "a country belongs to the employer, not to them"


def test_one_person_across_the_three_sources_the_leaf_names_resolves_by_their_address() -> None:
    """M14.7.1 asks for the cascade across HubSpot, Freshdesk and Lark, and this is that,
    end to end: three projected records, one live address each, and the pairs the cascade
    decides.

    The positive half matters as much as the refusals above. A person profile that refused
    everything would satisfy every other test in this file, and what makes this one a system is
    that the same name with the same address merges while the same name with a different one
    does not.

    Delete this and the person profile can be narrowed until nothing resolves, which is a
    change nobody would notice from the refusal tests."""
    mine = "wei.ming@acme.com"
    fields = {"name": "Tan Wei Ming"}
    across = [
        observe(
            record(source, str(index), **fields),
            PERSON_PROFILE,
            pepper=PEPPER,
            live={IdentifierKind.EMAIL: mine},
        ).observation
        for index, source in enumerate(PERSON_PROFILE.sources)
    ]

    for left, right in ((across[0], across[1]), (across[1], across[2]), (across[0], across[2])):
        decided = resolve_pair(left, right, PERSON_PROFILE)
        assert decided.decision is Decision.MATCHED, (left.record, right.record)
        assert decided.stage is Stage.CORROBORATED_NAME

    namesake = observe(
        record(lark_base.LARK_BASE, "9", **fields),
        PERSON_PROFILE,
        pepper=PEPPER,
        live={IdentifierKind.EMAIL: "someone.else@acme.com"},
    ).observation
    assert resolve_pair(across[0], namesake, PERSON_PROFILE).decision is Decision.TO_REVIEW


# ----------------------------------------------------------------- projects (M14.7.2)
def test_nothing_auto_merges_two_projects_at_any_stage() -> None:
    """**A project has no register and nothing that corroborates its name.**

    There is no identifier a project carries across two systems, and the corroborating fields
    the cascade has are the client's country and postcode, which every project of one client
    shares. So "Website Revamp" and "Website Redesign" for one client would corroborate each
    other on their client's address.

    Tested at stage one as well as stage three, with an identifier the profile would never have
    produced, because the profile is applied to the cascade's answer and not only to its input:
    a hand-built observation must not be able to merge two projects either.

    Delete this and two projects for one client are merged on a name, and the reader of one
    gets the other's."""
    named = observe(record("lark_base", "1", name="Website Revamp"), PROJECT_PROFILE, pepper=PEPPER)
    similar = observe(
        record("laravel", "2", name="Website Revamps"), PROJECT_PROFILE, pepper=PEPPER
    )

    assert PROJECT_PROFILE.identifiers == frozenset()
    assert PROJECT_PROFILE.fields == frozenset()
    assert PROJECT_PROFILE.auto_merge_stages == frozenset()
    assert named.observation.identifiers == {}
    assert named.observation.fields == {}

    decided = resolve_pair(named.observation, similar.observation, PROJECT_PROFILE)
    assert decided.decision is Decision.TO_REVIEW

    digest = "c" * 64
    forced_left = Observation(
        record=named.observation.record,
        name=named.observation.name,
        identifiers={IdentifierKind.UEN: digest},
    )
    forced_right = Observation(
        record=similar.observation.record,
        name=similar.observation.name,
        identifiers={IdentifierKind.UEN: digest},
    )
    assert resolve_pair(forced_left, forced_right, PROJECT_PROFILE).decision is Decision.TO_REVIEW
    assert resolve_pair(forced_left, forced_right, COMPANY_PROFILE).decision is Decision.MATCHED


def test_a_refused_merge_is_a_question_and_never_a_conclusion() -> None:
    """`Decision.NOT_MATCHED` says the cascade concluded the two records are different things,
    and a profile refusing to auto-merge concluded no such thing: the evidence was real and this
    type is not one it is sufficient for.

    A caller treating the two alike would either write a negative link or drop the pair
    entirely, and both lose the one thing worth keeping, which is that a person should look.

    Delete this and a profile refusal is recorded as a decision that the records are
    different."""
    left = observe(record("lark_base", "1", name="Website Revamp"), PROJECT_PROFILE, pepper=PEPPER)
    right = observe(record("laravel", "2", name="Website Revamps"), PROJECT_PROFILE, pepper=PEPPER)

    decided = resolve_pair(left.observation, right.observation, PROJECT_PROFILE)

    assert decided.decision is not Decision.NOT_MATCHED
    assert decided.confidence is None
    assert decided.review_item("item-1").evidence == decided.evidence


# ------------------------------------------------------------------- privacy (M14.7.3)
def test_a_profile_cannot_read_a_field_the_projection_may_never_store() -> None:
    """**The first of the two walls, and it is not this module's.**

    `brain.core.projection.NEVER_PROJECT` refuses `email`, `phone` and `address` by name and by
    shape, so those values cannot be in a projected record at all. A profile that named one as
    a source would be a profile describing a field that can never arrive, and the tempting
    repair for that is to relax the denylist.

    Asserted against the real denylist rather than a copy, and with the refusal shown to fire,
    so this is a check on the profiles rather than a restatement of the constant.

    Delete this and a profile reads `email` from the projection, and the pressure moves to the
    one list in this repository that must not be edited."""
    for profile in PROFILES.values():
        for column in profile.identifier_fields.values():
            assert not is_forbidden(column), column
    assert PERSON_PROFILE.live_identifiers == frozenset(
        {IdentifierKind.EMAIL, IdentifierKind.PHONE}
    )
    assert {"email", "phone", "address"} <= NEVER_PROJECT

    with pytest.raises(ResolutionError, match="refuses to store"):
        EntityProfile(
            entity_type=EntityType.PERSON,
            identifiers=frozenset({IdentifierKind.EMAIL}),
            fields=frozenset(),
            auto_merge_stages=frozenset(),
            sources=("hubspot",),
            name_field="name",
            identifier_fields={IdentifierKind.EMAIL: "email"},
        )


def test_no_raw_value_handed_in_live_survives_anywhere_on_an_observation() -> None:
    """**The second wall.** A join key is computed from a contact detail, so the value is in
    scope for the length of one function call, and the claim is that it leaves nowhere.

    Walked over every string on the returned object rather than checked field by field, because
    a field added later would not be in a list and the assertion is that nothing anywhere holds
    it. The digest is asserted present as well: an observation that dropped the address entirely
    would pass the first half and would have lost the join key the leaf is about.

    Delete this and the next convenience puts the address on the observation "for the review
    queue", which is the exact sentence M14.6.4 refuses."""
    address = "wei.ming@acme.com"
    number = "+6561234567"

    observed = observe(
        record("hubspot", "1", name="Tan Wei Ming"),
        PERSON_PROFILE,
        pepper=PEPPER,
        live={IdentifierKind.EMAIL: address, IdentifierKind.PHONE: number},
    )

    everywhere = strings_on(observed.observation)
    assert address not in everywhere
    assert number not in everywhere
    assert IdentifierKind.EMAIL in observed.observation.identifiers
    assert IdentifierKind.PHONE in observed.observation.identifiers
    assert all(len(one) == 64 for one in observed.observation.identifiers.values())


def test_a_join_key_without_the_pepper_joins_to_nothing() -> None:
    """The digest is keyed, so a copy of the identifier table taken without the deployment
    secret cannot be joined against a list of addresses.

    It is `canonical.identifier_hash`'s property and it is asserted through `observe` because
    this is the function that decides what gets hashed: a route that hashed the value some other
    way, or forgot the pepper, would produce a table that looks encrypted and is a mailing list.

    Delete this and a refactor can drop the pepper from this path without any test noticing,
    because every other test here passes one consistently."""
    contact = record("hubspot", "1", name="Tan Wei Ming")
    live = {IdentifierKind.EMAIL: "wei.ming@acme.com"}

    ours = observe(contact, PERSON_PROFILE, pepper=PEPPER, live=live)
    theirs = observe(contact, PERSON_PROFILE, pepper="a-different-deployment", live=live)

    assert ours.observation.identifiers != theirs.observation.identifiers


def test_a_live_value_for_a_kind_the_profile_does_not_fetch_live_is_refused() -> None:
    """Ignoring it would make `live` a parameter that silently does nothing for some kinds, and
    a caller would believe a join key is being computed when it is not. Admitting it would make
    `live` the way round every profile here.

    The sibling is the kind the profile does fetch live, which has to work, or the refusal is
    satisfied by a parameter that never does anything.

    Delete this and a caller hands in a domain for a person and gets no error and no digest."""
    contact = record("hubspot", "1", name="Tan Wei Ming")

    with pytest.raises(ResolutionError, match="does not fetch live"):
        observe(contact, PERSON_PROFILE, pepper=PEPPER, live={IdentifierKind.DOMAIN: "acme.com"})

    fine = observe(
        contact, PERSON_PROFILE, pepper=PEPPER, live={IdentifierKind.EMAIL: "wm@acme.com"}
    )
    assert IdentifierKind.EMAIL in fine.observation.identifiers


def test_a_shared_mailbox_is_dropped_and_the_report_names_the_rule_and_not_the_value() -> None:
    """The blocklist is `guardrails`' and is reached through `cascade.usable_identifiers`, not
    reimplemented here, so there is one shared-mailbox rule.

    What this adds is that the refusal survives the trip through `observe` in a shape that can
    be logged whole: `Dropped` names the rule and has no field for the value or for the part of
    it that matched.

    Delete this and an ingest path grows its own blocklist, and the two disagree about `info@`
    on the day one of them is edited."""
    observed = observe(
        record("hubspot", "1", name="Acme Trading"),
        PERSON_PROFILE,
        pepper=PEPPER,
        live={IdentifierKind.EMAIL: "info@acme.com"},
    )

    assert observed.observation.identifiers == {}
    assert len(observed.dropped) == 1
    assert observed.dropped[0].kind is IdentifierKind.EMAIL
    assert "acme" not in observed.dropped[0].reason
    assert not any(hasattr(observed.dropped[0], one) for one in ("value", "matched"))


def test_a_field_the_profile_does_not_name_contributes_nothing() -> None:
    """Nothing here iterates a record's fields looking for something useful, which is the
    fail-closed direction: a projection that grows a column does not become a comparison.

    The cost is that a genuinely useful field has to be admitted deliberately, and the benefit
    is that no field arrives by accident. The postcode is the example because it is admissible
    for a company and not for a person, so the same column means two different things depending
    on the profile.

    Delete this and a new projected column silently starts corroborating names."""
    with_postcode = record("hubspot", "1", name="Tan Wei Ming", postcode="238801")

    person = observe(with_postcode, PERSON_PROFILE, pepper=PEPPER)
    assert Feature.POSTCODE not in person.observation.fields

    company = observe(with_postcode, COMPANY_PROFILE, pepper=PEPPER)
    assert company.observation.fields[Feature.POSTCODE] == "238801"
