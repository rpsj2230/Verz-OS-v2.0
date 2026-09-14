"""The plugin registry: which plugins this install holds, in what state, and every version it ran.

`brain.plugins.lifecycle` holds install, enable, disable, upgrade and rollback as functions over an
`Installed` value, and `brain.plugins.points` holds the register of extension points as a compiled
constant. Neither remembers anything. These are the two tables M29.2.2 asks for, and
`brain.ops.plugin_registry` is what reads and writes them.

**The extension points are not a table, and that is `brain.plugins.points`' own argument.** The
register is a fact about the product, checked against the source by `contract_gaps`. A table
mirroring it would be a second copy of a constant, which `brain.tables.schedule` refuses for the
registry of controls in the same words. What gets the constant instead is a check constraint
generated from it: a plugin row may only name a point whose answer is `PLUGIN`, so a manifest for
the storage backend or the scope pack, which the register refuses as plugin points, is refused by
the table too.

**Two tables, and the split is the one `brain.tables.template` makes.** `ops.plugin_version` is
every manifest this install has actually run, appended and never edited, keyed by plugin and
version. `ops.plugin_install` is the one plugin's current record, which moves. A rollback needs
the manifest of a version this install ran, and `lifecycle.A_VERSION_THIS_INSTALL_HAS_NEVER_RUN_IS_
NOT_SOMEWHERE_TO_ROLL_BACK_TO` is why that has to be the document that ran rather than one fetched
again from the author: a version string names a document, and a registry that let the document
under one version change would roll back to something nobody ran.

**The manifest is carried whole, as the document.** `Installed` carries the manifest rather than
an id and a version, because every question worth asking of an install is a question about the
manifest, and a record holding only the pair would send each reader back to a registry. The
three columns repeated from it are there to be constrained and indexed, and a check constraint
ties each to the document so the two cannot disagree.

**Nothing arrives enabled, in the database as well.** `lifecycle.TRANSITIONS` has no edge from
`ABSENT` to `ENABLED`. There are two ways out of `ABSENT` in this table, an insert for a plugin
never seen and an update of a removed row for one coming back, and both are held to `installed`:
the insert by its policy and the return by a trigger that reads the row before the change. The
rest of the transition table is not restated in SQL: the edge that matters most is the one a person
could otherwise skip by writing one row, and a trigger copying all five edges would be a second
implementation of a table with a written argument.

**Removal retires the row rather than deleting it.** `ABSENT` is what `Installed` refuses to be
recorded as, so a removed plugin is a row with `removed_at` set, which the store reads as absent.
It was first written as a DELETE, and `tests/unit/test_directory_role_grant.py` refused it: the
directory role grant is the one DELETE in the system and that test exists so it does not become a
precedent. It was right to. A deleted install row takes with it when the plugin stopped running
here, and a check constraint on the retired row says the other half of the lifecycle's rule:
only a disabled plugin may be removed, the one edge into `ABSENT`.

Task ids: M29.2.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.plugins.lifecycle import PluginState
from brain.plugins.manifest import PLUGIN_ID_RE
from brain.plugins.points import Answer, points_answering
from brain.tables.identity import one_of

#: Every point a plugin may plug into, from the register. Generated so a point decided later
#: widens the constraint in the same edit that decides it, and a migration makes it true.
PLUGIN_POINTS: Final[tuple[str, ...]] = tuple(
    sorted(one.name for one in points_answering(Answer.PLUGIN))
)

#: The states a record may be in. Every state but `ABSENT`, which a removed row stands for.
RECORDED_STATES: Final[tuple[str, ...]] = tuple(
    sorted(one.value for one in PluginState if one is not PluginState.ABSENT)
)

#: The width of a plugin id, from the grammar the manifest holds it to.
PLUGIN_ID_CHARS: Final = 80

#: The width of a version string.
VERSION_CHARS: Final = 64


class PluginVersionRow(Base):
    """`ops.plugin_version`. One manifest this install has run, kept for ever (M29.2.2)."""

    __tablename__ = "plugin_version"

    plugin_id: Mapped[str] = mapped_column(String(PLUGIN_ID_CHARS), primary_key=True)
    version: Mapped[str] = mapped_column(String(VERSION_CHARS), primary_key=True)
    #: The document that ran, exactly as `PluginManifest.model_dump(mode="json")` writes it.
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    first_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("jsonb_typeof(manifest) = 'object'", name="manifest_object"),
        CheckConstraint(
            "manifest ->> 'plugin_id' = plugin_id AND manifest ->> 'version' = version",
            name="manifest_is_this_version",
        ),
        {"schema": "ops"},
    )


class PluginInstallRow(Base):
    """`ops.plugin_install`. One plugin on this install, as it stands now (M29.2.2).

    Mirrors `brain.plugins.lifecycle.Installed`, plus `removed_at`. The composite foreign key
    into `ops.plugin_version` is what makes "the version it is running" a version this install
    has a document for, which is what a rollback away from it will later need.
    """

    __tablename__ = "plugin_install"

    plugin_id: Mapped[str] = mapped_column(String(PLUGIN_ID_CHARS), primary_key=True)
    version: Mapped[str] = mapped_column(String(VERSION_CHARS), nullable=False)
    point: Mapped[str] = mapped_column(String(PLUGIN_ID_CHARS), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Every version this install has run, oldest first, repeats included.
    history: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    #: When the plugin was taken off the install. Null while it is on it.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"plugin_id ~ '{PLUGIN_ID_RE.pattern}'", name="plugin_id_shape"),
        CheckConstraint(one_of("point", PLUGIN_POINTS), name="point_takes_a_plugin"),
        CheckConstraint(one_of("state", RECORDED_STATES), name="state"),
        CheckConstraint(
            "cardinality(history) >= 1 AND version = ANY (history)",
            name="running_version_is_in_history",
        ),
        CheckConstraint("jsonb_typeof(manifest) = 'object'", name="manifest_object"),
        CheckConstraint(
            "manifest ->> 'plugin_id' = plugin_id AND manifest ->> 'version' = version "
            "AND manifest ->> 'point' = point",
            name="manifest_is_this_install",
        ),
        # `DISABLED -> ABSENT` is the only edge into absent, so only a disabled row is retired.
        CheckConstraint(
            f"removed_at IS NULL OR state = '{PluginState.DISABLED.value}'",
            name="removed_only_when_disabled",
        ),
        ForeignKeyConstraint(
            ["plugin_id", "version"],
            ["ops.plugin_version.plugin_id", "ops.plugin_version.version"],
        ),
        {"schema": "ops"},
    )
