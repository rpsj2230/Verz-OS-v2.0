"""The TypeScript piece and the application agree about the one request between them, and the
piece is a package the canvas can load.

`ops/automation/piece/contract.json` is the single statement of that request. This file holds it
equal to what the application mounts and to what a step may say, and runs the piece's own tests,
so the route, `PieceStep` and the request the piece builds cannot drift apart silently.

**Built and loaded here, not only its request builder.** Until 2026-09-15 `lib/index.ts`
imported an SDK that had never been installed, so nothing compiled, linted or loaded it, and
its property names were the framework's documented shape rather than a checked one. It now
compiles under strict settings against the framework release the canvas image was built with,
and `test/load.test.ts` requires the built package the way that release's engine does and holds
its authentication, its action and its inputs to `contract.json`.

**Skips on a machine without the toolchain, and fails in CI instead.** A laptop with no Node, or
one too old to strip types, is told why and moves on. On a GitHub runner the same condition is
a failure, because a skip there would print a green tick over a piece that went back to never
having been built, which is the state this file was written to end.

Task ids: none
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.automation_routes import TOOL_CALL_PATH
from brain.identity.bearer import BEARER_PREFIX
from brain.ops.automation_owner import CREDENTIAL_PREFIX
from brain.ops.automation_piece import PieceStep

REPO = Path(__file__).resolve().parents[2]
PIECE = REPO / "ops" / "automation" / "piece"
FRAMEWORK = "@activepieces/pieces-framework"

#: The framework release each canvas image was built with, read from
#: `packages/pieces/community/framework/package.json` in the Activepieces source at that tag.
#: For 0.39.5 that is 0.7.42, and 0.7.42 was also the newest framework on the registry when the
#: image was pushed (0.7.43 followed almost a month later), so the two readings agree. A newer
#: framework can declare property types and metadata the older server does not know.
FRAMEWORK_FOR_IMAGE: dict[str, str] = {"0.39.5": "0.7.42"}

#: The first Node release that strips TypeScript types without a flag, which is how the piece's
#: tests run without a separate compiler step for the test files.
STRIPS_TYPES_FROM: tuple[int, int] = (22, 18)

#: An exact version, with no range operator in front of it.
EXACT = re.compile(r"\d+\.\d+\.\d+")


def contract() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((PIECE / "contract.json").read_text(encoding="utf-8"))
    return loaded


def package(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((PIECE / name).read_text(encoding="utf-8"))
    return loaded


def usable_node(*, needs_toolchain: bool) -> str:
    """The Node to run the piece's tests on, or a skip (a failure in CI) saying why not.

    GitHub sets `GITHUB_ACTIONS` on every runner. Read here rather than through configuration
    because it is a property of where the suite is running, not of any install."""
    reason = ""
    node = shutil.which("node")
    if node is None:
        reason = "no node on this machine, so the piece cannot be built or run"
    else:
        stated = subprocess.run(
            [node, "--version"], capture_output=True, text=True, encoding="utf-8", check=False
        ).stdout.strip()
        major, minor = (int(part) for part in stated.lstrip("v").split(".")[:2])
        if (major, minor) < STRIPS_TYPES_FROM:
            reason = f"node {stated} cannot strip types, and the piece's tests need 22.18 or later"
        elif needs_toolchain and not (PIECE / "node_modules" / "typescript").is_dir():
            reason = "the piece's toolchain is not installed; run npm ci in ops/automation/piece"
    if reason:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail(f"{reason}. CI builds the piece rather than skipping it.")
        pytest.skip(reason)
    assert node is not None
    return node


def run_node(node: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [node, *arguments],
        cwd=PIECE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )


def counted(tap: str) -> tuple[int, int]:
    """The pass and fail totals from Node's TAP summary, read from their own lines."""
    passed = re.search(r"^# pass (\d+)$", tap, re.MULTILINE)
    failed = re.search(r"^# fail (\d+)$", tap, re.MULTILINE)
    assert passed is not None and failed is not None, tap
    return int(passed.group(1)), int(failed.group(1))


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


def test_the_framework_is_the_release_the_canvas_image_was_built_with() -> None:
    """The image tag is read from the compose file that runs it, so bumping the canvas without
    re-pinning the framework fails here rather than in a flow. Delete this and the piece can be
    compiled against a framework whose metadata the running server rejects, or silently
    misreads, and the first sign is a piece that installs and then will not open."""
    compose = yaml.safe_load((REPO / "docker-compose.automation.yml").read_text(encoding="utf-8"))
    image, tag = compose["services"]["activepieces"]["image"].rsplit(":", 1)

    assert image == "activepieces/activepieces"
    assert tag in FRAMEWORK_FOR_IMAGE, (
        f"the canvas image is {tag} and no framework release is recorded for it: read "
        "packages/pieces/community/framework/package.json at that tag and pin that version"
    )
    assert package("package.json")["dependencies"] == {FRAMEWORK: FRAMEWORK_FOR_IMAGE[tag]}
    locked = package("package-lock.json")["packages"][f"node_modules/{FRAMEWORK}"]
    assert locked["version"] == FRAMEWORK_FOR_IMAGE[tag]


def test_every_version_the_piece_installs_is_exact_and_locked() -> None:
    """A range resolves afresh on the day somebody builds, so the tarball an owner uploads
    would be a set of packages nobody tested. Delete this and a caret creeps into package.json,
    `npm ci` refuses the stale lock in CI, or worse the lock is regenerated and a newer
    framework ships unnoticed."""
    declared = package("package.json")
    lock = package("package-lock.json")
    pinned = {**declared["dependencies"], **declared["devDependencies"]}

    assert pinned, "the piece declares no dependencies at all"
    assert {
        name: bool(EXACT.fullmatch(version)) for name, version in pinned.items()
    } == dict.fromkeys(pinned, True)
    assert lock["lockfileVersion"] == 3
    root = lock["packages"][""]
    assert root["dependencies"] == declared["dependencies"]
    assert root["devDependencies"] == declared["devDependencies"]
    installed = {path: entry for path, entry in lock["packages"].items() if path}
    assert installed
    assert [path for path, entry in installed.items() if "integrity" not in entry] == []
    # No registry address in the lock, which `.npmrc` arranges: a mirror installs from the same
    # file, and the client independence sweep reads every file under `ops`.
    assert [path for path, entry in installed.items() if "resolved" in entry] == []


def test_the_request_the_piece_builds_passes_its_own_tests() -> None:
    """Runs `test/call.test.ts` on Node's own runner and type stripping. Delete this and
    `call.ts` can build a request `contract.json` does not describe while every assertion above
    still passes."""
    node = usable_node(needs_toolchain=False)

    finished = run_node(node, "--test", "--test-reporter=tap", "test/call.test.ts")

    assert finished.returncode == 0, finished.stdout + finished.stderr
    assert counted(finished.stdout) == (4, 0)


def test_the_piece_builds_and_loads_as_the_engine_loads_it() -> None:
    """Compiles `lib/` under strict settings against the pinned framework, stages the CommonJS
    package the canvas installs, then runs `test/load.test.ts` over the result.

    The build is `package.json`'s own `build` script, asserted rather than retyped, so what this
    runs is what an owner runs before uploading. Delete this and `lib/index.ts` goes back to
    being a file nothing compiles: a renamed framework property, an ES module the engine cannot
    require, or an action whose inputs are not the contract's fields would all reach the canvas
    first."""
    node = usable_node(needs_toolchain=True)
    build = package("package.json")["scripts"]["build"]
    assert build == "node scripts/build.mjs"

    built = run_node(node, "scripts/build.mjs")
    assert built.returncode == 0, built.stdout + built.stderr

    loaded = run_node(node, "--test", "--test-reporter=tap", "test/load.test.ts")
    assert loaded.returncode == 0, loaded.stdout + loaded.stderr
    assert counted(loaded.stdout) == (7, 0)
