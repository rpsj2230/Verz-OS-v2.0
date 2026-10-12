"""Install checks for the cascade's first stage, and for the same cascade over people and projects.

`brain.ops.acceptance_checks_matching` proved each stage of the online cascade over companies, and
`acceptance_checks_er_proof` proved the registration number. Three clauses were still shown by
nothing on an install: that stage one merges on **each** of the four hard identifiers the leaf
names and on no other, that people go through the same cascade as companies, and that projects do.

**The sources are the check's own, and say so.** No shipped connector declares a person or a
project for resolution (`brain.connectors.resolves`), and none keeps a tax number in its
projection, so each check declares company, person or project sources for the check alone, as
`acceptance_checks_matching.REGISTERED` is declared; the registry, the matching and the review
queue they run through are the product's, unchanged. The pass is therefore about the install's code
reading the records of a source, and not about any company's own records.

**A person's join keys are a decision still waiting (needs-rupash 155).** The person profile's only
identifiers are an email address and a telephone number, which are fetched live and never kept, and
the online registry hands `observe` no live values, so on this install two person records are
compared by their names alone. That is what the check shows: three records of one name in three
sources are put to a person at stage four, and are merged by nothing. It does not show a person
joined on an email address, because nothing on this install can yet.

**A project has nothing that corroborates its name.** Two projects of one client share the
client's country and postcode, so two differently named projects agree on every field the cascade
has, and the project profile admits none of them (`brain.resolution.entities`). The check gives two
projects of one name one country and one postcode and shows them put to a person at stage four,
where a company profile would have matched them at stage two on the address.

**Stage one's verified identifiers are shown on the cascade itself.** A verified domain and a
verified telephone number are properties the connector asserts and the online registry does not yet
assert, so they cannot be shown through the registry on any install. The check hands the cascade
two observations that carry the same telephone digest, once verified and once not, and shows stage
one decide the first and refuse to decide the second.

Task ids: M14.3.1, M14.7.1, M14.7.2
"""

from __future__ import annotations

import secrets
from types import MappingProxyType
from typing import Final

from sqlalchemy import text

from brain.connectors.resolves import ResolvesAs
from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_checks_matching import _records
from brain.ops.acceptance_run import Harness
from brain.resolution.canonical import EntityType, IdentifierKind, SourceRef, identifier_hash
from brain.resolution.cascade import Decision, Observation, Stage, cascade
from brain.resolution.matching_store import HELD_UNATTENDED
from brain.resolution.normalise import normalise_name

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 870

#: The check-only company source that keeps a tax number and a domain. See the module docstring.
TAXED: Final = ("hubspot", "acceptance_taxed_company")
#: The check-only person sources, one for each source the leaf names.
CONTACT: Final = ("hubspot", "acceptance_contact")
REQUESTER: Final = ("freshdesk", "acceptance_requester")
STAFF: Final = ("lark_base", "acceptance_staff")
#: The check-only project source.
PROJECT: Final = ("laravel", "acceptance_project")

NO_STAGE_ONE_ON_A_TAX_NUMBER: Final = (
    "two records sharing one tax number and nothing else were not put to a person at stage one"
)
A_UNVERIFIED_DOMAIN_DECIDED_STAGE_ONE: Final = (
    "two records sharing only a domain nobody verified were decided at stage one"
)
A_VERIFIED_PHONE_DID_NOT_DECIDE: Final = (
    "two records carrying one verified telephone number were not matched at stage one"
)
AN_UNVERIFIED_PHONE_DECIDED: Final = (
    "two records carrying one telephone number nobody verified were matched at stage one"
)
PEOPLE_WERE_NOT_COMPARED: Final = (
    "three records of one person's name in three sources were not each put to a person at "
    "stage four as people"
)
PEOPLE_WERE_MERGED: Final = "records of one person's name were merged with nobody looking"
A_DOMAIN_JOINED_PEOPLE: Final = "two people sharing an employer's domain were kept as a join key"
PROJECTS_WERE_NOT_COMPARED: Final = "two projects of one name were not put to a person"
PROJECTS_WERE_MATCHED: Final = (
    "two projects of one name sharing their client's address were not put to a person at stage four"
)


def _declared(
    kind: EntityType, *entities: tuple[str, str], keys: tuple[str, ...] = ()
) -> dict[tuple[str, str], ResolvesAs]:
    return {
        one: ResolvesAs(
            entity=one[1], entity_type=kind, fields={key: key for key in ("name", *keys)}
        )
        for one in entities
    }


async def _registered(
    h: Harness,
    declared: dict[tuple[str, str], ResolvesAs],
    *named: tuple[tuple[str, str], dict[str, str]],
) -> tuple[SourceRef, ...]:
    """Write, register and match these records, with these sources declared beside the shipped."""
    from brain.resolution.matching_store import StoredMatching
    from brain.resolution.registry_store import StoredRegistry
    from brain.resolution.sources import resolved_entities

    pepper = secrets.token_hex(32)
    every = MappingProxyType({**resolved_entities(), **declared})
    refs = await _records(h, *named)
    await StoredRegistry(h.sessions, declared=every).register(
        refs, pepper=pepper, now=h.now, by=h.actor
    )
    await StoredMatching(h.sessions, declared=every).match(refs, pepper=pepper, now=h.now)
    return refs


async def _queued(h: Harness, refs: tuple[SourceRef, ...]) -> list[tuple[str, str, int, str]]:
    """The review items raised over these records: type, origin, stage and reason, in id order."""
    ids = [one.source_id for one in refs]
    found = await h.execute(
        text(
            "SELECT entity_type, origin, stage, reason FROM er.review_item"
            " WHERE left_source_id = ANY(:ids) AND right_source_id = ANY(:ids)"
            " ORDER BY left_source_id, right_source_id"
        ).bindparams(ids=ids)
    )
    return [(str(a), str(b), int(c), str(d)) for a, b, c, d in found.all()]


def _observation(
    name: str, kind: IdentifierKind, value: str, *, pepper: str, verified: bool
) -> Observation:
    return Observation(
        record=SourceRef(source="acceptance", entity="acceptance", source_id=secrets.token_hex(6)),
        name=normalise_name(name),
        identifiers={kind: identifier_hash(kind, value, pepper=pepper)},
        verified=frozenset({kind}) if verified else frozenset(),
    )


# ---------------------------------------------------------------------------- M14.3.1
@check(
    leaves=("M14.3.1",),
    sentence=(
        "With a company source that keeps a tax number declared for the check, two records of "
        "different names sharing one tax number are put to a person at stage one, two records "
        "sharing only a domain nobody verified are not decided at stage one, and the cascade "
        "decides two records carrying one telephone number at stage one only when it is verified."
    ),
)
async def stage_one_decides_on_a_hard_identifier_and_only_a_verified_one(h: Harness) -> None:
    word = h.word()
    declared = _declared(EntityType.COMPANY, TAXED, keys=("tax_id", "domain"))

    number = f"TX{secrets.randbelow(10**9):09d}"
    same = await _registered(
        h,
        declared,
        (TAXED, {"name": f"{word} Beta Freight", "tax_id": number}),
        (TAXED, {"name": f"Entirely Other {word} Foods", "tax_id": number}),
    )
    if [(row[2], row[3]) for row in await _queued(h, same)] != [(1, HELD_UNATTENDED)]:
        raise CheckFailedError(NO_STAGE_ONE_ON_A_TAX_NUMBER)

    domain = f"{word.lower()}.example"
    shared = await _registered(
        h,
        declared,
        (TAXED, {"name": f"{word} Gamma Textiles", "domain": domain}),
        (TAXED, {"name": f"Another {word} Hardware", "domain": domain}),
    )
    if any(row[2] == int(Stage.HARD_IDENTIFIER) for row in await _queued(h, shared)):
        raise CheckFailedError(A_UNVERIFIED_DOMAIN_DECIDED_STAGE_ONE)

    pepper = secrets.token_hex(32)
    number = f"+65 6{secrets.randbelow(10**7):07d}"
    verified = cascade(
        _observation(
            f"{word} Delta Metals", IdentifierKind.PHONE, number, pepper=pepper, verified=True
        ),
        _observation(
            f"Unrelated {word} Paper", IdentifierKind.PHONE, number, pepper=pepper, verified=True
        ),
    )
    if verified.decision is not Decision.MATCHED or verified.stage is not Stage.HARD_IDENTIFIER:
        raise CheckFailedError(A_VERIFIED_PHONE_DID_NOT_DECIDE)
    unverified = cascade(
        _observation(
            f"{word} Delta Metals", IdentifierKind.PHONE, number, pepper=pepper, verified=False
        ),
        _observation(
            f"Unrelated {word} Paper", IdentifierKind.PHONE, number, pepper=pepper, verified=False
        ),
    )
    if unverified.decision is Decision.MATCHED and unverified.stage is Stage.HARD_IDENTIFIER:
        raise CheckFailedError(AN_UNVERIFIED_PHONE_DECIDED)


# ------------------------------------------------------------------- M14.7.1 and M14.7.2
@check(
    leaves=("M14.7.1",),
    sentence=(
        "With a CRM contact, a helpdesk requester and a chat directory person declared for the "
        "check, three records of one person's name are each put to a person as people and merged "
        "with nobody looking, and two people at one employer sharing its domain are given no "
        "domain as a join key."
    ),
)
async def people_in_three_sources_are_compared_and_never_joined_on_a_name(
    h: Harness,
) -> None:
    word = h.word()
    declared = _declared(EntityType.PERSON, CONTACT, REQUESTER, STAFF, keys=("domain",))
    name = f"Tan Wei Ming {word}"
    refs = await _registered(
        h,
        declared,
        (CONTACT, {"name": name}),
        (REQUESTER, {"name": name}),
        (STAFF, {"name": name}),
    )
    queued = await _queued(h, refs)
    if len(queued) != 3 or {(a, b, c) for a, b, c, _ in queued} != {
        (EntityType.PERSON.value, "cascade", 4)
    }:
        raise CheckFailedError(PEOPLE_WERE_NOT_COMPARED)
    ids = [one.source_id for one in refs]
    merged = await h.execute(
        text(
            "SELECT count(DISTINCT entity_id) FROM er.link WHERE source_id = ANY(:ids)"
        ).bindparams(ids=ids)
    )
    if merged.scalar_one() != 3:
        raise CheckFailedError(PEOPLE_WERE_MERGED)

    employer = f"{word.lower()}.example"
    colleagues = await _registered(
        h,
        declared,
        (CONTACT, {"name": f"Lim Hui Min {word}", "domain": employer}),
        (REQUESTER, {"name": f"Ong Kai Wen {word}", "domain": employer}),
    )
    kept = await h.execute(
        text("SELECT count(*) FROM er.identifier WHERE source_id = ANY(:ids)").bindparams(
            ids=[one.source_id for one in colleagues]
        )
    )
    if kept.scalar_one() or await _queued(h, colleagues):
        raise CheckFailedError(A_DOMAIN_JOINED_PEOPLE)


@check(
    leaves=("M14.7.2",),
    sentence=(
        "With a project source declared for the check, two projects of one name are put to a "
        "person as projects and merged with nobody looking, and two of one name sharing their "
        "client's country and postcode are put to a person at stage four and not matched at "
        "stage two on the address."
    ),
)
async def projects_are_queued_and_never_matched_on_their_clients_address(
    h: Harness,
) -> None:
    word = h.word()
    declared = _declared(EntityType.PROJECT, PROJECT, keys=("country", "postcode"))
    twins = await _registered(
        h,
        declared,
        (PROJECT, {"name": f"Website Revamp {word}"}),
        (PROJECT, {"name": f"Website Revamp {word}"}),
    )
    queued = await _queued(h, twins)
    if [(a, b, c) for a, b, c, _ in queued] != [(EntityType.PROJECT.value, "cascade", 4)]:
        raise CheckFailedError(PROJECTS_WERE_NOT_COMPARED)
    merged = await h.execute(
        text(
            "SELECT count(DISTINCT entity_id) FROM er.link WHERE source_id = ANY(:ids)"
        ).bindparams(ids=[one.source_id for one in twins])
    )
    if merged.scalar_one() != 2:
        raise CheckFailedError(PROJECTS_WERE_NOT_COMPARED)

    address = {"country": "SG", "postcode": f"{secrets.randbelow(10**6):06d}"}
    twins_at_one_address = await _registered(
        h,
        declared,
        (PROJECT, {"name": f"Annual Report {word}", **address}),
        (PROJECT, {"name": f"Annual Report {word}", **address}),
    )
    if [(a, b, c) for a, b, c, _ in await _queued(h, twins_at_one_address)] != [
        (EntityType.PROJECT.value, "cascade", 4)
    ]:
        raise CheckFailedError(PROJECTS_WERE_MATCHED)
