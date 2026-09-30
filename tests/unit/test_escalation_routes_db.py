"""The escalation routes over HTTP against PostgreSQL: naming a queue's person, and each list.

Driven through the application's own routes as the application role, signed in with chosen grants
that the grant table holds as well, for the reason `tests/unit/test_knowledge_lifecycle_db.py`
gives. The answer path that files and sends a handoff is proved end to end by the install check
(`tests/unit/test_acceptance_escalation.py`); what is here is the naming form and the two lists.

Naming is asked of the Compliance screen's authority and refused, as the screen's other forms are,
to anybody without it; a channel nothing can be sent on and a person who is not here are refused in
a sentence. The caller's list shows what they asked with the sentence they are told, and what was
handed to them with who asked, the question, what was tried and what is needed; a third person sees
neither.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is, and without pgvector.

Task ids: M8.3.2, M8.3.4
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Final

import httpx
import pytest

from brain.api import API_PREFIX
from brain.app import Settings, create_app, suspension_store_for
from brain.compliance_routes import COMPLIANCE_AUTHORITY
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.escalation_routes import ESCALATIONS_PATH, ROUTES_PATH, TOLD
from brain.gate.abstain import ESCALATION_TEXT, EscalationRoute
from brain.gate.context import Channel
from brain.gate.escalating import escalation_for
from brain.ops.escalation_store import StoredEscalations
from brain.session import make_session_factory
from brain.tools.skills import skill_from_markdown
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.knowledge_items import a_person
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import admin_url, run, sql
from tests.unit.test_automation_owner_store import app_engine

pytestmark = pytest.mark.needs_db

#: Names the queue's person on the Compliance screen.
ADMIN: Final = "u_admin"
#: Asks, and is handed nothing.
ASKER: Final = "u_narrow"
#: Is named for the queue.
PERSON: Final = "u_wide"
#: Neither asks nor is named.
OTHER: Final = "u_elsewhere"

QUEUE: Final = "pricing"
NEEDS: Final = "Somebody who can quote outside the price list"
WHOLE: Final = Scope.unrestricted()

GRANTS: Final[dict[str, tuple[Grant, ...]]] = {
    ADMIN: (Grant(capability=COMPLIANCE_AUTHORITY, scope=WHOLE),),
    ASKER: (),
    PERSON: (),
    OTHER: (),
}

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


@contextmanager
def company(name: str) -> Iterator[str]:
    """A database at head holding four people and their grants."""
    if not has_pgvector(admin_url()):
        pytest.skip("the chain to head needs pgvector, which CI's server has")
    with retirable(name) as url:
        for person, grants in GRANTS.items():
            a_person(url, person)
            for grant in grants:
                sql(
                    url,
                    "INSERT INTO gate.capability_grant "
                    "(principal_id, capability, scope, granted_by, reason) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    person,
                    grant.capability.value,
                    json.dumps(grant.scope.model_dump(mode="json")),
                    "u_seed",
                    "loaded by the test fixture",
                )
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The application's own routes as the application role."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = make_session_factory(built)
            app.state.suspensions = suspension_store_for(app.state.db_sessions)
            app.state.console_reads = None
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def api(path: str) -> str:
    return f"{API_PREFIX}{path}"


def filed(url: str) -> None:
    """One handoff from the asker, filed as the answer path files it."""
    skill = skill_from_markdown(
        "\n".join(
            [
                "---",
                "name: quote-desk",
                "description: Use when a client asks for a price the list does not hold",
                f"escalate_to: {QUEUE}",
                f"escalation_needs: {NEEDS}",
                "---",
                "Hand it on.",
            ]
        )
    )
    escalation = escalation_for(
        skill,
        route=EscalationRoute(queue=QUEUE, channel=Channel.CONSOLE),
        asker_id=ASKER,
        question="What does the premium plan cost for a charity?",
        trace_ref="t-routes",
        now=LONG_AGO,
    )

    async def go() -> None:
        engine = app_engine(url)
        try:
            store = StoredEscalations(make_session_factory(engine))
            await store.file(
                escalation, skill_name=skill.name, agent_id="agent_quotes", ent_hash="0" * 32
            )
        finally:
            await engine.dispose()

    run(go)


async def name(client: httpx.AsyncClient, by: str, body: dict[str, Any]) -> httpx.Response:
    return await client.put(api(f"{ROUTES_PATH}/{QUEUE}"), json=body, headers=headers(by))


def test_a_queue_s_person_is_named_by_the_compliance_authority_and_nobody_else() -> None:
    """The form's refusals and its write. Delete this and anybody signed in can reroute every
    question a skill hands on to themselves, or name a channel nothing sends on, or a person who
    is not here, and each reads as a queue with somebody behind it."""
    body = {"person": PERSON, "channel": "webhook", "address": "pricing-desk"}
    with company("brain_m83_routes") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            return {
                "by_asker": await name(client, ASKER, body),
                "no_wire": await name(client, ADMIN, {**body, "channel": "scheduler"}),
                "nobody": await name(client, ADMIN, {**body, "person": "u_nobody_at_all"}),
                "named": await name(client, ADMIN, body),
                "listed": await client.get(api(ROUTES_PATH), headers=headers(ADMIN)),
                "listed_by_asker": await client.get(api(ROUTES_PATH), headers=headers(ASKER)),
            }

        said = pressed(url, presses)
        ledger = sql(
            url,
            "SELECT actor_id FROM obs.audit_entry WHERE subject = %s",
            f"setting:escalation_route.{QUEUE}",
        )

    assert said["by_asker"].status_code == said["listed_by_asker"].status_code == 404
    for refused in ("no_wire", "nobody"):
        assert said[refused].status_code == 404, said[refused].text
        assert said[refused].json()["message"].startswith("that was not recorded:")
    assert said["named"].status_code == 200, said["named"].text
    assert (said["named"].json()["person"], said["named"].json()["channel"]) == (PERSON, "webhook")
    listed = said["listed"].json()
    assert [(one["queue"], one["person"], one["address"]) for one in listed["routes"]] == [
        (QUEUE, PERSON, "pricing-desk")
    ]
    assert "webhook" in listed["channels"] and "scheduler" not in listed["channels"]
    assert ledger == [(ADMIN,)]


def test_the_asker_and_the_named_person_each_see_their_half_and_nobody_else_sees_either() -> None:
    """Delete this and the list can show the named person's handoffs to the asker, which names who
    answers for a queue, or the asker's question to a third person."""
    body = {"person": PERSON, "channel": "webhook", "address": "pricing-desk"}
    with company("brain_m83_lists") as url:

        async def naming(client: httpx.AsyncClient) -> httpx.Response:
            return await name(client, ADMIN, body)

        assert pressed(url, naming).status_code == 200
        filed(url)

        async def lists(client: httpx.AsyncClient) -> dict[str, Any]:
            return {
                who: (await client.get(api(ESCALATIONS_PATH), headers=headers(who))).json()
                for who in (ASKER, PERSON, OTHER)
            }

        said = pressed(url, lists)

    asker, person, other = said[ASKER], said[PERSON], said[OTHER]
    assert asker["told"] == TOLD and asker["handed"] == []
    [asked] = asker["asked"]
    assert (asked["queue"], asked["expired"]) == (QUEUE, False)
    assert asked["said"] == ESCALATION_TEXT.format(queue=QUEUE)
    assert PERSON not in json.dumps(asker)
    assert person["asked"] == []
    [handed] = person["handed"]
    assert (handed["asker_id"], handed["asker_name"], handed["needed"]) == (ASKER, ASKER, NEEDS)
    assert handed["question"] == "What does the premium plan cost for a charity?"
    assert handed["tried"] == ["answer.searched_at_the_askers_reach", "skill.quote_desk"]
    assert other == {"asked": [], "handed": [], "told": TOLD}
