"""The install acceptance checks for tools: the catalogue table, the sensitive effects, the switch.

Three checks, split where the leaves split. The first builds the install's registry through
`brain.tools.startup.build_registry`, the one builder the application calls, writes it to
`agent.tool_definition` through the function the application calls at start, and reads every row
back beside the registration that produced it, then asks the table itself to take a name the
grammar refuses. The second registers tools the check declares into the install's own registry
class, whose rules are the ones every tool meets. The third switches one of the install's own
tools off and on through the functions the Tools screen's route calls, and calls it as reserved
principals of both reserved departments between each switch.

**The catalogue check writes the rows the application writes at start, and reads them back.**
`brain.app` calls `record_catalogue` once per process start and survives its failure, so on an
install that has started the rows are there already and the check's write is an upsert that
changes nothing; on a database nothing has started against (the one the unit suite builds), the
check's write is the only one. Either way the proof is the same: every tool the install's builder
registers has a row saying what its registration says. Rejected: reading only what is committed,
which is a check the unit suite cannot pass and would therefore be excluded from it, and a check
nobody runs before the owner's server is the shape `brain.tools.startup` was written to end.

**The switch check uses a real tool, and nobody else sees the switch.** `knowledge.read_document`
is registered on every install with a database and reads nothing for a reach holding no knowledge
grant, so a call that the switch lets through returns an empty result and a call it stops raises
`ToolSwitchedOffError`, and the two cannot be mistaken for each other. The stops are rows in the
check's transaction, which no other connection can read, so no real call is refused by them. See
`A_SWITCH_THE_CHECK_THROWS_STOPS_ONLY_ITS_OWN_CALLS`.

**What a department administrator may do is asked of the route's own two questions.**
`brain.tool_routes.may_switch_install` and `may_stop` are the whole place rule the route applies
before it writes, and a switch back on at the department's own place is written as the route would
write it, so "cannot switch it back" is seen in the table: the install's stop is still live and
still refuses their people's calls.

Task ids: M38.5.1
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert, text
from sqlalchemy.exc import IntegrityError

from brain.core.scope import Scope
from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    check,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.core.envelope import ToolDefinition, TypedResult
    from brain.knowledge.rows import RowRecord
    from brain.tools.registry import SensitiveEffect, ToolRegistry, ToolSwitchedOffError

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the switch check's stops refuse nobody but the check.
A_SWITCH_THE_CHECK_THROWS_STOPS_ONLY_ITS_OWN_CALLS: Final = (
    "The switch check writes its stops inside its own transaction, which is rolled back when it "
    "ends, and no other connection can read an uncommitted row. So the install's tool is switched "
    "off for the check's reserved principals and for nobody else, and never for longer than the "
    "check."
)

# ------------------------------------------------------------------------ the figures
#: The install's tool the switch check stops. Registered wherever there is a database.
SWITCHED: Final = "knowledge.read_document"

#: The entity the check's own declared tools return.
ENTITY: Final = "acceptance_record"

#: The capability the check's own declared tools require: a write, as a side effect needs.
WRITES: Final = "write:acceptance_record"

#: One name per sensitive effect, each read as that effect by its words.
SENSITIVELY_NAMED: Final = (
    ("acceptance.send_reminder", "client_message"),
    ("acceptance.issue_quote", "quotation"),
    ("acceptance.update_dns", "dns_or_hosting"),
    ("acceptance.void_invoice", "financial_record"),
    ("acceptance.delete_record", "deletion"),
    ("acceptance.publish_post", "publication"),
    ("acceptance.deploy_release", "production_change"),
)

#: The two contracts a tool may declare, and no third.
CONTRACTS: Final = frozenset({"typed", "opaque"})


# ------------------------------------------------------------------------ the helpers
def _everywhere(*capabilities: str) -> tuple[tuple[str, Scope], ...]:
    return tuple((one, Scope.unrestricted()) for one in capabilities)


def _in(department: str, *capabilities: str) -> tuple[tuple[str, Scope], ...]:
    return tuple((one, Scope.department(department)) for one in capabilities)


def _install_registry(h: Harness) -> ToolRegistry:
    """The registry this install's application builds, over the check's own sessions."""
    from brain.knowledge.row_store import SessionRowSource
    from brain.tools.startup import build_registry

    return build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))


async def _declared_handler(*, entitlement: EntitlementSet) -> TypedResult[RowRecord]:
    """A handler for the tools the check declares. Registered and never called."""
    del entitlement
    raise CheckFailedError("a tool the check declared was called")


def _definition(name: str, *, side_effect: str = "write", sensitive: bool = False) -> Any:
    from brain.core.envelope import SideEffect, ToolDefinition

    return ToolDefinition(
        name=name,
        description=f"Declared by an install acceptance check as {name}",
        entity=ENTITY,
        required_capability=WRITES if side_effect != "none" else f"read:{ENTITY}",
        side_effect=SideEffect(side_effect),
        sensitive=sensitive,
    )


def _registers(definition: ToolDefinition, **kwargs: Any) -> bool:
    """Whether the install's registry class takes this declaration, in a registry of its own."""
    from brain.tools.registry import ToolRegistrationError, ToolRegistry

    try:
        ToolRegistry().register(definition, _declared_handler, **kwargs)
    except ToolRegistrationError:
        return False
    return True


def _effect(value: str) -> SensitiveEffect:
    from brain.tools.registry import SensitiveEffect

    return SensitiveEffect(value)


async def _refused_by_the_table(h: Harness, **values: Any) -> str | None:
    """The check constraint the catalogue table names when it refuses this row, or None.

    In a session of its own, whose savepoint is rolled back on the refusal so the check's
    transaction carries on.
    """
    from brain.tables.tool_definition import ToolDefinitionRow

    async with h.sessions() as session:
        try:
            await session.execute(insert(ToolDefinitionRow).values(**values))
        except IntegrityError as refused:
            await session.rollback()
            diagnosis = getattr(refused.orig, "diag", None)
            return str(getattr(diagnosis, "constraint_name", "") or "unnamed")
        await session.commit()
    return None


async def _ledgered(h: Harness, subject: str) -> list[tuple[str, dict[str, Any]]]:
    """The actor and details of every entry about `subject` in the check's transaction."""
    rows = (
        await h.execute(
            text(
                "SELECT actor_id, details FROM obs.audit_entry"
                " WHERE subject = :subject ORDER BY seq"
            ).bindparams(subject=subject)
        )
    ).all()
    return [
        (str(actor), details if isinstance(details, dict) else json.loads(details))
        for actor, details in rows
    ]


# ------------------------------------------------------------ 1. the catalogue table
@check(
    leaves=("M12.1.1", "M12.1.4"),
    sentence=(
        "Every tool the install's own builder registers is written to agent.tool_definition by the "
        "function the application calls at start and reads back as registered, each declaring a "
        "typed or opaque result; the table refuses a name outside the tool grammar and a third "
        "contract, and the registry refuses an opaque tool asking for less than opaque reads."
    ),
)
async def every_registered_tool_is_a_catalogue_row_under_the_name_grammar(h: Harness) -> None:
    from brain.core.redaction import OPAQUE_CAPABILITY
    from brain.ops.tool_store import definition_values, record_catalogue, recorded_tools
    from brain.tools.registry import ResultContract, ToolRegistrationError, assert_tool_name

    registry = _install_registry(h)
    if not len(registry):
        raise CheckFailedError("the install's builder registered no tool")
    if {one.value for one in ResultContract} != CONTRACTS:
        raise CheckFailedError("a tool may declare a result contract other than typed or opaque")
    written = await record_catalogue(h.sessions, registry)
    if written != len(registry):
        raise CheckFailedError("the catalogue was not written for every registered tool")
    async with h.sessions() as session:
        rows = {one.name: one for one in await recorded_tools(session)}
    for name in registry.names():
        tool = registry.get(name)
        row = rows.get(name)
        if row is None:
            raise CheckFailedError(
                "a tool the install registers has no row in agent.tool_definition"
            )
        said = {key: value for key, value in definition_values(tool).items() if key != "name"}
        if {key: getattr(row, key) for key in said} != said:
            raise CheckFailedError("a catalogue row says something its registration does not")
        if row.result_contract not in CONTRACTS:
            raise CheckFailedError("a registered tool declares no typed or opaque result contract")
        if tool.result_contract.value == "opaque" and tool.capability != OPAQUE_CAPABILITY:
            raise CheckFailedError("an opaque tool is registered asking for less than opaque reads")

    # The grammar, held by the registry and by the table; and a good name the table takes.
    bad, good = "acceptance.Read Records", f"acceptance.read_r{h.run}"
    try:
        assert_tool_name(bad)
    except ToolRegistrationError:
        pass
    else:
        raise CheckFailedError("the registry accepted a tool name outside the grammar")
    values = {
        "source": "acceptance",
        "entity": ENTITY,
        "description": "Written by an install acceptance check",
        "required_capability": f"read:{ENTITY}",
        "side_effect": "none",
        "sensitive": False,
        "sensitive_effect": None,
        "result_contract": "typed",
        "identity_mode": "delegated",
    }
    named = await _refused_by_the_table(h, name=bad, **values)
    if named is None or "name_grammar" not in named:
        raise CheckFailedError("agent.tool_definition took a name outside the tool grammar")
    contract = await _refused_by_the_table(h, name=good, **{**values, "result_contract": "raw"})
    if contract is None or "result_contract" not in contract:
        raise CheckFailedError("agent.tool_definition took a result contract that is neither")
    if await _refused_by_the_table(h, name=good, **values) is not None:
        raise CheckFailedError("agent.tool_definition refused a well-formed tool")

    # The registry's contract rule: opaque asks for opaque reads, typed asks for its entity.
    read = _definition(f"acceptance.read_r{h.run}", side_effect="none")
    if _registers(read, result_contract=ResultContract.OPAQUE):
        raise CheckFailedError("an opaque tool asking for less than opaque reads was registered")
    if not _registers(read, result_contract=ResultContract.TYPED):
        raise CheckFailedError("a well-formed typed tool was refused at registration")
    opaque = read.model_copy(update={"required_capability": OPAQUE_CAPABILITY.value})
    if not _registers(opaque, result_contract=ResultContract.OPAQUE):
        raise CheckFailedError("a well-formed opaque tool was refused at registration")


# ------------------------------------------------------ 2. the owner's sensitive effects
@check(
    leaves=("M12.3.8",),
    sentence=(
        "A tool that changes something and is named for sending a client a message, a quotation, "
        "DNS or hosting, a financial record, a deletion, a publication or a production change is "
        "refused at registration until it declares that effect, and once declared it is held at a "
        "rung where a person approves each call; a read named the same way is taken."
    ),
)
async def a_tool_named_for_a_sensitive_effect_must_declare_it(h: Harness) -> None:
    from brain.gate.leash import SENSITIVE_EFFECT_RUNG
    from brain.tools.registry import (
        NOTHING_LEAVES,
        SensitiveEffect,
        ToolRegistry,
        leash_ceiling,
        sensitive_effects_named_by,
    )

    if {value for _, value in SENSITIVELY_NAMED} != {one.value for one in SensitiveEffect}:
        raise CheckFailedError("the check does not name every one of the owner's sensitive effects")
    for name, value in SENSITIVELY_NAMED:
        if _effect(value) not in sensitive_effects_named_by(name):
            raise CheckFailedError("a tool's name did not read as the sensitive effect it says")
        if _registers(_definition(name)):
            raise CheckFailedError(
                "a tool named for a sensitive effect that declares none was registered"
            )
        declared = _definition(name, sensitive=True)
        if not _registers(declared, sensitive_effect=_effect(value)):
            raise CheckFailedError("a tool declaring its sensitive effect was refused")
        registry = ToolRegistry()
        held = registry.register(declared, _declared_handler, sensitive_effect=_effect(value))
        if held.leash_ceiling > SENSITIVE_EFFECT_RUNG or leash_ceiling(declared) != (
            held.leash_ceiling
        ):
            raise CheckFailedError("a tool with a sensitive effect is allowed past a person")
        if _registers(_definition(name, sensitive=True)):
            raise CheckFailedError("a tool declared sensitive without naming its effect was taken")
        if not _registers(_definition(name, side_effect="none")):
            raise CheckFailedError("a tool that only reads was refused for the words in its name")

    # And every tool this install registers already meets the rule it registered under.
    installed = _install_registry(h)
    for name in installed.names():
        one = installed.get(name).definition
        if one.side_effect in NOTHING_LEAVES:
            continue
        if sensitive_effects_named_by(name) and not one.declares_sensitive_effect():
            raise CheckFailedError("the install registers a tool named for a sensitive effect")


# ------------------------------------------------------------------ 3. the switch
async def _switch(
    h: Harness,
    registry: ToolRegistry,
    reach: EntitlementSet,
    department: str | None,
    *,
    reason: str | None = None,
) -> bool:
    """The route's write: attributed, the catalogue row first, then the stop or its retirement."""
    from brain.ops.tool_store import record_definition, switch_off, switch_on
    from brain.tables.audit import attributed_to

    async with h.sessions() as session, session.begin():
        for statement in attributed_to(
            actor_id=reach.principal_id, ent_hash=reach.ent_hash(), trace_id=h.trace_id
        ):
            await session.execute(statement)
        await record_definition(session, registry.get(SWITCHED))
        if reason is not None:
            return await switch_on(
                session, SWITCHED, department, by=reach.principal_id, reason=reason
            )
        return await switch_off(session, SWITCHED, department, by=reach.principal_id, reason=None)


async def _stop_id(h: Harness, department: str | None) -> str | None:
    from brain.ops.tool_store import live_stops, stop_at

    async with h.sessions() as session:
        found = stop_at(await live_stops(session), SWITCHED, department)
    return None if found is None else found.switch.switch_id


async def _called(
    h: Harness, registry: ToolRegistry, reach: EntitlementSet | None
) -> ToolSwitchedOffError | None:
    """One call to the switched tool as `reach`: the refusal a switch gave it, or None."""
    from brain.core.envelope import TypedResult
    from brain.knowledge.document_tools import DocumentRead
    from brain.tools.registry import ToolSwitchedOffError

    handler = registry.get(SWITCHED).handler
    asked = DocumentRead(document_id=f"upload.acceptance_{h.run}")
    try:
        answered = handler(asked, entitlement=reach, now=h.now)
        if inspect.isawaitable(answered):
            answered = await answered
    except ToolSwitchedOffError as refused:
        return refused
    if not isinstance(answered, TypedResult) or answered.records:
        raise CheckFailedError("a call the switch let through did not answer as the tool does")
    return None


async def _refused_everyone(
    h: Harness,
    registry: ToolRegistry,
    callers: Sequence[EntitlementSet | None],
    switch_id: str | None,
) -> bool:
    """Whether every call is refused naming this switch, in words that name nothing to the asker.

    The detail names the switch for the administrator's trace; the public sentence is the one an
    absent record gets, for `brain.tools.registry.THE_ASKER_IS_NEVER_TOLD_WHICH_SWITCH`.
    """
    from brain.core.errors import Absent

    for caller in callers:
        refused = await _called(h, registry, caller)
        if refused is None or refused.switch is None or refused.switch.switch_id != switch_id:
            return False
        if switch_id not in str(refused) or refused.public_message != Absent().public_message:
            return False
    return True


@check(
    leaves=("M12.4.3",),
    sentence=(
        "An install tool switched off for the whole install by a Super Admin refuses every call, "
        "naming the switch, until switched back on with a reason; a department admin can neither "
        "switch it back nor lift it from their department, and their own stop refuses only their "
        "department's people. Every change is in the ledger."
    ),
)
async def a_switched_off_tool_is_refused_and_a_department_stops_its_own(
    h: Harness,
) -> None:
    from brain.ops.tool_store import SessionSwitchSource, departments_in_use
    from brain.tool_routes import (
        TOOL_AUTHORITY,
        may_open,
        may_stop,
        may_switch_install,
        offered_departments,
    )

    registry = _install_registry(h).govern(SessionSwitchSource(h.sessions))
    if not registry.has(SWITCHED):
        raise CheckFailedError("the install does not register the tool the check switches")
    await h.found_departments()
    admin, head = h.principal(A, "tools"), h.principal(B, "tools")
    member_a, member_b = h.principal(A, "member"), h.principal(B, "member")
    await h.person(admin, department=A, grants=_everywhere(TOOL_AUTHORITY.value))
    await h.person(head, department=B, grants=_in(B, TOOL_AUTHORITY.value))
    await h.person(member_a, department=A)
    await h.person(member_b, department=B)
    super_admin, department_admin = await h.reach(admin), await h.reach(head)
    in_a, in_b = await h.reach(member_a), await h.reach(member_b)

    # The place rule, as the route asks it before anything is written.
    if not may_switch_install(super_admin, h.now):
        raise CheckFailedError("a Super Admin may not switch a tool for the whole install")
    if may_switch_install(department_admin, h.now) or not may_open(department_admin, h.now):
        raise CheckFailedError("a department admin may switch a tool for the whole install")
    if not may_stop(department_admin, B, h.now) or may_stop(department_admin, A, h.now):
        raise CheckFailedError("a department admin may stop a tool outside their department")
    async with h.sessions() as session:
        in_use = await departments_in_use(session)
    if offered_departments(department_admin, in_use, h.now) != (B,):
        raise CheckFailedError("a department admin was offered a department that is not theirs")

    # Before any stop, every call runs.
    if await _called(h, registry, in_a) or await _called(h, registry, in_b):
        raise CheckFailedError("a tool nobody switched off refused a call")

    # The install's switch: every call refused, naming it, and not lifted from a department.
    if not await _switch(h, registry, super_admin, None):
        raise CheckFailedError("switching a tool off for the install wrote no stop")
    install = await _stop_id(h, None)
    if not await _refused_everyone(h, registry, (in_a, in_b, None), install):
        raise CheckFailedError("a call to a switched-off tool was not refused naming the switch")
    if await _switch(h, registry, department_admin, B, reason="Wanted back in this department"):
        raise CheckFailedError("a department admin's switch on lifted the install's stop")
    if await _stop_id(h, None) != install or not await _refused_everyone(
        h, registry, (in_b,), install
    ):
        raise CheckFailedError("a department admin switched a tool back on for the install")
    if not await _switch(h, registry, super_admin, None, reason="Checked and safe to run again"):
        raise CheckFailedError("switching a tool back on for the install retired no stop")
    if await _called(h, registry, in_a) or await _called(h, registry, in_b):
        raise CheckFailedError("a tool switched back on still refused a call")

    # A department's own stop: their people refused, everybody else answered.
    if not await _switch(h, registry, department_admin, B):
        raise CheckFailedError("a department admin's stop for their department wrote nothing")
    stopped = await _stop_id(h, B)
    if not await _refused_everyone(h, registry, (in_b, None), stopped):
        raise CheckFailedError("a department's stop did not refuse its own people's calls")
    if await _called(h, registry, in_a):
        raise CheckFailedError("a department's stop refused a call from another department")

    for subject, actor, changes in (
        (f"setting:tool_switch.{install}", admin, ["off", "on"]),
        (f"setting:tool_switch.{stopped}", head, ["off"]),
    ):
        entries = await _ledgered(h, subject)
        if [(who, d.get("change")) for who, d in entries] != [(actor, one) for one in changes]:
            raise CheckFailedError("a switch did not reach the ledger naming who threw it")
