"""A table outside the designed hard deletes grants the application no DELETE, from the migrations.

M27.15.52 asks that every destructive control name its act and that no table outside the designed
hard deletes grant the application a delete. The console half is
`console/tests/destructive-labels.test.ts`. This file is the table half, and it exists because the
guard that held it before read text.
`tests/unit/test_directory_role_grant.py` scanned lines beginning with a quoted `GRANT` and the
`GRANTS` tuple of each migration, and `0226` gave the application `DELETE` on `obs.trace_step`
through an f-string constant named `GRANT`, which neither scan sees. Six tables held the privilege
and five were named, with the suite green.

The set is derived from `brain.ops.application_privileges`, which renders the migrations as the SQL
they would run, so a grant built in a loop, an f-string or a constant is as visible as one written
out, and a privilege held through a role the application inherits counts.

Task ids: M27.15.52
"""

from __future__ import annotations

import pytest

from brain.ops.application_privileges import (
    APPLICATION_ROLE,
    catalogue_of,
    migrations_catalogue,
)
from brain.ops.hard_deletes import (
    A_TABLE_OUTSIDE_THE_DESIGNED_HARD_DELETES_GRANTS_THE_APPLICATION_NO_DELETE,
    DESIGNED_HARD_DELETES,
    held_by_the_application,
)


def test_the_application_may_delete_from_exactly_the_designed_tables() -> None:
    """The set the migrations leave behind equals the argued set, in both directions.

    Delete this and the next table that finds `deleted_at` inconvenient grants DELETE through an
    f-string or a constant, as 0226 did, and nothing notices; or a designed table loses its grant
    and the retention sweep that relies on it reports "kept" for ever.
    """
    held = held_by_the_application(migrations_catalogue())
    assert held == frozenset(DESIGNED_HARD_DELETES), (
        f"granted and not designed: {sorted(held - set(DESIGNED_HARD_DELETES))}; "
        f"designed and not granted: {sorted(set(DESIGNED_HARD_DELETES) - held)}"
    )


def test_a_table_the_text_scan_missed_is_found() -> None:
    """`obs.trace_step` is held through an f-string constant in 0226 and is in the derived set.

    Delete this and the derivation could be replaced by the line scan it replaced, which names five
    tables of the six and passes.
    """
    assert "obs.trace_step" in held_by_the_application(migrations_catalogue())


def test_every_designed_hard_delete_argues_why() -> None:
    """Each entry says why a hard delete is the design, in a sentence and not a word.

    Delete this and an entry can be added with a reason of "needed", which is the precedent the
    rule exists to prevent.
    """
    for table, reason in DESIGNED_HARD_DELETES.items():
        assert "." in table, f"{table} is not a qualified table name"
        assert len(reason.split()) >= 20, f"{table} is allowed without an argument"
    assert A_TABLE_OUTSIDE_THE_DESIGNED_HARD_DELETES_GRANTS_THE_APPLICATION_NO_DELETE.endswith(
        "Every other table retires its rows."
    )


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        pytest.param(
            "CREATE TABLE x.y (a int);\nGRANT SELECT, INSERT, UPDATE, DELETE ON x.y TO brain_app;",
            {"x.y"},
            id="a plain grant",
        ),
        pytest.param(
            "CREATE TABLE x.y (a int);\nGRANT DELETE ON x.y TO brain_app;",
            {"x.y"},
            id="a grant of DELETE alone, as 0226 writes it",
        ),
        pytest.param(
            "CREATE ROLE other;\nCREATE TABLE x.y (a int);\nGRANT DELETE ON x.y TO other;\n"
            "GRANT other TO brain_app;",
            {"x.y"},
            id="held through a role the application is a member of",
        ),
        pytest.param(
            "CREATE TABLE x.y (a int);\nGRANT SELECT, INSERT, UPDATE ON x.y TO brain_app;",
            set(),
            id="every other privilege leaves the table out",
        ),
        pytest.param(
            "CREATE TABLE x.y (a int);\nGRANT DELETE ON x.y TO brain_app;\n"
            "REVOKE DELETE ON x.y FROM brain_app;",
            set(),
            id="a revoked grant is not held",
        ),
        pytest.param(
            "CREATE ROLE other;\nCREATE TABLE x.y (a int);\nGRANT DELETE ON x.y TO other;",
            set(),
            id="a role the application is not a member of does not count",
        ),
    ],
)
def test_the_derivation_reads_each_way_a_delete_can_be_held(sql: str, expected: set[str]) -> None:
    """The reading itself, driven from SQL written here, with the positive case beside each refusal.

    Delete this and a change to `held_by_the_application` that ignored role membership, treated a
    revoke as no revoke, or matched any privilege, passes the one test that reads the real
    migrations, because the real migrations do not use every one of these shapes today.
    """
    assert APPLICATION_ROLE == "brain_app"
    assert held_by_the_application(catalogue_of(sql)) == frozenset(expected)
