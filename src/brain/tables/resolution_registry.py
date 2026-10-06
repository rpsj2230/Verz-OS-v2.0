"""What the registry keeps beside the entity graph: each record's comparison keys and the blocked
values.

`brain.tables.resolution` holds the graph (`er.canonical`, `er.alias`, `er.identifier`,
`er.link`). These two are what deciding a match needs and the graph does not hold.

**`er.observation` is the score's table, and its columns are the ones the score already names.**
`brain.resolution.cascade.SQL_PREDICATES` compares `name_key`, `name_collapsed`, `name_dm`, five
`*_hash` columns, `country_key` and `postcode_key`, and until this table nothing had them, which
`brain.resolution.query.NOTHING_HAS_RUN_THIS_AGAINST_POSTGRES` said. One row per source record,
keyed as `proj.record` is and holding what `brain.resolution.entities.observe` made of it:
digests, normalised name keys and opaque comparison tokens, and **no field a contact detail would
fit in**, for `entities.THERE_IS_NOWHERE_ON_AN_OBSERVATION_TO_PUT_A_CONTACT_RECORD`'s reason. A
`*_hash` column refuses anything but a digest, as `er.identifier.key_hash` does.

Rejected: reading the five digests off `er.identifier` at scoring time. A record's identifiers
there are keyed by assertion and pivoting them into one row per record is a five-way join on
every candidate pair, which is the cost `query.THE_COST_CLAIM_IS_ABOUT_THE_SCORING_AND_NOT_ABOUT_
THE_JOIN` refuses to pretend is free. `er.identifier` stays the record of what was asserted, and
this is the row the score reads.

**`er.blocked_value` is the install's own blocklist (M14.6.1), and it holds digests.** The
product's list (`brain.resolution.guardrails`, placeholder values and shared mailboxes) is
generic and written once; this is the place an administrator adds a value that is junk on this
install, such as the company's own switchboard number. Stored as the same peppered digest
`er.identifier` holds, so a blocked value is compared exactly where it would have joined and
the table never holds the value itself. SELECT and INSERT only: see the migration.

**A person's email or telephone digest has no table yet, deliberately (item 155).** Those values
are never stored (`brain.core.projection.NEVER_PROJECT`), so a person's join key could only be
hashed by a sync while it holds the record, and no shipped connector asks its source for one:
HubSpot's contact projects no name and reads no address. Whether a sync may ask is the owner's
question, and a table nothing writes would read as though the answer were yes.

Task ids: M14.1.3, M14.6.1, M14.7.3
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ARRAY, CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from brain.core.envelope import OBJECT_NAME_PATTERN
from brain.db import Base
from brain.resolution.canonical import EntityType, IdentifierKind
from brain.resolution.normalise import NameVerdict
from brain.tables.identity import one_of
from brain.tables.resolution import (
    ALIAS_CHARS,
    CREATED_BY_CHARS,
    DIGEST_CHARS,
    ENTITY_CHARS,
    ENUM_CHARS,
    KEY_HASH_IS_A_DIGEST,
    SOURCE_CHARS,
    SOURCE_ID_CHARS,
)

#: The tables this module declares, in the order migration 0182 creates them.
TABLES: tuple[str, ...] = ("er.observation", "er.blocked_value")

#: How wide a name verdict is. `NameVerdict`'s longest member is seventeen characters.
VERDICT_CHARS = 24

#: How wide the accent fold's stamp is. `normalise.ACCENT_FOLD_ID` is a short digest.
FOLD_CHARS = 64

#: How wide a corroborating comparison token is: a country or a postcode, casefolded.
TOKEN_CHARS = 120

#: Why a blocked value was added, in a sentence for the next administrator.
REASON_CHARS = 400

#: The five digest columns, one per identifier kind, in `IdentifierKind`'s order.
HASH_COLUMNS: tuple[str, ...] = tuple(f"{kind.value}_hash" for kind in IdentifierKind)


def _digest_or_null(column: str) -> str:
    return f"{column} IS NULL OR {column} ~ '^[0-9a-f]{{{DIGEST_CHARS}}}$'"


def _present(column: str) -> str:
    return f"length(btrim({column})) > 0"


def _source_ref() -> tuple[CheckConstraint, ...]:
    return (
        CheckConstraint(f"source ~ '{OBJECT_NAME_PATTERN}'", name="source_is_a_name"),
        CheckConstraint(f"entity ~ '{OBJECT_NAME_PATTERN}'", name="entity_is_a_name"),
        CheckConstraint(_present("source_id"), name="source_id_present"),
    )


class ObservationRow(Base):
    """`er.observation`: one source record as the score compares it. Digests and keys only."""

    __tablename__ = "observation"

    source: Mapped[str] = mapped_column(String(SOURCE_CHARS), primary_key=True)
    entity: Mapped[str] = mapped_column(String(ENTITY_CHARS), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(SOURCE_ID_CHARS), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(ENUM_CHARS), nullable=False)
    #: Case, accents, punctuation and whitespace settled; legal forms still on. Null when empty.
    name_collapsed: Mapped[str | None] = mapped_column(String(ALIAS_CHARS), nullable=True)
    #: The key a match may be made on, or null for every verdict that sends a name to a person.
    name_key: Mapped[str | None] = mapped_column(String(ALIAS_CHARS), nullable=True)
    name_verdict: Mapped[str] = mapped_column(String(VERDICT_CHARS), nullable=False)
    #: Which accent fold made the keys, so a key made by an older fold is detectably stale.
    name_fold: Mapped[str] = mapped_column(String(FOLD_CHARS), nullable=False)
    #: Daitch-Mokotoff codes of the key, empty when the key is not usable.
    name_dm: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), nullable=False, server_default=text("'{}'::varchar[]")
    )
    uen_hash: Mapped[str | None] = mapped_column(String(DIGEST_CHARS), nullable=True)
    tax_id_hash: Mapped[str | None] = mapped_column(String(DIGEST_CHARS), nullable=True)
    domain_hash: Mapped[str | None] = mapped_column(String(DIGEST_CHARS), nullable=True)
    email_hash: Mapped[str | None] = mapped_column(String(DIGEST_CHARS), nullable=True)
    phone_hash: Mapped[str | None] = mapped_column(String(DIGEST_CHARS), nullable=True)
    country_key: Mapped[str | None] = mapped_column(String(TOKEN_CHARS), nullable=True)
    postcode_key: Mapped[str | None] = mapped_column(String(TOKEN_CHARS), nullable=True)
    #: The identifier kinds the source confirmed rather than merely reported.
    verified: Mapped[list[str]] = mapped_column(
        ARRAY(String(ENUM_CHARS)), nullable=False, server_default=text("'{}'::varchar[]")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        *_source_ref(),
        CheckConstraint(one_of("entity_type", EntityType), name="entity_type_known"),
        CheckConstraint(one_of("name_verdict", NameVerdict), name="name_verdict_known"),
        *(
            CheckConstraint(_digest_or_null(column), name=f"{column}_is_a_digest")
            for column in HASH_COLUMNS
        ),
        # The candidate lookups: a hard identifier joins on equality, a name on its key.
        Index("ix_observation_domain_hash", "domain_hash"),
        Index("ix_observation_uen_hash", "uen_hash"),
        Index("ix_observation_name_key", "name_key"),
        {"schema": "er"},
    )


class BlockedValueRow(Base):
    """`er.blocked_value` (M14.6.1): a join key this install refuses, held as its digest."""

    __tablename__ = "blocked_value"

    kind: Mapped[str] = mapped_column(String(ENUM_CHARS), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(DIGEST_CHARS), primary_key=True)
    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)
    blocked_by: Mapped[str] = mapped_column(String(CREATED_BY_CHARS), nullable=False)
    blocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )

    __table_args__ = (
        CheckConstraint(one_of("kind", IdentifierKind), name="kind_known"),
        CheckConstraint(KEY_HASH_IS_A_DIGEST, name="key_hash_is_a_digest"),
        CheckConstraint(_present("reason"), name="reason_present"),
        CheckConstraint(_present("blocked_by"), name="blocked_by_present"),
        {"schema": "er"},
    )
