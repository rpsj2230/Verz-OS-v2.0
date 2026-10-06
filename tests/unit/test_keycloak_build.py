"""Keycloak is built once by a one-shot, and the server starts on that build and never rebuilds.

`docker-compose.keycloak.yml` says why: the build, run inside the server's first start, was killed
by the kernel in the server's cgroup on every fresh install the browser harness started. These
tests hold the three things the arrangement rests on, each of which fails quietly when broken:

- the server and the build are given the same build-time options, or `--optimized` starts the
  server on the build's options rather than its own;
- the server waits for the build and reads it from the volume the build wrote;
- the build skips itself only when the distribution and every build-time option are what it was
  built for, run here as the script it is, against a stand-in for `kc.sh`.

Task ids: none
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.keycloak.yml"
BUILD = "keycloak-build"
SERVER = "keycloak"
QUARKUS = "/opt/keycloak/lib/quarkus"

#: The Keycloak 26 options read at build time, as environment variables. A build-time option set
#: on the server and not on the build is one `--optimized` ignores, with only a warning to say so.
BUILD_TIME_OPTIONS = frozenset(
    {
        "KC_DB",
        "KC_HEALTH_ENABLED",
        "KC_METRICS_ENABLED",
        "KC_FEATURES",
        "KC_FEATURES_DISABLED",
        "KC_VAULT",
        "KC_CACHE",
        "KC_CACHE_STACK",
        "KC_TRANSACTION_XA_ENABLED",
        "KC_HTTP_RELATIVE_PATH",
    }
)


def _services() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    return loaded


def _build_time(service: dict[str, Any]) -> dict[str, str]:
    environment = service.get("environment") or {}
    return {name: str(value) for name, value in environment.items() if name in BUILD_TIME_OPTIONS}


def test_the_server_and_its_build_are_given_the_same_build_time_options() -> None:
    """Every build-time option on the server is on the build, with the same value, and back.

    Delete this and an option added to the server alone (a feature switched on, say) is silently
    not in the build the server starts on, because `--optimized` uses what was built.
    """
    services = _services()
    server, build = _build_time(services[SERVER]), _build_time(services[BUILD])
    assert {"KC_DB", "KC_HEALTH_ENABLED"} <= set(server)
    assert server == build


def test_the_server_starts_on_the_build_and_never_builds_itself() -> None:
    """`--optimized`, after the build has completed, reading the volume the build wrote.

    Delete this and the server can lose its wait or its mount, and `--optimized` then starts it on
    the image's own build for a development file store, which is the restart loop of 2026-09-07,
    or the flag can be dropped and the build goes back inside the server's first start.
    """
    services = _services()
    server, build = services[SERVER], services[BUILD]
    assert "--optimized" in server["command"]
    assert server["depends_on"][BUILD] == {"condition": "service_completed_successfully"}
    mounted = {str(volume).split(":")[1]: str(volume).split(":")[0] for volume in build["volumes"]}
    served = {str(volume).split(":")[1]: str(volume).split(":")[0] for volume in server["volumes"]}
    assert mounted[QUARKUS] == served[QUARKUS] == BUILD
    assert build["image"] == server["image"]
    assert build["restart"] == "no"


def _script() -> str:
    """The build's script as compose hands it to bash: `$$` is compose's escape for `$`."""
    return str(_services()[BUILD]["command"][0]).replace("$$", "$")


def _calls(root: Path) -> list[str]:
    """Every `kc.sh` invocation the stand-in recorded, one line each."""
    ledger = root / "calls"
    return ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []


def _run(root: Path, options: dict[str, str]) -> tuple[str, int]:
    """Run the script under `root` in place of /opt/keycloak. Returns its output and builds made."""
    script = _script().replace("/opt/keycloak", str(root))
    bin_dir = root / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    if shutil.which("sha256sum") is None:
        shim = bin_dir / "sha256sum"
        shim.write_text('#!/bin/sh\nexec shasum -a 256 "$@"\n', encoding="utf-8", newline="\n")
        shim.chmod(0o755)
    environment = {**os.environ, **options, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    done = subprocess.run(
        ["bash", "-c", script],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    builds = sum(1 for line in _calls(root) if line.split()[:1] == ["build"])
    return done.stdout, builds


@pytest.fixture
def keycloak(tmp_path: Path) -> Path:
    """A stand-in distribution: a jar list, an empty build directory, and a `kc.sh` that counts."""
    (tmp_path / "lib" / "lib" / "main").mkdir(parents=True)
    (tmp_path / "lib" / "lib" / "main" / "org.keycloak.keycloak-core-26.0.8.jar").touch()
    (tmp_path / "lib" / "quarkus").mkdir()
    kc = tmp_path / "bin" / "kc.sh"
    kc.parent.mkdir()
    kc.write_text(f'#!/bin/sh\necho "$*" >> "{tmp_path}/calls"\n', encoding="utf-8", newline="\n")
    kc.chmod(0o755)
    return tmp_path


OPTIONS = {"KC_DB": "postgres", "KC_HEALTH_ENABLED": "true", "KC_VAULT": "file"}


def test_the_build_runs_once_and_a_second_deploy_with_nothing_changed_skips_it(
    keycloak: Path,
) -> None:
    """The first run builds and writes its marker; the second finds the marker and builds nothing.

    Delete this and the skip can stop matching (a marker written differently from how it is read),
    so every release pays the build's memory and minute again, with nothing failing.
    """
    first, built = _run(keycloak, OPTIONS)
    assert built == 1
    assert "built, peak" in first
    assert [line.split()[0] for line in _calls(keycloak)] == ["build"]
    second, built = _run(keycloak, OPTIONS)
    assert built == 1
    assert "already built" in second
    assert len(_calls(keycloak)) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"KC_DB": "mariadb"},
        {"KC_HEALTH_ENABLED": "false"},
        {"KC_VAULT": "keystore"},
    ],
)
def test_a_changed_build_time_option_builds_again(keycloak: Path, change: dict[str, str]) -> None:
    """A deploy that changes any build-time option the build reads gets a new build.

    Delete this and the marker can leave an option out, so a deploy that changes it keeps starting
    the server on the old build, which `--optimized` does without complaint.
    """
    _run(keycloak, OPTIONS)
    _, built = _run(keycloak, {**OPTIONS, **change})
    assert built == 2


def test_a_new_keycloak_distribution_builds_again(keycloak: Path) -> None:
    """An upgraded image, whose jar list differs, gets a new build with the same options.

    Delete this and the marker can stop naming the distribution, so an upgraded Keycloak starts on
    the previous version's build.
    """
    _run(keycloak, OPTIONS)
    (keycloak / "lib" / "lib" / "main" / "org.keycloak.keycloak-core-26.0.8.jar").rename(
        keycloak / "lib" / "lib" / "main" / "org.keycloak.keycloak-core-26.1.0.jar"
    )
    _, built = _run(keycloak, OPTIONS)
    assert built == 2
