"""A written automation reaches the system: the migration, the row and the ledger entry.

The first half needs no server: it holds what `0219` copied to the live definitions and the model
it must match. The second half builds a database to head and proves a written automation arrives
in the three places `docs/admin-console.md` names: the row, which reads back as what was written;
the one `compose_change` entry the trigger appends, as `authored_install`; and the behaviour, which
is a person writing as many as they like while Install still answers a second press with the
first. **It skips when the server has no pgvector**, and CI always has one.

Task ids: M39.9.2.1, M17.4.2
"""

from __future__ import annotations

import re
from typing import Any

import psycopg
import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.audit.ledger import AuditChain
from brain.console.automation_authoring import (
    AUTHORED_TEMPLATE,
    MAXIMUM_INSTRUCTION,
    MINIMUM_INSTRUCTION,
    Authored,
    Authoring,
    Condition,
    ConditionOp,
    TriggerChoice,
    authored_from_row,
    authoring_of,
    preview,
)
from brain.console.automation_gallery import AUTOMATION_AUTHORITY, Cadence, Every
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.knowledge.visibility import Visibility
from brain.ops.agent_automation_store import (
    NOT_AUTHORED,
    StoredAgentAutomations,
    authored_values,
)
from brain.orchestration.unattended import TriggerKind
from brain.session import make_session_factory
from brain.tables import agent_automation as table_module
from brain.tables.agent_automation import AgentAutomationRow
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_agent_automation_store import (
    ADDED_BY_0219,
    AGENT,
    TEMPLATE,
    an_installation,
    entries,
)
from tests.unit.test_automation_owner_store import app_engine, as_app
from tests.unit.test_tables import VERSIONS, migration_module

MIGRATION = VERSIONS / "0219_authored_automation.py"

AUTHOR = "u_author"


def a_written_automation(
    automation_id: str = "auto_written", principal_id: str = AUTHOR, **changes: object
) -> Authoring:
    agent = AgentRecord(
        agent_id=AGENT,
        display_name="Quote helper",
        persona="Answers pricing questions.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(
            capabilities=(Capability(value="read:client.name"),),
            allowed_tools=frozenset({"search_tickets"}),
        ),
        created_by="u_builder",
    )
    values: dict[str, Any] = {
        "name": "I check each morning whether any ticket is overdue",
        "instruction": "Look at the tickets and tell me which are overdue by more than a week.",
        "guards": "Without it an overdue ticket is found when the client chases, not by us.",
        "trigger": TriggerChoice(
            kind=TriggerKind.SCHEDULE, cadence=Cadence(every=Every.WEEK, hour_utc=8, weekday=0)
        ),
        "tools": ("search_tickets",),
        "condition": Condition(field="freshdesk.ticket.due_by", op=ConditionOp.IS_OVER, value="7"),
    }
    values.update(changes)
    shown = preview(
        Authored(**values),
        agent,
        author=Principal(
            id=principal_id,
            kind=PrincipalKind.HUMAN,
            employment=Employment.STAFF,
            display_name=principal_id,
        ),
        author_reach=EntitlementSet(
            principal_id=principal_id,
            grants=(Grant(capability=AUTOMATION_AUTHORITY, scope=Scope.unrestricted()),),
        ),
    )
    return authoring_of(shown, confirmation=shown.confirmation, automation_id=automation_id)


# ------------------------------------------------------------------- what was copied


def words(quoted: str) -> set[str]:
    """The words in a parenthesised SQL list, as a set, since a list is not an order."""
    return set(re.findall(r"'([a-z_]+)'", quoted))


def test_the_migration_holds_the_words_the_application_uses() -> None:
    """`0219` copies the placeholder template, the trigger kinds, the cadences, the comparisons and
    the instruction bounds, for the reason `0009` gives. Delete this and one side can change alone:
    a comparison the form offers and the check refuses after the person confirmed, or an
    instruction the application admits and the table does not."""
    migration = migration_module(MIGRATION)

    assert migration.AUTHORED == AUTHORED_TEMPLATE == table_module.AUTHORED_TEMPLATE
    assert words(migration.TRIGGER_KINDS) == {kind.value for kind in TriggerKind}
    assert words(migration.EVERIES) == {every.value for every in Every}
    assert words(migration.CONDITION_OPS) == {op.value for op in ConditionOp}
    assert migration.CHECKS == table_module.AUTHORING_CHECKS
    assert migration.INSTRUCTION_MIN == MINIMUM_INSTRUCTION
    assert migration.INSTRUCTION_MAX == MAXIMUM_INSTRUCTION
    assert {name for name, _ in migration.COLUMNS} == ADDED_BY_0219
    assert {c.name for c in AgentAutomationRow.__table__.columns} >= ADDED_BY_0219


def test_a_written_automation_is_its_installs_columns_plus_exactly_the_added_ones() -> None:
    """One row whichever way it began. Delete this and an authored write can leave out a column an
    install writes, or write one the table does not have."""
    written = a_written_automation()
    values = authored_values(written)

    assert set(values) == {c.name for c in AgentAutomationRow.__table__.columns} - {
        "created_at",
        "updated_at",
    }
    assert values["template_id"] == AUTHORED_TEMPLATE
    assert values["next_run_at"] is None
    assert values["cadence_every"] == "week" and values["cadence_weekday"] == 0
    assert values["trigger_source"] is None
    assert values["tools"] == ["search_tickets"]
    assert NOT_AUTHORED == "template_id <> 'authored'"


def test_a_trigger_that_is_not_a_schedule_is_written_with_a_source_and_no_cadence() -> None:
    """Delete this and a webhook is written with a cadence the migration's check refuses."""
    values = authored_values(
        a_written_automation(
            trigger=TriggerChoice(kind=TriggerKind.WEBHOOK, source="ticket_closed"),
            condition=None,
        )
    )

    assert values["trigger_kind"] == "webhook"
    assert values["trigger_source"] == "ticket_closed"
    assert (values["cadence_every"], values["cadence_hour"], values["cadence_weekday"]) == (
        None,
        None,
        None,
    )
    assert values["condition_field"] is None


# ------------------------------------------------------------------- the database


def test_a_written_automation_reads_back_arrives_in_the_ledger_and_install_is_still_once() -> None:
    """The write, through the store the application uses and as the role it uses: one row that
    reads back as what was written, one `compose_change` entry saying `authored_install`, the
    chain verifying, a person writing two without conflict, and Install of a template still
    answered with the first on a second press. Delete this and every one of those can be false in
    production while the stubbed tests stay green. **Skips without pgvector.**"""
    with retirable("brain_automation_authoring") as url:
        if not has_pgvector(url):
            pytest.skip("the chain to head needs pgvector")
        first = a_written_automation("auto_first")
        second = a_written_automation(
            "auto_second",
            trigger=TriggerChoice(kind=TriggerKind.CONNECTOR_EVENT, source="freshdesk"),
            condition=None,
        )
        installed = an_installation(AUTHOR, "auto_installed")
        again = an_installation(AUTHOR, "auto_installed_again")

        async def work() -> tuple[str, str, Any, Any, str]:
            engine = app_engine(url)
            try:
                store = StoredAgentAutomations(make_session_factory(engine))
                one = await store.author(first, ent_hash="a" * 32, trace_id="trace-first")
                two = await store.author(second, ent_hash="a" * 32, trace_id="trace-second")
                again_one = await store.author(
                    first, ent_hash="a" * 32, trace_id="trace-pressed-twice"
                )
                done = await store.install(installed, ent_hash="a" * 32, trace_id="t-install")
                twice = await store.install(again, ent_hash="a" * 32, trace_id="t-again")
                return one, two, done, twice, again_one
            finally:
                await engine.dispose()

        one, two, done, twice, again_one = run(work)
        rows = sql(
            url,
            "SELECT automation_id, template_id, trigger_kind, trigger_source, cadence_every, "
            "cadence_hour, cadence_weekday, condition_field, condition_op, condition_value, "
            "instruction, tools, from_template_id, name, guards, task "
            "FROM agent.automation WHERE template_id = 'authored' ORDER BY automation_id",
        )
        chain = entries(url)

    class Stored:
        def __init__(self, row: tuple[Any, ...]) -> None:
            names = (
                "automation_id", "template_id", "trigger_kind", "trigger_source",
                "cadence_every", "cadence_hour", "cadence_weekday", "condition_field",
                "condition_op", "condition_value", "instruction", "tools", "from_template_id",
                "name", "guards", "task",
            )  # fmt: skip
            self.__dict__.update(zip(names, row, strict=True))

    read = [authored_from_row(Stored(row)) for row in rows]  # type: ignore[arg-type]
    reasons = sorted(
        str(dict(one.details)["reason_code"])
        for one in chain
        if one.action.value == "compose_change"
    )

    assert (one, two) == ("auto_first", "auto_second")
    assert again_one == "auto_first"
    assert len(rows) == 2
    assert [one.trace_id for one in chain if one.action.value == "compose_change"].count(
        "trace-pressed-twice"
    ) == 0
    assert read == [first.authored, second.authored]
    assert (
        done.created is True and twice.created is False and twice.automation_id == "auto_installed"
    )
    assert reasons == ["authored_install", "authored_install", "template_install"]
    assert AuditChain(chain).verify() is None


def test_the_database_holds_the_two_shapes_apart_whatever_wrote_the_row() -> None:
    """The migration's checks, measured by writing rows the application never would. A row
    installed from a template carrying authoring, an authored one with no instruction, no trigger,
    a schedule with no cadence, an event with a cadence, a condition with a word nothing offers:
    each refused. The sibling is the valid row, accepted. Delete this and a check can be dropped
    from `0219` with every stubbed test still green. **Skips without pgvector.**"""
    with retirable("brain_automation_authoring_checks") as url:
        if not has_pgvector(url):
            pytest.skip("the chain to head needs pgvector")
        good = authored_values(a_written_automation())
        refused: dict[str, dict[str, Any]] = {
            "a template row carrying an instruction": {
                **authored_values(a_written_automation("auto_t")),
                "template_id": TEMPLATE.template_id,
            },
            "an authored row with no instruction": {
                **good,
                "automation_id": "a1",
                "instruction": None,
            },
            "an authored row with a short instruction": {
                **good,
                "automation_id": "a2",
                "instruction": "do it",
            },
            "an authored row with no trigger": {
                **good,
                "automation_id": "a3",
                "trigger_kind": None,
            },
            "a schedule with no cadence": {
                **good,
                "automation_id": "a4",
                "cadence_every": None,
                "cadence_hour": None,
                "cadence_weekday": None,
            },
            "an event with a cadence": {
                **good,
                "automation_id": "a5",
                "trigger_kind": "connector_event",
                "trigger_source": "freshdesk",
            },
            "an event with no source": {
                **good,
                "automation_id": "a6",
                "trigger_kind": "connector_event",
                "cadence_every": None,
                "cadence_hour": None,
                "cadence_weekday": None,
            },
            "a condition with an operation nothing offers": {
                **good,
                "automation_id": "a7",
                "condition_op": "matches_regex",
            },
            "a condition with no value": {**good, "automation_id": "a8", "condition_value": None},
            "a weekly cadence with no day": {
                **good,
                "automation_id": "a9",
                "cadence_weekday": None,
            },
            "no tools list": {**good, "automation_id": "a10", "tools": None},
        }

        def insert(conn: psycopg.Connection[Any], values: dict[str, Any]) -> None:
            names = list(values)
            conn.execute(
                f"INSERT INTO agent.automation ({', '.join(names)}) "  # noqa: S608
                f"VALUES ({', '.join(['%s'] * len(names))})",
                tuple(values.values()),
            )

        with as_app(url, ("app.principal_id", AUTHOR)) as conn:
            insert(conn, good)
            for why, values in refused.items():
                with pytest.raises(psycopg.errors.CheckViolation):
                    insert(conn, values)
                assert why
            own = conn.execute("SELECT automation_id FROM agent.automation").fetchall()

    assert own == [("auto_written",)]


# ------------------------------------------------------------------- what the worker reads


def test_a_row_a_person_wrote_runs_on_its_own_cadence_and_one_with_nothing_to_fire_has_none() -> (
    None
):
    """The worker takes an authored row's cadence from its own columns, and a trigger nothing
    fires leaves it with none, so a run is refused as unbuilt and not counted as a failure.
    Delete this and the worker asks the template list about a row that has no template, so every
    authored automation reads as one whose template was withdrawn."""
    from brain.ops.automation_run_store import _cadence_of, _has_a_source

    scheduled = a_written_automation()
    hook = a_written_automation(
        "auto_hook",
        trigger=TriggerChoice(kind=TriggerKind.WEBHOOK, source="ticket_closed"),
        condition=None,
    )

    def row(values: dict[str, Any]) -> Any:
        return type("Row", (), values)

    scheduled_row, hook_row = row(authored_values(scheduled)), row(authored_values(hook))
    assert _cadence_of(scheduled_row) == Cadence(every=Every.WEEK, hour_utc=8, weekday=0)
    assert _has_a_source(scheduled_row, _cadence_of(scheduled_row))
    assert _cadence_of(hook_row) is None
    assert not _has_a_source(hook_row, _cadence_of(hook_row))
    gone = row({**authored_values(scheduled), "template_id": "withdrawn_template"})
    assert not _has_a_source(gone, None)
    installed = row({"template_id": TEMPLATE.template_id})
    assert _has_a_source(installed, TEMPLATE.cadence)
    assert _cadence_of(installed) == TEMPLATE.cadence
