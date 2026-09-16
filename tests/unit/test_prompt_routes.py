"""The Prompts screen over HTTP: who sees an agent's instructions, who may change them, and proof
that a change reaches what the agent is given.

Driven through the real application with the agent, its install and its pinned version held in
memory, built from a real publish and a real install by `tests/unit/test_agent_routes.py`'s
`install_rows`. An edit is followed to the two rows it writes, and then the written install is
materialised again and handed to `build_prefix`, which is where an agent's instructions enter a
prompt, so the proof is the prompt text rather than the response.

Task ids: M27.8.9
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.selectable import Select

from brain.agents.model import AgentAudience
from brain.agents.template import FieldOwner, TemplateInstance, materialise
from brain.api import API_PREFIX
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.gate.effort import OUTPUT_LENGTHS
from brain.gate.prefix import HOUSE_RULES, build_prefix
from brain.knowledge.visibility import Visibility
from brain.prompt_routes import INSTRUCTIONS_AUTHORITY, SWITCHED_OFF
from brain.tables.agent import AgentRow
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
from tests.fixtures.console_http import Stub, console_client, get, post
from tests.fixtures.setting_rows import Result, SettingRows
from tests.unit.test_agent_routes import agent_row, install_rows

PROMPTS = f"{API_PREFIX}/govern/prompts"

#: A PostgreSQL dialect from an engine that never connects, to see a locking read in its SQL.
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
EVERYWHERE = Scope.unrestricted()
SETTINGS_READ = tab(Tab.SETTINGS).read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
READS = (
    Grant(capability=SETTINGS_READ, scope=EVERYWHERE),
    Grant(capability=CONFIGURATION, scope=EVERYWHERE),
)

#: `u_admin` (web) may see every agent and edit any. `u_narrow` (web) may edit web's agents only.
#: `u_wide` (sales) may read and not edit. `u_prefix` (web) holds the authority and the tab
#: without the configuration plane, so may read nothing. `u_none` holds nothing.
GRANTS = {
    "u_admin": (*READS, Grant(capability=INSTRUCTIONS_AUTHORITY, scope=EVERYWHERE)),
    "u_narrow": (*READS, Grant(capability=INSTRUCTIONS_AUTHORITY, scope=Scope.department("web"))),
    "u_wide": READS,
    "u_prefix": (
        Grant(capability=SETTINGS_READ, scope=EVERYWHERE),
        Grant(capability=INSTRUCTIONS_AUTHORITY, scope=EVERYWHERE),
    ),
    "u_none": (),
}

COMPANY = "pricing_desk"
WEB = "web_helper"
SALES = "sales_helper"
LOOSE = "loose_agent"
INSTALLED_PERSONA = "Answer briefly and name the price list."
NEW = "Answer in two sentences and always name the price list and its date."


class Agents:
    """The agent rows, installs and versions the stub answers with, and every update made."""

    def __init__(self) -> None:
        self.rows: dict[str, tuple[AgentRow, TemplateInstanceRow | None, TemplateVersionRow | None]]
        self.rows = {}
        self.updates: list[tuple[str, dict[str, Any]]] = []
        for agent_id, level, department in (
            (COMPANY, Visibility.COMPANY, None),
            (WEB, Visibility.DEPARTMENT, "web"),
            (SALES, Visibility.DEPARTMENT, "sales"),
        ):
            instance_row, version_row, _, _ = install_rows(agent_id)
            self.rows[agent_id] = (
                agent_row(agent_id, level=level, department=department, persona=INSTALLED_PERSONA),
                instance_row,
                version_row,
            )
        self.rows[LOOSE] = (agent_row(LOOSE), None, None)

    def answer(self, statement: Any) -> Result | None:
        if isinstance(statement, Select):
            names = [one["name"] for one in statement.column_descriptions]
            if names != ["AgentRow", "TemplateInstanceRow", "TemplateVersionRow"]:
                return None
            if "FOR UPDATE" not in str(statement.compile(dialect=DIALECT)):
                return Result(self.rows[key] for key in sorted(self.rows))
            (wanted,) = statement.compile().params.values()
            return Result([self.rows[wanted]] if wanted in self.rows else [])
        if isinstance(statement, Update):
            values = statement.compile().params
            agent_id = values.pop("id_1")
            table = str(getattr(statement.table, "name", ""))
            self.updates.append((table, values))
            agent, instance, _ = self.rows[agent_id]
            target = agent if table == "agent" else instance
            for column, value in values.items():
                setattr(target, column, value)
            return Result([])
        return None


@pytest.fixture
def agents() -> Agents:
    return Agents()


@pytest.fixture
def settings() -> SettingRows:
    return SettingRows()


@pytest.fixture
def served(agents: Agents, settings: SettingRows) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([settings.answer, agents.answer])
        yield client, stub


def switched_on(settings: SettingRows) -> None:
    settings.hold("feature.prompt_editing", True, value_type="boolean", by="u_admin")


def listed(client: TestClient, pid: str) -> dict[str, dict[str, Any]]:
    return {one["agent_id"]: one for one in get(client, pid, PROMPTS).json()["agents"]}


def given_after(agents: Agents, agent_id: str) -> str:
    """What the agent is given now: its written install materialised and handed to the prompt
    builder, as a run would."""
    agent, instance_row, version_row = agents.rows[agent_id]
    assert instance_row is not None and version_row is not None
    _, _, signed, _ = install_rows(agent_id)
    instance = TemplateInstance(
        instance_id=instance_row.id,
        template_id=instance_row.template_id,
        template_version=instance_row.template_version,
        content_digest=instance_row.content_digest,
        overlay=instance_row.overlay,
        overlay_owners={
            p: FieldOwner.model_validate(o) for p, o in instance_row.field_owners.items()
        },
        created_by=instance_row.created_by,
    )
    audience = AgentAudience(level=Visibility.COMPANY, owner_id=agent.owner_id)
    effective = materialise(signed, instance, audience=audience)
    assert effective.config_hash == instance_row.effective_hash
    return build_prefix((), persona=effective.record.persona).text


# ------------------------------------------------------------------------ the read


def test_a_reader_of_agent_settings_sees_the_instructions_in_force_and_the_templates(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case: the persona in force, the template's, who set it, and the hash an edit
    must name, and the house rules beside them.

    Delete this and every refusal below is satisfied by a screen that shows nothing."""
    client, _ = served
    body = get(client, "u_admin", PROMPTS).json()
    agents = {one["agent_id"]: one for one in body["agents"]}

    company = agents[COMPANY]
    assert company["instructions"] == INSTALLED_PERSONA
    assert company["template_instructions"] == "Answer briefly."
    assert company["overridden"] is True
    assert company["set_by"] == "u_installer"
    assert company["installed"] is True
    assert company["editable"] is False
    assert agents[LOOSE]["installed"] is False
    assert body["house_rules"] == list(HOUSE_RULES)
    assert [one["name"] for one in body["output_lengths"]] == [one.name for one in OUTPUT_LENGTHS]
    assert body["system_instructions_are_product_text"] is True
    assert body["no_model_is_called_yet"] is True


def test_the_list_is_narrowed_by_audience_and_by_the_settings_tab(
    served: tuple[TestClient, Stub],
) -> None:
    """A sales reader does not see web's agent; a reader without the tab or the plane sees none.

    Delete this and the instructions of a department's agent are shown to the whole company."""
    client, _ = served

    assert set(listed(client, "u_wide")) == {COMPANY, LOOSE, SALES}
    assert set(listed(client, "u_admin")) == {COMPANY, LOOSE, WEB}
    assert listed(client, "u_none") == {}
    assert listed(client, "u_prefix") == {}


def test_the_system_instructions_have_no_route_that_writes_them(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and an install can edit the rule that tells every model never to mention
    what was withheld."""
    client, _ = served
    paths = {
        (path, method)
        for path, item in client.app.openapi()["paths"].items()  # type: ignore[attr-defined]
        if path.startswith(PROMPTS)
        for method in item
    }

    assert paths == {
        (PROMPTS, "get"),
        (f"{PROMPTS}/{{agent_id}}", "post"),
        (f"{PROMPTS}/{{agent_id}}/give-back", "post"),
    }


# ------------------------------------------------------------------------ the edit


def test_an_edit_is_written_to_the_install_and_changes_what_the_agent_is_given(
    served: tuple[TestClient, Stub], agents: Agents, settings: SettingRows
) -> None:
    """The write is followed to both rows, to who is recorded as setting it, and into the prompt
    the agent would be built with, whose hash the answer cache keys on.

    Delete this and the screen can report an edit while the agent goes on being given its old
    instructions."""
    client, stub = served
    switched_on(settings)
    before = listed(client, "u_admin")[COMPANY]
    assert INSTALLED_PERSONA in given_after(agents, COMPANY)

    answer = post(
        client,
        "u_admin",
        f"{PROMPTS}/{COMPANY}",
        {"instructions": NEW, "expected_hash": before["effective_hash"]},
    )

    assert answer.status_code == 200, answer.text
    assert answer.json()["instructions"] == NEW
    assert answer.json()["set_by"] == "u_admin"
    assert answer.json()["effective_hash"] != before["effective_hash"]
    assert [table for table, _ in agents.updates] == ["template_instance", "agent"]
    assert agents.rows[COMPANY][0].persona == NEW
    assert stub.commits == 1
    prompt = given_after(agents, COMPANY)
    assert NEW in prompt
    assert INSTALLED_PERSONA not in prompt
    assert prompt.startswith(HOUSE_RULES[0])


def test_giving_instructions_back_restores_the_templates_and_is_not_behind_the_feature(
    served: tuple[TestClient, Stub], agents: Agents
) -> None:
    """Delete this and an edit made while the feature was on can never be undone after it is
    turned off, which is the trap `brain.ops.features` refuses."""
    client, _ = served
    before = listed(client, "u_admin")[COMPANY]

    answer = post(
        client,
        "u_admin",
        f"{PROMPTS}/{COMPANY}/give-back",
        {"expected_hash": before["effective_hash"]},
    )

    assert answer.status_code == 200, answer.text
    assert answer.json()["instructions"] == "Answer briefly."
    assert answer.json()["overridden"] is False
    assert "Answer briefly." in given_after(agents, COMPANY)
    assert agents.rows[COMPANY][0].persona == "Answer briefly."


def test_an_edit_is_refused_by_name_while_the_feature_is_off_and_nothing_is_written(
    served: tuple[TestClient, Stub], agents: Agents
) -> None:
    """Delete this and the `prompt_editing` switch reaches nothing."""
    client, stub = served
    before = listed(client, "u_admin")[COMPANY]

    answer = post(
        client,
        "u_admin",
        f"{PROMPTS}/{COMPANY}",
        {"instructions": NEW, "expected_hash": before["effective_hash"]},
    )

    assert answer.status_code == 404
    assert SWITCHED_OFF in answer.json()["message"]
    assert agents.updates == []
    assert stub.commits == 0


@pytest.mark.parametrize(
    ("text", "because"),
    [
        ("   ", "cannot be empty"),
        ("x" * 2001, "at most"),
        ("Greet {name} warmly.", "contains '{'"),
        (INSTALLED_PERSONA, "already in force"),
    ],
)
def test_instructions_the_prompt_builder_would_refuse_are_refused_before_anything_is_written(
    served: tuple[TestClient, Stub], agents: Agents, settings: SettingRows, text: str, because: str
) -> None:
    """Delete this and a persona with a substitution point is stored and refused at the first run
    instead, or an empty one silently gives the agent no instructions."""
    client, _ = served
    switched_on(settings)
    before = listed(client, "u_admin")[COMPANY]

    answer = post(
        client,
        "u_admin",
        f"{PROMPTS}/{COMPANY}",
        {"instructions": text, "expected_hash": before["effective_hash"]},
    )

    assert answer.status_code == 404
    assert because in answer.json()["message"]
    assert agents.updates == []


def test_an_edit_naming_a_hash_that_has_moved_is_refused_so_nobody_overwrites_in_silence(
    served: tuple[TestClient, Stub], agents: Agents, settings: SettingRows
) -> None:
    """Delete this and two administrators editing one agent lose the first edit without either
    being told."""
    client, _ = served
    switched_on(settings)

    answer = post(
        client, "u_admin", f"{PROMPTS}/{COMPANY}", {"instructions": NEW, "expected_hash": "0" * 64}
    )

    assert answer.status_code == 404
    assert "changed this agent after you opened it" in answer.json()["message"]
    assert agents.updates == []


def test_a_department_scoped_authority_edits_that_departments_agent_and_no_other(
    served: tuple[TestClient, Stub], agents: Agents, settings: SettingRows
) -> None:
    """The authority's scope is matched against the agent, and a company agent is refused in the
    words an agent that does not exist is refused in.

    Delete this and a department's administrator rewrites the instructions of an agent the whole
    company uses."""
    client, _ = served
    switched_on(settings)
    shown = listed(client, "u_narrow")
    assert shown[WEB]["editable"] is True
    assert shown[COMPANY]["editable"] is False

    web = post(
        client,
        "u_narrow",
        f"{PROMPTS}/{WEB}",
        {"instructions": NEW, "expected_hash": shown[WEB]["effective_hash"]},
    )
    company = post(
        client,
        "u_narrow",
        f"{PROMPTS}/{COMPANY}",
        {"instructions": NEW, "expected_hash": shown[COMPANY]["effective_hash"]},
    )
    missing = post(
        client, "u_narrow", f"{PROMPTS}/no_such_agent", {"instructions": NEW, "expected_hash": "x"}
    )

    assert web.status_code == 200, web.text
    assert company.status_code == missing.status_code == 404
    assert company.json()["message"] == missing.json()["message"]
    assert [table for table, _ in agents.updates] == ["template_instance", "agent"]


def test_an_agent_outside_the_editors_audience_is_refused_as_an_agent_that_does_not_exist(
    served: tuple[TestClient, Stub], agents: Agents, settings: SettingRows
) -> None:
    """The authority over everything does not reach an agent the editor may not see.

    Delete this and an administrator who guessed a department's agent slug rewrites the
    instructions of an agent the roster would never have shown them, and learns it exists from
    the refusal being different."""
    client, _ = served
    switched_on(settings)
    hidden = agents.rows[SALES][1]
    assert hidden is not None

    guessed = post(
        client,
        "u_admin",
        f"{PROMPTS}/{SALES}",
        {"instructions": NEW, "expected_hash": hidden.effective_hash},
    )
    missing = post(
        client, "u_admin", f"{PROMPTS}/no_such_agent", {"instructions": NEW, "expected_hash": "x"}
    )

    assert guessed.status_code == missing.status_code == 404
    assert guessed.json()["message"] == missing.json()["message"]
    assert agents.updates == []


def test_an_agent_with_no_install_is_refused_by_name_rather_than_edited_on_its_row_alone(
    served: tuple[TestClient, Stub], agents: Agents, settings: SettingRows
) -> None:
    """Delete this and an agent's row persona is edited with no template to record the change
    against, which is a second copy of its instructions that nothing materialises."""
    client, _ = served
    switched_on(settings)

    answer = post(
        client, "u_admin", f"{PROMPTS}/{LOOSE}", {"instructions": NEW, "expected_hash": "x"}
    )

    assert answer.status_code == 404
    assert "no install record" in answer.json()["message"]
    assert agents.updates == []


@pytest.mark.parametrize("pid", ["u_none", "u_wide", "u_prefix"])
def test_a_caller_without_the_authority_or_the_settings_read_is_refused_before_the_database(
    pid: str,
) -> None:
    """Delete this and a reader learns whether this process has a database, or which agents
    exist, from how an edit is refused."""
    body = {"instructions": NEW, "expected_hash": "x"}
    with console_client(GRANTS, database=False) as (client, _):
        without = post(client, pid, f"{PROMPTS}/{COMPANY}", body)
    with console_client(GRANTS) as (client, stub):
        with_pool = post(client, pid, f"{PROMPTS}/{COMPANY}", body)
        statements = list(stub.statements)

    assert without.status_code == with_pool.status_code == 404
    assert without.json()["message"] == with_pool.json()["message"]
    assert statements == []
