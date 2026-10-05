"""The optional services an install switches on, planned in Python and started by the release.

Two halves, each tested where it can be. `brain.ops.overlays` decides: which services a setting
names, what the server holds, and which of them fit. `ops/deploy/overlays/apply.sh` does what the
plan says, and it is run here for real against a stub `docker` that keeps a log of every call and
hands the planner's standard input back to the test, so the facts the script gathers are read by
the same `read_host` the server runs. The deploy hook that copies the script out of the image is
`tests/unit/test_brain_deploy.py`'s.

Every date and figure here is a fixture of a host that does not exist, chosen so the arithmetic is
easy to follow: an 8,192 MiB machine, never the owner's.

Task ids: M32.2.1.1
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from brain.ops.overlays import (
    BY_NAME,
    NO_SERVICES,
    OVERLAYS,
    SERVICES_SETTING,
    UNLIMITED_GROWTH,
    Host,
    Overlay,
    OverlayError,
    main,
    mebibytes,
    plan,
    read_host,
    render,
    services_problem,
    switched_on,
    switched_on_here,
)
from brain.ops.wiring import HOST_RESERVE_MIB, component

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "deploy" / "overlays" / "apply.sh"
SH = shutil.which("sh")
PRESIDIO = BY_NAME["presidio"]
MIB = 1024 * 1024


# ------------------------------------------------------------------ the setting
def test_the_setting_names_services_by_name_and_none_names_none() -> None:
    """The three shapes an administrator types: none, one name, a list with spaces and a repeat.
    Delete this and a list that reads correctly to a person can start something else, or nothing."""
    assert switched_on(NO_SERVICES) == ()
    assert switched_on("presidio") == (PRESIDIO,)
    assert switched_on(" presidio , presidio ") == (PRESIDIO,)


@pytest.mark.parametrize("value", ["presidoi", "presidio,langfuse-x", "", " , "])
def test_a_name_nobody_declared_is_refused_rather_than_skipped(value: str) -> None:
    """A typo that started nothing would read on the server as a service that failed to start and
    in the setting as one that runs. Delete this and the two disagree with nobody told."""
    with pytest.raises(OverlayError, match=SERVICES_SETTING):
        switched_on(value)


def test_the_settings_screen_refuses_a_typo_in_words_and_saves_a_real_name() -> None:
    """Both sides of the screen's rule. Delete this and the screen can save a value the planner
    then refuses on every deploy, which is a switch that looks on and never is."""
    assert services_problem("presidio") == ""
    assert services_problem(NO_SERVICES) == ""
    said = services_problem("presidoi")
    assert said.startswith(f"Write {NO_SERVICES}, or one or more")
    assert "presidio for the personal data detector" in said


def test_the_setting_is_read_through_the_one_installation_reader_saved_first() -> None:
    """A value saved on the Settings screen outranks the environment, as every installation value
    does. Delete this and the planner could read the environment's template value and stop a
    detector somebody switched on in the console."""
    assert switched_on_here(env={}, saved={}) == ()
    assert switched_on_here(env={SERVICES_SETTING: "presidio"}, saved={}) == (PRESIDIO,)
    assert (
        switched_on_here(env={SERVICES_SETTING: "presidio"}, saved={SERVICES_SETTING: "none"}) == ()
    )


# ------------------------------------------------------------------ the declaration
def test_an_overlay_cannot_name_a_container_the_budget_does_not_cost() -> None:
    """An overlay is costed from `brain.ops.wiring`, so one naming a container nobody budgeted
    would start at whatever its file says with no arithmetic behind it. Delete this and an overlay
    can be cheaper on paper than on the server."""
    with pytest.raises(OverlayError, match="nobody budgeted"):
        Overlay(name="probe", what="a probe", components=("nope",), files=("x.yml",))
    with pytest.raises(OverlayError, match="starts nothing"):
        Overlay(name="probe", what="a probe", components=(), files=("x.yml",))
    with pytest.raises(OverlayError, match="can type into a setting"):
        Overlay(name="Probe", what="a probe", components=("seaweedfs",), files=("x.yml",))


@pytest.mark.parametrize("overlay", OVERLAYS, ids=lambda one: one.name)
def test_each_overlay_s_files_describe_exactly_the_containers_it_is_costed_for(
    overlay: Overlay,
) -> None:
    """The files are what starts and the components are what is paid for, and the two are read
    from different places, so they are compared. Every container the files describe carries the
    limit the budget gives it, and every network a JOIN names is declared there and internal.

    Delete this and a service can be added to the file and started on a server that was costed for
    one fewer, or a JOIN can name a network the file never creates and the application never reach
    the service."""
    described: dict[str, dict[str, object]] = {}
    networks: dict[str, dict[str, object]] = {}
    for name in overlay.files:
        raw = yaml.safe_load((REPO / name).read_text(encoding="utf-8"))
        described.update({svc: body for svc, body in raw["services"].items() if body})
        networks.update(raw.get("networks") or {})
    assert sorted(described) == sorted(overlay.components)
    for svc, body in described.items():
        limit = body["deploy"]["resources"]["limits"]["memory"]  # type: ignore[index]
        assert str(limit) == f"{component(svc).memory_mib}M", svc
    for network, services in overlay.joins:
        assert networks[network].get("internal") is True, network
        assert services


def test_the_image_carries_the_step_and_every_file_an_overlay_starts() -> None:
    """The deploy hook copies `/app/ops/deploy/overlays/` out of the image, so a file that is not
    copied there is a service the release cannot start. Read from the Dockerfile's COPY lines and
    the ignore file's exceptions, not from a sentence about them.

    Delete this and an overlay can be declared, tested and shipped in an image that lacks its
    compose file, which on the server reads as a plan whose files do not exist."""
    copies = {
        parts[-1]: parts[-2]
        for line in (REPO / "Dockerfile").read_text(encoding="utf-8").splitlines()
        if line.startswith("COPY ") and (parts := line.split())
    }
    target = "/app/ops/deploy/overlays"
    assert copies[f"{target}/apply.sh"] == "ops/deploy/overlays/apply.sh"
    for overlay in OVERLAYS:
        for name in overlay.files:
            assert copies[f"{target}/{name}"] == name
    ignored = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "!ops/deploy/overlays/apply.sh" in ignored


# ------------------------------------------------------------------ the server
FACTS = """## meminfo
MemTotal:        8388608 kB
MemFree:          100000 kB
## inspect
/app-u|u|1073741824
/db-u|u|2147483648
/panel||0
/canvas|other|0
/presidio-1|u-overlays|1610612736
## stats
app-u|880.3MiB / 1GiB
db-u|504.6MiB / 2GiB
panel|357.2MiB / 7.8GiB
canvas|1.5GiB / 7.8GiB
presidio-1|1.1GiB / 1.5GiB
"""


def test_the_server_is_read_as_its_limits_and_what_its_unlimited_containers_use() -> None:
    """Containers with a limit count at it, containers without count at what they use, and the
    overlays' own project counts at neither, because the plan is about to cost it from the budget.

    Delete this and a running detector pays for itself twice and is stopped by its own memory,
    or an unlimited neighbour counts at nought and the server is overcommitted on the first busy
    day."""
    host = read_host(FACTS.splitlines(), project="u-overlays")

    assert host.total_mib == 8192
    assert host.reserved_mib == 1024 + 2048
    assert host.unlimited_used_mib == 357 + 1536 + 1  # 357.2 + 1536 rounded up
    assert host.unlimited_floor_mib == -(-host.unlimited_used_mib * 11 // 10)
    assert host.available_mib == (
        8192 - host.reserved_mib - host.unlimited_floor_mib - HOST_RESERVE_MIB
    )


@pytest.mark.parametrize(
    ("written", "mib"),
    [("880.3MiB", 880.3), ("1.5GiB", 1536.0), ("512KiB", 0.5), ("0B", 0.0), ("2GB", 2048.0)],
)
def test_an_amount_is_read_in_every_unit_docker_writes(written: str, mib: float) -> None:
    """docker stats moves between units as a container grows. Delete this and a neighbour that
    crosses a gibibyte is read as using a thousandth of what it does."""
    assert mebibytes(written) == pytest.approx(mib)


def test_facts_with_no_memory_line_are_refused_rather_than_read_as_an_empty_server() -> None:
    """A server of nought mebibytes fits nothing, which would stop every service on a deploy whose
    facts were cut short. Delete this and that is what a truncated read does."""
    with pytest.raises(OverlayError, match="MemTotal"):
        read_host(["## inspect", "/app-u|u|0"], project="u-overlays")
    with pytest.raises(OverlayError):
        mebibytes("lots")


# ------------------------------------------------------------------ the plan
def _host(available: int) -> Host:
    return Host(total_mib=available + HOST_RESERVE_MIB, reserved_mib=0, unlimited_used_mib=0)


def test_an_overlay_that_fits_is_started_and_one_that_does_not_is_refused_in_words() -> None:
    """Both sides at the boundary: exactly its cost is room enough, one mebibyte less is not.
    Delete this and the planner can start a service the server cannot hold, or refuse one it can."""
    cost = PRESIDIO.cost_mib

    fits = plan((PRESIDIO,), _host(cost))
    assert fits.start == (PRESIDIO,)
    assert fits.refused == ()

    short = plan((PRESIDIO,), _host(cost - 1))
    assert short.start == ()
    [(refused, reason)] = short.refused
    assert refused is PRESIDIO
    assert reason == (
        f"the personal data detector (presidio) needs {cost} MiB and this server has "
        f"{cost - 1} MiB left for it, so it is not started"
    )


def test_room_is_given_in_declaration_order_and_spent_as_it_is_given() -> None:
    """Item 120 gave the room in an order, and a second overlay is costed against what the first
    left. Asserted with the same overlay twice so it holds whatever is declared after it.

    Delete this and two services that each fit alone can both be started on a server with room for
    one."""
    cost = PRESIDIO.cost_mib
    planned = plan((PRESIDIO, PRESIDIO), _host(cost + cost // 2))
    assert planned.start == (PRESIDIO,)
    assert len(planned.refused) == 1
    assert f"has {cost // 2} MiB left" in planned.refused[0][1]


def test_the_plan_tells_the_script_the_files_the_joins_and_what_to_say() -> None:
    """The script reads three kinds of line and nothing else. Delete this and a renamed prefix
    starts nothing on the server with every Python test green."""
    host = _host(PRESIDIO.cost_mib)
    lines = render(plan((PRESIDIO,), host), host).splitlines()

    assert "FILE docker-compose.presidio.yml" in lines
    assert "JOIN pii app brain-worker" in lines
    assert all(re.match(r"^(SAY|FILE|JOIN) ", one) for one in lines)
    assert lines[0].startswith("SAY this server has ")

    nothing = render(plan((), host), host).splitlines()
    assert not [one for one in nothing if not one.startswith("SAY ")]
    assert nothing[-1] == "SAY no optional service is started on this server"


def test_a_plan_that_cannot_be_made_exits_non_zero_and_names_no_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`A_PLAN_THAT_CANNOT_BE_MADE_STOPS_NOTHING`: with no database the planner says so and exits
    1, which the script reads as "leave everything as it is". Delete this and an unreadable
    setting becomes a plan with no files, and the script stops the detector."""
    import io
    import sys

    for name in ("DATABASE_URL", "BRAIN_MIGRATION_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(FACTS))

    assert main(["plan", "--project", "u-overlays"]) == 1
    said = capsys.readouterr().out
    assert said.startswith("SAY no plan was made, so nothing is started or stopped")
    assert "FILE " not in said
    assert main(["plan"]) == 64


def test_the_growth_margin_is_the_one_the_recorded_measurement_left() -> None:
    """`wiring.NEIGHBOUR_MIB` rounds 1,389 MiB of unlimited neighbours up to 1,536, a margin of
    about a tenth, and the live planner gives the same. Held against the recorded figures rather
    than against itself. Delete this and the two halves of the budget can count a neighbour
    differently on the same server."""
    from brain.ops.wiring import NEIGHBOUR_MIB

    floor = Host(total_mib=0, reserved_mib=0, unlimited_used_mib=1389).unlimited_floor_mib
    assert pytest.approx(0.1) == UNLIMITED_GROWTH
    assert floor <= NEIGHBOUR_MIB < floor + 128


# ------------------------------------------------------------------ the script, run for real
STUB = r"""#!/bin/sh
S="$STUB_STATE"
echo "$*" >> "$S/calls"
# containers: name project service limit-bytes usage networks(comma separated)
case "$1" in
  ps)
    shift; quiet=0; proj=""; svc=""
    while [ $# -gt 0 ]; do
      case "$1" in
        -q|-aq) quiet=1 ;;
        --filter) shift
          case "$1" in
            label=com.docker.compose.project=*) proj="${1#label=com.docker.compose.project=}" ;;
            label=com.docker.compose.service=*) svc="${1#label=com.docker.compose.service=}" ;;
          esac ;;
      esac
      shift
    done
    awk -v p="$proj" -v s="$svc" '(p == "" || $2 == p) && (s == "" || $3 == s) { print $1 }' \
      "$S/containers"
    exit 0 ;;
  inspect)
    shift; fmt=""; names=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --format) shift; fmt="$1" ;;
        *) names="$names $1" ;;
      esac
      shift
    done
    for n in $names; do
      line="$(awk -v n="$n" '$1 == n' "$S/containers")"
      [ -n "$line" ] || exit 1
      set -- $line
      case "$fmt" in
        *HostConfig.Memory*) echo "/$1|$2|$4" ;;
        *Networks*) echo "$6" | tr ',' '\n' ;;
        *compose.project*) echo "$2" ;;
      esac
    done
    exit 0 ;;
  stats)
    awk '{ print $1 "|" $5 " / 7.8GiB" }' "$S/containers"
    exit 0 ;;
  exec)
    cat > "$S/facts"
    cat "$S/plan"
    exit "$(cat "$S/plan_exit")" ;;
  compose)
    case "$*" in
      *--wait*) exit "$(cat "$S/compose_exit")" ;;
    esac
    exit "$(cat "$S/start_exit")" ;;
  network)
    echo "$3 $4" >> "$S/connected"
    exit 0 ;;
esac
exit 0
"""

#: The application's project and its containers, a neighbour, and the stopped-by-default overlay
#: project, in the stub's table format.
INSTALL = (
    "app-u u app 1073741824 880.3MiB u,u_default",
    "brain-worker-u u brain-worker 402653184 206.8MiB u,u_default",
    "db-u u db 2147483648 504.6MiB u",
    "panel - - 0 357.2MiB bridge",
)


@dataclass
class Applied:
    code: int
    calls: list[str]
    connected: list[str]
    facts: str
    output: str


def apply(
    tmp_path: Path,
    *,
    planned: str,
    plan_exit: int = 0,
    compose_exit: int = 0,
    start_exit: int = 0,
    containers: tuple[str, ...] = INSTALL,
) -> Applied:
    """Run the real script once against the stub, with the planner answering `planned`.

    `start_exit` is what starting the services exits with and `compose_exit` what waiting for
    them to report healthy exits with.
    """
    state = tmp_path / "state"
    bin_dir = tmp_path / "bin"
    state.mkdir()
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(STUB, encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    for name, text in (
        ("containers", "".join(f"{one}\n" for one in containers)),
        ("plan", planned),
        ("plan_exit", f"{plan_exit}\n"),
        ("compose_exit", f"{compose_exit}\n"),
        ("start_exit", f"{start_exit}\n"),
        ("calls", ""),
        ("connected", ""),
        ("meminfo", "MemTotal:        8388608 kB\nMemFree:          100000 kB\n"),
    ):
        (state / name).write_text(text, encoding="utf-8", newline="\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}",
        "STUB_STATE": state.as_posix(),
        "BRAIN_OVERLAYS_MEMINFO": (state / "meminfo").as_posix(),
    }
    assert SH is not None
    done = subprocess.run(
        [SH, SCRIPT.as_posix(), "app-u"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    facts = state / "facts"
    return Applied(
        code=done.returncode,
        calls=(state / "calls").read_text(encoding="utf-8").splitlines(),
        connected=(state / "connected").read_text(encoding="utf-8").splitlines(),
        facts=facts.read_text(encoding="utf-8") if facts.exists() else "",
        output=done.stdout + done.stderr,
    )


def _planned(available: int) -> str:
    host = _host(available)
    return render(plan((PRESIDIO,), host), host)


pytestmark_sh = pytest.mark.skipif(SH is None, reason="the step is a POSIX shell script")


@pytestmark_sh
def test_a_planned_service_is_started_as_its_own_project_and_the_app_and_worker_join_it(
    tmp_path: Path,
) -> None:
    """The whole of the step on a good day: the overlays are composed as `<project>-overlays` from
    the files the plan names, beside the step itself, and the application and the worker, found
    by their compose service labels, are joined to the overlay's network. The database is not.

    Delete this and the detector can start where the application cannot reach it, or start inside
    the application's own project, which on Coolify is the panel's copy of the compose file."""
    ran = apply(tmp_path, planned=_planned(PRESIDIO.cost_mib))

    assert ran.code == 0, ran.output
    here = SCRIPT.parent.as_posix()
    started, waited = [one for one in ran.calls if one.startswith("compose ") and " up " in one]
    assert started == (
        f"compose -p u-overlays -f {here}/docker-compose.presidio.yml up -d --remove-orphans"
    )
    assert waited == (
        f"compose -p u-overlays -f {here}/docker-compose.presidio.yml up -d --wait "
        "--wait-timeout 300"
    )
    assert sorted(ran.connected) == ["u-overlays_pii app-u", "u-overlays_pii brain-worker-u"]
    # Joined before the wait: the worker's acceptance run must not find itself off the network
    # for the minutes the detector takes to load its model.
    joined = next(i for i, one in enumerate(ran.calls) if one.startswith("network connect"))
    assert joined < ran.calls.index(waited)
    assert "overlays: starting the personal data detector (presidio)" in ran.output


@pytestmark_sh
def test_a_container_already_on_the_network_is_not_joined_again(tmp_path: Path) -> None:
    """The step runs after every deploy, and a container the deploy did not recreate is still
    joined. Delete this and every deploy logs a failed connect for it, which buries the one that
    matters."""
    joined = (
        "app-u u app 1073741824 880.3MiB u,u_default,u-overlays_pii",
        *INSTALL[1:],
    )
    ran = apply(tmp_path, planned=_planned(PRESIDIO.cost_mib), containers=joined)

    assert ran.code == 0, ran.output
    assert ran.connected == ["u-overlays_pii brain-worker-u"]


@pytestmark_sh
def test_the_facts_the_step_gathers_are_the_facts_the_planner_reads(tmp_path: Path) -> None:
    """The script asks docker for one format and the planner parses one format, in two languages,
    so the planner is handed what the script actually wrote. The overlays' own containers are left
    out by project, and the unlimited neighbour is counted at its use.

    Delete this and a change to either format makes the planner read an empty server, which fits
    nothing and stops every service."""
    running = (*INSTALL, "presidio-1 u-overlays presidio-analyzer 1610612736 1.1GiB u-overlays_pii")
    ran = apply(tmp_path, planned=_planned(PRESIDIO.cost_mib), containers=running)

    host = read_host(ran.facts.splitlines(), project="u-overlays")
    assert host.total_mib > 0
    assert host.reserved_mib == (1073741824 + 402653184 + 2147483648) // MIB
    assert host.unlimited_used_mib == 358


@pytestmark_sh
def test_a_plan_that_cannot_be_made_leaves_every_running_service_as_it_is(
    tmp_path: Path,
) -> None:
    """`A_PLAN_THAT_CANNOT_BE_MADE_STOPS_NOTHING` on the server: no compose call at all, the
    planner's sentence in the journal, and a non-zero exit for the deploy hook to report.

    Delete this and a database restart during a deploy switches the detector off."""
    running = (*INSTALL, "presidio-1 u-overlays presidio-analyzer 1610612736 1.1GiB u-overlays_pii")
    ran = apply(
        tmp_path,
        planned="SAY no plan was made, so nothing is started or stopped: no database\n",
        plan_exit=1,
        containers=running,
    )

    assert ran.code == 1
    assert not [one for one in ran.calls if one.startswith("compose")]
    assert "overlays: no plan was made" in ran.output


@pytestmark_sh
def test_a_service_switched_off_is_stopped_and_nothing_is_stopped_where_nothing_runs(
    tmp_path: Path,
) -> None:
    """A plan naming no file stops the overlays' project, keeping its volumes, and only when it has
    a container. Delete this and a detector switched off in the console runs for ever, or every
    deploy on an install without one asks docker to stop a project that does not exist."""
    (tmp_path / "on").mkdir()
    (tmp_path / "off").mkdir()
    running = (*INSTALL, "presidio-1 u-overlays presidio-analyzer 1610612736 1.1GiB u-overlays_pii")
    stopped = apply(tmp_path / "on", planned=_planned(0), containers=running)
    idle = apply(tmp_path / "off", planned=_planned(0))

    assert stopped.code == 0, stopped.output
    assert "compose -p u-overlays down" in stopped.calls
    assert not [one for one in idle.calls if one.startswith("compose")]


@pytestmark_sh
def test_a_service_that_does_not_become_healthy_is_said_and_the_joins_still_happen(
    tmp_path: Path,
) -> None:
    """Compose waits for health and reports a failure with a non-zero exit. The step says so,
    joins anyway (a slow start is still the service the application must reach once it is up)
    and exits non-zero for the deploy hook. Delete this and a slow detector strands the
    application off its network until the next deploy."""
    ran = apply(tmp_path, planned=_planned(PRESIDIO.cost_mib), compose_exit=1)

    assert ran.code == 1
    assert "did not report healthy within five minutes" in ran.output
    assert len(ran.connected) == 2


@pytestmark_sh
def test_services_that_cannot_be_started_are_said_and_nothing_is_joined(tmp_path: Path) -> None:
    """A compose file docker refuses starts nothing, so there is no network to join and no health
    to wait for. Delete this and a refused start is followed by joins to a network that does not
    exist, whose errors bury the one line that says what went wrong."""
    ran = apply(tmp_path, planned=_planned(PRESIDIO.cost_mib), start_exit=1)

    assert ran.code == 1
    assert "could not start the optional services" in ran.output
    assert ran.connected == []
    assert not [one for one in ran.calls if "--wait" in one]
