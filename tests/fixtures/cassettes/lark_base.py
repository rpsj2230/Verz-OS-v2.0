"""Lark Base's recordings: a page with more, one record, a refusal inside a 200, the minute,
and the Base's own schema, its tables and one table's typed fields.

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
#: A Base's tables and one table's fields, bitable v1, written from Lark's documentation and
#: not fetched for these recordings: each field carries `field_id`, `field_name`, the numeric
#: `type` that `lark_base.KIND_FACTS` names, `ui_type` and `is_primary`.
LARK_BASE_TABLES_DOC = (
    "https://open.larksuite.com/document/server-docs/docs/bitable-v1/app-table/list"
)
LARK_BASE_FIELDS_DOC = (
    "https://open.larksuite.com/document/server-docs/docs/bitable-v1/app-table-field/list"
)

#: The table every schema recording is about, which is the table the record recordings read.
SCHEMA_TABLE = "tblsRc9GRRXKqhvW"


def a_field(field_id: str, name: str, api_type: int, ui_type: str, **extra: Any) -> dict[str, Any]:
    """One field as the documented field listing describes it."""
    return {
        "field_id": field_id,
        "field_name": name,
        "type": api_type,
        "property": None,
        "is_primary": False,
        "ui_type": ui_type,
        **extra,
    }


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
        cid="LARK-200-tables",
        source=SOURCE,
        request="GET /open-apis/bitable/v1/apps/{app}/tables?page_size=100",
        status=200,
        body={
            "code": 0,
            "msg": "success",
            "data": {
                "has_more": False,
                "page_token": SCHEMA_TABLE,
                "total": 1,
                "items": [{"table_id": SCHEMA_TABLE, "revision": 1, "name": "Maintenance hours"}],
            },
        },
        why="The Base's own list of its tables. Connect Lark keeps the Base's token and nothing "
        "else, so this is where a table to read comes from, by its id and never its title.",
        kind=Kind.LIST,
        tools=("lark_base.list_{entity}",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARK_BASE_TABLES_DOC,
    ),
    Cassette(
        cid="LARK-200-fields",
        source=SOURCE,
        request="GET /open-apis/bitable/v1/apps/{app}/tables/{tbl}/fields?page_size=100",
        status=200,
        body={
            "code": 0,
            "msg": "success",
            "data": {
                "has_more": False,
                "page_token": "fldEdit0007",
                "total": 8,
                "items": [
                    a_field("fldPrim0001", "Client", 1, "Text", is_primary=True),
                    a_field("fldStat0002", "Status", 3, "SingleSelect"),
                    a_field("fldHour0003", "Hours Remaining", 2, "Number"),
                    a_field("fldValu0004", "Contract Value", 1, "Text"),
                    a_field("fldRenw0005", "Renewal", 5, "DateTime"),
                    a_field("fldOwnr0006", "Account manager", 11, "User"),
                    a_field("fldLink0008", "Projects", 18, "SingleLink"),
                    a_field("fldEdit0007", "Last modified", 1002, "ModifiedTime"),
                ],
            },
        },
        why="One table's fields with their Lark types, which decide what each becomes: the "
        "primary field is the index's one label, a person and a link are bound to nothing, "
        "and the contract value is read live and never kept.",
        kind=Kind.LIST,
        tools=("lark_base.list_{entity}",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARK_BASE_FIELDS_DOC,
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


@dataclass
class _Schema:
    reply: lark_base.LarkReply

    def list_tables(self, request: lark_base.SchemaRequest) -> lark_base.LarkReply:
        del request
        return self.reply

    def list_fields(self, request: lark_base.SchemaRequest) -> lark_base.LarkReply:
        del request
        return self.reply


def _replay_schema(recorded: Cassette) -> Replayed:
    """A schema recording through `read_tables` or `read_table`: answered when it names any."""
    from tests.unit.test_lark_base import BASE_ID

    schema = _Schema(lark_base.LarkReply(status=recorded.status, body=recorded.body))
    budget = lark_base.fair_share_budget()
    if recorded.request.split("?")[0].endswith("/tables"):
        tables, _ = lark_base.read_tables(schema, BASE_ID, budget=budget)
        return Replayed(Expect.ANSWERED if tables else Expect.ABSENT)
    table = lark_base.DiscoveredTable(table_id=SCHEMA_TABLE, title="")
    read, _ = lark_base.read_table(schema, BASE_ID, table, budget=budget)
    return Replayed(Expect.ANSWERED if read.fields else Expect.ABSENT)


def replay(recorded: Cassette) -> Replayed:
    """A recording through `lark_base.read_page` or `read_record`, and the table's projection,
    or through the schema reads for a recording of the Base's tables or fields."""
    from tests.unit.test_lark_base import a_table, list_operation, single_operation

    if recorded.request.split("?")[0].endswith(("/tables", "/fields")):
        return _replay_schema(recorded)
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
