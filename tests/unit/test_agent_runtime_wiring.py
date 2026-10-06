"""How the answer route hands an agent to the runtime, and what it does when a run is stopped.

Over `brain.api_routes.agent_runtime_for`, `reach_again` and `answered_for`'s halted branch. The
loop itself is `tests/unit/test_agent_runtime.py`.

Task ids: M13.7.1, M13.8.2, M13.7.6
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
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
from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.gate.injection import AutonomyTier
from brain.gate.leash import Leash, LeashEntry
from brain.gate.runtime import AgentRuntime, RunHaltedError
from brain.gate.screening import NOTHING_MATCHED
from brain.identity.oidc import TokenRefusal, TokenRefusedError
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


def test_a_caller_nothing_can_resolve_keeps_its_admitted_reach() -> None:
    """**A_CALLER_NOTHING_CAN_RESOLVE_KEEPS_ITS_ADMITTED_REACH.** A principal that is not a person
    with no authenticated caller is not re-resolved by id, which would drop whatever narrowed it.
    Delete this and such a run reads at its principal's whole reach."""
    question = asking(PrincipalKind.SERVICE)

    assert _again(question, wired=True) is question.reach


def _wired() -> Any:
    wiring = api_routes.GateWiring(
        authority=cast(Any, None),
        versions=cast(Any, None),
        store=cast(Any, None),
        cache=cast(Any, None),
    )
    return cast(Any, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(gate=wiring))))


def _again(question: api_routes.Answering, *, wired: bool) -> EntitlementSet:
    request = _wired() if wired else REQUEST

    async def resolved() -> EntitlementSet:
        return await api_routes.reach_again(request, question)(NOW)

    return asyncio.run(resolved())


def test_an_authenticated_caller_is_resolved_again_as_the_route_resolved_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**EVERY_CALLER_IS_RESOLVED_AGAIN_BEFORE_EACH_TOOL_CALL.** A caller the route authenticated,
    a service account included, is resolved again through `reach_of`, so a grant revoked since the
    run started is gone at the next call. Delete this and an account's revoked grant keeps
    working until the run's wall clock ends."""
    narrowed = EntitlementSet(
        principal_id="u_asker",
        grants=(Grant(capability=Capability(value="read:knowledge"), scope=Scope.unrestricted()),),
    )

    async def now_holds(caller: object, wiring: object, now: datetime) -> EntitlementSet:
        return narrowed

    monkeypatch.setattr(api_routes, "reach_of", now_holds)
    question = replace(
        asking(PrincipalKind.SERVICE),
        caller=cast(Any, SimpleNamespace(assurance=Assurance.AUTHENTICATED)),
    )

    again = _again(question, wired=True)

    assert again.holds(Capability(value="read:knowledge"), NOW)
    assert not again.holds(Capability(value="read:note.title"), NOW)


def test_an_account_whose_owner_has_gone_reaches_nothing_for_the_rest_of_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`reach_of` refuses an account whose owner is no longer active; mid-run that is a reach of
    nothing rather than a fault. Delete this and the run either fails a person who was being
    answered or keeps reading for an owner who is gone."""

    async def gone(caller: object, wiring: object, now: datetime) -> EntitlementSet:
        raise TokenRefusedError(TokenRefusal.OWNER_INACTIVE, "acct")

    monkeypatch.setattr(api_routes, "reach_of", gone)
    question = replace(
        asking(PrincipalKind.SERVICE),
        caller=cast(Any, SimpleNamespace(assurance=Assurance.AUTHENTICATED)),
    )

    assert _again(question, wired=True).grants == ()


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


# ------------------------------------------------------ a write the agent may ask for (M13.7.6)
class _NoRows:
    """What `session.execute(...)` returns for an agent with no install row."""

    def one_or_none(self) -> None:
        return None


class _OneSession:
    async def __aenter__(self) -> _OneSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def execute(self, statement: object) -> _NoRows:
        del statement
        return _NoRows()


def _stored(*, suspensions: bool = True) -> Any:
    """A request over a process with a database and, unless told not, a suspension store."""
    from brain.gate.suspension_store import StoredSuspensions

    sessions = cast(Any, lambda: _OneSession())
    state = SimpleNamespace(
        db_sessions=sessions,
        suspensions=StoredSuspensions(sessions) if suspensions else None,
    )
    return cast(Any, SimpleNamespace(app=SimpleNamespace(state=state)))


def _replying() -> AgentRecord:
    from tests.unit.test_runtime_side_effects import DESK_AGENT, DESK_CAPABILITIES, REPLY, agent_for

    return agent_for(
        DESK_AGENT,
        DESK_CAPABILITIES,
        ("freshdesk.read_ticket", REPLY),
        connectors=("freshdesk",),
    )


def test_an_agent_that_may_ask_for_a_write_is_handed_its_leash_and_a_place_to_hold_it() -> None:
    """**`AN_AGENT_THAT_MAY_ASK_FOR_A_WRITE_IS_GIVEN_ITS_LEASH_AND_A_PLACE_TO_HOLD_IT`.** An agent
    whose ceiling names the reply is handed side effects over the install's connections and its
    suspension store, and the loop then offers it the write beside the read; an agent that names no
    write is handed nothing, so it is run as it was. Delete this and the runtime can hold a write
    in tests and in no process, which is the mechanism correct, tested and never called."""
    from brain.gate.runtime_effects import ConnectorSideEffects
    from tests.unit.test_runtime_side_effects import (
        DESK_CAPABILITIES,
        REPLY,
        SUPPORT_SCOPE,
        desk_registry,
        holding,
    )

    reach = holding(*DESK_CAPABILITIES, principal="u_asker", scope=SUPPORT_SCOPE)
    question = replace(asking(), reach=reach)
    desk = desk_registry()

    _, effects = asyncio.run(
        api_routes.side_effects_for(_stored(), agent=_replying(), registry=desk)
    )
    leash = Leash(
        entries=(
            LeashEntry(
                agent_id="support_desk",
                target="ticket",
                scope=Scope.unrestricted(),
                rung=AutonomyTier.ASSISTED,
            ),
        )
    )
    runtime = api_routes.agent_runtime_for(
        _stored(),
        agent=_replying(),
        asking=question,
        registry=desk,
        assessment=NOTHING_MATCHED,
        leash=leash,
        side_effects=effects,
    )

    assert isinstance(effects, ConnectorSideEffects)
    assert isinstance(runtime, AgentRuntime) and runtime.side_effects is effects
    assert runtime.leash == leash
    assert REPLY in {one.name for one in desk.definitions()}
    reading = agent("notes.read_note")
    assert asyncio.run(
        api_routes.side_effects_for(_stored(), agent=reading, registry=registry())
    ) == (
        Leash(),
        None,
    )


def test_a_process_with_nowhere_to_hold_a_write_offers_none() -> None:
    """With no database, or a database and no suspension store, an agent that names the reply is
    handed no side effects and an empty leash, so the write is never offered and nothing is
    prepared that cannot be held. Delete this and a process offers a write it can only fail."""
    from tests.unit.test_runtime_side_effects import desk_registry

    for request in (REQUEST, _stored(suspensions=False)):
        assert asyncio.run(
            api_routes.side_effects_for(request, agent=_replying(), registry=desk_registry())
        ) == (Leash(), None)
