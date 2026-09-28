"""A browser session needs room on the global budget, on every origin it touches and for its agent.

The global half is `test_browsing_sessions.py`. This is the per-domain and per-agent half, and
the rule that every limit applies at once.

The clock is 2999, for the reason CLAUDE.md records about fixtures that go off.

Task ids: M19.6.2, M19.6.3
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.browsing.concurrency import (
    DEFAULT_SESSIONS_PER_AGENT,
    DEFAULT_SESSIONS_PER_DOMAIN,
    Axis,
    SessionCounts,
    SessionLimit,
    keys_for,
    limit_for,
    may_open,
    seed_session_limits,
)
from brain.browsing.sessions import SessionError
from brain.browsing.targets import Surface, Target, Verb
from brain.core.entitlement import Capability
from brain.ops.admission import Budget, CapacityState, Resource, seed_budgets
from brain.ops.halt import in_force, stop_everything

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
READ = Capability(value="read:browser_surface")
APP = "https://books.example"
LOGIN = "https://login.example"
OTHER = "https://payroll.example"


def a_target(name: str = "books", origins: tuple[str, ...] = (APP, LOGIN)) -> Target:
    return Target(
        name=name,
        origins=frozenset(origins),
        surfaces=(
            Surface(
                name="invoices",
                origin=origins[0],
                path="/invoices",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=READ,
                reads=("number",),
            ),
        ),
    )


def global_budget() -> tuple[Budget, ...]:
    return tuple(one for one in seed_budgets() if one.resource is Resource.BROWSER_SESSIONS)


def open_one(
    target: Target | None = None,
    *,
    agent_id: str = "agent_books",
    counts: SessionCounts | None = None,
    limits: tuple[SessionLimit, ...] | None = None,
    state: CapacityState | None = None,
    halted: bool = False,
) -> object:
    return may_open(
        target or a_target(),
        agent_id=agent_id,
        trace_id="trace_test",
        budgets=global_budget(),
        state=state or CapacityState(),
        limits=seed_session_limits() if limits is None else limits,
        counts=counts or SessionCounts(),
        now=NOW,
        halts=(
            in_force([stop_everything(declared_by="sam", at=NOW, reason="portal misbehaving")])
            if halted
            else in_force([])
        ),
    )


def test_a_session_with_room_everywhere_is_admitted() -> None:
    """The positive case every refusal below needs beside it.

    Delete this and a limiter that refused every session would pass the whole file."""
    decision = open_one()

    assert decision.admitted  # type: ignore[attr-defined]
    assert decision.over == ()  # type: ignore[attr-defined]


def test_a_second_session_on_one_origin_is_refused_and_another_website_still_opens() -> None:
    """M19.6.2. One session already on the portal refuses another there, whoever asks, while a
    target on a different origin opens.

    Delete this and two sessions can drive one vendor's portal at once, which is the lockout
    the limit exists to prevent."""
    busy = SessionCounts(held={(Axis.DOMAIN, APP): 1})

    refused = open_one(counts=busy, agent_id="agent_other")
    elsewhere = open_one(a_target("payroll", (OTHER,)), counts=busy, agent_id="agent_other")

    assert not refused.admitted  # type: ignore[attr-defined]
    assert refused.over == ((Axis.DOMAIN, APP),)  # type: ignore[attr-defined]
    assert elsewhere.admitted  # type: ignore[attr-defined]


def test_a_second_session_for_one_agent_is_refused_on_any_website() -> None:
    """M19.6.3. An agent holding a session is refused another on a website nobody is using, and
    a different agent on that same website opens.

    Delete this and one agent can take every session the machine has."""
    busy = SessionCounts(held={(Axis.AGENT, "agent_books"): 1})
    payroll = a_target("payroll", (OTHER,))

    refused = open_one(payroll, counts=busy)
    another = open_one(payroll, counts=busy, agent_id="agent_payroll")

    assert not refused.admitted  # type: ignore[attr-defined]
    assert refused.over == ((Axis.AGENT, "agent_books"),)  # type: ignore[attr-defined]
    assert another.admitted  # type: ignore[attr-defined]


def test_a_session_occupies_every_origin_its_target_declares() -> None:
    """A session on the login host of a target counts against a target whose application host
    is free, because a run may touch any declared origin.

    Delete this and `keys_for` can count only the first origin, and two targets sharing a login
    host drive it twice."""
    assert keys_for(a_target(), "agent_books") == (
        (Axis.DOMAIN, APP),
        (Axis.DOMAIN, LOGIN),
        (Axis.AGENT, "agent_books"),
    )

    decision = open_one(counts=SessionCounts(held={(Axis.DOMAIN, LOGIN): 1}))

    assert decision.over == ((Axis.DOMAIN, LOGIN),)  # type: ignore[attr-defined]


def test_every_full_axis_is_named_rather_than_only_the_first() -> None:
    """A run refused on its origin and its agent at once reports both.

    Delete this and an operator fixes the first limit and is refused by the second."""
    busy = SessionCounts(held={(Axis.DOMAIN, APP): 1, (Axis.AGENT, "agent_books"): 1})

    decision = open_one(counts=busy)

    assert decision.over == ((Axis.DOMAIN, APP), (Axis.AGENT, "agent_books"))  # type: ignore[attr-defined]
    assert "domain https://books.example" in decision.reason  # type: ignore[attr-defined]
    assert "agent agent_books" in decision.reason  # type: ignore[attr-defined]


def test_an_axis_nobody_limited_is_refused_rather_than_unlimited() -> None:
    """No rows at all refuses every key, and a default row for only one axis refuses the other.

    Delete this and a missing configuration row admits sessions without limit."""
    none = open_one(limits=())
    domain_only = open_one(
        limits=(SessionLimit(axis=Axis.DOMAIN, limit=1, reason="one per origin"),)
    )

    assert not none.admitted  # type: ignore[attr-defined]
    assert len(none.over) == 3  # type: ignore[attr-defined]
    assert domain_only.over == ((Axis.AGENT, "agent_books"),)  # type: ignore[attr-defined]


def test_a_subjects_own_row_is_preferred_to_the_axis_default() -> None:
    """A portal with its own row of three admits a third session where the default of one
    would refuse the second.

    Delete this and `limit_for` can read the default first, so a measured ceiling is ignored."""
    own = SessionLimit(axis=Axis.DOMAIN, subject=APP, limit=3, reason="this portal allows three")
    limits = (*seed_session_limits(), own)

    assert limit_for(limits, (Axis.DOMAIN, APP)) == own
    assert limit_for(limits, (Axis.DOMAIN, LOGIN)) == seed_session_limits()[0]

    decision = open_one(
        a_target("books", (APP,)),
        limits=limits,
        counts=SessionCounts(held={(Axis.DOMAIN, APP): 2}),
    )

    assert decision.admitted  # type: ignore[attr-defined]


def test_the_global_budget_still_refuses_with_room_on_both_axes() -> None:
    """Admission is asked first and its refusal stands.

    Delete this and `may_open` can admit on the two axes alone, which is a second counter
    deciding instead of the one admission holds."""
    full = CapacityState(used={(Resource.BROWSER_SESSIONS, ""): global_budget()[0].limit})

    decision = open_one(state=full)

    assert not decision.admitted  # type: ignore[attr-defined]
    assert decision.over == ()  # type: ignore[attr-defined]


def test_a_halt_refuses_as_a_halt_and_asks_no_axis() -> None:
    """A halted system is stopped rather than full, so a full axis is not reported beside it.

    Delete this and an operator who pressed stop reads that a portal is busy."""
    busy = SessionCounts(held={(Axis.DOMAIN, APP): 1})

    decision = open_one(counts=busy, halted=True)

    assert not decision.admitted  # type: ignore[attr-defined]
    assert decision.admission.halted  # type: ignore[attr-defined]
    assert decision.over == ()  # type: ignore[attr-defined]


def test_a_session_naming_no_agent_is_refused() -> None:
    """Delete this and a blank agent id is one agent that every unnamed run shares."""
    with pytest.raises(SessionError, match="names no agent"):
        open_one(agent_id="  ")


def test_a_limit_of_zero_or_with_no_reason_is_refused() -> None:
    """Delete this and a website is switched off by editing a number to zero."""
    with pytest.raises(SessionError, match="minimum is 1"):
        SessionLimit(axis=Axis.DOMAIN, limit=0, reason="off")
    with pytest.raises(SessionError, match="says nothing about why"):
        SessionLimit(axis=Axis.AGENT, limit=1, reason=" ")


def test_the_default_limits_bind_below_the_global_browser_budget() -> None:
    """Each default is smaller than the seeded global budget, which is the property that makes
    it a limit at all: equal to the global budget, it could never refuse anything the global
    budget had not.

    Delete this and a default raised to two passes, and one portal or one agent can hold both
    of the machine's sessions again."""
    ceiling = global_budget()[0].limit
    seeded = {row.axis: row.limit for row in seed_session_limits()}

    assert seeded == {
        Axis.DOMAIN: DEFAULT_SESSIONS_PER_DOMAIN,
        Axis.AGENT: DEFAULT_SESSIONS_PER_AGENT,
    }
    assert all(limit < ceiling for limit in seeded.values())
