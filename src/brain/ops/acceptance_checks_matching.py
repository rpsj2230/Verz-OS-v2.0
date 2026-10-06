"""The online cascade, proved on an install: each pair is matched, held, queued or left exactly as
the stage that answered says, and nothing is merged with nobody looking unless it may be.

Each check writes records the way a source sync leaves them in `proj.record`, runs the registry
and then the matching the worker's `entity_resolution` control runs
(`brain.resolution.matching_store.StoredMatching.match`), with the install's real merge store, all
inside the check's transaction. Nothing is committed.

**Unattended merging is off on every install until the owner says otherwise (item 155)**, and an
acceptance run does not switch on a feature its owner has not, even inside a transaction it rolls
back. So a match these checks find is held for a person and the checks read the hold; every hold
they prove comes before the switch is asked. That an automatic merge happens once it is on is
`tests/unit/test_matching_store.py`'s to prove, where switching it touches nobody's install.

**Two checks declare a source of their own.** A cap (M14.6.2) and a collision (M14.6.3) are only
reached on a hard identifier, and no shipped connector keeps one: a registration number is not in
any manifest's projection and no domain is verified. So those checks declare a company source that
keeps a registration number, for the check only, and say so in their sentence; the matching they
run is the product's, unchanged.

**The pepper is made for the check**, for `acceptance_checks_registry`'s reason.

Task ids: M14.2.5, M14.3.2, M14.3.3, M14.3.4, M14.3.6, M14.3.7, M14.3.8, M14.5.6, M14.6.2
Task ids: M14.6.3
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

from sqlalchemy import insert, text

from brain.connectors.resolves import ResolvesAs
from brain.core.scope import Scope
from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_run import Harness
from brain.resolution.canonical import EntityType, SourceRef
from brain.resolution.cascade import Feature, score
from brain.resolution.matching_store import (
    HELD_AT_A_CAP,
    HELD_BY_A_COLLISION,
    HELD_FOR_MONEY,
    HELD_ON_A_NAME,
    HELD_UNATTENDED,
    StoredMatching,
)
from brain.resolution.query import score_query
from brain.resolution.registry_store import StoredRegistry
from brain.resolution.sources import resolved_entities
from brain.tables.projection import ProjectedRecordRow

#: Where this module's checks sit on the acceptance page.
CHECK_ORDER: Final = 434

HUBSPOT: Final = ("hubspot", "hubspot_company")
XERO: Final = ("xero", "contact")
LARAVEL: Final = ("laravel", "laravel_client")
#: The check-only company source that keeps a registration number. See the module docstring.
REGISTERED: Final = ("hubspot", "acceptance_registered_company")

NOT_MATCHED_ON_NAMES: Final = "two names corroborated by a domain were not matched at stage two"
NOT_SCORED_IN_SQL: Final = "the database's score for a pair is not the cascade's own sum"
NOT_STAGE_THREE: Final = "two names a letter apart were not matched at stage three"
NO_QUESTION: Final = "two equal names nothing corroborates were not put to a person"
SHORT_NAME_MATCHED: Final = "a name too short to measure was not put to a person"
FREE_MAIL_JOINED: Final = "a mail provider's domain was kept as a join key"
PHONETIC_NOT_LOW: Final = "a phonetic agreement was not the weakest evidence on a pair"
MONEY_NOT_HELD: Final = "a match across the money boundary was not held for a person"
MERGED_WHILE_OFF: Final = "a match was merged while unattended merging was off"
CAP_NOT_HELD: Final = "a merge that breaches an identifier cap was not held"
COLLISION_NOT_HELD: Final = "a record matching two entities on one identifier was not held"


def _declared(extra: bool = False) -> Mapping[tuple[str, str], ResolvesAs]:
    found = dict(resolved_entities())
    if extra:
        found[REGISTERED] = ResolvesAs(
            entity=REGISTERED[1],
            entity_type=EntityType.COMPANY,
            fields={"name": "name", "uen": "uen"},
        )
    return MappingProxyType(found)


async def _records(
    h: Harness, *named: tuple[tuple[str, str], dict[str, str]]
) -> tuple[SourceRef, ...]:
    refs = []
    for (source, entity), fields in named:
        source_id = f"acceptance-{h.run}-{secrets.token_hex(6)}"
        await h.execute(
            *h.attributed(),
            insert(ProjectedRecordRow).values(
                source=source,
                entity=entity,
                source_id=source_id,
                last_seen_at=h.now,
                fields=fields,
            ),
        )
        refs.append(SourceRef(source=source, entity=entity, source_id=source_id))
    return tuple(refs)


async def _matched(
    h: Harness,
    *named: tuple[tuple[str, str], dict[str, str]],
    extra: bool = False,
    pepper: str | None = None,
) -> tuple[SourceRef, ...]:
    """Write, register and match these records as the worker's run does."""
    used = pepper or secrets.token_hex(32)
    declared = _declared(extra)
    refs = await _records(h, *named)
    await StoredRegistry(h.sessions, declared=declared).register(
        refs, pepper=used, now=h.now, by=h.actor
    )
    await StoredMatching(h.sessions, declared=declared).match(refs, pepper=used, now=h.now)
    return refs


async def _items(h: Harness, refs: tuple[SourceRef, ...]) -> list[tuple[Any, ...]]:
    """The review items raised over these records: left, right, origin, stage, reason, evidence."""
    ids = [one.source_id for one in refs]
    result = await h.execute(
        text(
            "SELECT left_source_id, right_source_id, origin, stage, reason, evidence"
            " FROM er.review_item WHERE left_source_id = ANY(:ids)"
            " AND right_source_id = ANY(:ids) ORDER BY left_source_id, right_source_id"
        ).bindparams(ids=ids)
    )
    return [tuple(row) for row in result.all()]


# ------------------------------------------------------------------ M14.3.2, M14.3.6
@check(
    leaves=("M14.3.2", "M14.3.6"),
    sentence=(
        "Two HubSpot companies whose names agree once Pte Ltd is off and whose domain agrees are "
        "read, scored in one database statement whose total equals the cascade's own sum, and "
        "matched at stage two; with unattended merging off they are held for a person."
    ),
)
async def a_corroborated_name_is_matched_and_scored_in_the_database(h: Harness) -> None:
    word = h.word()
    domain = f"{word.lower()}.example"
    refs = await _matched(
        h,
        (HUBSPOT, {"name": f"{word} Trading Pte. Ltd.", "domain": domain}),
        (HUBSPOT, {"name": f"{word.upper()} TRADING", "domain": domain}),
    )
    found = await _items(h, refs)
    if [row[2:5] for row in found] != [("held", 2, HELD_ON_A_NAME)]:
        raise CheckFailedError(NOT_MATCHED_ON_NAMES)
    query = score_query(table="er.observation", scope=Scope.unrestricted(), touching=refs)
    scored = (await h.execute(text(query.sql).bindparams(**query.params))).all()
    agreed = frozenset(Feature(one["field"]) for one in found[0][5] if float(one["weight"]) > 0)
    if len(scored) != 1 or float(scored[0].match_weight) != score(agreed):
        raise CheckFailedError(NOT_SCORED_IN_SQL)


# ------------------------------------------------------------ M14.3.3, M14.3.4, M14.3.8
@check(
    leaves=("M14.3.3", "M14.3.4", "M14.3.8"),
    sentence=(
        "Two HubSpot companies whose names are a letter apart are matched at stage three and "
        "held, with a phonetic agreement as their weakest evidence, and a HubSpot company and a "
        "Xero contact with the same name and nothing else in common are put to a person."
    ),
)
async def close_names_match_at_stage_three_and_bare_names_go_to_a_person(h: Harness) -> None:
    word = h.word()
    refs = await _matched(
        h,
        (HUBSPOT, {"name": f"Contoso Pharmaceuticals {word}"}),
        (HUBSPOT, {"name": f"Contosso Pharmaceuticals {word}"}),
        (HUBSPOT, {"name": f"{word} Studio"}),
        (XERO, {"name": f"{word} Studio"}),
    )
    found = {frozenset(row[0:2]): row for row in await _items(h, refs)}
    close = found.get(frozenset((refs[0].source_id, refs[1].source_id)))
    if close is None or close[2:5] != ("held", 3, HELD_ON_A_NAME):
        raise CheckFailedError(NOT_STAGE_THREE)
    weights = {one["field"]: float(one["weight"]) for one in close[5]}
    positive = [weight for weight in weights.values() if weight > 0]
    phonetic = weights.get(Feature.NAME_PHONETIC.value, 0.0)
    if phonetic <= 0 or phonetic != min(positive):
        raise CheckFailedError(PHONETIC_NOT_LOW)
    bare = found.get(frozenset((refs[2].source_id, refs[3].source_id)))
    if bare is None or bare[2:4] != ("cascade", 4):
        raise CheckFailedError(NO_QUESTION)


# ---------------------------------------------------------------------------- M14.2.5
@check(
    leaves=("M14.2.5",),
    sentence=(
        "Two HubSpot companies named with three letters and sharing a domain are read, and the "
        "pair is put to a person rather than matched, because a name under four characters "
        "cannot be measured."
    ),
)
async def a_name_too_short_to_measure_goes_to_a_person(h: Harness) -> None:
    word = h.word()
    domain = f"{word.lower()}.example"
    short = word[2:5]
    refs = await _matched(
        h,
        (HUBSPOT, {"name": short, "domain": domain}),
        (HUBSPOT, {"name": f"{short} Pte Ltd", "domain": domain}),
    )
    if [row[2] for row in await _items(h, refs)] != ["cascade"]:
        raise CheckFailedError(SHORT_NAME_MATCHED)


# ---------------------------------------------------------------------------- M14.3.7
@check(
    leaves=("M14.3.7",),
    sentence=(
        "Two HubSpot companies with different names whose domain is a mail provider's are read, "
        "and the domain is kept as a join key for neither, so they are not compared."
    ),
)
async def a_free_mail_domain_joins_nothing(h: Harness) -> None:
    word = h.word()
    refs = await _matched(
        h,
        (HUBSPOT, {"name": f"{word} Design", "domain": "gmail.com"}),
        (HUBSPOT, {"name": f"Other {word} Freight", "domain": "gmail.com"}),
    )
    keys = await h.execute(
        text("SELECT count(*) FROM er.identifier WHERE source_id = ANY(:ids)").bindparams(
            ids=[one.source_id for one in refs]
        )
    )
    if keys.scalar_one() or await _items(h, refs):
        raise CheckFailedError(FREE_MAIL_JOINED)


# ---------------------------------------------------------------------------- M14.5.6
@check(
    leaves=("M14.5.6",),
    sentence=(
        "A Laravel client and a Xero contact, both carrying financial records, whose names are a "
        "letter apart are matched by the cascade and held for a person at the money boundary, "
        "which comes before anything else that could let a match through."
    ),
)
async def a_match_across_the_money_boundary_waits_for_a_person(h: Harness) -> None:
    word = h.word()
    refs = await _matched(
        h,
        (LARAVEL, {"name": f"Acme Holdings International {word}"}),
        (XERO, {"name": f"Acmee Holdings International {word}"}),
    )
    if [row[2:5:2] for row in await _items(h, refs)] != [("money", HELD_FOR_MONEY)]:
        raise CheckFailedError(MONEY_NOT_HELD)


# --------------------------------------------------------------- M14.6.2 and M14.6.3
@check(
    leaves=("M14.6.2", "M14.6.3"),
    sentence=(
        "With a company source that keeps a registration number declared for the check, two "
        "records sharing one are held while unattended merging is off, a merge that would leave "
        "one entity two numbers is held at the cap, and three records sharing one are all held."
    ),
)
async def a_hard_match_merges_only_within_its_caps_and_without_a_tie(h: Harness) -> None:
    pepper = secrets.token_hex(32)
    word = h.word()

    def uen(n: int) -> str:
        return f"2019{n:05d}K"

    waiting = await _matched(
        h,
        (REGISTERED, {"name": f"{word} Labs", "uen": uen(1)}),
        (REGISTERED, {"name": f"{word} Laboratories", "uen": uen(1)}),
        extra=True,
        pepper=pepper,
    )
    if [row[4] for row in await _items(h, waiting)] != [HELD_UNATTENDED]:
        raise CheckFailedError(MERGED_WHILE_OFF)

    capped = await _records(
        h,
        (REGISTERED, {"name": f"{word} Orbit", "uen": uen(3)}),
        (REGISTERED, {"name": f"{word} Orbit", "uen": uen(3)}),
    )
    declared = _declared(extra=True)
    await StoredRegistry(h.sessions, declared=declared).register(
        capped, pepper=pepper, now=h.now, by=h.actor
    )
    await h.execute(
        text(
            "INSERT INTO er.identifier (source, entity, source_id, kind, key_hash, entity_id,"
            " first_seen_at) SELECT source, entity, source_id, 'uen', :digest, entity_id, :at"
            " FROM er.link WHERE source_id = :first"
        ).bindparams(digest="e" * 64, at=h.now, first=capped[0].source_id)
    )
    await StoredMatching(h.sessions, declared=declared).match(capped, pepper=pepper, now=h.now)
    if [row[4] for row in await _items(h, capped)] != [HELD_AT_A_CAP]:
        raise CheckFailedError(CAP_NOT_HELD)

    tied = await _matched(
        h,
        (REGISTERED, {"name": f"{word} Vega", "uen": uen(4)}),
        (REGISTERED, {"name": f"{word} Vega Works", "uen": uen(4)}),
        (REGISTERED, {"name": f"{word} Vega Labs", "uen": uen(4)}),
        extra=True,
        pepper=pepper,
    )
    held = [row[4] for row in await _items(h, tied)]
    if len(held) != 3 or set(held) != {HELD_BY_A_COLLISION}:
        raise CheckFailedError(COLLISION_NOT_HELD)
