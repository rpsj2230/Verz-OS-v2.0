"""The connectors' writes, as an agent run may ask for them: prepared by the connector, held here.

`brain.gate.runtime.SideEffects` is what lets a run offer a tool that changes something, and this
is the implementation an install builds. A connector declares, on the write grant that sends a
tool, how a model's arguments become the action a person approves
(`brain.connectors.declaration.ProposesAction`); this module finds those declarations, checks a
model's arguments against the tool's own schema, hands the connector the record the run read and
the connection's settings, and stores what the leash says must wait.

**Nothing here decides a permission.** Whether a write may be asked for at all is the agent's
tool ceiling and the run's reach, which the projected catalogue and the runtime have already
applied; what happens to it is `brain.gate.leash`. This module is the translation between a
model's JSON and a connector's preparer, and the door to the suspension table.

**The arguments are checked against the tool's schema before the connector sees them, and a
tool with no schema is never offered.** A model's arguments are its own words, so the check is
exact: every key the schema names and none it does not, each a string, none longer than the schema
allows. A write tool whose `args_schema` names no property would be offered with nothing to check
its arguments against, so `offers` refuses it. Rejected: leaving the check to each preparer. The
first one to forget it is the one a model finds, and a check made once here is the check every
connector's write gets.

**The department an approver is matched against comes from the connection, never from the
model.** `action_for` is handed the connection's settings and the record the run read, and the
connector's own declaration says what each is for. A run proposing a write for a connector nobody
has connected is answered as a tool that is not there.

**The ledger is a refusing one.** `brain.gate.leash.govern` takes a ledger and a run never
reaches it, because every write a run proposes waits for a person
(`brain.gate.runtime.RUNTIME_WRITES_ALWAYS_WAIT_FOR_A_PERSON`). Giving it the install's real ledger
would be a way for a later change to execute from a run without noticing; the one given here
raises the first time anything asks it for a key.

Task ids: M13.7.6, M13.7.7
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from pydantic import JsonValue

from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import (
    ConnectorDeclaration,
    ProposesAction,
    SimulatesAction,
    proposers,
)
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import ToolDefinition, TypedResult
from brain.core.field_policy import FieldPolicy
from brain.gate.injection import RiskAssessment, assess
from brain.gate.leash import Action, SuspendedAction
from brain.gate.runtime import NoRuntimeLedger
from brain.gate.suspension_store import StoredSuspensions, put_suspension
from brain.ops.idempotency import OperationLedger
from brain.tools.startup import field_policy_for

#: Why a model's arguments are held to the tool's schema before a connector reads them.
A_MODELS_ARGUMENTS_ARE_CHECKED_AGAINST_THE_TOOLS_OWN_SCHEMA: Final = (
    "A model's arguments are its own words. Each write tool declares the keys it takes and that "
    "each is a string with a length, and a call carrying any other key, missing one, holding a "
    "value that is not a string or one longer than the schema says is answered as a tool that "
    "is not there, before the connector's preparer is asked about it. A tool whose schema names "
    "nothing has nothing to check against and is never offered."
)


def arguments_fit(
    tool: ToolDefinition, arguments: Mapping[str, JsonValue]
) -> dict[str, str] | None:
    """The arguments as strings when they are exactly what the tool's schema takes, else None.

    See `A_MODELS_ARGUMENTS_ARE_CHECKED_AGAINST_THE_TOOLS_OWN_SCHEMA`. A property typed as
    anything but a string is a schema this check cannot judge, and the call is refused rather than
    passed.
    """
    properties = tool.args_schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return None
    required = tool.args_schema.get("required", [])
    if not isinstance(required, list):
        return None
    if set(arguments) - set(properties) or not set(required) <= set(arguments):
        return None
    fitted: dict[str, str] = {}
    for name, value in arguments.items():
        shape = properties[name]
        if not isinstance(value, str):
            return None
        if not isinstance(shape, dict) or shape.get("type") != "string":
            return None
        longest = shape.get("maxLength")
        if isinstance(longest, int) and len(value) > longest:
            return None
        fitted[name] = value
    return fitted


def action_policy(action: Action) -> FieldPolicy:
    """The field policy an action's target is decided under: its source's read classification,
    and the fields that source's write grants declare (`brain.tools.startup.field_policy_for`).

    The one function a held action is decided under where it is raised and where it is run
    (`brain.ops.approved_runs.policy_of` is this), so the two cannot disagree about which fields
    the reach must hold.
    """
    return field_policy_for(action.target, source=action.tool.source or None)


def action_assessment(action: Action) -> RiskAssessment:
    """The injection screen over what the action carries, as the worker takes it when it runs it.

    The same function where the action is raised and where it is run, so the two see one score
    (`brain.ops.approved_runs.assessment_of` is this).
    """
    return assess(json.dumps(dict(action.args), sort_keys=True, default=str))


@dataclass(frozen=True)
class ConnectorSideEffects:
    """`brain.gate.runtime.SideEffects` over the connectors' declarations and the suspension store.

    `connections` are the live ones, read at each proposal so a connector disconnected a moment
    ago is not written to; `declarations` default to the install's catalogue, so a connector
    reviewed on it is included.
    """

    suspensions: StoredSuspensions
    connections: Callable[[], Awaitable[Sequence[Any]]]
    declarations: Mapping[str, ConnectorDeclaration] | None = None
    ledger: OperationLedger = field(default_factory=NoRuntimeLedger)

    def _declared(self) -> Mapping[str, ConnectorDeclaration]:
        """The declarations asked about: those given, or this install's catalogue, which is the
        shipped connectors and the reviewed ones and what the registry's writes were read from."""
        if self.declarations is not None:
            return self.declarations
        from brain.ops.connector_catalogue import declarations

        return declarations()

    def _preparer(self, tool: ToolDefinition) -> tuple[str, ProposesAction] | None:
        found = proposers(self._declared()).get(tool.name)
        if found is None or found[2].tool != tool:
            return None
        return found[0], found[2]

    def offers(self, tool: ToolDefinition) -> bool:
        return self._preparer(tool) is not None and bool(tool.args_schema.get("properties"))

    def target_of(self, tool: ToolDefinition, arguments: Mapping[str, JsonValue]) -> str | None:
        prepared = self._preparer(tool)
        fitted = arguments_fit(tool, arguments)
        if prepared is None or fitted is None:
            return None
        try:
            return prepared[1].target_of(fitted)
        except ConnectorContractError:
            return None

    async def propose(
        self,
        tool: ToolDefinition,
        arguments: Mapping[str, JsonValue],
        *,
        agent_id: str,
        record: Mapping[str, Any],
    ) -> Action | None:
        prepared = self._preparer(tool)
        fitted = arguments_fit(tool, arguments)
        if prepared is None or fitted is None:
            return None
        connector, preparer = prepared
        connection = next(
            (one for one in await self.connections() if one.connector == connector), None
        )
        if connection is None:
            return None
        try:
            return preparer.action_for(
                fitted, agent_id=agent_id, record=record, settings=connection.settings
            )
        except ConnectorContractError:
            return None

    def simulate(self, action: Action) -> TypedResult[Any] | None:
        prepared = self._preparer(action.tool)
        if prepared is None or not isinstance(prepared[1], SimulatesAction):
            return None
        return prepared[1].simulate(action)

    def policy_for(self, action: Action) -> FieldPolicy:
        return action_policy(action)

    def assessment_for(self, action: Action) -> RiskAssessment:
        return action_assessment(action)

    async def hold(self, suspension: SuspendedAction, reach: EntitlementSet, now: datetime) -> None:
        async with self.suspensions.holding(reach, now) as rows:
            await put_suspension(rows.session, suspension)
