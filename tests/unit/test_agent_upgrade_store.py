"""An agent's upgrade followed to its rows and its ledger entries, against PostgreSQL.

`tests/unit/test_agent_upgrade_routes.py` proves the routes' decisions over an in-memory store.
This file proves what those decisions write. **The first half needs no server**: it reads `0204`'s
two trigger functions off the migration and holds their words, their actors and their details to
`AuditRecorder.agent`, and holds the store's acceptance to the compare-and-set the route
reads and to the columns a manifest decides.

**The second half presses the routes over HTTP** against a database built through the migrations
that ship, connected as the application role so every policy applies, signed in as a person
holding the lifecycle authority with a second factor: two agents installed from version two of a
template, version three published, the first agent accepting it and the second turning it away.
Each row is read back as the superuser and each ledger entry as an `AuditEntry`, and the chain is
verified. An operator's statement moving the pin is recorded with the inferred actor, and a
statement that leaves the pin where it is records nothing. **It skips without a server**, which is
CI's to provide.

Task ids: M13.4.4, M13.4.5
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from brain.agent_lifecycle_routes import INSTALL_PATH
from brain.agent_upgrade_routes import (
    ACCEPT_PATH,
    DECLINE_PATH,
    UPGRADE_PATH,
    StoredAgentUpgrades,
)
from brain.api import API_PREFIX
from brain.audit.ledger import AuditChain, AuditEntry
from brain.audit.record import INFERRED_ACTOR, AgentUpgradeChange, AuditRecorder
from brain.db import normalise_database_url
from brain.tables.template import TemplateVersionRow
from tests.fixtures.console_http import headers
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_agent_lifecycle_routes import TEMPLATE_ID, VERSION
from tests.unit.test_agent_lifecycle_store import (
    UNSUPPLIED,
    a_published_version,
    agent_entries,
    pressed,
    through_0137,
)
from tests.unit.test_agent_upgrade_routes import NEWER_PERSONA, newer
from tests.unit.test_credential_writes import entries
from tests.unit.test_tables import VERSIONS, migration_module

MIGRATION = VERSIONS / "0204_agent_upgrade_audit.py"


def recorder() -> AuditRecorder:
    return AuditRecorder(
        AuditChain(),
        actor_id="u_admin",
        ent_hash=UNSUPPLIED,
        trace_id="t",
        clock=lambda: datetime(2019, 3, 4, tzinfo=UTC),
    )


def squashed(text: str) -> str:
    return " ".join(text.split())


def upgraded_function() -> str:
    return squashed(migration_module(MIGRATION).UPGRADED_FUNCTION)


def declined_function() -> str:
    return squashed(migration_module(MIGRATION).DECLINED_FUNCTION)


# ------------------------------------------------------------------ the triggers' shape
def test_the_triggers_write_the_recorders_two_words_and_nothing_else() -> None:
    """Each function appends exactly one `jsonb_build_object('change', ...)` and the word is the
    recorder's, and between them they write both of its words.

    Delete this and a trigger can write a word `AuditRecorder` does not know, which the audit
    screen renders as a code and a reader cannot filter on."""
    module = migration_module(MIGRATION)
    assert re.findall(r"jsonb_build_object\('change', '(\w+)'\)", upgraded_function()) == [
        AgentUpgradeChange.UPGRADED.value
    ]
    assert re.findall(r"jsonb_build_object\('change', '(\w+)'\)", declined_function()) == [
        AgentUpgradeChange.UPGRADE_DECLINED.value
    ]
    assert tuple(one.value for one in AgentUpgradeChange) == (
        module.UPGRADED,
        module.UPGRADE_DECLINED,
    )


def test_a_pin_moved_is_attributed_to_the_person_the_route_named_and_a_decline_to_its_own_row() -> (
    None
):
    """The upgrade names `brain.actor_id` and marks the database role as inferred when nobody set
    it; the decline names the row's own `declined_by`, because the decision is the person's.

    Delete this and an acceptance is attributed to the database role, or a decline to whoever
    happened to hold the transaction."""
    upgraded, declined = upgraded_function(), declined_function()

    assert "v_actor := COALESCE(v_supplied, session_user::text);" in upgraded
    assert "v_inferred := v_supplied IS NULL;" in upgraded
    assert "v_supplied text := NULLIF(current_setting('brain.actor_id', true), '');" in upgraded
    assert f"jsonb_build_object('actor', '{INFERRED_ACTOR}')" in upgraded
    assert "v_subject text := 'agent:' || NEW.id;" in upgraded
    assert "v_actor := NEW.declined_by;" in declined
    assert "v_inferred" not in declined.split("BEGIN", 1)[1].split("IF v_inferred", 1)[0]
    assert "v_subject text := 'agent:' || NEW.instance_id;" in declined
    for body in (upgraded, declined):
        assert "v_seq, v_at, v_actor, 'agent', v_subject, v_ent_hash," in body


def test_the_triggers_record_the_change_and_never_a_version_a_digest_or_a_steward() -> None:
    """The details are the change word and, for an unnamed actor, the inferred marker, and the
    triggers read no version, digest or steward column.

    Delete this and an entry could carry a principal id, which the recorder stores as the marker
    and the ledger keeps longest of any table."""
    for body in (upgraded_function(), declined_function()):
        details = re.findall(r"v_details := (.*?);", body)
        assert all("NEW." not in one and "OLD." not in one for one in details)
        assert "owner_id" not in body and "content_digest" not in body


def test_the_upgrade_trigger_fires_only_when_the_pinned_version_moves() -> None:
    """The trigger's own condition is the version, so an overlay, a hash or a document written
    alone never reaches the function. The decline trigger is the insert, and nothing else.

    Delete this and every write to an install, a persona edit or a skill assignment, is also
    recorded as an upgrade."""
    module = migration_module(MIGRATION)
    trigger = squashed(module.UPGRADED_TRIGGER)
    assert "AFTER UPDATE ON agent.template_instance" in trigger
    assert "WHEN (OLD.template_version IS DISTINCT FROM NEW.template_version)" in trigger
    assert "AFTER INSERT ON agent.upgrade_decline" in squashed(module.DECLINED_TRIGGER)


def test_the_acceptance_is_a_compare_and_set_on_the_hash_and_version_the_page_drew() -> None:
    """The write that moves the pin names the install's hash and the version it was on, and writes
    the pin and the cached document and hash together; the agent row takes the manifest's own
    columns only.

    Delete this and two administrators pressing at once can both win, or an acceptance can write
    the agent's steward, audience or channels."""
    captured: list[Any] = []

    class Nothing:
        def scalar_one_or_none(self) -> None:
            return None

    class Capturing:
        """A session and its transaction in one: every statement kept, and no row matched."""

        async def __aenter__(self) -> Capturing:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        def begin(self) -> Capturing:
            return self

        async def execute(self, statement: Any) -> Nothing:
            captured.append(statement)
            return Nothing()

    from tests.unit.test_agent_upgrade_routes import Memory, on_offer

    memory = Memory()
    on_offer(memory, newer())
    reading = run(lambda: memory.read("pricing_desk"))
    assert reading is not None and reading.found.install is not None

    from brain.agents.upgrade import accept as accepted
    from brain.agents.upgrade import review
    from brain.connectors.registry import ConnectorRegistry
    from tests.unit.test_agent_lifecycle_routes import tools
    from tests.unit.test_agent_routes import KEY

    reviewed = review(reading.found.install[1], shelf=reading.shelf, declines=reading.declines)
    upgraded = accepted(
        reviewed,
        resolutions=dict.fromkeys((one.path for one in reviewed.conflicts), _take()),
        key=KEY,
        audience=reading.found.record.audience,
        registry=ConnectorRegistry(),
        tools=tools("ledger"),
        by="u_admin",
        at=datetime(2019, 3, 4, tzinfo=UTC),
    )
    store = StoredAgentUpgrades(Capturing)  # type: ignore[arg-type]
    written = run(
        lambda: store.accept(
            upgraded,
            from_version=VERSION,
            expected_hash="a" * 64,
            disabled_at=None,
            actor_id="u_admin",
            ent_hash="e" * 32,
            trace_id="t",
        )
    )

    dialect = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
    first = str(next(one for one in captured if "UPDATE" in str(one)).compile(dialect=dialect))
    assert written is False
    assert "agent.template_instance.effective_hash =" in first
    assert "agent.template_instance.template_version =" in first
    assert "RETURNING agent.template_instance.id" in first
    assigned = first.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
    assert {part.split("=")[0].strip() for part in assigned.split(", ")} >= {
        "template_version",
        "content_digest",
        "overlay",
        "field_owners",
        "effective_document",
        "effective_hash",
    }


def _take() -> Any:
    from brain.agents.upgrade import Resolution

    return Resolution.TAKE_TEMPLATE


# ------------------------------------------------------------------------ the database
def publish_newer(url: str) -> str:
    """Version three of the route tests' template, written as the superuser. Its digest."""
    signed = newer()
    built = create_engine(normalise_database_url(url), poolclass=NullPool)
    try:
        with Session(built) as session:
            session.add(
                TemplateVersionRow(
                    template_id=signed.manifest.identity.template_id,
                    version=signed.manifest.identity.version,
                    content_digest=signed.content_digest,
                    signature=signed.signature,
                    signed_by=signed.signed_by,
                    signed_at=signed.signed_at,
                    document=signed.manifest.document(),
                )
            )
            session.commit()
    finally:
        built.dispose()
    return signed.content_digest


def post(client: httpx.AsyncClient, path: str, body: Mapping[str, Any]) -> Any:
    return client.post(f"{API_PREFIX}{path}", json=dict(body), headers=headers("u_admin"))


def summary(found: list[AuditEntry]) -> list[tuple[str, str, dict[str, str]]]:
    return [(one.actor_id, one.subject, dict(one.details)) for one in found]


def test_an_acceptance_and_a_decline_pressed_reach_their_rows_and_one_ledger_entry_each() -> None:
    """Two agents installed from version two, version three published; the first accepts it and the
    second turns it away, each pressed over HTTP.

    The first agent's pin, persona and hash move together and the review afterwards is current;
    the second's pin stays where it was and `agent.upgrade_decline` holds one row naming the person
    and the version; and the ledger holds, beside each install's `created`, one `upgraded` entry
    for the first and one `upgrade_declined` for the second, each naming that person, the request's
    reach digest and its trace rather than the trigger's fallbacks, and the chain verifies. An
    operator's statement moving the pin is recorded with the inferred actor, and one that leaves it
    where it is records nothing. Delete this and either write can stop reaching its rows, or stop
    reaching the ledger, while the route tests over memory stay green.
    **Skips without a server.**"""
    with through_0137("brain_agent_upgrade_pressed") as url:
        digest = a_published_version(url)

        async def install(client: httpx.AsyncClient) -> list[dict[str, Any]]:
            made = []
            for name in ("Invoice desk one", "Invoice desk two"):
                response = await post(
                    client,
                    INSTALL_PATH.format(template_id=TEMPLATE_ID, version=VERSION),
                    {"expected_digest": digest, "display_name": name},
                )
                assert response.status_code == 201, response.text
                made.append(response.json()["agent"])
            return made

        first, second = (one["agent_id"] for one in pressed(url, install))
        third = publish_newer(url)
        before = sql(
            url,
            "SELECT id, template_version, effective_hash FROM agent.template_instance ORDER BY id",
        )

        async def press(client: httpx.AsyncClient) -> dict[str, Any]:
            seen = {}
            for agent_id in (first, second):
                response = await client.get(
                    f"{API_PREFIX}{UPGRADE_PATH.format(agent_id=agent_id)}",
                    headers=headers("u_admin"),
                )
                assert response.status_code == 200, response.text
                seen[agent_id] = response.json()
            accepted = await post(
                client,
                ACCEPT_PATH.format(agent_id=first),
                {
                    "to_version": seen[first]["to_version"],
                    "expected_hash": seen[first]["expected_hash"],
                    "resolutions": {},
                },
            )
            declined = await post(
                client,
                DECLINE_PATH.format(agent_id=second),
                {
                    "to_version": seen[second]["to_version"],
                    "expected_hash": seen[second]["expected_hash"],
                },
            )
            after = await client.get(
                f"{API_PREFIX}{UPGRADE_PATH.format(agent_id=first)}", headers=headers("u_admin")
            )
            return {
                "seen": seen,
                "accepted": (accepted.status_code, accepted.json()),
                "declined": (declined.status_code, declined.json()),
                "after": after.json(),
            }

        pressed_ = pressed(url, press)
        rows = {
            row[0]: tuple(row)
            for row in sql(
                url,
                "SELECT i.id, i.template_version, i.effective_hash, a.persona"
                " FROM agent.template_instance i JOIN agent.agent a ON a.id = i.id",
            )
        }
        declines = [
            tuple(row)
            for row in sql(
                url,
                "SELECT instance_id, template_id, version, content_digest, declined_by"
                " FROM agent.upgrade_decline",
            )
        ]
        sql(
            url,
            "UPDATE agent.template_instance SET effective_hash = effective_hash WHERE id = %s",
            first,
        )
        sql(
            url,
            "UPDATE agent.template_instance SET template_version = %s,"
            " content_digest = %s WHERE id = %s",
            VERSION,
            digest,
            first,
        )
        found = agent_entries(url)
        [(role,)] = sql(url, "SELECT session_user::text")
        chain = entries(url)

    assert pressed_["seen"][first]["badge"] == pressed_["seen"][second]["badge"] == "available"
    assert pressed_["accepted"][0] == 200 and pressed_["accepted"][1]["outcome"] == "upgraded"
    assert pressed_["declined"][0] == 200 and pressed_["declined"][1]["outcome"] == "declined"
    assert pressed_["after"]["badge"] == "current"
    old_first = next(one for one in before if one[0] == first)
    old_second = next(one for one in before if one[0] == second)
    assert rows[first][1] == VERSION + 1 and rows[first][2] != old_first[2]
    assert rows[first][3] == NEWER_PERSONA
    assert rows[second][1:3] == (VERSION, old_second[2])
    assert declines == [(second, TEMPLATE_ID, VERSION + 1, third, "u_admin")]

    one = recorder()
    assert summary(found) == [
        ("u_admin", f"agent:{first}", dict(one.agent(agent_id=first, change=_created()).details)),
        ("u_admin", f"agent:{second}", dict(one.agent(agent_id=second, change=_created()).details)),
        (
            "u_admin",
            f"agent:{first}",
            dict(one.agent(agent_id=first, change=AgentUpgradeChange.UPGRADED).details),
        ),
        (
            "u_admin",
            f"agent:{second}",
            dict(one.agent(agent_id=second, change=AgentUpgradeChange.UPGRADE_DECLINED).details),
        ),
        (
            role,
            f"agent:{first}",
            dict(
                one.agent(
                    agent_id=first, change=AgentUpgradeChange.UPGRADED, actor_inferred=True
                ).details
            ),
        ),
    ]
    pressed_entries = found[2:4]
    assert all(entry.ent_hash != UNSUPPLIED for entry in pressed_entries)
    assert all(not entry.trace_id.startswith("tx.") for entry in pressed_entries)
    assert AuditChain(chain).verify() is None


def _created() -> Any:
    from brain.audit.record import AgentChange

    return AgentChange.CREATED
