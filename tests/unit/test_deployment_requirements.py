"""The server each profile needs, held to the compose files it is computed from.

Every figure here is asserted against something outside itself: the memory against the parsed
compose documents, the cores and the disk against pinned numbers that move when either ratio
does, the connection ceiling against `brain.ops.connections` and against the `command:` in the
compose file that sets it. A specification that recomputed its own constants would be green
for every value they could hold, which is the trap CLAUDE.md records about the retry
constant that dropped from three hundred seconds to one and passed both its tests.

The exact per-profile figures are pinned deliberately. They are expected to change when the
deployment changes, and that failure is the notification: a service added without a memory
limit, or a profile that quietly grew a container, both show up here as a number that moved.

Task ids: M42.2.1, M42.2.2
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.requirements import (
    COMPOSE_FILES_FOR,
    CONTAINERS_PER_CPU,
    DATA_GIB,
    IMAGE_GIB,
    MIB_PER_CPU,
    RUNTIME_REQUIREMENTS,
    Requirement,
    RequirementError,
    ServerSpec,
    connection_arithmetic,
    exposed_ports,
    files_for,
    images_in,
    profiles_by_size,
    published_ports,
    spec_for,
)
from brain.ops.compose import components_with_no_service, deployment_mib, host_mib_for
from brain.ops.connections import DATABASES, POSTGRES_RESERVED_CONNECTIONS, headroom_on
from brain.ops.wiring import HOST_RESERVE_MIB, PROFILES, WiringError

REPO = Path(__file__).resolve().parents[2]

#: What each profile needs, pinned. Memory is computed from the files; cores and disk are the
#: two ratios applied to them. A change to any of the three fails here with the profile named.
#:
#: Standard and full each lost 2 GiB of disk on 2026-09-09, and the deployment did not get
#: smaller. The realm importer is built from this repository and runs the same image as the
#: application, and it selected that image through `BRAIN_IMAGE` while the application
#: selected it through `APP_IMAGE`. `images_in` counts distinct references, so two names for
#: one pull were two pulls, and the figure a client sized a disk against included a download
#: that never happens. Unifying the variable is what let it dedupe.
EXPECTED: dict[str, tuple[int, int, int, int]] = {
    # profile: (memory MiB, containers, cores, disk GiB)
    "lite": (3968, 4, 2, 28),
    "standard": (9920, 12, 5, 36),
    "full": (12864, 19, 7, 48),
}


def parsed(names: tuple[str, ...]) -> dict[str, Any]:
    """The named compose files, parsed. `yaml.safe_load` in the test, for the reason
    `brain.ops.compose` gives: what is checked is the deployment rather than a copy of it."""
    return {name: yaml.safe_load((REPO / name).read_text(encoding="utf-8")) for name in names}


def files_of(profile: str) -> dict[str, Any]:
    return parsed(files_for(profile))


# --- the file list per profile ---------------------------------------------------------


def test_every_profile_names_files_that_exist_and_parse() -> None:
    """`COMPOSE_FILES_FOR` is a declaration, and one naming a file nobody wrote would make
    every figure below describe a smaller deployment than the profile runs, in the direction
    that reads as a machine being cheaper than it is.

    Delete this and a renamed compose file silently shrinks a server specification."""
    for profile in PROFILES:
        for name in files_for(profile):
            assert (REPO / name).is_file(), f"{profile} names {name}, which is missing"
        assert files_of(profile), f"{profile} composes nothing"


def test_the_full_profile_reuses_the_compose_modules_declaration_rather_than_copying_it() -> None:
    """`brain.ops.compose.FULL_PROFILE_FILES` is already the declaration of what a full
    install composes, already checked from the other side by `components_with_no_service`. A
    second list here would be a second answer to one question, and the one that would be wrong
    is whichever nobody updated.

    Delete this and the two lists drift, with the server specification computed from the stale
    one."""
    from brain.ops.compose import FULL_PROFILE_FILES

    assert COMPOSE_FILES_FOR["full"] is FULL_PROFILE_FILES


def test_a_profile_nobody_declared_is_refused_rather_than_composing_nothing() -> None:
    """A typo in a deployment variable would otherwise select no files, cost nothing, and
    report a server requirement of the host reserve alone, which looks like a small install
    rather than like a mistake.

    Delete this and `spec_for("lte")` answers with a number."""
    with pytest.raises(WiringError, match="unknown profile"):
        files_for("lte")


def test_the_standard_and_full_profiles_still_budget_a_component_with_no_service() -> None:
    """The first of the four reasons there is no aggregate compose file, asserted here as
    well because it is also the reason a one-command install of these two profiles cannot
    complete: the memory is spent and the container cannot be started.

    This test is expected to fail when somebody writes the missing service, and that failure
    is the notification. Delete it and the specification claims a profile is installable
    while one of its components has nothing to start."""
    for profile in ("standard", "full"):
        findings = components_with_no_service(profile, files_of(profile))
        assert len(findings) == 1, findings
        assert "presidio-analyzer" in findings[0]

    assert components_with_no_service("lite", files_of("lite")) == ()


def test_the_sizing_table_a_client_reads_says_what_the_compose_files_say() -> None:
    """**The figures in `install.md` were not checked against anything until 2026-09-09.**

    They are what somebody buys a server against, and they had been written by hand from a
    run of `spec_for` on the day the document was written. Two of the four disk figures went
    stale the same day the realm importer stopped being counted as a second pull, and nothing
    would have said so: the deployment tests all read the compose files, and the document is
    the one surface that does not.

    This is the shape the operations chapter had a week earlier, where a checked table
    replaced three prose counts of "twelve" that were one out. A number in a document of
    record is worse than no number, because a reader takes it for the current position.

    Delete this and the sizing table drifts from the deployment with the tests still green,
    and the reader who notices is the one whose disk filled."""
    table = (REPO / "docs" / "install" / "install.md").read_text(encoding="utf-8")
    rows = {
        one.split("|")[1].strip().strip("`"): one
        for one in table.splitlines()
        if one.startswith("| `") and "GiB" in one
    }

    assert sorted(rows) == sorted(EXPECTED), "every profile has a row and no row is invented"
    for profile, row in rows.items():
        memory, containers, cores, disk = EXPECTED[profile]
        cells = [one.strip() for one in row.split("|")]
        assert f"{memory} MiB" in cells, f"{profile}: memory"
        assert f"{cores}" in cells, f"{profile}: cores"
        assert f"{disk} GiB" in cells, f"{profile}: disk"
        assert f"{containers}" in cells, f"{profile}: containers"


# --- the specification -----------------------------------------------------------------


@pytest.mark.parametrize("profile", sorted(EXPECTED))
def test_the_specification_for_each_profile_is_what_its_compose_files_say(profile: str) -> None:
    """The four figures, pinned. Memory is asserted against `host_mib_for` as well as against
    the pin, so this fails both when the deployment changes and when this module stops asking
    the compose module.

    Delete this and a container added without a memory limit, or a ratio edited to make a
    profile look affordable, both pass unnoticed."""
    files = files_of(profile)
    memory, containers, cores, disk = EXPECTED[profile]
    spec = spec_for(profile, files)

    assert spec.memory_mib == memory == host_mib_for(profile, files)
    assert spec.containers == containers
    assert spec.cpus == cores
    assert spec.disk_gib == disk


@pytest.mark.parametrize("profile", sorted(EXPECTED))
def test_the_cores_and_the_disk_follow_the_ratios_they_are_derived_from(profile: str) -> None:
    """The pinned figures above catch a ratio that moved. This catches the other direction:
    a figure that stopped being derived at all. Both terms of the core count are asserted,
    because a profile of many small containers is under-counted by the memory term alone.

    Delete this and `cpus` could be a constant that happens to equal today's arithmetic."""
    files = files_of(profile)
    spec = spec_for(profile, files)

    assert spec.cpus * MIB_PER_CPU >= spec.memory_mib
    assert spec.cpus * CONTAINERS_PER_CPU >= spec.containers
    assert spec.disk_gib == len(images_in(files)) * IMAGE_GIB + DATA_GIB


def test_the_memory_figure_is_larger_than_what_the_containers_reserve() -> None:
    """A specification that quoted only the sum of the compose limits would describe a machine
    with nothing left for the kernel, the docker daemon or the session an operator needs in
    order to fix whatever went wrong. `host_mib_for` adds that reserve and the components the
    profile budgets but cannot start.

    Delete this and the recommended server is exactly full on the day it is bought."""
    files = files_of("lite")
    spec = spec_for("lite", files)
    assert spec.memory_mib == deployment_mib(files) + HOST_RESERVE_MIB


def test_the_profiles_are_ordered_by_the_machine_they_need() -> None:
    """The question a reader arrives with is "what fits on the machine I have", and an answer
    they have to sort themselves is one they sort by the name of the profile, which is
    alphabetical and puts `full` first.

    Delete this and the smallest profile stops being the first thing anybody reads."""
    ordered = profiles_by_size({one: files_of(one) for one in PROFILES})
    assert [one.profile for one in ordered] == ["lite", "standard", "full"]


def test_a_specification_with_a_zero_in_it_is_refused_rather_than_reported() -> None:
    """This is the number somebody buys a machine against. A zero anywhere in it reads as "no
    requirement" rather than as a costing that did not happen, and the four fields fail for
    four different reasons, so each is refused separately with its own sentence.

    Delete this and a profile whose files failed to parse is reported as needing nothing."""
    for field in ("memory_mib", "containers", "cpus", "disk_gib"):
        values: dict[str, Any] = {
            "profile": "lite",
            "memory_mib": 4096,
            "containers": 4,
            "cpus": 2,
            "disk_gib": 28,
        }
        values[field] = 0
        with pytest.raises(RequirementError):
            ServerSpec(**values)

    with pytest.raises(WiringError, match="unknown profile"):
        ServerSpec(profile="tiny", memory_mib=1, containers=1, cpus=1, disk_gib=1)


def test_the_notes_say_which_figures_were_measured_and_which_are_ratios() -> None:
    """A reader handed "7 cores" cannot tell a measurement from a judgement, and the two
    deserve different amounts of trust on the day the machine turns out to be too small.

    Delete this and the ratios read as measurements, which is the failure `brain.ops.wiring`
    calls false precision."""
    notes = spec_for("full", files_of("full")).notes()
    assert "(measured:" in notes
    assert notes.count("a ratio:") == 2


# --- ports -----------------------------------------------------------------------------


@pytest.mark.parametrize("profile", sorted(EXPECTED))
def test_no_profile_publishes_a_port_to_the_host(profile: str) -> None:
    """The finding, pinned. Every service in this repository uses `expose` and none uses
    `ports`, so a server that has run the install to completion answers on nothing from
    outside its own docker network. That makes the reverse proxy a requirement of the install
    rather than an optional extra, and no compose file declares one.

    This test is expected to fail on the day somebody publishes a port, and that failure is
    the notification. Delete it and the install is documented as complete while the console is
    reachable from nowhere."""
    assert published_ports(files_of(profile)) == ()


def test_the_internal_ports_are_readable_per_service() -> None:
    """The other half of M42.2.2: a firewall and a proxy are configured against the ports that
    exist, and reading them out of the deployment is the only way that list stays true.

    Delete this and the port requirements are a hand-written list that is wrong the first time
    somebody adds a service."""
    exposed = exposed_ports(files_of("lite"))
    assert exposed["db"] == ("5432",)
    assert exposed["cache"] == ("6379",)
    assert "app" not in exposed, "the application exposes nothing and is reached by the proxy"


# --- the connection arithmetic ---------------------------------------------------------


def test_the_connection_arithmetic_is_reported_for_the_databases_a_profile_deploys() -> None:
    """M42.2.1 names the connection arithmetic explicitly. It exists in
    `brain.ops.connections` and had never been reported per profile, so a client sizing a
    machine had the memory figure and nothing about the ceiling that actually stops an
    install: a database admitting a hundred connections with a pooler holding twenty of them.

    Delete this and a profile that deploys Keycloak is specified without the second database
    it runs."""
    lite = connection_arithmetic(files_of("lite"))
    assert len(lite) == 1
    assert lite[0].startswith("db: 100 connections")
    assert f"{POSTGRES_RESERVED_CONNECTIONS} reserved" in lite[0]
    assert f"{headroom_on('db')} spare" in lite[0]

    full = connection_arithmetic(files_of("full"))
    assert len(full) == 2
    assert any(one.startswith("keycloak-db: 30 connections") for one in full)


def test_the_ceiling_in_the_compose_command_and_the_one_in_the_budget_are_compared() -> None:
    """Two copies of one number, and the whole value of the budget is that it stops agreeing
    with the deployment when somebody edits the file. Reported as drift rather than raised,
    because which of the two is right is a decision about the server.

    Delete this and `max_connections` can be lowered in the compose file while every figure
    in the budget goes on describing the old one."""
    files = files_of("lite")
    assert all("describing a different server" not in one for one in connection_arithmetic(files))

    # The same documents with the server's own ceiling edited underneath the budget.
    edited = yaml.safe_load(yaml.safe_dump(files["docker-compose.lite.yml"]))
    edited["services"]["db"]["command"] = "postgres -c max_connections=40"
    drifted = connection_arithmetic({"docker-compose.lite.yml": edited})
    assert len(drifted) == 1
    assert "the compose command says 40" in drifted[0]


def test_a_database_that_sets_no_ceiling_in_its_command_is_reported_without_drift() -> None:
    """A service with no `command:` at all, and one whose command sets other things, both mean
    "this deployment does not state a ceiling here". Reporting drift for a number nobody wrote
    would make every profile look inconsistent with its own budget.

    Delete this and the absence of a setting reads as a disagreement."""
    files = files_of("lite")
    edited = yaml.safe_load(yaml.safe_dump(files["docker-compose.lite.yml"]))
    del edited["services"]["db"]["command"]
    assert (
        "describing a different server"
        not in connection_arithmetic({"docker-compose.lite.yml": edited})[0]
    )

    edited["services"]["db"]["command"] = ["postgres", "-c", "shared_buffers=512MB"]
    assert (
        "describing a different server"
        not in connection_arithmetic({"docker-compose.lite.yml": edited})[0]
    )


def test_a_database_this_profile_does_not_deploy_is_not_in_its_specification() -> None:
    """`brain.ops.connections.DATABASES` holds every PostgreSQL on the deployment host,
    including one a lite install never runs. A specification listing it would be describing a
    different install, and the reader would size a machine for a container that is not there.

    Delete this and every profile is specified as if it ran Keycloak."""
    names = {one.name for one in DATABASES}
    assert "keycloak-db" in names
    assert all("keycloak-db" not in one for one in connection_arithmetic(files_of("lite")))


# --- the runtime requirements ----------------------------------------------------------


def test_every_runtime_requirement_says_what_breaks_without_it() -> None:
    """A requirement whose reason nobody wrote down is one that gets waived by the person
    under the most time pressure, at two in the morning, on a client's server. It is the same
    rule `Component.ready_when` and `brain.install.Setting.meaning` are held to.

    Delete this and the list becomes a set of version numbers nobody can argue with or for."""
    assert RUNTIME_REQUIREMENTS
    for one in RUNTIME_REQUIREMENTS:
        assert one.what.strip()
        assert len(one.why.split()) >= 8, f"{one.what} has a reason nobody could act on"

    for empty in ("", " "):
        with pytest.raises(RequirementError, match="no reason"):
            Requirement(what="docker", minimum="", why=empty)
        with pytest.raises(RequirementError, match="no name"):
            Requirement(what=empty, minimum="", why="because")


def test_the_compose_version_requirement_is_load_bearing_for_every_service() -> None:
    """The one requirement whose absence produces no error message anywhere: the v1 tool
    ignores `deploy.resources.limits` silently, so an install on it comes up healthy with
    every container unlimited. This asserts the premise rather than the sentence, by proving
    every service in every profile does declare its ceiling there, which is what makes the
    requirement true rather than cautious.

    Delete this and the requirement becomes a claim about a block that may no longer be used."""
    from brain.deployment.requirements import LIMITS_ARE_IGNORED_WITHOUT_COMPOSE_V2

    for profile in PROFILES:
        # `deployment_mib` refuses a service that declares no memory limit, so a clean sum is
        # the proof that every one of them writes it under `deploy.resources.limits`.
        assert deployment_mib(files_of(profile)) > 0

    stated = next(one for one in RUNTIME_REQUIREMENTS if one.what.startswith("Docker Compose v2"))
    assert stated.why == LIMITS_ARE_IGNORED_WITHOUT_COMPOSE_V2
    assert stated.minimum


def test_the_installer_requires_no_git_and_the_reason_is_the_duplication_rule() -> None:
    """A requirement list naming git is an installer that clones, which is the shape
    `brain.ops.independence.duplication_gaps` refuses in a build input for the reason that
    ends with a client running a copy no fix ever reached.

    Delete this and `git` joins the list because it is convenient, and the second copy follows
    it."""
    assert all("git" not in one.what.lower() for one in RUNTIME_REQUIREMENTS)
    assert any("curl" in one.what for one in RUNTIME_REQUIREMENTS)


def test_a_service_body_that_is_not_a_mapping_is_skipped_rather_than_raising() -> None:
    """A half-finished edit leaves `app:` with nothing under it, and a specification that
    raised on that would refuse to describe a deployment because somebody was mid-edit. The
    checks that refuse a malformed document live in `brain.ops.compose`, which costs it.

    Delete this and reading the ports out of a tree somebody is editing crashes."""
    document = {"services": {"app": None, "db": {"expose": ["5432"], "ports": ["8000:8000"]}}}
    assert published_ports({"one.yml": document}) == ("db: 8000:8000",)
    assert exposed_ports({"one.yml": document}) == {"db": ("5432",)}
    assert images_in({"one.yml": document}) == ()
