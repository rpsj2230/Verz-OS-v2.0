"""How the answer route hands an agent to the runtime, and what it does when a run is stopped.

Over `brain.api_routes.agent_runtime_for`, `reach_again` and `answered_for`'s halted branch. The
loop itself is `tests/unit/test_agent_runtime.py`.

Task ids: M13.7.1, M13.8.2
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

import brain.api_routes as api_routes
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.gate.runtime import AgentRuntime, RunHaltedError
from brain.gate.screening import NOTHING_MATCHED
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY, SEARCH_DOCUMENTS
from brain.knowledge.visibility import Visibility
from brain.tools.registry import ToolRegistry
from tests.unit.test_answer_route_model import client as client
from tests.unit.test_answer_route_model import transport as transport
from tests.unit.test_model_calls import Scripted

#: Far from any wall clock: nothing here is about the present.
NOW = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)


class Note(Entity):
    title: str = ""


def a_handler() -> TypedResult[Note]:
    return TypedResult[Note]()


def _definition(name: str, entity: str, capability: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"does {name}",
        entity=entity,
        required_capability=capability,
        side_effect=SideEffect.NONE,
        identity_mode=IdentityMode.DELEGATED,
    )


def registry() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(_definition(SEARCH_DOCUMENTS, KNOWLEDGE_ENTITY, "read:knowledge"), a_handler)
    tools.register(_definition("notes.read_note", "note", "read:note.title"), a_handler)
    return tools.freeze()


def agent(*tools: str) -> AgentRecord:
    return AgentRecord(
        agent_id="pricing_desk",
        display_name="Pricing desk",
        persona="Answers about prices.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(
            scope=Scope.unrestricted(),
            capabilities=(Capability(value="read:knowledge"), Capability(value="read:note.title")),
            allowed_tools=frozenset(tools),
        ),
        created_by="u_steward",
    )


def asking(kind: PrincipalKind = PrincipalKind.HUMAN) -> api_routes.Answering:
    person = Principal(
        id="u_asker",
        kind=kind,
        employment=Employment.STAFF,
        display_name="Asker",
    )
    reach = EntitlementSet(
        principal_id="u_asker",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in ("read:knowledge", "read:note.title")
        ),
    )
    return api_routes.Answering(principal=person, reach=reach, channel=Channel.CONSOLE, now=NOW)


REQUEST = cast(Any, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db_sessions=None))))


def test_an_agent_that_only_searches_documents_keeps_the_passage_step() -> None:
    """**AN_AGENT_WITH_A_TOOL_BEYOND_THE_PASSAGE_SEARCH_RUNS_THE_LOOP, the half that changes
    nothing.** An agent whose catalogue is the document search alone is answered as it was.
    Delete this and every knowledge agent moves to the loop with nobody having decided it."""
    found = api_routes.agent_runtime_for(
        REQUEST,
        agent=agent(SEARCH_DOCUMENTS),
        asking=asking(),
        registry=registry(),
        assessment=NOTHING_MATCHED,
    )

    assert found is None


def test_an_agent_offering_another_read_tool_runs_the_loop() -> None:
    """The sibling: a read tool beyond the search hands the run to the runtime, at the asker's
    admitted reach. Delete this and the selection can refuse every agent and the runtime is
    never reached from the route."""
    question = asking()

    found = api_routes.agent_runtime_for(
        REQUEST,
        agent=agent(SEARCH_DOCUMENTS, "notes.read_note"),
        asking=question,
        registry=registry(),
        assessment=NOTHING_MATCHED,
    )

    assert isinstance(found, AgentRuntime)
    assert found.asker is question.reach


def test_an_account_s_run_keeps_the_reach_it_was_admitted_at() -> None:
    """**A_PERSON_IS_RESOLVED_AGAIN_AND_AN_ACCOUNT_IS_NOT.** A service account's reach is not
    re-resolved by principal id, which would ignore the account's own narrowing and widen it.
    Delete this and an account's run can read at its principal's whole reach."""
    question = asking(PrincipalKind.SERVICE)

    async def resolved() -> EntitlementSet:
        return await api_routes.reach_again(REQUEST, question)(NOW)

    again = asyncio.run(resolved())

    assert again is question.reach


@pytest.mark.usefixtures("transport")
def test_a_stopped_run_is_answered_as_a_halted_question(
    client: TestClient, transport: Scripted, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run the halt store stopped reaches the person as the 503 a halted question is, in the
    halt's sentence. Delete this and a stopped agent's run surfaces as a 500 or as an answer."""
    from tests.fixtures.console_http import headers
    from tests.unit.test_answer_route_model import READER

    async def stopped(*args: object, **kwargs: object) -> object:
        raise RunHaltedError("Stopped by an administrator.")

    monkeypatch.setattr(api_routes, "answer_lane", stopped)

    answered = client.post(
        "/api/v1/answer", headers=headers(READER), json={"question": "how much annual leave"}
    )

    assert answered.status_code == 503
    assert answered.json()["message"] == "Stopped by an administrator."
    assert transport.sent == []
