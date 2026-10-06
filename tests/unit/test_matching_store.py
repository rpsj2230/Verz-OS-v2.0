"""The online cascade over a real schema: each pair merged, held for a person, queued, or left.

Records are written into `proj.record` as the superuser and registered as the application role,
then matched with the real merge store, whose unattended switch is off unless a test turns it on.
A source that keeps a registration number is declared here for the paths only a hard identifier
reaches (an automatic merge, a cap, a collision), because no shipped connector keeps one.

Task ids: M14.2.5, M14.3.2, M14.3.3, M14.3.4, M14.3.6, M14.3.7, M14.3.8, M14.5.6, M14.6.2
Task ids: M14.6.3
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

import pytest

from brain.connectors.resolves import ResolvesAs
from brain.resolution.canonical import EntityType, SourceRef
from brain.resolution.matching_store import (
    HELD_AT_A_CAP,
    HELD_BY_A_COLLISION,
    HELD_FOR_MONEY,
    HELD_ON_A_NAME,
    HELD_UNATTENDED,
    Matched,
    StoredMatching,
    money_of,
)
from brain.resolution.merge import MoneyBearing
from brain.resolution.registry_store import StoredRegistry
from brain.resolution.sources import resolved_entities

AT = datetime(2019, 3, 4, 12, tzinfo=UTC)
PEPPER = "cd" * 32
COMPANY = "hubspot_company"
#: Shipped declarations, plus a company source that keeps a registration number.
REGISTERED = ("hubspot", "registered_company")
DECLARED: Mapping[tuple[str, str], ResolvesAs] = MappingProxyType(
    {
        **resolved_entities(),
        REGISTERED: ResolvesAs(
            entity=REGISTERED[1],
            entity_type=EntityType.COMPANY,
            fields={"name": "name", "uen": "uen"},
        ),
    }
)


@pytest.fixture
def schema() -> Iterator[tuple[str, Callable[..., Any]]]:
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_acceptance import at_head

    with at_head("brain_matching_store") as url:
        yield url, sql


def write(url: str, sql: Callable[..., Any], ref: SourceRef, **fields: str) -> SourceRef:
    sql(
        url,
        "INSERT INTO proj.record (source, entity, source_id, fields, last_seen_at)"
        " VALUES (%s, %s, %s, %s::jsonb, %s)",
        ref.source,
        ref.entity,
        ref.source_id,
        json.dumps(fields),
        AT,
    )
    return ref


def company(n: int) -> SourceRef:
    return SourceRef(source="hubspot", entity=COMPANY, source_id=f"c{n}")


def registered(n: int) -> SourceRef:
    return SourceRef(source=REGISTERED[0], entity=REGISTERED[1], source_id=f"r{n}")


def run(url: str, *refs: SourceRef, unattended: bool = False) -> Matched:
    """Register these records and match them, as the worker's run does, in one process."""
    from brain.db import normalise_database_url
    from brain.ops.features import UNATTENDED_ENTITY_MERGE, switch
    from brain.session import make_app_engine, make_session_factory

    async def go() -> Matched:
        engine = make_app_engine(normalise_database_url(url))
        try:
            sessions = make_session_factory(engine)
            if unattended:
                async with sessions() as session, session.begin():
                    await switch(session, UNATTENDED_ENTITY_MERGE, on=True, by="u_owner")
            await StoredRegistry(sessions, declared=DECLARED).register(
                list(refs), pepper=PEPPER, now=AT
            )
            return await StoredMatching(sessions, declared=DECLARED).match(
                list(refs), pepper=PEPPER, now=AT
            )
        finally:
            await engine.dispose()

    return asyncio.run(go())


def items(url: str, sql: Callable[..., Any]) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in sql(
            url,
            "SELECT left_source_id, right_source_id, origin, stage, reason, state"
            " FROM er.review_item ORDER BY left_source_id, right_source_id",
        )
    ]


# ------------------------------------------------------------------------ pure half
def test_a_family_carries_money_when_any_record_is_of_a_money_entity_and_otherwise_none() -> None:
    """Read off the declarations: one money record makes the family money-bearing, none makes it
    money-free, and a record nothing declares makes it unchecked.

    Delete this and the money boundary reads the wrong answer for a family of mixed sources."""
    assert money_of([("xero", "xero_contact")], DECLARED) is MoneyBearing.CARRIES_FINANCIAL_RECORDS
    assert money_of([("hubspot", COMPANY)], DECLARED) is MoneyBearing.NO_FINANCIAL_RECORDS_FOUND
    mixed = [("hubspot", COMPANY), ("laravel", "laravel_client")]
    assert money_of(mixed, DECLARED) is MoneyBearing.CARRIES_FINANCIAL_RECORDS
    assert money_of([("nobody", "nothing")], DECLARED) is MoneyBearing.NOT_CHECKED
    assert money_of([], DECLARED) is MoneyBearing.NOT_CHECKED


# ------------------------------------------------------------------ on a real schema
@pytest.mark.needs_db
def test_a_corroborated_name_is_matched_and_held_because_it_is_not_a_hard_identifier(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """Two companies whose names agree once their legal forms are off and whose domain agrees
    are matched at stage two, and held for a person with that stage and the reason, even with
    unattended merging switched on.

    Delete this and a name match can be merged with nobody looking, or never reach anybody."""
    url, sql = schema
    one = write(url, sql, company(1), name="Northwind Trading Pte. Ltd.", domain="nw.example")
    two = write(url, sql, company(2), name="NORTHWIND TRADING", domain="nw.example")

    done = run(url, one, two, unattended=True)

    assert (done.compared, done.merged, done.queued) == (1, 0, 1)
    assert items(url, sql) == [("c1", "c2", "held", 2, HELD_ON_A_NAME, "open")]


@pytest.mark.needs_db
def test_close_names_are_matched_at_stage_three_and_names_alone_wait_for_a_person(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """Two names a letter apart are a stage-three match, held; two equal names with nothing to
    corroborate them are a question, raised from the cascade; two unrelated names are nothing.

    Delete this and the trigram stage or the band below stage two stops reaching a person."""
    url, sql = schema
    refs = (
        write(url, sql, company(1), name="Contoso Pharmaceuticals"),
        write(url, sql, company(2), name="Contosso Pharmaceuticals"),
        write(url, sql, company(3), name="Fabrikam Studio"),
        write(url, sql, SourceRef("xero", "xero_contact", "x1"), name="Fabrikam Studio"),
        write(url, sql, company(4), name="Unrelated Holdings"),
    )

    done = run(url, *refs)

    assert done.merged == 0
    found = items(url, sql)
    assert [row[:4] for row in found] == [("c1", "c2", "held", 3), ("c3", "x1", "cascade", 4)]
    assert found[0][4] == HELD_ON_A_NAME
    assert found[1][4] not in {HELD_ON_A_NAME, HELD_UNATTENDED}


@pytest.mark.needs_db
def test_a_name_too_short_to_measure_goes_to_a_person_when_something_else_agreed(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """Two three-letter names sharing a domain reach a person rather than a merge (M14.2.5).

    Delete this and an initialism could be matched on the strength of a similarity over
    fewer trigrams than a measurement needs."""
    url, sql = schema
    one = write(url, sql, company(1), name="IBX", domain="ibx.example")
    two = write(url, sql, company(2), name="IBX Pte Ltd", domain="ibx.example")

    run(url, one, two, unattended=True)

    assert [row[:3] for row in items(url, sql)] == [("c1", "c2", "cascade")]


@pytest.mark.needs_db
def test_a_free_mail_domain_joins_nothing(schema: tuple[str, Callable[..., Any]]) -> None:
    """Two companies at one mail provider's domain are not candidates on it (M14.3.7).

    Delete this and every customer of a mail provider becomes one company."""
    url, sql = schema
    one = write(url, sql, company(1), name="Alpha Design", domain="gmail.com")
    two = write(url, sql, company(2), name="Omega Freight", domain="gmail.com")

    done = run(url, one, two, unattended=True)

    assert done.compared == 0
    assert sql(url, "SELECT count(*) FROM er.identifier") == [(0,)]


@pytest.mark.needs_db
def test_a_match_across_the_money_boundary_waits_for_a_person(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """An accounting contact and a client view matched on a near name are held at the money
    boundary, whatever the switch says (M14.5.6).

    Delete this and a contract value could be joined to another department's client with nobody
    looking."""
    url, sql = schema
    one = write(
        url, sql, SourceRef("laravel", "laravel_client", "l1"), name="Acmee Holdings International"
    )
    two = write(
        url, sql, SourceRef("xero", "xero_contact", "x1"), name="Acme Holdings International"
    )

    run(url, one, two, unattended=True)

    assert [row[:3] + row[4:5] for row in items(url, sql)] == [
        ("l1", "x1", "money", HELD_FOR_MONEY)
    ]


@pytest.mark.needs_db
def test_a_hard_identifier_is_merged_when_unattended_merging_is_on_and_held_while_it_is_off(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """Two money-free companies sharing a registration number are merged at stage one with the
    switch on, and held with the switch's reason while it is off.

    Delete this and the switch either merges nothing or merges with nobody having turned it on."""
    url, sql = schema
    one = write(url, sql, registered(1), name="Orbit Labs", uen="201912345K")
    two = write(url, sql, registered(2), name="Orbit Laboratories", uen="201912345K")
    held = run(url, one, two)
    assert items(url, sql) == [("r1", "r2", "held", 1, HELD_UNATTENDED, "open")]
    assert held.merged == 0

    three = write(url, sql, registered(3), name="Vega Works", uen="201954321Z")
    four = write(url, sql, registered(4), name="Vega Workshop", uen="201954321Z")
    merged = run(url, three, four, unattended=True)

    assert merged.merged == 1
    assert sql(url, "SELECT count(*) FROM er.merge") == [(1,)]
    assert sql(
        url,
        "SELECT count(*) FROM er.canonical WHERE merged_into IS NOT NULL",
    ) == [(1,)]


@pytest.mark.needs_db
def test_a_merge_that_would_breach_a_cap_is_held(schema: tuple[str, Callable[..., Any]]) -> None:
    """A registration number shared by two entities that already hold one each of their own is
    held at the cap, because a company holds one registration number (M14.6.2).

    Delete this and a merge can leave one entity holding two registered companies' numbers."""
    url, sql = schema
    one = write(url, sql, registered(1), name="Orbit Labs", uen="201912345K")
    two = write(url, sql, registered(2), name="Orbit Labs", uen="201912345K")
    run(url, one, two)
    [(entity_id,)] = sql(url, "SELECT entity_id FROM er.link WHERE source_id = 'r1'")
    sql(
        url,
        "INSERT INTO er.identifier (source, entity, source_id, kind, key_hash, entity_id,"
        " first_seen_at) VALUES ('hubspot', 'registered_company', 'r1', 'uen', %s, %s, %s)",
        "e" * 64,
        entity_id,
        AT,
    )
    sql(url, "DELETE FROM er.review_item")

    done = run(url, one, two, unattended=True)

    assert done.merged == 0
    assert [row[2:5] for row in items(url, sql)] == [("held", 1, HELD_AT_A_CAP)]


@pytest.mark.needs_db
def test_a_record_matching_two_entities_on_one_identifier_is_held_for_a_person(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """Three records sharing one registration number: every match is a collision the priority
    order cannot settle at the top, so every pair is held (M14.6.3).

    Delete this and the first pair compared wins a tie nothing decided."""
    url, sql = schema
    refs = [
        write(url, sql, registered(n), name=name, uen="201912345K")
        for n, name in enumerate(("Orbit Labs", "Orbit Laboratories", "Orbit Lab Works"), 1)
    ]

    done = run(url, *refs, unattended=True)

    assert done.merged == 0
    assert {row[4] for row in items(url, sql)} == {HELD_BY_A_COLLISION}
    assert len(items(url, sql)) == 3


@pytest.mark.needs_db
def test_a_pair_is_raised_once_and_a_rejected_pair_is_never_raised_again(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """A second run over a pair already waiting adds nothing, and a pair a person rejected is not
    compared again.

    Delete this and the queue fills with the same question every ten minutes."""
    url, sql = schema
    one = write(url, sql, company(1), name="Fabrikam Studio")
    two = write(url, sql, SourceRef("xero", "xero_contact", "x1"), name="Fabrikam Studio")
    run(url, one, two)
    again = run(url, one, two)
    assert again.queued == 0 and again.compared == 0
    sql(
        url,
        "UPDATE er.review_item SET state = 'rejected', decided_by = 'u_r', decided_at = now()",
    )

    after = run(url, one, two)

    assert after.compared == 0
    assert len(items(url, sql)) == 1


@pytest.mark.needs_db
def test_the_entity_minted_first_survives_and_a_merged_pair_is_not_compared_again(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """A record registered a day before its match keeps its entity as the survivor, so the id
    issued first is the one others resolve to; and once the two are one entity, a later run
    compares nothing.

    Delete this and a merge can retire the id everybody already holds, or a merged pair is raised
    for review after it was merged."""
    from datetime import timedelta

    from brain.db import normalise_database_url
    from brain.ops.features import UNATTENDED_ENTITY_MERGE, switch
    from brain.session import make_app_engine, make_session_factory

    url, sql = schema
    older = write(url, sql, registered(1), name="Orbit Labs", uen="201912345K")
    newer = write(url, sql, registered(2), name="Orbit Laboratories", uen="201912345K")

    async def go() -> Matched:
        engine = make_app_engine(normalise_database_url(url))
        try:
            sessions = make_session_factory(engine)
            async with sessions() as session, session.begin():
                await switch(session, UNATTENDED_ENTITY_MERGE, on=True, by="u_owner")
            registry = StoredRegistry(sessions, declared=DECLARED)
            await registry.register([older], pepper=PEPPER, now=AT)
            later = AT + timedelta(days=1)
            await registry.register([newer], pepper=PEPPER, now=later)
            matching = StoredMatching(sessions, declared=DECLARED)
            await matching.match([newer], pepper=PEPPER, now=later)
            return await matching.match([older, newer], pepper=PEPPER, now=later)
        finally:
            await engine.dispose()

    again = asyncio.run(go())

    [(first,)] = sql(url, "SELECT entity_id FROM er.link WHERE source_id = 'r1'")
    assert sql(url, "SELECT survivor_id FROM er.merge") == [(first,)]
    assert again.compared == 0


def test_a_merge_refused_for_any_reason_but_the_switch_is_not_swallowed() -> None:
    """Only the switch's refusal becomes a held item; any other refusal stops the run.

    Delete this and a merge refused because the graph was wrong reads as a question for a person,
    and the fault behind it is never seen."""
    from brain.resolution.cascade import CascadeResult, Decision, Stage
    from brain.resolution.guardrails import Evidence
    from brain.resolution.matching_store import _Match
    from brain.resolution.merge_store import MergeRefusedError

    async def refuses(**arguments: Any) -> None:
        raise MergeRefusedError("the graph moved underneath")

    matching = StoredMatching(None, declared=DECLARED, merges=refuses)  # type: ignore[arg-type]
    one = _Match(
        result=CascadeResult(
            decision=Decision.MATCHED,
            stage=Stage.HARD_IDENTIFIER,
            left=registered(1),
            right=registered(2),
            evidence=(Evidence(field="uen", weight=10.0),),
            reason="r",
            confidence=1.0,
        ),
        entity_type=EntityType.COMPANY,
        left_current="ent_a",
        right_current="ent_b",
    )

    async def families(*args: Any) -> Any:
        return {"ent_a": {"x": REGISTERED}, "ent_b": {"y": REGISTERED}}

    async def survivor(*args: Any) -> Any:
        return ("ent_a", "ent_b")

    async def identifiers(*args: Any) -> Any:
        return []

    import brain.resolution.matching_store as store

    class Session:
        async def __aenter__(self) -> Session:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

    matching._sessions = lambda: Session()  # type: ignore[assignment]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(store, "families_of", families)
        patch.setattr(store, "survivor_first", survivor)
        patch.setattr(store, "_identifiers", identifiers)
        with pytest.raises(MergeRefusedError, match="moved underneath"):
            asyncio.run(matching._merge_or_hold(one, now=AT))
