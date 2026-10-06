"""An agent's lifecycle followed to its row and its ledger entry, against PostgreSQL.

`tests/unit/test_agent_lifecycle_routes.py` proves the routes' decisions over an in-memory store.
This file proves what those decisions write. **The first half needs no server**: it reads `0137`'s
trigger function off the migration and holds its words, its actors and its details to
`AuditRecorder.agent`, holds that the trigger never writes the steward, and holds the store's
compare-and-set to the three columns a lifecycle move reads.

**The second half presses the routes over HTTP** against a database built through the migrations
that ship, connected as the application role so every policy applies, signed in as a person
holding both authorities with a second factor: a published version installed, the new agent
enabled, disabled, handed on, duplicated and archived, and an enable refused on the archived
agent. Each row is read back as the superuser and each ledger entry as an `AuditEntry`, and the
chain is verified. An operator's statement unarchiving an agent is recorded with the inferred
actor. A hand-over is recorded once, as `0105`'s `agent_owner`. **It skips without a server**,
which is CI's to provide.

Task ids: M27.11.6, M27.11.7
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from brain.agent_lifecycle_routes import (
    ARCHIVE_PATH,
    CHANNELS_PATH,
    DISABLE_PATH,
    DUPLICATE_PATH,
    ENABLE_PATH,
    INSTALL_PATH,
    LIFECYCLE_PATH,
    REFUSED,
    TRANSFER_PATH,
    StoredAgentLifecycles,
)
from brain.agents.lifecycle import PUBLICATION_LEVEL
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.audit.ledger import AuditChain, AuditEntry
from brain.audit.record import INFERRED_ACTOR, AgentChange, AuditRecorder
from brain.core.scope import Scope
from brain.db import normalise_database_url
from brain.knowledge.visibility import Visibility
from brain.session import make_session_factory
from brain.tables.template import TemplateVersionRow
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_agent_lifecycle_routes import (
    GRANTS,
    ONE_SOURCE,
    TEMPLATE_ID,
    VERSION,
    signed,
    tools,
)
from tests.unit.test_agent_routes import KEY
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_credential_writes import entries
from tests.unit.test_entitlement_store import a_principal
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0137_agent_lifecycle_audit.py"

#: The reach digest a trigger writes when nobody supplied one.
UNSUPPLIED = "0" * 32


def recorder() -> AuditRecorder:
    return AuditRecorder(
        AuditChain(),
        actor_id="u_admin",
        ent_hash=UNSUPPLIED,
        trace_id="t",
        clock=lambda: datetime(2019, 3, 4, tzinfo=UTC),
    )


def function() -> str:
    """The trigger function as it stands at head, whitespace collapsed: `0137`'s, as `0190`
    replaces it with the channels branch."""
    channels = migration_module(MIGRATION.with_name("0190_agent_channels_audited.py"))
    return " ".join(channels.replaced(migration_module(MIGRATION).AGENT_TRIGGER_FUNCTION).split())


# ------------------------------------------------------------------ the trigger's shape


def test_the_agent_trigger_writes_the_recorders_words_in_the_recorders_order() -> None:
    """Every word the trigger appends is an `AgentChange`, every one appears, and in the enum's
    order, which is the order entries land in when one statement moves several columns.

    Delete this and the trigger can write a word the recorder does not know, which the audit
    screen renders as a code and a reader cannot filter on."""
    body = function()

    assert re.findall(r"v_changes := v_changes \|\| '(\w+)'::text;", body) == [
        one.value for one in AgentChange
    ]


def test_0190_replaces_the_last_definition_of_the_agent_trigger_and_nothing_replaces_it_since() -> (
    None
):
    """`0190` rebuilds the function from `0137`'s text, so it is right only while `0137` is the
    last migration before it to define `agent.record_agent_change`, and it stays right only while
    nothing after it does so without starting from `0190`'s result. Checked on main and on every
    open migration branch the day `0190` was written: `0137` was the only definition.

    Delete this and a later migration that adds a branch to the trigger can be undone silently by
    `0190` on an install that applies them in revision order, or can undo `0190`'s branch, and the
    ledger stops recording channel switches with every other test green."""
    defining = sorted(
        path.name[:4]
        for path in VERSIONS.glob("*.py")
        if "record_agent_change" in path.read_text(encoding="utf-8")
        or "AGENT_TRIGGER_FUNCTION" in path.read_text(encoding="utf-8")
    )

    assert defining == ["0137", "0190"]


def test_an_insert_is_attributed_to_its_builder_and_an_update_to_the_person_the_route_named() -> (
    None
):
    """`created` names the row's own `created_by`; every other change names `brain.actor_id` and
    marks the database role as inferred when nobody set it.

    Delete this and an install can be attributed to the database role, or a disable to the agent's
    builder, who pressed nothing."""
    body = function()

    assert "v_changes := v_changes || 'created'::text; v_actor := NEW.created_by;" in body
    assert "v_actor := COALESCE(v_supplied, session_user::text);" in body
    assert "v_inferred := v_supplied IS NULL;" in body
    assert "v_supplied text := NULLIF(current_setting('brain.actor_id', true), '');" in body
    assert f"v_details := v_details || jsonb_build_object('actor', '{INFERRED_ACTOR}');" in body
    assert "v_seq, v_at, v_actor, 'agent', v_subject, v_ent_hash," in body
    assert "v_subject text := 'agent:' || NEW.id;" in body


def test_the_agent_trigger_records_the_change_and_never_the_steward_or_a_time() -> None:
    """The details are the change word and, for an unnamed actor, the inferred marker. The
    steward's id is compared and never written.

    Delete this and an entry could carry a principal id, which the recorder stores as the marker
    and the ledger keeps longest of any table."""
    body = function()

    assert "v_details := jsonb_build_object('change', v_changes[i]);" in body
    assert "jsonb_build_object('owner" not in body
    assert "NEW.owner_id)" not in body
    assert "NEW.disabled_at)" not in body and "NEW.archived_at)" not in body
    entry = recorder().agent(agent_id="pricing_desk", change=AgentChange.ARCHIVED)
    assert (entry.subject, dict(entry.details)) == (
        "agent:pricing_desk",
        {"change": "archived"},
    )
    inferred = recorder().agent(
        agent_id="pricing_desk", change=AgentChange.UNARCHIVED, actor_inferred=True
    )
    assert dict(inferred.details) == {"change": "unarchived", "actor": INFERRED_ACTOR}


def test_a_hand_over_is_left_to_the_owner_trigger_so_it_is_recorded_once() -> None:
    """`0105` records every change of `owner_id` as `agent_owner`, with both owners. This trigger
    never reads the owner, so a transfer is one entry and not two under two actions.

    Delete this and the draft's `transferred` can come back, and every hand-over is recorded
    twice, which 0105's own title says it is not."""
    body = function()

    assert "owner_id" not in body
    assert "transferred" not in {one.value for one in AgentChange}
    owner = migration_module(VERSIONS / "0105_agent_owner_audit.py")
    assert "AFTER UPDATE OF owner_id ON agent.agent" in " ".join(owner.TRIGGER.split())


def test_the_action_list_this_replaces_is_the_one_0136_leaves() -> None:
    """The draft revised 0083 and copied 0062's list, which would have dropped every action added
    since. Delete this and a migration re-pointed at a new head can still narrow the ledger."""
    module = migration_module(MIGRATION)
    halt = migration_module(VERSIONS / "0136_ops_halt.py")

    assert module.down_revision == halt.revision
    assert module.NARROWER_ACTIONS == halt.WIDENED_ACTIONS
    assert (
        module.NARROWER_ACTIONS.replace("IN ('agent_owner'", "IN ('agent', 'agent_owner'")
        == module.WIDENED_ACTIONS
    )


def test_a_publication_in_the_trigger_is_the_level_the_lifecycle_publishes_to() -> None:
    """The migration's copy of the company level and of the inferred marker are the product's.

    Delete this and renaming the company level would record every publication as an audience
    change, with every test that reads the trigger's words still green."""
    module = migration_module(MIGRATION)

    assert PUBLICATION_LEVEL.value == module.PUBLICATION_LEVEL
    assert module.INFERRED == INFERRED_ACTOR
    assert f"IF NEW.visibility = '{PUBLICATION_LEVEL.value}' THEN" in function()


def test_the_agent_trigger_is_created_on_the_insert_and_the_update() -> None:
    """Delete this and a trigger on the update alone records every move and never an install."""
    emitted = squash(rendered("upgrade", MIGRATION))

    assert (
        "CREATE TRIGGER agent_is_audited AFTER INSERT OR UPDATE ON agent.agent FOR EACH ROW "
        "EXECUTE FUNCTION agent.record_agent_change()"
    ) in emitted


def test_a_lifecycle_write_compares_the_three_columns_it_read_and_writes_only_those() -> None:
    """The store's statement, compiled: the row must still hold the timestamps and the steward
    the route read, and nothing else about the agent is written.

    Delete this and the compare-and-set can lose a column, so a page that drew an agent before
    somebody archived it could enable it, or the write could carry a ceiling."""
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

    record = AgentRecord(
        agent_id="pricing_desk",
        display_name="Pricing desk",
        persona="Answer briefly.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(scope=Scope.unrestricted()),
        created_by="u_builder",
    )
    store = StoredAgentLifecycles(Capturing)  # type: ignore[arg-type]
    written = run(
        lambda: store.change(record, record, actor_id="u_admin", ent_hash="e" * 32, trace_id="t")
    )

    dialect = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
    update = next(str(one.compile(dialect=dialect)) for one in captured if "UPDATE" in str(one))
    assert written is False
    assert "agent.agent.disabled_at IS NOT DISTINCT FROM" in update
    assert "agent.agent.archived_at IS NOT DISTINCT FROM" in update
    assert "agent.agent.owner_id =" in update
    assert "RETURNING agent.agent.id" in update
    assigned = update.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
    assert sorted(part.split("=")[0].strip() for part in assigned.split(", ")) == [
        "archived_at",
        "disabled_at",
        "owner_id",
        "updated_at",
    ]


def test_a_channel_switch_compares_the_channels_it_read_and_writes_only_those() -> None:
    """`change_channels`' statement, compiled: the row must still hold the channels the route
    read, and nothing but the channels (and the row's own timestamp) is written.

    Delete this and the compare-and-set can lose its one column, so two stewards pressing at once
    both win and the second silently undoes the first; the route's own `expected` check reads the
    row before this statement runs and cannot see that race."""
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

    before = AgentRecord(
        agent_id="pricing_desk",
        display_name="Pricing desk",
        persona="Answer briefly.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(scope=Scope.unrestricted()),
        created_by="u_builder",
        channels=("console",),
    )
    after = before.model_copy(update={"channels": ("console", "lark")})
    store = StoredAgentLifecycles(Capturing)  # type: ignore[arg-type]
    written = run(
        lambda: store.change_channels(
            before, after, actor_id="u_steward", ent_hash="e" * 32, trace_id="t"
        )
    )

    dialect = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
    [update] = [one for one in captured if "UPDATE" in str(one)]
    compiled = update.compile(dialect=dialect)
    sql_text = str(compiled)
    assert written is False
    assert "AND agent.agent.channels = %(channels_1)s" in sql_text
    assert compiled.params["channels_1"] == ["console"]
    assert compiled.params["channels"] == ["console", "lark"]
    assert "RETURNING agent.agent.id" in sql_text
    assigned = sql_text.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
    assert sorted(part.split("=")[0].strip() for part in assigned.split(", ")) == [
        "channels",
        "updated_at",
    ]


# ------------------------------------------------------------------------ the database


@contextmanager
def through_0137(database: str) -> Iterator[str]:
    """A database built through every migration to head, which includes `0137`.

    `retirable` runs the whole chain where the server has pgvector, which CI's has. Without it
    the chain stops short of `0105` and `0136`, which this file's entries depend on, so it skips.
    """
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("0137 is built only on the chain CI runs, where every migration is")
        yield url


def a_published_version(url: str) -> str:
    """The route tests' template version, written as the superuser. Its digest."""
    version = signed()
    built = create_engine(normalise_database_url(url), poolclass=NullPool)
    try:
        with Session(built) as session:
            session.add(
                TemplateVersionRow(
                    template_id=version.manifest.identity.template_id,
                    version=version.manifest.identity.version,
                    content_digest=version.content_digest,
                    signature=version.signature,
                    signed_by=version.signed_by,
                    signed_at=version.signed_at,
                    document=version.manifest.document(),
                )
            )
            session.commit()
    finally:
        built.dispose()
    return version.content_digest


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The application's own routes over this database as the application role, with a signing
    key and the route tests' one-source registry. No lifespan runs."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = make_session_factory(built)
            app.state.console_reads = None
            app.state.template_key = KEY
            app.state.tools = tools(*ONE_SOURCE)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def post(client: httpx.AsyncClient, path: str, body: Mapping[str, Any]) -> Awaitable[Any]:
    return client.post(f"{API_PREFIX}{path}", json=dict(body), headers=headers("u_admin"))


def agent_row(url: str, agent_id: str) -> tuple[Any, ...]:
    [row] = sql(
        url,
        "SELECT disabled_at IS NOT NULL, archived_at IS NOT NULL, owner_id, visibility, created_by"
        " FROM agent.agent WHERE id = %s",
        agent_id,
    )
    return tuple(row)


def agent_entries(url: str) -> list[AuditEntry]:
    return [one for one in entries(url) if one.action.value == "agent"]


def summary(found: list[AuditEntry]) -> list[tuple[str, str, dict[str, str]]]:
    return [(one.actor_id, one.subject, dict(one.details)) for one in found]


def test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person() -> None:
    """An install, then enable, disable, transfer, duplicate and archive, each pressed over HTTP.

    The installed agent is written disabled, `created` by the person who pressed; each move after
    it writes its row and one entry naming that person, with the request's reach digest and trace
    rather than the trigger's fallbacks; the duplicate is a second agent, disabled and `created`;
    and enabling the archived agent is a 409 that writes neither a row nor an entry. The chain
    verifies. Delete this and any of the six writes can stop reaching the ledger, or stop reaching
    the table, while the route tests over memory stay green. **Skips without a server.**"""
    with through_0137("brain_agent_lifecycle_moves") as url:
        digest = a_published_version(url)
        a_principal(url, "u_wide")

        async def install(client: httpx.AsyncClient) -> Any:
            response = await post(
                client,
                INSTALL_PATH.format(template_id=TEMPLATE_ID, version=VERSION),
                {"expected_digest": digest},
            )
            assert response.status_code == 201, response.text
            return response.json()["agent"]

        made = pressed(url, install)
        agent_id = made["agent_id"]
        after_install = agent_row(url, agent_id)

        async def moves(client: httpx.AsyncClient) -> list[int]:
            codes = []
            for path, body in (
                (ENABLE_PATH, {"expected_state": "disabled"}),
                (DISABLE_PATH, {"expected_state": "enabled"}),
                (TRANSFER_PATH, {"to_owner": "u_wide", "expected_owner": "u_admin"}),
            ):
                response = await post(client, path.format(agent_id=agent_id), body)
                codes.append(response.status_code)
            view = await client.get(
                f"{API_PREFIX}{LIFECYCLE_PATH.format(agent_id=agent_id)}",
                headers=headers("u_admin"),
            )
            codes.append(view.status_code)
            return codes

        # After the transfer the agent is personal to u_wide and u_admin cannot see it, so the
        # lifecycle view that closes the list is the one 404.
        assert pressed(url, moves) == [200, 200, 200, 404]
        after_moves = agent_row(url, agent_id)

        async def copy_and_retire(client: httpx.AsyncClient) -> tuple[Any, ...]:
            # A second install, which u_admin can still see, to duplicate and archive.
            second = await post(
                client,
                INSTALL_PATH.format(template_id=TEMPLATE_ID, version=VERSION),
                {"expected_digest": digest, "display_name": "Invoice desk two"},
            )
            second_id = second.json()["agent"]["agent_id"]
            duplicated = await post(
                client,
                DUPLICATE_PATH.format(agent_id=second_id),
                {
                    "display_name": "Invoice desk copy",
                    "expected_hash": second.json()["agent"]["effective_hash"],
                },
            )
            archived = await post(
                client, ARCHIVE_PATH.format(agent_id=second_id), {"expected_state": "disabled"}
            )
            refused = await post(
                client, ENABLE_PATH.format(agent_id=second_id), {"expected_state": "archived"}
            )
            return (
                second_id,
                duplicated.status_code,
                duplicated.json(),
                archived.status_code,
                (
                    refused.status_code,
                    refused.json(),
                ),
            )

        second_id, dup_status, dup_body, archive_status, (refused_status, refused_body) = pressed(
            url, copy_and_retire
        )
        copy_id = dup_body["agent"]["agent_id"]
        copy_row = agent_row(url, copy_id)
        second_row = agent_row(url, second_id)
        found = agent_entries(url)
        handed = [one for one in entries(url) if one.action.value == "agent_owner"]
        chain = entries(url)

    assert after_install == (True, False, "u_admin", "personal", "u_admin")
    assert after_moves == (True, False, "u_wide", "personal", "u_admin")
    assert (dup_status, archive_status) == (201, 200)
    assert copy_row == (True, False, "u_admin", "personal", "u_admin")
    assert second_row == (True, True, "u_admin", "personal", "u_admin")
    assert (refused_status, refused_body["outcome"]) == (409, REFUSED)
    one = recorder()
    assert summary(found) == [
        ("u_admin", f"agent:{agent_id}", dict(one.agent(agent_id=agent_id, change=change).details))
        for change in (
            AgentChange.CREATED,
            AgentChange.ENABLED,
            AgentChange.DISABLED,
        )
    ] + [
        (
            "u_admin",
            f"agent:{second_id}",
            dict(one.agent(agent_id=second_id, change=AgentChange.CREATED).details),
        ),
        (
            "u_admin",
            f"agent:{copy_id}",
            dict(one.agent(agent_id=copy_id, change=AgentChange.CREATED).details),
        ),
        (
            "u_admin",
            f"agent:{second_id}",
            dict(one.agent(agent_id=second_id, change=AgentChange.ARCHIVED).details),
        ),
    ]
    assert summary(handed) == [
        (
            "u_admin",
            f"agent:{agent_id}",
            {"change": "owner_changed", "from_owner": "u_admin", "to_owner": "u_wide"},
        )
    ]
    assert all(entry.ent_hash != UNSUPPLIED for entry in found)
    assert all(not entry.trace_id.startswith("tx.") for entry in found)
    assert AuditChain(chain).verify() is None


def test_an_operators_statement_bringing_an_archived_agent_back_is_recorded_as_inferred() -> None:
    """Archive is terminal in the product and a statement can still clear it: the ledger records
    `unarchived`, attributed to the database role and marked inferred, and a statement that moves
    no lifecycle column records nothing.

    Delete this and the one way an archived agent comes back is the one way nothing records.
    **Skips without a server.**"""
    with through_0137("brain_agent_lifecycle_statement") as url:
        sql(
            url,
            "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
            " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
            " created_by, archived_at) VALUES ('quote_helper', 'Quote helper', 'Answers briefly.',"
            " 'main', 'company', 'u_steward', NULL, '{\"clauses\": []}', '{}', '{}', '{}', 'none',"
            " 'u_builder', now())",
        )
        sql(
            url, "UPDATE agent.agent SET persona = 'Answers in one line.' WHERE id = 'quote_helper'"
        )
        sql(url, "UPDATE agent.agent SET archived_at = NULL WHERE id = 'quote_helper'")
        found = agent_entries(url)
        [(role,)] = sql(url, "SELECT session_user::text")
        chain = entries(url)

    one = recorder()
    assert summary(found) == [
        (
            "u_builder",
            "agent:quote_helper",
            dict(one.agent(agent_id="quote_helper", change=AgentChange.CREATED).details),
        ),
        (
            role,
            "agent:quote_helper",
            dict(
                one.agent(
                    agent_id="quote_helper", change=AgentChange.UNARCHIVED, actor_inferred=True
                ).details
            ),
        ),
    ]
    assert AuditChain(chain).verify() is None


def test_a_channel_switch_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person() -> None:
    """**M13.7.4's change, on the ledger.** An administrator switches an installed agent onto two
    channels over HTTP: the row holds them, one `channels_changed` entry names the person, and a
    second press from a page that still shows none is a 409 that writes neither. Delete this and a
    channel can be switched with nothing recording who did it. **Skips without a server.**"""
    with through_0137("brain_agent_channel_switch") as url:
        digest = a_published_version(url)

        async def switch(client: httpx.AsyncClient) -> tuple[str, int, int]:
            made = await post(
                client,
                INSTALL_PATH.format(template_id=TEMPLATE_ID, version=VERSION),
                {"expected_digest": digest},
            )
            agent_id = made.json()["agent"]["agent_id"]
            path = CHANNELS_PATH.format(agent_id=agent_id)
            first = await post(client, path, {"channels": ["lark", "console"], "expected": []})
            stale = await post(client, path, {"channels": ["email"], "expected": []})
            return agent_id, first.status_code, stale.status_code

        before = len(agent_entries(url))
        agent_id, first, stale = pressed(url, switch)
        [stored] = sql(url, "SELECT channels FROM agent.agent WHERE id = %s", agent_id)
        switched = [
            one
            for one in agent_entries(url)[before:]
            if one.details.get("change") == "channels_changed"
        ]

    assert (first, stale) == (200, 409)
    assert stored == (["console", "lark"],)
    assert [(one.actor_id, one.subject) for one in switched] == [("u_admin", f"agent:{agent_id}")]
