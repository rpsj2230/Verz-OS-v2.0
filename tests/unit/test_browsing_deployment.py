"""The launcher's compose overlay and the runner image, read as files and held to the design.

`tests/unit/test_compose_networks.py` already holds every composition the product runs to its
network rule, and this overlay is in that set. What is here is what that rule does not know: that
this is the one service with the Docker socket, and what it must therefore not have.

Task ids: M19.1.1, M19.1.6
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import yaml

from brain.browsing.launcher import OVERLAY, WORKER_FILE, overlays_for
from brain.browsing.sandbox import PROXY_ADDRESS, RUNNER_ENTRY, RUNNER_USER
from brain.deployment.requirements import COMPOSE_FILES_FOR, files_for

REPO = Path(__file__).resolve().parents[2]
SOCKET = "/var/run/docker.sock"


def load(name: str) -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load((REPO / name).read_text(encoding="utf-8")) or {}
    return parsed


def launcher() -> dict[str, Any]:
    service: dict[str, Any] = load(OVERLAY)["services"]["browser-launcher"]
    return service


def test_the_launcher_is_the_only_service_in_any_compose_file_with_the_docker_socket() -> None:
    """Whatever mounts the socket is root on the host. Delete this and a second service can be
    given it in passing, and the one argued-for exception becomes a pattern."""
    holders = sorted(
        f"{path.name}: {name}"
        for path in REPO.glob("docker-compose*.yml")
        for name, body in (load(path.name).get("services") or {}).items()
        if any(SOCKET in str(one) for one in (body or {}).get("volumes") or ())
    )

    assert holders == [f"{OVERLAY}: browser-launcher"]


def test_the_launcher_holds_nothing_but_the_socket() -> None:
    """No environment at all, so no database address, vault token or provider key, a read-only
    filesystem, no capabilities and no way to gain any.

    Delete this and one environment line hands the process that can start any container on the
    host the credentials to the rest of the system as well."""
    service = launcher()

    assert "environment" not in service
    assert "env_file" not in service
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["volumes"] == [f"{SOCKET}:{SOCKET}"]
    assert "ports" not in service
    assert service["deploy"]["resources"]["limits"]["memory"]


def test_the_launcher_sits_only_on_an_internal_network() -> None:
    """Delete this and the socket holder can be put on a network with a route out."""
    document = load(OVERLAY)

    assert launcher()["networks"] == ["browser-control"]
    assert document["networks"]["browser-control"] == {"internal": True}


def test_the_worker_keeps_its_own_network_when_it_joins_the_launchers() -> None:
    """A service given a networks key is on only those networks. Delete this and composing the
    overlay silently takes the worker off the network its database is on."""
    assert load(OVERLAY)["services"]["brain-worker"] == {"networks": ["default", "browser-control"]}


def test_the_launcher_names_the_runner_by_the_same_release_it_runs() -> None:
    """One variable selects every container. Delete this and the launcher can be told a different
    image from the one it is, and start runners from another release."""
    service = launcher()
    command = service["command"]
    image_argument = command[command.index("--app-image") + 1]

    assert image_argument == service["image"]
    assert service["image"].startswith("${APP_IMAGE:?")
    assert command[:3] == ["python", "-m", "brain.browsing.launcher"]


def test_the_launchers_health_is_the_daemon_having_gvisor() -> None:
    """Readiness, not liveness. Delete this and the check can become a port probe, which is healthy
    on a host where every run will be refused for want of `runsc`."""
    test = launcher()["healthcheck"]["test"]

    assert test[0] == "CMD"
    assert test[1:4] == ["python", "-m", "brain.browsing.launcher"]
    assert test[-1] == "--check"


def test_the_overlay_is_composed_only_onto_profiles_that_run_the_worker() -> None:
    """Lite has no worker. Delete this and lite with browsing composes a worker with no image."""
    for profile in COMPOSE_FILES_FOR:
        files = files_for(profile)
        assert overlays_for(files) == ((OVERLAY,) if WORKER_FILE in files else ())
    assert overlays_for(files_for("lite")) == ()
    assert overlays_for(files_for("standard")) == (OVERLAY,)


# ------------------------------------------------------------------ the runner image
def test_the_runner_image_pins_playwright_to_one_version_twice_and_runs_as_the_image_user() -> None:
    """The package finds its browsers by version, so the base image and the package must name the
    same one. Delete this and a bump to either leaves a runner whose browser cannot be found.

    Parsed from the instructions rather than searched as text, so the comment above the FROM line
    that names the rule cannot satisfy it."""
    lines = [
        line.strip()
        for line in (REPO / "ops/browser/Dockerfile").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    base = next(line for line in lines if line.startswith("FROM "))
    (base_version,) = re.findall(r"playwright/python:v(\d+\.\d+\.\d+)-", base)
    (package_version,) = re.findall(r"playwright==(\d+\.\d+\.\d+)", " ".join(lines))

    assert base_version == package_version
    assert f"USER {RUNNER_USER}" in lines
    assert f'CMD ["{RUNNER_ENTRY}"]' in lines
    assert any(line.endswith(RUNNER_ENTRY) and line.startswith("COPY ") for line in lines)


def test_the_runner_entry_launches_chromium_through_the_runs_proxy() -> None:
    """Read off the call, not the text. Delete this and the entry can launch Chromium with no proxy,
    which on the run's internal network is a browser that reaches nothing and fails every run as
    though every target were down."""
    tree = ast.parse((REPO / "ops/browser/playwright_browser.py").read_text(encoding="utf-8"))
    launches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "launch"
    ]

    (launch,) = launches
    proxy = next(one.value for one in launch.keywords if one.arg == "proxy")
    assert isinstance(proxy, ast.Dict)
    assert [ast.literal_eval(key) for key in proxy.keys if key is not None] == ["server"]
    assert isinstance(proxy.values[0], ast.Name) and proxy.values[0].id == "PROXY_ADDRESS"
    assert PROXY_ADDRESS.startswith("http://egress:")
