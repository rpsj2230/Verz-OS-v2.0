"""The console's knobs followed to the row, the ledger entry and the behaviour, against PostgreSQL.

`docs/console-audit.md` measures, for every write the console sends, whether a test follows it to
the row it writes, the audit entry it leaves and the behaviour it changes. On 2026-09-17 a feature
switch, the three job controls, an instruction edit and its give-back, a rung save and the three
webhook changes left no entry at all, and a grant written or removed from the People screen had
only ever been asserted against a stub session. `0059` is the triggers; this file is the proof.

**The first half needs no server.** It reads each trigger function off the migration that runs it
and holds its subject, its change words, its actor and its details to the `AuditRecorder` method
that writes the same entry, and holds that no trigger puts a value in the ledger: not a setting's
value, not a rung's numbers, not an agent's instructions.

**The second half presses the controls over HTTP**, through the application's own routes, signed in
as a person with the grants the screen asks for, against a database built through the migrations
that ship and connected as the application role, so every row-level security policy applies. Each
test then reads the row as the superuser, the ledger as `AuditEntry`s and verifies the chain, and
reads the behaviour through the function that consumes the row: the tick's choice of what to start,
the prompt a run would be given, and the reach the resolver returns for the holder. **It skips
without a server**, which is CI's to provide; a server without pgvector builds the tables these
triggers sit on by running their own migrations out of order, which `through_0059` states.

The webhook changes are driven through `brain.ops.webhook_store.StoredWebhooks`, the store the
routes call, as `tests/unit/test_retention_audit.py` drives the retention writes: the routes also
need a vault to keep a signing secret in, which a store test hands a function and an HTTP test
would have to stand up. A legal hold placed and lifted through the store is followed to the sweep
that honours it the same way.

Task ids: M27.8.17
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from brain.agents.model import AgentAudience
from brain.agents.template import FieldOwner, TemplateInstance, materialise
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.audit.ledger import AuditChain, AuditEntry, LegalHold
from brain.audit.record import (
    INFERRED_ACTOR,
    AuditRecorder,
    InstructionsChange,
    RoutingChange,
    SettingChange,
)
from brain.console.reads import Plane, plane_capability
from brain.console.scoped_authority import REACH_AUTHORITY
from brain.console.screens import screen
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.db import normalise_database_url
from brain.feature_routes import FEATURE_AUTHORITY
from brain.gate.entitlement_store import StoredEntitlements
from brain.gate.prefix import build_prefix
from brain.jobs_routes import SCHEDULE_AUTHORITY
from brain.knowledge.visibility import Visibility
from brain.ops.features import SCHEDULE_CONTROL, is_on
from brain.ops.retention import sweep
from brain.ops.retention_store import active_holds, lift_hold, place_hold
from brain.ops.schedule import Owed
from brain.ops.schedule_control import Chosen, chosen_this_tick, paused_controls, run_requests
from brain.ops.webhook_store import StoredWebhooks
from brain.prompt_routes import (
    INSTRUCTIONS_AUTHORITY,
    THE_INSTALL_IS_LOCKED_BEFORE_IT_IS_READ,
    one_agent_locked,
    one_install_locked,
)
from brain.routing_routes import MATRIX_READ, MATRIX_WRITE
from brain.session import make_session_factory
from brain.tables.webhook_change import WebhookChange
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import engine, migrate, run, sql
from tests.unit.test_agent_routes import agent_row, install_rows
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_credential_writes import entries
from tests.unit.test_entitlement_store import a_principal
from tests.unit.test_retention_store import OLD, YOUNG, a_sweeper, remaining
from tests.unit.test_retention_store import server as server  # the fixture, by its name
from tests.unit.test_routing_routes import rung
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash
from tests.unit.test_webhook_store import a_subscriber, kept

MIGRATION = VERSIONS / "0059_console_controls_audit.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
AT = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
FAR_OFF = datetime(2999, 1, 1, tzinfo=UTC)

#: The reach digest a recorder is built with. Entries are compared on everything else.
UNSUPPLIED = "0" * 32

#: A wired job that is not destructive, as `tests/unit/test_console_controls_reach_behaviour.py`.
REFRESH = "spend_report_refresh"
COMPANY_AGENT = "pricing_desk"
EDITED = "Answer in two sentences and always name the price list and its date."
GRANTED = "read:client.name"
MAINTENANCE = "maintenance"
EVERYWHERE = Scope.unrestricted()


def recorder(actor: str = "u_admin") -> AuditRecorder:
    return AuditRecorder(
        AuditChain(), actor_id=actor, ent_hash=UNSUPPLIED, trace_id="t", clock=lambda: AT
    )


def function(name: str) -> str:
    """One trigger function as the migration executes it, whitespace collapsed."""
    return " ".join(getattr(migration_module(MIGRATION), name).split())


def words(body: str, variable: str = "v_changes") -> list[str]:
    """Each change word a trigger appends to its list, in the order written."""
    return re.findall(rf"{variable} := {variable} \|\| '(\w+)'::text;", body)


# ------------------------------------------------------------------ the triggers' shape


def test_the_setting_trigger_writes_the_recorders_words_its_writer_and_never_the_value() -> None:
    """Delete this and `0059`'s trigger on `ops.setting` can drift from `AuditRecorder.setting`: a
    word the enum lacks, an actor other than the row's own `updated_by`, or, the one that cannot be
    taken back, the value itself written into the table kept longest."""
    body = function("SETTING_TRIGGER_FUNCTION")

    assert sorted(words(body)) == sorted(one.value for one in SettingChange)
    assert "v_subject text := 'setting:' || NEW.key;" in body
    assert "v_details := jsonb_build_object('change', v_changes[i]);" in body
    assert "v_seq, v_at, NEW.updated_by, 'setting', v_subject, v_ent_hash," in body
    assert "OLD.value IS DISTINCT FROM NEW.value;" in body
    assert "v_retired := OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL;" in body
    assert "jsonb_build_object('value'" not in body and "NEW.value)" not in body
    switched = recorder().setting(key="feature.prompt_editing", change=SettingChange.SWITCHED_ON)
    assert (switched.subject, dict(switched.details)) == (
        "setting:feature.prompt_editing",
        {"change": "switched_on"},
    )


def test_the_routing_trigger_names_the_columns_that_moved_and_marks_an_actor_nobody_named() -> None:
    """Delete this and the rung trigger can record the numbers rather than the names of the columns,
    stop excluding the row's own instants so every save reads as a change of `updated_at`, or
    attribute an operator's statement to nobody without saying so."""
    body = function("ROUTING_TRIGGER_FUNCTION")
    module = migration_module(MIGRATION)

    assert sorted(set(words(body))) == sorted(one.value for one in RoutingChange)
    assert module.ROUTING_COLUMNS_NOT_RECORDED == ("id", "created_at", "updated_at", "deleted_at")
    assert "moved.key <> ALL (ARRAY['id', 'created_at', 'updated_at', 'deleted_at'])" in body
    assert "SELECT string_agg(moved.key, ',' ORDER BY moved.key) INTO v_fields" in body
    assert "v_actor := COALESCE(v_supplied, session_user::text);" in body
    assert (
        f"IF v_supplied IS NULL THEN v_details := v_details || "
        f"jsonb_build_object('actor', '{INFERRED_ACTOR}');"
    ) in body
    changed = recorder().routing(
        rung_id="3c2b1a09-8f7e-4d6c-9b5a-1e2d3c4b5a69",
        change=RoutingChange.CHANGED,
        fields=("timeout_seconds", "attempts"),
        actor_inferred=True,
    )
    assert dict(changed.details) == {
        "change": "changed",
        "fields": "attempts,timeout_seconds",
        "actor": "inferred",
    }


def test_the_instructions_trigger_fires_on_the_persona_alone_and_records_a_digest_not_words() -> (
    None
):
    """Delete this and the instructions trigger can fire on every overlay edit or upgrade, take a
    give-back's actor from an owner the give-back just removed, or put the instructions themselves
    into the ledger where `effective_hash` was meant to stand for them."""
    body = function("INSTRUCTIONS_TRIGGER_FUNCTION")

    assert re.findall(r"v_change := '(\w+)';", body) == [one.value for one in InstructionsChange]
    assert (
        "IF (OLD.overlay -> 'persona') IS NOT DISTINCT FROM (NEW.overlay -> 'persona') THEN "
        "RETURN NULL;"
    ) in body
    assert "v_actor := NEW.field_owners -> 'persona' ->> 'set_by';" in body
    assert (
        "v_details := jsonb_build_object('change', v_change, 'config_hash', NEW.effective_hash);"
    ) in body
    assert "->> 'persona'" not in body
    edited = recorder().instructions(
        agent_id=COMPANY_AGENT, change=InstructionsChange.EDITED, config_hash="e" * 64
    )
    assert (edited.subject, dict(edited.details)) == (
        f"agent:{COMPANY_AGENT}",
        {"change": "edited", "config_hash": "e" * 64},
    )


def test_the_webhook_trigger_writes_one_entry_per_change_row_with_its_own_author() -> None:
    """Delete this and the webhook trigger can drift from `AuditRecorder.webhook`, or read the
    subscriber's endpoint into the entry, which is where the company's identifiers are sent."""
    body = function("WEBHOOK_TRIGGER_FUNCTION")

    assert "v_subject text := 'webhook:' || NEW.subscriber_id;" in body
    assert "v_details jsonb := jsonb_build_object('change', NEW.change);" in body
    assert "v_seq, v_at, NEW.changed_by, 'webhook', v_subject, v_ent_hash," in body
    assert "endpoint" not in body and "secret" not in body
    for change in WebhookChange:
        entry = recorder().webhook(subscriber_id="billing_bridge", change=change)
        assert (entry.subject, dict(entry.details)) == (
            "webhook:billing_bridge",
            {"change": change.value},
        )


def test_each_trigger_is_created_on_the_statements_it_judges() -> None:
    """Delete this and a trigger created on INSERT alone records a setting's first value and never
    a pause, or one on the webhook table fires on an update nothing makes."""
    emitted = squash(rendered("upgrade", MIGRATION))

    for trigger in (
        "CREATE TRIGGER setting_is_audited AFTER INSERT OR UPDATE ON ops.setting FOR EACH ROW "
        "EXECUTE FUNCTION ops.record_setting_change()",
        "CREATE TRIGGER routing_rung_is_audited AFTER INSERT OR UPDATE ON ops.routing_rung FOR "
        "EACH ROW EXECUTE FUNCTION ops.record_routing_change()",
        "CREATE TRIGGER instructions_are_audited AFTER UPDATE ON agent.template_instance FOR EACH "
        "ROW EXECUTE FUNCTION agent.record_instructions_change()",
        "CREATE TRIGGER webhook_change_is_audited AFTER INSERT ON ops.webhook_change FOR EACH ROW "
        "EXECUTE FUNCTION ops.record_webhook_change()",
    ):
        assert trigger in emitted


def test_a_recorded_rung_change_names_its_columns_and_nothing_else_does() -> None:
    """The positive and negative halves of `AuditRecorder.routing`'s one rule. Delete this and a
    changed rung can be recorded with no columns, or an added one with a list that says nothing."""
    assert recorder().routing(rung_id="r_1", change=RoutingChange.ADDED).details == {
        "change": "added"
    }
    for change, fields in (
        (RoutingChange.CHANGED, ()),
        (RoutingChange.ADDED, ("attempts",)),
        (RoutingChange.RETIRED, ("enabled",)),
    ):
        try:
            recorder().routing(rung_id="r_1", change=change, fields=fields)
        except ValueError:
            continue
        raise AssertionError(f"{change} with {fields} was recorded")


def test_an_instructions_entry_refuses_anything_but_a_configuration_digest() -> None:
    """Delete this and an entry could carry a hash the ledger stores as the marker, which says
    nothing about which configuration was put in force."""
    for bad in ("", "E" * 64, "e" * 63):
        try:
            recorder().instructions(
                agent_id=COMPANY_AGENT, change=InstructionsChange.EDITED, config_hash=bad
            )
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} was recorded")


def test_an_instruction_edit_locks_the_install_alone_and_then_reads_it_with_the_agent_locked() -> (
    None
):
    """Found by the database test below on its first run: `one_agent_locked` asked for `FOR UPDATE
    OF agent, template_instance` over an outer join, which PostgreSQL refuses, so every edit and
    give-back failed on every install while the stub tests passed. Delete this and the lock can go
    back into the join, or come out of the route altogether, which is the silent overwrite
    `THE_INSTALL_IS_LOCKED_BEFORE_IT_IS_READ` describes; the database test catches the first and
    only this catches the second."""
    dialect = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
    install = str(one_install_locked(COMPANY_AGENT).compile(dialect=dialect))
    joined = str(one_agent_locked(COMPANY_AGENT).compile(dialect=dialect))

    assert install.startswith("SELECT agent.template_instance.id")
    assert install.endswith("FOR UPDATE")
    assert joined.endswith("FOR UPDATE OF agent")
    assert "LEFT OUTER JOIN agent.template_instance" in joined
    assert THE_INSTALL_IS_LOCKED_BEFORE_IT_IS_READ.startswith("The install is the nullable side")


# ------------------------------------------------------------------------ the database


@contextmanager
def through_0059(database: str) -> Iterator[str]:
    """A database with `0059` applied.

    With pgvector, which CI has, `retirable` runs every migration to head. Without it, `retirable`
    stops at `0048`; `0049` is run for real, then the migrations that build the four tables
    `0059` puts triggers on and nothing else built, out of order and each after a stamp of its
    predecessor: `0014` and `0016` for the agent and its install, `0025` because `0030` widens the
    control run's name, `0030` for the subscriber and `0053` for its changes. `0054` to `0059`
    then run in order. Nothing between them alters the four tables; `0045`'s policies on
    `ops.setting` and `ops.routing_rung` were already run by `retirable`.
    """
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "upgrade", "0049")
            for predecessor, revision in (
                ("0013", "0014"),
                ("0015", "0016"),
                ("0024", "0025"),
                ("0029", "0030"),
                ("0052", "0053"),
            ):
                migrate(database, "stamp", predecessor)
                migrate(database, "upgrade", revision)
            migrate(database, "upgrade", "0059")
        yield url


def seen(url: str, action: str) -> list[AuditEntry]:
    """Every entry of one action, in chain order."""
    return [one for one in entries(url) if one.action.value == action]


def summary(found: list[AuditEntry]) -> list[tuple[str, str, dict[str, str]]]:
    return [(one.actor_id, one.subject, dict(one.details)) for one in found]


def wanted(*expected: tuple[str, AuditEntry]) -> list[tuple[str, str, dict[str, str]]]:
    return [(actor, one.subject, dict(one.details)) for actor, one in expected]


def pressed[T](
    url: str,
    grants: Mapping[str, tuple[Grant, ...]],
    presses: Callable[[httpx.AsyncClient], Awaitable[T]],
) -> T:
    """The application's own routes, signed in with these grants, over this database as the
    application role. No lifespan runs, so nothing is read from the environment."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.state.gate = gate_wiring(grants)
            app.state.db_sessions = make_session_factory(built)
            app.state.console_reads = None
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def as_application[T](url: str, work: Callable[[Any], Awaitable[T]]) -> T:
    """Read through one session as the application role, the way the consumer of a row reads."""

    async def go() -> T:
        built = app_engine(url)
        try:
            async with make_session_factory(built)() as session:
                return await work(session)
        finally:
            await built.dispose()

    return run(go)


def attributed(found: list[AuditEntry]) -> bool:
    """Whether every entry carries a reach digest and a request's trace rather than the trigger's
    fallbacks, which is what the route's `attributed_to` statements are for."""
    return all(one.ent_hash != UNSUPPLIED and not one.trace_id.startswith("tx.") for one in found)


# --------------------------------------------------------- features and scheduled jobs

JOB_GRANTS = {
    "u_admin": (
        Grant(capability=screen("queue").read.requires, scope=EVERYWHERE),
        Grant(capability=plane_capability(Plane.CONFIGURATION), scope=EVERYWHERE),
        Grant(capability=SCHEDULE_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=FEATURE_AUTHORITY, scope=EVERYWHERE),
    ),
}


def owed(name: str, now: datetime) -> Owed:
    return Owed(name=name, due_since=now, late_by=timedelta(0), first_run=True, report_only=False)


def next_tick(url: str, now: datetime) -> tuple[Chosen, ...]:
    """What the worker's next tick starts, from the rows as the tick reads them."""

    async def read(session: Any) -> tuple[frozenset[str], dict[str, datetime]]:
        return await paused_controls(session), await run_requests(session)

    paused, requested = as_application(url, read)
    return chosen_this_tick(
        (owed(REFRESH, now),), now=now, paused=paused, requested=requested, last_attempt={}
    )


def test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick() -> None:
    """M27.8.17 for the Features screen and the Scheduled jobs screen, pressed over HTTP.

    Switching `schedule_control` on writes its row, one `setting` entry naming the person, the key
    and the direction, and is what `is_on` then reads; pressing it again with the same answer
    writes no second entry. Pause, resume and run now each write their row, one entry, and change
    what the next tick starts. Every entry carries the request's reach digest and trace, which is
    the routes' `attributed_to`, and the chain verifies. Delete this and any of the four controls
    can stop reaching the ledger, or reach it under the wrong key, while every stub test stays
    green. **Skips without a server.**"""
    now = datetime.now(UTC)
    with through_0059("brain_console_audit_jobs") as url:

        async def switch_twice(client: httpx.AsyncClient) -> list[int]:
            path = f"{API_PREFIX}/install/features/schedule_control"
            first = await client.post(path, json={"on": True}, headers=headers("u_admin"))
            again = await client.post(path, json={"on": True}, headers=headers("u_admin"))
            return [first.status_code, again.status_code]

        assert pressed(url, JOB_GRANTS, switch_twice) == [200, 200]
        switched_on = as_application(url, lambda session: is_on(session, SCHEDULE_CONTROL))
        assert Chosen(REFRESH, False, False) in next_tick(url, now)

        def job(action: str) -> Callable[[httpx.AsyncClient], Awaitable[int]]:
            async def press(client: httpx.AsyncClient) -> int:
                path = f"{API_PREFIX}/jobs/{REFRESH}/{action}"
                return (await client.post(path, headers=headers("u_admin"))).status_code

            return press

        assert pressed(url, JOB_GRANTS, job("pause")) == 200
        while_paused = next_tick(url, now)
        assert pressed(url, JOB_GRANTS, job("resume")) == 200
        after_resume = next_tick(url, now)
        assert pressed(url, JOB_GRANTS, job("pause")) == 200
        assert pressed(url, JOB_GRANTS, job("run")) == 200
        asked_while_paused = next_tick(url, datetime.now(UTC) + timedelta(seconds=1))
        rows = sql(
            url,
            "SELECT key, value, updated_by FROM ops.setting WHERE deleted_at IS NULL ORDER BY key",
        )
        found = seen(url, "setting")
        chain = entries(url)

    assert switched_on is True
    assert while_paused == ()
    assert after_resume == (Chosen(REFRESH, False, False),)
    assert asked_while_paused == (Chosen(REFRESH, False, True),)
    assert [(key, updated_by) for key, _, updated_by in rows] == [
        ("feature.schedule_control", "u_admin"),
        (f"schedule.paused.{REFRESH}", "u_admin"),
        (f"schedule.run_requested.{REFRESH}", "u_admin"),
    ]
    assert [value for key, value, _ in rows if key.startswith("schedule.paused")] == [True]
    feature = f"feature.{SCHEDULE_CONTROL.name}"
    paused = f"schedule.paused.{REFRESH}"
    assert summary(found) == wanted(
        ("u_admin", recorder().setting(key=feature, change=SettingChange.SWITCHED_ON)),
        ("u_admin", recorder().setting(key=paused, change=SettingChange.SWITCHED_ON)),
        ("u_admin", recorder().setting(key=paused, change=SettingChange.SWITCHED_OFF)),
        ("u_admin", recorder().setting(key=paused, change=SettingChange.SWITCHED_ON)),
        (
            "u_admin",
            recorder().setting(key=f"schedule.run_requested.{REFRESH}", change=SettingChange.SET),
        ),
    )
    assert attributed(found)
    assert AuditChain(chain).verify() is None


def test_an_operators_statement_on_a_setting_is_recorded_without_its_value() -> None:
    """The trigger's other half, which no route reaches: a statement typed at a prompt. A string
    set, changed, a description edited, and the row retired: three entries, none carrying the
    value, attributed to the row's `updated_by` and marked with the fallback reach and trace.
    Delete this and a hand edit of an installation value can be missed, or recorded with the value
    in it, and nothing else in the suite would notice. **Skips without a server.**"""
    with through_0059("brain_console_audit_statement") as url:
        sql(
            url,
            "INSERT INTO ops.setting (key, value_type, value, description, updated_by) VALUES "
            "('install.company_name', 'string', '\"Example Holdings\"', 'The name', 'u_operator')",
        )
        sql(
            url,
            "UPDATE ops.setting SET value = '\"Example Group\"' WHERE key = 'install.company_name'",
        )
        sql(
            url, "UPDATE ops.setting SET description = 'Renamed' WHERE key = 'install.company_name'"
        )
        sql(url, "UPDATE ops.setting SET deleted_at = now() WHERE key = 'install.company_name'")
        found = seen(url, "setting")
        chain = entries(url)

    key = "install.company_name"
    assert summary(found) == wanted(
        ("u_operator", recorder().setting(key=key, change=SettingChange.SET)),
        ("u_operator", recorder().setting(key=key, change=SettingChange.SET)),
        ("u_operator", recorder().setting(key=key, change=SettingChange.RETIRED)),
    )
    assert all("Example" not in str(one.details) for one in chain)
    assert all(one.ent_hash == UNSUPPLIED and one.trace_id.startswith("tx.") for one in found)
    assert AuditChain(chain).verify() is None


# ---------------------------------------------------------------------- instructions

PROMPT_GRANTS = {
    "u_admin": (
        Grant(capability=tab(Tab.SETTINGS).read.requires, scope=EVERYWHERE),
        Grant(capability=plane_capability(Plane.CONFIGURATION), scope=EVERYWHERE),
        Grant(capability=INSTRUCTIONS_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=FEATURE_AUTHORITY, scope=EVERYWHERE),
    ),
}


def an_installed_agent(url: str) -> None:
    """One company agent, its signed template version and its install, as the superuser."""
    instance_row, version_row, _, _ = install_rows(COMPANY_AGENT)
    built = create_engine(normalise_database_url(url), poolclass=NullPool)
    try:
        with Session(built) as session:
            session.add(version_row)
            session.add(agent_row(COMPANY_AGENT, level=Visibility.COMPANY))
            session.flush()
            session.add(instance_row)
            session.commit()
    finally:
        built.dispose()


def given(url: str) -> tuple[str, str]:
    """What a run of the agent would be given now, from the install as stored, and its hash."""
    [(template_id, version, digest, overlay, owners, effective_hash, created_by)] = sql(
        url,
        "SELECT template_id, template_version, content_digest, overlay, field_owners, "
        "effective_hash, created_by FROM agent.template_instance WHERE id = %s",
        COMPANY_AGENT,
    )
    _, _, signed, _ = install_rows(COMPANY_AGENT)
    instance = TemplateInstance(
        instance_id=COMPANY_AGENT,
        template_id=template_id,
        template_version=version,
        content_digest=digest,
        overlay=overlay,
        overlay_owners={path: FieldOwner.model_validate(one) for path, one in owners.items()},
        created_by=created_by,
    )
    audience = AgentAudience(level=Visibility.COMPANY, owner_id="u_steward")
    effective = materialise(signed, instance, audience=audience)
    assert effective.config_hash == effective_hash
    return build_prefix((), persona=effective.record.persona).text, effective_hash


def test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt() -> (
    None
):
    """M27.8.17 for the Prompts screen's two writes, pressed over HTTP.

    An edit writes the install's overlay, one `instructions` entry about the agent naming the
    editor and the configuration digest now in force, and changes the prompt a run is given. A
    give-back removes the overlay and its owner, writes one entry naming the person who pressed it
    rather than an inferred actor, and the prompt is the template's again. Delete this and either
    write can stop reaching the ledger, or a give-back can be attributed to the database role,
    while the stub tests stay green. **Skips without a server.**"""
    with through_0059("brain_console_audit_prompts") as url:
        an_installed_agent(url)
        before, first_hash = given(url)

        async def edit(client: httpx.AsyncClient) -> tuple[int, int]:
            switched = await client.post(
                f"{API_PREFIX}/install/features/prompt_editing",
                json={"on": True},
                headers=headers("u_admin"),
            )
            edited = await client.post(
                f"{API_PREFIX}/govern/prompts/{COMPANY_AGENT}",
                json={"instructions": EDITED, "expected_hash": first_hash},
                headers=headers("u_admin"),
            )
            return switched.status_code, edited.status_code

        assert pressed(url, PROMPT_GRANTS, edit) == (200, 200)
        after_edit, edit_hash = given(url)

        async def give_back(client: httpx.AsyncClient) -> int:
            response = await client.post(
                f"{API_PREFIX}/govern/prompts/{COMPANY_AGENT}/give-back",
                json={"expected_hash": edit_hash},
                headers=headers("u_admin"),
            )
            return response.status_code

        assert pressed(url, PROMPT_GRANTS, give_back) == 200
        after_give_back, back_hash = given(url)
        [(overlay, persona)] = sql(
            url,
            "SELECT i.overlay, a.persona FROM agent.template_instance i "
            "JOIN agent.agent a ON a.id = i.id WHERE i.id = %s",
            COMPANY_AGENT,
        )
        found = seen(url, "instructions")
        chain = entries(url)

    _, _, signed, _ = install_rows(COMPANY_AGENT)
    assert EDITED in after_edit and EDITED not in before
    assert EDITED not in after_give_back and signed.manifest.persona in after_give_back
    assert "persona" not in overlay and persona == signed.manifest.persona
    assert summary(found) == wanted(
        (
            "u_admin",
            recorder().instructions(
                agent_id=COMPANY_AGENT, change=InstructionsChange.EDITED, config_hash=edit_hash
            ),
        ),
        (
            "u_admin",
            recorder().instructions(
                agent_id=COMPANY_AGENT, change=InstructionsChange.GIVEN_BACK, config_hash=back_hash
            ),
        ),
    )
    assert attributed(found)
    assert all(EDITED not in str(one.details) for one in chain)
    assert AuditChain(chain).verify() is None


# --------------------------------------------------------------------------- routing

ROUTING_GRANTS = {
    "u_admin": (
        Grant(capability=MATRIX_READ, scope=EVERYWHERE),
        Grant(capability=MATRIX_WRITE, scope=EVERYWHERE),
    ),
}


def test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved() -> None:
    """The routing matrix's one write, pressed over HTTP, and the statements around it.

    A rung inserted by an operator is recorded as added, attributed to the database role and
    marked inferred; a save that moves two numbers writes them and one entry naming those two
    columns and the person; the same save again writes no entry; and an operator's statement
    switching the rung off is recorded with its column and the inferred role. Delete this and a
    retuned timeout can reach production with no record of who or when, which is where every rung
    save was before `0059`. **Skips without a server.** What the save changes about an answer is
    not here: nothing on the answer path reads `ops.routing_rung` yet (M27.8.8)."""
    row = rung(attempts=1, timeout_seconds=12.0)
    rung_id = str(row.id)
    with through_0059("brain_console_audit_routing") as url:
        [(role,)] = sql(url, "SELECT session_user")
        built = create_engine(normalise_database_url(url), poolclass=NullPool)
        try:
            with Session(built) as session:
                session.add(row)
                session.commit()
        finally:
            built.dispose()

        body = {"attempts": 2, "timeout_seconds": 20.0, "max_concurrency": 40, "enabled": True}

        async def save_twice(client: httpx.AsyncClient) -> list[int]:
            path = f"{API_PREFIX}/routing/rungs/{rung_id}"
            first = await client.patch(path, json=body, headers=headers("u_admin"))
            again = await client.patch(path, json=body, headers=headers("u_admin"))
            return [first.status_code, again.status_code]

        assert pressed(url, ROUTING_GRANTS, save_twice) == [200, 200]
        [(attempts, timeout)] = sql(
            url, "SELECT attempts, timeout_seconds FROM ops.routing_rung WHERE id = %s", rung_id
        )
        sql(url, "UPDATE ops.routing_rung SET enabled = false WHERE id = %s", rung_id)
        found = seen(url, "routing")
        chain = entries(url)

    assert (attempts, float(timeout)) == (2, 20.0)
    assert summary(found) == wanted(
        (
            str(role),
            recorder().routing(rung_id=rung_id, change=RoutingChange.ADDED, actor_inferred=True),
        ),
        (
            "u_admin",
            recorder().routing(
                rung_id=rung_id,
                change=RoutingChange.CHANGED,
                fields=("attempts", "timeout_seconds"),
            ),
        ),
        (
            str(role),
            recorder().routing(
                rung_id=rung_id,
                change=RoutingChange.CHANGED,
                fields=("enabled",),
                actor_inferred=True,
            ),
        ),
    )
    assert attributed([found[1]])
    assert AuditChain(chain).verify() is None


# --------------------------------------------------------------------------- webhooks


def test_each_webhook_change_through_the_store_appends_one_entry_naming_its_own_author() -> None:
    """M27.8.17's ledger half for the Webhooks screen's three writes, through the store the routes
    call and as the role they run as. Registered by one person, rotated by a second, switched off
    by a third: three entries, each naming its own author and the reach digest the store set, and
    never the endpoint. Delete this and a change to where the company's identifiers are sent can
    be missing from the ledger while `tests/unit/test_webhook_store.py`, which reads the change
    rows, stays green. **Skips without a server.** The name of the action the delivery work
    records under is `webhook`, and this is the test that holds it."""
    with through_0059("brain_console_audit_webhooks") as url:

        async def three(sessions: Any) -> None:
            store = StoredWebhooks(sessions)
            await store.register(
                a_subscriber(),
                actor="u_admin",
                at=AT,
                trace_id="trace-register",
                ent_hash="a" * 32,
                keep_secret=kept,
            )
            await store.replace_secret(
                "billing_bridge",
                actor="u_other",
                at=AT,
                trace_id="trace-replace",
                ent_hash="b" * 32,
                keep_secret=kept,
            )
            await store.switch_off("billing_bridge", actor="u_third", at=AT)

        async def go() -> None:
            built = app_engine(url)
            try:
                await three(make_session_factory(built))
            finally:
                await built.dispose()

        run(go)
        found = seen(url, "webhook")
        chain = entries(url)

    assert summary(found) == wanted(
        (
            "u_admin",
            recorder().webhook(subscriber_id="billing_bridge", change=WebhookChange.REGISTERED),
        ),
        (
            "u_other",
            recorder().webhook(
                subscriber_id="billing_bridge", change=WebhookChange.SECRET_REPLACED
            ),
        ),
        (
            "u_third",
            recorder().webhook(subscriber_id="billing_bridge", change=WebhookChange.SWITCHED_OFF),
        ),
    )
    assert [(one.ent_hash, one.trace_id) for one in found[:2]] == [
        ("a" * 32, "trace-register"),
        ("b" * 32, "trace-replace"),
    ]
    assert all("hooks.example.test" not in str(one.details) for one in chain)
    assert AuditChain(chain).verify() is None


# ----------------------------------------------------------------------------- grants

GRANT_GRANTS = {
    "u_admin": (
        Grant(capability=Capability(value="read:grant"), scope=EVERYWHERE),
        Grant(capability=Capability(value="read:scope"), scope=EVERYWHERE),
        Grant(capability=REACH_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=Capability(value=GRANTED), scope=EVERYWHERE),
        Grant(capability=plane_capability(Plane.CONFIGURATION), scope=EVERYWHERE),
    ),
}


def holds_granted(url: str, principal_id: str) -> bool:
    """Whether the resolver, read as the application role, gives this principal the capability."""

    async def load() -> bool:
        built = app_engine(url)
        now = datetime.now(UTC)
        try:
            reach = await StoredEntitlements(make_session_factory(built)).load(principal_id, now)
        finally:
            await built.dispose()
        return reach.scope_for(Capability(value=GRANTED), now) is not None

    return run(load)


def test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach() -> None:
    """M27.8.17 for the People screen's two writes, pressed over HTTP against PostgreSQL, which is
    what `docs/console-audit.md` recorded as missing: every earlier test saw a stub session commit.

    A grant written at the maintenance scope is a row naming the writer, a `grant` entry the
    `0003` trigger appends with the writer as actor rather than inferred, and a reach the resolver
    then returns to the holder; removing it retires the row, appends a `revoke` entry naming the
    remover, and the resolver returns the capability no more. Delete this and row-level security
    can refuse either write on every install, which happened to the removal until d2cfb32 while the
    stub saw a commit each time. **Skips without a server.**"""
    with through_0059("brain_console_audit_grants") as url:
        a_principal(url, "u_admin")
        a_principal(url, "u_2")
        sql(
            url,
            "INSERT INTO gate.scope (slug, predicate, is_department, label) "
            "VALUES (%s, %s::jsonb, true, 'Maintenance')",
            MAINTENANCE,
            f'{{"department": "{MAINTENANCE}"}}',
        )
        held_before = holds_granted(url, "u_2")

        async def grant(client: httpx.AsyncClient) -> int:
            response = await client.post(
                f"{API_PREFIX}/govern/grants",
                json={
                    "principal_id": "u_2",
                    "capability": GRANTED,
                    "scope_slug": MAINTENANCE,
                    "reason": "covering the maintenance rota",
                },
                headers=headers("u_admin"),
            )
            return response.status_code

        assert pressed(url, GRANT_GRANTS, grant) == 201
        [(granted_id, granted_by)] = sql(
            url,
            "SELECT id, granted_by FROM gate.capability_grant "
            "WHERE principal_id = 'u_2' AND deleted_at IS NULL",
        )
        held_after_grant = holds_granted(url, "u_2")

        async def remove(client: httpx.AsyncClient) -> int:
            response = await client.post(
                f"{API_PREFIX}/govern/grants/removal",
                json={"principal_id": "u_2", "capability": GRANTED},
                headers=headers("u_admin"),
            )
            return response.status_code

        assert pressed(url, GRANT_GRANTS, remove) == 200
        retired = sql(
            url,
            "SELECT deleted_at IS NOT NULL FROM gate.capability_grant WHERE id = %s",
            granted_id,
        )
        held_after_removal = holds_granted(url, "u_2")
        found = [one for one in entries(url) if one.subject == f"grant:{granted_id}"]
        chain = entries(url)

    assert (held_before, held_after_grant, held_after_removal) == (False, True, False)
    assert granted_by == "u_admin"
    assert retired == [(True,)]
    assert [(one.action.value, one.actor_id, one.details.get("capability")) for one in found] == [
        ("grant", "u_admin", GRANTED),
        ("revoke", "u_admin", GRANTED),
    ]
    assert all("actor" not in one.details for one in found)
    assert AuditChain(chain).verify() is None


# ------------------------------------------------------------------------- legal holds


def test_a_hold_placed_through_the_store_keeps_its_rows_from_the_sweep_and_lifted_releases_them(
    server: str,
) -> None:
    """M27.8.17's behaviour half for the Retention screen's two hold writes. A hold on `u_two`
    placed with `place_hold`, the function the route calls, is read by `active_holds`, the function
    the scheduled run reads its holds with, and the sweep over them keeps `u_two`'s old row; lifted
    with `lift_hold`, the next sweep removes it. Delete this and a hold can be written in a shape
    the sweep does not read as a hold, which the tests building holds in memory or with raw SQL
    would never see. **Skips without a server.**"""
    hold = LegalHold(
        id="h_dispute", reason_code="litigation", subjects=frozenset({"u_two"}), placed_at=OLD
    )
    now = FAR_OFF

    async def with_session(work: Callable[[Any], Awaitable[Any]]) -> Any:
        built = engine(server)
        try:
            async with AsyncSession(built) as session:
                answer = await work(session)
                await session.commit()
                return answer
        finally:
            await built.dispose()

    run(lambda: with_session(lambda session: place_hold(session, hold, by="u_admin")))
    with psycopg.connect(server) as conn:
        sweep(a_sweeper(conn, holds=active_holds(conn, now)), now=now, report_only=False)
        conn.commit()
    while_held = remaining(server)

    lifted = run(
        lambda: with_session(
            lambda session: lift_hold(
                session, "h_dispute", by="u_admin", at=now - timedelta(days=1)
            )
        )
    )
    with psycopg.connect(server) as conn:
        sweep(a_sweeper(conn, holds=active_holds(conn, now)), now=now, report_only=False)
        conn.commit()

    assert while_held == [("u_one", YOUNG), ("u_two", OLD)]
    assert lifted is True
    assert remaining(server) == [("u_one", YOUNG)]
