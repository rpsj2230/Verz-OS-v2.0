"""The verification job over the stored ledger, the published head, and who may run the job.

Two halves. `check_ledger` over a ledger in memory whose rows are real `AuditChain` entries stored
as the table's own row type, walked in chunks small enough that every property crosses a chunk
boundary. Then the three routes through the real application: the public head and the digest at a
position, and the console's verification run, whose refusals each have a permitted sibling.

Task ids: M24.1.2, M24.3.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import audit_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.audit.chain_check import (
    LedgerCheck,
    LedgerSequence,
    check_ledger,
    published_anchor,
    published_head,
)
from brain.audit.export import Anchor
from brain.audit.ledger import (
    GENESIS_HASH,
    AuditAction,
    AuditChain,
    AuditEntry,
    BreakReason,
    ChainBreak,
)
from brain.audit.reads import READ_LOG_CAPABILITY
from brain.audit.verify import (
    ANCHOR_MISSING_CAVEAT,
    ANCHORED_CAVEAT,
    UNANCHORED_CAVEAT,
    Completeness,
)
from brain.audit.view import CAPABILITY_BY_KIND
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.tables.audit import AuditEntryRow
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

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
BEGAN = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
AT = datetime(2019, 6, 1, 12, 0, tzinfo=UTC)
ENT = "0" * 32

VERIFY = f"{API_PREFIX}/audit/verification"


def stored(entry: AuditEntry) -> AuditEntryRow:
    return AuditEntryRow(
        seq=entry.seq,
        at=entry.at,
        actor_id=entry.actor_id,
        action=entry.action.value,
        subject=entry.subject,
        ent_hash=entry.ent_hash,
        trace_id=entry.trace_id,
        details=dict(entry.details),
        prev_hash=entry.prev_hash,
        entry_hash=entry.entry_hash,
    )


def rows(count: int) -> list[AuditEntryRow]:
    chain = AuditChain()
    for i in range(count):
        chain.append(
            action=AuditAction.GRANT,
            actor_id="u_admin",
            subject=f"principal:u_{i}",
            ent_hash=ENT,
            trace_id=f"trace{i}",
            at=BEGAN + timedelta(minutes=i),
            details={"capability": "read:client.name"},
        )
    return [stored(one) for one in chain.entries]


@dataclass
class Ledger:
    """`LedgerSequence` over rows in memory, in sequence order as the statement reads them."""

    rows: list[AuditEntryRow] = field(default_factory=list)

    async def after(self, seq: int | None, *, limit: int) -> Sequence[AuditEntryRow]:
        ordered = sorted(self.rows, key=lambda row: row.seq)
        return [row for row in ordered if seq is None or row.seq > seq][:limit]

    async def newest(self) -> AuditEntryRow | None:
        return max(self.rows, key=lambda row: row.seq) if self.rows else None

    async def at_seq(self, seq: int) -> AuditEntryRow | None:
        return next((row for row in self.rows if row.seq == seq), None)


def anchor_at(row: AuditEntryRow, head: str | None = None) -> Anchor:
    return published_anchor(seq=row.seq, head=head or row.entry_hash, recorded_at=AT)


def walk(ledger: Ledger, anchor: Anchor | None = None) -> LedgerCheck:
    """One walk in chunks of two, so every property below crosses a chunk boundary."""
    assert isinstance(ledger, LedgerSequence)
    return asyncio.run(check_ledger(ledger, at=AT, anchor=anchor, chunk=2))


def broken(checked: LedgerCheck) -> ChainBreak:
    assert checked.break_found is not None
    return checked.break_found


# ---------------------------------------------------------------------------- the walk


def test_an_untouched_ledger_walks_continuous_across_every_chunk() -> None:
    """Seven entries in chunks of two: every one walked, the head the newest digest, and the
    caveat that no anchor was checked. Delete this and each refusal below is satisfied by a walk
    that reports every ledger broken, or that stops after the first chunk."""
    ledger = Ledger(rows(7))
    checked = walk(ledger)
    assert (checked.continuous, checked.entries_walked) == (True, 7)
    assert (checked.first_seq, checked.last_seq) == (0, 6)
    assert checked.head == ledger.rows[-1].entry_hash
    assert checked.completeness is Completeness.UNANCHORED
    assert checked.caveats == (UNANCHORED_CAVEAT,)


def test_an_entry_edited_to_another_name_is_found_at_its_own_sequence_number() -> None:
    """Entry four's detail changed to a different field name, which still constructs: the walk
    stops at seq 4, in the third chunk, and says so. Delete this and a break in a later chunk can
    be reported at its index within the chunk, sending the reader to the wrong row."""
    ledger = Ledger(rows(7))
    ledger.rows[4].details = {"capability": "read:client.margin"}
    checked = walk(ledger)
    assert checked.continuous is False
    assert broken(checked).seq == 4
    assert broken(checked).index == 4
    assert broken(checked).reason is BreakReason.CONTENT_ALTERED


def test_a_row_carrying_a_value_is_a_break_and_is_never_skipped() -> None:
    """A detail holding prose does not construct. The audit screen skips such a row; the walk must
    not. Delete this and a hand-edited entry reads as a continuous ledger, because the walk steps
    over exactly the row that was edited. See A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_A_BREAK."""
    ledger = Ledger(rows(5))
    ledger.rows[3].details = {"capability": "Somebody wrote a sentence here"}
    checked = walk(ledger)
    assert checked.continuous is False
    assert broken(checked).seq == 3
    assert broken(checked).reason is BreakReason.CONTENT_ALTERED


def test_a_removed_middle_entry_and_a_removed_first_entry_are_each_a_break() -> None:
    """Deleting seq 3 breaks the sequence at 4; deleting seq 0 leaves a ledger starting at 1,
    which a window would call unmoored and this calls broken. Delete this and removing the oldest
    entry, the one a person covering an old grant would remove, verifies clean."""
    middle = Ledger([row for row in rows(6) if row.seq != 3])
    checked = walk(middle)
    assert checked.continuous is False
    assert broken(checked).seq == 4

    head_gone = Ledger([row for row in rows(6) if row.seq != 0])
    checked = walk(head_gone)
    assert checked.continuous is False
    assert broken(checked).reason is BreakReason.SEQUENCE_BROKEN
    assert broken(checked).seq == 1


def test_a_published_head_still_held_is_anchored() -> None:
    """The positive sibling of the two below. Delete this and they pass against a walk that calls
    every anchor missing."""
    ledger = Ledger(rows(7))
    checked = walk(ledger, anchor_at(ledger.rows[5]))
    assert checked.completeness is Completeness.ANCHORED
    assert ANCHORED_CAVEAT in checked.caveats


def test_entries_removed_after_the_last_published_head_are_reported() -> None:
    """**The property M24.3.3 is for.** Seven entries, the head published at seq 6, then the two
    newest removed: what remains walks perfectly continuous, and only the published head says the
    ledger was longer. Delete this and a truncated tail verifies as a complete ledger, which is
    the one tamper a hash chain cannot see."""
    full = rows(7)
    published = anchor_at(full[6])
    truncated = Ledger(full[:5])
    checked = walk(truncated, published)
    assert checked.continuous is True
    assert checked.completeness is Completeness.ANCHOR_MISSING
    assert ANCHOR_MISSING_CAVEAT in checked.caveats


def test_a_published_head_whose_entry_was_rewritten_is_reported() -> None:
    """Seq 5 is present with a different digest from the one published. Delete this and a
    rewritten tail, recomputed to verify, passes as long as its length did not change."""
    ledger = Ledger(rows(7))
    checked = walk(ledger, anchor_at(ledger.rows[5], head="a" * 64))
    assert checked.completeness is Completeness.ANCHOR_MISSING


def test_the_published_head_is_the_stored_newest_entry_and_genesis_when_empty() -> None:
    """Delete this and the head can be read from anything but the table, which is what the route
    did until 2026-09-21: it anchored an empty in-memory chain whatever the ledger held."""
    ledger = Ledger(rows(4))
    head = asyncio.run(published_head(ledger))
    assert (head.seq, head.head) == (3, ledger.rows[3].entry_hash)
    empty = asyncio.run(published_head(Ledger()))
    assert (empty.seq, empty.head, empty.is_empty) == (0, GENESIS_HASH, True)


# -------------------------------------------------------------------------- the routes

SCREEN_READ = screen("audit").read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
WHOLE_LEDGER: tuple[Capability, ...] = (*CAPABILITY_BY_KIND.values(), READ_LOG_CAPABILITY)


def grant(value: Capability) -> Grant:
    return Grant(capability=value, scope=Scope.unrestricted())


#: `u_admin` reads the whole ledger; `u_narrow` every audit kind but not the read log, which no
#: audit wildcard reaches; `u_wide` holds the whole ledger and not the screen.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (grant(SCREEN_READ), grant(CONFIGURATION), *(grant(c) for c in WHOLE_LEDGER)),
    "u_narrow": (
        grant(SCREEN_READ),
        grant(CONFIGURATION),
        *(grant(c) for c in CAPABILITY_BY_KIND.values()),
    ),
    "u_wide": tuple(grant(c) for c in WHOLE_LEDGER),
}


class Directory:
    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        for pid, sub in SUBJECTS.items():
            if issuer == ISSUER and sub == subject:
                return Principal(
                    id=pid, kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name=pid
                )
        return None


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS.get(principal_id, ()))


@pytest.fixture
def ledger() -> Ledger:
    return Ledger(rows(5))


@pytest.fixture
def app(ledger: Ledger) -> Iterator[FastAPI]:
    built = create_app(Settings(env="development"))
    built.include_router(audit_routes.router)
    yield built


@pytest.fixture
def client(app: FastAPI, ledger: Ledger) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        app.state.audit_sequence = ledger
        yield c


def verify(c: TestClient, pid: str, body: dict[str, object] | None = None) -> Response:
    token = token_for(pid, claims={"amr": ["otp"]})
    answer: Response = c.post(VERIFY, json=body or {}, headers={"authorization": f"Bearer {token}"})
    return answer


def test_the_public_head_is_the_stored_ledgers_newest_entry(
    client: TestClient, ledger: Ledger
) -> None:
    """Delete this and the anchor route can go back to publishing an empty chain's head, which
    no truncation ever contradicts."""
    answer = client.get("/api/audit/anchor")
    assert answer.status_code == 200
    body = answer.json()
    assert (body["seq"], body["head"]) == (4, ledger.rows[4].entry_hash)
    assert set(body) == {"chain", "head", "seq", "taken_at", "version"}


def test_the_digest_at_a_position_is_answered_and_an_absent_one_has_none(
    client: TestClient, ledger: Ledger
) -> None:
    """The workflow's coverage check reads this. An absent entry is a 200 with no digest, so a
    release without the route (a 404) is never mistaken for a ledger that lost the entry. Delete
    this and the workflow cannot tell the two apart."""
    held = client.get("/api/audit/anchor/2").json()
    assert held == {"seq": 2, "head": ledger.rows[2].entry_hash}
    gone = client.get("/api/audit/anchor/40")
    assert (gone.status_code, gone.json()) == (200, {"seq": 40, "head": None})


def test_a_process_with_no_ledger_publishes_no_head_rather_than_an_empty_one() -> None:
    """Delete this and a process that cannot see its database anchors "empty", which is exactly
    the false anchor the route published before it read the table."""
    built = create_app(Settings(env="development"))
    with TestClient(built, raise_server_exceptions=False) as c:
        built.state.db_sessions = None
        assert c.get("/api/audit/anchor").status_code == 503


def test_a_reader_of_the_whole_ledger_runs_the_job_and_is_told_what_it_did_not_prove(
    client: TestClient, ledger: Ledger
) -> None:
    """The positive case for both refusals below, with a published head checked. Delete this and
    they pass against a route that refuses everybody."""
    answer = verify(
        client,
        "u_admin",
        {
            "published": {
                "seq": 3,
                "head": ledger.rows[3].entry_hash,
                "taken_at": AT.isoformat(),
            }
        },
    )
    assert answer.status_code == 200
    body = answer.json()
    assert (body["continuous"], body["entries_walked"], body["completeness"]) == (
        True,
        5,
        "anchored",
    )
    assert body["caveats"] == [ANCHORED_CAVEAT]
    assert "verified" not in body


def test_a_truncated_ledger_is_reported_through_the_route(
    client: TestClient, ledger: Ledger
) -> None:
    """Delete this and the route can drop the published head on its way to the walk."""
    published = ledger.rows[4].entry_hash
    del ledger.rows[3:]
    body = verify(
        client, "u_admin", {"published": {"seq": 4, "head": published, "taken_at": AT.isoformat()}}
    ).json()
    assert (body["continuous"], body["completeness"]) == (True, "anchor_missing")


def test_a_reader_the_screen_does_not_open_for_is_refused_and_a_narrow_reader_is_not(
    client: TestClient,
) -> None:
    """The whole ledger without the screen is not the screen, and nothing at all is nothing: both
    are told the screen's one sentence before the ledger is read. A reader of every audit kind but
    the read log is not the whole ledger and runs the job anyway, because the report says nothing
    the public head does not. Delete this and the job can be closed to every first administrator,
    none of whom reads the whole ledger, or opened to somebody the screen refuses."""
    for pid in ("u_wide", "u_none"):
        answer = verify(client, pid)
        assert answer.status_code == 404, pid
        assert "entries" not in answer.text
    narrow = verify(client, "u_narrow")
    assert narrow.status_code == 200
    assert narrow.json()["continuous"] is True
