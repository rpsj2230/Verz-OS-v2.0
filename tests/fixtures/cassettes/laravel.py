"""Laravel's recordings, through database views: rows, a row cap, a withdrawn grant, a gone server.

The client's contract value carries a canary, and a row carrying a column its view contract does
not name must not arrive at all.

Task ids: M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

from typing import Any, Final

from brain.connectors import laravel
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.throttle import CallOutcome
from tests.fixtures.cassettes._types import (
    DOCUMENTED,
    FETCHED_AT,
    SEEN_AT,
    Cassette,
    CassetteFile,
    Expect,
    Kind,
    Protocol,
    RateLimit,
    Replayed,
    unreachable_or_quota,
)

SOURCE: Final = "laravel"

MYSQL_ERRORS_DOC = "https://dev.mysql.com/doc/mysql-errors/8.0/en/server-error-reference.html"
MYSQL_CLIENT_ERRORS_DOC = (
    "https://dev.mysql.com/doc/mysql-errors/8.0/en/client-error-reference.html"
)
#: Laravel's rows are the view contract this connector declares rather than a vendor's API, so
#: the documented shape of a row is the connector's own column list.
LARAVEL_VIEW_CONTRACT = "brain.connectors.laravel.columns_for"


def _laravel_client(number: int) -> dict[str, Any]:
    return {
        "id": 4_400 + number,
        "name": f"Client {number}",
        "status": "active",
        "department": "maintenance",
        "manager_id": "u_weiling",
        "updated_at": "2026-09-01T10:00:00+00:00",
        "contract_value": "CANARY-CONTRACT-7Q4XZ",
    }


#: Laravel's row cap in the recording below, which is the bound the replay's connection declares.
LARAVEL_RECORDED_CAP = 200


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="LARAVEL-500",
        source=SOURCE,
        request="GET /internal/clients/4471",
        status=500,
        body={"message": "Server Error"},
        why="Our own system failing. Still DEGRADED, still no substituted value - being "
        "in-house is not a reason to trust an error response. Laravel's default JSON error "
        "body; the connector reads views, and this is how the application's own failure was "
        "recorded rather than something the connector requests.",
        kind=Kind.ERROR,
        tools=("laravel.read_clients",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference="https://laravel.com/docs/errors",
    ),
    Cassette(
        cid="LARAVEL-rows-clients",
        source=SOURCE,
        request="SELECT id, contract_value, department, manager_id, name, status, updated_at "
        "FROM portal.v_clients LIMIT 200",
        status=0,
        body={"rows": [_laravel_client(71), {**_laravel_client(72), "api_token": "CANARY-TOK"}]},
        why="Two rows, one carrying a column the view contract does not name. It must not "
        "arrive, and the contract value must not be projected.",
        kind=Kind.LIST,
        tools=("laravel.read_clients",),
        projects="client",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARAVEL_VIEW_CONTRACT,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-rows-users",
        source=SOURCE,
        request="SELECT id, department, display_name, status, updated_at FROM portal.v_users "
        "LIMIT 200",
        status=0,
        body={
            "rows": [
                {
                    "id": 12,
                    "display_name": "Wei Ling",
                    "department": "maintenance",
                    "status": "active",
                    "updated_at": "2026-09-01T10:00:00+00:00",
                }
            ]
        },
        why="A staff record: a name and a department, and nothing that reaches a person.",
        kind=Kind.LIST,
        tools=("laravel.read_users",),
        projects="user",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARAVEL_VIEW_CONTRACT,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-rows-at-cap",
        source=SOURCE,
        # A recorded statement, compared as text and never executed.
        request=(
            "SELECT id, contract_value, department, manager_id, name, status, updated_at "  # noqa: S608
            f"FROM portal.v_clients LIMIT {LARAVEL_RECORDED_CAP}"
        ),
        status=0,
        body={"rows": [_laravel_client(n) for n in range(LARAVEL_RECORDED_CAP)]},
        why="A read that filled its row cap. A database does not page; the cap is ours, and "
        "reaching it is the only sign there were more.",
        kind=Kind.PAGINATION,
        tools=("laravel.read_clients",),
        projects="client",
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=LARAVEL_VIEW_CONTRACT,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-1142",
        source=SOURCE,
        request="SELECT id, display_name FROM portal.v_users LIMIT 200",
        status=0,
        body={
            "errno": 1142,
            "sqlstate": "42000",
            "message": "SELECT command denied to user 'brain_ro'@'10.0.0.8' for table 'v_users'",
        },
        why="The grant no longer covers the view. A withdrawn contract, never an empty view.",
        kind=Kind.ERROR,
        tools=("laravel.read_users",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=MYSQL_ERRORS_DOC,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-1146",
        source=SOURCE,
        request="SELECT id, name FROM portal.v_clients LIMIT 200",
        status=0,
        body={
            "errno": 1146,
            "sqlstate": "42S02",
            "message": "Table 'portal.v_clients' doesn't exist",
        },
        why="The view was dropped or renamed. Also a withdrawn contract.",
        kind=Kind.ERROR,
        tools=("laravel.read_clients",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=MYSQL_ERRORS_DOC,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-3024",
        source=SOURCE,
        request="SELECT id, name FROM portal.v_clients LIMIT 200",
        status=0,
        body={
            "errno": 3024,
            "sqlstate": "HY000",
            "message": "Query execution was interrupted, maximum statement execution time exceeded",
        },
        why="Our own time bound fired on somebody else's database.",
        kind=Kind.ERROR,
        tools=("laravel.read_clients",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference=MYSQL_ERRORS_DOC,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-2006",
        source=SOURCE,
        request="SELECT id, name FROM portal.v_clients LIMIT 200",
        status=0,
        body={"errno": 2006, "sqlstate": "HY000", "message": "MySQL server has gone away"},
        why="The server went away mid-read. A client error number, from the client reference.",
        kind=Kind.ERROR,
        tools=("laravel.read_clients",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference=MYSQL_CLIENT_ERRORS_DOC,
        protocol=Protocol.DATABASE,
    ),
)

RATE_LIMIT: Final = RateLimit(SOURCE, 0, "no ceiling", "Our own system.", True)


def replay(recorded: Cassette) -> Replayed:
    """A recording through `laravel.interpret` and `projected_record`, under the recorded cap."""
    from tests.unit.test_laravel import connection

    entity = laravel.ENTITY_USER if "v_users" in recorded.request else laravel.ENTITY_CLIENT
    read = laravel.read_plan(connection(), entity)
    assert read.plan.limit == LARAVEL_RECORDED_CAP, "the recording's cap is not the replay's"
    body = recorded.body
    if recorded.protocol is Protocol.HTTP:
        view = laravel.ViewReply(app_status=recorded.status)
    elif "errno" in body:
        view = laravel.ViewReply(fault=laravel.fault_for_mysql_error(body["errno"]))
    else:
        view = laravel.ViewReply(rows=tuple(body["rows"]))
    reply = laravel.interpret(read, view, fetched_at=FETCHED_AT)
    if reply.outcome is laravel.LaravelOutcome.REFUSED:
        return Replayed(Expect.REFUSED)
    if reply.outcome is laravel.LaravelOutcome.UNREACHABLE:
        return Replayed(unreachable_or_quota(reply.call))
    assert reply.rows is not None
    rows = [record.model_dump() for record in reply.rows.records]
    if not rows:
        return Replayed(Expect.ABSENT)
    kept = [laravel.projected_record(entity, row, last_seen_at=SEEN_AT) for row in rows]
    projected = tuple(one for one in kept if one is not None)
    more = reply.call is CallOutcome.TRUNCATED
    return Replayed(Expect.MORE_TO_READ if more else Expect.ANSWERED, projected)


def manifest() -> ConnectorManifest:
    from tests.unit import test_laravel

    built: ConnectorManifest = test_laravel.manifest()
    return built


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
    not_recordable={
        Kind.RATE_LIMIT: (
            "a database read through views has no rate limiter; "
            "laravel.THERE_IS_NO_MEASURED_CEILING_HERE"
        ),
    },
)
