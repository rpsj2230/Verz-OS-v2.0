"""Lark Base's recordings: a page with more, one record, a refusal inside a 200, and the minute.

A cell carries a canary: a contract value is read live and never kept.

Task ids: M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from brain.connectors import lark_base
from brain.connectors.manifest import ConnectorManifest
from tests.fixtures.cassettes._types import (
    DOCUMENTED,
    SEEN_AT,
    Cassette,
    CassetteFile,
    Expect,
    Kind,
    RateLimit,
    Replayed,
    unreachable_or_quota,
)

SOURCE: Final = "lark_base"

LARK_BASE_LIST_DOC = (
    "https://open.larksuite.com/document/server-docs/docs/bitable-v1/app-table-record/list"
)
LARK_BASE_GET_DOC = (
    "https://open.larksuite.com/document/server-docs/docs/bitable-v1/app-table-record/get"
)
LARK_RATE_DOC = "https://open.larksuite.com/document/ukTMukTMukTM/uUzN04SN3QjL1cDN"


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="LARK-200-records",
        source=SOURCE,
        request="GET /open-apis/bitable/v1/apps/{app}/tables/{tbl}/records?page_size=100",
        status=200,
        body={
            "code": 0,
            "data": {
                "has_more": True,
                "page_token": "eyJvZmZzZXQiOjEwMH0",
                "total": 412,
                "items": [
                    {
                        "record_id": "recSNM0447",
                        "fields": {
                            "Client": "SNM Construction Pte Ltd",
                            "Hours Remaining": 12,
                            "Contract Value": "CANARY-CONTRACT-7Q4XZ",
                            "Renewal": 1794700800000,
                        },
                    }
                ],
            },
        },
        why="Lark returns code 0 inside a 200 for success and a non-zero code inside a "
        "200 for failure. A connector checking only the HTTP status treats every error "
        "as a successful empty result.",
        kind=Kind.PAGINATION,
        tools=("lark_base.list_{entity}",),
        projects="{entity}",
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=LARK_BASE_LIST_DOC,
    ),
    Cassette(
        cid="LARK-200-code-permission",
        source=SOURCE,
        request="GET /open-apis/bitable/v1/apps/{app}/tables/{tbl}/records",
        status=200,
        body={"code": 91403, "msg": "Forbidden", "data": {}},
        why="HTTP 200 carrying a permission failure. The bot's own token is scoped to "
        "base:record:read; anything wider comes back like this, and a connector reading "
        "only the status code records an empty table as fact.",
        kind=Kind.ERROR,
        tools=("lark_base.list_{entity}",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=LARK_BASE_LIST_DOC,
    ),
    Cassette(
        cid="LARK-200-record",
        source=SOURCE,
        request="GET /open-apis/bitable/v1/apps/{app}/tables/{tbl}/records/recSNM0447",
        status=200,
        body={
            "code": 0,
            "msg": "success",
            "data": {
                "record": {
                    "id": "recSNM0447",
                    "record_id": "recSNM0447",
                    "fields": {
                        "Client": "SNM Construction Pte Ltd",
                        "Title": "Maintenance 0447",
                        "Status": "Active",
                        "Hours Remaining": 12,
                        "Contract Value": "CANARY-CONTRACT-7Q4XZ",
                        "Renewal": 1794700800000,
                    },
                }
            },
        },
        why="One record under data.record with no has_more: a different envelope from a page.",
        kind=Kind.READ,
        tools=("lark_base.read_{entity}",),
        projects="{entity}",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARK_BASE_GET_DOC,
    ),
    Cassette(
        cid="LARK-429",
        source=SOURCE,
        request="GET /open-apis/bitable/v1/apps/{app}/tables/{tbl}/records",
        status=429,
        headers={"x-ogw-ratelimit-limit": "100", "x-ogw-ratelimit-reset": "37"},
        body={"code": 99991400, "msg": "request trigger frequency limit"},
        why="Lark documents the wait in x-ogw-ratelimit-reset and not in Retry-After, so a "
        "connector reading only Retry-After falls back to its own figure.",
        kind=Kind.RATE_LIMIT,
        tools=("lark_base.list_{entity}",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=LARK_RATE_DOC,
    ),
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    100,
    "minute",
    "Permanently uncapped - Lark does not raise this on request, so it is a design "
    "constraint rather than a starting tier.",
    False,
)


@dataclass
class _OneReply:
    reply: Any

    def read(self, cursor: object) -> Any:
        del cursor
        return self.reply


def replay(recorded: Cassette) -> Replayed:
    """A recording through `lark_base.read_page` or `read_record`, and the table's projection."""
    from tests.unit.test_lark_base import a_table, list_operation, single_operation

    table = a_table()
    reader = _OneReply(
        lark_base.LarkReply(status=recorded.status, headers=recorded.headers, body=recorded.body)
    )
    single = recorded.kind is Kind.READ
    try:
        if single:
            cursor = lark_base.PageCursor(
                endpoint=lark_base.Endpoint.GET_RECORD, record_id="recSNM0447"
            )
            row, _ = lark_base.read_record(
                single_operation(), reader, cursor, budget=lark_base.fair_share_budget()
            )
            rows: tuple[Mapping[str, Any], ...] = (row,)
            more = False
        else:
            rows, envelope = lark_base.read_page(list_operation(), reader, lark_base.first_cursor())
            more = envelope.has_more
    except lark_base.LarkBaseRefusedError:
        return Replayed(Expect.REFUSED)
    except lark_base.LarkBaseUnreachableError as failed:
        return Replayed(unreachable_or_quota(failed.call_outcome))
    if not rows:
        return Replayed(Expect.ABSENT)
    projected = tuple(table.projected_record(row, last_seen_at=SEEN_AT) for row in rows)
    return Replayed(Expect.MORE_TO_READ if more else Expect.ANSWERED, projected)


def manifest() -> ConnectorManifest:
    from tests.unit import test_lark_base

    built: ConnectorManifest = test_lark_base.a_manifest()
    return built


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
    tools_named_after_the_table=True,
)
