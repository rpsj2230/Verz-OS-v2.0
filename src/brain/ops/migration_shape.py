"""The migration round trip over a database shaped like an install, and a count of how shaped.

M0.5.3 asks for forward and rollback against production-shaped data. What CI had on 2026-09-17
was the round trip in every unit-test shard, run over whatever the shard's tests left behind
(324690c), and that already paid for itself when `0059`'s downgrade refused ledger rows a test had
written (f858071). But what tests leave is an accident of which tests landed in the shard, not the
shape of an install, and nothing said how much of the schema held a row when the rollback ran.

**So the `migrations_install_shaped` job builds an install first.** A database from empty, the
migrations to head, the demo company `brain.seed` loads (the same company the install job answers a
question from), and then a table-by-table row count before anything is taken back.

**One step back must lose nothing it keeps.** An install's own rollback re-pins the code and runs
no downgrade (`brain.deployment.release` argues why), so `alembic downgrade -1` is what a person
undoing the newest migration by hand runs, and a downgrade to base is what nobody runs on data. The
counts are taken at head, one step back and head again: every table that exists one step back
holds exactly the rows it held at head, and holds them still after the upgrade. A table the last
migration creates is absent one step back and is left out, because dropping it is the rollback.
Only then is the whole chain taken to base and back, which is the check the shards already make.

**The shape is printed as a number, not asserted as one.** `shape_line` says how many of the
schema's tables held a row when the rollback ran. Rejected: a floor on that number. The demo is
what an install holds on its first day, and a floor would be raised by seeding tables for the test
rather than by the demo becoming more like an install; the number is the measurement M0.5.3 needs,
and the gate is that nothing is lost.

Task ids: M0.5.3
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

LOST_NOTHING_IT_KEPT: Final = (
    "A downgrade that keeps a table and changes its row count has deleted or invented data on the "
    "way back, which is the rollback an install cannot undo. So every table present one step back "
    "must hold the rows it held at head, and hold them again after the upgrade."
)


def row_counts(database_url: str) -> dict[str, int]:
    """Every ordinary table in the application's schemas and its exact row count."""
    import psycopg
    from psycopg import sql

    from brain.db import SCHEMAS, libpq_conninfo

    counts: dict[str, int] = {}
    with psycopg.connect(libpq_conninfo(database_url)) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.nspname, c.relname FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = ANY(%(schemas)s) AND c.relkind IN ('r', 'p')
            ORDER BY 1, 2
            """,
            {"schemas": sorted(SCHEMAS)},
        )
        for schema, table in cur.fetchall():
            cur.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            )
            row = cur.fetchone()
            counts[f"{schema}.{table}"] = int(row[0]) if row else 0
    return counts


def losses(
    head: Mapping[str, int], back: Mapping[str, int], again: Mapping[str, int]
) -> tuple[str, ...]:
    """Tables the step back kept whose rows moved. See `LOST_NOTHING_IT_KEPT`."""
    found: list[str] = []
    for table, kept in sorted(back.items()):
        if table in head and head[table] != kept:
            found.append(f"{table}: {head[table]} row(s) at head, {kept} one step back")
        if again.get(table) != kept:
            found.append(f"{table}: {kept} row(s) one step back, {again.get(table)} after upgrade")
    return tuple(found)


def shape_line(counts: Mapping[str, int]) -> str:
    held = sum(1 for n in counts.values() if n > 0)
    return (
        f"shape: {held} of {len(counts)} table(s) held a row when the rollback ran, "
        f"{sum(counts.values())} row(s) in all"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m brain.ops.migration_shape")
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record", help="write every table's row count")
    record.add_argument("out", type=Path)
    compare = sub.add_parser("compare", help="refuse a rollback that lost rows it kept")
    compare.add_argument("head", type=Path)
    compare.add_argument("back", type=Path)
    compare.add_argument("again", type=Path)
    arguments = parser.parse_args(argv)

    if arguments.command == "record":
        from brain.settings import Settings

        url = Settings().database_url
        if not url:
            print("no database is configured, so nothing was counted", file=sys.stderr)
            return 1
        counts = row_counts(url)
        arguments.out.write_text(
            json.dumps(counts, indent=1) + "\n", encoding="utf-8", newline="\n"
        )
        print(shape_line(counts))
        return 0

    def load(path: Path) -> dict[str, int]:
        return {str(k): int(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}

    head = load(arguments.head)
    print(shape_line(head))
    empty = sorted(table for table, n in head.items() if n == 0)
    print(f"note: {len(empty)} table(s) held no row: {', '.join(empty)}")
    found = losses(head, load(arguments.back), load(arguments.again))
    for line in found:
        print(f"lost: {line}")
    if not any(head.values()):
        print("FAIL: nothing was seeded, so the round trip ran over an empty database")
        return 1
    print(f"{'FAIL' if found else 'ok'}: one step back and forward kept every row it kept")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
