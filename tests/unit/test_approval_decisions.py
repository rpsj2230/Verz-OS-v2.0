"""Deciding an approval over HTTP: once, by an approver in reach, with one ledger entry, and every
refusal the answer an approval that does not exist gets.

Driven through the real application, as `tests/unit/test_approval_routes.py` drives the reads, with
the token machinery borrowed from `tests/unit/test_api_routes.py` for the reason that file gives.
The store is an in-memory `SuspensionStore` whose `holding` applies a write only when the block
ends without a raise, which is the one property of a transaction `decide_once` relies on. What a
real table does with a lock, a policy and a second writer is `tests/unit/test_suspension_store.py`.

**The suspensions are built the way `brain.gate.leash.suspend` builds them**, through a real
`Action` with its real digest and rendered artefact, and the ledger is a real `AuditChain`.

**The clock is the wall clock**, for the reason `tests/unit/test_approval_routes.py` gives: the
routes read `datetime.now(UTC)` through `Asking`, and whether an approval is open is a question
about the present.

Task ids: M35.3.1.1
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import approval_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app, suspension_store_for
from brain.approval_routes import (
    DecidableVerdict,
    DecisionAsked,
    RejectionReason,
)
from brain.audit.ledger import AuditAction, AuditChain
from brain.audit.record import ApprovalVerdict, AuditRecorder
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.errors import Absent
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.gate.leash import Action, ApprovalState, SuspendedAction, render_artefact
from brain.gate.suspension_store import StoredSuspensions
from brain.identity.bearer import TokenAuthority
from brain.session import make_app_engine, make_session_factory
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


def decision_path(ident: str) -> str:
    return f"{APPROVALS}/{ident}/decision"


def in_department(department: str) -> Scope:
    return Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),))


#: `u_narrow` may change a ticket's status in maintenance, `u_wide` in finance, and nobody else
#: holds anything an action requires.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_narrow": (
        Grant(capability=Capability(value=WRITE_STATUS), scope=in_department(MAINTENANCE)),
    ),
    "u_wide": (Grant(capability=Capability(value=WRITE_STATUS), scope=in_department(FINANCE)),),
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
        return EntitlementSet(principal_id=principal_id, grants=GRANTS.get(principal_id, ()))


def an_action(department: str) -> Action:
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
) -> SuspendedAction:
    """One suspension raised relative to the wall clock, built the way `suspend` builds one."""
    action = an_action(department)
    raised_at = datetime.now(UTC) - raised_ago
    decided = state is not ApprovalState.PENDING
    return SuspendedAction(
        id=ident,
        trace_id="trace_test",
        action=action,
        principal_id="u_asker",
        ent_hash="e" * 32,
        artefact=render_artefact(action),
        action_digest=action.digest(),
        raised_at=raised_at,
        expires_at=raised_at + window,
        state=state,
        decided_by="u_somebody" if decided else "",
        decided_at=raised_at + timedelta(minutes=1) if decided else None,
    )


# ------------------------------------------------------------------------ the stores


class MemorySource:
    """A `SuspensionSource` over a dict. Readable, and unable to keep a decision."""

    def __init__(self, rows: dict[str, SuspendedAction]) -> None:
        self.rows = rows

    async def open_suspensions(self) -> Sequence[SuspendedAction]:
        return list(self.rows.values())

    async def suspension(self, suspension_id: str) -> SuspendedAction | None:
        return self.rows.get(suspension_id)


class MemoryHeld:
    """A `HeldSuspensions` whose writes land only when the holding block ends cleanly."""

    def __init__(self, rows: dict[str, SuspendedAction], *, writes_land: bool) -> None:
        self.rows = rows
        self.writes: dict[str, SuspendedAction] = {}
        self.writes_land = writes_land
        self.locked: list[str] = []

    async def lock(self, suspension_id: str) -> SuspendedAction | None:
        self.locked.append(suspension_id)
        return self.rows.get(suspension_id)

    async def record(self, decided: SuspendedAction) -> bool:
        current = self.rows.get(decided.id)
        if (
            not self.writes_land
            or current is None
            or current.state is not ApprovalState.PENDING
            or current.action_digest != decided.action_digest
        ):
            return False
        self.writes[decided.id] = decided
        return True


class MemoryStore:
    """A `SuspensionStore` over a dict, a real `AuditChain`, and a record of who read it."""

    def __init__(self, held: Sequence[SuspendedAction] = (), *, writes_land: bool = True) -> None:
        self.rows: dict[str, SuspendedAction] = {one.id: one for one in held}
        self._ledger = AuditChain()
        self.writes_land = writes_land
        self.read_as: list[str] = []
        self.held_as: list[str] = []

    @property
    def ledger(self) -> AuditChain:
        return self._ledger

    def reading_as(self, reach: EntitlementSet, now: datetime) -> MemorySource:
        self.read_as.append(reach.principal_id)
        return MemorySource(self.rows)

    @asynccontextmanager
    async def holding(self, reach: EntitlementSet, now: datetime) -> AsyncIterator[MemoryHeld]:
        self.held_as.append(reach.principal_id)
        held = MemoryHeld(self.rows, writes_land=self.writes_land)
        yield held
        self.rows.update(held.writes)


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
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def client(store: MemoryStore) -> Iterator[TestClient]:
    """The real application with the store attached after the lifespan has run."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.suspensions = store
        yield c


def headers(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid)}"}


def post(c: TestClient, pid: str, ident: str, body: object) -> Response:
    response: Response = c.post(decision_path(ident), json=body, headers=headers(pid))
    return response


def approve(c: TestClient, pid: str, ident: str) -> Response:
    return post(c, pid, ident, {"verdict": "approved"})


def without_trace(response: Response) -> dict[str, object]:
    return {k: v for k, v in response.json().items() if k != "trace_id"}


# ---------------------------------------------------------------------- the decision


def test_an_approver_in_reach_approves_once_and_one_ledger_entry_records_it(
    client: TestClient, store: MemoryStore
) -> None:
    """The row moves to approved under the approver's name, the answer says what was decided,
    and one approval entry names the suspension, the verdict, the digest, the approver's reach
    and the trace the response carries.

    Delete this and every refusal below is satisfied by a route that decides nothing."""
    held = a_suspension("m_1")
    store.rows = {held.id: held}

    response = approve(client, "u_narrow", "m_1")

    assert response.status_code == 200, response.text
    assert response.json() == {"suspension_id": "m_1", "verdict": "approved"}
    stored = store.rows["m_1"]
    assert (stored.state, stored.decided_by) == (ApprovalState.APPROVED, "u_narrow")
    [entry] = store.ledger.entries
    assert entry.action is AuditAction.APPROVAL
    assert entry.subject == "leash:m_1"
    assert entry.actor_id == "u_narrow"
    assert entry.ent_hash == asyncio.run(Store().load("u_narrow", datetime.now(UTC))).ent_hash()
    assert entry.trace_id == response.headers["x-trace-id"]
    assert entry.details == {"verdict": "approved", "action_digest": held.action_digest}
    assert store.held_as == ["u_narrow"]


def test_a_rejection_moves_the_row_to_rejected_and_the_ledger_keeps_its_reason(
    client: TestClient, store: MemoryStore
) -> None:
    """Delete this and a rejection can be recorded as an approval, or lose its why."""
    store.rows = {"m_1": a_suspension("m_1")}

    response = post(
        client, "u_narrow", "m_1", {"verdict": "rejected", "reason_code": "wrong_target"}
    )

    assert response.status_code == 200, response.text
    assert store.rows["m_1"].state is ApprovalState.REJECTED
    [entry] = store.ledger.entries
    assert entry.details["verdict"] == "rejected"
    assert entry.details["reason_code"] == "wrong_target"


def test_deciding_out_of_reach_decided_lapsed_or_invented_is_one_404_and_writes_nothing(
    client: TestClient, store: MemoryStore
) -> None:
    """Every reason there is no card answers a decision exactly as an invented id does, moves no
    row and writes no entry, and the sibling proves the approver in reach is answered.

    Delete this and a POST loop enumerates which pending actions exist, one id at a time."""
    held = [
        a_suspension("f_1", department=FINANCE),
        a_suspension("decided", state=ApprovalState.APPROVED),
        a_suspension("lapsed", raised_ago=timedelta(hours=5), window=timedelta(hours=4)),
    ]
    store.rows = {one.id: one for one in held}
    before = dict(store.rows)

    missing = approve(client, "u_narrow", "nothing_here")
    refusals = [approve(client, "u_narrow", ident) for ident in ("f_1", "decided", "lapsed")]
    nobody = approve(client, "u_none", "f_1")

    assert missing.status_code == 404
    assert missing.json()["message"] == Absent.public_message
    for refused in (*refusals, nobody):
        assert refused.status_code == missing.status_code
        assert without_trace(refused) == without_trace(missing)
    assert store.rows == before
    assert store.ledger.entries == ()

    assert approve(client, "u_wide", "f_1").status_code == 200


def test_a_second_decision_on_one_approval_gets_the_answer_an_invented_id_gets(
    client: TestClient, store: MemoryStore
) -> None:
    """Approved once, then approved or rejected again, by the same approver or another in reach:
    the later attempts are the invented id's 404 and the ledger still holds one entry.

    Delete this and one card pressed twice on a slow phone is two approvals in the ledger."""
    store.rows = {"m_1": a_suspension("m_1")}

    first = approve(client, "u_narrow", "m_1")
    again = approve(client, "u_narrow", "m_1")
    rejected = post(
        client, "u_narrow", "m_1", {"verdict": "rejected", "reason_code": "no_longer_needed"}
    )
    missing = approve(client, "u_narrow", "nothing_here")

    assert first.status_code == 200
    for late in (again, rejected):
        assert late.status_code == 404
        assert without_trace(late) == without_trace(missing)
    assert len(store.ledger.entries) == 1
    assert store.rows["m_1"].state is ApprovalState.APPROVED


def test_a_decided_approval_leaves_the_queue_and_its_card_no_longer_opens(
    client: TestClient, store: MemoryStore
) -> None:
    """Delete this and a phone keeps offering a card that can only be refused."""
    store.rows = {"m_1": a_suspension("m_1"), "m_2": a_suspension("m_2")}

    assert approve(client, "u_narrow", "m_1").status_code == 200

    queue = client.get(APPROVALS, headers=headers("u_narrow")).json()
    assert [one["suspension_id"] for one in queue["items"]] == ["m_2"]
    assert client.get(f"{APPROVALS}/m_1", headers=headers("u_narrow")).status_code == 404
    assert client.get(f"{APPROVALS}/m_2", headers=headers("u_narrow")).status_code == 200


def test_a_decision_the_store_would_not_write_is_a_fault_and_the_row_is_not_moved(
    client: TestClient, store: MemoryStore
) -> None:
    """A held row whose write does not land raises inside the holding block, so nothing the
    block wrote is kept, and the caller gets a fault rather than a 200 for a decision that did
    not happen.

    Delete this and `decide_once` can ignore the store's answer and report success."""
    store.rows = {"m_1": a_suspension("m_1")}
    store.writes_land = False

    response = approve(client, "u_narrow", "m_1")

    assert response.status_code == 500
    assert store.rows["m_1"].state is ApprovalState.PENDING


def test_a_card_the_approver_reads_and_a_card_they_decide_are_read_at_their_own_reach(
    client: TestClient, store: MemoryStore
) -> None:
    """The queue, the single card and the decision each ask the store at the caller's reach,
    which is what gives row-level security something to narrow on.

    Delete this and a store can be read at a reach nobody asked with."""
    store.rows = {"m_1": a_suspension("m_1")}

    client.get(APPROVALS, headers=headers("u_narrow"))
    client.get(f"{APPROVALS}/m_1", headers=headers("u_wide"))
    approve(client, "u_narrow", "m_1")

    assert store.read_as == ["u_narrow", "u_wide"]
    assert store.held_as == ["u_narrow"]


# -------------------------------------------------------------------------- the body


def test_a_rejection_without_a_reason_and_an_approval_with_one_are_refused_before_the_store(
    client: TestClient, store: MemoryStore
) -> None:
    """Both shapes are refused with one status whether the id is real, in reach or invented, and
    no transaction is opened for either; a well-formed body is not refused.

    Delete this and whether a malformed decision is refused depends on the suspension it names."""
    store.rows = {"m_1": a_suspension("m_1"), "f_1": a_suspension("f_1", department=FINANCE)}
    malformed = (
        {"verdict": "rejected"},
        {"verdict": "approved", "reason_code": "wrong_target"},
        {"verdict": "rejected", "reason_code": "because I said so"},
        {"verdict": "taken_over"},
        {"verdict": "amended"},
    )

    answers = [
        post(client, "u_narrow", ident, body).status_code
        for body in malformed
        for ident in ("m_1", "f_1", "nothing_here")
    ]

    assert set(answers) == {422}
    assert store.held_as == []
    assert store.ledger.entries == ()
    assert approve(client, "u_narrow", "m_1").status_code == 200


def test_the_body_refuses_exactly_what_the_recorder_refuses() -> None:
    """For every verdict offered and every reason or none, the body accepts a decision exactly
    when `AuditRecorder.approval` would, so the early refusal is the recorder's rule and not a
    second one that has drifted.

    Delete this and the body can admit a rejection the ledger will refuse after the row is
    locked, or refuse one the ledger would have kept."""
    recorder = AuditRecorder(
        AuditChain(),
        actor_id="u_approver",
        ent_hash="e" * 32,
        trace_id="trace_test",
        clock=lambda: datetime.now(UTC),
    )
    offered = 0
    for verdict in DecidableVerdict:
        for reason in (None, *RejectionReason):
            try:
                DecisionAsked(verdict=verdict, reason_code=reason)
                body_accepts = True
            except ValueError:
                body_accepts = False
            try:
                recorder.approval(
                    suspension_id="sus_1",
                    verdict=ApprovalVerdict(verdict.value),
                    digest="d" * 64,
                    reason_code=reason.value if reason is not None else "",
                )
                recorder_accepts = True
            except ValueError:
                recorder_accepts = False
            assert body_accepts == recorder_accepts, (verdict, reason)
            offered += body_accepts
    assert offered == 1 + len(RejectionReason)


def test_only_approving_and_rejecting_are_offered_and_both_are_ledger_verdicts() -> None:
    """Delete this and taking over or amending can be offered with nothing behind either, which
    `TAKING_OVER_AND_AMENDING_WAIT_FOR_WHAT_THEY_HAND_OVER_TO` refuses."""
    offered = {one.value for one in DecidableVerdict}

    assert offered == {ApprovalVerdict.APPROVED.value, ApprovalVerdict.REJECTED.value}
    assert offered <= {one.value for one in ApprovalVerdict}


# ------------------------------------------------------------------------ the process


def test_a_process_that_cannot_keep_a_decision_refuses_every_decision_alike() -> None:
    """No store, a thing that is not one, and a source that can only be read all answer every
    caller and every id with one fault, and a store answers.

    Delete this and a process whose decisions have nowhere to go can accept one."""
    app: FastAPI = create_app(Settings(env="development"))
    held = a_suspension("m_1")
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        for attached in (None, object(), MemorySource({held.id: held})):
            app.state.suspensions = attached
            answers = [approve(c, "u_narrow", "m_1"), approve(c, "u_none", "nothing_here")]
            assert {one.status_code for one in answers} == {500}
            assert len({str(without_trace(one)) for one in answers}) == 1

        app.state.suspensions = MemoryStore([held])
        assert approve(c, "u_narrow", "m_1").status_code == 200


def test_a_store_is_built_only_with_a_database_and_a_ledger_and_the_lifespan_builds_none() -> None:
    """Delete this and a process can be given a store whose decisions are recorded in a ledger
    that is gone at the next restart."""
    engine = make_app_engine("postgresql://nobody@127.0.0.1:1/nothing")
    sessions = make_session_factory(engine)
    ledger = AuditChain()

    assert suspension_store_for(None, ledger) is None
    assert suspension_store_for(sessions, None) is None
    built = suspension_store_for(sessions, ledger)
    assert isinstance(built, StoredSuspensions)
    assert isinstance(built, approval_routes.SuspensionStore)

    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False):
        assert app.state.suspensions is None


def test_the_approvals_router_serves_two_reads_and_one_decision_through_decide() -> None:
    """The paths are the queue, the card and the card's decision, and the module moves a
    suspension only through `brain.console.approvals.decide`.

    Delete this and a second way of approving can be added beside the one that writes the
    ledger entry."""
    document = create_app(Settings(env="development")).openapi()["paths"]
    approval_paths = {
        path: set(ops) for path, ops in document.items() if path.startswith(APPROVALS)
    }

    assert approval_paths == {
        APPROVALS: {"get"},
        f"{APPROVALS}/{{suspension_id}}": {"get"},
        f"{APPROVALS}/{{suspension_id}}/decision": {"post"},
    }
    tree = ast.parse(inspect.getsource(approval_routes))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "decide" in called
    assert not called & {"approved_by", "rejected_by", "resume"}
