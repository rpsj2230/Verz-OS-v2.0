"""`0159`, `0159b`'s backfill of where every agent answered, and the web page switched on in the
write that makes an agent.

The migration is read as rendered SQL without a server, as `tests/unit/test_tables.py` reads every
migration. The backfill is run for real: a database migrated to the revision before `0159`, agents
written into it, then `0159` run over them, so what is asserted is what an install upgrading from
the previous release gets. The install and the draft publish are driven through their own stores as
the application role, so `0159`'s insert policy is the one an install has. **The server half skips
when there is no server**, and CI always has one.

Task ids: M39.2.4.1, M39.2.4.2
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.agent_roster import agent_channels_for, agent_roster_for
from brain.agents.creation import install_draft
from brain.agents.install import InstallDraft
from brain.agents.install_store import StoredAgentInstalls, prepared
from brain.agents.model import AgentAudience
from brain.agents.template import (
    ManifestAuthority,
    ManifestIdentity,
    SignedManifest,
    TemplateManifest,
    publish,
)
from brain.api_routes import DEFAULT_AGENT, Answering, roster_of
from brain.builder.agent_drafts import Act, AgentDraft
from brain.builder.draft_store import Attribution, StoredAgentDrafts
from brain.builder.draft_words import DraftAct, DraftKind
from brain.builder.drafts import FIRST_REVISION, ManifestDraft, Revision
from brain.channels.adapter import channel_wires
from brain.core.entitlement import EntitlementSet
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.db import metadata
from brain.gate.addressing import from_mention
from brain.gate.context import Channel
from brain.gate.select import SelectionStage, select_agent
from brain.knowledge.visibility import Visibility
from brain.session import make_session_factory
from brain.tables import channel_switch as table_module
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of
from brain.tools.registry import ToolRegistry
from tests.e2e.test_wave_three_installed_agent import SIGNING_KEY, serving
from tests.fixtures.retirable import EXTENSIONS, has_pgvector, predecessor, retirable
from tests.fixtures.scratch_postgres import drop, fresh, migrate, run, sql
from tests.unit.test_agent_install_store import tools
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries
from tests.unit.test_tables import DIALECT, VERSIONS, as_amended, migration_module, rendered, squash

MIGRATION = VERSIONS / "0159_channel_switches.py"
BACKFILL = VERSIONS / "0159b_channels_for_existing_agents.py"
MIGRATION_0149 = VERSIONS / "0149_agent_manifest_draft.py"

AGENT_COLUMNS = (
    "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id, department,"
    " scope, capabilities, allowed_tools, required_tools, max_side_effect, created_by)"
    " VALUES (%s, %s, 'Answer briefly.', 'main', 'company', 'u_steward', NULL,"
    " '{\"clauses\": []}', '{}', '{}', '{}', 'none', 'u_steward')"
)


#: A chat this install connected: its record, on or off, as the channel set-up writes it.
CONNECTED = (
    "INSERT INTO ops.channel (channel, enabled, tenant, secret_path, secret_role, updated_by)"
    " VALUES (%s, %s, '{}', %s, 'application', 'u_admin')"
)
PERSON = (
    "INSERT INTO auth.principal (id, kind, employment, display_name)"
    " VALUES (%s, 'human', 'staff', 'Owner')"
)
#: A service account, which asks `/answer` with no session and so on the API.
SERVICE_ACCOUNT = (
    "INSERT INTO auth.service_account (client_id, owner_principal_id, ceiling, not_after,"
    " created_by) VALUES (%s, %s, ARRAY['read:note'], now() + interval '1 day', 'u_admin')"
)


# ------------------------------------------------------------------------- the migration
def test_0159_holds_the_widths_words_and_vocabulary_the_model_holds() -> None:
    """`0159` copies the widths, the patterns, the channel vocabulary and the backfill's reason.
    Delete this and a channel added to the enum is refused by the database on the first switch, or
    the backfill's reason drifts from the one the module names."""
    migration = migration_module(MIGRATION)

    assert migration.TABLES == ("agent.channel_switch",)
    assert migration.AGENT_ID_CHARS == table_module.AGENT_ID_CHARS
    assert migration.CHANNEL_CHARS == table_module.CHANNEL_CHARS
    assert migration.TRACE_ID_CHARS == table_module.TRACE_ID_CHARS
    assert migration.REASON_CHARS == table_module.REASON_CHARS
    assert migration.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS
    assert migration.ENT_HASH_PATTERN == table_module.ENT_HASH_PATTERN
    assert migration.REASON_PATTERN == table_module.REASON_PATTERN
    assert one_of("channel", Channel) == migration.CHANNELS
    backfill = migration_module(BACKFILL)
    assert backfill.down_revision == migration.revision == "0159"
    assert backfill.WEB == table_module.WEB_PAGE.value == Channel.CONSOLE.value
    assert backfill.BACKFILL_REASON == table_module.ANSWERED_HERE_BEFORE_CHANNELS_EXISTED
    assert backfill.BACKFILL_ACTOR == table_module.BACKFILLED_BY == f"migration.{backfill.revision}"
    assert Channel.API.value == backfill.API
    assert tuple(sorted(one.value for one in channel_wires())) == backfill.RECEIVING_CHANNELS


def test_0159_builds_the_table_as_the_model_declares_and_the_act_column_it_claims() -> None:
    """Compared as rendered DDL: the table and its index as the model declares them, row-level
    security on, SELECT and INSERT only in the session's own name, the ledger trigger, the backfill,
    and the one column `AMENDS_CREATE_TABLE` says it adds to `0149`'s acts. Delete this and the
    model can gain a column the database never has, an UPDATE grant ships, or the amendment the
    comparison trusts claims a column the upgrade never adds."""
    emitted = squash(rendered("upgrade", MIGRATION))
    table = metadata.tables["agent.channel_switch"]
    principal = "current_setting('app.principal_id', true)"

    assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted
    for index in table.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted
    assert "ALTER TABLE agent.channel_switch ENABLE ROW LEVEL SECURITY" in emitted
    assert "GRANT SELECT, INSERT ON agent.channel_switch TO brain_app" in emitted
    assert "UPDATE ON agent.channel_switch" not in emitted
    assert "DELETE ON agent.channel_switch" not in emitted
    assert (
        "CREATE POLICY channel_switch_made_in_the_sessions_name ON agent.channel_switch "
        f"FOR INSERT TO brain_app WITH CHECK (changed_by = {principal})"
    ) in emitted
    assert (
        "CREATE TRIGGER channel_switch_is_audited AFTER INSERT ON agent.channel_switch "
        "FOR EACH ROW EXECUTE FUNCTION agent.record_channel_switch()"
    ) in emitted
    assert squash(migration_module(BACKFILL).BACKFILL) in squash(rendered("upgrade", BACKFILL))
    assert squash(migration_module(BACKFILL).UNDONE) in squash(rendered("downgrade", BACKFILL))
    assert "INSERT INTO" not in emitted
    assert (
        "ALTER TABLE agent.manifest_act ADD COLUMN on_the_web BOOLEAN DEFAULT true NOT NULL"
    ) in emitted
    acts = metadata.tables["agent.manifest_act"]
    assert squash(str(CreateTable(acts).compile(dialect=DIALECT))) in as_amended(
        rendered("upgrade", MIGRATION_0149)
    )
    down = squash(rendered("downgrade", MIGRATION))
    assert "DROP TABLE agent.channel_switch" in down
    assert "DROP FUNCTION agent.record_channel_switch()" in down
    assert "ALTER TABLE agent.manifest_act DROP COLUMN on_the_web" in down


# ------------------------------------------------------------------------- on a server
@pytest.fixture
def before_0159() -> Iterator[tuple[str, str]]:
    """A database at the revision `0159` follows, and its name, dropped afterwards."""
    name = f"brain_channel_backfill_{uuid.uuid4().hex[:8]}"
    url = fresh(name)
    try:
        if not has_pgvector(url):
            pytest.skip("the full chain needs pgvector, which CI's server has")
        for extension in EXTENSIONS:
            sql(url, f'CREATE EXTENSION IF NOT EXISTS "{extension}"')
        migrate(name, "stamp", "0001")
        migrate(name, "upgrade", predecessor(MIGRATION))
        yield name, url
    finally:
        drop(name)


def test_on_an_install_with_nothing_connected_every_existing_agent_keeps_the_web_page_alone(
    before_0159: tuple[str, str],
) -> None:
    """**Nothing that answered stops answering.** On an install that connected no chat and whose
    only service account is retired, every agent written before the upgrade, archived included,
    gets one switch turning the web page on, by the migration and for the named reason, and one
    `compose_change` entry about it naming the channels, the web page and the direction; nothing
    else is switched on; an agent written afterwards gets none; and every act already taken reads
    as on the web.

    Delete this and an upgrade can leave every existing agent answering nowhere, switch on a
    surface nothing reached it through, switch them on with nothing on the ledger, or switch on an
    agent made after it ran."""
    name, url = before_0159
    for agent_id in ("sales_desk", "help_desk", "old_desk"):
        sql(url, AGENT_COLUMNS, agent_id, agent_id.replace("_", " ").title())
    sql(url, "UPDATE agent.agent SET archived_at = now() WHERE id = 'old_desk'")
    sql(url, PERSON, "u_owner")
    sql(url, SERVICE_ACCOUNT, "svc_retired", "u_owner")
    sql(url, "UPDATE auth.service_account SET deleted_at = now() WHERE client_id = 'svc_retired'")

    migrate(name, "upgrade", "head")
    sql(url, AGENT_COLUMNS, "new_desk", "New desk")

    switches = sql(
        url,
        "SELECT agent_id, channel, switched_on, changed_by, reason_code FROM agent.channel_switch"
        " ORDER BY agent_id",
    )
    reason = "answered_here_before_channels_existed"
    assert switches == [
        (agent_id, "console", True, "migration.0159b", reason)
        for agent_id in ("help_desk", "old_desk", "sales_desk")
    ]
    ledgered = entries(url, "compose_change")
    assert sorted(
        (one.actor_id, one.subject, dict(one.details)["part"], dict(one.details)["reference"])
        for one in ledgered
    ) == [
        ("migration.0159b", f"agent:{agent_id}", "channels", "console")
        for agent_id in ("help_desk", "old_desk", "sales_desk")
    ]
    assert {dict(one.details)["direction"] for one in ledgered} == {"attached"}
    assert sql(
        url,
        "SELECT column_default FROM information_schema.columns"
        " WHERE table_schema = 'agent' AND table_name = 'manifest_act'"
        " AND column_name = 'on_the_web'",
    ) == [("true",)]


def test_an_agent_reached_by_a_mention_on_a_connected_chat_before_the_upgrade_is_reached_after(
    before_0159: tuple[str, str],
) -> None:
    """**Nothing that answers today stops answering, on any install.** Before the upgrade a message
    on a connected Lark opening with `@sales_desk` reached that agent, and so did the API for a
    service account. After it, every existing agent is switched on for the web page, for every
    connected chat this release receives on (a connected chat switched off included, because it
    answers again the moment it is switched back on) and for the API, each with one ledger entry;
    and the answer route's own readers, asked on Lark with the mention read by `from_mention`,
    still select that agent. A chat nobody connected is switched on for nobody.

    Delete this and the upgrade can silently stop every agent answering in the chat the owner uses,
    which is the rule the upgrade exists to keep."""
    name, url = before_0159
    for agent_id in ("sales_desk", "help_desk"):
        sql(url, AGENT_COLUMNS, agent_id, agent_id.replace("_", " ").title())
    for channel, on in (("lark", True), ("webhook", False)):
        sql(url, CONNECTED, channel, on, f"providers/channel_{channel}")
    sql(url, PERSON, "u_owner")
    sql(url, SERVICE_ACCOUNT, "svc_reporting", "u_owner")

    migrate(name, "upgrade", "head")

    switches = sql(
        url,
        "SELECT agent_id, channel, changed_by, reason_code FROM agent.channel_switch"
        " WHERE switched_on ORDER BY agent_id, channel",
    )
    assert switches == [
        (agent_id, channel, "migration.0159b", "answered_here_before_channels_existed")
        for agent_id in ("help_desk", "sales_desk")
        for channel in ("api", "console", "lark", "webhook")
    ]
    ledgered = [one for one in entries(url, "compose_change") if one.actor_id == "migration.0159b"]
    assert len(ledgered) == len(switches)

    person = Principal(
        id="u_reader", kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name="Reader"
    )
    reach = EntitlementSet(principal_id="u_reader")

    async def selected(channel: Channel, text: str) -> tuple[SelectionStage, str]:
        built = app_engine(url)
        try:
            sessions = make_session_factory(built)
            state = SimpleNamespace(
                agent_roster=agent_roster_for(sessions), agent_channels=agent_channels_for(sessions)
            )
            asked = Answering(principal=person, reach=reach, channel=channel, now=AT)
            roster = await roster_of(state, asked, ToolRegistry())
            address = from_mention(text)
            chosen = select_agent(
                address.question,
                channel,
                visible_agents=roster.visible,
                default_agent=DEFAULT_AGENT,
                addressed=address.agent_id,
            )
            return chosen.stage, chosen.agent_id
        finally:
            await built.dispose()

    assert run(lambda: selected(Channel.LARK, "@sales_desk what is on this week")) == (
        SelectionStage.ADDRESSED,
        "sales_desk",
    )
    assert run(lambda: selected(Channel.SLACK, "@sales_desk what is on this week")) == (
        SelectionStage.DEFAULT,
        DEFAULT_AGENT,
    )


#: Far from any wall clock, for CLAUDE.md's reason.
AT = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
AUTHOR = "u_author"
AUDIENCE = AgentAudience(level=Visibility.PERSONAL, owner_id=AUTHOR)


def signed_as(template_id: str) -> SignedManifest:
    """A template with nothing to answer, bind or reach, signed for this file alone."""
    return publish(
        TemplateManifest(
            identity=ManifestIdentity(
                template_id=template_id, version=1, published_by=AUTHOR, display_name="Desk"
            ),
            persona="Answers a channel switch test and nobody else.",
            authority=ManifestAuthority(scope=Scope.unrestricted(), capabilities=()),
        ),
        key=SIGNING_KEY,
        signed_by=AUTHOR,
        at=AT,
    )


def made(signed: SignedManifest, agent_id: str) -> InstallDraft:
    return install_draft(signed, agent_id=agent_id, maker_id=AUTHOR, display_name=None)


@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_channel_made_{uuid.uuid4().hex[:8]}") as url:
        yield url


def test_an_install_and_a_publish_switch_the_web_page_on_in_the_write_that_makes_the_agent(
    database: str,
) -> None:
    """**M39.2.4.1 in the create flow, on PostgreSQL.** An install asked to switches the web page on
    in its own transaction, in the installer's name, and one not asked to writes no switch; a draft
    publish asked to does the same in the publisher's name. Each switch is one ledger entry.

    Delete this and an agent made with the web page ticked answers nowhere, because the write the
    route asked for was refused by the insert policy or never made."""
    by = Attribution(actor_id=AUTHOR, ent_hash="e" * 32, trace_id="channel-switch-made")

    async def go() -> None:
        built = app_engine(database)
        try:
            sessions = make_session_factory(built)
            installs = StoredAgentInstalls(sessions)
            template = signed_as("desk_template")
            for agent_id, web in (("installed_desk", True), ("quiet_desk", False)):
                await installs.finish(
                    made(template, agent_id),
                    key=SIGNING_KEY,
                    audience=AUDIENCE,
                    registry=serving(()),
                    tools=tools(),
                    at=AT,
                    ent_hash=by.ent_hash,
                    trace_id=by.trace_id,
                    on_the_web=web,
                )
            drafts = StoredAgentDrafts(sessions)
            draft = AgentDraft(
                draft=ManifestDraft(draft_id=str(uuid.uuid4()), owner_id=AUTHOR, created_at=AT),
                agent_id="drafted_desk",
                kind=DraftKind.NEW,
                base_hash=None,
            )
            first = Revision(
                draft_id=draft.draft_id,
                number=FIRST_REVISION,
                body="{}",
                saved_by=AUTHOR,
                saved_at=AT,
            )
            await drafts.start(draft, first, by=by)
            done = Act(
                revision=FIRST_REVISION,
                act=DraftAct.PUBLISHED,
                actor_id=AUTHOR,
                at=AT,
                on_the_web=True,
            )
            drafted = signed_as("drafted_desk")
            installation = prepared(
                made(drafted, "drafted_desk"),
                key=SIGNING_KEY,
                audience=AUDIENCE,
                registry=serving(()),
                tools=tools(),
                at=AT,
            )
            written = await drafts.publish_new(
                draft.draft_id,
                (done,),
                drafted,
                installation,
                by=by,
                on_the_web=True,
            )
            assert written
        finally:
            await built.dispose()

    run(go)

    switches = sql(
        database,
        "SELECT agent_id, channel, switched_on, changed_by, reason_code FROM agent.channel_switch"
        " WHERE changed_by = %s ORDER BY agent_id",
        AUTHOR,
    )
    assert switches == [
        ("drafted_desk", "console", True, AUTHOR, table_module.SWITCHED_ON_WHEN_PUBLISHED),
        ("installed_desk", "console", True, AUTHOR, table_module.SWITCHED_ON_WHEN_MADE),
    ]
    assert sql(
        database, "SELECT on_the_web FROM agent.manifest_act WHERE actor_id = %s", AUTHOR
    ) == [(True,)]
    ledgered = [one for one in entries(database, "compose_change") if one.actor_id == AUTHOR]
    assert sorted((one.subject, dict(one.details)["part"]) for one in ledgered) == [
        ("agent:drafted_desk", "channels"),
        ("agent:installed_desk", "channels"),
    ]
