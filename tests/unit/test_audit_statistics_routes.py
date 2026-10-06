"""The Audit screen's refusal and redaction statistics over HTTP, in the reader's own view.

Driven through the real application over a ledger in memory whose rows are real `AuditChain`
entries, as `tests/unit/test_audit_routes.py` drives the ledger, with the window's assessed patterns
built by the digest's own `patterns_from`; then once against a real PostgreSQL, where
`gate.record_denial` writes the entries and the digest's grouped statement assesses them. The
database half skips without `DATABASE_URL` or pgvector, and CI has both.

The readers, by the people the token machinery knows. `u_prefix` and `u_admin` read the whole
ledger and hold the refused capability company-wide, so `denial_alerts.reach` tells them every
shape. `u_narrow` reads the whole ledger and does not hold it. `u_admin_only` reads only entries
about people. `u_elsewhere` holds everything but the screen; `u_none` holds nothing.

**Every refusal has a sibling proving the permitted case is answered.**

Task ids: M33.4.1.3
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import audit_statistics_routes as routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.audit.ledger import AuditAction, AuditChain, AuditEntry
from brain.audit_routes import READ_CEILING
from brain.audit_statistics_routes import (
    STATISTICS_PATH,
    THE_CEILING_IS_A_CONSTANT_AND_NOT_A_MEASUREMENT,
    AuditStatisticsView,
    RefusalShapeView,
)
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.ops.denial_alerts import ALERT_TEXT, DenialPattern
from brain.ops.denial_digest_run import patterns_from
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.ops.limits import DenialShape
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)
from tests.unit.test_audit_routes import Directory, Ledger, stored

STATISTICS = f"{API_PREFIX}{STATISTICS_PATH}"
AUDIT = f"{API_PREFIX}/audit"

#: Far outside any plausible wall clock, for CLAUDE.md's reason: the window is asked for by date.
BEGAN = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
WINDOW = {"since": "2019-03-04T00:00:00Z", "until": "2019-03-05T00:00:00Z"}
ENT = "0" * 32

#: The capability every denial below was refused.
REFUSED = "read:client.name"


def grant(value: Capability | str) -> Grant:
    capability = value if isinstance(value, Capability) else Capability(value=value)
    return Grant(capability=capability, scope=Scope.unrestricted())


SCREEN = (grant(screen("audit").read.requires), grant(plane_capability(Plane.CONFIGURATION)))

GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_prefix": (*SCREEN, grant("read:audit.*"), grant(REFUSED)),
    "u_admin": (*SCREEN, grant("read:audit.*"), grant(REFUSED)),
    "u_narrow": (*SCREEN, grant("read:audit.*")),
    "u_admin_only": (*SCREEN, grant("read:audit.principal"), grant(REFUSED)),
    "u_elsewhere": (grant("read:audit.*"), grant(REFUSED)),
    "u_none": (),
}


def denied(person: str, thing: str) -> tuple[AuditAction, str, str, Mapping[str, object]]:
    """A `deny` entry as `gate.record_denial` writes one: the person refused is the actor."""
    return (AuditAction.DENY, person, thing, {"capability": REFUSED, "reason": "no_grant"})


def redacted(actor: str, subject: str) -> tuple[AuditAction, str, str, Mapping[str, object]]:
    """A grant whose details the ledger stored redacted."""
    return (AuditAction.GRANT, actor, subject, {"capability": "<redacted>", "scope": "<redacted>"})


#: Oldest first. Two denials of `u_1` and one of `u_wide` are other people's; one of `u_admin` is
#: `u_admin`'s own. Of the redacted entries, one is about `u_2` by `u_narrow`, one is about
#: `u_admin` by `u_narrow`, and one is `u_admin`'s own request.
PLAN: Sequence[tuple[AuditAction, str, str, Mapping[str, object]]] = (
    denied("u_1", "entity:client_1"),
    denied("u_1", "entity:client_2"),
    denied("u_wide", "entity:client_3"),
    denied("u_admin", "entity:client_4"),
    redacted("u_narrow", "principal:u_2"),
    redacted("u_narrow", "principal:u_admin"),
    redacted("u_admin", "entity:client_9"),
)

#: The window's runs as the digest assesses them: `u_1` and `u_admin` reached for many things,
#: `u_wide` for one, again and again.
PATTERNS: tuple[DenialPattern, ...] = patterns_from(
    [("u_1", REFUSED, 9, 6), ("u_wide", REFUSED, 9, 1), ("u_admin", REFUSED, 9, 6)]
)


def chain_of(
    plan: Sequence[tuple[AuditAction, str, str, Mapping[str, object]]],
) -> list[AuditEntry]:
    chain = AuditChain()
    for i, (action, actor, subject, details) in enumerate(plan):
        chain.append(
            action=action,
            actor_id=actor,
            subject=subject,
            ent_hash=ENT,
            trace_id=f"trace{i}",
            at=BEGAN + timedelta(minutes=i),
            details=details,
        )
    return list(chain.entries)


@dataclass
class Patterns:
    """A `DenialPatterns` answering fixed patterns, and every window it was asked about."""

    found: tuple[DenialPattern, ...] = PATTERNS
    asked: list[tuple[datetime, datetime]] = field(default_factory=list)

    async def between(self, since: datetime, until: datetime) -> tuple[DenialPattern, ...]:
        self.asked.append((since, until))
        return self.found


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


@contextmanager
def serving(ledger: Ledger, patterns: Patterns) -> Iterator[TestClient]:
    from brain import audit_routes

    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(audit_routes.router)
    app.include_router(routes.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = wiring()
        app.state.audit_ledger = ledger
        app.state.denial_patterns = patterns
        yield client


@pytest.fixture
def ledger() -> Ledger:
    return Ledger(rows=[stored(one) for one in chain_of(PLAN)])


@pytest.fixture
def patterns() -> Patterns:
    return Patterns()


@pytest.fixture
def client(ledger: Ledger, patterns: Patterns) -> Iterator[TestClient]:
    with serving(ledger, patterns) as served:
        yield served


def get(c: TestClient, pid: str, path: str = STATISTICS, **params: str) -> Response:
    token = token_for(pid, claims={"amr": ["otp"]})
    response: Response = c.get(path, params=params, headers={"authorization": f"Bearer {token}"})
    return response


def statistics_of(
    c: TestClient, pid: str, params: Mapping[str, str] = WINDOW
) -> AuditStatisticsView:
    response = get(c, pid, **params)
    assert response.status_code == 200, response.text
    return AuditStatisticsView.model_validate(response.json())


def by_shape(body: AuditStatisticsView) -> dict[str, int]:
    return {one.shape: one.occurrences for one in body.refusals}


# ------------------------------------------------------------------------------- the counts


def test_an_auditor_is_told_refusals_by_shape_and_redacted_entries_over_other_peoples_entries(
    client: TestClient, patterns: Patterns
) -> None:
    """The positive case for every refusal below. `u_prefix` reads the whole ledger and is told
    every shape: three enumeration refusals and one access-needed, each under `denial_alerts`' own
    sentence, and three entries that carried a redaction. The patterns were asked about the window
    the reader asked about. Delete this and each refusal is satisfied by a route that counts
    nothing."""
    body = statistics_of(client, "u_prefix")

    assert by_shape(body) == {"access_needed": 1, "enumeration": 3}
    assert all(one.reads_as == ALERT_TEXT[DenialShape(one.shape)] for one in body.refusals)
    assert body.redacted_entries == 3
    assert patterns.asked == [(datetime(2019, 3, 4, tzinfo=UTC), datetime(2019, 3, 5, tzinfo=UTC))]


def test_an_auditors_own_refusals_and_the_redactions_on_their_own_entries_are_never_counted(
    client: TestClient,
) -> None:
    """**The hidden-count rule, about the one person it must never be about.** `u_admin` reads the
    same ledger with the same grants as `u_prefix` and is counted none of their own denials, none
    of the redactions on their own request and none of those on the entry about them, because a
    count of those tells them how much was kept from them. `u_prefix`, the sibling, is counted all
    of them, because to `u_prefix` they are other people's. Delete this and the statistics tell an
    auditor how often they were refused and how much of their own record was withheld."""
    mine = statistics_of(client, "u_admin")
    theirs = statistics_of(client, "u_prefix")

    assert by_shape(mine) == {"access_needed": 1, "enumeration": 2}
    assert mine.redacted_entries == 1
    assert by_shape(theirs) == {"access_needed": 1, "enumeration": 3}
    assert theirs.redacted_entries == 3


def test_a_reader_the_alert_would_not_reach_is_told_no_shape_and_still_their_redactions(
    client: TestClient,
) -> None:
    """`u_narrow` reads every denial and does not hold the refused capability, so
    `denial_alerts.reach` tells them no shape and no refusal is counted, while the redaction count
    over other people's entries is still theirs: one, since two of the three redacted entries are
    `u_narrow`'s own requests. Delete this and a shape assessed over denials the reader cannot see
    reaches somebody its alert never would."""
    body = statistics_of(client, "u_narrow")

    assert body.refusals == []
    assert body.redacted_entries == 1


def test_an_entry_the_reader_may_not_see_is_never_counted(client: TestClient) -> None:
    """`u_admin_only` reads entries about people and nothing else, and holds the refused capability.
    Every denial is about an entity, so none is counted although every shape would be told, and the
    two redacted entries about people are. Delete this and the statistics count what the ledger
    holds rather than what the reader may read."""
    body = statistics_of(client, "u_admin_only")

    assert body.refusals == []
    assert body.redacted_entries == 2


def test_a_reader_without_the_audit_screen_is_refused_before_the_ledger_is_read(
    client: TestClient, ledger: Ledger, patterns: Patterns
) -> None:
    """The one refusal, `brain.audit_routes`' own, identical to the ledger's and between a reader
    with no grant and one holding every audit grant without the screen, with no window read and no
    pattern asked for. Delete this and the statistics are a way to count the ledger without the
    screen's grant."""
    answers = []
    for pid in ("u_none", "u_elsewhere"):
        for path in (STATISTICS, AUDIT):
            response = get(client, pid, path)
            assert response.status_code == 404, response.text
            body = dict(response.json())
            body["trace_id"] = "<per request>"
            answers.append(body)

    assert all(one == answers[0] for one in answers)
    assert ledger.calls == []
    assert patterns.asked == []


def test_the_answer_names_no_capability_field_or_person_and_carries_no_total(
    client: TestClient,
) -> None:
    """Read off the models and off the body: a shape, its sentence and a count, and one number of
    redacted entries, and nothing the refused capability, a redacted field or a person could be
    written into. Delete this and a breakdown by capability or by field can be added beside the
    counts without anybody deciding it."""
    response = get(client, "u_prefix", **WINDOW)
    text = response.text

    for named in (REFUSED, "client.name", "scope", "u_1", "u_wide", "client_1"):
        assert named not in text
    assert set(RefusalShapeView.model_fields) == {"shape", "reads_as", "occurrences"}
    assert set(AuditStatisticsView.model_fields) == {
        "since",
        "until",
        "refusals",
        "redacted_entries",
        "read_at_most",
    }
    assert set(AuditStatisticsView.model_fields).isdisjoint(NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT)


def test_the_window_is_the_last_seven_days_unless_asked_and_a_malformed_one_is_a_422(
    client: TestClient, patterns: Patterns
) -> None:
    """Unasked, the window ends now and starts seven days earlier, the Audit screen's opening
    period, so the 2019 entries are not counted. A naive instant and an inverted range are the 422
    a malformed parameter is. Delete this and the statistics count the whole ledger by default, or
    an unreadable window is answered as an empty one."""
    body = statistics_of(client, "u_prefix", params={})

    assert body.until - body.since == timedelta(days=7)
    assert (body.refusals, body.redacted_entries) == ([], 0)
    assert patterns.asked == [(body.since, body.until)]
    naive = get(client, "u_prefix", since="2019-03-04T00:00:00", until="2019-03-05T00:00:00")
    inverted = get(client, "u_prefix", since=WINDOW["until"], until=WINDOW["since"])
    assert (naive.status_code, inverted.status_code) == (422, 422)


def test_the_window_is_read_to_its_ceiling_newest_first_and_the_ceiling_is_sent_as_a_constant(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """See `THE_CEILING_IS_A_CONSTANT_AND_NOT_A_MEASUREMENT`. With a load of one row at a time and
    a ceiling of three, only the three newest entries are counted, which are the three redacted
    ones; and the answer carries the ceiling and nothing that says whether it was reached. Unpatched
    it carries `READ_CEILING` to every reader alike. Delete this and the load can read without
    a bound, or the answer can grow a flag that counts the ledger."""
    unbounded = [statistics_of(client, pid) for pid in ("u_prefix", "u_narrow")]
    assert {one.read_at_most for one in unbounded} == {READ_CEILING}

    monkeypatch.setattr(routes, "LOAD_CHUNK", 1)
    monkeypatch.setattr(routes, "READ_CEILING", 3)
    bounded = statistics_of(client, "u_prefix")

    assert (bounded.refusals, bounded.redacted_entries, bounded.read_at_most) == ([], 3, 3)
    assert "boolean" not in THE_CEILING_IS_A_CONSTANT_AND_NOT_A_MEASUREMENT
    assert "nothing on the answer varies" in THE_CEILING_IS_A_CONSTANT_AND_NOT_A_MEASUREMENT


def test_every_page_of_the_view_is_counted_for_the_redactions(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """The redactions are counted over every page of the reader's view, not its first. With a page
    of one row the three redacted entries are still all counted. Delete this and the count stops
    at the first page, which on a busy ledger reads as a quiet week."""
    monkeypatch.setattr(routes, "MAX_PAGE_SIZE", 1)
    body = statistics_of(client, "u_prefix")

    assert body.redacted_entries == 3


# ----------------------------------------------------------------- against PostgreSQL


@pytest.fixture(scope="module")
def recorded() -> Iterator[str]:
    """Every migration to head, and denials written by `gate.record_denial` itself: nine by `u_1`
    across six things, and nine by `u_admin` across six things, both refused `REFUSED`."""
    import psycopg

    from tests.unit.test_decision_entries import at_head

    with at_head("brain_test_audit_statistics_routes") as url:
        for person in ("u_1", "u_admin"):
            with psycopg.connect(url) as conn, conn.transaction():
                conn.execute("SELECT set_config('brain.actor_id', %s, true)", (person,))
                conn.execute("SELECT set_config('brain.trace_id', 'trace-statistics', true)")
                for n in range(9):
                    conn.execute(
                        "SELECT gate.record_denial(%s, %s, 'no_grant')",
                        (f"entity:e{n % 6}", REFUSED),
                    )
        yield url


def test_against_the_database_the_digest_assesses_the_window_and_the_reader_is_not_counted(
    recorded: str,
) -> None:
    """The whole read over a real ledger: the window statement loads what `gate.record_denial`
    wrote, the digest's grouped statement assesses both runs as enumeration, and `u_admin`, who
    made nine of the eighteen denials, is counted only `u_1`'s nine while `u_prefix` is counted all
    eighteen. Delete this and the patterns are proved only over a fake that hands back what the
    test chose."""
    from brain.session import make_session_factory
    from tests.unit.test_automation_owner_store import app_engine

    engine = app_engine(recorded)
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(routes.router)
    with TestClient(app, raise_server_exceptions=False) as served:
        app.state.gate = wiring()
        app.state.db_sessions = make_session_factory(engine)
        mine = get(served, "u_admin")
        theirs = get(served, "u_prefix")

    assert mine.status_code == 200, mine.text
    assert by_shape(AuditStatisticsView.model_validate(mine.json())) == {"enumeration": 9}
    assert by_shape(AuditStatisticsView.model_validate(theirs.json())) == {"enumeration": 18}
