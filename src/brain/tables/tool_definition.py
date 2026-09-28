"""`agent.tool_definition` and `agent.tool_switch`: every tool an install offers, and its stops.

**`agent.tool_definition` is the catalogue as the database holds it (M12.1.1).** One row per tool
name a process on this install has registered, written from the frozen registry by
`brain.ops.tool_store.record_definition`, carrying what the Tools screen says about a tool: the
capability it needs, its side effect and whether that effect is one a person approves every time,
the sensitive effect it names, the result contract it declares (M12.1.4) and whose credential it
runs as. The name is checked against the closed grammar by the database as well as by
`brain.tools.registry.assert_tool_name`, from the one pattern `brain.core.envelope` writes down,
so a row can never name a tool no registry would accept. Rows are updated and never deleted: a
tool a release stops registering keeps its row, so a stop that names it still points at
something and the Tools screen can say the tool is no longer offered.

**`agent.tool_switch` holds stops and nothing else (M12.4.3).** One live row is one tool switched
off for the whole install (`department` null) or stopped for one department's people. Switching a
tool back on retires the row with `deleted_at` and says who did it and why; there is no row that
says a tool is on, which is `brain.tools.registry.A_SWITCH_ONLY_EVER_NARROWS` in the only place
it can be enforced for good. One live stop per tool and department, including one per tool for
the install.

**Stopping needs no reason and starting again needs one**, for `brain.ops.halt`'s reason: a wrong
stop is an outage somebody can undo and a wrong start is the incident carrying on. So `off_reason`
may be null, and `brain.tool_routes` refuses a retirement without an `on_reason`. That rule is the
route's and not a check constraint coupling `deleted_at` to `switched_on_by`, because every
retirable table here is retired by one generic statement in
`tests/unit/test_retirable_rows.py`, which is how its policies are proved, and a table that could
not be retired that way would be the one table nobody proved.

Task ids: M12.1.1, M12.1.4, M12.4.3
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from brain.core.envelope import OBJECT_NAME_PATTERN, IdentityMode, SideEffect
from brain.db import Base, SoftDeleteMixin, TimestampMixin
from brain.tables.gate import (
    CAPABILITY_CHARS,
    CAPABILITY_PATTERN,
    ENTITY_CHARS,
    TOOL_NAME_CHARS,
    TOOL_NAME_PATTERN,
)
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of
from brain.tools.registry import ResultContract, SensitiveEffect

#: Wide enough for the longest value of any of the four vocabularies below, with room.
VOCABULARY_CHARS: Final = 32

#: As wide as `auth.principal.primary_department`, which is the value a department stop is
#: compared with at every call.
DEPARTMENT_CHARS: Final = 120

#: `ToolDefinition.description` is `Field(max_length=400)`.
DESCRIPTION_CHARS: Final = 400

#: `brain.core.envelope.TOOL_NAME_PATTERN` with its named groups made plain, as
#: `brain.tables.gate` already renders it for PostgreSQL. One rendering, two constraints.
TOOL_NAME_SQL_PATTERN: Final = TOOL_NAME_PATTERN

#: The object grammar, which uses nothing PostgreSQL's regex engine lacks.
OBJECT_NAME_SQL_PATTERN: Final = OBJECT_NAME_PATTERN

#: The source is the name's first segment, which is how `RegisteredTool.source` reads it.
SOURCE_IS_THE_NAME_PREFIX: Final = "source = split_part(name, '.', 1)"


class ToolDefinitionRow(TimestampMixin, Base):
    """One tool name an install has registered, with what the Tools screen says about it."""

    __tablename__ = "tool_definition"

    name: Mapped[str] = mapped_column(String(TOOL_NAME_CHARS), primary_key=True)
    source: Mapped[str] = mapped_column(String(TOOL_NAME_CHARS), nullable=False)
    entity: Mapped[str] = mapped_column(String(ENTITY_CHARS), nullable=False)
    description: Mapped[str] = mapped_column(String(DESCRIPTION_CHARS), nullable=False)
    required_capability: Mapped[str] = mapped_column(String(CAPABILITY_CHARS), nullable=False)
    side_effect: Mapped[str] = mapped_column(String(VOCABULARY_CHARS), nullable=False)
    #: `ToolDefinition.declares_sensitive_effect()`: a person approves every call.
    sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sensitive_effect: Mapped[str | None] = mapped_column(String(VOCABULARY_CHARS), nullable=True)
    result_contract: Mapped[str] = mapped_column(String(VOCABULARY_CHARS), nullable=False)
    identity_mode: Mapped[str] = mapped_column(String(VOCABULARY_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint(f"name ~ '{TOOL_NAME_SQL_PATTERN}'", name="name_grammar"),
        CheckConstraint(SOURCE_IS_THE_NAME_PREFIX, name="source_is_the_name_prefix"),
        CheckConstraint(f"entity ~ '{OBJECT_NAME_SQL_PATTERN}'", name="entity_grammar"),
        CheckConstraint(
            f"required_capability ~ '{CAPABILITY_PATTERN}'", name="required_capability_grammar"
        ),
        CheckConstraint(one_of("side_effect", SideEffect), name="side_effect"),
        CheckConstraint(one_of("result_contract", ResultContract), name="result_contract"),
        CheckConstraint(one_of("identity_mode", IdentityMode), name="identity_mode"),
        CheckConstraint(
            f"sensitive_effect IS NULL OR {one_of('sensitive_effect', SensitiveEffect)}",
            name="sensitive_effect",
        ),
        # A named effect is a sensitive one on a tool that changes something, which is
        # `brain.tools.registry.assert_sensitive_effect_declared` held by the database too.
        CheckConstraint(
            "sensitive_effect IS NULL OR (sensitive AND side_effect <> 'none')",
            name="a_named_effect_is_sensitive",
        ),
        CheckConstraint("length(btrim(description)) > 0", name="description_present"),
        {"schema": "agent"},
    )


class ToolSwitchRow(TimestampMixin, SoftDeleteMixin, Base):
    """One stop on one tool, for the install or for one department, retired and never deleted."""

    __tablename__ = "tool_switch"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tool_name: Mapped[str] = mapped_column(
        String(TOOL_NAME_CHARS),
        ForeignKey("agent.tool_definition.name", ondelete="RESTRICT"),
        nullable=False,
    )
    #: Null for the whole install.
    department: Mapped[str | None] = mapped_column(String(DEPARTMENT_CHARS), nullable=True)
    switched_off_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    off_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    switched_on_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    on_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "department IS NULL OR length(btrim(department)) > 0", name="department_present"
        ),
        CheckConstraint(
            "off_reason IS NULL OR length(btrim(off_reason)) > 0", name="off_reason_present"
        ),
        CheckConstraint(
            "on_reason IS NULL OR length(btrim(on_reason)) > 0", name="on_reason_present"
        ),
        Index(
            "uq_tool_switch_tool_name_department_live",
            "tool_name",
            text("coalesce(department, '')"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "agent"},
    )
