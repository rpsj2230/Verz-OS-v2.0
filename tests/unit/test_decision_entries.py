"""M24.1.3: a deny, a leash change, a merge, a publish and a break-glass each write their entry.

Each kind is proved the same way on real rows: the decision is written inside a transaction, the
entry is read back from that same transaction, and the transaction is rolled back, after which the
entry is gone. An entry that survives the rollback was written somewhere else; one missing inside
it was not written with the decision. Then the decision is written for real and the entry's
details are compared with what `brain.audit.record.AuditRecorder` writes for the same event, so
the database and a chain held in memory cannot disagree about what one looks like.

The first two tests read the migration and the recorder and need no server; the rest build the
database to head, which CI has and a development machine without pgvector skips.

Task ids: M24.1.3
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.audit.ledger import AuditChain
from brain.audit.record import AuditRecorder, DenyReason
from brain.core.entitlement import Capability
from brain.gate.injection import AutonomyTier
from brain.identity.roles import BreakGlassReason
from brain.resolution.canonical import EntityType
from tests.unit.test_tables import VERSIONS, migration_module

MIGRATION = VERSIONS / "0104_compliance_record_and_decision_entries.py"


def recorder() -> AuditRecorder:
    return AuditRecorder(
        AuditChain(),
        actor_id="u_actor",
        ent_hash="0" * 32,
        trace_id="t",
        clock=lambda: datetime.now(UTC),
    )


def test_each_trigger_writes_the_keys_its_recorder_method_writes() -> None:
    """The five triggers against the five methods. Delete this and a trigger can write a detail
    the recorder never does, or miss one it always does, and the audit view renders the database's
    entries differently from every chain held in memory."""
    body = migration_module(MIGRATION)
    record = recorder()
    pairs = {
        body.BREAK_GLASS_TRIGGER_FUNCTION: record.break_glass(
            session_id="s1",
            principal_id="u_requester",
            reason=BreakGlassReason.INCIDENT_RESPONSE,
            authorised_by="u_approver",
        ),
        body.LEASH_CHANGE_TRIGGER_FUNCTION: record.leash_change(
            agent_id="a1",
            target="ticket",
            from_rung=AutonomyTier.SHADOW,
            to_rung=AutonomyTier.ASSISTED,
        ),
        body.DENIAL_FUNCTION: record.deny(
            subject_kind="entity",
            subject_id="price_list",
            capability=Capability(value="read:price_list"),
            reason=DenyReason.NO_GRANT,
        ),
    }
    for function, entry in pairs.items():
        for key in entry.details:
            assert f"'{key}'" in function, (key, function[:60])
    merged = record.entity_merge(kept_entity_id="e1", merged_entity_id="e2")
    assert all(dict(one.details) == {} for one in merged)
    assert dict(record.publish(artifact_id="agent.v1").details) == {}
    for rung in AutonomyTier:
        assert f"'{rung.name.lower()}'" in body.LEASH_CHANGE_TRIGGER_FUNCTION
    for reason in DenyReason:
        assert f"'{reason.value}'" in body.DENY_REASONS


def test_the_upgrade_creates_every_trigger_and_the_downgrade_drops_it() -> None:
    """Delete this and a trigger can sit in a constant that `upgrade` never executes, which is a
    decision point recorded in a docstring and nowhere else."""
    from tests.unit.test_tables import rendered, squash

    up = squash(rendered("upgrade", MIGRATION))
    down = squash(rendered("downgrade", MIGRATION))
    for name, table in (
        ("elevation_request_opens_break_glass", "gate.elevation_request"),
        ("canonical_merge_is_audited", "er.canonical"),
        ("template_instance_leash_is_audited", "agent.template_instance"),
        ("template_version_publish_is_audited", "agent.template_version"),
        ("breach_case_is_audited", "ops.breach_case"),
    ):
        assert f"CREATE TRIGGER {name}" in up
        assert f"DROP TRIGGER {name} ON {table}" in down
    assert "CREATE FUNCTION gate.record_denial(" in up
    assert "DROP FUNCTION gate.record_denial(text, text, text)" in down


# ---------------------------------------------------------------------------- the database


@contextmanager
def at_head(database: str) -> Iterator[str]:
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import admin_url

    admin_url()
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("the chain to 0104 needs pgvector, which CI has")
        yield url


def within_and_after(
    url: str, write: Callable[[Any], None], action: str
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    """The entries of `action` seen inside a transaction that made `write`, and after rolling it
    back. Attribution is set in the transaction the way `attributed_to` sets it."""
    import psycopg

    query = (
        "SELECT actor_id, subject, details, trace_id FROM obs.audit_entry"
        " WHERE action = %s ORDER BY seq"
    )
    with psycopg.connect(url) as conn:
        with conn.transaction(force_rollback=True):
            conn.execute("SELECT set_config('brain.actor_id', 'u_actor', true)")
            conn.execute("SELECT set_config('brain.trace_id', 'trace-decision', true)")
            write(conn)
            inside = conn.execute(query, (action,)).fetchall()
        after = conn.execute(query, (action,)).fetchall()
    return inside, after


def details_of(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else json.loads(value)


def test_a_recorded_denial_appends_a_deny_entry_in_its_transaction() -> None:
    """The deny `brain.ops.denial_store` writes for the records route's refusal. Delete this and
    `gate.record_denial` can append nothing, or append outside the caller's transaction."""
    with at_head("brain_ws9_deny") as url:
        inside, after = within_and_after(
            url,
            lambda c: c.execute(
                "SELECT gate.record_denial('entity:price_list', 'read:price_list', 'no_grant')"
            ),
            "deny",
        )

    [(actor, subject, details, trace)] = inside
    assert (actor, subject, trace) == ("u_actor", "entity:price_list", "trace-decision")
    assert details_of(details) == {"capability": "read:price_list", "reason": "no_grant"}
    assert after == []


def test_a_denial_that_is_not_a_deny_reason_is_refused() -> None:
    """The function is narrow: a reason outside `DenyReason` is refused rather than recorded.
    Delete this and the function becomes the general append `brain.audit.record` refuses to have."""
    import psycopg

    with (
        at_head("brain_ws9_deny_refused") as url,
        psycopg.connect(url) as conn,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        conn.execute(
            "SELECT gate.record_denial('entity:price_list', 'read:price_list', 'felt_like_it')"
        )


def test_an_approved_elevation_appends_a_break_glass_entry_in_its_transaction() -> None:
    """Break-glass at its decision point: the approval of an elevation request. Delete this and
    break-glass is recorded only as an elevation, which the tracker audit found."""
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_entitlement_store import a_principal

    with at_head("brain_ws9_break_glass") as url:
        for pid in ("u_requester", "u_approver"):
            a_principal(url, pid)
        [(grant_id,)] = sql(
            url,
            "INSERT INTO gate.capability_grant"
            " (principal_id, capability, scope, granted_by, reason)"
            " VALUES ('u_requester', 'read:client.name', '{\"clauses\": []}', 'u_approver',"
            " 'an elevation') RETURNING id",
        )
        [(request_id,)] = sql(
            url,
            "INSERT INTO gate.elevation_request (principal_id, capability, scope_slug, reason,"
            " explanation, hours) VALUES ('u_requester', 'read:client.name', 'web_all',"
            " 'incident_response', 'the portal is down', 2) RETURNING id",
        )
        inside, after = within_and_after(
            url,
            lambda c: c.execute(
                "UPDATE gate.elevation_request SET decision = 'approved',"
                " decided_by = 'u_approver', decided_at = now(), grant_id = %s,"
                " lapses_at = now() + interval '1 hour' WHERE id = %s",
                (grant_id, request_id),
            ),
            "break_glass",
        )

    [(actor, subject, details, trace)] = inside
    assert (actor, subject, trace) == ("u_approver", f"session:{request_id}", "trace-decision")
    assert details_of(details) == {
        "reason": "incident_response",
        "principal": "u_requester",
        "authorised_by": "u_approver",
    }
    assert after == []


def test_a_merge_appends_one_entry_per_side_in_its_transaction() -> None:
    """Both ids of a merge are findable, kept first. Delete this and the id that disappeared has
    no entry saying where it went."""
    from tests.fixtures.scratch_postgres import sql

    kind = next(iter(EntityType)).value
    with at_head("brain_ws9_merge") as url:
        for entity_id in ("e_kept", "e_gone"):
            sql(
                url,
                "INSERT INTO er.canonical (entity_id, entity_type, created_by, created_from_source,"
                " created_from_entity, created_from_source_id) VALUES (%s, %s, 'resolver', 'xero',"
                " 'contact', %s)",
                entity_id,
                kind,
                f"src-{entity_id}",
            )
        inside, after = within_and_after(
            url,
            lambda c: c.execute(
                "UPDATE er.canonical SET merged_into = 'e_kept', merged_at = now()"
                " WHERE entity_id = 'e_gone'"
            ),
            "entity_merge",
        )

    assert [(a, s, details_of(d), t) for a, s, d, t in inside] == [
        ("u_actor", "entity:e_kept", {}, "trace-decision"),
        ("u_actor", "entity:e_gone", {}, "trace-decision"),
    ]
    assert after == []


def installed(url: str) -> str:
    """One agent installed through the install store, as the application role. Its id."""
    from brain.agents.install_store import StoredAgentInstalls
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run
    from tests.unit.test_agent_install_store import MANIFEST, a_draft, finishing
    from tests.unit.test_automation_owner_store import app_engine

    async def go() -> None:
        built = app_engine(url)
        try:
            await finishing(StoredAgentInstalls(make_session_factory(built)), a_draft())()
        finally:
            await built.dispose()

    run(go)
    return str(MANIFEST.identity.template_id)


def test_a_published_template_version_appends_a_publish_entry_in_its_transaction() -> None:
    """A template version arriving in the install is a publish. Delete this and publishing an agent
    leaves nothing, and the only publish recorded is a data export."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_ws9_publish") as url:
        agent = installed(url)
        [(version, document, digest)] = sql(
            url,
            "SELECT version, document, content_digest FROM agent.template_version"
            " WHERE template_id = %s",
            agent,
        )
        published = sql(
            url,
            "SELECT subject, details FROM obs.audit_entry WHERE action = 'publish'"
            " AND subject = %s",
            f"artifact:{agent}.v{version}",
        )
        inside, after = within_and_after(
            url,
            lambda c: c.execute(
                "INSERT INTO agent.template_version (template_id, version, content_digest,"
                " signature, signed_by, signed_at, document)"
                " SELECT template_id, version + 1, content_digest, signature, signed_by, signed_at,"
                " document FROM agent.template_version WHERE template_id = %s",
                (agent,),
            ),
            "publish",
        )

    assert [(s, details_of(d)) for s, d in published] == [(f"artifact:{agent}.v{version}", {})]
    assert (document, digest) and inside[-1][1] == f"artifact:{agent}.v{version + 1}"
    assert inside[-1][0] == "u_actor"
    assert len(after) == len(inside) - 1


def test_a_leash_change_appends_one_entry_per_moved_target_in_its_transaction() -> None:
    """A rung added for one target, with every other target the install carries left as it was,
    is exactly one entry naming both rungs, and a write that leaves the leash alone writes none.
    Delete this and loosening an agent from Shadow to Autonomous leaves no record of who did it,
    or every untouched target is recorded as changed too."""
    from tests.fixtures.scratch_postgres import sql

    # A target no manifest names, so its rung before the change is the Shadow default.
    added = {"target": "compliance_probe", "scope": {"clauses": []}, "rung": 2}
    with at_head("brain_ws9_leash") as url:
        agent = installed(url)
        [(before,)] = sql(
            url,
            "SELECT effective_document -> 'guardrails.leash' FROM agent.template_instance"
            " WHERE id = %s",
            agent,
        )
        rung = json.dumps([*(before or []), added])
        untouched, _ = within_and_after(
            url,
            lambda c: c.execute(
                "UPDATE agent.template_instance SET effective_document = effective_document"
                " WHERE id = %s",
                (agent,),
            ),
            "leash_change",
        )
        inside, after = within_and_after(
            url,
            lambda c: c.execute(
                "UPDATE agent.template_instance SET effective_document ="
                " jsonb_set(effective_document, '{guardrails.leash}', %s::jsonb) WHERE id = %s",
                (rung, agent),
            ),
            "leash_change",
        )

    assert all(one.get("target") != added["target"] for one in (before or []))
    assert untouched == []
    [(actor, subject, details, trace)] = inside
    assert (actor, subject, trace) == ("u_actor", f"agent:{agent}", "trace-decision")
    assert details_of(details) == {
        "target": "compliance_probe",
        "from_rung": AutonomyTier.SHADOW.name.lower(),
        "to_rung": "autonomous",
    }
    assert after == []


def test_an_install_that_arrives_with_a_leash_is_not_a_leash_change() -> None:
    """The first leash is the install, recorded as the publish of its version. Delete this and the
    trigger fires on insert, and every install reads as somebody loosening an agent."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_ws9_leash_install") as url:
        installed(url)
        changes = sql(url, "SELECT count(*) FROM obs.audit_entry WHERE action = 'leash_change'")

    assert changes == [(0,)]


def test_a_denied_elevation_opens_no_break_glass() -> None:
    """The sibling of the approval: a denial is recorded as an elevation and never as a session
    opened. Delete this and a refused request reads as emergency access taken."""
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_entitlement_store import a_principal

    with at_head("brain_ws9_break_glass_denied") as url:
        for pid in ("u_requester", "u_approver"):
            a_principal(url, pid)
        [(request_id,)] = sql(
            url,
            "INSERT INTO gate.elevation_request (principal_id, capability, scope_slug, reason,"
            " explanation, hours) VALUES ('u_requester', 'read:client.name', 'web_all',"
            " 'incident_response', 'the portal is down', 2) RETURNING id",
        )
        sql(
            url,
            "UPDATE gate.elevation_request SET decision = 'denied', decided_by = 'u_approver',"
            " decided_at = now() WHERE id = %s",
            request_id,
        )
        opened = sql(url, "SELECT count(*) FROM obs.audit_entry WHERE action = 'break_glass'")

    assert opened == [(0,)]
    assert uuid.UUID(str(request_id))
