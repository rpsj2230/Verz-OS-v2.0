"""An outside AI service registered as a tool an agent must be given (M12.3.7), without a database.

The declaration, what it derives, what registering it does, who the catalogue then offers it to and
how the install's rows are read back. The call is not tested because it does not exist: the
handler is a refusal, and the tests say so. What the rows hold and what a statement writes are
asserted on the compiled statement, because there is no database here to run one.

Task ids: M12.3.7
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import IdentityMode, SideEffect
from brain.core.errors import Denied
from brain.core.scope import Scope
from brain.gate.catalogue import AgentCeiling, project
from brain.ops.external_ai_store import (
    NAMESPACE,
    declared_if_on,
    declared_in,
    key_of,
    record_service,
    retire_service,
    retire_statement,
    service_statement,
    stored_value,
)
from brain.ops.setting_store import SettingState
from brain.tools.external_ai import (
    OUTSIDE_SERVICES_ARE_NOT_CALLED_YET,
    SERVICE_SIDE_EFFECT,
    ExternalAiService,
    ServiceAsked,
    capability_of,
    definition_of,
    entity_of,
    is_a_service_name,
    key_slot_of,
    never_called_directly,
    register_external_ai,
    scope_of,
    tool_name_of,
)
from brain.tools.registry import (
    EffectClass,
    ToolRegistry,
    effect_class,
    leash_ceiling,
)

#: Far from any wall clock, because nothing here is about the present. See CLAUDE.md on a fixture
#: with a date in it.
NOW = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
LONG_AGO = datetime(2019, 1, 1, 9, 0, tzinfo=UTC)

#: An address that cannot be anybody's: the reserved test domain.
ENDPOINT = "https://ai.example.test/v1/generate"


def service(name: str = "imagegen", **overrides: Any) -> ExternalAiService:
    fields: dict[str, Any] = {
        "service": name,
        "does": "Draws a picture from a sentence",
        "kind": "image_generation",
        "endpoint": ENDPOINT,
    }
    fields.update(overrides)
    return ExternalAiService.model_validate(fields)


def holding(*capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_asker",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in capabilities
        ),
    )


def state(value: Any, *, value_type: str = "json") -> SettingState:
    return SettingState(
        key="external_ai.x",
        value_type=value_type,
        value=value,
        updated_by="u_a",
        updated_at=LONG_AGO,
    )


def registry_with(*names: str) -> ToolRegistry:
    registry = ToolRegistry()
    register_external_ai(registry, [service(name) for name in names])
    return registry


# ------------------------------------------------------------------ the declaration
def test_a_declaration_has_four_fields_and_none_of_them_can_hold_a_secret() -> None:
    """A name, what it does, a kind and an address, and nothing a key, a capability or a class could
    arrive in. Delete this and a fifth field can be added that an administrator pastes a key into,
    and it is stored in a table every administrator reads."""
    assert set(ExternalAiService.model_fields) == {"service", "does", "kind", "endpoint"}
    assert set(stored_value(service())) == {"service", "does", "kind", "endpoint"}


@pytest.mark.parametrize("field", ["side_effect", "capability", "key", "api_key", "identity_mode"])
def test_a_declaration_cannot_say_what_it_counts_as_what_it_needs_or_what_key_it_has(
    field: str,
) -> None:
    """Each of these is refused as an unknown field. Delete this and a declaration can count itself
    as a read, name a capability many people already hold, or carry a key in its own row, which are
    the three ways a declared service widens who may spend the company's account."""
    with pytest.raises(ValidationError):
        service(**{field: "send"})


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://ai.example.test/v1",
        "ftp://ai.example.test/v1",
        "https://user:secret@ai.example.test/v1",
        "https://user@ai.example.test/v1",
        "https://:secret@ai.example.test/v1",
        "https://ai.example.test/v1?key=abc",
        "https://ai.example.test/v1#frag",
        "https://10.0.0.5/v1",
        "https://[::1]/v1",
        "https://localhost/v1",
        "https:///v1",
        "ai.example.test/v1",
        "",
    ],
    ids=[
        "plain-http",
        "other-scheme",
        "credentials",
        "user-only",
        "password-only",
        "query",
        "fragment",
        "address-literal",
        "address-literal-v6",
        "single-label",
        "no-host",
        "no-scheme",
        "empty",
    ],
)
def test_an_address_a_key_could_travel_in_or_that_names_the_install_s_own_network_is_refused(
    endpoint: str,
) -> None:
    """Thirteen addresses, each refused when the declaration is built. Delete this and a key can be
    put in the address and shown on every screen that lists the service, or a declaration can
    point a call at a machine inside the network the install sits in."""
    with pytest.raises(ValidationError):
        service(endpoint=endpoint)
    assert service(endpoint="https://ai.example.test:8443/v1").endpoint.endswith(":8443/v1")


@pytest.mark.parametrize(
    "name",
    ["a", "Image", "1image", "image-gen", "image.gen", "image gen", "x" * 32, ""],
    ids=["one-letter", "upper", "digit-first", "hyphen", "dot", "space", "long", "empty"],
)
def test_a_name_that_is_not_one_lower_case_segment_is_refused(name: str) -> None:
    """The name is a tool source, an object and a key slot, so it is one path segment. Delete this
    and a name with a dot or a slash becomes the path a key is written under."""
    with pytest.raises(ValidationError):
        service(name)
    assert not is_a_service_name(name)
    assert is_a_service_name("imagegen") and is_a_service_name("speech_to_text_2")


@pytest.mark.parametrize("does", ["", " padded ", "two\nlines", "tab\there"])
def test_what_a_service_does_is_one_plain_line(does: str) -> None:
    """It is shown to a model and an administrator in a list. Delete this and a sentence with a
    line break can start a second instruction in a catalogue a model reads."""
    with pytest.raises(ValidationError):
        service(does=does)


# ------------------------------------------------------------------ what it derives
def test_the_tool_the_capability_and_the_key_slot_are_worked_out_from_the_name_alone() -> None:
    """`ai_<service>.call_service`, `invoke:external_ai.<service>` and the key slot
    `connector_keys/ai_<service>`, asserted as text, because a test that compares a derivation
    with itself passes for every value it could hold. Delete this and a derivation can move to a
    name another part of the product already uses, or to a capability that is not the service's
    own."""
    assert tool_name_of("imagegen") == "ai_imagegen.call_service"
    assert entity_of("imagegen") == "external_ai_imagegen"
    assert capability_of("imagegen").value == "invoke:external_ai.imagegen"
    assert capability_of("imagegen").verb == "invoke"
    assert key_slot_of("imagegen").path == "connector_keys/ai_imagegen"


def test_two_services_never_share_a_tool_a_capability_an_object_or_a_key_slot() -> None:
    """Delete this and two services can be opened by one grant, or can write one key slot, which is
    one company's account used for another's work."""
    one, other = "imagegen", "speech"
    derived = [
        (tool_name_of(n), entity_of(n), capability_of(n).value, key_slot_of(n).path)
        for n in (one, other)
    ]
    assert all(len(set(column)) == 2 for column in zip(*derived, strict=True))


def test_a_service_counts_as_sending_something_out_whatever_is_declared() -> None:
    """The class is `SEND`, which is sensitive by its kind, so a person approves each call and the
    rung a leash entry may hold is capped at Assisted. Delete this and a service can be registered
    as a read, which is the loosening only the owner may decide (needs-rupash 184)."""
    from brain.gate.injection import AutonomyTier

    declared = definition_of(service())

    assert SERVICE_SIDE_EFFECT is SideEffect.SEND
    assert declared.side_effect is SideEffect.SEND
    assert declared.declares_sensitive_effect()
    assert effect_class(declared) is EffectClass.IRREVERSIBLE
    assert leash_ceiling(declared) is AutonomyTier.ASSISTED


def test_the_tool_is_a_service_tool_that_carries_a_scope_naming_its_service() -> None:
    """The key a call would be sent with is the install's own, so the tool is SERVICE and carries a
    scope that narrows something, as the registry requires. Delete this and a service tool can be
    registered unscoped, which the registry refuses at start and so takes the application down."""
    declared = definition_of(service())

    assert declared.identity_mode is IdentityMode.SERVICE
    assert declared.required_capability == "invoke:external_ai.imagegen"
    assert [(c.field, c.value) for c in scope_of(service()).clauses] == [("service", "imagegen")]
    assert not scope_of(service()).is_unrestricted()


def test_the_description_names_the_service_so_two_services_never_read_alike() -> None:
    """Delete this and two services doing the same thing share a description, which the registry
    refuses at freeze and so stops the application starting."""
    first = definition_of(service("imagegen")).description
    second = definition_of(service("imagemaker")).description

    assert first != second and "imagegen" in first
    assert len(definition_of(service(does="x" * 300)).description) <= 400


# ------------------------------------------------------------------ registering
def test_every_declared_service_is_registered_in_name_order_and_once() -> None:
    """Two services and a repeat of one: two tools, in name order. Delete this and the order two
    starts register in can differ, or a repeated declaration can fail the start."""
    registry = ToolRegistry()

    names = register_external_ai(
        registry, [service("speech"), service("imagegen"), service("speech")]
    )

    assert names == ("ai_imagegen.call_service", "ai_speech.call_service")
    assert registry.names() == names


def test_none_declared_registers_nothing() -> None:
    """The positive case for every install until somebody declares one. Delete this and an install
    with no service can find a tool in its catalogue that names a company that is not its own."""
    registry = ToolRegistry()

    assert register_external_ai(registry, []) == ()
    assert registry.names() == ()


def test_a_service_the_registry_refuses_is_skipped_and_the_others_are_registered() -> None:
    """One name already taken: the other services still register and nothing is raised. Delete
    this and one install's declaration stops the application starting for everybody who uses it."""
    registry = registry_with("imagegen")

    names = register_external_ai(registry, [service("imagegen"), service("speech")])

    assert names == ("ai_speech.call_service",)
    assert registry.names() == ("ai_imagegen.call_service", "ai_speech.call_service")


def test_a_registered_service_refuses_every_call_in_one_sentence() -> None:
    """The handler a registry holds is a refusal, so nothing can reach an outside company through
    it. Delete this and a registered service can be called by whatever calls tools by name, with a
    key nobody decided to send."""
    registry = registry_with("imagegen")
    call = registry.get("ai_imagegen.call_service").handler

    with pytest.raises(Denied) as refused:
        asyncio.run(_run(call(ServiceAsked(instruction="draw a cat"), entitlement=holding())))

    assert str(refused.value) == OUTSIDE_SERVICES_ARE_NOT_CALLED_YET
    with pytest.raises(Denied):
        asyncio.run(
            _run(
                never_called_directly(ServiceAsked(instruction="x"), entitlement=holding(), now=NOW)
            )
        )


async def _run(pending: Any) -> Any:
    return await pending


def test_the_words_a_person_reads_are_the_ones_written_here() -> None:
    """The sentence a refused call is answered with and the class are asserted against the text.
    Delete this and the sentence can start to name the service or the reason."""
    assert (
        OUTSIDE_SERVICES_ARE_NOT_CALLED_YET == "this outside service is not available to call yet"
    )
    assert NAMESPACE == "external_ai"
    assert key_of("imagegen") == "external_ai.imagegen"


# ------------------------------------------------------------------ who is offered one
def ceiling(*tools: str, up_to: SideEffect = SideEffect.SEND) -> AgentCeiling:
    return AgentCeiling(agent_id="a", allowed_tools=frozenset(tools), max_side_effect=up_to)


def offered(entitlement: EntitlementSet, agent: AgentCeiling) -> tuple[str, ...]:
    return project(registry_with("imagegen", "speech"), entitlement, agent, now=NOW).names


def test_an_agent_that_names_a_service_is_offered_it_to_a_caller_who_holds_its_permission() -> None:
    """**The positive case every refusal below needs beside it.** The agent's ceiling names the
    tool and allows a side effect as large as sending, and the caller holds the service's own
    capability. Delete this and a catalogue that offers nothing passes every refusal here."""
    caller = holding("invoke:external_ai.imagegen")

    assert offered(caller, ceiling("ai_imagegen.call_service")) == ("ai_imagegen.call_service",)


def test_an_agent_whose_ceiling_does_not_name_a_service_is_offered_nothing() -> None:
    """The leaf's own sentence: refused to any agent whose ceiling does not name it. Delete this and
    a caller who holds the capability reaches the service through an agent nobody gave it to."""
    caller = holding("invoke:external_ai.imagegen", "invoke:external_ai.speech")

    assert offered(caller, ceiling("ai_speech.call_service")) == ("ai_speech.call_service",)
    assert offered(caller, ceiling()) == ()


def test_an_agent_that_names_a_service_but_may_not_send_is_offered_nothing() -> None:
    """The service counts as sending something out, so an agent whose own ceiling allows less than
    a send is not offered it even when it names it. Delete this and the class is a label: the
    catalogue's side-effect ceiling is what makes it bite."""
    caller = holding("invoke:external_ai.imagegen")

    for less in (SideEffect.NONE, SideEffect.DRAFT, SideEffect.WRITE):
        assert offered(caller, ceiling("ai_imagegen.call_service", up_to=less)) == ()


def test_a_caller_without_the_services_own_permission_is_offered_nothing_through_any_agent() -> (
    None
):
    """Holding another service's permission, or a read of everything, opens nothing. Delete this and
    the derived capability is decoration."""
    agent = ceiling("ai_imagegen.call_service", "ai_speech.call_service")

    assert offered(holding("invoke:external_ai.speech"), agent) == ("ai_speech.call_service",)
    assert offered(holding("read:client.name", "write:ticket.status"), agent) == ()
    assert offered(holding(), agent) == ()


# ------------------------------------------------------------------ the rows
def test_the_rows_that_declare_services_are_read_back_in_name_order() -> None:
    """Delete this and the order two starts register in follows the order the database returned."""
    rows = {
        "external_ai.speech": state(stored_value(service("speech"))),
        "external_ai.imagegen": state(stored_value(service("imagegen"))),
    }

    assert [one.service for one in declared_in(rows)] == ["imagegen", "speech"]


@pytest.mark.parametrize(
    "row",
    [
        state("a string", value_type="string"),
        state(["not", "an", "object"]),
        state(stored_value(service("imagegen")), value_type="string"),
        state({"service": "imagegen"}),
        state({**stored_value(service("imagegen")), "side_effect": "none"}),
        state({**stored_value(service("imagegen")), "endpoint": "http://ai.example.test"}),
        state(stored_value(service("other_name"))),
    ],
    ids=[
        "string",
        "list",
        "typed-string",
        "partial",
        "extra-field",
        "bad-address",
        "key-names-another",
    ],
)
def test_a_row_that_is_not_a_declaration_is_absent_and_the_good_rows_still_read(
    row: SettingState,
) -> None:
    """Seven rows somebody could have written by hand, each skipped while a good one beside it is
    read. Delete this and one bad row stops every service registering, or registers a service its
    own key does not name, which the retire statement would then miss."""
    rows = {
        "external_ai.imagegen": row,
        "external_ai.speech": state(stored_value(service("speech"))),
    }

    assert [one.service for one in declared_in(rows)] == ["speech"]


def test_a_row_deeper_than_one_segment_is_not_a_service() -> None:
    """`external_ai.imagegen.extra` is not `imagegen`. Delete this and a key with a third segment
    registers a service its row does not name."""
    rows = {"external_ai.imagegen.extra": state(stored_value(service("imagegen")))}

    assert declared_in(rows) == ()


def test_a_declaration_is_written_as_json_under_its_own_key_and_nothing_else() -> None:
    """The statement writes one row: the service's key, a JSON value of the four fields and a
    sentence that is product text. Delete this and the row can be written under another key, or
    with a type that is not JSON, or with a value a person typed beside the declaration."""
    compiled = service_statement(service(), by="u_admin").compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    params = compiled.params

    assert params["key"] == "external_ai.imagegen"
    assert params["value_type"] == "json"
    assert params["value"] == stored_value(service())
    assert params["updated_by"] == "u_admin"
    assert "type" not in params["description"] and "Draws" not in params["description"]


def test_retiring_a_declaration_touches_one_key_and_says_who() -> None:
    """The statement retires the one service's live row and names who. Delete this and taking away
    one service retires every service the install declared."""
    compiled = retire_statement("imagegen", by="u_admin").compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]

    assert "setting.key = " in str(compiled)
    assert "external_ai.imagegen" in compiled.params.values()
    assert "u_admin" in compiled.params.values()
    with pytest.raises(ValueError, match="nobody"):
        retire_statement("imagegen", by=" ")


class _Session:
    """A session that remembers what it was asked to run, in order."""

    def __init__(self) -> None:
        self.ran: list[Any] = []

    async def execute(self, statement: Any) -> None:
        self.ran.append(statement)


@pytest.mark.parametrize("writing", ["record", "retire"])
def test_a_declaration_is_written_and_retired_only_after_the_attribution_is_set(
    writing: str,
) -> None:
    """Both writers run the three statements that tell the ledger's trigger who is writing, at what
    reach and for which request, and only then the write. Delete this and a declaration is
    recorded with the placeholder reach, an entry that verifies and answers none of the questions
    the ledger exists to answer."""
    session = _Session()
    attribution = {"actor": "u_admin", "ent_hash": "a" * 32, "trace_id": "trace_1"}

    if writing == "record":
        asyncio.run(record_service(session, service(), **attribution))  # type: ignore[arg-type]
    else:
        asyncio.run(retire_service(session, "imagegen", **attribution))  # type: ignore[arg-type]

    *before, write = session.ran
    assert len(before) == 3
    assert [one.compile().params["value"] for one in before] == ["u_admin", "a" * 32, "trace_1"]
    assert "ops.setting" in str(write)


def test_nothing_is_registered_without_a_database_or_with_the_switch_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No sessions is no services, and a switch that is off is no services without the rows being
    read. Delete this and an install with the switch off registers what it declared, or one with no
    database fails to start."""
    import brain.ops.external_ai_store as store

    reads: list[str] = []

    async def off(sessions: Any) -> bool:
        return False

    async def on(sessions: Any) -> bool:
        return True

    async def rows(session: Any) -> tuple[ExternalAiService, ...]:
        reads.append("read")
        return (service(),)

    class Sessions:
        def __call__(self) -> Any:
            class One:
                async def __aenter__(self) -> None:
                    return None

                async def __aexit__(self, *exc: object) -> None:
                    return None

            return One()

    monkeypatch.setattr(store, "declared", rows)
    monkeypatch.setattr(store, "services_are_on", off)
    assert asyncio.run(declared_if_on(Sessions())) == () and reads == []  # type: ignore[arg-type]
    monkeypatch.setattr(store, "services_are_on", on)
    assert asyncio.run(declared_if_on(None)) == () and reads == []
    assert [one.service for one in asyncio.run(declared_if_on(Sessions()))] == ["imagegen"]  # type: ignore[arg-type]
    assert reads == ["read"]


def test_an_install_whose_settings_cannot_be_read_starts_without_outside_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed read answers none and does not raise. Delete this and an install whose settings
    table is not there yet, or not readable, stops starting over a feature that ships off."""
    import brain.ops.external_ai_store as store

    async def unreadable(sessions: Any) -> bool:
        raise OSError("the database went away")

    monkeypatch.setattr(store, "services_are_on", unreadable)

    assert asyncio.run(declared_if_on(object())) == ()  # type: ignore[arg-type]


def test_an_install_with_no_database_is_not_a_failed_read() -> None:
    """No sessions answers none quietly, where an unreadable database answers none with a warning.
    Delete this and a process with no database logs a failure at every start, which is a warning
    nobody reads after the first week."""
    from structlog.testing import capture_logs

    with capture_logs() as logged:
        assert asyncio.run(declared_if_on(None)) == ()

    assert logged == []


# ------------------------------------------------------------------ the registry the app builds
def test_the_application_registry_holds_the_services_it_is_handed_and_none_by_default() -> None:
    """`build_registry` registers what it is given and nothing otherwise. Delete this and the
    declared services never reach the registry the application freezes."""
    from brain.tools.startup import build_registry

    plain = build_registry(source="demo")
    with_one = build_registry(source="demo", external_ai=[service()])

    assert "ai_imagegen.call_service" not in plain.names()
    assert "ai_imagegen.call_service" in with_one.names()
    assert with_one.get("ai_imagegen.call_service").capability == capability_of("imagegen")
