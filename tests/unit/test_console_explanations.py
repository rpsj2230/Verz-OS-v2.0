"""The sentences that explain what the console cannot offer: shape, expiry and route.

`brain.console.explanations` holds every sentence a console screen draws when an act cannot be
done, `brain.explanation_routes` serves one, and `console/src/components/kit/explanation.tsx` draws
it. These tests hold the three properties a reviewer must not be able to break: a sentence has one
shape of identifier and is written in the house register; a sentence about a route that does not
exist yet is retired the day the route does; and the route answers every reader the same bytes.

Task ids: M27.15.70
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.explanations import (
    ACT_SHAPE,
    BY_ACT,
    EXPLANATIONS,
    NOT_YET,
    SOON,
    Form,
    Lead,
    explanation_for,
    retired_by_a_route,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import Directory, Keys, NoCache, Versions, token_for, verifier

PATH = f"{API_PREFIX}/console/explanations"

#: The two dashes the house style forbids, written as code points so this file holds neither.
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)

#: A route that, mounted, would make the sentence of the act untrue. Written here and not derived
#: from the expression, because a test that builds its example out of the pattern is satisfied by
#: any pattern.
A_ROUTE_THAT_WOULD_RETIRE_IT: dict[str, str] = {
    "agent.browser": f"{API_PREFIX}/agents/{{agent_id}}/browser",
    "learning.promote": f"{API_PREFIX}/govern/learning/promote",
    "learning.decide": f"{API_PREFIX}/govern/learning/decisions",
    "operations.stop_run": f"{API_PREFIX}/jobs/{{name}}/stop",
    "operations.import_data": f"{API_PREFIX}/data-transfer/imports",
    "template.author": f"{API_PREFIX}/agent-templates/publish",
    "automation.reinstate": f"{API_PREFIX}/automations/{{automation_id}}/reinstate",
    "channel.verify": f"{API_PREFIX}/channels/{{name}}/verify",
    "credential.check_source": f"{API_PREFIX}/connectors/{{connector}}/test",
    "knowledge.export_inventory": f"{API_PREFIX}/knowledge/inventory",
    "service_account.change_end": f"{API_PREFIX}/govern/service-accounts/{{client_id}}/end",
    "skill.try_out": f"{API_PREFIX}/skills/{{digest}}/rehearsal",
}

#: A neighbouring route that must NOT retire it, so a pattern that matches everything is caught.
A_ROUTE_THAT_MUST_NOT: dict[str, str] = {
    "automation.reinstate": f"{API_PREFIX}/automations/{{automation_id}}/remove",
    "operations.stop_run": f"{API_PREFIX}/jobs/{{name}}/pause",
    "learning.promote": f"{API_PREFIX}/govern/learning/undo",
}


def served_paths() -> tuple[str, ...]:
    """Every path the real application mounts, in its own OpenAPI description."""
    app = create_app(Settings(env="development", database_url="", run_migrations=False))
    return tuple(app.openapi().get("paths", {}))


def test_every_explanation_has_one_shape_of_id_and_is_written_in_the_house_register() -> None:
    """Ids are unique and shaped `noun.act`; a sentence is not empty, uses no dash a person would
    read as an em dash, ends where a sentence ends, and an action leads with whether it is coming
    or not available.

    Delete this and an id can be written twice (the second silently losing), a sentence can
    contain a dash the house style forbids everywhere, or an action can drop its lead and read as
    a fact about the product."""
    acts = [one.act for one in EXPLANATIONS]
    assert len(acts) == len(set(acts)), "an act is registered twice"
    assert len(EXPLANATIONS) >= 35, "the registry is not the whole set the console drew"
    for one in EXPLANATIONS:
        assert ACT_SHAPE.match(one.act), one.act
        assert one.sentence.strip() == one.sentence and one.sentence != "", one.act
        assert EM_DASH not in one.sentence and EN_DASH not in one.sentence, one.act
        if one.form is Form.ACTION:
            assert one.sentence.startswith((SOON, NOT_YET)), one.act
            assert one.lead is Lead.NONE, one.act
        if one.form is Form.LINE:
            assert one.lead is Lead.NONE, one.act
        if one.form is Form.NOTE:
            assert one.lead is not Lead.NONE, one.act
            assert not one.sentence.startswith((SOON, NOT_YET)), one.act


def test_an_action_that_names_a_route_names_one_that_does_not_exist_yet() -> None:
    """Every explanation with an expiry is retired by an example route written out by hand, is not
    retired by the neighbouring route that must not, and is retired by no route the application
    mounts today.

    Delete this and a sentence can go on saying coming soon about a route that has landed, which
    is the statement the product makes falsely and the reason the sentence lives on the server."""
    with_expiry = {one.act for one in EXPLANATIONS if one.retired_by != ""}
    assert with_expiry == set(A_ROUTE_THAT_WOULD_RETIRE_IT), (
        "an expiry has no example, or an example no expiry"
    )
    mounted = served_paths()
    for act, example in A_ROUTE_THAT_WOULD_RETIRE_IT.items():
        one = BY_ACT[act]
        assert retired_by_a_route(one, (example,)), f"{act} is not retired by {example}"
        assert not retired_by_a_route(one, mounted), (
            f"{act} says a route is not there, and one that retires it is mounted"
        )
    for act, neighbour in A_ROUTE_THAT_MUST_NOT.items():
        assert not retired_by_a_route(BY_ACT[act], (neighbour,)), f"{act} matches {neighbour}"


def test_an_explanation_without_an_expiry_is_retired_by_nothing() -> None:
    """A sentence about something the product deliberately does not offer has no route that
    retires it, and `retired_by_a_route` says so for any path at all.

    Delete this and an empty expression can become a pattern that matches every path, retiring
    every deliberate refusal the moment any route is mounted."""
    one = BY_ACT["role.not_edited"]
    assert one.retired_by == ""
    assert not retired_by_a_route(one, (f"{API_PREFIX}/roles", PATH, ""))


def test_an_unregistered_act_has_no_explanation() -> None:
    """Looking up an id nobody registered answers none, and a registered one answers itself.

    Delete this and the lookup can answer a default sentence for any id, which would make the
    route an oracle that says every act exists."""
    assert explanation_for("nobody.registered_this") is None
    assert explanation_for("role.not_edited") is BY_ACT["role.not_edited"]


# --------------------------------------------------------------------------- over the wire


class TwoReaders:
    """An `EntitlementStore`: one reader holds nothing, the other holds one grant."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        if principal_id == "u_wide":
            return EntitlementSet(
                principal_id=principal_id,
                grants=(
                    Grant(capability=Capability(value="read:release"), scope=Scope.unrestricted()),
                ),
            )
        return EntitlementSet(principal_id=principal_id, grants=())


@pytest.fixture
def client() -> Iterator[TestClient]:
    """The real application, so the route is proved mounted as well as correct."""
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer="https://id.verz.example/realms/brain",
                audience="brain-api",
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=TwoReaders(),
            cache=NoCache(),
        )
        yield c


def ask(c: TestClient, pid: str, act: str) -> Response:
    token = token_for(pid, claims={"amr": ["otp"]})
    response: Response = c.get(f"{PATH}/{act}", headers={"authorization": f"Bearer {token}"})
    return response


def test_the_route_answers_a_reader_who_holds_nothing_and_one_who_holds_a_grant_the_same_bytes(
    client: TestClient,
) -> None:
    """The sentence for an act is byte-identical for a reader holding nothing and a reader holding
    a grant, and is the registered sentence with its form and lead.

    Delete this and the answer can start to differ by grants, which is a refusal that can be told
    apart from an absence: the rule `THE_SAME_SENTENCE_FOR_EVERY_READER` states."""
    for one in EXPLANATIONS[:: max(1, len(EXPLANATIONS) // 6)]:
        nothing = ask(client, "u_none", one.act)
        wide = ask(client, "u_wide", one.act)
        assert nothing.status_code == 200 and wide.status_code == 200, one.act
        assert nothing.content == wide.content, one.act
        body: dict[str, Any] = nothing.json()
        assert body == {
            "act": one.act,
            "form": one.form.value,
            "lead": one.lead.value,
            "sentence": one.sentence,
        }


def test_the_route_does_not_serve_the_expiry_pattern(client: TestClient) -> None:
    """The body carries the act, form, lead and sentence and no `retired_by`, which is how the
    server decides a sentence is stale and is nothing a browser needs.

    Delete this and the registry's internals can leak onto the wire one field at a time."""
    body = ask(client, "u_none", "learning.promote").json()
    assert set(body) == {"act", "form", "lead", "sentence"}


def test_an_unregistered_act_is_the_ordinary_not_found_and_an_anonymous_request_is_refused(
    client: TestClient,
) -> None:
    """An id nobody registered answers 404, the same as any absent thing, and a request with no
    token is refused before the lookup.

    Delete this and the route can become a public page, or answer a placeholder for any id."""
    assert ask(client, "u_none", "nobody.registered_this").status_code == 404
    anonymous: Response = client.get(f"{PATH}/role.not_edited")
    assert anonymous.status_code == 401
