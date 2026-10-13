"""New automation over HTTP: the options, the preview and the one confirmed write.

Driven through the real application with the token machinery and the people of
`tests/unit/test_automation_gallery_routes.py`, and with the stores in memory. What reaches
PostgreSQL is `tests/unit/test_automation_authoring_store.py`'s.

**Every refusal is compared body to body and status to status with the case it must be
indistinguishable from**, and has a sibling proving the permitted case is answered.

Task ids: M39.9.2.1, M39.9.2.2, M39.9.2.3, M39.9.2.4, M17.4.1, M17.4.2
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import automation_authoring_routes as routes
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.connectors.manifest import manifest_digest
from brain.connectors.registry import ConnectorRegistry, ConnectorState, RegisteredConnector
from brain.console.automation_authoring import (
    AUTHORED_TASK,
    IT_STARTS_PAUSED,
    NOTHING_FIRES_THIS_YET,
    Authoring,
)
from brain.console.automation_gallery import BUILT_IN
from brain.core.entitlement import Capability
from brain.knowledge.visibility import Visibility
from tests.fixtures.http_client import Response
from tests.unit import test_freshdesk
from tests.unit.test_automation_gallery_routes import (
    WEB_AGENT,
    Agents,
    _wiring,
    auth,
    refusal,
)

AGENT = "quote_helper"
OPTIONS = f"{API_PREFIX}/agents/{{agent}}/automation-authoring"
PREVIEW = f"{API_PREFIX}/agents/{{agent}}/automation-authoring/preview"
CREATE = f"{API_PREFIX}/agents/{{agent}}/automations/authored"

#: The field the connected source reports that the examples below compare.
DUE = "freshdesk.ticket.due_by"

WORDS: dict[str, Any] = {
    "name": "I check each morning whether any ticket is overdue",
    "instruction": "Look at the tickets and tell me which are overdue by more than a week.",
    "guards": "Without it an overdue ticket is found when the client chases, not by us.",
    "trigger": {"kind": "schedule", "cadence": {"every": "day", "hour_utc": 7}},
    "tools": ["search_tickets"],
}


def an_agent(
    agent_id: str, *, department: str = "", connectors: tuple[str, ...] = ()
) -> AgentRecord:
    level = Visibility.DEPARTMENT if department else Visibility.COMPANY
    return AgentRecord(
        agent_id=agent_id,
        display_name=agent_id.replace("_", " ").title(),
        persona="Answers briefly.",
        audience=AgentAudience(level=level, owner_id="u_steward", department=department),
        authority=AgentAuthority(
            capabilities=(Capability(value="read:client.name"),),
            allowed_tools=frozenset({"search_tickets"}),
            connectors=connectors,
        ),
        created_by="u_builder",
    )


@dataclass
class Authors:
    """`routes.AutomationAuthors` in memory."""

    written: list[Authoring] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def author(self, authoring: Authoring, *, ent_hash: str, trace_id: str) -> str:
        self.calls.append({"ent_hash": ent_hash, "trace_id": trace_id})
        self.written.append(authoring)
        return authoring.installation.automation.automation_id


def connected() -> ConnectorRegistry:
    built = test_freshdesk.a_console_manifest()
    return ConnectorRegistry.of_connected(
        [
            RegisteredConnector(
                manifest=built, digest=manifest_digest(built), state=ConnectorState.ENABLED
            )
        ]
    )


@pytest.fixture
def authors() -> Authors:
    return Authors()


@pytest.fixture
def client(authors: Authors) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(routes.router)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.agent_records = Agents(
            held={
                AGENT: an_agent(AGENT, connectors=("freshdesk",)),
                WEB_AGENT: an_agent(WEB_AGENT, department="web"),
            }
        )
        app.state.automation_authors = authors
        app.state.connector_registry = connected()
        app.state.automation_authoring_on = True
        yield c


def options_of(c: TestClient, pid: str, agent: str = AGENT) -> Response:
    answer: Response = c.get(OPTIONS.format(agent=agent), headers=auth(pid))
    return answer


def preview_of(
    c: TestClient, pid: str, body: Mapping[str, object] = WORDS, agent: str = AGENT
) -> Response:
    answer: Response = c.post(PREVIEW.format(agent=agent), json=dict(body), headers=auth(pid))
    return answer


def create_as(c: TestClient, pid: str, body: Mapping[str, object], agent: str = AGENT) -> Response:
    answer: Response = c.post(CREATE.format(agent=agent), json=dict(body), headers=auth(pid))
    return answer


def confirmed(c: TestClient, pid: str, body: Mapping[str, object] = WORDS) -> dict[str, object]:
    shown = preview_of(c, pid, body)
    assert shown.status_code == 200, shown.text
    return {**body, "confirmation": shown.json()["confirmation"]}


# ------------------------------------------------------------------ the options


def test_the_options_offer_templates_triggers_this_agents_fields_and_its_own_tools(
    client: TestClient,
) -> None:
    """The form's whole vocabulary: every product template, all three trigger kinds with only the
    schedule marked as firing, the fields of the connectors this agent is bound to by shape, and
    exactly the tools its ceiling allows. Delete this and the form offers a field the agent could
    never read or a tool it may not use."""
    body = options_of(client, "u_admin").json()

    assert body["enabled"] is True
    assert {one["template_id"] for one in body["templates"]} == {
        one.template_id for one in BUILT_IN
    }
    assert {(one["kind"], one["fires"]) for one in body["triggers"]} == {
        ("schedule", True),
        ("connector_event", False),
        ("webhook", False),
    }
    fields = {one["key"]: one for one in body["fields"]}
    assert DUE in fields
    assert [op["op"] for op in fields[DUE]["ops"]] == ["is_over", "is_under", "within_days"]
    assert all(op["in_days"] for op in fields[DUE]["ops"])
    assert "freshdesk.ticket.status" in fields
    assert [op["op"] for op in fields["freshdesk.ticket.status"]["ops"]] == ["equals"]
    assert body["tools"] == ["search_tickets"]
    assert body["connectors"] == ["freshdesk"]
    assert body["starts_paused"] == IT_STARTS_PAUSED


def test_an_agent_not_bound_to_a_source_is_not_offered_its_fields(client: TestClient) -> None:
    """The agent's ceiling decides what a run can read, so a field of a source it is not bound to
    is not offered. Delete this and a condition is written that every run would refuse."""
    body = options_of(client, "u_admin", WEB_AGENT).json()

    assert body["enabled"] is True
    assert body["fields"] == []
    assert body["connectors"] == []


def test_a_switched_off_install_says_so_and_offers_nothing_and_refuses_the_rest(
    client: TestClient, authors: Authors
) -> None:
    """Off by default: the options say `enabled: false` with no vocabulary, and the preview and
    the write are the one refusal. Delete this and the feature is live on every install."""
    client.app.state.automation_authoring_on = False  # type: ignore[attr-defined]

    off = options_of(client, "u_admin").json()
    assert off == {
        "enabled": False,
        "templates": [],
        "triggers": [],
        "fields": [],
        "tools": [],
        "connectors": [],
        "starts_paused": IT_STARTS_PAUSED,
        "writes_wait": off["writes_wait"],
    }
    missing = refusal(preview_of(client, "u_admin", agent="no_such_agent"))
    assert refusal(preview_of(client, "u_admin")) == missing
    assert refusal(create_as(client, "u_admin", {**WORDS, "confirmation": "0" * 64})) == missing
    assert authors.written == []


def test_a_reader_who_may_not_author_and_an_agent_nobody_may_see_are_one_answer(
    client: TestClient,
) -> None:
    """DENIED equals ABSENT. The tab refused for want of the plane, a reader without the authority,
    an agent that does not exist and one outside the audience give one status and one body.
    Delete this and the options say which agents exist to somebody trying them."""
    missing = refusal(options_of(client, "u_admin", "no_such_agent"))

    assert refusal(options_of(client, "u_prefix")) == missing
    assert refusal(options_of(client, "u_narrow")) == missing
    assert refusal(options_of(client, "u_none")) == missing
    assert refusal(options_of(client, "u_elsewhere", WEB_AGENT)) == missing
    assert options_of(client, "u_admin", WEB_AGENT).status_code == 200


# ------------------------------------------------------------------ the preview


def test_the_preview_shows_the_terms_the_rehearsal_and_a_digest_and_writes_nothing(
    client: TestClient, authors: Authors
) -> None:
    """Everything the person agrees to, in words, with three earlier triggers rehearsed and
    nothing written or sent. Delete this and a person confirms what they were not shown."""
    answer = preview_of(client, "u_admin")
    body = answer.json()

    assert answer.status_code == 200, answer.text
    assert body["trigger"] == "Runs every day at 07:00 UTC"
    assert body["fires"] is True
    assert body["nothing_fires"] is None
    assert body["condition"] is None
    assert body["tools"] == ["search_tickets"]
    assert body["runs_as"] == "u_admin"
    assert "read:client.name" in body["reach"]
    assert len(body["rehearsal"]) == 3
    assert all("Nothing was read, written or sent" in one["says"] for one in body["rehearsal"])
    assert body["starts_paused"] == IT_STARTS_PAUSED
    assert authors.written == []


def test_a_condition_is_said_in_words_and_a_trigger_nothing_fires_says_so(
    client: TestClient,
) -> None:
    """The card's two sentences from the leaf: the condition and the trigger. Delete this and a
    webhook looks live, or the condition is a field key."""
    body = preview_of(
        client,
        "u_admin",
        {
            **WORDS,
            "trigger": {"kind": "webhook", "source": "ticket_closed"},
            "condition": {"field": DUE, "op": "is_over", "value": "7"},
        },
    ).json()

    assert body["fires"] is False
    assert body["nothing_fires"] == NOTHING_FIRES_THIS_YET
    assert body["condition"] == "only when the ticket due by (freshdesk) is more than 7 days ago"
    assert body["trigger"].startswith("Runs when ticket closed is called")
    assert len(body["rehearsal"]) == 1


def test_unfit_words_are_refused_with_every_finding_and_nothing_is_written(
    client: TestClient, authors: Authors
) -> None:
    """A tool the agent may not use, a field nothing reports, a name written as wiring: one 422
    carrying them all. Delete this and a form is corrected one error at a time, or an instruction
    names a tool its agent may not use."""
    answer = preview_of(
        client,
        "u_admin",
        {
            **WORDS,
            "name": "when a ticket arrives then send",
            "tools": ["send_email"],
            "condition": {"field": "freshdesk.ticket.nothing", "op": "equals", "value": "x"},
        },
    )

    assert answer.status_code == 422
    sentences = " ".join(answer.json()["sentences"])
    assert answer.json()["outcome"] == "refused"
    assert "send_email" in sentences
    assert "field none of this install" in sentences
    assert len(answer.json()["sentences"]) >= 3
    assert authors.written == []
    assert preview_of(client, "u_admin").status_code == 200


def test_a_template_start_takes_the_templates_words_when_none_are_given(
    client: TestClient,
) -> None:
    """Start from a named outcome and change only the trigger. Delete this and a template start
    demands every field again, or runs the instruction task."""
    template = BUILT_IN[0]
    body = preview_of(
        client,
        "u_admin",
        {
            "template_id": template.template_id,
            "trigger": {"kind": "schedule", "cadence": {"every": "day", "hour_utc": 5}},
        },
    ).json()

    assert body["name"] == template.name
    assert body["task"] == template.task
    assert body["from_template"] == template.template_id
    assert body["trigger"] == "Runs every day at 05:00 UTC"
    missing = refusal(
        preview_of(
            client, "u_admin", {"template_id": "no_such_template", "trigger": WORDS["trigger"]}
        )
    )
    assert refusal(preview_of(client, "u_admin", agent="no_such_agent")) == missing


# ------------------------------------------------------------------ the write


def test_one_confirmed_request_writes_one_paused_automation_as_the_caller(
    client: TestClient, authors: Authors
) -> None:
    """The write: the digest the preview gave, one row for the caller with no next run and the
    task the words imply, and the caller's reach digest carried. Delete this and the write is
    unconfirmed, written as somebody else, or not paused."""
    asked_for = confirmed(client, "u_admin")
    answer = create_as(client, "u_admin", asked_for)
    body = answer.json()

    assert answer.status_code == 201, answer.text
    assert body["automation_id"] == routes.authored_id(str(asked_for["confirmation"]), "u_admin")
    assert body["runs_as"] == "u_admin"
    assert body["next_run_at"] is None
    assert body["starts_paused"] == IT_STARTS_PAUSED
    assert len(authors.written) == 1
    made = authors.written[0]
    assert made.installation.automation.task == AUTHORED_TASK
    assert made.installation.automation.automation_id == body["automation_id"]
    assert made.installation.installed_by == "u_admin"
    assert made.authored.tools == ("search_tickets",)
    assert len(authors.calls[0]["ent_hash"]) == 32


def test_a_confirmation_for_other_words_is_refused_and_writes_nothing(
    client: TestClient, authors: Authors
) -> None:
    """The digest is over what was shown. Delete this and a request can carry one preview's digest
    to write a different instruction."""
    shown = confirmed(client, "u_admin")
    changed = {**shown, "instruction": "Delete every ticket this agent can reach, and tell nobody."}
    skipped = {**WORDS, "confirmation": "0" * 64}

    for body in (changed, skipped):
        answer = create_as(client, "u_admin", body)
        assert answer.status_code == 409
        assert answer.json()["outcome"] == "unconfirmed"
    assert authors.written == []
    assert create_as(client, "u_admin", shown).status_code == 201


def test_a_request_without_a_digest_never_reaches_the_handler(
    client: TestClient, authors: Authors
) -> None:
    """Validation refuses it before anything is read. Delete this and an unconfirmed write is
    possible by leaving the field out."""
    answer = create_as(client, "u_admin", WORDS)

    assert answer.status_code == 422
    assert authors.written == []


def test_the_caller_cannot_name_who_it_runs_as_or_what_it_reaches(
    client: TestClient, authors: Authors
) -> None:
    """The body has nowhere to say who, so the field is refused as unknown. Delete this and a
    picker for the principal is a way to widen yourself."""
    body = {**confirmed(client, "u_admin"), "runs_as": "u_wide"}

    assert create_as(client, "u_admin", body).status_code == 422
    assert authors.written == []


def test_a_reader_without_the_authority_over_this_task_cannot_write_it(
    client: TestClient, authors: Authors
) -> None:
    """The authority is asked of the agent, the task and the person, before anything is read.
    Delete this and the tab's read is enough."""
    answer = create_as(client, "u_narrow", {**WORDS, "confirmation": "0" * 64})
    missing = refusal(
        create_as(client, "u_admin", {**WORDS, "confirmation": "0" * 64}, "no_such_agent")
    )

    assert refusal(answer) == missing
    assert authors.written == []


def test_the_id_a_confirmation_writes_is_derived_from_it_and_from_who_wrote_it() -> None:
    """So a second press of the same confirmed request meets the key and writes nothing, and two
    people never share an id. Delete this and a retry after a dropped answer writes a second
    automation, or one person's confirmation collides with another's."""
    one = routes.authored_id("a" * 64, "u_admin")

    assert one == routes.authored_id("a" * 64, "u_admin")
    assert one != routes.authored_id("b" * 64, "u_admin")
    assert one != routes.authored_id("a" * 64, "u_other")
    assert one.startswith("auto_") and len(one) == len("auto_") + 32
