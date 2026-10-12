"""The entity registry, proved on an install: records become entities, names are keyed, blocked
values are refused and no join key is kept in the clear.

Each check writes records the way a source sync leaves them in `proj.record`, under a connector
whose declaration says what they are (HubSpot's companies), and runs the registry the worker's
`entity_resolution` control runs (`brain.resolution.registry_store.StoredRegistry.register`) inside
the check's transaction. Nothing is committed.

**The pepper is made for the check.** A join key's digest is keyed with a pepper, and these checks
prove what the registry writes and refuses, which is the same under any pepper. The install's own
pepper is read from its vault by the worker; reading it here would put the one secret every digest
depends on into a process that only needs to compare two of its own digests.

**Each check proves what its leaves' own words ask and no more.** The forwarding pointer (M14.1.5)
is a merge's, and a name too short to match (M14.2.5) is sent to review by the cascade; both are
proved where those are built. UEN validation (M14.2.6) needs a source that keeps a
registration number and no shipped connector projects one, so
`brain.ops.acceptance_checks_er_proof` proves it over a source declared for the check.

Task ids: M14.1.1, M14.1.2, M14.1.3, M14.1.4, M14.1.6, M14.2.1, M14.2.2, M14.2.3, M14.2.4
Task ids: M14.6.1, M14.7.3
"""

from __future__ import annotations

import secrets
from typing import Final

from sqlalchemy import insert, select, text

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_run import Harness
from brain.resolution.canonical import IdentifierKind, SourceRef, identifier_hash
from brain.resolution.registry_store import StoredRegistry
from brain.tables.projection import ProjectedRecordRow

#: Where this module's checks sit on the acceptance page.
CHECK_ORDER: Final = 430

#: The connector whose declared records the checks write: HubSpot keeps a company's name and
#: domain, so both the alias and a join key are exercised.
SOURCE: Final = "hubspot"
ENTITY: Final = "hubspot_company"

#: The registry's tables, searched for a value that must not be in any of them.
REGISTRY_TABLES: Final = (
    "er.canonical",
    "er.alias",
    "er.identifier",
    "er.link",
    "er.observation",
    "er.blocked_value",
)

NOT_AN_ENTITY: Final = "a record read by the registry was not given an entity of its declared type"
NOT_LINKED: Final = "a record was not linked to its entity, or its local id was not set"
NO_ALIAS: Final = "a record's observed name was not kept verbatim as an alias"
NO_KEY: Final = "a record's join key was not kept as a digest of the right kind"
NOT_RESOLVED: Final = "the resolved alias view did not name the record's current entity"
NOT_FOLDED: Final = "two spellings of one name differing in case or spacing were keyed apart"
PUNCTUATION_KEPT: Final = "punctuation survived into a name's key"
SUFFIX_KEPT: Final = "a legal form such as Pte Ltd survived into a name's key"
ACCENT_KEPT: Final = "an accented letter was keyed apart from its plain form"
BLOCK_IGNORED: Final = "a join key this install blocks was kept for a record"
BLOCK_TOO_WIDE: Final = "blocking one join key stopped another record's key being kept"
IN_THE_CLEAR: Final = "a join key's value was found in a registry table"


async def _records(h: Harness, *named: tuple[str, str]) -> tuple[SourceRef, ...]:
    """Records of the declared entity, as a sync leaves them, each with a name and a domain."""
    refs = []
    for n, (name, domain) in enumerate(named):
        source_id = f"acceptance-{h.run}-{n}"
        await h.execute(
            *h.attributed(),
            insert(ProjectedRecordRow).values(
                source=SOURCE,
                entity=ENTITY,
                source_id=source_id,
                last_seen_at=h.now,
                fields={"name": name, "domain": domain},
            ),
        )
        refs.append(SourceRef(source=SOURCE, entity=ENTITY, source_id=source_id))
    return tuple(refs)


async def _registered(h: Harness, pepper: str, *named: tuple[str, str]) -> tuple[SourceRef, ...]:
    refs = await _records(h, *named)
    await StoredRegistry(h.sessions).register(refs, pepper=pepper, now=h.now, by=h.actor)
    return refs


async def _one(h: Harness, sql: str, ref: SourceRef) -> list[tuple[object, ...]]:
    result = await h.execute(
        text(sql).bindparams(source=ref.source, entity=ref.entity, source_id=ref.source_id)
    )
    return [tuple(row) for row in result.all()]


# ------------------------------------------------------------ M14.1.1 to M14.1.4, M14.1.6
@check(
    leaves=("M14.1.1", "M14.1.2", "M14.1.3", "M14.1.4", "M14.1.6"),
    sentence=(
        "Two HubSpot companies are read by the registry: each becomes a company entity minted "
        "from its record, linked to it, with its name kept verbatim as an alias, its domain kept "
        "as a digest of the domain kind, its local id set, and the resolved view naming it."
    ),
)
async def two_records_each_become_an_entity_with_names_keys_and_link(h: Harness) -> None:
    pepper = secrets.token_hex(32)
    word = h.word()
    named = (
        (f"{word} Trading Pte. Ltd.", f"{word.lower()}.example"),
        (f"{word} Holdings", f"{word.lower()}-holdings.example"),
    )
    refs = await _registered(h, pepper, *named)
    for ref, (name, domain) in zip(refs, named, strict=True):
        made = await _one(
            h,
            "SELECT c.entity_id, c.entity_type, c.created_from_source_id FROM er.link l"
            " JOIN er.canonical c ON c.entity_id = l.entity_id"
            " WHERE l.source = :source AND l.entity = :entity AND l.source_id = :source_id",
            ref,
        )
        if len(made) != 1:
            raise CheckFailedError(NOT_LINKED)
        entity_id, kind, created_from = made[0]
        if kind != "company" or created_from != ref.source_id:
            raise CheckFailedError(NOT_AN_ENTITY)
        local = await _one(
            h,
            "SELECT local_id FROM proj.record"
            " WHERE source = :source AND entity = :entity AND source_id = :source_id",
            ref,
        )
        if local != [(entity_id,)]:
            raise CheckFailedError(NOT_LINKED)
        aliases = await _one(
            h,
            "SELECT name, entity_id FROM er.alias"
            " WHERE source = :source AND entity = :entity AND source_id = :source_id",
            ref,
        )
        if aliases != [(name, entity_id)]:
            raise CheckFailedError(NO_ALIAS)
        keys = await _one(
            h,
            "SELECT kind, key_hash FROM er.identifier"
            " WHERE source = :source AND entity = :entity AND source_id = :source_id",
            ref,
        )
        if keys != [("domain", identifier_hash(IdentifierKind.DOMAIN, domain, pepper=pepper))]:
            raise CheckFailedError(NO_KEY)
        resolved = await _one(
            h,
            "SELECT entity_id FROM er.resolved_alias"
            " WHERE source = :source AND entity = :entity AND source_id = :source_id",
            ref,
        )
        if resolved != [(entity_id,)]:
            raise CheckFailedError(NOT_RESOLVED)


# ------------------------------------------------------------------ M14.2.1 to M14.2.4
@check(
    leaves=("M14.2.1", "M14.2.2", "M14.2.3", "M14.2.4"),
    sentence=(
        "Five HubSpot companies whose names differ only in case and spacing, punctuation, a "
        "legal form such as Pte Ltd, or an accent are read by the registry, and each pair is "
        "given the same name key, with no punctuation, legal form or accent left in it."
    ),
)
async def a_name_is_keyed_the_same_however_it_is_written(h: Harness) -> None:
    pepper = secrets.token_hex(32)
    word = h.word()
    base = f"{word} Cafe"
    spelled = (
        base,
        f"  {word.lower()}   CAFE ",
        f"{word}, Cafe.",
        f"{base} Pte. Ltd.",
        f"{word} Café",
    )
    refs = await _registered(
        h, pepper, *((one, f"k{n}.{word.lower()}.example") for n, one in enumerate(spelled))
    )
    keys = []
    for ref in refs:
        found = await _one(
            h,
            "SELECT name_key FROM er.observation"
            " WHERE source = :source AND entity = :entity AND source_id = :source_id",
            ref,
        )
        keys.append(found[0][0] if found else None)
    plain = keys[0]
    if plain is None or keys[1] != plain:
        raise CheckFailedError(NOT_FOLDED)
    if keys[2] != plain or any(mark in str(plain) for mark in ",."):
        raise CheckFailedError(PUNCTUATION_KEPT)
    if keys[3] != plain or "pte" in str(plain):
        raise CheckFailedError(SUFFIX_KEPT)
    if keys[4] != plain:
        raise CheckFailedError(ACCENT_KEPT)


# ---------------------------------------------------------------------------- M14.6.1
@check(
    leaves=("M14.6.1",),
    sentence=(
        "An administrator blocks one domain on this install; a HubSpot company carrying it is "
        "then read by the registry and keeps no join key, while another company carrying a "
        "different domain keeps its own."
    ),
)
async def a_join_key_this_install_blocks_is_never_kept(h: Harness) -> None:
    pepper = secrets.token_hex(32)
    word = h.word()
    blocked, open_domain = f"{word.lower()}-portal.example", f"{word.lower()}.example"
    store = StoredRegistry(h.sessions)
    await store.block(
        IdentifierKind.DOMAIN,
        blocked,
        pepper=pepper,
        reason="a shared portal's domain, not a client's",
        by=h.actor,
        trace_id=h.trace_id,
    )
    refs = await _registered(h, pepper, (f"{word} One", blocked), (f"{word} Two", open_domain))
    kept = [
        await _one(
            h,
            "SELECT kind FROM er.identifier"
            " WHERE source = :source AND entity = :entity AND source_id = :source_id",
            ref,
        )
        for ref in refs
    ]
    if kept[0]:
        raise CheckFailedError(BLOCK_IGNORED)
    if kept[1] != [("domain",)]:
        raise CheckFailedError(BLOCK_TOO_WIDE)


# ---------------------------------------------------------------------------- M14.7.3
@check(
    leaves=("M14.7.3",),
    sentence=(
        "A HubSpot company with a domain no other record has is read by the registry, and the "
        "domain is then found in no registry table: the entity, its names, its keys, its link "
        "and its comparison row hold the domain only as a digest."
    ),
)
async def no_registry_table_holds_a_join_key_in_the_clear(h: Harness) -> None:
    pepper = secrets.token_hex(32)
    word = h.word()
    domain = f"{word.lower()}-private.example"
    [ref] = await _registered(h, pepper, (f"{word} Private", domain))
    keys = await _one(
        h,
        "SELECT kind FROM er.identifier"
        " WHERE source = :source AND entity = :entity AND source_id = :source_id",
        ref,
    )
    if keys != [("domain",)]:
        raise CheckFailedError(NO_KEY)
    for table in REGISTRY_TABLES:
        # The names are this module's constants, never input.
        found = await h.execute(
            select(text("1"))
            .select_from(text(f"{table} AS t"))
            .where(text("position(:value in t::text) > 0").bindparams(value=domain))
            .limit(1)
        )
        if found.first() is not None:
            raise CheckFailedError(IN_THE_CLEAR)
