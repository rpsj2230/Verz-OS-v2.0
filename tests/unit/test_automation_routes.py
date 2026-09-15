"""A step calls one tool through the gate as its automation's owner, over HTTP, end to end.

The real application, the real registry with real row tools, the real `resolve`, `admit`,
`flow_reach`, `invoke`, projection and redactor. The seams are the ones a deployed process has no
implementation for yet: where grants are loaded from, who is a live principal, and where a
registration is read. The grants are mutable, so revocation is a change to what the store
returns and a bump of the grants version, which is exactly what revocation is here.

The row source hands back every seeded row whatever was asked, as `test_api_routes.py`'s does, so
anything absent from a response was removed by the projection or the redactor.

The route reads the wall clock, so no principal here carries an expiry that could be crossed:
the one engagement that has ended ended in 2019.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.automation_routes import (
    TOOL_CALL_PATH,
    AutomationWiring,
    RegistryToolCaller,
    _request_type,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.identity.oidc import SIGN_IN_PROMPT, KeySet, SigningKey
from brain.knowledge.rows import ID_KEY, RowQuery, RowRequest
from brain.ops.automation_owner import Registration, register
from brain.ops.automation_piece import PieceRefusedError
from brain.tools.registry import ToolRegistry
from brain.tools.startup import build_registry

REGISTERED_AT = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
ENDED = datetime(2019, 1, 1, tzinfo=UTC)
SOURCE = "local"
CANARY_COST = "CANARY-COST-7QXW2"
CANARY_PRICE = "CANARY-PRICE-3KPLM"
PATH = f"{API_PREFIX}{TOOL_CALL_PATH}"

SEEDED_ROWS: tuple[dict[str, Any], ...] = (
    {
        ID_KEY: "p_web_1",
        "sku": "WEB-1001",
        "name": "Managed hosting, small",
        "sell_price": CANARY_PRICE,
        "cost": CANARY_COST,
        "margin": "0.4",
    },
)

EVERY_COLUMN = (
    "read:price_list",
    "read:price_list.sku",
    "read:price_list.name",
    "read:price_list.sell_price",
    "read:price_list.cost",
)


def grants(*capabilities: str) -> tuple[Grant, ...]:
    return tuple(
        Grant(capability=Capability(value=one), scope=Scope.unrestricted()) for one in capabilities
    )


def person(pid: str, *, not_after: datetime | None = None) -> Principal:
    return Principal(
        id=pid,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name=f"Person {pid}",
        primary_department="web",
        not_after=not_after,
    )


# ------------------------------------------------------------------ the seams


class Rows:
    """A `RowSource` returning every seeded row whatever the statement asked for."""

    def __init__(self) -> None:
        self.asked = 0

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        self.asked += 1
        return SEEDED_ROWS


class Grants:
    """An `EntitlementStore` and its `VersionSource` together, because revoking is both."""

    def __init__(self) -> None:
        self.held: dict[str, tuple[Grant, ...]] = {}
        self.version = 1
        self.loads = 0

    def load(self, principal_id: str) -> EntitlementSet:
        self.loads += 1
        return EntitlementSet(principal_id=principal_id, grants=self.held.get(principal_id, ()))

    def grants_version(self, principal_id: str) -> int:
        return self.version

    def revoke_all(self, principal_id: str, *, keep: tuple[str, ...] = ()) -> None:
        self.held[principal_id] = grants(*keep)
        self.version += 1


class Cache:
    """A real cache keyed as `resolve` keys it, so a stale entry would be served if it could be."""

    def __init__(self) -> None:
        self.kept: dict[str, EntitlementSet] = {}

    def get(self, key: str) -> EntitlementSet | None:
        return self.kept.get(key)

    def set(self, key: str, value: EntitlementSet, ttl_seconds: int) -> None:
        self.kept[key] = value


class Records:
    """A `PrincipalRecords`. Removing a principal is disabling or deleting them."""

    def __init__(self, *live: Principal) -> None:
        self.live = {one.id: one for one in live}

    def live_principal(self, principal_id: str) -> Principal | None:
        return self.live.get(principal_id)


class Registrations:
    """A `RegistrationSource`. It has no write method, so a refused call cannot write here."""

    def __init__(self, *kept: Registration) -> None:
        self.kept = {one.automation_id: one for one in kept}
        self.read: list[str] = []

    async def registration(self, automation_id: str) -> Registration | None:
        self.read.append(automation_id)
        return self.kept.get(automation_id)


class Keys:
    """Present only because `GateWiring` holds an authority. The automation route never asks."""

    def keys_for(self, issuer: str, now: datetime) -> KeySet:
        return KeySet(issuer=issuer, keys=(), fetched_at=now)

    def key_for(self, issuer: str, kid: str, now: datetime) -> SigningKey:
        raise AssertionError("the automation route asked a person's key source")


class NoDirectory:
    def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        raise AssertionError("the automation route asked a person's directory")


def refuse_every_signature(*, signing_input: bytes, signature: bytes, key: SigningKey) -> bool:
    return False


class World:
    """One application, its seams, one owner and one automation with a credential."""

    def __init__(self, client: TestClient, app: FastAPI) -> None:
        self.client = client
        self.app = app
        self.rows = Rows()
        self.grants = Grants()
        self.records = Records(person("u_owner"))
        self.grants.held["u_owner"] = grants(*EVERY_COLUMN)
        app.state.tools = build_registry(source=SOURCE, records=self.rows)
        self.tool = next(d.name for d in app.state.tools.definitions() if d.entity == "price_list")
        issued = register(
            automation_id="nightly-prices",
            owner=person("u_owner"),
            declared_tools=frozenset({self.tool}),
            ceiling=EntitlementSet(
                principal_id="nightly-prices",
                grants=grants("read:price_list", "read:price_list.sku", "read:price_list.name"),
            ),
            now=REGISTERED_AT,
        )
        self.registration = issued.registration
        self.credential = issued.credential
        self.registrations = Registrations(self.registration)
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer="https://issuer.invalid/realms/brain",
                audience="brain-api",
                keys=Keys(),
                verify=refuse_every_signature,
                directory=NoDirectory(),
            ),
            versions=self.grants,
            store=self.grants,
            cache=Cache(),
        )
        app.state.automation = AutomationWiring(
            registrations=self.registrations, principals=self.records
        )

    def call(
        self,
        *,
        tool: str | None = None,
        arguments: dict[str, Any] | None = None,
        credential: str | None = None,
    ) -> Any:
        return self.client.post(
            PATH,
            headers={"authorization": f"Bearer {credential or self.credential}"},
            json={"tool": tool or self.tool, "arguments": arguments or {}},
        )


@pytest.fixture
def world() -> Iterator[World]:
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield World(client, app)


def refusal(response: Any) -> tuple[int, str]:
    """What a caller can compare between two refusals: the status and the sentence."""
    return response.status_code, response.json()["message"]


# ------------------------------------------------------------------ the call


def test_a_step_calls_a_tool_through_the_gate_and_receives_only_its_narrowed_reach(
    world: World,
) -> None:
    """The whole path, and the positive case for every refusal below. The owner reads every
    column; the automation declares sku and name. What comes back is the record with sku and name
    and neither the price nor the cost, which were fetched and withheld.

    Delete this and every refusal test in this file passes against a route that refuses
    everything."""
    response = world.call(arguments={"limit": 5})

    assert response.status_code == 200, response.text
    (record,) = response.json()["items"]
    assert record["sku"] == "WEB-1001"
    assert record["name"] == "Managed hosting, small"
    assert CANARY_COST not in response.text
    assert CANARY_PRICE not in response.text
    assert world.rows.asked == 1


def test_the_automations_ceiling_cannot_give_it_what_its_owner_does_not_hold(world: World) -> None:
    """Item 56: never more than the owner may do. The ceiling names the cost and the owner holds
    no grant for it, so the cost is not returned. Delete this and a ceiling becomes a grant
    whoever writes the registration can hand themselves."""
    world.grants.held["u_owner"] = grants("read:price_list", "read:price_list.sku")
    world.registrations.kept["nightly-prices"] = Registration(
        automation_id="nightly-prices",
        owner_principal_id="u_owner",
        credential_digest=world.registration.credential_digest,
        declared_tools=world.registration.declared_tools,
        ceiling=EntitlementSet(principal_id="nightly-prices", grants=grants(*EVERY_COLUMN)),
    )

    response = world.call()

    assert response.status_code == 200, response.text
    (record,) = response.json()["items"]
    assert record["sku"] == "WEB-1001"
    assert "name" not in record
    assert CANARY_COST not in response.text


def test_a_grant_revoked_from_the_owner_is_gone_from_the_next_call(world: World) -> None:
    """Item 56: when the owner loses a permission, the automation loses it at the same moment.
    The first call reads the name; the owner's name grant is deleted and the grants version
    bumped; the second call, with nothing about the automation changed, does not. Delete this
    and the owner's reach can be resolved once and kept."""
    first = world.call()
    world.grants.revoke_all("u_owner", keep=("read:price_list", "read:price_list.sku"))
    second = world.call()

    assert first.status_code == 200 and "name" in first.json()["items"][0]
    assert second.status_code == 200, second.text
    assert "name" not in second.json()["items"][0]


def test_an_owner_who_loses_the_entity_takes_the_tool_away_with_them(world: World) -> None:
    """The same, at the level of the tool: with no grant over the entity the tool is not in the
    catalogue at all, and the answer is the one a tool that does not exist gets. Delete this and
    a revoked owner's automation is told the tool exists and it may not have it."""
    world.grants.revoke_all("u_owner")

    revoked = world.call()
    missing = world.call(tool="local.no_such_tool")

    assert revoked.status_code == 404
    assert refusal(revoked) == refusal(missing)
    assert world.rows.asked == 0


# ------------------------------------------------------------------ the owner gone


@pytest.mark.parametrize("how", ["disabled", "engagement_ended"])
def test_an_automation_whose_owner_has_gone_is_refused_as_an_unknown_one_and_reads_nothing(
    world: World, how: str
) -> None:
    """Item 56: an automation whose owner has gone stops. It is answered exactly as an automation
    nobody registered, and the owner's grants and the rows are never read. Delete this and a
    leaver's automation runs on, or tells whoever holds its credential that its owner has left."""
    if how == "disabled":
        world.records.live.pop("u_owner")
    else:
        world.records.live["u_owner"] = person("u_owner", not_after=ENDED)

    gone = world.call()
    unknown = world.call(credential=world.credential.replace("nightly-prices", "nobody-registered"))

    assert gone.status_code == 401
    assert refusal(gone) == refusal(unknown) == (401, SIGN_IN_PROMPT)
    assert world.grants.loads == 0
    assert world.rows.asked == 0


def test_an_adopted_automation_runs_again_as_its_new_owner(world: World) -> None:
    """The positive sibling of the refusal above: stopping is a state with a way out. Delete
    this and an automation whose owner left is refused for ever, adopted or not."""
    world.records.live.pop("u_owner")
    stopped = world.call()
    world.records.live["u_heir"] = person("u_heir")
    world.grants.held["u_heir"] = grants("read:price_list", "read:price_list.sku")
    world.registrations.kept["nightly-prices"] = Registration(
        automation_id="nightly-prices",
        owner_principal_id="u_heir",
        credential_digest=world.registration.credential_digest,
        declared_tools=world.registration.declared_tools,
        ceiling=world.registration.ceiling,
    )

    resumed = world.call()

    assert stopped.status_code == 401
    assert resumed.status_code == 200, resumed.text
    (record,) = resumed.json()["items"]
    assert record["sku"] == "WEB-1001"
    assert "name" not in record, "the heir's reach, not the previous owner's"


# ------------------------------------------------------------------ one answer each


def test_every_way_a_credential_fails_is_one_answer(world: World) -> None:
    """A malformed credential, a person's token, an API key, no credential, an unknown
    automation, a wrong secret and a gone owner. Delete this and the refusals can come to differ
    by a word, which tells somebody holding a copied credential which part to fix next."""
    wrong_secret = world.credential[:-1] + ("B" if world.credential.endswith("A") else "A")
    attempts = {
        "person_token": world.client.post(
            PATH,
            headers={"authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1In0.c2ln"},
            json={"tool": world.tool, "arguments": {}},
        ),
        "api_key": world.call(credential="brn.handle123.AAAAAAAAAAAAAAAAAAAAAAAA"),
        "no_header": world.client.post(PATH, json={"tool": world.tool, "arguments": {}}),
        "unknown": world.call(credential=world.credential.replace("nightly-prices", "nobody")),
        "wrong_secret": world.call(credential=wrong_secret),
    }
    world.records.live.pop("u_owner")
    attempts["owner_gone"] = world.call()

    answers = {name: refusal(response) for name, response in attempts.items()}

    assert set(answers.values()) == {(401, SIGN_IN_PROMPT)}, answers


def test_a_tool_the_automation_may_not_reach_and_a_tool_that_does_not_exist_are_one_answer(
    world: World,
) -> None:
    """A tool outside the declared set, a tool that does not exist, and arguments the tool will
    not take. Delete this and a flow author can enumerate the catalogue one step at a time."""
    undeclared = next(d.name for d in world.app.state.tools.definitions() if d.name != world.tool)

    answers = {
        refusal(world.call(tool=undeclared)),
        refusal(world.call(tool="local.no_such_tool")),
        refusal(world.call(arguments={"limit": 0})),
    }

    assert len(answers) == 1
    ((status, _),) = answers
    assert status == 404
    assert world.rows.asked == 0


def test_a_process_with_no_automation_wiring_refuses_every_credential(world: World) -> None:
    """A deployed process has none today. Delete this and the absence of a registration source
    could read as authentication being switched off."""
    world.app.state.automation = None

    assert refusal(world.call()) == (401, SIGN_IN_PROMPT)
    assert world.rows.asked == 0


def test_a_declared_tool_whose_entity_has_no_field_policy_is_refused_as_unavailable(
    world: World,
) -> None:
    """The document tools have no field classification, so nothing says which of a passage's
    fields this owner may be shown, and a step asking for one is refused with the one sentence
    rather than answered through an empty policy. The owner holds the capability and the
    automation declares it, so this is the only thing refusing. Delete this and an unclassified
    entity reaches the redactor with no policy, which faults, or with an invented one."""
    search = next(
        d for d in world.app.state.tools.definitions() if d.name.endswith(".search_documents")
    )
    world.grants.held["u_owner"] = grants(search.required_capability)
    world.registrations.kept["nightly-prices"] = Registration(
        automation_id="nightly-prices",
        owner_principal_id="u_owner",
        credential_digest=world.registration.credential_digest,
        declared_tools=frozenset({search.name}),
        ceiling=EntitlementSet(
            principal_id="nightly-prices", grants=grants(search.required_capability)
        ),
    )

    unclassified = world.call(tool=search.name, arguments={"question": "hosting"})

    assert refusal(unclassified) == refusal(world.call(tool="local.no_such_tool"))
    assert unclassified.status_code == 404
    assert world.rows.asked == 0


# ------------------------------------------------------------------ calling a registered handler


async def untyped_handler(
    request: dict[str, Any], *, entitlement: EntitlementSet, now: datetime | None
) -> None:
    raise AssertionError("a handler whose request is not a model was called")


async def keyword_only_handler(*, entitlement: EntitlementSet, now: datetime | None) -> None:
    raise AssertionError("a handler with no request parameter was called")


def test_the_request_model_is_read_off_the_handlers_first_parameter() -> None:
    """A row handler's first parameter is `RowRequest`, and a handler with no positional
    parameter, or one annotated with something that is not a model, has no request model.
    Delete this and a step's argument bag can be handed to a handler as a raw dictionary."""
    registry = build_registry(source=SOURCE, records=Rows())
    row_tool = next(d for d in registry.definitions() if d.entity == "price_list")

    assert _request_type(registry.get(row_tool.name).handler) is RowRequest
    assert _request_type(untyped_handler) is None
    assert _request_type(keyword_only_handler) is None


class OneHandler:
    """Stands in for a registry holding one handler, which no registered tool here can be."""

    def __init__(self, handler: Any) -> None:
        self.handler = handler

    def get(self, name: str) -> OneHandler:
        return self


@pytest.mark.parametrize("handler", [untyped_handler, keyword_only_handler])
def test_a_handler_with_no_request_model_is_refused_before_it_is_called(handler: Any) -> None:
    """Every tool the application registers today takes a model, so this is reached only by a
    handler registered later. Delete this and that handler is called with a dictionary nobody
    validated, or the route faults."""
    definition = next(
        d for d in build_registry(source=SOURCE, records=Rows()).definitions() if d.entity
    )
    caller = RegistryToolCaller(cast(ToolRegistry, OneHandler(handler)))

    with pytest.raises(PieceRefusedError):
        caller.call(
            tool=definition,
            arguments={"limit": 1},
            entitlement=EntitlementSet(principal_id="u_owner"),
            now=None,
        )
