"""The TypeScript piece and the application agree about the one request between them.

`ops/automation/piece/contract.json` is the single statement of that request. This file holds it
equal to what the application mounts and to what a step may say, and runs the piece's own tests
on the Node that is here, so the route, `PieceStep` and the request the piece builds cannot drift
apart silently.

**What is not tested here, and cannot be.** `src/index.ts` imports
`@activepieces/pieces-framework`, which is not installed, and building a piece for Activepieces is
that project's toolchain. Nothing in this repository compiles, lints or loads it; the request it
sends is `call.ts`'s, and that is what runs.

Task ids: none
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.automation_routes import TOOL_CALL_PATH
from brain.identity.bearer import BEARER_PREFIX
from brain.ops.automation_owner import CREDENTIAL_PREFIX
from brain.ops.automation_piece import PieceStep

REPO = Path(__file__).resolve().parents[2]
PIECE = REPO / "ops" / "automation" / "piece"


def contract() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((PIECE / "contract.json").read_text(encoding="utf-8"))
    return loaded


def test_the_piece_calls_the_path_and_method_the_application_mounts() -> None:
    """Read from the generated document rather than from the constant alone, so a route that
    was renamed, or never mounted, fails here. Delete this and the piece posts to a path that
    answers 404 to every step, which reads as every tool being unavailable."""
    stated = contract()
    document = create_app(Settings(env="development")).openapi()["paths"]

    assert stated["path"] == f"{API_PREFIX}{TOOL_CALL_PATH}"
    assert stated["method"].lower() in document[stated["path"]]


def test_the_piece_sends_exactly_the_fields_a_step_may_say() -> None:
    """Delete this and the piece can grow a field `PieceStep` refuses, and every step fails, or
    `PieceStep` can grow one the piece never sends."""
    assert sorted(contract()["body_fields"]) == sorted(PieceStep.model_fields)


def test_the_piece_presents_the_automation_credential_as_a_bearer() -> None:
    """Delete this and the piece can send its credential under a scheme or prefix the route
    parses as malformed."""
    stated = contract()

    assert stated["credential_header"] == "authorization"
    assert stated["credential_scheme"].lower() == BEARER_PREFIX
    assert stated["credential_prefix"] == CREDENTIAL_PREFIX


def test_the_request_the_piece_builds_passes_its_own_tests() -> None:
    """Runs `test/call.test.ts` on Node's own runner and type stripping. Skips where there is no
    Node, and says so. Delete this and `call.ts` can build a request `contract.json` does not
    describe while every assertion above still passes."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("no node on this machine, so the piece's request builder cannot be run")

    finished = subprocess.run(
        [node, "--test", "test/call.test.ts"],
        cwd=PIECE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )

    assert finished.returncode == 0, finished.stdout + finished.stderr
    assert "fail 0" in finished.stdout
    assert "pass 4" in finished.stdout
