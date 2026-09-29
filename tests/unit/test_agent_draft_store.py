"""`0149` and `brain.builder.draft_store`: an agent's drafts written, published and on the ledger.

**The first half needs no server.** It holds the migration to the model on rendered DDL and to the
domain's words, holds its grants to SELECT and INSERT, and holds every word its triggers write to
`brain.builder.draft_words.DraftChange`.

**The second half presses the routes over HTTP** against a database built through the migrations
that ship, connected as the application role so every policy applies: a new agent drafted, saved,
checked and asked for, approved by a second person and published; then edited, checked and
published again as the next version of its own template. Every row is read back as the superuser and
every ledger entry as an `AuditEntry`, and the chain verifies. A row naming somebody other than the
session is refused, and nothing can be changed or removed. **It skips without a server**, which is
CI's to provide.

Task ids: M27.11.6, M27.15.29, M27.15.31
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import httpx
import psycopg
import pytest
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.agent_builder_routes import (
    APPROVE_PATH,
    CHECK_PATH,
    DECLINE_PATH,
    DRAFTS_PATH,
    EDIT_PATH,
    PUBLISH_PATH,
    SAVE_PATH,
)
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.audit.ledger import AuditChain, AuditEntry
from brain.builder.draft_words import DraftAct, DraftChange, DraftKind
from brain.db import metadata
from brain.identity.principal_store import PRINCIPAL_SETTING
from brain.session import make_session_factory
from brain.tables import manifest_draft as tables
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_agent_builder_routes import GRANTS, PERSONA, a_document
from tests.unit.test_agent_lifecycle_routes import tools
from tests.unit.test_agent_routes import KEY
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_credential_writes import entries
from tests.unit.test_tables import DIALECT, VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0149_agent_manifest_draft.py"
TABLE_NAMES = ("agent.manifest_draft", "agent.manifest_revision", "agent.manifest_act")


def module() -> Any:
    return migration_module(MIGRATION)


# ------------------------------------------------------------------------ the migration's copy
def test_the_migration_builds_the_three_tables_exactly_as_the_models_declare_them() -> None:
    """The copy compared on rendered DDL. Delete this and the model can declare a key, a width or a
    check the database does not enforce."""
    emitted = squash(rendered("upgrade", MIGRATION))
    for name in TABLE_NAMES:
        table = metadata.tables[name]
        assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted
        for index in table.indexes:
            assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_the_words_and_widths_the_migration_copies_are_the_ones_the_code_holds() -> None:
    """Delete this and a third kind of draft, or a sixth act, is refused by the database after
    passing every test that only exercised Python."""
    m = module()
    assert one_of("kind", DraftKind) == m.KINDS
    assert one_of("act", DraftAct) == m.ACTS
    assert tables.AGENT_ID_GRAMMAR == m.AGENT_ID_GRAMMAR
    assert tables.BASE_HASH_IFF_EDIT == m.BASE_HASH_IFF_EDIT
    assert (tables.KIND_CHARS, tables.ACT_CHARS, tables.HASH_CHARS) == (
        m.KIND_CHARS,
        m.ACT_CHARS,
        m.HASH_CHARS,
    )
    assert m.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS
    assert max(len(one.value) for one in DraftAct) <= m.ACT_CHARS
    assert max(len(one.value) for one in DraftKind) <= m.KIND_CHARS


def test_the_application_may_read_and_add_a_row_and_never_change_one() -> None:
    """Insert-only is the absence of two grants, and each table's rows are written in the
    session's own name. Delete this and an UPDATE grant can arrive with a store that "just marks
    the draft published", overwriting who approved it."""
    m = module()
    assert tuple(f"GRANT SELECT, INSERT ON {one} TO brain_app" for one in TABLE_NAMES) == m.GRANTS
    upgrade = squash(rendered("upgrade", MIGRATION))
    for name in TABLE_NAMES:
        assert f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY" in upgrade
    for column in ("owner_id", "saved_by", "actor_id"):
        assert f"WITH CHECK ({column} = current_setting('app.principal_id', true))" in upgrade


def test_every_word_the_triggers_write_is_a_draft_change_about_the_agent() -> None:
    """The draft and revision triggers write their two words, the act trigger writes the act's
    own, and every entry is a `publish` about `agent:<id>`, with no path or value in it.

    Delete this and a trigger can write a word the audit page does not know, or carry the
    document into the longest-kept record there is."""
    m = module()
    functions = " ".join(
        " ".join(one.split())
        for one in (m.DRAFT_TRIGGER_FUNCTION, m.REVISION_TRIGGER_FUNCTION, m.ACT_TRIGGER_FUNCTION)
    )
    written = set(re.findall(r"jsonb_build_object\( ?'change', '(\w+)'", functions))
    assert written == {DraftChange.DRAFTED.value, DraftChange.SAVED.value}
    assert "'change', NEW.act," in functions
    assert {one.value for one in DraftChange} == written | {one.value for one in DraftAct}
    assert functions.count("'publish'") == 2 * 3
    assert "NEW.body" not in functions and "NEW.base_hash" not in functions


# ------------------------------------------------------------------------------ the database
@contextmanager
def through_0149(database: str) -> Iterator[str]:
    """A database built through every migration to head, which includes `0149`."""
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("0149 is built only on the chain CI runs, where every migration is")
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The application's own routes over this database as the application role."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = make_session_factory(built)
            app.state.console_reads = None
            app.state.template_key = KEY
            app.state.tools = tools("ledger")
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


async def post(
    client: httpx.AsyncClient, pid: str, path: str, body: Mapping[str, Any] | None = None
) -> Any:
    return await client.post(f"{API_PREFIX}{path}", json=dict(body or {}), headers=headers(pid))


def publishes(url: str, subject: str) -> list[AuditEntry]:
    return [one for one in entries(url) if one.action.value == "publish" and one.subject == subject]


def test_a_new_agent_is_drafted_approved_by_a_second_person_and_every_step_is_on_the_ledger() -> (
    None
):
    """Start, save, check, ask, approve: the agent's three rows exist, disabled, owned by its
    author; the acts are four rows naming who did each; and the ledger holds one `publish` entry
    per step about the agent, naming the same people, with the chain verifying.

    Delete this and any step can stop reaching its table or the ledger while the route tests over
    memory stay green. **Skips without a server.**"""
    with through_0149("brain_agent_draft_new") as url:

        async def build(client: httpx.AsyncClient) -> tuple[str, str, int]:
            draft = (await post(client, "u_admin", DRAFTS_PATH)).json()
            draft_id = draft["draft_id"]
            saved = await post(
                client,
                "u_admin",
                SAVE_PATH.format(draft_id=draft_id),
                {"document": a_document(), "base": draft["revision"]},
            )
            assert saved.status_code == 200, saved.text
            revision = saved.json()["revision"]
            check = await post(
                client, "u_admin", CHECK_PATH.format(draft_id=draft_id), {"revision": revision}
            )
            assert check.json()["passed"] is True, check.text
            asked = await post(
                client, "u_admin", PUBLISH_PATH.format(draft_id=draft_id), {"revision": revision}
            )
            assert asked.status_code == 202, asked.text
            approved = await post(
                client, "u_prefix", APPROVE_PATH.format(draft_id=draft_id), {"revision": revision}
            )
            assert approved.status_code == 201, approved.text
            return draft_id, draft["agent_id"], revision

        draft_id, agent_id, revision = pressed(url, build)

        assert sql(
            url,
            "SELECT disabled_at IS NOT NULL, owner_id, created_by, capabilities"
            " FROM agent.agent WHERE id = %s",
            agent_id,
        ) == [(True, "u_admin", "u_admin", ["read:invoice.reference"])]
        assert sql(
            url,
            "SELECT template_id, template_version FROM agent.template_instance WHERE id = %s",
            agent_id,
        ) == [(agent_id, 1)]
        assert sql(
            url,
            "SELECT act, actor_id FROM agent.manifest_act WHERE draft_id = %s ORDER BY at, act",
            uuid.UUID(draft_id),
        ) == [
            ("checked", "u_admin"),
            ("requested", "u_admin"),
            ("approved", "u_prefix"),
            ("published", "u_prefix"),
        ]
        assert revision == 2
        steps = publishes(url, f"agent:{agent_id}")
        assert [(one.details["change"], one.actor_id) for one in steps] == [
            ("drafted", "u_admin"),
            ("saved", "u_admin"),
            ("saved", "u_admin"),
            ("checked", "u_admin"),
            ("requested", "u_admin"),
            ("approved", "u_prefix"),
            ("published", "u_prefix"),
        ]
        assert all(re.fullmatch(r"[0-9a-f]{32}", one.ent_hash) for one in steps)
        assert steps[-1].details == {"change": "published", "widened": "true"}
        assert AuditChain(entries(url)).verify() is None


def test_an_edit_published_is_the_next_version_of_the_agents_own_template() -> None:
    """A persona change to a published agent re-pins its instance to version two of its own
    lineage and rewrites the persona, and leaves its owner and state alone.

    Delete this and an edit can write the agent without its version, or rewrite who answers for
    it. **Skips without a server.**"""
    with through_0149("brain_agent_draft_edit") as url:

        async def build(client: httpx.AsyncClient) -> str:
            draft = (await post(client, "u_admin", DRAFTS_PATH)).json()
            nothing = a_document(capabilities=(), tools_allowed=())
            path = SAVE_PATH.format(draft_id=draft["draft_id"])
            revision = (
                await post(client, "u_admin", path, {"document": nothing, "base": 1})
            ).json()["revision"]
            await post(
                client,
                "u_admin",
                CHECK_PATH.format(draft_id=draft["draft_id"]),
                {"revision": revision},
            )
            made = await post(
                client,
                "u_admin",
                PUBLISH_PATH.format(draft_id=draft["draft_id"]),
                {"revision": revision},
            )
            assert made.status_code == 201, made.text
            agent_id = str(made.json()["agent_id"])

            edit = (await post(client, "u_admin", EDIT_PATH.format(agent_id=agent_id))).json()
            changed = {**edit["document"], "persona": PERSONA + " Name the currency."}
            number = (
                await post(
                    client,
                    "u_admin",
                    SAVE_PATH.format(draft_id=edit["draft_id"]),
                    {"document": changed, "base": edit["revision"]},
                )
            ).json()["revision"]
            await post(
                client,
                "u_admin",
                CHECK_PATH.format(draft_id=edit["draft_id"]),
                {"revision": number},
            )
            published = await post(
                client,
                "u_admin",
                PUBLISH_PATH.format(draft_id=edit["draft_id"]),
                {"revision": number},
            )
            assert published.status_code == 201, published.text
            return agent_id

        agent_id = pressed(url, build)

        assert sql(
            url,
            "SELECT template_id, template_version FROM agent.template_instance WHERE id = %s",
            agent_id,
        ) == [(agent_id, 2)]
        assert sql(
            url,
            "SELECT persona, owner_id, disabled_at IS NOT NULL FROM agent.agent WHERE id = %s",
            agent_id,
        ) == [(PERSONA + " Name the currency.", "u_admin", True)]
        changes = [one.details["change"] for one in publishes(url, f"agent:{agent_id}")]
        assert changes.count("published") == 2
        assert changes.count("drafted") == 2
        assert AuditChain(entries(url)).verify() is None


def test_a_row_naming_somebody_else_is_refused_and_no_row_can_be_changed_or_removed() -> None:
    """The session's principal is the only name a row may carry, and there is no UPDATE or DELETE.

    Delete this and a revision can say somebody else saved it, or an approval can be rewritten to
    name nobody. **Skips without a server.**"""
    with through_0149("brain_agent_draft_policy") as url:

        async def start(client: httpx.AsyncClient) -> str:
            return str((await post(client, "u_admin", DRAFTS_PATH)).json()["draft_id"])

        draft_id = pressed(url, start)

        def as_app(principal: str, statement: str, *values: object) -> None:
            with psycopg.connect(url, autocommit=True) as conn:
                conn.execute("SET ROLE brain_app")
                conn.execute("SELECT set_config(%s, %s, false)", (PRINCIPAL_SETTING, principal))
                conn.execute(statement, values)

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            as_app(
                "u_admin",
                "INSERT INTO agent.manifest_revision (draft_id, number, body, saved_by)"
                " VALUES (%s, 2, '{}', 'u_other')",
                draft_id,
            )
        for statement in (
            "UPDATE agent.manifest_revision SET saved_by = 'u_other' WHERE draft_id = %s",
            "DELETE FROM agent.manifest_revision WHERE draft_id = %s",
            "UPDATE agent.manifest_draft SET owner_id = 'u_other' WHERE id = %s",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                as_app("u_admin", statement, draft_id)
        as_app(
            "u_admin",
            "INSERT INTO agent.manifest_revision (draft_id, number, body, saved_by)"
            " VALUES (%s, 2, '{}', 'u_admin')",
            draft_id,
        )
        assert sql(
            url,
            "SELECT count(*) FROM agent.manifest_revision WHERE draft_id = %s",
            uuid.UUID(draft_id),
        ) == [(2,)]


def test_a_downgrade_keeps_the_entries_and_an_upgrade_builds_the_tables_again() -> None:
    """Delete this and the downgrade can fail, or take the ledger's record of a draft with it.
    **Skips without a server.**"""
    with through_0149("brain_agent_draft_downgrade") as url:

        async def start(client: httpx.AsyncClient) -> None:
            await post(client, "u_admin", DRAFTS_PATH)

        pressed(url, start)
        before = len([one for one in entries(url) if one.action.value == "publish"])
        name = "brain_agent_draft_downgrade"
        migrate(name, "downgrade", str(module().down_revision))
        assert sql(url, "SELECT to_regclass('agent.manifest_draft')") == [(None,)]
        assert len([one for one in entries(url) if one.action.value == "publish"]) == before == 2
        migrate(name, "upgrade", "head")
        assert sql(url, "SELECT count(*) FROM agent.manifest_draft") == [(0,)]


def test_a_publish_sent_back_is_one_row_and_one_entry_and_makes_no_agent() -> None:
    """The second person declines: a `declined` act naming them, one `publish` entry saying so,
    and no agent row. Delete this and sending back could publish, or leave nothing to show who
    refused it. **Skips without a server.**"""
    with through_0149("brain_agent_draft_decline") as url:

        async def build(client: httpx.AsyncClient) -> tuple[str, str]:
            draft = (await post(client, "u_admin", DRAFTS_PATH)).json()
            path = SAVE_PATH.format(draft_id=draft["draft_id"])
            revision = (
                await post(client, "u_admin", path, {"document": a_document(), "base": 1})
            ).json()["revision"]
            body = {"revision": revision}
            await post(client, "u_admin", CHECK_PATH.format(draft_id=draft["draft_id"]), body)
            await post(client, "u_admin", PUBLISH_PATH.format(draft_id=draft["draft_id"]), body)
            declined = await post(
                client, "u_prefix", DECLINE_PATH.format(draft_id=draft["draft_id"]), body
            )
            assert declined.status_code == 200, declined.text
            return str(draft["draft_id"]), str(draft["agent_id"])

        draft_id, agent_id = pressed(url, build)

        assert sql(url, "SELECT count(*) FROM agent.agent WHERE id = %s", agent_id) == [(0,)]
        assert sql(
            url,
            "SELECT actor_id FROM agent.manifest_act WHERE draft_id = %s AND act = 'declined'",
            uuid.UUID(draft_id),
        ) == [("u_prefix",)]
        last = publishes(url, f"agent:{agent_id}")[-1]
        assert (last.details["change"], last.actor_id) == ("declined", "u_prefix")
        assert AuditChain(entries(url)).verify() is None
