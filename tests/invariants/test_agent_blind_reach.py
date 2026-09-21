"""No agent setting can widen what a run returns, because the three things that decide it cannot
see an agent.

`E_run(caller, agent) = E(caller) ∩ agent_ceiling` has one place the agent enters, which is the
intersection in `brain.gate.leash`. Everything that decides a caller's reach before it, and
everything that removes fields after it, is agent-blind: the entitlement resolver, the
entitlement hash the answer cache keys on, and the redactor. If any of them took an agent, an
agent's configuration could reach a decision that is only ever supposed to narrow, and the
first sign would be an answer that is simply too wide.

So this reads each function's inputs as types, all the way down through every model, dataclass
and protocol they are built from, and fails when an agent-bearing type or a field named for an
agent appears anywhere in them. A parameter that does not exist has to be added before it can be
misused, and adding it turns this red. The behavioural half calls each one with an agent and
expects a `TypeError`, because a `**kwargs` would pass the type walk and swallow one.

Task ids: M3.9.5
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import typing
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

import pytest
from pydantic import BaseModel

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import Entity, TypedResult
from brain.core.field_policy import FieldPolicy
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.redaction import compute_mask, redact, serialise_for_channel, simulate_redaction
from brain.gate import resolve as gate_resolve
from brain.identity.packs import resolve_entitlement

NOW = datetime(2999, 1, 1, tzinfo=UTC)

#: The functions M3.9.5 names: the entitlement resolver (both halves: the pure union over grant
#: rows and the gate step that loads and caches it), the entitlement hash, and the redactor's
#: every public entry point.
AGENT_BLIND: dict[str, Callable[..., object]] = {
    "brain.identity.packs.resolve_entitlement": resolve_entitlement,
    "brain.gate.resolve.resolve": gate_resolve.resolve,
    "brain.core.entitlement.EntitlementSet.ent_hash": EntitlementSet.ent_hash,
    "brain.core.redaction.redact": redact,
    "brain.core.redaction.serialise_for_channel": serialise_for_channel,
    "brain.core.redaction.compute_mask": compute_mask,
    "brain.core.redaction.simulate_redaction": simulate_redaction,
}

#: Modules whose types carry an agent: its record, its ceiling, its leash, its catalogue, its
#: invocation, its selection. A type from any of them in a resolver's or redactor's inputs is an
#: agent reaching the decision.
AGENT_BEARING_MODULES: tuple[str, ...] = (
    "brain.agents",
    "brain.gate.catalogue",
    "brain.gate.invoke",
    "brain.gate.leash",
    "brain.gate.select",
    "brain.orchestration",
)


def _hints(target: object) -> dict[str, Any]:
    try:
        return typing.get_type_hints(target, include_extras=True)
    except (NameError, TypeError):
        # A class whose annotations name something only its own module imports. Its fields
        # are still read from pydantic below; a plain class with none has nothing to walk.
        return {}


def _fields_of(cls: type) -> dict[str, Any]:
    """Every declared input of a type, by name: model fields, dataclass fields, annotations,
    and the parameters of a protocol's methods."""
    found: dict[str, Any] = {}
    if issubclass(cls, BaseModel):
        for name, info in cls.model_fields.items():
            found[name] = info.annotation
    if dataclasses.is_dataclass(cls):
        hints = _hints(cls)
        for f in dataclasses.fields(cls):
            found[f.name] = hints.get(f.name, f.type)
    if getattr(cls, "_is_protocol", False):
        for name, member in vars(cls).items():
            if callable(member) and not name.startswith("_"):
                for param, hint in _hints(member).items():
                    found[f"{name}.{param}"] = hint
    return found


def reachable(function: Callable[..., object]) -> tuple[set[type], set[str]]:
    """Every `brain` type and every input name reachable from a function's parameters."""
    types: set[type] = set()
    names: set[str] = set(inspect.signature(function).parameters)
    owner = getattr(function, "__qualname__", "").rsplit(".", 1)
    pending: list[Any] = [v for k, v in _hints(function).items() if k != "return"]
    if len(owner) == 2 and owner[0] == "EntitlementSet":
        pending.append(EntitlementSet)
    while pending:
        hint = pending.pop()
        if isinstance(hint, TypeVar):
            pending.extend(c for c in (hint.__bound__, *hint.__constraints__) if c is not None)
            continue
        pending.extend(typing.get_args(hint))
        origin = typing.get_origin(hint)
        cls = origin if isinstance(origin, type) else hint
        if not isinstance(cls, type) or not cls.__module__.startswith("brain"):
            continue
        if cls in types:
            continue
        types.add(cls)
        for name, inner in _fields_of(cls).items():
            names.add(name)
            pending.append(inner)
    return types, names


@pytest.mark.parametrize("label", sorted(AGENT_BLIND))
def test_no_agent_type_is_reachable_from_the_inputs_of_the_resolver_hash_or_redactor(
    label: str,
) -> None:
    """M3.9.5, by type. Deleting this lets an `AgentCeiling`, a leash or an agent record be
    threaded into the resolver, the hash or the redactor, and from then on an agent setting can
    decide how wide an answer is, which the invariant says only a caller's grants may."""
    types, _ = reachable(AGENT_BLIND[label])
    carrying = sorted(
        f"{t.__module__}.{t.__qualname__}"
        for t in types
        if t.__module__.startswith(AGENT_BEARING_MODULES)
    )
    assert carrying == [], f"{label} can be handed an agent through {carrying}"


@pytest.mark.parametrize("label", sorted(AGENT_BLIND))
def test_no_input_of_the_resolver_hash_or_redactor_is_named_for_an_agent(label: str) -> None:
    """M3.9.5, by name. Deleting this admits `agent_id: str`, which the type walk cannot see
    because a string is a string, and an agent id is all a lookup needs to widen a result."""
    _, names = reachable(AGENT_BLIND[label])
    assert sorted(n for n in names if "agent" in n.lower()) == []


def test_the_walk_sees_an_agent_when_one_is_there() -> None:
    """The positive case. Deleting this lets the two tests above pass because the walk found
    nothing at all, which is what a broken walk and an agent-blind function look alike in."""
    from brain.gate.leash import decide

    types, names = reachable(decide)
    assert any(t.__module__ == "brain.gate.leash" for t in types)
    assert "agent_ceiling" in names
    # And it reaches through the models: an entitlement's grants and their scopes.
    types, _ = reachable(redact)
    assert {t.__name__ for t in types} >= {"EntitlementSet", "Grant", "Scope", "FieldPolicy"}


def test_there_is_no_agent_kind_of_principal() -> None:
    """An agent is a lens, never a principal. Deleting this lets an `AGENT` kind be added, and
    then an agent resolves an entitlement of its own through the resolver above."""
    assert {kind.value for kind in PrincipalKind} == {"human", "service"}


class _Row(Entity):
    status: str = ""


def _call_with_an_agent(label: str) -> object:
    principal = Principal(
        id="u_1", kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name="One"
    )
    reach = EntitlementSet(principal_id="u_1", grants=())
    result = TypedResult[_Row](records=(_Row(entity="row", id="r_1"),))
    policy = FieldPolicy(rules=())
    # `Any`, because the point is a call no signature admits: mypy refusing it statically is
    # the same property this asserts at run time, and the run-time half is the one CI keeps.
    agent: dict[str, Any] = {"agent": "ag_support"}
    nothing: Any = None
    match label:
        case "brain.identity.packs.resolve_entitlement":
            return resolve_entitlement(principal, now=NOW, **agent)
        case "brain.gate.resolve.resolve":
            return asyncio.run(
                gate_resolve.resolve(
                    "u_1", versions=nothing, store=nothing, cache=nothing, now=NOW, **agent
                )
            )
        case "brain.core.entitlement.EntitlementSet.ent_hash":
            return reach.ent_hash(**agent)
        case "brain.core.redaction.redact":
            return redact(result, entitlement=reach, policy=policy, **agent)
        case "brain.core.redaction.serialise_for_channel":
            return serialise_for_channel(result, entitlement=reach, policy=policy, **agent)
        case "brain.core.redaction.compute_mask":
            return compute_mask("row", (), entitlement=reach, policy=policy, row={}, **agent)
        case "brain.core.redaction.simulate_redaction":
            return simulate_redaction(result, entitlement=reach, policy=policy, **agent)
    raise AssertionError(label)


@pytest.mark.parametrize("label", sorted(AGENT_BLIND))
def test_handing_the_resolver_hash_or_redactor_an_agent_is_refused(label: str) -> None:
    """M3.9.5's "a test fails if any of them is given one", behaviourally. Deleting this lets a
    `**kwargs` catch-all be added, which the signature walk reads as nothing and which would
    quietly accept an agent and could one day act on it."""
    with pytest.raises(TypeError):
        _call_with_an_agent(label)
