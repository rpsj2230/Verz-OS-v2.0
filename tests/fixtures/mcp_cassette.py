"""The recorded MCP exchange, and a server that replays one of its conversations exactly.

`tests/fixtures/cassettes/mcp_exchange.json` holds four conversations with one MCP server, each
every request the client sends in order, with its headers, and the answer the server gave. The
player answers the n-th request with the n-th recorded answer only when the request is the n-th
recorded request, body and headers both; a request that differs is answered 400 and kept in
`mismatches`, rather than raised, because the product catches a failure broadly and an assertion
inside a fake would be read as a shape it disagreed with.

`{key}` in a recorded header stands for the key the player was handed, so the recording holds no
key and the replay still proves the leased key was the one sent.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from brain.ops.connector_sync_run import SourceAnswer

CASSETTE: Final = Path(__file__).resolve().parent / "cassettes" / "mcp_exchange.json"


def recorded() -> dict[str, Any]:
    """The whole recording, decoded."""
    decoded: dict[str, Any] = json.loads(CASSETTE.read_text(encoding="utf-8"))
    return decoded


def conversation(name: str) -> list[dict[str, Any]]:
    """One recorded conversation, request by request."""
    found: list[dict[str, Any]] = recorded()["conversations"][name]
    return found


@dataclass
class CassettePlayer:
    """`SourcePoster` replaying one recorded conversation, request by request. No socket."""

    exchanges: list[dict[str, Any]]
    key: str = field(repr=False)
    at: int = 0
    mismatches: list[str] = field(default_factory=list)
    sent: list[Mapping[str, Any]] = field(default_factory=list)

    def post(
        self,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        body: bytes,
        max_bytes: int,
    ) -> SourceAnswer:
        del url, address, max_bytes
        if self.at >= len(self.exchanges):
            self.mismatches.append(f"request {self.at + 1} was not recorded")
            return SourceAnswer(status=400, headers={}, body=b"")
        expected = self.exchanges[self.at]
        self.at += 1
        message = json.loads(body)
        self.sent.append(message)
        if message != expected["request"]["body"]:
            self.mismatches.append(f"request {self.at} body differs from the recording")
            return SourceAnswer(status=400, headers={}, body=b"")
        wanted = {
            name.lower(): value.replace("{key}", self.key)
            for name, value in expected["request"]["headers"].items()
        }
        given = {name.lower(): value for name, value in headers.items()}
        if given != wanted:
            self.mismatches.append(f"request {self.at} headers differ from the recording")
            return SourceAnswer(status=400, headers={}, body=b"")
        answer = expected["response"]
        return SourceAnswer(
            status=answer["status"],
            headers=dict(answer["headers"]),
            body=answer["body"].encode("utf-8"),
        )

    def done(self) -> bool:
        """Whether every recorded request was sent, and nothing else."""
        return self.at == len(self.exchanges) and not self.mismatches
