"""Lark Wiki's recordings: a node, a page of nodes, a page's permission settings, a page's text,
a refusal inside a 200, and the tenant's minute.

The wiki projects nothing, so no recording here feeds a kept record. The page's text carries a
canary: it is read live for an answer and never kept.

Task ids: M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.connectors import lark_wiki
from brain.connectors.contract import FetchRequest
from brain.connectors.manifest import ConnectorManifest
from brain.ops.idempotency import Verification
from tests.fixtures.cassettes._read_back import answered
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
#: A page's permission settings, v2, read with type=wiki: `permission_public` and its
#: `lock_switch`, which is true once a page stops following its parent. The two addresses below
#: were written from Lark's documentation, not fetched for these recordings (nothing here
#: contacts Lark); lark-cli's own lark-drive reference states the same meaning of lock_switch,
#: true as a page that no longer inherits its parent's permissions.
LARK_PERMISSION_PUBLIC_DOC = (
    "https://open.larksuite.com/document/server-docs/docs/permission/permission-public/get-2"
)
#: One docx document's plain text, `data.content`.
LARK_DOCX_RAW_CONTENT_DOC = (
    "https://open.larksuite.com/document/server-docs/docs/docs/docx-v1/document/raw_content"
)

#: The node every single-page recording is about, and the document behind it.
WIKI_NODE = "wikcnKQ1k3pcuo5uSK4t8Vabcef"
WIKI_DOCUMENT = "doccnzAaODNqykc8g9hOWabcdef"


def permission_settings(*, locked: bool) -> dict[str, object]:
    """The documented permission settings reply for one wiki page, following or restricted."""
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "permission_public": {
                "external_access_entity": "open",
                "security_entity": "anyone_can_view",
                "comment_entity": "anyone_can_view",
                "share_entity": "anyone",
                "manage_collaborator_entity": "collaborator_can_view",
                "link_share_entity": "tenant_readable",
                "copy_entity": "anyone_can_view",
                "lock_switch": locked,
            }
        },
    }


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
        why="The documented listing, and what it does not carry matters: a documented node "
        "carries no permission field, so a listed page is undetermined until its own "
        "permission settings are read, and a title found here is only a candidate.",
        kind=Kind.PAGINATION,
        tools=("lark_wiki.read_page",),
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=LARK_WIKI_LIST_DOC,
    ),
    Cassette(
        cid="LARK-WIKI-200-permission-follows",
        source=SOURCE,
        request=f"GET /open-apis/drive/v2/permissions/{WIKI_NODE}/public?type=wiki",
        status=200,
        body=permission_settings(locked=False),
        why="A page that still follows its parent: lock_switch false is the only setting "
        "that lets the page be answered from at its space's reach.",
        kind=Kind.READ,
        tools=("lark_wiki.read_page",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARK_PERMISSION_PUBLIC_DOC,
    ),
    Cassette(
        cid="LARK-WIKI-200-permission-locked",
        source=SOURCE,
        request=f"GET /open-apis/drive/v2/permissions/{WIKI_NODE}/public?type=wiki",
        status=200,
        body=permission_settings(locked=True),
        why="A page somebody restricted so it no longer follows its parent. The call "
        "answered, and the page, with every page under it, is withheld.",
        kind=Kind.READ,
        tools=("lark_wiki.read_page",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARK_PERMISSION_PUBLIC_DOC,
    ),
    Cassette(
        cid="LARK-WIKI-200-raw-content",
        source=SOURCE,
        request=f"GET /open-apis/docx/v1/documents/{WIKI_DOCUMENT}/raw_content",
        status=200,
        body={
            "code": 0,
            "msg": "success",
            "data": {"content": "CANARY-WIKI-PAGE-TEXT renewals are quoted at the contract rate"},
        },
        why="A page's text, read live for one answer. It carries a canary because it is "
        "exactly what must never be kept, embedded or logged.",
        kind=Kind.READ,
        tools=("lark_wiki.read_page",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARK_DOCX_RAW_CONTENT_DOC,
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

    def read_permission(self, request: lark_wiki.NodeReadRequest) -> lark_wiki.LarkReply:
        del request
        return self.reply

    def read_text(self, request: lark_wiki.TextReadRequest) -> lark_wiki.LarkReply:
        del request
        return self.reply


def replay(recorded: Cassette) -> Replayed:
    """A recording through `lark_wiki.walk_nodes`, the page fetch, or the two live reads."""
    reader = _WikiReader(lark_wiki.LarkReply(status=recorded.status, body=recorded.body))
    try:
        if "/permissions/" in recorded.request:
            lark_wiki.permission_of(reader.read_permission(lark_wiki.NodeReadRequest(WIKI_NODE)))
            return Replayed(Expect.ANSWERED)
        if "/raw_content" in recorded.request:
            text = lark_wiki.text_of(reader.read_text(lark_wiki.TextReadRequest(WIKI_DOCUMENT)))
            return Replayed(Expect.ANSWERED if text.strip() else Expect.ABSENT)
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


def read_back_answer(recorded: Cassette) -> Verification:
    """One recording through Lark Wiki's read-back reading, as the reply Lark sent."""
    return answered(SOURCE, lark_wiki.LarkReply(status=recorded.status, body=recorded.body))


#: How each recording this connector's read-back names is answered. Written here rather than
#: read from the connector, so the expectation and the reading are two accounts that have to
#: agree (`tests/unit/test_write_verification.py`).
READ_BACK: Final[Mapping[str, Verification]] = MappingProxyType(
    {
        "LARK-200-records": Verification.FOUND,
        "LARK-200-code-permission": Verification.INCONCLUSIVE,
        # A wiki node read, which read ABSENT until the reading required has_more.
        "LARK-WIKI-200-node": Verification.INCONCLUSIVE,
        "LARK-WIKI-200-nodes-page": Verification.FOUND,
        "LARK-WIKI-200-code-permission": Verification.INCONCLUSIVE,
        "LARK-WIKI-429": Verification.INCONCLUSIVE,
        # A page's permission settings and its text are not listings, so they say nothing about
        # more.
        "LARK-WIKI-200-permission-follows": Verification.INCONCLUSIVE,
        "LARK-WIKI-200-permission-locked": Verification.INCONCLUSIVE,
        "LARK-WIKI-200-raw-content": Verification.INCONCLUSIVE,
    }
)


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    read_back=READ_BACK,
    read_back_answer=read_back_answer,
    wait_not_in_retry_after="x-ogw-ratelimit-reset",
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
)
