"""Which tools an agent carries once tools and connectors are attached and detached.

Real `AgentRecord`s, real `ToolDefinition`s and the real ceiling, so what is attachable is what a
run could call. Dates are pinned far from any wall clock, for CLAUDE.md's reason.

Task ids: M39.8.6, M39.2.1.2, M39.1.1.3
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.attachments import (
    A_REQUIRED_TOOL_STAYS,
    ALREADY_ATTACHED,
    CANNOT_BE_ATTACHED,
    NOT_ATTACHED,
    NOTHING_TO_ATTACH,
    AttachmentChange,
    AttachmentError,
    attached_tools,
    connectors_after_attach,
    connectors_after_detach,
    narrowed,
    opened_by,
    to_attach,
    to_detach,
    within_ceiling,
)
from brain.agents.binding import providers
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord, entitlement_ceiling
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition
from brain.core.scope import Scope
from brain.gate.roster import setup_of
from brain.knowledge.visibility import Visibility
from brain.tables.attachment import AttachmentPart

AT = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


def tool(
    name: str, capability: str, effect: SideEffect = SideEffect.NONE, source: str = "crm"
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"The {name} tool",
        entity=capability.split(":", 1)[1].split(".", 1)[0],
        required_capability=capability,
        side_effect=effect,
        identity_mode=IdentityMode.DELEGATED,
        source=source,
    )


READ_CLIENT = tool("crm.read_client", "read:client")
READ_DEAL = tool("crm.read_deal", "read:deal")
WRITE_DEAL = tool("crm.update_deal", "write:deal.stage", SideEffect.WRITE)
READ_TICKET = tool("desk.read_ticket", "read:ticket", source="desk")
REGISTERED = (READ_CLIENT, READ_DEAL, WRITE_DEAL, READ_TICKET)

RECORD = AgentRecord(
    agent_id="sales_desk",
    display_name="Sales desk",
    persona="Answers about deals.",
    audience=AgentAudience(level=Visibility.COMPANY, owner_id="p_steward"),
    authority=AgentAuthority(
        capabilities=(
            Capability(value="read:client"),
            Capability(value="read:deal"),
            Capability(value="write:deal.stage"),
        ),
        allowed_tools=frozenset({"crm.read_client"}),
        required_tools=frozenset({"crm.read_client"}),
        max_side_effect=SideEffect.NONE,
    ),
    created_by="p_steward",
)

ADMIN = EntitlementSet(
    principal_id="p_admin",
    grants=tuple(
        Grant(capability=Capability(value=one), scope=Scope.unrestricted())
        for one in ("read:client", "read:deal", "write:deal.stage", "read:ticket")
    ),
)


def change(tools: tuple[str, ...], attached: bool, *, minutes: int) -> AttachmentChange:
    return AttachmentChange(
        agent_id="sales_desk",
        part=AttachmentPart.TOOL,
        reference=tools[0],
        attached=attached,
        tools=tools,
        at=AT + timedelta(minutes=minutes),
        changed_by="p_admin",
    )


#: A connector this release ships and an entity it provides, read through the binding's own map so
#: a renamed entity moves the test with it rather than leaving it asserting about nothing.
CONNECTOR = "freshdesk"
SOURCED = Capability(value=f"read:{min(e for e, n in providers().items() if n == CONNECTOR)}")
BOUND = RECORD.model_copy(
    update={
        "authority": RECORD.authority.model_copy(
            update={"capabilities": (*RECORD.authority.capabilities, SOURCED)}
        )
    }
)
REACHES_IT = EntitlementSet(
    principal_id="p_steward",
    grants=(*ADMIN.grants, Grant(capability=SOURCED, scope=Scope.unrestricted())),
)


def test_the_newest_press_decides_and_a_tool_nobody_pressed_keeps_the_manifests_word() -> None:
    """**M39.8.6.** A tool attached and then detached is gone, whatever order the presses are read
    in, and a tool nobody pressed on keeps the manifest's word. Delete this and a stale press
    decides, or a detached tool comes back because rows were read newest first."""
    attached = change(("crm.read_deal",), True, minutes=1)
    detached = change(("crm.read_deal",), False, minutes=2)

    assert attached_tools({"crm.read_client"}, [detached, attached]) == frozenset(
        {"crm.read_client"}
    )
    assert attached_tools({"crm.read_client"}, [attached]) == frozenset(
        {"crm.read_client", "crm.read_deal"}
    )
    assert attached_tools({"crm.read_client"}, []) == frozenset({"crm.read_client"})


def test_a_run_is_handed_only_the_tools_the_agent_carries_now() -> None:
    """**M39.8.6's last clause.** The narrowed record is what `setup_of` builds a run's ceiling
    from, so a detached tool is absent from the catalogue and the configuration hash moves; a
    required tool is never taken away, and the agent's connectors are carried over untouched.
    Delete this and a detach changes the page and not the runs, or narrowing the tools silently
    unbinds every connector the agent names."""
    attached = narrowed(RECORD, [change(("crm.read_deal",), True, minutes=1)])
    before = setup_of(attached, (one.name for one in REGISTERED))
    removed = narrowed(
        RECORD,
        [change(("crm.read_deal",), True, minutes=1), change(("crm.read_deal",), False, minutes=2)],
    )
    after = setup_of(removed, (one.name for one in REGISTERED))

    assert "crm.read_deal" in before.ceiling.allowed_tools
    assert "crm.read_deal" not in after.ceiling.allowed_tools
    assert before.config_hash != after.config_hash
    stripped = narrowed(RECORD, [change(("crm.read_client",), False, minutes=1)])
    assert "crm.read_client" in stripped.authority.allowed_tools
    assert narrowed(RECORD, []) is RECORD
    named = BOUND.model_copy(
        update={"authority": BOUND.authority.model_copy(update={"connectors": (CONNECTOR,)})}
    )
    kept = narrowed(named, [change(("crm.read_deal",), True, minutes=1)])
    assert kept.authority.connectors == (CONNECTOR,)
    assert entitlement_ceiling(kept).holds(SOURCED)


def test_an_attach_is_checked_against_the_ceiling_and_the_person_and_refused_in_one_sentence() -> (
    None
):
    """**M39.2.1.2.** A tool the ceiling holds and the person holds is attachable; a write above the
    ceiling's largest effect, a tool outside the ceiling's capabilities, a tool the person does not
    hold and a name nothing registers are all refused in the same words. Delete this and a tool no
    run could call is attached and inert, or a person hands an agent what they could not reach."""
    carried = RECORD.authority.allowed_tools
    assert to_attach(
        "crm.read_deal", record=RECORD, carried=carried, registered=REGISTERED, by=ADMIN, now=AT
    ) == ("crm.read_deal",)
    assert within_ceiling(WRITE_DEAL, RECORD) is False
    assert within_ceiling(READ_TICKET, RECORD) is False
    nobody = EntitlementSet(principal_id="p_nobody")
    for name, by in (
        ("crm.update_deal", ADMIN),
        ("desk.read_ticket", ADMIN),
        ("crm.read_deal", nobody),
        ("no.such_tool", ADMIN),
    ):
        with pytest.raises(AttachmentError) as refused:
            to_attach(name, record=RECORD, carried=carried, registered=REGISTERED, by=by, now=AT)
        assert str(refused.value) == CANNOT_BE_ATTACHED
    with pytest.raises(AttachmentError) as again:
        to_attach(
            "crm.read_client",
            record=RECORD,
            carried=carried,
            registered=REGISTERED,
            by=ADMIN,
            now=AT,
        )
    assert str(again.value) == ALREADY_ATTACHED


def test_a_detach_asks_nothing_of_the_person_and_keeps_a_required_tool() -> None:
    """A detach of a tool nothing carries is refused, and so is one of a required tool; any other
    is moved. Delete this and a detach breaks every run of the agent."""
    carried = RECORD.authority.allowed_tools
    with pytest.raises(AttachmentError) as nothing:
        to_detach("crm.read_deal", record=RECORD, carried=carried)
    assert str(nothing.value) == NOT_ATTACHED
    with pytest.raises(AttachmentError) as required:
        to_detach("crm.read_client", record=RECORD, carried=carried)
    assert str(required.value) == A_REQUIRED_TOOL_STAYS
    wider = frozenset({"crm.read_client", "crm.read_deal"})
    assert to_detach("crm.read_deal", record=RECORD, carried=wider) == ("crm.read_deal",)


def test_a_connector_is_the_agents_own_list_and_opens_only_what_its_attacher_reaches() -> None:
    """**M39.8.6 for connectors** (`A_CONNECTOR_IS_THE_AGENTS_OWN_LIST_AND_NOTHING_ELSE`). What a
    connector opens is read through `bound_capabilities`: the agent's read on its entity, and
    nothing else of the ceiling. Attaching it appends its name to the agent's list, which the
    ceiling then holds the read through; a person who does not reach the read, a connector that
    opens nothing for this agent and a name no connector has are refused in one sentence; one
    already named is told so. Detaching takes the name out and asks nothing of the person; one not
    named is refused. Delete this and a steward hands an agent a source they cannot read, or a
    connector is bound that changes no run.

    The positive half is the first assertion pair: without it a function refusing every attach
    would satisfy the refusals below it."""
    assert opened_by(BOUND, CONNECTOR) == (SOURCED,)
    assert not entitlement_ceiling(BOUND).holds(SOURCED)
    becomes = connectors_after_attach(CONNECTOR, record=BOUND, by=REACHES_IT, now=AT)
    assert becomes == (CONNECTOR,)
    named = BOUND.model_copy(
        update={"authority": BOUND.authority.model_copy(update={"connectors": becomes})}
    )
    assert entitlement_ceiling(named).holds(SOURCED)
    assert opened_by(named, CONNECTOR) == ()

    for connector, record, by in (
        (CONNECTOR, BOUND, ADMIN),
        (CONNECTOR, RECORD, REACHES_IT),
        ("no_such_connector", BOUND, REACHES_IT),
    ):
        with pytest.raises(AttachmentError) as refused:
            connectors_after_attach(connector, record=record, by=by, now=AT)
        assert str(refused.value) == NOTHING_TO_ATTACH
    with pytest.raises(AttachmentError) as again:
        connectors_after_attach(CONNECTOR, record=named, by=REACHES_IT, now=AT)
    assert str(again.value) == ALREADY_ATTACHED

    assert connectors_after_detach(CONNECTOR, record=named) == ()
    with pytest.raises(AttachmentError) as unnamed:
        connectors_after_detach(CONNECTOR, record=BOUND)
    assert str(unnamed.value) == NOT_ATTACHED
