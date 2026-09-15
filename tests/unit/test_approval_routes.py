"""The approvals queue and one approval's card over HTTP: who is offered what, who is refused,
and that every refusal is one answer.

Driven through the real application. The token machinery and the key source are imported from
`tests/unit/test_api_routes.py`, for the reason `tests/unit/test_agent_routes.py` gives about
the same borrowing. The grants are this file's own, because what is under test is a reach over
an action's own row, and that file's people hold nothing an action requires.

**The suspensions are built the way `brain.gate.leash.suspend` builds them**, through a real
`Action` with its real digest and its real rendered artefact, as `tests/unit/test_approvals.py`
does. A test that assembled its own would be a test of a shape the gate never writes.

**The clock is the wall clock, and that is the one fixture here allowed to be.** The routes
read `datetime.now(UTC)` through `Asking`, and whether an approval is open is a question about
the present. So every suspension is raised relative to now rather than pinned to a date, which
is the case CLAUDE.md excepts from its rule about fixtures that are clocks: what is tested here
is itself about the present.

**Every refusal is compared body to body with the case it must be indistinguishable from**, and
has a sibling proving the permitted case is answered.

Task ids: M35.3.1.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.approval_routes import (
    MAX_QUEUE_CARDS,
    ApprovalCardView,
    ApprovalQueue,
    queue,
)
from brain.console.approvals import CALL_SHAPED, Card
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.errors import Absent
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.gate.leash import Action, ApprovalState, SuspendedAction, render_artefact
from brain.identity.bearer import TokenAuthority
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    SUBJECTS,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

APPROVALS = f"{API_PREFIX}/approvals"
WRITE_STATUS = "write:ticket.status"
MAINTENANCE = "maintenance"
FINANCE = "finance"


def in_department(department: str) -> Scope:
    return Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),))


#: What each signed-in person holds. `u_narrow` may change a ticket's status in maintenance,
#: `u_wide` in finance, and `u_none` holds nothing any action requires, which is the person
#: every queue must be empty for without saying why.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_narrow": (
        Grant(capability=Capability(value=WRITE_STATUS), scope=in_department(MAINTENANCE)),
    ),
    "u_wide": (Grant(capability=Capability(value=WRITE_STATUS), scope=in_department(FINANCE)),),
    "u_prefix": (),
    "u_none": (),
    "u_admin": (),
    "u_elsewhere": (),
}


class Directory:
    """A `PrincipalDirectory` over the subjects `test_api_routes` mints tokens for."""

    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        for pid, sub in SUBJECTS.items():
            if issuer == ISSUER and sub == subject:
                return Principal(
                    id=pid,
                    kind=PrincipalKind.HUMAN,
                    employment=Employment.STAFF,
                    display_name=f"Person {pid}",
                )
        return None


class Store:
    """A `brain.gate.resolve.EntitlementStore` over `GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


# ----------------------------------------------------------------------- suspensions


def an_action(department: str) -> Action:
    """One real action on a ticket in one department, so the digest and artefact are the gate's."""
    return Action(
        agent_id="agent_test",
        tool=ToolDefinition(
            name="ticket.update_status",
            description="a tool a test built so that a suspension has something real behind it",
            entity="ticket",
            required_capability=WRITE_STATUS,
            side_effect=SideEffect.WRITE,
        ),
        target="ticket",
        touched_fields=("status",),
        row={"department": department},
        args={"status": "closed"},
    )


def a_suspension(
    ident: str,
    *,
    department: str = MAINTENANCE,
    raised_ago: timedelta = timedelta(hours=1),
    window: timedelta = timedelta(hours=4),
    state: ApprovalState = ApprovalState.PENDING,
    artefact: str | None = None,
) -> SuspendedAction:
    """One suspension raised relative to the wall clock, built the way `suspend` builds one."""
    action = an_action(department)
    raised_at = datetime.now(UTC) - raised_ago
    return SuspendedAction(
        id=ident,
        trace_id="trace_test",
        action=action,
        principal_id="u_asker",
        ent_hash="e" * 32,
        artefact=render_artefact(action) if artefact is None else artefact,
        action_digest=action.digest(),
        raised_at=raised_at,
        expires_at=raised_at + window,
        state=state,
    )


class MemorySource:
    """A `SuspensionSource` over a list, recording which ids it was asked for."""

    def __init__(self, held: Sequence[SuspendedAction] = ()) -> None:
        self.held: list[SuspendedAction] = list(held)
        self.asked: list[str] = []

    async def open_suspensions(self) -> Sequence[SuspendedAction]:
        return list(self.held)

    async def suspension(self, suspension_id: str) -> SuspendedAction | None:
        self.asked.append(suspension_id)
        return next((one for one in self.held if one.id == suspension_id), None)


def _wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


@pytest.fixture
def source() -> MemorySource:
    """A fresh source per test, so one test's suspensions are never another's evidence."""
    return MemorySource()


@pytest.fixture
def client(source: MemorySource) -> Iterator[TestClient]:
    """The real application, its router registration included, with the source attached."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.suspensions = source
        yield c


def get(c: TestClient, pid: str, path: str) -> Response:
    response: Response = c.get(path, headers={"authorization": f"Bearer {token_for(pid)}"})
    return response


def queued(c: TestClient, pid: str) -> list[str]:
    response = get(c, pid, APPROVALS)
    assert response.status_code == 200, response.text
    return [one["suspension_id"] for one in response.json()["items"]]


def without_trace(response: Response) -> dict[str, object]:
    return {k: v for k, v in response.json().items() if k != "trace_id"}


# ------------------------------------------------------------------------- the queue


def test_the_queue_is_the_approvals_the_callers_reach_covers(
    client: TestClient, source: MemorySource
) -> None:
    """Each approver is offered the approvals inside their own reach and nobody else's.

    Delete this and every refusal below is satisfied by a queue that is always empty."""
    source.held = [
        a_suspension("m_1", department=MAINTENANCE),
        a_suspension("f_1", department=FINANCE),
        a_suspension("m_2", department=MAINTENANCE, window=timedelta(hours=5)),
    ]

    assert queued(client, "u_narrow") == ["m_1", "m_2"]
    assert queued(client, "u_wide") == ["f_1"]


def test_an_approval_outside_the_callers_reach_is_absent_from_the_queue_rather_than_marked(
    client: TestClient, source: MemorySource
) -> None:
    """A person offered nothing gets exactly the body a person gets from an empty store.

    Delete this and a queue can list what it withheld, greyed out or counted, and a reader
    learns what is pending in departments they cannot see."""
    empty = get(client, "u_narrow", APPROVALS).json()
    source.held = [a_suspension("m_1"), a_suspension("f_1", department=FINANCE)]

    assert get(client, "u_none", APPROVALS).json() == empty
    assert queued(client, "u_narrow") == ["m_1"]


def test_a_decided_or_lapsed_approval_is_absent_from_the_queue_and_an_open_one_is_listed(
    client: TestClient, source: MemorySource
) -> None:
    """Only what may still be decided is offered.

    Delete this and a phone shows an approval that was already approved elsewhere, or that
    lapsed an hour ago, beside a button that could only be refused."""
    source.held = [
        a_suspension("open"),
        a_suspension("approved", state=ApprovalState.APPROVED),
        a_suspension("rejected", state=ApprovalState.REJECTED),
        a_suspension("lapsed", raised_ago=timedelta(hours=5), window=timedelta(hours=4)),
    ]

    assert queued(client, "u_narrow") == ["open"]


def test_no_queue_answer_carries_a_count_of_anything(
    client: TestClient, source: MemorySource
) -> None:
    """The queue has its items, a null cursor, a null total and a truncation flag, and a card
    has no field under a name a hidden count arrives under.

    Delete this and "3 of 47 approvals" is one serialiser change away."""
    source.held = [a_suspension("m_1"), a_suspension("f_1", department=FINANCE)]
    body = get(client, "u_narrow", APPROVALS).json()

    assert body["total"] is None
    assert body["next_cursor"] is None
    assert set(body) == {"items", "next_cursor", "total", "truncated"}
    assert set(body["items"][0]) == set(ApprovalCardView.model_fields)
    assert not set(ApprovalCardView.model_fields) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
    assert set(ApprovalQueue.model_fields) - {"total"} == {"items", "next_cursor", "truncated"}


def test_the_queue_is_bounded_after_the_reach_filter_and_says_only_that_there_is_more() -> None:
    """Suspensions outside the reach ahead of the ones inside it do not use up the queue, and a
    queue over the bound says it is truncated without saying by how much.

    Delete this and the bound can move in front of the filter, where a short queue says that
    approvals were withheld."""
    reach = asyncio.run(Store().load("u_narrow", datetime.now(UTC)))
    now = datetime.now(UTC)
    hidden = [a_suspension(f"f_{n:04}", department=FINANCE) for n in range(MAX_QUEUE_CARDS)]
    visible = [a_suspension(f"m_{n:04}") for n in range(MAX_QUEUE_CARDS)]

    exactly = queue([*hidden, *visible], reach, now)
    assert [one.suspension_id for one in exactly.items] == [one.id for one in visible]
    assert exactly.truncated is False

    over = queue([*hidden, *visible, a_suspension("m_9999")], reach, now)
    assert len(over.items) == MAX_QUEUE_CARDS
    assert over.truncated is True
    assert over.total is None


def test_the_queue_lapses_soonest_first_whatever_order_the_store_holds() -> None:
    """Ordered by when an approval lapses and then by its id, never by the store's order.

    Delete this and a phone's first card is whatever the store returned first, and the one
    about to lapse is below the fold."""
    reach = asyncio.run(Store().load("u_narrow", datetime.now(UTC)))
    later = a_suspension("a_later", window=timedelta(hours=6))
    soon_b = a_suspension("b_soon", window=timedelta(hours=2))
    soon_a = soon_b.model_copy(update={"id": "a_soon"})

    shown = queue([later, soon_b, soon_a], reach, datetime.now(UTC))

    assert [one.suspension_id for one in shown.items] == ["a_soon", "b_soon", "a_later"]


def test_a_suspension_that_does_not_make_a_card_is_absent_from_every_queue_and_takes_nothing_down(
    client: TestClient, source: MemorySource
) -> None:
    """An artefact of whitespace passes the suspension's length bound and is refused by `Card`.
    It is absent, and the approval beside it is still offered.

    Delete this and one bad row is a 500 for every approver in its department."""
    source.held = [a_suspension("blank", artefact="   \n  "), a_suspension("m_1")]

    assert queued(client, "u_narrow") == ["m_1"]


# ----------------------------------------------------------------------- one approval


def test_an_approval_in_reach_opens_as_its_card_with_the_artefact_as_it_was_rendered(
    client: TestClient, source: MemorySource
) -> None:
    """The card is the suspension's own stored artefact, whose reach it runs under, and when it
    was raised and lapses.

    Delete this and every 404 below is satisfied by a route that refuses everybody."""
    held = a_suspension("m_1")
    source.held = [held]

    response = get(client, "u_narrow", f"{APPROVALS}/m_1")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["suspension_id"] == held.id
    assert body["artefact"] == held.artefact
    assert body["runs_as"] == held.principal_id
    assert datetime.fromisoformat(body["raised_at"]) == held.raised_at
    assert datetime.fromisoformat(body["expires_at"]) == held.expires_at
    assert source.asked == ["m_1"]


def test_an_approval_the_caller_may_not_decide_and_one_that_is_not_there_are_one_404_with_one_body(
    client: TestClient, source: MemorySource
) -> None:
    """Out of reach, already decided, lapsed, without a card, and an id nothing holds all
    answer identically, and the sibling line proves the approver is answered.

    Delete this and the address bar enumerates the company's pending actions one id at a time."""
    source.held = [
        a_suspension("f_1", department=FINANCE),
        a_suspension("decided", state=ApprovalState.APPROVED),
        a_suspension("lapsed", raised_ago=timedelta(hours=5), window=timedelta(hours=4)),
        a_suspension("blank", artefact="   "),
    ]

    missing = get(client, "u_narrow", f"{APPROVALS}/nothing_here")
    refusals = [
        get(client, "u_narrow", f"{APPROVALS}/{ident}")
        for ident in ("f_1", "decided", "lapsed", "blank")
    ]

    assert missing.status_code == 404
    assert missing.json()["message"] == Absent.public_message
    for refused in refusals:
        assert refused.status_code == missing.status_code
        assert without_trace(refused) == without_trace(missing)

    assert get(client, "u_wide", f"{APPROVALS}/f_1").status_code == 200


def test_a_card_on_the_wire_is_card_field_for_field_and_no_field_is_call_shaped() -> None:
    """The wire shape is `Card` field for field, and no name on it is call shaped.

    Compared against `Card`'s own dataclass fields, which `card_gaps` already holds to the
    rule, rather than against a list written here.

    Delete this and a serialiser can add the arguments `Card` was built to keep off the screen."""
    card_fields = list(Card.__dataclass_fields__)

    assert list(ApprovalCardView.model_fields) == card_fields
    assert not set(ApprovalCardView.model_fields) & CALL_SHAPED


# ------------------------------------------------------------------------ the process


def test_a_process_with_no_suspension_store_answers_every_caller_and_every_id_alike() -> None:
    """No store, and a store that is not a `SuspensionSource`, are one fault for everybody.

    Delete this and a process with no store can answer an empty queue, which is a claim that
    nothing is waiting on this person made with no evidence at all."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        for attached in (None, object()):
            app.state.suspensions = attached
            answers = [
                get(c, "u_narrow", APPROVALS),
                get(c, "u_none", APPROVALS),
                get(c, "u_narrow", f"{APPROVALS}/m_1"),
                get(c, "u_none", f"{APPROVALS}/nothing_here"),
            ]
            assert {one.status_code for one in answers} == {500}
            assert len({str(without_trace(one)) for one in answers}) == 1

        app.state.suspensions = MemorySource()
        assert get(c, "u_narrow", APPROVALS).status_code == 200
