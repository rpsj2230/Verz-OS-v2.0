"""The record matcher as it would be deployed, held to what the code declares about it.

`docs/needs-rupash.md` item 55 put Splink and DuckDB in an image of their own, so the matcher
is four files beside the application's: a dependency set, its lock, a Dockerfile and a compose
file. Each carries a figure or a rule some Python module also holds, and each is only safe while
something compares the two.

**None of this has been built or started.** There is no Docker on the machine these were
written on. The job ran once in a throwaway environment holding exactly this lock's packages;
these tests are about the files, and a green run here says the files agree with the code and
nothing about whether the image builds. It is expected not to, today: its licence step refuses
numpy's declared licence expression until the owner decides about it.

Task ids: M14.4.1
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import yaml

from brain.ops.wiring import Wiring, component, components_for
from brain.resolution import matcher

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.matcher.yml"
DOCKERFILE = REPO / "matcher" / "Dockerfile"


def _service() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    service: dict[str, Any] = loaded["services"][matcher.MATCHER_COMPONENT]
    return service


def _lock(path: Path) -> dict[str, dict[str, Any]]:
    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    return {str(one["name"]): one for one in parsed["package"]}


# ------------------------------------------------------------------ the compose file
def test_the_container_is_sized_to_the_component_it_is_budgeted_as() -> None:
    """`brain.ops.wiring` decides what the job may take and the profile's arithmetic is computed
    from it, and DuckDB's ceiling is derived from the same figure. More here is memory no budget
    counted and a DuckDB ceiling computed from a limit the container does not have.

    Delete this and the file can be raised to make a large export fit while every budget and
    the DuckDB ceiling keep describing the old container."""
    limit = _service()["deploy"]["resources"]["limits"]["memory"]

    assert int(str(limit).rstrip("M")) == component(matcher.MATCHER_COMPONENT).memory_mib


def test_the_profiles_in_the_file_match_the_profiles_the_component_is_budgeted_in() -> None:
    """Both directions. A compose profile the component lacks starts a job no arithmetic
    includes; a component profile the file lacks costs memory for a job that never runs.

    Delete this and `full`'s figure and `full`'s deployment can describe two different hosts."""
    from_file = set(_service()["profiles"])
    from_module = {
        profile
        for profile in ("lite", "standard", "full")
        if matcher.MATCHER_COMPONENT in {one.name for one in components_for(profile)}
    }

    assert from_file == from_module == {"full"}


def test_the_job_holds_no_database_connection_and_joins_only_an_internal_network() -> None:
    """**The structural half of "it suggests and never merges".** No environment value names a
    database, the component is wired to none, and the one network it joins is internal, so the
    records in the export have no route off the host and there is nothing to merge into.

    Delete this and a `DATABASE_URL` added "for logging" is the connection a merge needs."""
    service = _service()
    loaded = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    environment = {
        str(key): str(value) for key, value in (service.get("environment") or {}).items()
    }

    assert component(matcher.MATCHER_COMPONENT).wiring is Wiring.NONE
    assert not any("postgres" in value.lower() for value in environment.values()), environment
    assert not any("DATABASE" in key or "QUEUE" in key for key in environment), environment
    assert service["networks"] == ["matcher"]
    assert loaded["networks"]["matcher"]["internal"] is True
    assert "ports" not in service


def test_the_export_is_mounted_read_only_where_the_job_reads_it() -> None:
    """The evidence cannot be changed by the job asked about it, and the command points at the
    mount the file declares rather than at a path somebody typed differently.

    Delete this and the `:ro` can be dropped, and a job with write access to its own input
    produces suggestions nobody can reproduce."""
    service = _service()
    mounts = [str(one) for one in service["volumes"]]
    command = [str(one) for one in service["command"]]

    assert f"matcher-exports:{matcher.DEFAULT_EXPORT.parent}:ro" in mounts
    assert command[:3] == ["python", "-m", "brain.resolution.splink_job"]
    assert command[command.index("--export") + 1] == str(matcher.DEFAULT_EXPORT)
    assert command[command.index("--suggestions") + 1] == str(matcher.DEFAULT_SUGGESTIONS)
    suggestions_mount = next(one for one in mounts if one.startswith("matcher-suggestions:"))
    assert not suggestions_mount.endswith(":ro")


def test_the_image_is_required_and_the_job_is_never_restarted() -> None:
    """No image is published, so none is defaulted; and a job restarted on failure re-reads the
    export it already matched and is refused by its own output, which is a loop with a log line.

    Delete this and `restart: unless-stopped` is copied in from a service beside it."""
    service = _service()

    assert str(service["image"]).startswith("${MATCHER_IMAGE:?"), service["image"]
    assert service["restart"] == "no"


# ------------------------------------------------------------------ the dependency set
def test_the_matcher_lock_pins_the_two_packages_its_project_declares() -> None:
    """The versions the real run used are the versions the image installs, and the application
    is a dependency by path rather than a copy.

    Delete this and the lock can be regenerated against a newer Splink whose comparison-vector
    numbering nobody has checked against `cascade.compare`."""
    project = tomllib.loads((REPO / "matcher" / "pyproject.toml").read_text(encoding="utf-8"))
    declared = dict(one.split("==") for one in project["project"]["dependencies"] if "==" in one)
    locked = _lock(REPO / "matcher" / "uv.lock")

    assert declared == {"splink": "4.0.17", "duckdb": "1.5.5"}
    assert {name: locked[name]["version"] for name in declared} == declared
    assert project["tool"]["uv"]["sources"]["verz-brain"] == {"path": "..", "editable": False}


def test_the_gpl_package_splink_declares_is_never_installed() -> None:
    """Splink 4.0.17 declares igraph, which is GPL, and never imports it. The override leaves it
    in the lock under a marker that is never true, which is what `uv sync` reads.

    Delete this and a regenerated lock without the override installs a licence the application
    refuses into an image handed to a client."""
    locked = _lock(REPO / "matcher" / "uv.lock")
    splink_needs = {one["name"]: one for one in locked["splink"]["dependencies"]}
    manifest = tomllib.loads((REPO / "matcher" / "uv.lock").read_text(encoding="utf-8"))["manifest"]

    assert splink_needs["igraph"].get("marker") == "sys_platform == 'never'"
    assert {"name": "igraph", "marker": "sys_platform == 'never'"} in manifest["overrides"]
    assert "marker" not in splink_needs["duckdb"], "the positive half: a real dependency has none"


def test_every_package_both_locks_hold_is_at_the_same_version() -> None:
    """The matcher runs the application's code, so it has to run it on the application's
    libraries. Two locks resolved on different days drift, and the first time they did here six
    packages differed, SQLAlchemy among them.

    Delete this and the matcher image imports a different ORM from the one the application was
    tested with, and nothing notices until a model definition behaves differently."""
    application = _lock(REPO / "uv.lock")
    job = _lock(REPO / "matcher" / "uv.lock")
    shared = sorted(set(application) & set(job) - {"verz-brain"})

    assert len(shared) > 50, "the locks share almost nothing, so one of them was misread"
    drift = [
        (name, application[name]["version"], job[name]["version"])
        for name in shared
        if application[name]["version"] != job[name]["version"]
    ]
    assert drift == []


# ------------------------------------------------------------------ the image definition
def test_the_image_installs_the_matcher_lock_checks_licences_and_runs_the_job() -> None:
    """The three lines that make the image what item 55 decided: the matcher's lock rather than
    the application's, the application's licence rule over the result, and the job as the
    command rather than the server.

    Delete this and the Dockerfile can install from `uv.lock` at the root, which is an image
    without Splink that fails at its first import."""
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    runs = " ".join(line.strip() for line in lines)
    commands = [line.removeprefix("CMD").strip() for line in lines if line.startswith("CMD")]

    assert "uv sync --project matcher --locked --no-dev --no-editable" in runs
    assert "-m brain.resolution.splink_job --check-licences" in runs
    assert runs.index("uv sync --project matcher") < runs.index("--check-licences")
    assert json.loads(commands[-1]) == ["python", "-m", "brain.resolution.splink_job"]
