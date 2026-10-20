"""The two questions a rehearsal asks a loaded copy that its row counts cannot answer.

`ops/backup/brain-restore-drill` loads a copy into a scratch database and compares every table's row
count and the migration head with the copy's manifest. That is the `smoke_query` check, and it
catches a load that stopped early. It cannot see a load that brought back every row and none of the
rules about who may read them, which is the failure `brain.ops.recovery` argues is the quiet one
(`A_RESTORE_CAN_BRING_BACK_EVERY_ROW_AND_NONE_OF_THE_POLICIES`). Until this module those two checks
were a paragraph in the drill page that a person was asked to do by hand, so a weekly rehearsal
could only ever be a rehearsal of the first question. This is the code that asks the other two, run
from the application's own image against the scratch database and nothing else.

**`schema_complete` asks the schema check the product already owns.** Every schema in
`brain.db.SCHEMAS` is present. It reuses `brain.ops.schema_check.missing_schemas` rather than a list
of its own, because that list drifted once already (the sweep's copy had lost `ops`), and a
rehearsal holding a fourth copy of it would drift the same way.

**`permission_canary` is four questions and every one of them has to be answered yes.** The
application's role is not a superuser and cannot bypass row-level security, because a restore that
recreated the role with `BYPASSRLS` answers everything to everybody. Every table in the product's
schemas has row-level security enabled, which is the sweep `python -m brain.ops.sweeps rls` runs
against a migrated database, asked here of the copy. The fast lane's role cannot write to any table
(`0008` granted it SELECT and nothing else). And the question a table-level sweep cannot ask: a
row is written into the scratch copy for a made-up owner, and the application's role, acting as a
stranger, is shown none of it, while acting as the owner it is shown the row. **The second half is
what stops the first from being satisfied by a policy that denies everyone.** A canary that only
refuses is satisfied by a copy in which the policy was lost and the table fell back to refusing
the owner too, which is a broken copy reported as a working one.

**The canary writes into the scratch copy, inside a transaction it always rolls back.** The scratch
database is disposable and so the write is safe there, and a read-only canary would have to find a
row somebody else's data happened to put in the copy, which is a canary that passes on an empty
install. It is refused anywhere else by the same value class that refuses a drill against the live
system: `main` takes the URL it is given and the service that calls it gives it the scratch
container's address and no other.

**The detail is prose about what was asked and never a value read out of the copy.** A drill report
goes into a ticket and an alert (`brain.ops.recovery.CheckRun`), so a sentence here names the
kind of fault and a count and never a table's contents. A table that lost its protection is
counted, not named, which costs a person one query to find and spares a report the schema of a
client's data.

Rejected: running the canary through the application's HTTP routes with a token for a made-up
person. It tests more, and it needs the application to be started against the copy, which is a
second container with the vault, the identity provider and the cache around it. That is the drill a
person does by hand today and is why the rehearsal was never weekly. The database's own policy is
the layer that decides, and asking it directly asks the layer that failed.

Rejected: a canary that reads a row already in the copy. See above.

Task ids: M30.3.7
"""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Sequence
from typing import Any, Final

import psycopg

from brain.db import SCHEMAS, libpq_conninfo
from brain.ops.recovery import Check, CheckRun
from brain.ops.schema_check import missing_schemas

#: The role the application connects as, which every policy is written to.
APPLICATION_ROLE: Final = "brain_app"

#: The role the fast lane reads as, which may select and do nothing else.
FAST_LANE_ROLE: Final = "brain_fastlane"

#: The setting `chat.conversation`'s policy reads, which the canary sets to ask as somebody.
PRINCIPAL_SETTING: Final = "app.principal_id"

#: Why the canary asks the owner as well as the stranger.
A_CANARY_THAT_ONLY_REFUSES_IS_SATISFIED_BY_A_COPY_THAT_REFUSES_EVERYONE: Final = (
    "A policy lost in the copy leaves the table enabled with nothing admitting anybody, which "
    "refuses the stranger and the owner alike. A canary that asked only the stranger would "
    "read that as a copy that works."
)

#: Said when the copy cannot be reached at all.
THE_COPY_WAS_NOT_REACHABLE: Final = (
    "the scratch copy did not answer, so nothing was asked of it and nothing about it passed"
)

#: What the canary row is made to look like, so a person reading a log knows whose it was.
_OWNER_PREFIX: Final = "drill-canary-owner-"
_STRANGER_PREFIX: Final = "drill-canary-stranger-"


def schema_complete(present: set[str]) -> CheckRun:
    """Every schema the application expects, asked of what the copy holds."""
    missing = missing_schemas(present)
    if missing:
        return CheckRun(
            check=Check.SCHEMA_COMPLETE,
            passed=False,
            detail=(
                f"the scratch copy lacks {len(missing)} of the {len(SCHEMAS)} schemas the "
                "application expects, so the load stopped early or the copy is of something else"
            ),
        )
    return CheckRun(
        check=Check.SCHEMA_COMPLETE,
        passed=True,
        detail=(
            f"all {len(SCHEMAS)} schemas the application expects are present in the scratch copy"
        ),
    )


def _role_findings(rows: Sequence[tuple[str, bool, bool]]) -> list[str]:
    """What is wrong with the roles a copy brought back, as sentences naming a role's kind."""
    by_name = {name: (is_super, bypass) for name, is_super, bypass in rows}
    findings: list[str] = []
    for role, kind in ((APPLICATION_ROLE, "application"), (FAST_LANE_ROLE, "fast lane")):
        if role not in by_name:
            findings.append(f"the {kind} role does not exist in the scratch copy")
            continue
        is_super, bypass = by_name[role]
        if is_super or bypass:
            findings.append(f"the {kind} role can bypass row-level security in the scratch copy")
    return findings


def permission_canary(conn: Any) -> CheckRun:
    """The four permission questions, asked on one connection to the scratch copy.

    `conn` is a psycopg connection to the scratch database as a role that may `SET ROLE` to the
    application's, which is the superuser the scratch container was made with. It is left with
    nothing changed: the canary row and every setting live in a transaction rolled back at the end,
    including when a question raises, so a failure to ask is a failure and not a leftover row.
    """
    findings: list[str] = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = ANY(%s)",
            ([APPLICATION_ROLE, FAST_LANE_ROLE],),
        )
        roles = [(r[0], bool(r[1]), bool(r[2])) for r in cur.fetchall()]
        findings.extend(_role_findings(roles))
        application_role_exists = any(name == APPLICATION_ROLE for name, _, _ in roles)

        cur.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = ANY(%s) AND c.relkind = 'r' AND NOT c.relrowsecurity",
            (sorted(SCHEMAS),),
        )
        unprotected = int(cur.fetchone()[0])
        if unprotected:
            findings.append(
                f"{unprotected} table(s) in the scratch copy have row-level security switched off"
            )

        cur.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = ANY(%s) AND c.relkind = 'r' AND EXISTS "
            "(SELECT 1 FROM pg_roles WHERE rolname = %s) AND "
            "has_table_privilege(%s, c.oid, 'INSERT,UPDATE,DELETE')",
            (sorted(SCHEMAS), FAST_LANE_ROLE, FAST_LANE_ROLE),
        )
        writable = int(cur.fetchone()[0])
        if writable:
            findings.append(
                f"the fast lane's role can write to {writable} table(s) in the scratch copy"
            )

    if application_role_exists:
        findings.extend(_owner_and_stranger(conn))
    conn.rollback()

    if findings:
        return CheckRun(
            check=Check.PERMISSION_CANARY,
            passed=False,
            detail="; ".join(findings),
        )
    return CheckRun(
        check=Check.PERMISSION_CANARY,
        passed=True,
        detail=(
            "in the scratch copy the application's role cannot bypass row-level security, every "
            "table has it switched on, the fast lane cannot write, and a made-up stranger was "
            "shown none of a made-up owner's row while the owner was shown it"
        ),
    )


def _shown(cur: Any, row_id: object, *, as_principal: str) -> int:
    """How many of the canary's rows the application's role is shown as this principal."""
    cur.execute("SELECT set_config(%s, %s, true)", (PRINCIPAL_SETTING, as_principal))
    cur.execute("SELECT count(*) FROM chat.conversation WHERE id = %s", (row_id,))
    return int(cur.fetchone()[0])


def _owner_and_stranger(conn: Any) -> list[str]:
    """Write an owned row, then ask as a stranger and as the owner. Always rolled back."""
    owner = f"{_OWNER_PREFIX}{uuid.uuid4().hex[:12]}"
    stranger = f"{_STRANGER_PREFIX}{uuid.uuid4().hex[:12]}"
    findings: list[str] = []
    try:
        with conn.cursor() as cur:
            # Literal statements: the table and the role are this module's own constants, and a
            # statement built from a name is a statement a reviewer has to resolve to read.
            cur.execute(
                "INSERT INTO chat.conversation (principal_id) VALUES (%s) RETURNING id", (owner,)
            )
            row_id = cur.fetchone()[0]
            cur.execute("SET LOCAL ROLE brain_app")
            shown_to_stranger = _shown(cur, row_id, as_principal=stranger)
            shown_to_nobody = _shown(cur, row_id, as_principal="")
            shown_to_owner = _shown(cur, row_id, as_principal=owner)
    except psycopg.Error as error:
        conn.rollback()
        return [
            "the application's role could not be asked the canary question in the scratch copy "
            f"({type(error).__name__}), so its grants or its policies did not come back"
        ]
    if shown_to_stranger or shown_to_nobody:
        findings.append(
            "a made-up stranger, or nobody at all, was shown a made-up owner's row in the "
            "scratch copy, so its policy did not come back"
        )
    if not shown_to_owner:
        findings.append(
            "the made-up owner was not shown their own row in the scratch copy. "
            f"{A_CANARY_THAT_ONLY_REFUSES_IS_SATISFIED_BY_A_COPY_THAT_REFUSES_EVERYONE}"
        )
    return findings


def run_checks(url: str) -> tuple[CheckRun, ...]:
    """Both questions asked of the copy at `url`, or both reported as not asked.

    An unreachable copy returns a failed check for each rather than raising, because the caller is
    a script assembling a record and a record saying the copy could not be reached is the honest
    outcome of a drill, where an exception would leave no record at all.
    """
    try:
        with psycopg.connect(libpq_conninfo(url), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)", (sorted(SCHEMAS),)
                )
                present = {row[0] for row in cur.fetchall()}
            schema = schema_complete(present)
            canary = permission_canary(conn)
    except psycopg.Error:
        return tuple(
            CheckRun(check=one, passed=False, detail=THE_COPY_WAS_NOT_REACHABLE)
            for one in (Check.SCHEMA_COMPLETE, Check.PERMISSION_CANARY)
        )
    return (schema, canary)


def as_entries(runs: Sequence[CheckRun]) -> list[dict[str, object]]:
    """The checks in the layout a drill record carries, with `passed` as a bare boolean."""
    return [{"check": one.check.value, "passed": one.passed, "detail": one.detail} for one in runs]


def main(argv: Sequence[str] | None = None) -> int:
    """Print the checks as a JSON list. Exits 0 whatever they found; the record carries it."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m brain.ops.drill_checks <scratch database url>", file=sys.stderr)
        return 2
    print(json.dumps(as_entries(run_checks(args[0]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
