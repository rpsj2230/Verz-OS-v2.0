"""A person's own skills in the database: who sees a skill nobody offered, and who never does.

The first half needs no database: the statements the library and a person's list are read with are
compiled and held to each other, so they are each other's complement by construction. The second
half runs `ops.personal_skill_store` and `ops.skill_store` as the application role on a scratch
PostgreSQL at head, and **skips without a server**.

Task ids: M40.3.2.1, M40.3.2.2, M40.3.2.3, M40.3.2.4
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from brain.audit.ledger import AuditAction, AuditChain
from brain.console.skill_library import LibrarySkill, added, read_package
from brain.ops import personal_skill_store
from brain.ops.personal_skill_store import (
    MOST_UNOFFERED,
    Claim,
    StoredPersonalSkills,
    mine_of,
)
from brain.ops.skill_store import (
    A_SKILL_NOBODY_OFFERED_IS_NOT_THE_LIBRARY,
    StoredSkills,
    library_of,
    one_skill,
)
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine, as_app
from tests.unit.test_skill_library import SKILL_MD, text_with
from tests.unit.test_skill_store import NOW, entries

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

ME = "u_member"
COLLEAGUE = "u_colleague"
ADMIN = "u_admin"


def compiled(statement: object) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())  # type: ignore[attr-defined]


def a_skill(text: str = SKILL_MD, by: str = ME) -> LibrarySkill:
    return added(read_package("SKILL.md", text.encode("utf-8")), by=by, at=NOW)


# -------------------------------------------------------------------- the statements, offline
#: The clause every reading of the library carries, written out as the database will be asked it.
THE_CLAUSE = (
    "NOT (EXISTS (SELECT * FROM agent.skill_personal WHERE agent.skill_personal.digest = "
    "agent.skill.digest AND agent.skill_personal.submitted_at IS NULL))"
)


def test_both_readings_of_the_library_carry_the_one_clause_that_leaves_out_an_unoffered_skill() -> (
    None
):
    """`library_of` and `one_skill` are the two statements every library read goes through, and
    each must ask whether the skill is somebody's unfinished one. Delete this and a new statement
    that read `agent.skill` without the clause would be the leak, with every other test green. The
    clause is compared whole, as the database is asked it, and not as a word that also appears in
    a docstring."""
    assert THE_CLAUSE in compiled(library_of(10))
    assert THE_CLAUSE in compiled(one_skill("a" * 64))
    assert A_SKILL_NOBODY_OFFERED_IS_NOT_THE_LIBRARY.startswith("a skill a person added")


def test_a_persons_own_list_is_the_complement_of_the_librarys_and_is_held_to_one_owner() -> None:
    """`mine_of` joins the personal row and names its owner, and carries no clause that would hide
    an unoffered skill from its owner. Delete this and a person's list could be built from the
    library's statement, which would be empty for exactly the skills it exists to show."""
    one = compiled(mine_of(ME, 5))
    assert "agent.skill_personal.owner_id = " in one
    assert THE_CLAUSE not in one
    assert "JOIN agent.skill_personal ON agent.skill_personal.digest = agent.skill.digest" in one
    assert "agent.skill.digest = " in compiled(mine_of(ME, 5, "a" * 64))


# ------------------------------------------------------------------------------ the database
def with_stores(
    url: str, work: Callable[[StoredPersonalSkills, StoredSkills], Awaitable[Any]]
) -> Any:
    async def go() -> Any:
        engine = app_engine(url)
        try:
            factory = make_session_factory(engine)
            return await work(StoredPersonalSkills(factory), StoredSkills(factory))
        finally:
            await engine.dispose()

    return run(go)


def test_a_skill_nobody_offered_is_the_owners_alone_and_offering_puts_it_in_the_library() -> None:
    """**M40.3.2.1 to M40.3.2.4 against the tables, as the application role.** Added, the skill is
    on its owner's list and absent from the library's list, from a read of it by key and from a
    colleague's list; a colleague cannot offer it; offered, it is in the library and still on the
    owner's list with its offer. Delete this and the leak the clause closes is a claim about a
    statement nobody ran. **Skips without a server.**"""
    from tests.unit.test_acceptance import at_head

    one = a_skill()
    with at_head("brain_personal_skills") as url:

        async def work(personal: StoredPersonalSkills, library: StoredSkills) -> dict[str, object]:
            claim = await personal.add(one, ent_hash="a" * 32, trace_id="trace-add")
            before = {
                "claim": claim,
                "mine": [e.skill.digest for e in await personal.mine(ME)],
                "theirs": await personal.mine(COLLEAGUE),
                "library": await library.library(),
                "by_key": await library.skill(one.digest),
                "colleague_offer": await personal.offer(COLLEAGUE, one.digest, NOW),
                "colleague_read": await personal.one_of_mine(COLLEAGUE, one.digest),
            }
            offered = await personal.offer(ME, one.digest, NOW)
            again = await personal.offer(ME, one.digest, NOW)
            after = {
                "offered": offered,
                "again": again,
                "library": [s.digest for s in await library.library()],
                "by_key": (await library.skill(one.digest)) is not None,
                "mine": [(e.skill.digest, e.offered) for e in await personal.mine(ME)],
            }
            return {"before": before, "after": after}

        found = with_stores(url, work)
        chain = entries(url)

    before, after = found["before"], found["after"]
    assert before["claim"] is Claim.ADDED
    assert before["mine"] == [one.digest]
    assert before["theirs"] == ()
    assert before["library"] == ()
    assert before["by_key"] is None
    assert before["colleague_offer"] is False
    assert before["colleague_read"] is None
    assert after["offered"] is True
    assert after["again"] is False
    assert after["library"] == [one.digest]
    assert after["by_key"] is True
    assert after["mine"] == [(one.digest, True)]
    imported = [e for e in chain if e.action is AuditAction.SKILL]
    assert [(e.actor_id, e.subject) for e in imported] == [(ME, "skill:hosting-expiry")]
    assert AuditChain(chain).verify() is None


def test_adding_bytes_that_are_held_is_told_apart_only_as_yours_or_held() -> None:
    """The same bytes added again by their owner are theirs already; added by anybody else, or when
    the library holds them, they are held, and the answer is one value for every case. Delete this
    and the claim could say whose they are. **Skips without a server.**"""
    from tests.unit.test_acceptance import at_head

    mine, library_only = a_skill(), a_skill(text_with(name="in-the-library"), by=ADMIN)
    with at_head("brain_personal_skills_held") as url:

        async def work(personal: StoredPersonalSkills, library: StoredSkills) -> list[Claim]:
            await library.add(library_only, ent_hash="a" * 32, trace_id="t1")
            return [
                await personal.add(mine, ent_hash="a" * 32, trace_id="t2"),
                await personal.add(mine, ent_hash="a" * 32, trace_id="t3"),
                await personal.add(a_skill(by=COLLEAGUE), ent_hash="a" * 32, trace_id="t4"),
                await personal.add(
                    a_skill(text_with(name="in-the-library")), ent_hash="a" * 32, trace_id="t5"
                ),
            ]

        claims = with_stores(url, work)

    assert claims == [
        Claim.ADDED,
        Claim.YOURS_ALREADY,
        Claim.HELD_ALREADY,
        Claim.HELD_ALREADY,
    ]


def test_a_person_cannot_hold_more_unoffered_skills_than_the_bound_and_offering_makes_room(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bound stands in for deletion, which `0232` does not grant. Delete this and a person's
    skills accumulate for ever. The sibling: one under the bound is stored, and offering one makes
    room for another. **Skips without a server.**"""
    from tests.unit.test_acceptance import at_head

    monkeypatch.setattr(personal_skill_store, "MOST_UNOFFERED", 2)
    skills = [a_skill(text_with(name=f"skill-{n}")) for n in range(4)]
    with at_head("brain_personal_skills_bound") as url:

        async def work(personal: StoredPersonalSkills, library: StoredSkills) -> list[object]:
            claims = [
                await personal.add(skills[0], ent_hash="a" * 32, trace_id="t"),
                await personal.add(skills[1], ent_hash="a" * 32, trace_id="t"),
                await personal.add(skills[2], ent_hash="a" * 32, trace_id="t"),
            ]
            await personal.offer(ME, skills[0].digest, NOW)
            claims.append(await personal.add(skills[3], ent_hash="a" * 32, trace_id="t"))
            return list(claims)

        claims = with_stores(url, work)

    assert claims == [Claim.ADDED, Claim.ADDED, Claim.TOO_MANY, Claim.ADDED]
    assert MOST_UNOFFERED > 2


def test_a_skill_with_a_script_is_stored_with_its_script_and_still_hidden_until_offered() -> None:
    """The script's row is written in the personal skill's own transaction, and the skill reads back
    with the hash its digest covers. Delete this and a personal skill's script could be lost between
    the add and the review. **Skips without a server.**"""
    from tests.unit.test_acceptance import at_head
    from tests.unit.test_skill_library import a_zip

    package = read_package(
        "skill.zip",
        a_zip(
            {
                "SKILL.md": text_with(scripts="[scripts/check.py]").encode("utf-8"),
                "scripts/check.py": b"print('renewal due')\n",
            }
        ),
    )
    one = added(package, by=ME, at=NOW)
    with at_head("brain_personal_skills_script") as url:

        async def work(personal: StoredPersonalSkills, library: StoredSkills) -> tuple[object, ...]:
            await personal.add(one, ent_hash="a" * 32, trace_id="t")
            (entry,) = await personal.mine(ME)
            return (
                entry.skill.imported.skill.script_sha256,
                entry.skill.moved,
                await library.library(),
            )

        hashes, moved, library = with_stores(url, work)
        held = sql(url, "SELECT path FROM agent.skill_script")

    assert hashes == one.imported.skill.script_sha256
    assert moved is False
    assert library == ()
    assert held == [("scripts/check.py",)]


def test_the_database_holds_a_personal_row_to_the_person_the_session_names() -> None:
    """Measured as the application role: a personal row in another person's name is refused, one in
    the session's own is admitted, and a person cannot offer a skill that is not theirs. Delete this
    and the ownership the routes rely on is a claim about a policy nobody ran. **Skips without a
    server.**"""
    from tests.unit.test_acceptance import at_head

    one = a_skill()
    with at_head("brain_personal_skills_policy") as url:

        async def stored(personal: StoredPersonalSkills, library: StoredSkills) -> bool:
            return await library.add(one, ent_hash="a" * 32, trace_id="t")

        assert with_stores(url, stored) is True
        with as_app(url, ("app.principal_id", ME)) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    "INSERT INTO agent.skill_personal (digest, owner_id) VALUES (%s, %s)",
                    (one.digest, COLLEAGUE),
                )
            conn.execute(
                "INSERT INTO agent.skill_personal (digest, owner_id) VALUES (%s, %s)",
                (one.digest, ME),
            )
        with as_app(url, ("app.principal_id", COLLEAGUE)) as conn:
            moved = conn.execute(
                "UPDATE agent.skill_personal SET submitted_at = now() WHERE digest = %s",
                (one.digest,),
            )
            assert moved.rowcount == 0
        offered = sql(url, "SELECT submitted_at FROM agent.skill_personal")

    assert offered == [(None,)]
