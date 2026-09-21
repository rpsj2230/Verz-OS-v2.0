"""The audit ledger over HTTP: what a reader is shown, what a filter may offer, and where a page
stops, with nothing anywhere counting what was withheld.

Driven through the real application with the token machinery borrowed from
`tests/unit/test_api_routes.py`, over a ledger in memory whose rows are real `AuditChain` entries
stored as the table's own row type. The ledger applies a window's filters, position and direction
as `brain.audit_routes.window` asks the database to, and the statement itself is held to that
shape by reading the SQL it compiles to. The decision about each entry is never the ledger's: it
is `brain.audit.view.AuditView`'s, inside the route.

**Every refusal has a sibling proving the permitted case is answered**, which is CLAUDE.md's rule
about a guard tested only by its refusals.

Task ids: M27.7.13
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from brain import audit_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.audit.ledger import AuditAction, AuditChain, AuditEntry
from brain.audit.view import MAX_PAGE_SIZE, AuditFilter
from brain.audit_routes import entry_from, window
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
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

AUDIT = f"{API_PREFIX}/audit"
HISTORY = f"{API_PREFIX}/audit/history"

#: A PostgreSQL dialect to compile statements against, from an engine that never connects.
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock:
#: nothing here is about the present, and the view is asked at the request's own instant.
BEGAN = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
ENT = "0" * 32

#: Improbable on purpose: if this appears in a body, a row carrying a value reached a screen.
CANARY = "CANARY Value 4TQ9M"

SCREEN_READ = screen("audit").read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
EXISTENCE = plane_capability(Plane.EXISTENCE)


def grant(value: Capability | str) -> Grant:
    capability = value if isinstance(value, Capability) else Capability(value=value)
    return Grant(capability=capability, scope=Scope.unrestricted())


#: `u_admin` is the auditor, reading every kind. `u_narrow` reads principal entries only.
#: `u_wide` holds the screen and no audit grant, so reads only the entries about themselves.
#: `u_prefix` holds everything on the existence plane, which a bare capability check lets in.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (grant(SCREEN_READ), grant(CONFIGURATION), grant("read:audit.*")),
    "u_narrow": (grant(SCREEN_READ), grant(CONFIGURATION), grant("read:audit.principal")),
    "u_wide": (grant(SCREEN_READ), grant(CONFIGURATION)),
    "u_prefix": (grant(SCREEN_READ), grant(EXISTENCE), grant("read:audit.*")),
    "u_elsewhere": (),
    "u_none": (),
}


class Directory:
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
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def stored(entry: AuditEntry) -> AuditEntryRow:
    """An entry as `obs.audit_entry` holds it."""
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


#: Six entries, oldest first: three about principals, three about other kinds.
PLAN: Sequence[tuple[AuditAction, str, str, Mapping[str, object]]] = (
    (AuditAction.GRANT, "u_admin", "principal:u_wide", {"capability": "read:client.name"}),
    (AuditAction.PUBLISH, "u_elsewhere", "artifact:report_1", {}),
    (AuditAction.DENY, "u_narrow", "connector:xero", {"reason": "no_grant"}),
    (AuditAction.LEASH_CHANGE, "u_admin", "agent:helper", {"target": "ticket.status"}),
    (AuditAction.REVOKE, "u_admin", "principal:u_narrow", {"capability": "read:client.name"}),
    (AuditAction.SIGN_IN, "u_admin", "principal:u_wide", {"change": "bound"}),
)


@dataclass
class Ledger:
    """A `brain.audit_routes.LedgerWindows` over rows in memory, windowed as the statement is."""

    rows: list[AuditEntryRow] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def window(
        self,
        criteria: AuditFilter,
        *,
        subject: str | None = None,
        position: tuple[datetime, str] | None,
        newest_first: bool,
        limit: int,
    ) -> Sequence[AuditEntryRow]:
        self.calls.append(
            {
                "position": position,
                "newest_first": newest_first,
                "limit": limit,
                "subject": subject,
            }
        )
        chosen = [
            row
            for row in self.rows
            if (not criteria.actions or row.action in {a.value for a in criteria.actions})
            and (
                not criteria.subject_kinds
                or row.subject.partition(":")[0] in criteria.subject_kinds
            )
            and (not criteria.actors or row.actor_id in criteria.actors)
            and (criteria.since is None or row.at >= criteria.since)
            and (criteria.until is None or row.at < criteria.until)
            and (subject is None or row.subject == subject)
        ]
        chosen.sort(key=lambda row: (row.at, row.entry_hash), reverse=newest_first)
        if position is not None:
            chosen = [
                row
                for row in chosen
                if ((row.at, row.entry_hash) < position) == newest_first
                and (row.at, row.entry_hash) != position
            ]
        return chosen[:limit]


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
def ledger() -> Ledger:
    return Ledger(rows=[stored(one) for one in chain_of(PLAN)])


@pytest.fixture
def client(ledger: Ledger) -> Iterator[TestClient]:
    # The router is included here as well as by `brain.app`, which is
    # `tests/unit/test_sign_in_routes.py`' arrangement: a route registered twice answers from the
    # same function, and this file tests the router whether or not that line is in the tree.
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(audit_routes.router)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.audit_ledger = ledger
        yield c


def get(c: TestClient, pid: str, path: str = AUDIT, **params: str | int) -> Response:
    token = token_for(pid, claims={"amr": ["otp"]})
    response: Response = c.get(path, params=params, headers={"authorization": f"Bearer {token}"})
    return response


def seen(answer: Response) -> list[tuple[str, str, str]]:
    return [
        (one["action"], one["actor_id"], f"{one['subject_kind']}:{one['subject_id']}")
        for one in answer.json()["items"]
    ]


def refusal(answer: Response) -> dict[str, Any]:
    body = dict(answer.json())
    assert "trace_id" in body
    body["trace_id"] = "<per request>"
    return body


# ----------------------------------------------------------------------- the page


def test_an_auditor_reads_the_whole_ledger_newest_first_and_oldest_first_on_request(
    client: TestClient,
) -> None:
    """The positive case for every refusal below. Delete this and each refusal is satisfied by a
    route that shows nothing, and the default order can be the one that puts what just happened
    on the last page."""
    newest = get(client, "u_admin")
    oldest = get(client, "u_admin", order="oldest")

    assert newest.status_code == 200, newest.text
    assert [one[2] for one in seen(newest)] == [
        "principal:u_wide",
        "principal:u_narrow",
        "agent:helper",
        "connector:xero",
        "artifact:report_1",
        "principal:u_wide",
    ]
    assert seen(oldest) == list(reversed(seen(newest)))
    assert newest.json()["next_cursor"] is None


def test_a_reader_of_one_kind_is_answered_as_though_the_rest_were_never_written(
    client: TestClient, ledger: Ledger
) -> None:
    """M27.7.13's first half: readable without naming what is withheld. The byte comparison is the
    strong form: an entry the reader may not see and an entry never written are indistinguishable
    on the page, in its length, its cursor and its offered filters. Delete this and a withheld row
    can leave a trace, a placeholder, a short page or an actor in a dropdown."""
    with_withheld = get(client, "u_narrow", limit=2)
    ledger.rows = [row for row in ledger.rows if row.subject.startswith("principal:")]
    without = get(client, "u_narrow", limit=2)

    assert with_withheld.status_code == 200, with_withheld.text
    assert {one[2].partition(":")[0] for one in seen(with_withheld)} == {"principal"}
    assert with_withheld.content == without.content


def test_a_person_with_the_screen_and_no_audit_grant_reads_only_what_is_about_them(
    client: TestClient,
) -> None:
    """The view's subject access rule, served. Delete this and the screen shows such a reader
    nothing, or shows them the ledger their grant does not cover."""
    answer = get(client, "u_wide")

    assert answer.status_code == 200, answer.text
    assert {one[2] for one in seen(answer)} == {"principal:u_wide"}


def test_the_people_a_filter_offers_are_the_actors_on_the_rows_shown_and_nobody_else(
    client: TestClient,
) -> None:
    """M27.7.13's second half: narrowable without naming what is withheld. Delete this and the
    actor list can be read from the table, which tells a reader who has done anything here: the
    actors of every withheld entry arriving through a dropdown."""
    mine = get(client, "u_wide").json()
    everything = get(client, "u_admin").json()

    assert mine["actors"] == ["u_admin"]
    assert everything["actors"] == ["u_admin", "u_narrow", "u_elsewhere"]
    assert mine["actions"] == [one.value for one in AuditAction]
    assert mine["subject_kinds"] == sorted(
        {
            "principal",
            "grant",
            "agent",
            "leash",
            "entity",
            "artifact",
            "connector",
            "session",
            "credential",
            "retention",
            "legal_hold",
            "skill",
            "setting",
            "routing",
            "webhook",
            "erasure",
            "memory",
            "department",
            "scope",
            "breach",
        }
    )


def test_every_filter_narrows_to_exactly_what_it_names(client: TestClient) -> None:
    """Delete this and a filter can be accepted and dropped, so a reader believes they are looking
    at one action, kind, person or day and is looking at all of them."""
    by_action = seen(get(client, "u_admin", action="revoke"))
    by_kind = seen(get(client, "u_admin", subject_kind="agent"))
    by_actor = seen(get(client, "u_admin", actor="u_narrow"))
    by_window = seen(
        get(
            client,
            "u_admin",
            since=(BEGAN + timedelta(minutes=1)).isoformat(),
            until=(BEGAN + timedelta(minutes=3)).isoformat(),
        )
    )

    assert by_action == [("revoke", "u_admin", "principal:u_narrow")]
    assert by_kind == [("leash_change", "u_admin", "agent:helper")]
    assert by_actor == [("deny", "u_narrow", "connector:xero")]
    assert [one[2] for one in by_window] == ["connector:xero", "artifact:report_1"]


def test_a_search_reads_what_a_visible_row_says_and_never_an_entry_the_reader_may_not_see(
    client: TestClient,
) -> None:
    """Delete this and the ledger search can be matched before the visibility decision, so a reader
    of principal entries types a connector's name and learns from a short page or a cursor whether
    it was denied; or it reads the digest or the trace, which a row never shows. The positive halves
    are the auditor finding the connector entry and a principal reader finding their own kind by a
    detail it carries."""
    auditor = seen(get(client, "u_admin", q="XERO"))
    narrow = get(client, "u_narrow", q="xero").json()
    by_detail = seen(get(client, "u_narrow", q="client.name revoke"))
    by_trace = get(client, "u_admin", q="trace2").json()

    assert auditor == [("deny", "u_narrow", "connector:xero")]
    assert narrow["items"] == [] and narrow["next_cursor"] is None
    assert by_detail == [("revoke", "u_admin", "principal:u_narrow")]
    assert by_trace["items"] == []


def test_a_page_continues_from_its_cursor_through_every_visible_entry_exactly_once(
    client: TestClient,
) -> None:
    """Delete this and the loader can start from the newest entry every time, repeat the page it
    came from, or skip the entry at a page boundary, which a reader reads as a gap in the ledger."""
    for order in ("newest", "oldest"):
        collected: list[tuple[str, str, str]] = []
        cursor: str | None = None
        while True:
            params: dict[str, str | int] = {"limit": 2, "order": order}
            if cursor is not None:
                params["cursor"] = cursor
            body = get(client, "u_admin", AUDIT, **params).json()
            collected.extend((one["action"], one["at"], one["subject_id"]) for one in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break
        assert len(collected) == 6 == len(set(collected)), order


def test_a_reading_ceiling_stops_a_short_page_with_a_cursor_that_skips_nothing(
    client: TestClient, ledger: Ledger, monkeypatch: pytest.MonkeyPatch
) -> None:
    """See `A_READING_CEILING_SAYS_WHERE_IT_STOPPED_AND_NEVER_HOW_MUCH_IT_PASSED`. Six withheld
    entries lie between a principal reader and the two entries they may see. Delete this and the
    route can read without a ceiling, or stop and return no cursor, so the two entries are never
    reached; or continue from the last row it showed rather than the last it read, and loop."""
    monkeypatch.setattr(audit_routes, "LOAD_CHUNK", 2)
    monkeypatch.setattr(audit_routes, "READ_CEILING", 4)
    plan: list[tuple[AuditAction, str, str, Mapping[str, object]]] = [
        (AuditAction.GRANT, "u_admin", "principal:u_wide", {}),
        (AuditAction.REVOKE, "u_admin", "principal:u_narrow", {}),
        *((AuditAction.DENY, "u_admin", f"connector:c{i}", {}) for i in range(6)),
    ]
    ledger.rows = [stored(one) for one in chain_of(plan)]
    pages: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        params: dict[str, str | int] = {"limit": 5}
        if cursor is not None:
            params["cursor"] = cursor
        body = get(client, "u_narrow", AUDIT, **params).json()
        pages.append(body)
        cursor = body["next_cursor"]
        if cursor is None or len(pages) > 5:
            break

    assert pages[0]["items"] == []
    assert pages[0]["next_cursor"] is not None
    shown = [one["subject_id"] for page in pages for one in page["items"]]
    assert shown == ["u_narrow", "u_wide"]
    assert max(one["limit"] for one in ledger.calls) == 2


def test_a_page_that_has_found_its_next_entry_stops_reading(
    client: TestClient, ledger: Ledger, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the loader can go on reading chunk after chunk once the page is full and
    its cursor known, which is the whole ledger read for a page of two."""
    monkeypatch.setattr(audit_routes, "LOAD_CHUNK", 2)
    monkeypatch.setattr(audit_routes, "READ_CEILING", 100)

    body = get(client, "u_admin", limit=2).json()

    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None
    assert len(ledger.calls) == 2


def test_a_stored_row_that_is_not_an_entry_is_skipped_and_never_shown(
    client: TestClient, ledger: Ledger
) -> None:
    """Delete this and a row written by hand carrying a value reaches the screen, or takes the
    whole ledger down for every reader."""
    ledger.rows[0].details = {"note": CANARY}

    answer = get(client, "u_admin")

    assert answer.status_code == 200, answer.text
    assert CANARY not in answer.text
    assert len(answer.json()["items"]) == 5


def test_nothing_on_the_answer_could_carry_a_count() -> None:
    """Delete this and a total can join the page, which on a ledger filtered per reader is the
    subtraction CLAUDE.md forbids."""
    for model in (
        audit_routes.AuditLedgerPage,
        audit_routes.AuditRowView,
        audit_routes.PermissionHistoryView,
        audit_routes.PermissionEventView,
    ):
        assert not set(model.model_fields) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT, model
    assert "total" not in audit_routes.AuditLedgerPage.model_fields


# ----------------------------------------------------------------------- the refusals


def test_a_caller_without_the_screen_or_on_the_existence_plane_is_refused_before_the_ledger(
    client: TestClient, ledger: Ledger
) -> None:
    """`permitted` asks the capability and the plane together, first. Delete this and an
    existence-only reader opens a configuration screen, or the ledger is read for a caller who
    will be refused, which is a timing difference between a busy install and an empty one."""
    stranger = get(client, "u_none")
    existence = get(client, "u_prefix")
    history = get(client, "u_none", HISTORY, subject_kind="principal", subject_id="u_wide")

    assert stranger.status_code == existence.status_code == history.status_code == 404
    assert refusal(stranger) == refusal(existence)
    assert ledger.calls == []


def test_a_filter_or_cursor_the_view_would_refuse_is_a_malformed_parameter_before_any_read(
    client: TestClient, ledger: Ledger
) -> None:
    """Delete this and an unknown kind, a naive date or a forged cursor can reach the loader as a
    500, or be quietly ignored and answered with the whole ledger."""
    unknown_kind = get(client, "u_admin", subject_kind="payroll")
    naive = get(client, "u_admin", since="2019-03-04T09:00:00")
    inverted = get(
        client, "u_admin", since=BEGAN.isoformat(), until=(BEGAN - timedelta(days=1)).isoformat()
    )
    forged = get(client, "u_admin", cursor="not-a-cursor")
    pattern = get(client, "u_admin", actor="u_%")

    assert {
        unknown_kind.status_code,
        naive.status_code,
        inverted.status_code,
        forged.status_code,
        pattern.status_code,
    } == {422}
    assert ledger.calls == []


# ----------------------------------------------------------------------- the history


def test_a_subjects_permission_history_is_its_grants_and_revocations_oldest_first(
    client: TestClient, ledger: Ledger
) -> None:
    """`brain.console.auditor.permission_history`, served. Delete this and the history can carry a
    sign-in or a publish, which changed nothing anybody may do, or another subject's grants, or
    read every entry of the kind to find this subject's."""
    ledger.rows = [
        stored(one)
        for one in chain_of(
            [
                (AuditAction.GRANT, "u_admin", "principal:u_wide", {"capability": "read:a.b"}),
                (AuditAction.GRANT, "u_admin", "principal:u_narrow", {}),
                (AuditAction.SIGN_IN, "u_admin", "principal:u_wide", {"change": "bound"}),
                (AuditAction.REVOKE, "u_admin", "principal:u_wide", {"capability": "read:a.b"}),
            ]
        )
    ]

    answer = get(client, "u_admin", HISTORY, subject_kind="principal", subject_id="u_wide")

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert [one["action"] for one in body["events"]] == ["grant", "revoke"]
    assert body["full"] is False
    assert {one["subject"] for one in ledger.calls} == {"principal:u_wide"}


def test_a_history_that_fills_a_page_says_so(client: TestClient, ledger: Ledger) -> None:
    """Delete this and a history cut short at a page reads as the whole of it, which is an
    auditor told a grant was never revoked because the revocation was the two hundred and first
    change."""
    many: list[tuple[AuditAction, str, str, Mapping[str, object]]] = [
        (AuditAction.GRANT, "u_admin", "principal:u_wide", {}) for _ in range(MAX_PAGE_SIZE + 1)
    ]
    ledger.rows = [stored(one) for one in chain_of(many)]

    body = get(client, "u_admin", HISTORY, subject_kind="principal", subject_id="u_wide").json()

    assert len(body["events"]) == MAX_PAGE_SIZE
    assert body["full"] is True


def test_a_history_the_reader_may_not_see_and_a_history_of_nobody_are_the_same_answer(
    client: TestClient,
) -> None:
    """Delete this and the history becomes a way of asking whether somebody's reach has ever
    changed: a withheld history answered differently from an empty one."""
    withheld = get(client, "u_wide", HISTORY, subject_kind="principal", subject_id="u_narrow")
    nobody = get(client, "u_wide", HISTORY, subject_kind="principal", subject_id="u_nobody")

    assert withheld.json()["events"] == nobody.json()["events"] == []
    assert withheld.status_code == nobody.status_code == 200


# ----------------------------------------------------------------------- the statement


def compiled(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


def test_the_window_puts_every_filter_into_the_statement_in_the_views_order() -> None:
    """See `A_FILTER_IN_THE_STATEMENT_ONLY_LOADS_LESS`. Delete this and the statement can drop a
    filter, so a busy ledger is read to find three entries; match a kind without its colon, so
    `principal` loads a kind that merely begins with it; or order ties by a collation the view
    does not use, which makes a page boundary repeat or skip an entry."""
    position = (BEGAN, "a" * 64)
    criteria = AuditFilter(
        actions=frozenset({AuditAction.GRANT}),
        subject_kinds=frozenset({"principal"}),
        actors=frozenset({"u_admin"}),
        since=BEGAN,
        until=BEGAN + timedelta(days=1),
    )

    newest = compiled(window(criteria, position=position, newest_first=True, limit=500))
    oldest = compiled(
        window(
            AuditFilter(), subject="principal:u_x", position=position, newest_first=False, limit=5
        )
    )

    kinds = window(criteria, position=None, newest_first=True, limit=5).compile(dialect=DIALECT)

    assert "obs.audit_entry.action IN" in newest
    assert "obs.audit_entry.subject LIKE" in newest
    assert "principal:" in kinds.params.values()
    assert "obs.audit_entry.actor_id IN" in newest
    assert "obs.audit_entry.at >=" in newest and "obs.audit_entry.at <" in newest
    assert '(obs.audit_entry.at, obs.audit_entry.entry_hash COLLATE "C") <' in newest
    assert (
        'ORDER BY obs.audit_entry.at DESC, obs.audit_entry.entry_hash COLLATE "C" DESC LIMIT'
        in newest
    )
    assert "obs.audit_entry.subject = " in oldest
    assert '(obs.audit_entry.at, obs.audit_entry.entry_hash COLLATE "C") >' in oldest
    assert 'ORDER BY obs.audit_entry.at, obs.audit_entry.entry_hash COLLATE "C"' in oldest
    assert "LIKE" not in oldest and "IN (" not in oldest


def test_a_row_with_an_action_nobody_declared_is_not_an_entry() -> None:
    """Delete this and a row a later version wrote under an action this one does not know raises
    out of the page instead of being skipped."""
    row = stored(chain_of(PLAN)[0])
    row.action = "invented"

    assert entry_from(row) is None
    assert entry_from(stored(chain_of(PLAN)[0])) is not None
