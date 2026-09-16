"""An S3-compatible store in memory, reached through `httpx.MockTransport`, that checks signatures.

`brain.ops.object_store.S3Backend` takes a transport, and this is the one tests hand it. It answers
the five calls the backend makes, path-style, the way SeaweedFS's gateway does: put, get and delete
an object, and list a bucket in pages with a continuation token. Anything else is a 501.

**It refuses a request whose signature does not verify, and that is the reason it exists rather
than a dictionary behind the protocol.** Every request's `Authorization` is recomputed from what
arrived: the signed headers as sent, the path and query as sent, the region and key the fake was
built with, and a payload hash it computes from the body itself rather than trusting the header.
A backend that signed with the wrong secret, the wrong region, a header it did not send, or a body
hash that disagrees with the body is answered 403 `SignatureDoesNotMatch`, as a real store would.
The recomputation shares `authorization` with the code under test, so the canonical form itself is
held by the AWS examples in `tests/unit/test_object_store_client.py` and not by this.

Nothing here reads a clock or a network.

Task ids: M32.3.2.2
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from brain.ops.object_store import StoreCredential, authorization

_AUTH = re.compile(
    r"^AWS4-HMAC-SHA256 Credential=(?P<access>[^/]+)/(?P<day>\d{8})/(?P<region>[^/]+)/s3/"
    r"aws4_request, SignedHeaders=(?P<signed>[a-z0-9;-]+), Signature=(?P<signature>[0-9a-f]{64})$"
)


def _error(status: int, code: str) -> httpx.Response:
    body = f"<?xml version='1.0'?><Error><Code>{code}</Code><Message>refused</Message></Error>"
    return httpx.Response(
        status, content=body.encode(), headers={"content-type": "application/xml"}
    )


@dataclass
class FakeS3:
    """Buckets of objects, the one key pair it accepts, and a log of what was asked."""

    credential: StoreCredential
    region: str = "us-east-1"
    buckets: dict[str, dict[str, bytes]] = field(default_factory=dict)
    #: Every request that verified, as (method, path, query), in arrival order.
    asked: list[tuple[str, str, str]] = field(default_factory=list)
    #: Objects per listing page, whatever the client asks for. Small, so paging is exercised.
    page: int = 1000
    #: When set, every request fails as a connection that could not be made.
    down: bool = False

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def holding(self, bucket: str, objects: Mapping[str, bytes]) -> FakeS3:
        self.buckets.setdefault(bucket, {}).update(objects)
        return self

    def _verified(self, request: httpx.Request, body: bytes) -> bool:
        found = _AUTH.fullmatch(request.headers.get("authorization", ""))
        if found is None or found["access"] != self.credential.access_key_id:
            return False
        if found["region"] != self.region:
            return False
        claimed = request.headers.get("x-amz-content-sha256", "")
        if claimed != hashlib.sha256(body).hexdigest():
            return False
        names = found["signed"].split(";")
        if "host" not in names or "x-amz-date" not in names:
            return False
        stamp = request.headers.get("x-amz-date", "")
        if not stamp.startswith(found["day"]):
            return False
        at = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        expected = authorization(
            method=request.method,
            path=request.url.path,
            query=list(request.url.params.multi_items()),
            headers={name: request.headers.get(name, "") for name in names},
            payload_sha256=claimed,
            credential=self.credential,
            region=self.region,
            at=at,
        )
        return expected == request.headers["authorization"]

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("the fake store is down", request=request)
        body = request.read()
        if not self._verified(request, body):
            return _error(403, "SignatureDoesNotMatch")
        self.asked.append((request.method, request.url.path, str(request.url.params)))
        bucket, _, key = request.url.path.lstrip("/").partition("/")
        objects = self.buckets.get(bucket)
        if objects is None:
            return _error(404, "NoSuchBucket")
        if not key:
            if request.method == "GET" and request.url.params.get("list-type") == "2":
                return self._list(objects, request.url.params)
            return _error(501, "NotImplemented")
        if request.method == "PUT":
            objects[key] = body
            return httpx.Response(200)
        if request.method == "GET":
            if key not in objects:
                return _error(404, "NoSuchKey")
            return httpx.Response(200, content=objects[key])
        if request.method == "DELETE":
            objects.pop(key, None)
            return httpx.Response(204)
        return _error(501, "NotImplemented")

    def _list(self, objects: Mapping[str, bytes], params: httpx.QueryParams) -> httpx.Response:
        prefix = params.get("prefix", "")
        names = sorted(name for name in objects if name.startswith(prefix))
        start = int(params.get("continuation-token", "0") or "0")
        chunk = names[start : start + min(self.page, int(params.get("max-keys", "1000")))]
        following = start + len(chunk)
        truncated = following < len(names)
        contents = "".join(
            f"<Contents><Key>{name}</Key><Size>{len(objects[name])}</Size></Contents>"
            for name in chunk
        )
        token = f"<NextContinuationToken>{following}</NextContinuationToken>" if truncated else ""
        document = (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'>"
            f"<KeyCount>{len(chunk)}</KeyCount><IsTruncated>{str(truncated).lower()}</IsTruncated>"
            f"{contents}{token}</ListBucketResult>"
        )
        return httpx.Response(200, content=document.encode())
