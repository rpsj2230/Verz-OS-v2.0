"""A run another agent handed on is narrowed by the agents above it at every tool call.

Over `brain.api_routes.reach_again` and `through_lenses`. `Answering.lenses` carries the ceilings of
the coordinating agent and the subtask, and the reach resolved again before each tool call folds
them into the fresh one. Without them a specialist would hold, from its first tool call, what the
two lenses above it took away at the start.

Task ids: M18.5.2
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

import brain.api_routes as api_routes
from brain.agents.model import CEILING_PRINCIPAL_PREFIX
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import Channel

#: Far from any wall clock: nothing here is about the present.
NOW = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)

A, B, C = "read:alpha.value", "read:beta.value", "read:gamma.value"


def _set(principal: str, *capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope()) for one in capabilities
        ),
    )


def _lens(name: str, *capabilities: str) -> EntitlementSet:
    return _set(f"{CEILING_PRINCIPAL_PREFIX}{name}", *capabilities)


def _asking(*lenses: EntitlementSet) -> api_routes.Answering:
    person = Principal(
        id="u_asker", kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name="Asker"
    )
    return api_routes.Answering(
        principal=person,
        reach=_set("u_asker", A, B, C),
        channel=Channel.CONSOLE,
        now=NOW,
        lenses=lenses,
    )


def _wired() -> Any:
    wiring = api_routes.GateWiring(
        authority=cast(Any, None),
        versions=cast(Any, None),
        store=cast(Any, None),
        cache=cast(Any, None),
    )
    return cast(Any, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(gate=wiring))))


def _held(reach: EntitlementSet) -> set[str]:
    return {
        one.value for one in (Capability(value=x) for x in (A, B, C)) if reach.scope_for(one, NOW)
    }


def test_a_question_nobody_delegated_resolves_to_the_reach_it_was_admitted_at() -> None:
    """Delete this and a plain question's reach is rebuilt on every call by a fold that has no work.

    No lens means the same object back, so a run nobody handed on is exactly what it was.
    """
    question = _asking()

    async def go() -> EntitlementSet:
        return await api_routes.reach_again(
            cast(Any, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))), question
        )(NOW)

    assert asyncio.run(go()) is question.reach


def test_each_lens_narrows_the_reach_resolved_afresh_and_it_does_so_at_every_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a delegated run gets back at its first tool call what the lenses took away.

    The person holds A, B and C at the first call and only A and C at the second, as if a grant had
    been revoked in between. The first lens keeps A and B and the second B and C, so the run holds
    B and then nothing: each call is resolved again, and each time through both lenses.
    """
    fresh = [_set("u_asker", A, B, C), _set("u_asker", A, C)]

    async def resolved(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(entitlements=fresh.pop(0))

    monkeypatch.setattr(api_routes, "resolve", resolved)
    monkeypatch.setattr(api_routes, "admit", lambda reach, *_a, **_k: reach)
    question = _asking(_lens("lead", A, B), _lens("sub", B, C))

    async def go() -> tuple[EntitlementSet, EntitlementSet]:
        again = api_routes.reach_again(_wired(), question)
        return await again(NOW), await again(NOW)

    first, second = asyncio.run(go())
    assert _held(first) == {B}
    assert _held(second) == set()
    assert first.principal_id == "u_asker"


def test_a_lens_never_adds_to_what_the_person_holds() -> None:
    """Delete this and a wide coordinator becomes a way to read what the asker cannot."""
    narrowed = api_routes.through_lenses(_set("u_asker", A), [_lens("lead", A, B, C)])
    assert _held(narrowed) == {A}


def test_the_lenses_are_folded_in_order_through_the_one_wrapper() -> None:
    """Delete this and the lenses are applied one at a time by a copy of the rule."""
    folded = api_routes.through_lenses(
        _set("u_asker", A, B, C), [_lens("one", A, B), _lens("two", B, C), _lens("three", B)]
    )
    assert _held(folded) == {B}
    assert folded.principal_id == "u_asker"
