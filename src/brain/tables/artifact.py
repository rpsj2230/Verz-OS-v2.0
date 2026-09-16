"""What an agent produced: one row per artifact, pointing at bytes kept in the object store.

`brain.console.agent_output` decided what an artifact record carries, who may know one exists and
how long it is kept, and built `Artifact` for it with no store. `brain.artifact_routes` said so on
every install. This is the store's table, `0058` builds it, and `brain.ops.artifact_store` is the
one writer.

**The row mirrors `Artifact` and adds only where the bytes are.** The object key, the bytes' media
type and the sha256 of exactly what was put, so a file fetched back can be checked against the
record that describes it. There is no column the content could arrive in, which is
`Artifact`'s own refusal carried into the schema: a record holding its bytes is a second copy of
the file under the database's retention rather than the one its class decided.

**The retention class is a column the database checks, and the window is not.** `data_class` is
one of `brain.ops.retention.DataClass`, decided by `retention_class_for` when the row is written,
and when the artifact stops being kept is `brain.ops.retention.expires_at` over that class and
`produced_at`. Storing the date as well would be a second answer to one question, and the copy
is the one that goes stale when a class's window is changed in a release.

**The key names the class and nothing about the content.** `<prefix>/artifacts/<class>/<id>`, with
a random identifier, checked here as a shape: a key built from a title or a file name is a name
that says what a document is about, sitting in a bucket listing somebody else can read. The class
is in the key so a lifecycle rule scoped to a prefix can apply that class's window to the bytes,
which is the one way a bucket with a single rule can hold several windows.

**No state column, no successor, never edited, never removed.** SELECT and INSERT only.
`supersede` and `archive` in `brain.console.agent_output` return new records and nothing here
stores one yet, so every row is current, and saying so in the schema is better than a column
nothing writes.

Task ids: M39.5.1.1, M39.5.1.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from brain.console.agent_output import ArtifactKind
from brain.db import Base
from brain.ops.retention import DataClass
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: How wide an artifact's identifier may be. A uuid in hex is thirty-two.
ARTIFACT_ID_CHARS: Final = 64
#: An artifact's identifier: lower-case hex, as `brain.ops.artifact_store` mints it.
ARTIFACT_ID_PATTERN: Final = r"^[0-9a-f]{32}$"
#: How wide an agent's identifier may be, matching `brain.tables.skill.AGENT_ID_CHARS`.
AGENT_ID_CHARS: Final = 128
#: How wide a run's identifier may be.
RUN_ID_CHARS: Final = 128
#: How wide an agent version may be.
VERSION_CHARS: Final = 64
#: How wide a kind and a class may be.
KIND_CHARS: Final = 16
CLASS_CHARS: Final = 32
#: How wide a media type may be.
CONTENT_TYPE_CHARS: Final = 128
#: How wide an object key may be.
OBJECT_KEY_CHARS: Final = 256
#: What an object key may be: a prefix word, the artifacts segment, the class, the identifier.
#: No colon and no `(?:`, because SQLAlchemy reads either inside a constraint's text as a bind.
OBJECT_KEY_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}/artifacts/[a-z_]{1,32}/[0-9a-f]{32}$"
#: An entitlement hash, as `EntitlementSet.ent_hash` returns it.
ENT_HASH_PATTERN: Final = r"^[0-9a-f]{32}$"
#: A sha256 in lower-case hex.
DIGEST_PATTERN: Final = r"^[0-9a-f]{64}$"


class ArtifactRow(Base):
    """`agent.artifact`. One thing an agent produced for somebody, and where its bytes are."""

    __tablename__ = "artifact"

    artifact_id: Mapped[str] = mapped_column(String(ARTIFACT_ID_CHARS), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    kind: Mapped[str] = mapped_column(String(KIND_CHARS), nullable=False)
    run_id: Mapped[str] = mapped_column(String(RUN_ID_CHARS), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(VERSION_CHARS), nullable=False)
    caller_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    entitlement_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    produced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_class: Mapped[str] = mapped_column(String(CLASS_CHARS), nullable=False)
    bytes_stored: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(CONTENT_TYPE_CHARS), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(OBJECT_KEY_CHARS), nullable=False)
    #: Connector names and knowledge item ids the run drew on, in the run's order. Narrowed to a
    #: reader by `brain.console.agent_output.provenance_for` and never shown whole.
    sources: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    knowledge_items: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )

    __table_args__ = (
        CheckConstraint(f"artifact_id ~ '{ARTIFACT_ID_PATTERN}'", name="artifact_id_shape"),
        CheckConstraint(one_of("kind", ArtifactKind), name="kind"),
        CheckConstraint(one_of("data_class", DataClass), name="data_class"),
        CheckConstraint(
            "length(btrim(agent_id)) > 0 AND length(btrim(run_id)) > 0 "
            "AND length(btrim(caller_id)) > 0 AND length(btrim(agent_version)) > 0",
            name="attributed",
        ),
        CheckConstraint(f"entitlement_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        CheckConstraint(f"content_digest ~ '{DIGEST_PATTERN}'", name="digest_shape"),
        CheckConstraint(f"object_key ~ '{OBJECT_KEY_PATTERN}'", name="object_key_shape"),
        CheckConstraint("bytes_stored > 0", name="holds_bytes"),
        Index("ix_artifact_caller_produced", "caller_id", "produced_at"),
        {"schema": "agent"},
    )
