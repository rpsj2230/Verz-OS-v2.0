"""A database holding every soft-deleted table with 0045 applied, built through the migrations.

**Two chains, chosen by whether the server has pgvector.** Where it does, which is CI, `0001` is
stamped over what `tests.fixtures.scratch_postgres.fresh` leaves plus the four extensions `0001`
would have created, and the database is upgraded to head, so every table and every later
migration is real. Where it does not, `0002` to `0008`, `0019`, `0045` and `0048` are run for
real and everything between them is stamped: all but `0048` build and repair the soft-deleted
tables other than `know.chunk`, `0048` is the function the entitlement store calls, and none of
them needs the extension. `know.chunk`
is then absent, and `present_tables` says so rather than a test assuming it.

**The revision before 0045 is read off the migration**, for the reason
`tests.fixtures.knowledge_items` gives.

Task ids: none
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

from tests.fixtures.scratch_postgres import ROOT, drop, fresh, migrate, sql

RETIRABLE_MIGRATION = ROOT / "migrations" / "versions" / "0045_retirable_rows.py"

#: The resolver's lapse, which `brain.gate.entitlement_store` calls. It reads only `0002`'s and
#: `0003`'s tables, so it is run for real on the chain without pgvector too, and every fixture
#: whose tests load a reach through the store has it.
LAPSE_MIGRATION = ROOT / "migrations" / "versions" / "0048_grant_lapse.py"

#: What `0001` creates as extensions, restated for the reason `scratch_postgres.SCHEMAS` gives.
EXTENSIONS: tuple[str, ...] = ("vector", "pg_trgm", "fuzzystrmatch", "unaccent")


def _migration(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def predecessor(path: Path = RETIRABLE_MIGRATION) -> str:
    """The revision a migration names as the one before it, `0045` unless told otherwise."""
    return str(_migration(path).down_revision)


def revision_of(path: Path) -> str:
    """The revision a migration file declares, read off the file rather than its name."""
    return str(_migration(path).revision)


def has_pgvector(url: str) -> bool:
    return bool(sql(url, "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"))


@contextmanager
def retirable(database: str) -> Iterator[str]:
    """A fresh database holding the soft-deleted tables with their policies repaired."""
    scratch = fresh(database)
    try:
        if has_pgvector(scratch):
            for extension in EXTENSIONS:
                sql(scratch, f'CREATE EXTENSION IF NOT EXISTS "{extension}"')
            migrate(database, "stamp", "0001")
            migrate(database, "upgrade", "head")
        else:
            migrate(database, "stamp", "0001")
            migrate(database, "upgrade", "0008")
            # `0015` repairs the slug constraints `0003` mangled, without which no row can be
            # written to `gate.scope`, `gate.department` or `gate.team` at all.
            migrate(database, "stamp", "0014")
            migrate(database, "upgrade", "0015")
            migrate(database, "stamp", "0018")
            migrate(database, "upgrade", "0019")
            migrate(database, "stamp", predecessor())
            migrate(database, "upgrade", "0045")
            # A fixture stamping an earlier revision after this keeps the functions: a stamp
            # rewrites the version row and runs nothing.
            migrate(database, "stamp", predecessor(LAPSE_MIGRATION))
            migrate(database, "upgrade", revision_of(LAPSE_MIGRATION))
        yield scratch
    finally:
        drop(database)


def present_tables(url: str) -> frozenset[str]:
    """Every `schema.table` in this database with a `deleted_at` column."""
    rows = sql(
        url,
        "SELECT table_schema || '.' || table_name FROM information_schema.columns"
        " WHERE column_name = 'deleted_at'"
        " AND table_schema NOT IN ('pg_catalog', 'information_schema')",
    )
    return frozenset(str(row[0]) for row in rows)
