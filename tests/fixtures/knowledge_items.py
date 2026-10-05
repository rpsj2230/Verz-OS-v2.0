"""A database the re-verification nag can run in, and the rows it reads, built by migrations.

`tests.fixtures.scratch_postgres` stamps past everything before `0029`, and this cannot: the nag
resolves an owner's grants through `gate.resolve_entitlements`, so `0002` and `0003` are run for
real, stamped from `0001` because `0001` needs pgvector. `0025`, `0030` and `0037` follow for the
control-run table and the outbox, and then `0040` itself.

**The revision before `0040` is read off the migration rather than written here**, so this goes
on building the chain the migrations describe whichever revision sits before it, and a
predecessor that moves is not a fixture that quietly stamps the wrong one.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from brain.core.department import department_scope
from brain.core.scope import Scope
from brain.knowledge.item import KnowledgeItem
from brain.knowledge.item_store import NAG_ENTITY, put_item
from brain.knowledge.search import KNOWLEDGE_READ
from brain.session import make_app_engine, make_session_factory
from tests.fixtures.scratch_postgres import (
    ROOT,
    SCHEDULE_CONTROL_TABLES,
    STAMPED_AT,
    add_modelled,
    drop,
    fresh,
    migrate,
    run,
    sql,
)

ITEM_MIGRATION = ROOT / "migrations" / "versions" / "0040_knowledge_item.py"

#: The migration that adds `know.item.kind`. Its constants are read rather than restated.
KIND_MIGRATION = ROOT / "migrations" / "versions" / "0115_knowledge_item_kind.py"


def predecessor() -> str:
    """The revision `0040` names as the one before it."""
    spec = importlib.util.spec_from_file_location("migration_0040_predecessor", ITEM_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.down_revision)


def add_item_kind(url: str) -> None:
    """`know.item.kind` and its check, as `0115` adds them, on a chain that stops at `0040`.

    Applied from `0115`'s own constants rather than by running it, because `0115` also replaces
    `0069`'s library read, which a chain stopping at `0040` never built. `put_item` writes the
    column, so without it every write here fails. Whether `0115` itself builds exactly this is
    `tests/unit/test_knowledge_upload_db.py`'s, against a database migrated to head.
    """
    spec = importlib.util.spec_from_file_location("migration_0115_kind", KIND_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sql(url, f"ALTER TABLE know.item ADD COLUMN kind VARCHAR({module.KIND_CHARS})")
    sql(url, f"ALTER TABLE know.item ADD CONSTRAINT ck_item_kind CHECK ({module.KIND_CHECK})")


#: The migration adding `know.item`'s public marking. Its constants are read, not restated.
PUBLIC_MIGRATION = ROOT / "migrations" / "versions" / "0171_public_knowledge.py"


def add_item_public(url: str) -> None:
    """`know.item.public_by` and `public_at` and their checks, as `0171` adds them.

    From `0171`'s own constants, for `add_item_kind`'s reason: `0171` also creates a role and
    policies over `know.chunk`, which a chain stopping at `0040` never built. Whether `0171`
    itself builds exactly this is `tests/unit/test_public_knowledge.py`'s.
    """
    spec = importlib.util.spec_from_file_location("migration_0171_public", PUBLIC_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sql(url, f"ALTER TABLE know.item ADD COLUMN public_by VARCHAR({module.PRINCIPAL_CHARS})")
    sql(url, "ALTER TABLE know.item ADD COLUMN public_at TIMESTAMP WITH TIME ZONE")
    for name, check in (
        ("a_public_marking_names_a_person", module.A_MARKING_NAMES_A_PERSON),
        ("a_public_marker_names_a_time", module.A_MARKER_NAMES_A_TIME),
        ("a_personal_item_is_never_public", module.A_PERSONAL_ITEM_IS_NEVER_PUBLIC),
    ):
        sql(url, f"ALTER TABLE know.item ADD CONSTRAINT ck_item_{name} CHECK ({check})")


@contextmanager
def knowledge_items(database: str) -> Iterator[str]:
    """A fresh database holding the grant tables, the outbox, the run table and `know.item`."""
    scratch = fresh(database)
    try:
        migrate(database, "stamp", "0001")
        migrate(database, "upgrade", "0003")
        migrate(database, "stamp", "0024")
        migrate(database, "upgrade", "0025")
        migrate(database, "stamp", STAMPED_AT)
        migrate(database, "upgrade", "0030")
        migrate(database, "stamp", "0036")
        migrate(database, "upgrade", "0037")
        migrate(database, "stamp", predecessor())
        migrate(database, "upgrade", "0040")
        add_item_kind(scratch)
        add_item_public(scratch)
        # `ops.setting`, which `0004` builds and this chain stamps past: the sweep asks whether an
        # administrator switched the request off before it records anything.
        add_modelled(scratch, SCHEDULE_CONTROL_TABLES)
        yield scratch
    finally:
        drop(database)


def a_person(url: str, principal_id: str, *, disabled_at: datetime | None = None) -> None:
    sql(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name, disabled_at) "
        "VALUES (%s, 'human', 'staff', %s, %s)",
        principal_id,
        principal_id,
        disabled_at,
    )


def a_reader(url: str, principal_id: str, department: str) -> None:
    """A grant of `read:knowledge` in one department, as the grant table holds it."""
    sql(
        url,
        "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by, reason) "
        "VALUES (%s, %s, %s, %s, %s)",
        principal_id,
        KNOWLEDGE_READ.value,
        json.dumps(department_scope(department).model_dump(mode="json")),
        "u_seed",
        "loaded by the test fixture",
    )


def a_reader_of_everything(url: str, principal_id: str) -> None:
    """A grant of `read:knowledge` with an unrestricted scope, as the grant table holds it."""
    sql(
        url,
        "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by, reason) "
        "VALUES (%s, %s, %s, %s, %s)",
        principal_id,
        KNOWLEDGE_READ.value,
        json.dumps(Scope.unrestricted().model_dump(mode="json")),
        "u_seed",
        "loaded by the test fixture",
    )


def put(url: str, *items: KnowledgeItem) -> None:
    """Write items through `put_item`, committed."""

    async def write() -> None:
        made = make_app_engine(url)
        try:
            async with make_session_factory(made)() as session, session.begin():
                for one in items:
                    await put_item(session, one)
        finally:
            await made.dispose()

    run(write)


def nags(url: str) -> list[tuple[str, dict[str, Any]]]:
    """Every nag recorded, as the item it names and its attributes, in item order."""
    return [
        (row[0], row[1])
        for row in sql(
            url,
            "SELECT record_id, attributes FROM ops.outbox_event WHERE entity = %s "
            "ORDER BY record_id, occurred_at",
            NAG_ENTITY,
        )
    ]
