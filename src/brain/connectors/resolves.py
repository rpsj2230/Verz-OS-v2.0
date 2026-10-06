"""What a connector says about its records for entity resolution: their type, their name, money.

`brain.resolution.entities` holds one profile per entity type and reads a record's name and join
keys by the profile's own field names (`name`, `domain`, `uen` and so on). Nothing said which of a
connector's records are companies, which are people, which of their projected fields holds the name,
or which carry financial records. This is where a connector says so, in its own module, beside its
Ask rows (`brain.connectors.declaration.ConnectorDeclaration.resolves`).

**Declared by the connector, never listed centrally.** A map in `brain.resolution` keyed by
connector names would be a hand-kept list every connector appends to, which is the class #342
removed for Ask rows: two connectors added at once conflict in it, and a third-party connector
cannot add itself without editing the product. `brain.resolution.sources` discovers the
declarations the way `brain.knowledge.connector_rows` discovers Ask rows. See
`A_CONNECTOR_SAYS_WHAT_ITS_RECORDS_ARE`.

**Outside the pinned manifest, deliberately.** The manifest's projected entities are inside
`brain.connectors.manifest.manifest_digest`, and a connection whose manifest changes is quarantined
on its next reconnect until an administrator accepts the upgrade. A record's entity type and its
money flag say nothing about what the connector reads or what a model is told it can do, which is
what the pin protects, so putting them in the digest would quarantine every connected source on the
release that added them for no protection gained. See `NOT_IN_THE_PIN_BECAUSE_IT_CHANGES_NO_CALL`.

**A renaming, not a copy.** `fields` maps the profile's field names onto the entity's projected
fields, so Laravel's staff record is read by `display_name` and a company by `name`. Only fields the
entity already projects can be named, which a test holds against each connector's own manifest:
this cannot widen what is kept, only say which kept field means what.

**Money is declared, and an entity that declares nothing has not been asked.** `carries_money` is
the connector's statement that records of this entity hold invoices, contract values or margins.
`brain.resolution.merge.MoneyBearing` reads it later; the declaration is here so the fact lives with
the code that knows it. See `MONEY_IS_A_FACT_ABOUT_THE_SOURCE`.

Task ids: M14.1.1, M14.7.3
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from brain.core.envelope import OBJECT_NAME_PATTERN
from brain.resolution.canonical import EntityType

# ------------------------------------------------------------------ written-down reasons
#: Why each connector declares its own records.
A_CONNECTOR_SAYS_WHAT_ITS_RECORDS_ARE: Final = (
    "Which records are companies, which are people and which field names them are facts about one "
    "connector, known by the code that reads it. A central list would be a second account of the "
    "connector that could disagree with its first, and a place every new connector has to edit."
)

#: Why the declaration is outside the manifest digest.
NOT_IN_THE_PIN_BECAUSE_IT_CHANGES_NO_CALL: Final = (
    "The manifest digest pins what a connector reads and what a model is told it can do, and a "
    "changed digest quarantines a connection until a person accepts it. A record's entity type "
    "and its money flag change neither, so pinning them would quarantine every connected source "
    "on the release that added them and protect nothing."
)

#: Why the money flag is declared rather than inferred.
MONEY_IS_A_FACT_ABOUT_THE_SOURCE: Final = (
    "Whether a record carries financial records is known by the connector that reads the source: "
    "an accounting contact has invoices and a client view has contract values. Inferring it from "
    "field names would make the sharpest merge guard a guess."
)

#: The profile field names a renaming may target. `brain.resolution.entities` reads these.
PROFILE_FIELDS: Final[frozenset[str]] = frozenset(
    {"name", "uen", "tax_id", "domain", "country", "postcode"}
)

_NAME_RE: Final = re.compile(OBJECT_NAME_PATTERN)


class ResolvesError(ValueError):
    """A connector declared its records for resolution in a shape nothing can use."""


@dataclass(frozen=True)
class ResolvesAs:
    """One entity kind of one connector, as entity resolution should read it."""

    #: The entity name exactly as the connector's manifest projects it.
    entity: str
    entity_type: EntityType
    #: Profile field name to this entity's projected field name. `name` is required.
    fields: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    #: Whether records of this entity hold invoices, contract values or margins.
    carries_money: bool = False

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.entity):
            msg = f"{self.entity!r} is not an entity name"
            raise ResolvesError(msg)
        if "name" not in self.fields:
            msg = (
                f"{self.entity} names no field for the name, so every record would reach the "
                "cascade with nothing to normalise"
            )
            raise ResolvesError(msg)
        unknown = sorted(set(self.fields) - PROFILE_FIELDS)
        if unknown:
            msg = (
                f"{self.entity} renames onto {unknown}, which no profile reads; a renaming nothing "
                "reads is a claim with nothing behind it"
            )
            raise ResolvesError(msg)
        blank = sorted(one for one, projected in self.fields.items() if not projected.strip())
        if blank:
            msg = f"{self.entity} maps {blank} onto no projected field"
            raise ResolvesError(msg)
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def renamed(self, fields: Mapping[str, object]) -> dict[str, object]:
        """A record's projected fields under the profile's names, and nothing else."""
        return {
            profile: fields[projected]
            for profile, projected in sorted(self.fields.items())
            if projected in fields
        }
