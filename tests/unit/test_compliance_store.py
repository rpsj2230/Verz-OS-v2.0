"""The compliance stores on real rows, as the application role: referrals, named people, breaches.

What the routes' tests cannot see is here: the policies that decide who reads a referral, the
trigger that records each step of a breach case, and the attribution that makes each entry name
the person whose session moved the case. Each builds the database to head, which CI has and a
development machine without pgvector skips.

Task ids: M24.2.2, M24.2.4
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.audit.compliance import Awareness, AwarenessBasis, AwarenessSource, SensitiveTopic
from brain.audit.ledger import AuditChain, AuditEntry
from brain.audit.record import AuditRecorder, BreachChange
from brain.ops.breach_store import Actor, BreachRefusedError, StoredBreachCases
from brain.ops.sensitive_referral_store import NamingRefusedError, StoredSensitiveReferrals
from tests.unit.test_tables import VERSIONS, migration_module

MIGRATION = VERSIONS / "0104_compliance_record_and_decision_entries.py"


@contextmanager
def at_head(database: str) -> Iterator[str]:
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import admin_url

    admin_url()
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("the chain to 0104 needs pgvector, which CI has")
        yield url


def details_of(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else json.loads(value)


def with_sessions(url: str, work: Any) -> Any:
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run
    from tests.unit.test_automation_owner_store import app_engine

    async def go() -> Any:
        engine = app_engine(url)
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


def test_the_trigger_writes_the_changes_the_recorder_names() -> None:
    """Every `BreachChange` is a word the trigger writes, and the recorder's details are the
    trigger's. Delete this and the two can drift, and the audit view reads one shape from the
    database and another from a chain in memory."""
    body = migration_module(MIGRATION).BREACH_CASE_TRIGGER_FUNCTION
    recorder = AuditRecorder(
        AuditChain(),
        actor_id="u_dpo",
        ent_hash="0" * 32,
        trace_id="t",
        clock=lambda: datetime.now(UTC),
    )
    for change in BreachChange:
        assert f"'{change.value}'" in body
        entry = recorder.breach(case_id="3b1f7c2e-8d4a-4e6b-9f0c-1a2b3c4d5e6f", change=change)
        assert dict(entry.details) == {"change": change.value}


def test_naming_a_person_writes_one_route_row_and_a_setting_entry_without_the_value() -> None:
    """The named person for a topic is one `ops.setting` row, and `0059`'s trigger records the
    change under the key with the writer and never the value. Somebody who is not an active
    principal is refused and nothing is written. Delete this and a route can name nobody, or the
    ledger can carry who receives whistleblowing referrals."""
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_entitlement_store import a_principal

    with at_head("brain_ws9_naming") as url:
        a_principal(url, "u_ethics")

        async def work(sessions: Any) -> Any:
            store = StoredSensitiveReferrals(sessions)
            named = await store.name(
                SensitiveTopic.WHISTLEBLOWING,
                "u_ethics",
                by="u_dpo",
                ent_hash="ab" * 16,
                trace_id="trace-name",
            )
            with pytest.raises(NamingRefusedError):
                await store.name(
                    SensitiveTopic.LEGAL, "u_ghost", by="u_dpo", ent_hash="", trace_id="t2"
                )
            return named, await store.named()

        named, listed = with_sessions(url, work)
        rows = sql(
            url,
            "SELECT key, value #>> '{}', updated_by FROM ops.setting"
            " WHERE key LIKE 'sensitive_route.%' AND deleted_at IS NULL",
        )
        entries = sql(
            url,
            "SELECT actor_id, subject, details, trace_id FROM obs.audit_entry"
            " WHERE action = 'setting' AND subject LIKE 'setting:sensitive_route.%'",
        )

    assert named.principal_id == "u_ethics" and set(listed) == {SensitiveTopic.WHISTLEBLOWING}
    assert rows == [("sensitive_route.whistleblowing", "u_ethics", "u_dpo")]
    [(actor, subject, details, trace)] = entries
    assert (actor, subject, trace) == (
        "u_dpo",
        "setting:sensitive_route.whistleblowing",
        "trace-name",
    )
    assert details_of(details) == {"change": "set"}
    assert "u_ethics" not in json.dumps(details_of(details))


def test_a_referral_is_filed_without_content_and_read_only_by_its_person() -> None:
    """M24.2.2 on real rows. A legal question is routed to the person named for legal matters and
    only they read it; a medical one, arriving while nobody was named, is read by nobody until
    somebody is named, and then by them; the asker reads neither; a stranger cannot mark one
    handled; the tally counts both without a row. The table has no column a question could be in.
    Delete this and a referral can be read by anybody the application connects as, or lost."""
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_entitlement_store import a_principal

    with at_head("brain_ws9_referral") as url:
        for pid in ("u_asker", "u_counsel", "u_nurse"):
            a_principal(url, pid)

        async def work(sessions: Any) -> dict[str, Any]:
            store = StoredSensitiveReferrals(sessions)
            await store.name(
                SensitiveTopic.LEGAL, "u_counsel", by="u_dpo", ent_hash="", trace_id="t"
            )
            routed = await store.refer(
                asked_by="u_asker", topic=SensitiveTopic.LEGAL, ent_hash="", trace_id="t-legal"
            )
            unrouted = await store.refer(
                asked_by="u_asker", topic=SensitiveTopic.MEDICAL, ent_hash="", trace_id="t-med"
            )
            seen = {pid: await store.mine(pid) for pid in ("u_counsel", "u_nurse", "u_asker")}
            await store.name(
                SensitiveTopic.MEDICAL, "u_nurse", by="u_dpo", ent_hash="", trace_id="t"
            )
            nurse_now = await store.mine("u_nurse")
            legal_id = seen["u_counsel"][0].referral_id
            stranger = await store.handle(
                legal_id, by="u_nurse", ent_hash="", trace_id="t", at=datetime.now(UTC)
            )
            done = await store.handle(
                nurse_now[0].referral_id,
                by="u_nurse",
                ent_hash="",
                trace_id="t",
                at=datetime.now(UTC),
            )
            tally = await store.tally(datetime.now(UTC).strftime("%Y-%m"))
            return {
                "routed": routed,
                "unrouted": unrouted,
                "seen": seen,
                "nurse_now": nurse_now,
                "stranger": stranger,
                "done": done,
                "handled": await store.mine("u_nurse"),
                "tally": tally,
            }

        found = with_sessions(url, work)
        columns = sql(
            url,
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'ops' AND table_name = 'sensitive_referral'",
        )

    assert (found["routed"], found["unrouted"]) == ("u_counsel", None)
    assert [r.topic for r in found["seen"]["u_counsel"]] == [SensitiveTopic.LEGAL]
    assert found["seen"]["u_nurse"] == () and found["seen"]["u_asker"] == ()
    assert [r.topic for r in found["nurse_now"]] == [SensitiveTopic.MEDICAL]
    assert (found["stranger"], found["done"]) == (False, True)
    assert (
        found["handled"][0].handled_by == "u_nurse" and found["handled"][0].routed_to == "u_nurse"
    )
    assert found["tally"].counts == {SensitiveTopic.LEGAL: 1, SensitiveTopic.MEDICAL: 1}
    assert {c for (c,) in columns} == {
        "referral_id",
        "topic",
        "asked_by",
        "asked_at",
        "routed_to",
        "handled_at",
        "handled_by",
    }


def test_each_breach_step_writes_its_column_and_one_breach_entry_in_the_same_transaction() -> None:
    """M24.2.4 on real rows. A case opened, assessed, the Commission and the individuals told and
    closed leaves each column set and one `breach` entry per step, each naming the person whose
    session moved it and that request's trace, and the chain verifies. A step written inside a
    transaction that is rolled back leaves neither its column nor its entry. A closed case moves
    no further. Delete this and the clock can move with no record of who moved it."""
    import psycopg

    from tests.fixtures.scratch_postgres import sql

    aware = datetime.now(UTC) - timedelta(days=2)
    with at_head("brain_ws9_breach") as url:

        async def work(sessions: Any) -> Any:
            store = StoredBreachCases(sessions)
            dpo = Actor(principal_id="u_dpo", ent_hash="ab" * 16, trace_id="trace-open")
            case = await store.open(
                Awareness(
                    became_aware_at=aware,
                    basis=AwarenessBasis.OBSERVED,
                    source=AwarenessSource.INTERNAL_DETECTION,
                    recorded_at=datetime.now(UTC),
                    recorded_by="u_dpo",
                    evidence_reference="alert-4471",
                ),
                actor=dpo,
            )
            case_id = case.case.case_id
            steps = (
                (
                    "trace-assess",
                    {
                        "assessed_at": datetime.now(UTC),
                        "significant_harm": True,
                        "harm_decided_by": "u_dpo",
                        "harm_rationale_reference": "dpo-note-7",
                        "affected_count": 12,
                    },
                ),
                ("trace-commission", {"commission_notified_at": datetime.now(UTC)}),
                ("trace-individuals", {"individuals_notified_at": datetime.now(UTC)}),
                ("trace-close", {"closed_at": datetime.now(UTC), "closed_by": "u_dpo"}),
            )
            for trace, changes in steps:
                await store.move(case_id, changes, actor=Actor("u_dpo", "ab" * 16, trace))
            with pytest.raises(BreachRefusedError):
                await store.move(
                    case_id, {"confirmed_at": datetime.now(UTC)}, actor=Actor("u_dpo", "", "t")
                )
            return case_id, await store.cases()

        case_id, cases = with_sessions(url, work)
        [row_state] = sql(
            url,
            "SELECT assessed_at IS NOT NULL, commission_notified_at IS NOT NULL,"
            " individuals_notified_at IS NOT NULL, closed_by FROM ops.breach_case",
        )
        names = (
            "seq",
            "at",
            "actor_id",
            "action",
            "subject",
            "ent_hash",
            "trace_id",
            "details",
            "prev_hash",
            "entry_hash",
        )
        chain = [
            AuditEntry(**dict(zip(names, row, strict=True)))
            for row in sql(
                url,
                "SELECT seq, at, actor_id, action, subject, ent_hash, trace_id, details, prev_hash,"
                " entry_hash FROM obs.audit_entry ORDER BY seq",
            )
        ]
        # The same transaction: a case opened and moved inside one that is rolled back.
        with psycopg.connect(url) as conn:
            with conn.transaction(force_rollback=True):
                [(other,)] = conn.execute(
                    "INSERT INTO ops.breach_case (became_aware_at, awareness_basis,"
                    " awareness_source, recorded_at, recorded_by, evidence_reference, updated_by)"
                    " VALUES (now(), 'observed', 'staff_report', now(), 'u_dpo', 'ticket-9',"
                    " 'u_dpo') RETURNING case_id"
                ).fetchall()
                inside = conn.execute(
                    "SELECT count(*) FROM obs.audit_entry WHERE subject = %s",
                    (f"breach:{other}",),
                ).fetchall()
            after = conn.execute(
                "SELECT count(*) FROM obs.audit_entry WHERE subject = %s", (f"breach:{other}",)
            ).fetchall()

    breach = [one for one in chain if one.action.value == "breach"]
    assert [(e.subject, e.actor_id, e.trace_id, dict(e.details)) for e in breach] == [
        (f"breach:{case_id}", "u_dpo", "trace-open", {"change": "opened"}),
        (f"breach:{case_id}", "u_dpo", "trace-assess", {"change": "assessed"}),
        (f"breach:{case_id}", "u_dpo", "trace-commission", {"change": "commission_notified"}),
        (f"breach:{case_id}", "u_dpo", "trace-individuals", {"change": "individuals_notified"}),
        (f"breach:{case_id}", "u_dpo", "trace-close", {"change": "closed"}),
    ]
    assert AuditChain(chain).verify() is None
    assert row_state == (True, True, True, "u_dpo")
    assert cases[0].closed_by == "u_dpo"
    assert (inside, after) == ([(1,)], [(0,)])
