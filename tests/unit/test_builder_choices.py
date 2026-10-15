"""A department's builder is offered only what their department holds (M13.9.2).

The pure half holds `brain.builder.choices` to the catalogue's own answer over a registry of two
sources, and the route half serves the real builder form to a Super Admin, to an administrator of a
department that reads one source and to one that reads none.

Task ids: M13.9.2
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.agent_builder_routes import FORM_PATH
from brain.agents.creation import AGENT_INSTALL_CAPABILITY
from brain.app import Settings, create_app
from brain.builder.choices import (
    THE_OFFER_IS_WHAT_YOUR_DEPARTMENT_HOLDS,
    Choices,
    held_choices,
    limited_to_a_department,
    offered,
)
from brain.builder.form import form_document
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from tests.fixtures.console_http import gate_wiring
from tests.unit.test_agent_builder_routes import GALLERY, GRANTS, Console, Memory, everybody
from tests.unit.test_agent_lifecycle_routes import an_invoice, tools
from tests.unit.test_agent_routes import KEY

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2019, 6, 1, 9, 0, tzinfo=UTC)
WEB = Scope.department("web")
EVERYWHERE = Scope.unrestricted()
READS = Capability(value="read:invoice.reference")


def holding(*grants: Grant) -> EntitlementSet:
    return EntitlementSet(principal_id="u_builder", grants=grants)


def builds(scope: Scope) -> Grant:
    return Grant(capability=AGENT_INSTALL_CAPABILITY, scope=scope)


def test_only_a_builder_holding_the_authority_in_a_department_is_limited_to_one() -> None:
    """Over everything is not limited, in a department is, and holding no install authority at all
    is not either, because that reader is held to the personal-agent rule and not to this one.

    Delete this and a Super Admin is cut to what they hold, which refuses them the flow where a
    colleague who holds more approves what they name."""
    assert limited_to_a_department(holding(builds(WEB)), NOW)
    assert not limited_to_a_department(holding(builds(EVERYWHERE)), NOW)
    assert not limited_to_a_department(holding(), NOW)


def test_the_choices_are_the_tools_the_catalogue_admits_and_the_sources_they_belong_to() -> None:
    """A reader who reads invoices in their department holds both sources' invoice tools, and a
    reader who reads nothing holds neither. The answer is `brain.gate.catalogue.project`'s.

    Delete this and the choices are computed by something other than the catalogue, which is a
    second opinion about who may reach what."""
    registry = tools("books", "ledger")
    reads = holding(builds(WEB), Grant(capability=READS, scope=EVERYWHERE))

    assert held_choices(registry, reads, NOW) == Choices(
        tools=("books.read_invoice", "ledger.read_invoice"), connectors=("books", "ledger")
    )
    assert held_choices(registry, holding(builds(WEB)), NOW) == Choices(tools=(), connectors=())


def _entries(document: dict[str, Any]) -> dict[str, Any]:
    """Each cut field's `items` and bounds, by manifest path."""
    found: dict[str, Any] = {}
    for section in document["sections"]:
        properties = section["schema"]["properties"]
        for name, fragment in properties.get("authority", {}).get("properties", {}).items():
            if name in ("allowed_tools", "required_tools"):
                found[f"authority.{name}"] = fragment
        if "connectors" in properties:
            found["connectors"] = properties["connectors"]
    return found


def test_the_form_is_cut_to_the_choices_and_the_model_description_is_not_touched() -> None:
    """Tools and connectors carry an enum of the choices, a list with nothing to choose has no room
    in it, and the document `form_document` returns is the same afterwards.

    Delete this and the cut is made on the model's own description, which the console's fixture is
    held equal to, or a department holding nothing is served an enum JSON Schema refuses."""
    whole = form_document()
    before = repr(whole)

    cut = _entries(offered(whole, Choices(tools=("a.read",), connectors=("a",))))
    none = _entries(offered(whole, Choices(tools=(), connectors=())))

    assert cut["authority.allowed_tools"]["items"]["enum"] == ["a.read"]
    assert cut["authority.allowed_tools"]["uniqueItems"] is True
    assert cut["authority.required_tools"]["items"]["enum"] == ["a.read"]
    assert cut["connectors"]["items"]["enum"] == ["a"]
    assert all("enum" not in one["items"] and one["maxItems"] == 0 for one in none.values())
    assert repr(whole) == before
    assert "enum" not in _entries(whole)["connectors"]["items"]


@pytest.fixture
def console() -> Iterator[Console]:
    """The real application, with a two-source registry and a department builder who reads
    invoices (`u_elsewhere` here, the one principal the shared fixtures leave unused) and one who
    reads nothing (`u_narrow`)."""
    grants = {
        **GRANTS,
        "u_elsewhere": (
            *GALLERY,
            builds(WEB),
            Grant(capability=READS, scope=WEB),
        ),
    }
    app = create_app(Settings(env="development"))
    memory = Memory(agents=everybody())
    with TestClient(app) as client:
        app.state.gate = gate_wiring(grants)
        app.state.db_sessions = None
        app.state.agent_drafts = memory
        app.state.template_key = KEY
        app.state.tools = tools("books", "ledger")
        yield Console(client=client, app=app, memory=memory)


def test_the_served_form_offers_each_builder_what_their_reach_holds(console: Console) -> None:
    """A Super Admin is served the form whole, a department's builder who reads invoices is offered
    the invoice tools and their sources and told why, and one who reads nothing is offered none.

    Delete this and the form a department's administrator is given lists every tool on the install,
    which is the choice the leaf says they cannot make."""
    whole = console.get("u_admin", FORM_PATH).json()
    reading = console.get("u_elsewhere", FORM_PATH).json()
    reading_nothing = console.get("u_narrow", FORM_PATH).json()

    assert whole["offer_note"] is None
    assert "enum" not in _entries(whole)["authority.allowed_tools"]["items"]
    assert reading["offer_note"] == THE_OFFER_IS_WHAT_YOUR_DEPARTMENT_HOLDS
    assert _entries(reading)["authority.allowed_tools"]["items"]["enum"] == [
        "books.read_invoice",
        "ledger.read_invoice",
    ]
    assert _entries(reading)["connectors"]["items"]["enum"] == ["books", "ledger"]
    assert _entries(reading_nothing)["authority.allowed_tools"]["maxItems"] == 0
    assert reading_nothing["offer_note"] == THE_OFFER_IS_WHAT_YOUR_DEPARTMENT_HOLDS


def test_a_tool_that_changes_records_is_offered_to_a_reader_whose_reach_holds_it() -> None:
    """The choices are every tool the reach admits, whatever it does: a department that may write
    invoices is offered the tool that does, which a ceiling on side effects would have left out.

    Delete this and the cut is made over reading tools alone, so a department's administrator
    cannot name the one tool that makes their agent useful."""
    from brain.core.envelope import IdentityMode, SideEffect
    from brain.tools.registry import ToolDefinition, ToolRegistry

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="helpdesk.change_entry",
            description="changes one invoice",
            entity="invoice",
            required_capability="write:invoice.reference",
            side_effect=SideEffect.WRITE,
            identity_mode=IdentityMode.DELEGATED,
            source="helpdesk",
        ),
        an_invoice,
    )
    writes = holding(
        builds(WEB), Grant(capability=Capability(value="write:invoice.reference"), scope=WEB)
    )

    assert held_choices(registry, writes, NOW).tools == ("helpdesk.change_entry",)
    assert held_choices(registry, holding(builds(WEB)), NOW).tools == ()


def test_a_process_with_no_tool_registry_offers_a_department_builder_nothing_and_does_not_fail(
    console: Console,
) -> None:
    """The form is still served, with nothing to choose. Delete this and a process whose registry is
    missing answers the builder's form with a server error."""
    console.app.state.tools = None

    served = console.get("u_elsewhere", FORM_PATH)

    assert served.status_code == 200, served.text
    assert _entries(served.json())["authority.allowed_tools"]["maxItems"] == 0
