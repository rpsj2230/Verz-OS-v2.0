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


def predecessor() -> str:
    """The revision `0040` names as the one before it."""
    spec = importlib.util.spec_from_file_location("migration_0040_predecessor", ITEM_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.down_revision)


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
