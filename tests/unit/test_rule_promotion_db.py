"""`0206` on PostgreSQL: the walls the database keeps around a learned rule's promotion
(M39.4.2.3), each asked directly as the application role so no Python stands in front of it.

The install check (`brain.ops.acceptance_checks_promotion`) proves the product end to end; these
prove that a statement written anywhere else meets the same refusals.

Task ids: M39.4.2.3
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

pytestmark = pytest.mark.needs_db


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_rule_promotion") as url:
        yield url


def as_app(
    url: str, *statements: tuple[str, tuple[Any, ...]], actor: str | None, principal: str = ""
) -> list[Any]:
    """Statements in one transaction as `brain_app`, with the actor and principal set, committed."""
    import psycopg

    out: list[Any] = []
    with psycopg.connect(url, options="-c role=brain_app") as conn:
        if actor is not None:
            conn.execute("SELECT set_config('brain.actor_id', %s, true)", (actor,))
        if principal:
            conn.execute("SELECT set_config('app.principal_id', %s, true)", (principal,))
        for statement, values in statements:
            cursor = conn.execute(statement, values)
            out.append(cursor.fetchall() if cursor.description else cursor.rowcount)
    return out


def held(url: str, memory_id: str, *, proposed_by: str | None = "u_proposer") -> None:
    """A tier-two learning and the rule it proposes, written by the table's owner."""
    import psycopg

    with psycopg.connect(url) as owner:
        owner.execute(
            "INSERT INTO mem.learning (memory_id, change, tier, subject)"
            " VALUES (%s, 'fast_path_rule', 2, %s)",
            (memory_id, memory_id),
        )
        owner.execute(
            "INSERT INTO mem.learned_rule (memory_id, rule_id, template, slot, source, entity,"
            " match_field, answer_field, department, proposed_by, state)"
            " VALUES (%s, %s, 'what is the rate for {name}', 'name', 'tables', 'price_list',"
            " 'name', 'sell_price', 'sales', %s, 'held')",
            (memory_id, f"sales__{memory_id}", proposed_by),
        )


PROMOTE = (
    "UPDATE mem.learned_rule SET state = 'promoted', needs_two = %s, first_by = %s,"
    " first_at = now(), promoted_by = %s, promoted_at = now() WHERE memory_id = %s"
)
FIRST = (
    "UPDATE mem.learned_rule SET state = 'awaiting_second', needs_two = true, first_by = %s,"
    " first_at = now() WHERE memory_id = %s"
)


def test_a_press_in_somebody_elses_name_is_refused_and_ones_own_is_written(database: str) -> None:
    """The update policy binds the presser to the transaction's actor. Delete this and a session
    can promote a rule naming somebody else as its promoter."""
    import psycopg

    held(database, "lr_named")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        as_app(database, (PROMOTE, (False, "u_other", "u_other", "lr_named")), actor="u_admin")
    assert as_app(
        database, (PROMOTE, (False, "u_admin", "u_admin", "lr_named")), actor="u_admin"
    ) == [1]


def test_the_proposer_and_one_person_for_two_are_refused_by_the_tables_checks(
    database: str,
) -> None:
    """**`NOBODY_PROMOTES_WHAT_THEY_PROPOSED` and two people being two.** The proposer's promotion,
    and a two-person promotion whose second presser is its first, are each refused by a check;
    a different second presser is written.

    Delete this and the database's half of both rules can go with every Python test green."""
    import psycopg

    held(database, "lr_proposer")
    with pytest.raises(psycopg.errors.CheckViolation):
        as_app(
            database,
            (PROMOTE, (False, "u_proposer", "u_proposer", "lr_proposer")),
            actor="u_proposer",
        )
    held(database, "lr_two")
    as_app(database, (FIRST, ("u_first", "lr_two")), actor="u_first")
    once = "UPDATE mem.learned_rule SET state = 'promoted', promoted_by = %s, promoted_at = now()"
    with pytest.raises(psycopg.errors.CheckViolation):
        as_app(database, (once + " WHERE memory_id = %s", ("u_first", "lr_two")), actor="u_first")
    assert as_app(
        database, (once + " WHERE memory_id = %s", ("u_second", "lr_two")), actor="u_second"
    ) == [1]


def test_a_press_is_on_the_ledger_under_its_presser_and_one_with_nobody_named_is_refused(
    database: str,
) -> None:
    """Each press is a ledger entry under the actor, and a press with no actor set is refused.
    Delete this and a promotion can record nobody."""
    import psycopg

    held(database, "lr_ledger")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        as_app(database, (FIRST, ("u_first", "lr_ledger")), actor=None)
    # And as the table's owner, whom no policy binds: the trigger alone refuses it.
    with psycopg.connect(database) as owner, pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner.execute(FIRST, ("u_first", "lr_ledger"))
    as_app(database, (FIRST, ("u_first", "lr_ledger")), actor="u_first")
    with psycopg.connect(database) as owner:
        rows = owner.execute(
            "SELECT actor_id, details FROM obs.audit_entry"
            " WHERE subject = 'setting:learned_rule.lr_ledger'"
        ).fetchall()
    assert [(actor, details["change"], details["needs_two"]) for actor, details in rows] == [
        ("u_first", "first", "yes")
    ]


def test_an_occurrence_is_counted_only_from_the_askers_own_conversation(database: str) -> None:
    """The insert policy admits an occurrence only for a conversation of the principal the session
    names, so agreement cannot be manufactured from conversations a session does not hold. Delete
    this and the policy can be `WITH CHECK (true)`."""
    import psycopg

    held(database, "lr_count")
    with psycopg.connect(database) as owner:
        (theirs,) = owner.execute(
            "INSERT INTO chat.conversation (principal_id) VALUES ('u_asker') RETURNING id"
        ).fetchone() or (None,)
    count = (
        "INSERT INTO mem.rule_occurrence (memory_id, conversation_id, on_day)"
        " VALUES ('lr_count', %s, current_date)"
    )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        as_app(database, (count, (theirs,)), actor=None, principal="u_other")
    assert as_app(database, (count, (theirs,)), actor=None, principal="u_asker") == [1]


def test_only_held_rules_are_counted_and_only_the_one_a_question_matches(database: str) -> None:
    """The shadow match reads the rules still held, never a promoted one, and a question counts
    the one rule whose words it is, once for its conversation and day.

    Delete this and a promoted rule keeps collecting occurrences, or one question counts as
    agreement for every rule held in its department."""
    import asyncio
    import uuid
    from datetime import UTC, datetime

    import psycopg
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from brain.db import normalise_database_url
    from brain.memory.promotion_store import StoredLearnedRules

    held(database, "lr_rate")
    held(database, "lr_cost")
    held(database, "lr_done")
    with psycopg.connect(database) as owner:
        owner.execute(
            "UPDATE mem.learned_rule SET template = 'what is the cost for {name}',"
            " rule_id = 'sales__lr_cost' WHERE memory_id = 'lr_cost'"
        )
        owner.execute("SELECT set_config('brain.actor_id', 'u_admin', false)")
        owner.execute(
            "UPDATE mem.learned_rule SET state = 'promoted', needs_two = false,"
            " first_by = 'u_admin', first_at = now(), promoted_by = 'u_admin',"
            " promoted_at = now(), template = 'what is the margin for {name}',"
            " rule_id = 'sales__lr_done' WHERE memory_id = 'lr_done'"
        )
        (conversation,) = owner.execute(
            "INSERT INTO chat.conversation (principal_id) VALUES ('u_counted') RETURNING id"
        ).fetchone() or (None,)

    async def run() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        engine = create_async_engine(
            normalise_database_url(database),
            poolclass=NullPool,
            connect_args={"options": "-c role=brain_app"},
        )
        store = StoredLearnedRules(async_sessionmaker(engine, expire_on_commit=False))
        try:
            held_now = tuple(one.memory_id for one in await store.held_for("sales"))
            at = datetime(2999, 6, 1, 9, tzinfo=UTC)
            counted = await store.count_occurrence(
                "what is the cost for acme",
                principal_id="u_counted",
                department="sales",
                thread_id=str(conversation),
                now=at,
            )
            margin = await store.count_occurrence(
                "what is the margin for acme",
                principal_id="u_counted",
                department="sales",
                thread_id=str(uuid.UUID(str(conversation))),
                now=at,
            )
            return held_now, counted, margin
        finally:
            await engine.dispose()

    held_now, counted, margin = asyncio.run(run())
    assert set(held_now) >= {"lr_rate", "lr_cost"}
    assert "lr_done" not in held_now
    assert counted == ("lr_cost",)
    assert margin == ()
