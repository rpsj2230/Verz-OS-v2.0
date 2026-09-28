"""A tool switched off is refused at every call, and a sensitive effect cannot be left undeclared.

The registry's half of the Tools screen, without a database. The switch source is a double over
stops a test chose, because what is under test is the door: that every handler a caller can reach
asks it, at the call and not at the lookup, refuses with the one sentence every refusal carries,
and lets the call through when nothing stops it. The records route at the end drives the same
door through the application, so the refusal a person sees is the one an absent record gets.

Task ids: M12.1.3, M12.3.8, M12.4.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.app import Settings, create_app
from brain.automation_routes import _request_type
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.errors import Absent, Denied
from brain.gate.injection import AutonomyTier
from brain.gate.leash import SENSITIVE_EFFECT_RUNG, Leash, LeashEntry, Route
from brain.knowledge.rows import RowRequest
from brain.ops.tool_store import widest
from brain.tools.registry import (
    EffectClass,
    SensitiveEffect,
    Switch,
    SwitchScope,
    ToolRegistrationError,
    ToolRegistry,
    ToolSwitchedOffError,
    caller_of,
    default_rung,
    effect_class,
    leash_ceiling,
    sensitive_effects_named_by,
    sensitive_words,
)
from brain.tools.startup import build_registry
from tests.unit.test_api_routes import SOURCE, UnfilteredRows, ask, wiring
from tests.unit.test_leash import CALLER, action, leash_at, run

#: Far from any wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

READ_NOTES = "notes.read_note"


class Note(Entity):
    text: str = ""


def read_note(*, entitlement: EntitlementSet, now: datetime | None = None) -> TypedResult[Note]:
    """A synchronous typed handler, which is the shape a skill handler has."""
    return TypedResult[Note](records=(Note(entity="note", id="n_1", text="kept"),))


def definition(
    name: str = READ_NOTES,
    *,
    effect: SideEffect = SideEffect.NONE,
    capability: str = "read:note.text",
    sensitive: bool = False,
    description: str | None = None,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description or f"a tool called {name}",
        entity="note",
        required_capability=capability,
        side_effect=effect,
        identity_mode=IdentityMode.DELEGATED,
        sensitive=sensitive,
    )


def reach(principal_id: str) -> EntitlementSet:
    return EntitlementSet(principal_id=principal_id)


class Stops:
    """A `SwitchSource` over stops a test chose, with a department for each person."""

    def __init__(self, departments: Mapping[str, str] | None = None) -> None:
        self.departments = dict(departments or {})
        self.stops: list[Switch] = []
        self.asked: list[tuple[str, str | None]] = []
        self.unreachable = False

    def off(self, tool: str, department: str | None = None) -> Switch:
        stop = Switch(
            switch_id=f"sw_{len(self.stops) + 1}",
            tool=tool,
            department=department,
            switched_off_by="u_admin",
            switched_off_at=LONG_AGO,
        )
        self.stops.append(stop)
        return stop

    def on(self, tool: str) -> None:
        self.stops = [one for one in self.stops if one.tool != tool]

    async def stop_for(self, tool: str, principal_id: str | None) -> Switch | None:
        self.asked.append((tool, principal_id))
        if self.unreachable:
            raise ConnectionError("the switch table is on a host that did not answer")
        mine = self.departments.get(principal_id or "")
        return widest(
            one
            for one in self.stops
            if one.tool == tool
            and (one.department is None or principal_id is None or one.department == mine)
        )


def call(registry: ToolRegistry, principal_id: str, name: str = READ_NOTES) -> Any:
    """Call a registered handler the way every caller in the tree does: awaiting what needs it."""

    async def go() -> Any:
        answered = registry.get(name).handler(entitlement=reach(principal_id), now=LONG_AGO)
        return await answered if asyncio.iscoroutine(answered) else answered

    return asyncio.run(go())


def governed(stops: Stops) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(definition(), read_note)
    return registry.freeze().govern(stops)


# ------------------------------------------------------------------- the switch (M12.4.3)
def test_a_tool_nobody_switched_off_answers_through_the_guard() -> None:
    """The positive sibling of every refusal below. Delete it and a guard that refuses every call
    passes them all, which is a switch stuck off for the whole install."""
    stops = Stops()
    result = call(governed(stops), "u_weiling")
    assert [one.text for one in result.records] == ["kept"]
    assert stops.asked == [(READ_NOTES, "u_weiling")]


def test_a_tool_switched_off_for_the_install_is_refused_to_every_caller() -> None:
    """The owner's sentence: after a switch, every call to it is refused. Delete this and the
    switch table can be written, shown and audited while the tool goes on answering."""
    stops = Stops(departments={"u_weiling": "web", "u_ahmad": "sales"})
    registry = governed(stops)
    thrown = stops.off(READ_NOTES)
    for person in ("u_weiling", "u_ahmad", "u_nobody"):
        with pytest.raises(ToolSwitchedOffError) as refused:
            call(registry, person)
        assert refused.value.switch == thrown
        assert refused.value.switch.scope is SwitchScope.INSTALL


def test_the_refusal_names_the_switch_to_the_trace_and_nothing_to_the_asker() -> None:
    """`THE_ASKER_IS_NEVER_TOLD_WHICH_SWITCH`. The public sentence is `Denied`'s own, compared with
    `Absent`'s rather than with itself, and the detail carries the switch for the log. Delete this
    and a refusal body can tell a department which of its tools somebody switched off."""
    stops = Stops()
    registry = governed(stops)
    thrown = stops.off(READ_NOTES, "web")
    stops.departments["u_weiling"] = "web"
    with pytest.raises(ToolSwitchedOffError) as refused:
        call(registry, "u_weiling")
    assert isinstance(refused.value, Denied)
    assert refused.value.public_message == Absent().public_message
    assert thrown.switch_id not in refused.value.public_message
    assert READ_NOTES not in refused.value.public_message
    detail = str(refused.value)
    assert thrown.switch_id in detail and "department 'web'" in detail and "u_admin" in detail


def test_a_department_stop_refuses_that_departments_people_and_nobody_else() -> None:
    """A department administrator's stop narrows their own department and no other. Delete this
    and a stop written for one department either stops the whole company or stops nobody."""
    stops = Stops(departments={"u_weiling": "web", "u_ahmad": "sales"})
    registry = governed(stops)
    stops.off(READ_NOTES, "web")
    with pytest.raises(ToolSwitchedOffError):
        call(registry, "u_weiling")
    assert [one.text for one in call(registry, "u_ahmad").records] == ["kept"]


def test_a_handler_taken_before_the_switch_is_still_refused_after_it() -> None:
    """`THE_SWITCH_IS_ASKED_AT_THE_CALL_AND_NOT_AT_THE_LOOKUP`. The answer lane holds the passage
    search's handler from startup, so a check made at lookup would never see a switch. Delete this
    and the guard can move to `get`, where it would be asked once, before anybody could throw it."""
    registry = ToolRegistry()
    registry.register(definition(), read_note)
    registry.freeze()
    held = registry.get(READ_NOTES).handler
    stops = Stops()
    registry.govern(stops)
    stops.off(READ_NOTES)

    async def go() -> Any:
        answered = held(entitlement=reach("u_weiling"), now=LONG_AGO)
        assert asyncio.iscoroutine(answered)
        return await answered

    with pytest.raises(ToolSwitchedOffError):
        asyncio.run(go())


def test_switching_a_tool_back_on_lets_the_next_call_through() -> None:
    """A stop retired is a stop gone, at the next call and without a restart. Delete this and a
    guard remembering the first stop it saw would keep a tool off for the life of the process."""
    stops = Stops()
    registry = governed(stops)
    stops.off(READ_NOTES)
    with pytest.raises(ToolSwitchedOffError):
        call(registry, "u_weiling")
    stops.on(READ_NOTES)
    assert call(registry, "u_weiling").records


def test_a_switch_nobody_could_read_refuses_the_call() -> None:
    """`AN_UNREADABLE_SWITCH_REFUSES_THE_CALL`. Delete this and the moment the switch table is
    unreachable is the moment every stop an administrator threw stops applying."""
    stops = Stops()
    registry = governed(stops)
    stops.unreachable = True
    with pytest.raises(ToolSwitchedOffError) as refused:
        call(registry, "u_weiling")
    assert refused.value.switch is None
    assert isinstance(refused.value.__cause__, ConnectionError)


def test_a_call_handed_no_reach_is_asked_about_as_nobodys() -> None:
    """`caller_of` reads the reach off the call, and answers None when there is none, which the
    source must treat as any department's. Delete this and a handler called positionally or with
    no reach walks past every department stop."""
    assert caller_of((), {"entitlement": reach("u_weiling")}) == "u_weiling"
    assert caller_of((reach("u_ahmad"),), {}) == "u_ahmad"
    assert caller_of(("a request",), {"now": LONG_AGO}) is None
    stops = Stops(departments={"u_weiling": "web"})
    registry = ToolRegistry()
    registry.register(definition(), read_note)
    registry.freeze().govern(stops)
    stops.off(READ_NOTES, "sales")

    async def go() -> Any:
        answered = registry.get(READ_NOTES).handler(now=LONG_AGO)
        return await answered if asyncio.iscoroutine(answered) else answered

    with pytest.raises(ToolSwitchedOffError):
        asyncio.run(go())
    assert stops.asked == [(READ_NOTES, None)]


def test_an_ungoverned_registry_calls_the_handler_exactly_as_before() -> None:
    """With no source the guard returns what the handler returns, a value for a synchronous one.
    Delete this and every registry built without a database, a test's or a canary's, starts
    handing its callers a coroutine they never asked for."""
    registry = ToolRegistry()
    registry.register(definition(), read_note)
    registry.freeze()
    answered = registry.get(READ_NOTES).handler(entitlement=reach("u_weiling"), now=LONG_AGO)
    assert isinstance(answered, TypedResult)
    assert not registry.is_governed


def test_a_registry_is_governed_by_one_source_and_never_by_a_second() -> None:
    """Replacing the source is the one way to lift every stop with nobody switching a tool on.
    Delete this and a second `govern` with a source that never refuses undoes them all."""
    registry = governed(Stops())
    assert registry.is_governed
    with pytest.raises(ToolRegistrationError, match="already governed"):
        registry.govern(Stops())


def test_the_guard_keeps_the_signature_a_workflow_reads_its_request_model_from() -> None:
    """`brain.automation_routes` finds the request model on the handler's first parameter. Delete
    this and a guard written without `functools.wraps` makes every workflow step refused as a tool
    that takes no request, which is a switch stuck off for automations only."""
    registry = build_registry(source=SOURCE, records=UnfilteredRows()).govern(Stops())
    row_tool = next(one for one in registry.definitions() if one.entity == "price_list")
    assert _request_type(registry.get(row_tool.name).handler) is RowRequest


# ------------------------------------------------------------- the records route, end to end
@pytest.fixture
def records() -> Iterator[tuple[TestClient, Stops, str]]:
    """The real application and its records route, over a governed registry."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = wiring()
        stops = Stops()
        registry = build_registry(source=SOURCE, records=UnfilteredRows()).govern(stops)
        app.state.tools = registry
        name = next(one.name for one in registry.definitions() if one.entity == "price_list")
        yield client, stops, name


def test_a_person_reading_records_through_a_switched_off_tool_is_told_what_an_absence_says(
    records: tuple[TestClient, Stops, str],
) -> None:
    """The switch through a real route: answered while on, and when off refused with the status
    and the sentence a record that is not there gets, naming neither the tool nor the switch.
    Delete this and the door can be proved on a registry no route ever reads through."""
    client, stops, name = records
    assert ask(client, "u_wide").status_code == 200
    thrown = stops.off(name)
    refused = ask(client, "u_wide")
    absent = ask(client, "u_wide", entity="no_such_entity")
    assert refused.status_code == absent.status_code == 404
    assert refused.json()["message"] == absent.json()["message"]
    assert name not in refused.text and thrown.switch_id not in refused.text
    stops.on(name)
    assert ask(client, "u_wide").status_code == 200


# ------------------------------------------------------- sensitive effects (M12.3.8)
#: A side-effecting tool name for each of the owner's seven, each read by the vocabulary.
NAMED: Mapping[SensitiveEffect, str] = {
    SensitiveEffect.CLIENT_MESSAGE: "gmail.reply_thread",
    SensitiveEffect.QUOTATION: "crm.issue_quotation",
    SensitiveEffect.DNS_OR_HOSTING: "cloudflare.update_dns",
    SensitiveEffect.FINANCIAL_RECORD: "books.update_invoice",
    SensitiveEffect.DELETION: "drive.delete_file",
    SensitiveEffect.PUBLICATION: "wordpress.publish_page",
    SensitiveEffect.PRODUCTION_CHANGE: "wordpress.update_plugin",
}


def test_the_vocabulary_names_every_one_of_the_owners_effects() -> None:
    """Asserted against the names above, written from the owner's list rather than from the
    vocabulary. Delete this and an effect whose words were never written is an effect no name can
    ever be refused for."""
    assert set(NAMED) == set(SensitiveEffect)
    for effect, name in NAMED.items():
        assert effect in sensitive_effects_named_by(name), (effect, name)
        assert sensitive_words(effect)


@pytest.mark.parametrize("effect", list(SensitiveEffect))
def test_a_tool_whose_name_says_it_acts_sensitively_must_declare_it(
    effect: SensitiveEffect,
) -> None:
    """`A_TOOL_WHOSE_NAME_SAYS_IT_ACTS_SENSITIVELY_MUST_DECLARE_IT`, for each of the seven. Delete
    this and `drive.delete_file` registers as an ordinary write and runs at whatever rung its leash
    holds, Autonomous included."""
    registry = ToolRegistry()
    with pytest.raises(ToolRegistrationError, match="declares none"):
        registry.register(
            definition(NAMED[effect], effect=SideEffect.WRITE, capability="write:note.text"),
            read_note,
        )
    registered = registry.register(
        definition(
            NAMED[effect], effect=SideEffect.WRITE, capability="write:note.text", sensitive=True
        ),
        read_note,
        sensitive_effect=effect,
    )
    assert registered.sensitive_effect is effect
    assert registered.effect is EffectClass.IRREVERSIBLE


def test_a_tool_that_only_reads_or_drafts_is_not_asked_about_its_name() -> None:
    """A read changes nothing and a draft is the prepared action itself. Delete this and the rule
    is satisfied by refusing every tool whose name mentions an invoice, including the ones that
    read one."""
    registry = ToolRegistry()
    registry.register(definition("books.read_invoice"), read_note)
    registry.register(
        definition("gmail.draft_reply", effect=SideEffect.DRAFT, capability="write:note.text"),
        read_note,
    )
    registry.register(
        definition("ticket.update_status", effect=SideEffect.WRITE, capability="write:note.text"),
        read_note,
    )
    assert len(registry) == 3


def test_a_send_or_money_tool_is_sensitive_by_its_kind_without_naming_the_effect() -> None:
    """`invoice.send_reminder` is a client message by its name and sensitive by its kind. Delete
    this and the rule demands a second declaration of what the kind already says, and breaks every
    send tool registered before it."""
    registry = ToolRegistry()
    registered = registry.register(
        definition("invoice.send_reminder", effect=SideEffect.SEND, capability="write:note.text"),
        read_note,
    )
    assert registered.sensitive_effect is None
    assert registered.effect is EffectClass.IRREVERSIBLE


def test_a_named_effect_the_definition_does_not_declare_is_refused() -> None:
    """The leash reads the definition, not the registration. Delete this and a tool can name
    deletion on the Tools screen while the gate runs it unapproved."""
    with pytest.raises(ToolRegistrationError, match="does not declare one"):
        ToolRegistry().register(
            definition("notes.archive_note", effect=SideEffect.WRITE, capability="write:note.text"),
            read_note,
            sensitive_effect=SensitiveEffect.DELETION,
        )


def test_a_named_effect_on_a_tool_that_only_reads_is_refused() -> None:
    """Delete this and a read can be listed as deleting records, and the Tools screen says a thing
    about a tool that no call to it can do."""
    with pytest.raises(ToolRegistrationError, match="only reads"):
        ToolRegistry().register(
            definition(sensitive=True), read_note, sensitive_effect=SensitiveEffect.DELETION
        )


def test_a_tool_declared_sensitive_must_say_which_effect() -> None:
    """Delete this and an approver is asked to approve "a sensitive action" with nothing saying
    which of the owner's seven it is."""
    with pytest.raises(ToolRegistrationError, match="names no effect"):
        ToolRegistry().register(
            definition(
                "notes.archive_note",
                effect=SideEffect.WRITE,
                capability="write:note.text",
                sensitive=True,
            ),
            read_note,
        )


@pytest.mark.parametrize("effect", list(SensitiveEffect))
def test_no_leash_entry_or_promotion_lets_a_declared_effect_run_before_a_person_approves(
    effect: SensitiveEffect,
) -> None:
    """The second half of M12.3.8, for a tool registered through the rule above: Autonomous, and
    Autonomous again after a promotion adds a second entry, both suspend for approval of the exact
    prepared action, and Shadow still simulates because the cap only lowers. Delete this and a
    declaration can be kept at registration and lost at the gate."""
    registered = ToolRegistry().register(
        definition(
            NAMED[effect],
            effect=SideEffect.WRITE,
            capability="write:ticket.status",
            sensitive=True,
        ).model_copy(update={"entity": "ticket"}),
        read_note,
        sensitive_effect=effect,
    )
    subject = action(tool=registered.definition)
    promoted = leash_at(AutonomyTier.AUTONOMOUS).with_entry(
        LeashEntry(
            agent_id=subject.agent_id,
            target=subject.target,
            scope=leash_at(AutonomyTier.AUTONOMOUS).entries[0].scope,
            rung=AutonomyTier.AUTONOMOUS,
        )
    )
    for leash in (leash_at(AutonomyTier.AUTONOMOUS), promoted):
        governed_run = run(subject, leash=leash, caller=CALLER)
        assert governed_run.route is Route.SUSPEND
        assert governed_run.suspension is not None
        assert governed_run.suspension.action_digest == subject.digest()
    assert run(subject, leash=leash_at(AutonomyTier.SHADOW)).route is Route.SIMULATE


# ------------------------------------------------ effect and leash ceiling (M12.1.3)
def test_the_screen_calls_a_read_a_read_a_write_a_write_and_a_sensitive_effect_irreversible() -> (
    None
):
    """Three words, one reading of the declaration the gate reads. Delete this and the Tools
    screen can call a money tool a write while the leash caps it as sensitive."""
    assert effect_class(definition()) is EffectClass.READ
    for effect in (SideEffect.DRAFT, SideEffect.WRITE):
        assert effect_class(definition(effect=effect)) is EffectClass.WRITE
    for effect in (SideEffect.SEND, SideEffect.MONEY):
        assert effect_class(definition(effect=effect)) is EffectClass.IRREVERSIBLE
    flagged = definition(effect=SideEffect.WRITE, sensitive=True)
    assert effect_class(flagged) is EffectClass.IRREVERSIBLE


def test_the_leash_ceiling_is_the_side_effects_rung_held_under_the_gates_sensitive_cap() -> None:
    """Asserted against `brain.gate.leash.SENSITIVE_EFFECT_RUNG` and `default_rung`, not against
    itself. Delete this and the Tools screen can show a rung the gate never lets a call reach."""
    for effect in SideEffect:
        plain = definition(effect=effect)
        expected = default_rung(effect)
        if plain.declares_sensitive_effect():
            expected = min(expected, SENSITIVE_EFFECT_RUNG)
        assert leash_ceiling(plain) is expected
    assert (
        leash_ceiling(definition(effect=SideEffect.WRITE, sensitive=True)) is SENSITIVE_EFFECT_RUNG
    )
    assert leash_ceiling(definition(effect=SideEffect.MONEY)) is AutonomyTier.SHADOW


def test_tightening_a_leash_only_ever_lowers_a_rung() -> None:
    """`ToolRegistry.tighten`: an Autonomous entry on a money tool falls to Shadow, a Shadow entry
    on a read stays Shadow, and an entry on a target no tool carries is kept as written. Delete
    this and the side effect can be applied as a default that raises a rung somebody pinned."""
    registry = ToolRegistry()
    registry.register(definition(), read_note)
    registry.register(
        definition("books.pay_bill", effect=SideEffect.MONEY, capability="write:note.text"),
        read_note,
    )
    anywhere = leash_at(AutonomyTier.AUTONOMOUS).entries[0].scope
    leash = Leash(
        entries=(
            LeashEntry(
                agent_id="ag", target="books.pay_bill", scope=anywhere, rung=AutonomyTier.AUTONOMOUS
            ),
            LeashEntry(agent_id="ag", target=READ_NOTES, scope=anywhere, rung=AutonomyTier.SHADOW),
            LeashEntry(
                agent_id="ag", target="ticket", scope=anywhere, rung=AutonomyTier.AUTONOMOUS
            ),
        )
    )
    assert [one.rung for one in registry.tighten(leash).entries] == [
        AutonomyTier.SHADOW,
        AutonomyTier.SHADOW,
        AutonomyTier.AUTONOMOUS,
    ]
