"""Each department head's audit reach, rewritten from the staff list on every scheduled read.

Without a server: the statements a head's reach becomes, over reaches `audit_reach_for_head`
computes from real rosters, and the whole rewrite over a session that answers the three reads the
way the database would. Then the scheduled run, which rewrites the heads after the roster and never
lets a failure there undo it. The statements run against PostgreSQL only in CI's unit shards,
through the staff sync's own database tests; nothing here needs one.

Task ids: M1.8.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.dml import Insert, Update

from brain.core.entitlement import Capability
from brain.core.scope import Clause, Op, Scope
from brain.identity.packs import SubjectGrant
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import DEFAULT_TRUST, Roster
from brain.identity.staff_sync import (
    GRANT_LIFETIME,
    ROSTER_PREFIX,
    audit_reach_for_head,
)
from brain.identity.teams import PrincipalSubject
from brain.ops import head_audit_store
from brain.ops.head_audit_store import rewrite_head_audit_reach, writes_for
from tests.unit.test_staff_sync import person

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
READ_AT = datetime(2999, 1, 1, 3, 0, tzinfo=UTC)
SOURCE = "google_workspace"
BOUND = {"priya@example.com": "u_priya", "wei@example.com": "u_wei", "sam@example.com": "u_sam"}


def roster(*people: Any) -> Roster:
    return Roster(source=SOURCE, people=people, complete=True, asserts=DEFAULT_TRUST[SOURCE])


MAINTENANCE = roster(
    person("priya@example.com", department="Maintenance"),
    person("wei@example.com", department="Maintenance"),
    person("sam@example.com", department="Web"),
)


def sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


def grant(
    capability: str, members: tuple[str, ...], *, by: str = f"{ROSTER_PREFIX}{SOURCE}"
) -> SubjectGrant:
    return SubjectGrant(
        subject=PrincipalSubject(principal_id="u_head"),
        capability=Capability(value=capability),
        scope=Scope(clauses=(Clause(field="actor_id", op=Op.IN, value=members),)),
        granted_by=by,
        reason="heads maintenance, whose people this roster names",
        granted_at=READ_AT - timedelta(days=1),
        not_after=READ_AT + timedelta(hours=1),
    )


def reach_for(source: Roster, held: Sequence[SubjectGrant] = ()) -> Any:
    return audit_reach_for_head(
        source, department="maintenance", head_id="u_head", known=BOUND, read_at=READ_AT, held=held
    )


# ------------------------------------------------------------------------ the statements


def test_a_head_with_people_and_nothing_held_is_granted_the_four_audit_reads_over_them() -> None:
    """**Option A applied.** The page read and the three governance kinds, each scoped to the
    people the roster places in the department, and no department anywhere in the statement.
    Delete this and the reach `audit_reach_for_head` computes can go on being computed and never
    written, which is where it stood from item 48's decision until this module."""
    statements = writes_for(reach_for(MAINTENANCE), [], read_at=READ_AT)
    assert all(isinstance(one, Insert) for one in statements)
    written = [one.compile(dialect=DIALECT).params for one in statements]
    assert sorted(one["capability"] for one in written) == [
        "read:audit",
        "read:audit.agent",
        "read:audit.leash",
        "read:audit.principal",
    ]
    for one in written:
        assert one["principal_id"] == "u_head"
        assert one["granted_by"] == f"{ROSTER_PREFIX}{SOURCE}"
        assert one["scope"]["clauses"] == [
            {"field": "actor_id", "op": "in", "value": ["u_priya", "u_wei"]}
        ]
        assert "department" not in str(one["scope"])
        assert one["not_after"] == READ_AT + GRANT_LIFETIME


def test_a_capability_somebody_else_granted_the_head_is_not_written_again() -> None:
    """The table holds one live grant per person and capability, and an administrator's is not
    the sync's to replace. Delete this and a head who already reads principal entries company-wide
    makes every nightly run fail on the unique index."""
    theirs = grant("read:audit.principal", ("u_anyone",), by="u_admin")
    statements = writes_for(reach_for(MAINTENANCE, [theirs]), [theirs], read_at=READ_AT)
    written = [one.compile(dialect=DIALECT).params["capability"] for one in statements]
    assert "read:audit.principal" not in written
    assert len(written) == 3


def test_a_transfer_retires_the_roster_grants_and_writes_them_again_over_who_is_left() -> None:
    """Wei moves to Web: each roster grant naming both is retired and one naming Priya alone is
    written, retirements first so the unique index never sees two live rows. Delete this and a
    head goes on reading somebody who left their department."""
    held = [
        grant(one, ("u_priya", "u_wei"))
        for one in ("read:audit", "read:audit.agent", "read:audit.leash", "read:audit.principal")
    ]
    moved = roster(
        person("priya@example.com", department="Maintenance"),
        person("wei@example.com", department="Web"),
    )
    statements = writes_for(reach_for(moved, held), held, read_at=READ_AT)
    kinds = [type(one).__name__ for one in statements]
    assert kinds == ["Update"] * 4 + ["Insert"] * 4
    assert all("deleted_at" in sql(one) and "LIKE" in sql(one) for one in statements[:4])
    assert {
        tuple(one.compile(dialect=DIALECT).params["scope"]["clauses"][0]["value"])
        for one in statements[4:]
    } == {("u_priya",)}


def test_a_head_whose_people_did_not_change_has_the_lapse_moved_on_and_nothing_else() -> None:
    """A roster grant lapses two sync intervals after its reading. Delete this and a head whose
    department is unchanged loses every audit read the night after the lifetime runs out, because
    the reach reads as unchanged and nothing renews it."""
    held = [
        grant(one, ("u_priya", "u_wei"))
        for one in ("read:audit", "read:audit.agent", "read:audit.leash", "read:audit.principal")
    ]
    statements = writes_for(reach_for(MAINTENANCE, held), held, read_at=READ_AT)
    assert all(isinstance(one, Update) for one in statements)
    assert len(statements) == 4
    assert {one.compile(dialect=DIALECT).params["not_after"] for one in statements} == {
        READ_AT + GRANT_LIFETIME
    }
    assert all(
        "deleted_at" not in sql(one).split(" SET ")[1].split(" WHERE ")[0] for one in statements
    )


def test_a_source_not_trusted_with_departments_writes_nothing() -> None:
    """Delete this and a spreadsheet that cannot say who is in which department rewrites who a
    head may audit."""
    untrusted = Roster(source="google_sheet", people=MAINTENANCE.people, complete=True)
    assert reach_for(untrusted).refusals
    assert writes_for(reach_for(untrusted), [], read_at=READ_AT) == []


# ------------------------------------------------------------------------ the rewrite


@dataclass
class Answer:
    rows: list[Any]

    def all(self) -> list[Any]:
        return self.rows

    def scalars(self) -> Answer:
        return self


@dataclass
class HeadsSession:
    """Answers the lead, binding and grant reads as the database would, and keeps every write."""

    held: list[Any] = field(default_factory=list)
    written: list[Any] = field(default_factory=list)

    async def execute(self, statement: Any) -> Answer:
        text = sql(statement)
        if isinstance(statement, Insert | Update):
            self.written.append(statement)
            return Answer([])
        if "department_lead" in text:
            return Answer([("u_head", "maintenance")])
        if "principal_identity" in text:
            return Answer([(digest_of(address), pid) for address, pid in BOUND.items()])
        if "capability_grant" in text:
            return Answer(self.held)
        raise AssertionError(text)


def test_the_rewrite_reads_leads_bindings_and_grants_and_writes_each_heads_reach() -> None:
    """End to end over the three reads: the lead table names the head, the email bindings name
    the people, and the head's four grants are written. Delete this and the pieces above can each
    be right while the rewrite asks the wrong table who leads."""
    session = HeadsSession()
    applied = asyncio.run(rewrite_head_audit_reach(session, MAINTENANCE, read_at=READ_AT))  # type: ignore[arg-type]
    assert [(one.head_id, one.members) for one in applied] == [("u_head", ("u_priya", "u_wei"))]
    assert len(session.written) == 4


def test_a_person_nobody_has_bound_contributes_nothing() -> None:
    """Delete this and the rewrite can put somebody into a head's reach by address alone."""
    known = head_audit_store.known_from(MAINTENANCE, {digest_of("priya@example.com"): "u_priya"})
    assert known == {"priya@example.com": "u_priya"}


# ------------------------------------------------------------------------ the scheduled run


def test_the_scheduled_run_rewrites_the_heads_after_the_roster_and_survives_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run applies the roster, then the heads, each in its own transaction; a failure in the
    second is logged and the run still reports the roster applied. Delete this and the heads'
    reach can stop being called, or its failure can roll back every joiner and leaver."""
    from brain.ops import staff_sync_run
    from tests.unit.test_staff_sync_run import APP_ID, APP_SECRET, LARK_ENV, Keys, Lease, run

    order: list[str] = []

    async def read_members(session: object, source: str) -> tuple[()]:
        return ()

    async def read_last_applied(session: object, source: str) -> None:
        return None

    async def write_application(session: object, app: object, record: object) -> None:
        order.append("roster")

    async def failing(session: object, roster: Roster, *, read_at: datetime) -> tuple[()]:
        order.append("heads")
        raise RuntimeError("a unique index said no")

    monkeypatch.setattr(staff_sync_run, "read_members", read_members)
    monkeypatch.setattr(staff_sync_run, "read_last_applied", read_last_applied)
    monkeypatch.setattr(staff_sync_run, "write_application", write_application)
    monkeypatch.setattr(staff_sync_run, "run_row", lambda record: ("run", record))
    monkeypatch.setattr(staff_sync_run, "rewrite_head_audit_reach", failing)

    ran, _ = run(env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")))
    assert order == ["roster", "heads"]
    assert ran.outcome is not None
    assert ran.outcome.value in {"applied", "unchanged"}
