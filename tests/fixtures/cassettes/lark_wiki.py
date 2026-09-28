"""Lark Wiki's recordings: a node, a page of nodes, a refusal inside a 200, and the tenant's minute.

The wiki projects nothing, so no recording here feeds a kept record.

Task ids: M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from brain.connectors import lark_wiki
from brain.connectors.contract import FetchRequest
from brain.connectors.manifest import ConnectorManifest
from tests.fixtures.cassettes._types import (
    DOCUMENTED,
    FETCHED_AT,
    Cassette,
    CassetteFile,
    Expect,
    Kind,
    RateLimit,
    Replayed,
    unreachable_or_quota,
)

SOURCE: Final = "lark_wiki"

LARK_RATE_DOC = "https://open.larksuite.com/document/ukTMukTMukTM/uUzN04SN3QjL1cDN"
LARK_WIKI_LIST_DOC = "https://open.larksuite.com/document/server-docs/docs/wiki-v2/space-node/list"
LARK_WIKI_GET_DOC = (
    "https://open.larksuite.com/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/wiki-v2/space/get_node"
)

#: The space a wiki recording's listing was asked for.
WIKI_SPACE = "6946843325487912356"


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="LARK-WIKI-200-node",
        source=SOURCE,
        request="GET /open-apis/wiki/v2/spaces/get_node?token=wikcnKQ1k3pcuo5uSK4t8Vabcef",
        status=200,
        body={
            "code": 0,
            "msg": "success",
            "data": {
                "node": {
                    "space_id": WIKI_SPACE,
                    "node_token": "wikcnKQ1k3pcuo5uSK4t8Vabcef",
                    "obj_token": "doccnzAaODNqykc8g9hOWabcdef",
                    "obj_type": "docx",
                    "parent_node_token": "",
                    "node_type": "origin",
                    "origin_node_token": "wikcnKQ1k3pcuo5uSK4t8Vabcef",
                    "origin_space_id": WIKI_SPACE,
                    "has_child": False,
                    "title": "Maintenance handbook",
                    "obj_create_time": "1642402428",
                    "obj_edit_time": "1642402428",
                    "node_create_time": "1642402428",
                    "creator": "ou_xxxxx",
                    "owner": "ou_xxxxx",
                }
            },
        },
        why="The page's metadata. No body travels on this path, and the creator and owner "
        "ids arrive and are mapped by nothing.",
        kind=Kind.READ,
        tools=("lark_wiki.read_page",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARK_WIKI_GET_DOC,
    ),
    Cassette(
        cid="LARK-WIKI-200-nodes-page",
        source=SOURCE,
        request=f"GET /open-apis/wiki/v2/spaces/{WIKI_SPACE}/nodes?page_size=50",
        status=200,
        body={
            "code": 0,
            "msg": "success",
            "data": {
                "items": [
                    {
                        "space_id": WIKI_SPACE,
                        "node_token": "wikcnKQ1k3pcuo5uSK4t8Vabcef",
                        "obj_token": "doccnzAaODNqykc8g9hOWabcdef",
                        "obj_type": "docx",
                        "parent_node_token": "",
                        "node_type": "origin",
                        "origin_node_token": "wikcnKQ1k3pcuo5uSK4t8Vabcef",
                        "origin_space_id": WIKI_SPACE,
                        "has_child": True,
                        "title": "Maintenance handbook",
                        "obj_create_time": "1642402428",
                        "obj_edit_time": "1642402428",
                        "node_create_time": "1642402428",
                        "creator": "ou_xxxxx",
                        "owner": "ou_xxxxx",
                    }
                ],
                "page_token": "6946843325487906839",
                "has_more": True,
            },
        },
        why="The documented listing, and what it does not carry matters: there is no "
        "has_member_setting on a documented node, so this connector reads every such page "
        "as having undetermined permissions and withholds it. A live capture decides whether "
        "a real tenant ever says otherwise.",
        kind=Kind.PAGINATION,
        tools=("lark_wiki.read_page",),
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=LARK_WIKI_LIST_DOC,
    ),
    Cassette(
        cid="LARK-WIKI-200-code-permission",
        source=SOURCE,
        request="GET /open-apis/wiki/v2/spaces/get_node?token=wikcnKQ1k3pcuo5uSK4t8Vabcef",
        status=200,
        body={"code": 131006, "msg": "permission denied", "data": {}},
        why="The wiki's own permission code, which is not Lark Base's 91403. It is not in the "
        "connector's table of known codes, so it is read as the refusal an unknown code is.",
        kind=Kind.ERROR,
        tools=("lark_wiki.read_page",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=LARK_WIKI_LIST_DOC,
    ),
    Cassette(
        cid="LARK-WIKI-429",
        source=SOURCE,
        request="GET /open-apis/wiki/v2/spaces/get_node?token=wikcnKQ1k3pcuo5uSK4t8Vabcef",
        status=429,
        headers={"x-ogw-ratelimit-limit": "100", "x-ogw-ratelimit-reset": "12"},
        body={"code": 99991400, "msg": "request trigger frequency limit"},
        why="The tenant's minute, shared with Lark Base.",
        kind=Kind.RATE_LIMIT,
        tools=("lark_wiki.read_page",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=LARK_RATE_DOC,
    ),
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    100,
    "minute",
    "The same tenant bucket as Lark Base: Lark publishes one frequency limit per tenant, "
    "and `brain.connectors.lark_wiki` runs against Lark Base's ceiling for that reason.",
    False,
)


@dataclass
class _WikiReader:
    reply: lark_wiki.LarkReply

    def list_nodes(self, request: lark_wiki.NodeListRequest) -> lark_wiki.LarkReply:
        del request
        return self.reply

    def read_node(self, request: lark_wiki.NodeReadRequest) -> lark_wiki.LarkReply:
        del request
        return self.reply


def replay(recorded: Cassette) -> Replayed:
    """A recording through `lark_wiki.walk_nodes` or the page fetch."""
    reader = _WikiReader(lark_wiki.LarkReply(status=recorded.status, body=recorded.body))
    try:
        if "/nodes" in recorded.request:
            listing = lark_wiki.walk_nodes(reader, space_id=WIKI_SPACE, max_pages=1)
            if not listing.nodes:
                return Replayed(Expect.ABSENT)
            return Replayed(Expect.ANSWERED if listing.complete else Expect.MORE_TO_READ)
        fetch = lark_wiki.page_fetch(lark_wiki.operation_for(), reader, fetched_at=FETCHED_AT)
        result = fetch(
            FetchRequest(
                entity=lark_wiki.WIKI_PAGE, filters=(("token", "wikcnKQ1k3pcuo5uSK4t8Vabcef"),)
            )
        )
    except lark_wiki.LarkWikiRefusedError:
        return Replayed(Expect.REFUSED)
    except lark_wiki.LarkWikiUnreachableError as failed:
        return Replayed(unreachable_or_quota(failed.call_outcome))
    return Replayed(Expect.ANSWERED if result.records else Expect.ABSENT)


def manifest() -> ConnectorManifest:
    from tests.unit import test_lark_wiki

    built: ConnectorManifest = test_lark_wiki.a_manifest()
    return built


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
)
