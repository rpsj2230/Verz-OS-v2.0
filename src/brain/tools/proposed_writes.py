"""A connector's write as a tool in the registry, which a model may ask for and nothing may call.

Until this module the registry held no tool that changes anything. `freshdesk.reply_to_ticket` was
a `ToolDefinition` that existed only as a name inside a write grant, and an agent run offers a
model what the projected catalogue holds, and the catalogue is projected from the registry. So an
agent whose ceiling named the tool never saw it, and the run that holds a write for a person
(`brain.gate.runtime`) had nothing to hold.

**It is registered, and it cannot be called.** The registered handler raises whoever calls it, so
the one way to reach a connector's write stays the approved action the worker sends with the
grant's own key (`brain.ops.approved_runs.ConnectorWrites`). `brain.gate.runtime` never calls it
either: a model's request for it is a proposal, decided by the leash. Both are held, the first by
this handler and the second by `assert_no_side_effect`, because a registered tool is one a later
caller will find, and the caller who finds it should meet a refusal rather than a send. See
`A_REGISTERED_WRITE_IS_A_NAME_AND_NEVER_A_WAY_TO_SEND`.

**Only a write with a preparer is registered.** A connector says how a model's arguments become
the action a person approves (`brain.connectors.declaration.ProposesAction`); a write grant that
declares none sends approved actions raised some other way and is not offered to a model, because
there would be nothing to build the held action from but the model's own words. A write whose
entity has no row tool in this registry is skipped too: the run reads the record a write is
about, at the run's reach, before anything is prepared, and a tool that can never find its record
is one a model would be offered and always refused.

**The scope is the pin a row tool has.** A SERVICE tool must carry a scope that narrows something,
and a write is registered as the same tool kind as the read beside it: this source and this entity.
It decides nothing about who may ask, which is the run's reach and the leash.

**The sensitive effect is read from the tool's name and never defaulted.** The registry refuses a
tool that is declared sensitive and names no effect, and one whose name says it has one and does not
declare it, so the effect passed here is the one its name reads as, and a name that reads as none
or several is left for the registry to refuse. A connector's write that sends a client a message is
therefore a `client_message` because its name says `reply`, and one that says nothing is refused at
start-up and not guessed at.

Task ids: M13.7.6, M13.7.7
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict

from brain.connectors.declaration import ConnectorDeclaration, proposers
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import Entity, TypedResult
from brain.core.scope import Clause, Op, Scope
from brain.ops.idempotency import IdempotencyError
from brain.tools.registry import (
    ResultContract,
    SensitiveEffect,
    ToolRegistry,
    sensitive_effects_named_by,
)

#: Why a registered write refuses every direct call.
A_REGISTERED_WRITE_IS_A_NAME_AND_NEVER_A_WAY_TO_SEND: Final = (
    "A write is in the registry so that an agent's catalogue can offer it and a run can hold its "
    "call for a person. Whatever sends it is the worker's, after an approval, with a key the "
    "install gave for that write alone. So the handler a registry holds for it is one that refuses "
    "to be called, and every caller that finds a tool by name meets the refusal."
)


class WriteAsked(BaseModel):
    """What a caller of a write tool by name would pass. Anything, and it is never read."""

    model_config = ConfigDict(extra="allow")


class WriteRefused(Entity):
    """The record type a registered write promises, which it never returns."""


async def never_called_directly(
    request: WriteAsked, *, entitlement: EntitlementSet, now: datetime | None = None
) -> TypedResult[WriteRefused]:
    """Refuse. See `A_REGISTERED_WRITE_IS_A_NAME_AND_NEVER_A_WAY_TO_SEND`."""
    del request, entitlement, now
    raise IdempotencyError(A_REGISTERED_WRITE_IS_A_NAME_AND_NEVER_A_WAY_TO_SEND)


def reader_name(source: str, entity: str) -> str:
    """The row tool that reads what a write writes, by the grammar `RowTool.name` gives it."""
    return f"{source}.read_{entity}"


def register_proposed_writes(
    registry: ToolRegistry, declarations: Mapping[str, ConnectorDeclaration]
) -> tuple[str, ...]:
    """Register every write a connector prepares for a model, and say which were registered.

    Each beside the row tool that reads its entity, in name order so two builds register the same
    tools in the same order. A write whose reader is not registered is skipped, and so is one whose
    tool declares no arguments to check: see the module docstring.
    """
    registered: list[str] = []
    for name, (_connector, _grant, preparer) in sorted(proposers(declarations).items()):
        tool = preparer.tool
        if not tool.args_schema.get("properties"):
            continue
        if not registry.has(reader_name(tool.source, tool.entity)):
            continue
        named = sensitive_effects_named_by(tool.name)
        effect: SensitiveEffect | None = next(iter(named)) if len(named) == 1 else None
        registry.register(
            tool,
            never_called_directly,
            result_contract=ResultContract.TYPED,
            scope=Scope(
                clauses=(
                    Clause(field="source", op=Op.EQ, value=tool.source),
                    Clause(field="entity", op=Op.EQ, value=tool.entity),
                )
            ),
            sensitive_effect=effect,
        )
        registered.append(name)
    return tuple(registered)
