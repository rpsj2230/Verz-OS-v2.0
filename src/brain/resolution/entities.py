"""The same cascade applied to people and to projects, which mostly means deciding what it may
not be told about them.

`brain.resolution.cascade` was written for companies and M14.7 asks for it to be applied to
people and to projects. The tempting reading is that this module is where a second cascade
lives, tuned for each type. It is the opposite: **there is one cascade, and a profile decides
which comparisons ever reach it.** A pair of person records that carry no domain digest cannot
be merged on a domain by any code path, and that is a stronger guarantee than a branch which
skips the domain for people, because the branch is one edit away from being widened and the
absent digest is not there to compare.

**A profile narrows and never widens, and that is the property to check.** Every profile's
admissible identifiers are a subset of the company profile's, every profile's admissible
corroborating fields are a subset of it too, and the stages at which a type may auto-merge are
a subset of the stages the cascade has. There is no field on `EntityProfile` that could add a
comparison the company profile does not already allow. See `THE_PROFILE_NARROWS_AND_NEVER_WIDENS`.

**A domain identifies an employer and never a person (M14.7.1).** This is the single most
expensive mistake available here. Twenty people at one company share `acme.com`, so a person
profile that admitted a domain digest would merge a company's entire staff into one person, and
that person would then be readable by everybody who reaches any of them. It is
`guardrails`'s shared-mailbox argument with the domain half instead of the local half, applied
to a different entity type, and the repair is the same one: the value never becomes a join key.
See `A_DOMAIN_IDENTIFIES_AN_EMPLOYER_AND_NEVER_A_PERSON`.

**Two people can share a name and two companies cannot share a registration (M14.7.1).** Name
similarity is stage three's evidence and it is far weaker for people than for companies: "Tan
Wei Ming" is a name many people have, and the trigram similarity of two spellings of one common
name is indistinguishable from the similarity of two people who happen to share it. So a person
may auto-merge on an identifier or on a corroborated name, and never on a similarity alone. See
`TWO_PEOPLE_CAN_SHARE_A_NAME_AND_A_COMPANY_CANNOT_SHARE_A_REGISTRATION`.

**A project has no register and nothing that corroborates its name (M14.7.2).** There is no
identifier a project carries across two systems, and the fields that corroborate a company name
are exactly the fields every project of one client shares: the country and the postcode of the
client. So "Website Revamp" and "Website Redesign" for one client would corroborate each other
on the client's own address. The project profile therefore admits no identifier and no
corroborating field, which leaves nothing that can auto-merge two projects, and every candidate
pair of projects goes to a person. That is not a placeholder for a better rule; it is the
honest state of the evidence available. See
`A_PROJECT_HAS_NO_REGISTER_AND_NOTHING_THAT_CORROBORATES_ITS_NAME`.

**Hashed join keys only, and there are two walls rather than a rule (M14.7.3).** The first is
not this module's: `brain.core.projection.NEVER_PROJECT` refuses `email`, `phone` and `address`
by name and by shape, so a `ProjectedRecord` cannot hold a contact value at all and no profile
here can name a field that would. The second is this module's: the identifier values that are
therefore fetched live are handed to `observe` and become digests inside it, and what it returns
is a `cascade.Observation`, which has digests, a normalised name and two opaque tokens and no
field an address or a telephone number would fit in. So a contact record cannot be stored, and
the value that is briefly in scope while a join key is computed has nowhere on the far side to
land. See `A_JOIN_KEY_ON_A_PERSON_IS_A_CONTACT_DETAIL_AND_IS_FETCHED_LIVE` and
`THERE_IS_NOWHERE_ON_AN_OBSERVATION_TO_PUT_A_CONTACT_RECORD`.

**A field the profile does not name is not read at all.** The mapping from a connector's field
names to identifier kinds is declared per profile, so a projection that grew a `home_address`
column does not become a comparison because somebody added a kind for it. Everything not named
is ignored, which is the fail-closed direction: the cost is that a genuinely useful field has to
be added deliberately, and the benefit is that no field arrives by accident.

Rejected: a per-type cascade with its own thresholds and its own weights. It is the obvious
design, it gives each type the treatment it deserves, and it is three copies of the four stages.
The stage ordering is the whole safety argument of `cascade`, and three copies of it are three
places for a hard identifier to stop outranking a pile of weak agreements.

Rejected: passing the profile into `cascade` as a parameter. That would put the entity type
inside the function that decides matches, which is the same coupling in a nicer shape: the
cascade would then have a branch per type and the guarantee would be that the branch is right
rather than that the comparison is absent.

Scope: domain logic. Nothing here opens a connection, reads a clock or writes a row. The pepper
is a parameter for the reason `canonical.identifier_hash` takes one.

Task ids: M14.7.1, M14.7.2, M14.7.3
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.connectors.projection import ProjectedRecord
from brain.core.projection import is_forbidden
from brain.resolution.canonical import (
    EntityType,
    IdentifierKind,
    ResolutionError,
    SourceRef,
)
from brain.resolution.cascade import (
    DECLARED_THRESHOLDS,
    DECLARED_WEIGHTS,
    FIELD_FEATURES,
    CascadeResult,
    Decision,
    Dropped,
    Feature,
    Observation,
    Stage,
    Thresholds,
    WeightTable,
    cascade,
    usable_identifiers,
)
from brain.resolution.normalise import normalise_name

# ------------------------------------------------------------------ written-down reasons
#: The property that makes one cascade over three types safe.
THE_PROFILE_NARROWS_AND_NEVER_WIDENS: Final = (
    "A profile can only take comparisons away. Its identifiers are a subset of the company "
    "profile's, its corroborating fields are a subset, and the stages at which it may "
    "auto-merge are a subset of the cascade's own. There is no field on EntityProfile that "
    "adds anything, so a profile cannot be the route by which a new comparison arrives, and "
    "the worst a wrong profile can do is refuse a merge that should have happened. That is the "
    "direction this system fails in everywhere else: a missed link is two entities that stay "
    "two, and a wrong link is two permission surfaces joined together."
)

#: Why a person carries no domain digest.
A_DOMAIN_IDENTIFIES_AN_EMPLOYER_AND_NEVER_A_PERSON: Final = (
    "Twenty people at one company share one domain. A person profile that admitted a domain "
    "digest would merge a company's entire staff into a single person entity, and every reader "
    "who reaches any one of them would then reach a record assembled from all twenty. It is "
    "guardrails' shared-mailbox argument with the domain half rather than the local half, and "
    "the repair is the same: the value never becomes a join key, so there is no weight to tune "
    "and no branch to widen. The email address as a whole is kept, because the whole address "
    "identifies one person even when its domain identifies a mail provider, which is the "
    "distinction cascade.usable_identifiers already draws."
)

#: Why a person may not be merged on a name similarity.
TWO_PEOPLE_CAN_SHARE_A_NAME_AND_A_COMPANY_CANNOT_SHARE_A_REGISTRATION: Final = (
    "Stage three merges on trigram similarity between two names that differ, and the "
    "assumption underneath it is that two similar names are probably one thing with two "
    "spellings. That assumption holds for registered companies, whose names are close to "
    "unique within a jurisdiction, and fails for people: many people share a name, and the "
    "similarity between two spellings of one common name is indistinguishable from the "
    "similarity between two people who have it. So a person auto-merges on an identifier or on "
    "a corroborated name, and a similarity alone goes to a reviewer. The same argument removes "
    "the corroborating fields: a country and a postcode belong to a person's employer, so in a "
    "single-jurisdiction estate the country agrees for every pair and stage two becomes 'the "
    "names agree' by the corroborant rather than by the name. What corroborates a person's "
    "name is their address or their number, and both of those are identifier agreements the "
    "cascade already treats as non-name features. The cost is a longer queue, which is the "
    "cost this system chooses everywhere it has the choice."
)

#: Why nothing auto-merges two projects.
A_PROJECT_HAS_NO_REGISTER_AND_NOTHING_THAT_CORROBORATES_ITS_NAME: Final = (
    "A project has no identifier that crosses two systems: there is no register, no domain and "
    "no address that belongs to the project rather than to its client. The corroborating "
    "fields that work for a company are exactly the ones every project of one client shares, "
    "so corroborating a project name with a country or a postcode corroborates it with its "
    "client's, and 'Website Revamp' and 'Website Redesign' for one client would agree on it. "
    "The project profile therefore admits no identifier and no corroborating field, which "
    "leaves stage one empty, stage two unreachable and stage three refused, so every candidate "
    "pair reaches a person. That is the honest state of the evidence rather than a placeholder: "
    "the thing that would change it is a project code carried by both systems, and nothing in "
    "this repository has one."
)

#: Why a person's join keys never come out of the projection.
A_JOIN_KEY_ON_A_PERSON_IS_A_CONTACT_DETAIL_AND_IS_FETCHED_LIVE: Final = (
    "The two identifiers that identify a person are an email address and a telephone number, "
    "and both are on brain.core.projection.NEVER_PROJECT: they may be fetched and may not be "
    "stored. That is decided a layer above this one and it is the reason the person profile "
    "maps no projected field for either. The values arrive as an argument to observe, from a "
    "connector that fetched them for this call, and leave it as digests; nothing here writes "
    "them anywhere and nothing on the far side can hold them. So the privacy rule is not that "
    "this module is careful with contact details. It is that the projection cannot hold one, "
    "and the one place a value exists at all is a function whose output has no room for it. A "
    "profile that named a projected field for a denylisted kind is refused at construction, "
    "which is what stops the second wall being quietly moved to the first."
)

#: Why the privacy rule is a shape rather than a discipline.
THERE_IS_NOWHERE_ON_AN_OBSERVATION_TO_PUT_A_CONTACT_RECORD: Final = (
    "M14.7.3 asks for hashed join keys only and never full contact records. Written as a rule "
    "about what callers should do it lasts until somebody needs a value for a reason. Written "
    "as a shape it does not need anybody's cooperation: observe returns an Observation, whose "
    "identifiers are digests checked against a hex pattern, whose name is a normalised key, and "
    "whose remaining two slots hold opaque tokens the cascade compares for equality and cannot "
    "read. There is no field on it for an address, a telephone number or an address line, so a "
    "contact record cannot be passed through this function; it can only be refused by the "
    "constructor on the far side. canonical.Identifier and er.identifier refuse a non-digest "
    "again at the two layers below, which is the same rule at three depths rather than three "
    "rules."
)


# ---------------------------------------------------------------------- the profile
@dataclass(frozen=True)
class EntityProfile:
    """What the cascade may be told about one kind of entity.

    Three fields and all three subtract. `identifiers` is which join keys may be computed at
    all, `fields` is which corroborating comparisons may be carried, and `auto_merge_stages` is
    which stages may produce a match rather than a review. Nothing here adds a comparison, which
    is `THE_PROFILE_NARROWS_AND_NEVER_WIDENS` stated as a shape.

    `sources` is the connectors this type is observed on. It is documentation with a check
    behind it rather than a filter: `observe` does not refuse a record from an unlisted source,
    because a connector added tomorrow would then silently stop resolving, and a test holds the
    listed names against the connector registry so the list cannot name one that does not exist.
    """

    entity_type: EntityType
    identifiers: frozenset[IdentifierKind]
    fields: frozenset[Feature]
    auto_merge_stages: frozenset[Stage]
    sources: tuple[str, ...]
    #: Which projected field holds the name. Required: an entity with no name has nothing to
    #: normalise and would reach the cascade with an unusable key on every record.
    name_field: str
    #: Which projected field holds each admissible identifier. A kind with no field here is
    #: never read from the record, which is the same refusal as leaving it out of `identifiers`
    #: and is here so a profile can admit a kind before a connector exposes it.
    identifier_fields: Mapping[IdentifierKind, str] = MappingProxyType({})
    #: The kinds whose value may never be stored and therefore arrives live (M14.7.3).
    #:
    #: `brain.core.projection.NEVER_PROJECT` decides which those are, not this module, and a
    #: profile that mapped a projected field for one of them is refused at construction.
    live_identifiers: frozenset[IdentifierKind] = frozenset()
    #: Which projected field holds each corroborating comparison token.
    field_sources: Mapping[Feature, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.name_field.strip():
            msg = (
                f"the {self.entity_type.value} profile names no field for the name; every "
                "record would reach the cascade with nothing to normalise"
            )
            raise ResolutionError(msg)
        unknown = sorted(one.value for one in self.fields if one not in FIELD_FEATURES)
        if unknown:
            msg = (
                f"{', '.join(unknown)} is not a corroborating field. A name feature here would "
                "let a name corroborate itself and an identifier here would skip the blocklist"
            )
            raise ResolutionError(msg)
        admitted = self.identifiers
        stray = sorted(
            one.value
            for one in (set(self.identifier_fields) | self.live_identifiers)
            if one not in admitted
        )
        if stray:
            msg = (
                f"the {self.entity_type.value} profile names a source for {', '.join(stray)}, "
                "which it does not admit; a source for an inadmissible kind reads as though "
                "the kind were in use and is the shape a widening arrives in"
            )
            raise ResolutionError(msg)
        both = sorted(one.value for one in set(self.identifier_fields) & self.live_identifiers)
        if both:
            msg = (
                f"{', '.join(both)} is read from the projection and handed in live; two "
                "sources for one join key are two digests for one value, and whichever the "
                "cascade sees first decides whether two records join"
            )
            raise ResolutionError(msg)
        stored = sorted(
            f"{one.value}={column}"
            for one, column in self.identifier_fields.items()
            if is_forbidden(column)
        )
        if stored:
            msg = (
                f"the {self.entity_type.value} profile reads {', '.join(stored)} out of the "
                "projection, and brain.core.projection refuses to store that field at all. "
                f"{A_JOIN_KEY_ON_A_PERSON_IS_A_CONTACT_DETAIL_AND_IS_FETCHED_LIVE}"
            )
            raise ResolutionError(msg)

    def may_auto_merge(self, stage: Stage) -> bool:
        """Whether a match decided at this stage stands for this type."""
        return stage in self.auto_merge_stages


#: The company profile, which is the cascade as `brain.resolution.cascade` wrote it.
#:
#: Every other profile is checked against this one, so it is the widest by construction rather
#: than by intention: a test asserts each of the others is a subset of it on all three axes.
COMPANY_PROFILE: Final = EntityProfile(
    entity_type=EntityType.COMPANY,
    identifiers=frozenset(IdentifierKind),
    fields=FIELD_FEATURES,
    auto_merge_stages=frozenset({Stage.HARD_IDENTIFIER, Stage.CORROBORATED_NAME, Stage.SIMILARITY}),
    sources=("hubspot", "freshdesk", "xero", "lark_base", "laravel"),
    name_field="name",
    identifier_fields=MappingProxyType(
        {
            IdentifierKind.UEN: "uen",
            IdentifierKind.TAX_ID: "tax_id",
            IdentifierKind.DOMAIN: "domain",
        }
    ),
    live_identifiers=frozenset({IdentifierKind.PHONE, IdentifierKind.EMAIL}),
    field_sources=MappingProxyType({Feature.COUNTRY: "country", Feature.POSTCODE: "postcode"}),
)

#: The person profile (M14.7.1). HubSpot, Freshdesk and Lark, which are the leaf's three.
#:
#: No UEN and no tax id, because those identify a registered company and a person carrying one
#: is a sole proprietor's business rather than the person. No domain, for the reason
#: `A_DOMAIN_IDENTIFIES_AN_EMPLOYER_AND_NEVER_A_PERSON` gives at length. No similarity stage,
#: for `TWO_PEOPLE_CAN_SHARE_A_NAME_AND_A_COMPANY_CANNOT_SHARE_A_REGISTRATION`.
#:
#: **And no corroborating field, which is the least obvious of the four.** The corroborating
#: fields the cascade has are a country and a postcode, and neither is a fact about a person:
#: they are their employer's, so in a business whose clients are all in one jurisdiction the
#: country agrees for every pair of records in the estate. Stage two would then be "the names
#: agree", which is exactly the promotion M14.3.2 exists to prevent, arrived at through the
#: corroborant rather than through the name. What corroborates a person's name is their email
#: address or their telephone number, both of which are identifier agreements and both of which
#: `cascade.corroboration_for` already accepts as non-name features. So stage two still works
#: for people and works on the right evidence.
PERSON_PROFILE: Final = EntityProfile(
    entity_type=EntityType.PERSON,
    identifiers=frozenset({IdentifierKind.EMAIL, IdentifierKind.PHONE}),
    fields=frozenset(),
    auto_merge_stages=frozenset({Stage.HARD_IDENTIFIER, Stage.CORROBORATED_NAME}),
    sources=("hubspot", "freshdesk", "lark_base"),
    name_field="name",
    live_identifiers=frozenset({IdentifierKind.EMAIL, IdentifierKind.PHONE}),
)

#: The project profile (M14.7.2). Nothing auto-merges, and the reason is the evidence.
PROJECT_PROFILE: Final = EntityProfile(
    entity_type=EntityType.PROJECT,
    identifiers=frozenset(),
    fields=frozenset(),
    auto_merge_stages=frozenset(),
    sources=("lark_base", "laravel", "freshdesk"),
    name_field="name",
)

#: Every profile, by the type it is for. Exhaustive over `EntityType` by `profile_gaps`.
PROFILES: Mapping[EntityType, EntityProfile] = MappingProxyType(
    {
        EntityType.COMPANY: COMPANY_PROFILE,
        EntityType.PERSON: PERSON_PROFILE,
        EntityType.PROJECT: PROJECT_PROFILE,
    }
)


def profile_for(
    entity_type: EntityType, profiles: Mapping[EntityType, EntityProfile] | None = None
) -> EntityProfile:
    """The profile for one type. Refuses an unprofiled type rather than defaulting.

    A default would be the company profile, which is the widest one, so a type nobody wrote a
    profile for would be resolved with every comparison the system has. That is the failure
    `guardrails.priority_of` refuses a default for, in the direction that matters most.

    The mapping is a parameter so the refusal can be shown to fire: every declared type has a
    profile, so a check written against the constant alone could never be seen to fail, which
    is the argument `brain.ops.queue.concurrency_gaps` makes about its own signature.
    """
    declared = PROFILES if profiles is None else profiles
    if entity_type not in declared:
        msg = (
            f"no profile for {entity_type.value}; defaulting would resolve an unprofiled type "
            "with every comparison the cascade has, which is the widest possible answer to a "
            "question nobody has thought about"
        )
        raise ResolutionError(msg)
    return declared[entity_type]


# ------------------------------------------------------ from a projected record (M14.7.3)
@dataclass(frozen=True)
class Observed:
    """What one projected record became, and what was refused on the way.

    `dropped` is `cascade.Dropped`, which names the rule and never the value, so this type can
    be logged whole. It is here rather than discarded because a record that produced no
    identifiers at all is an operator fact worth having, and the alternative is discovering it
    as an entity that never resolves.
    """

    observation: Observation
    dropped: tuple[Dropped, ...]


def _text(value: object) -> str:
    """One projected value as a comparable string, or empty when there is nothing there.

    Deliberately narrow. A projected value may be a number or a timestamp, and both are
    stringified rather than refused, because a phone number stored as an integer is a real
    shape and refusing it would silently drop the identifier. What is not accepted is anything
    that is not a scalar, which `ProjectedRecord` already refuses on the way in.
    """
    if value is None:
        return ""
    return str(value).strip()


def observe(
    record: ProjectedRecord,
    profile: EntityProfile,
    *,
    pepper: str,
    live: Mapping[IdentifierKind, str] | None = None,
    verified: frozenset[IdentifierKind] = frozenset(),
) -> Observed:
    """One projected record as something the cascade may compare (M14.7.3).

    **The only function in this module that sees a raw value**, and the values it sees come from
    two places for a reason that is not this module's. `brain.core.projection.NEVER_PROJECT`
    refuses to store an email address, a telephone number or an address, so those cannot be in
    the record and arrive through `live` from a connector that fetched them for this call. The
    rest are ordinary projected fields. What comes back holds digests, a normalised name and
    opaque tokens, and there is no field on `Observation` that a contact detail would fit in.
    See `A_JOIN_KEY_ON_A_PERSON_IS_A_CONTACT_DETAIL_AND_IS_FETCHED_LIVE` and
    `THERE_IS_NOWHERE_ON_AN_OBSERVATION_TO_PUT_A_CONTACT_RECORD`.

    A live value for a kind the profile does not declare live is refused rather than ignored.
    Ignoring it would make `live` a parameter that silently does nothing for some kinds, which
    is how a caller comes to believe a join key is being computed when it is not; and admitting
    it would make `live` the way round every profile in this module.

    `verified` is what the source says it confirmed rather than merely reported, and it is a
    parameter because it is a fact about the connector. Inferring it here would make stage one's
    strength a guess, which is `Observation.verified`'s own argument. It is intersected with the
    profile's admissible kinds, so a caller cannot verify its way past a profile: a person
    record arriving with a verified domain still carries no domain.

    Only the fields the profile names are read. A projection that grew a `postcode` column for
    people contributes nothing, because nothing here iterates the record's fields looking for
    something useful, and that is the fail-closed direction.

    Hashing is `cascade.usable_identifiers`, which is the one place a value becomes a digest and
    the one place the blocklist and the free-mail list are applied. Not reimplemented here, for
    the reason that module gives: two implementations of a join key produce two sets of digests,
    and the day they disagree the entities stop joining with nothing reporting it.
    """
    handed = dict(live or {})
    stray = sorted(one.value for one in handed if one not in profile.live_identifiers)
    if stray:
        msg = (
            f"a live value was handed in for {', '.join(stray)}, which the "
            f"{profile.entity_type.value} profile does not fetch live. Admitting it would make "
            "this argument the way round every profile in this module, and ignoring it would "
            "let a caller believe a join key is being computed when it is not"
        )
        raise ResolutionError(msg)

    raw: dict[IdentifierKind, str] = {}
    for kind in sorted(profile.identifiers, key=lambda one: one.value):
        if kind in profile.live_identifiers:
            value = _text(handed.get(kind))
        else:
            column = profile.identifier_fields.get(kind)
            value = "" if column is None else _text(record.fields.get(column))
        if value:
            raw[kind] = value

    hashed, dropped = usable_identifiers(raw, pepper=pepper)

    tokens: dict[Feature, str] = {}
    for feature in sorted(profile.fields, key=lambda one: one.value):
        column = profile.field_sources.get(feature)
        if column is None:
            continue
        value = _text(record.fields.get(column))
        if value:
            tokens[feature] = value.casefold()

    return Observed(
        observation=Observation(
            record=SourceRef(
                source=record.source, entity=record.entity, source_id=record.source_id
            ),
            name=normalise_name(_text(record.fields.get(profile.name_field))),
            identifiers=hashed,
            fields=MappingProxyType(tokens),
            verified=frozenset(verified & profile.identifiers & set(hashed)),
        ),
        dropped=dropped,
    )


# --------------------------------------------------- the same cascade, narrowed (M14.7.1/2)
def resolve_pair(
    left: Observation,
    right: Observation,
    profile: EntityProfile,
    *,
    thresholds: Thresholds = DECLARED_THRESHOLDS,
    weights: WeightTable = DECLARED_WEIGHTS,
) -> CascadeResult:
    """The cascade's answer about two records of one type, with this type's stages applied.

    `cascade.cascade` decides; this only ever turns a match into a review. There is no branch
    here that could turn a review into a match, and no path that reaches a different stage
    ordering, so the whole of the cascade's safety argument holds unchanged and what a profile
    adds is refusals.

    A match decided at a stage the profile does not admit becomes `TO_REVIEW`, which is a
    question rather than a refusal: the evidence was real and this type is not one the evidence
    is sufficient for. `Decision.NOT_MATCHED` would be the wrong answer, because it says the
    cascade concluded they are two things and it concluded no such thing.

    The confidence is dropped with the decision, which `CascadeResult` enforces: a review item
    carrying a number is a number somebody writes into a link.
    """
    result = cascade(left, right, thresholds=thresholds, weights=weights)
    if result.decision is not Decision.MATCHED or profile.may_auto_merge(result.stage):
        return result
    return CascadeResult(
        decision=Decision.TO_REVIEW,
        stage=Stage.HUMAN_REVIEW,
        left=result.left,
        right=result.right,
        evidence=result.evidence,
        reason=(
            f"the evidence reached stage {int(result.stage)}, which is not evidence a "
            f"{profile.entity_type.value} may be merged on without a person looking"
        ),
    )


def profile_gaps(profiles: Mapping[EntityType, EntityProfile] | None = None) -> tuple[str, ...]:
    """Every way this set of profiles could quietly stop being safe.

    Four checks, and each is a way a profile becomes a widening rather than a narrowing.

    A type with no profile is resolved by whatever the caller passes, and the convenient thing
    to pass is the company profile. A profile admitting an identifier, a field or a stage the
    company profile does not is a comparison the cascade was never argued for. And a profile
    whose entity type disagrees with the key it is filed under would be applied to the wrong
    type by every lookup.

    **The fourth is the one a mutation found.** A profile that admits a comparison and names no
    source for it is inert: `observe` reads nothing, no digest and no token is produced, and the
    admission is a claim with nothing behind it. Two deliberate widenings of the project and
    person profiles survived every test for exactly that reason, which is a bad state to be in
    even though nothing was disclosed: the declared sets are the design record, a later author
    reads them as the decision, and the widening is already there when somebody adds the source.

    The profiles are a parameter defaulting to the declared ones, for the reason
    `brain.ops.jobs.driver_mapping_gaps` takes one: a check that can only be run against the
    constant beside it cannot be shown to fail.
    """
    declared = PROFILES if profiles is None else profiles
    findings = [
        f"{entity_type.value}: no profile, so the type would be resolved with whichever "
        "profile a caller passed, and the convenient one to pass is the widest"
        for entity_type in EntityType
        if entity_type not in declared
    ]
    for entity_type, profile in sorted(declared.items(), key=lambda one: one[0].value):
        if profile.entity_type is not entity_type:
            findings.append(
                f"{entity_type.value}: filed under one type and declares itself another "
                f"({profile.entity_type.value}), so every lookup applies it to the wrong one"
            )
        wider_ids = sorted(one.value for one in profile.identifiers - COMPANY_PROFILE.identifiers)
        wider_fields = sorted(one.value for one in profile.fields - COMPANY_PROFILE.fields)
        wider_stages = sorted(
            int(one) for one in profile.auto_merge_stages - COMPANY_PROFILE.auto_merge_stages
        )
        for what, names in (
            ("identifier", wider_ids),
            ("corroborating field", [str(one) for one in wider_fields]),
            ("auto-merge stage", [str(one) for one in wider_stages]),
        ):
            if names:
                findings.append(
                    f"{entity_type.value}: admits {what}(s) {', '.join(names)} that the company "
                    f"profile does not. {THE_PROFILE_NARROWS_AND_NEVER_WIDENS}"
                )
        sourced = set(profile.identifier_fields) | profile.live_identifiers
        inert = sorted(one.value for one in profile.identifiers - sourced)
        inert += sorted(one.value for one in profile.fields - set(profile.field_sources))
        if inert:
            findings.append(
                f"{entity_type.value}: admits {', '.join(inert)} and names no source for it, so "
                "observe reads nothing and the admission is a claim with nothing behind it. An "
                "inert widening is still a widening in the file a later author reads as the "
                "decision, and it becomes a real one the day somebody adds the source"
            )
    return tuple(findings)


def sources_named(profiles: Sequence[EntityProfile] | None = None) -> tuple[str, ...]:
    """Every connector named by any profile, deduplicated and sorted.

    Used by a test to hold the declared names against the connector registry, so a profile
    cannot name a source that does not exist: a misspelled connector name is a type that
    silently never resolves records from the source it was written for.
    """
    rows = tuple(PROFILES.values()) if profiles is None else tuple(profiles)
    return tuple(sorted({one for profile in rows for one in profile.sources}))
