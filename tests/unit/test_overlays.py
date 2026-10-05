"""The optional services an install switches on, planned in Python and started by the release.

Two halves, each tested where it can be. `brain.ops.overlays` decides: which services a setting
names, what the server holds, and which of them fit. `ops/deploy/overlays/apply.sh` does what the
plan says, and it is run here for real against a stub `docker` that keeps a log of every call and
hands the planner's standard input back to the test, so the facts the script gathers are read by
the same `read_host` the server runs. The deploy hook that copies the script out of the image is
`tests/unit/test_brain_deploy.py`'s.

Every date and figure here is a fixture of a host that does not exist, chosen so the arithmetic is
easy to follow: an 8,192 MiB machine, never the owner's.

Task ids: M32.2.1.1, M32.1.1.1, M32.1.1.2
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
    Seen,
    main,
    mebibytes,
    observation,
    plan,
    read_host,
    read_seen,
    render,
    seen_in,
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


def _overlay_file(name: str) -> Path:
    """A file an overlay names: the product's compose files at the root, the step's beside it."""
    root = REPO / name
    return root if root.exists() else REPO / "ops" / "deploy" / "overlays" / name


@pytest.mark.parametrize("overlay", OVERLAYS, ids=lambda one: one.name)
def test_each_overlay_s_files_describe_exactly_the_containers_it_is_costed_for(
    overlay: Overlay,
) -> None:
    """The files are what starts and the components are what is paid for, and the two are read
    from different places, so they are compared after the files are merged as compose merges them.
    Every long-running container is a costed component at its budgeted limit, a one-shot (restart
    "no") is not costed because it exits but still carries a limit, and every network a JOIN names
    is declared there and internal.

    Delete this and a service can be added to a file and started on a server that was costed for
    one fewer, or a JOIN can name a network the files never create and the application never reach
    the service."""
    merged: dict[str, dict[str, object]] = {}
    networks: dict[str, dict[str, object]] = {}
    for name in overlay.files:
        raw = yaml.safe_load(_overlay_file(name).read_text(encoding="utf-8"))
        for service, body in raw["services"].items():
            merged.setdefault(service, {}).update(body or {})
        networks.update(raw.get("networks") or {})
    described = {service: body for service, body in merged.items() if body}
    running = sorted(svc for svc, body in described.items() if body.get("restart") != "no")
    assert running == sorted(overlay.components)
    for svc, body in described.items():
        limit = str(body["deploy"]["resources"]["limits"]["memory"])  # type: ignore[index]
        if svc in overlay.components:
            assert limit == f"{component(svc).memory_mib}M", svc
        else:
            assert limit.endswith("M") and int(limit[:-1]) > 0, svc
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
    ignored = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert copies[f"{target}/"] == "ops/deploy/overlays/"
    step = REPO / "ops" / "deploy" / "overlays"
    for overlay in OVERLAYS:
        for name in (*overlay.files, *overlay.prepare):
            if (step / name).exists():
                assert f"!ops/deploy/overlays/{name}" in ignored, name
            else:
                assert copies[f"{target}/{name}"] == name
    assert "!ops/deploy/overlays/apply.sh" in ignored
    for mounted in ("ops/langfuse/clickhouse-memory.xml", "ops/seaweedfs/provision.sh"):
        assert f"!{mounted}" in ignored
        settled = mounted.removeprefix("ops/")
        assert copies[f"{target}/settings/{settled}"] == mounted


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
    """The script reads six kinds of line and nothing else. Delete this and a renamed prefix
    starts nothing on the server with every Python test green."""
    host = _host(PRESIDIO.cost_mib)
    lines = render(plan((PRESIDIO,), host), host).splitlines()

    assert "FILE docker-compose.presidio.yml" in lines
    assert "JOIN pii app brain-worker" in lines
    assert all(re.match(r"^(START|SAY|PREPARE|FILE|JOIN|WAIT) ", one) for one in lines)
    assert "START presidio" in lines
    assert "WAIT presidio-analyzer" in lines
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
        *compose.service*) echo "$3|$4|running|healthy" ;;
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
    case "$*" in
      *observe*) cat > "$S/observed"; echo "SAY kept what the stub saw"; exit 0 ;;
    esac
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
    observed: str
    prepared: str
    handed: str


def apply(
    tmp_path: Path,
    *,
    planned: str,
    plan_exit: int = 0,
    compose_exit: int = 0,
    start_exit: int = 0,
    containers: tuple[str, ...] = INSTALL,
    prepare_exit: int | None = None,
    env_file: bool = False,
) -> Applied:
    """Run the real script once against the stub, with the planner answering `planned`.

    `start_exit` is what starting the services exits with and `compose_exit` what waiting for
    them to report healthy exits with. `prepare_exit` runs the step from a copy of its directory
    holding a `langfuse.prepare.sh` stand-in that records its environment and exits with it, and
    `env_file` puts an environment file where the step looks for one.
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
    script = SCRIPT
    if prepare_exit is not None:
        step = tmp_path / "step"
        shutil.copytree(SCRIPT.parent, step)
        (step / "langfuse.hand.sh").write_text(
            f'#!/bin/sh\necho "$BRAIN_APP_CONTAINER $BRAIN_OVERLAYS_ENV" > "{state}/handed"\n',
            encoding="utf-8",
            newline="\n",
        )
        (step / "langfuse.prepare.sh").write_text(
            "#!/bin/sh\n"
            'echo "$BRAIN_APP_PROJECT $BRAIN_OVERLAYS_SETTINGS $BRAIN_OVERLAYS_ENV'
            ' $BRAIN_APP_CONTAINER"'
            f' > "{state}/prepared"\n'
            f"exit {prepare_exit}\n",
            encoding="utf-8",
            newline="\n",
        )
        script = step / "apply.sh"
    settings = tmp_path / "settings"
    settings.mkdir()
    if env_file:
        (settings / "overlays.env").write_text("A=1\n", encoding="utf-8", newline="\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}",
        "STUB_STATE": state.as_posix(),
        "BRAIN_OVERLAYS_MEMINFO": (state / "meminfo").as_posix(),
        "BRAIN_OVERLAYS_SETTINGS": settings.as_posix(),
    }
    assert SH is not None
    done = subprocess.run(
        [SH, script.as_posix(), "app-u"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    facts = state / "facts"
    observed = state / "observed"
    prepared = state / "prepared"
    return Applied(
        code=done.returncode,
        calls=(state / "calls").read_text(encoding="utf-8").splitlines(),
        connected=(state / "connected").read_text(encoding="utf-8").splitlines(),
        facts=facts.read_text(encoding="utf-8") if facts.exists() else "",
        output=done.stdout + done.stderr,
        observed=observed.read_text(encoding="utf-8") if observed.exists() else "",
        prepared=prepared.read_text(encoding="utf-8").strip() if prepared.exists() else "",
        handed=(state / "handed").read_text(encoding="utf-8").strip()
        if (state / "handed").exists()
        else "",
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
        "--wait-timeout 300 presidio-analyzer"
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


# ------------------------------------------------------------------ the trace ledger's half
LANGFUSE = BY_NAME["langfuse"]


def _both(available: int) -> str:
    host = _host(available)
    return render(plan((PRESIDIO, LANGFUSE), host), host)


def test_the_ledger_is_costed_as_its_five_services_and_prepared_before_it_starts() -> None:
    """The ledger's plan names its preparation before its files and waits on its five services and
    not on the one-shot that makes its bucket. Delete this and the ledger starts before its
    secrets exist, or the step waits on a container that exits and calls the deploy a failure."""
    assert LANGFUSE.cost_mib == 2304
    lines = _both(PRESIDIO.cost_mib + LANGFUSE.cost_mib).splitlines()
    start = lines.index("START langfuse")
    own = lines[start:]
    assert own.index("PREPARE langfuse.prepare.sh") < own.index("FILE docker-compose.langfuse.yml")
    assert sorted(one for one in own if one.startswith("WAIT ")) == sorted(
        f"WAIT {name}" for name in LANGFUSE.components
    )
    assert "WAIT langfuse-events-bucket" not in lines


def test_the_detector_is_given_the_room_first_and_the_ledger_is_refused_when_it_does_not_fit() -> (
    None
):
    """Item 120's order on a server with room for one of the two. Delete this and the ledger can
    take the room the owner gave the detector."""
    lines = _both(PRESIDIO.cost_mib + LANGFUSE.cost_mib - 1).splitlines()
    assert "START presidio" in lines
    assert "START langfuse" not in lines
    assert any(
        one.startswith("SAY the trace ledger and its file store (langfuse) needs") for one in lines
    )


def test_what_docker_reported_is_kept_for_the_release_and_read_back_only_for_it() -> None:
    """The step's report, from docker's own format to the row and back. A report for another
    release, or of a shape nobody wrote, reads as no report at all. Delete this and a check can
    judge a release on what an earlier one ran, or on a row somebody typed."""
    lines = [
        f"langfuse-web|{512 * MIB}|running|healthy",
        f"langfuse-events-bucket|{64 * MIB}|exited|",
        "",
        "|0|running|healthy",
    ]
    seen = read_seen(lines)
    assert [one.service for one in seen] == ["langfuse-web", "langfuse-events-bucket"]
    kept = observation(seen, commit="abc1234")
    back = seen_in(kept, commit="abc1234")
    assert back is not None
    assert back["langfuse-web"] == Seen("langfuse-web", 512, "running", "healthy")
    assert back["langfuse-events-bucket"].health == ""
    assert seen_in(kept, commit="def5678") is None
    assert seen_in({"commit": "abc1234", "services": "nope"}, commit="abc1234") is None
    assert seen_in("nope", commit="abc1234") is None


def test_a_report_that_cannot_be_kept_says_so_and_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no database the report is not kept, and the step's journal says it. Delete this and a
    lost report is silent, and the ledger's checks are not run for a reason nobody can see."""
    import io
    import sys

    for name in ("DATABASE_URL", "BRAIN_MIGRATION_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"langfuse-web|{512 * MIB}|running|healthy\n"))

    assert main(["observe"]) == 1
    assert capsys.readouterr().out.startswith(
        "SAY what the optional services are running was not kept"
    )


@pytestmark_sh
def test_an_overlay_is_prepared_with_the_project_settings_and_environment_file_it_is_given(
    tmp_path: Path,
) -> None:
    """The preparation is told where the settings and the secrets go, which project's database
    to use and which container is the application's, and the services are composed with that
    environment file. Delete this and the ledger starts with secrets interpolated as empty
    strings, or the class pools' preparation has no application to ask for its configuration."""
    ran = apply(tmp_path, planned=_both(10_000), prepare_exit=0, env_file=True)

    assert ran.code == 0, ran.output
    settings = (tmp_path / "settings").as_posix()
    assert ran.prepared == f"u {settings} {settings}/overlays.env app-u"
    [started] = [
        one for one in ran.calls if one.startswith("compose ") and "--remove-orphans" in one
    ]
    assert f"--env-file {settings}/overlays.env" in started
    assert "langfuse.attach.yml" in started


@pytestmark_sh
def test_an_overlay_whose_preparation_fails_is_left_out_and_nothing_running_is_removed(
    tmp_path: Path,
) -> None:
    """The detector still starts, the ledger's files are not composed, and compose is not told to
    remove orphans, so a ledger already running from an earlier deploy keeps running. Delete this
    and a database that is briefly unreachable during a deploy takes the ledger down."""
    ran = apply(tmp_path, planned=_both(10_000), prepare_exit=1)

    assert ran.code == 0, ran.output
    assert "langfuse is not started: its preparation did not finish" in ran.output
    composed = [one for one in ran.calls if one.startswith("compose ")]
    assert composed and all("docker-compose.langfuse.yml" not in one for one in composed)
    assert all("--remove-orphans" not in one for one in composed)
    assert all("down" not in one.split() for one in composed)


@pytestmark_sh
def test_with_the_only_overlay_unprepared_nothing_is_stopped(tmp_path: Path) -> None:
    """A plan of the ledger alone whose preparation fails leaves no file to compose, which would
    otherwise read as "nothing is switched on" and stop the project. Delete this and that is what
    happens."""
    host = _host(LANGFUSE.cost_mib)
    running = (
        *INSTALL,
        "langfuse-web-1 u-overlays langfuse-web 536870912 300MiB u-overlays_default",
    )
    ran = apply(
        tmp_path,
        planned=render(plan((LANGFUSE,), host), host),
        prepare_exit=1,
        containers=running,
    )

    assert ran.code == 1
    assert not [one for one in ran.calls if one.startswith("compose")]


@pytestmark_sh
def test_what_docker_says_of_the_overlays_is_handed_to_the_application_to_keep(
    tmp_path: Path,
) -> None:
    """After the wait, each overlay container's service, limit, state and health goes to `observe`,
    in the format `read_seen` reads. Delete this and the ledger's checks never have a report to
    read, and are not run on every release."""
    running = (*INSTALL, "presidio-1 u-overlays presidio-analyzer 1610612736 1.1GiB u-overlays_pii")
    ran = apply(tmp_path, planned=_planned(PRESIDIO.cost_mib), containers=running)

    assert ran.code == 0, ran.output
    assert read_seen(ran.observed.splitlines()) == (
        Seen("presidio-analyzer", 1536, "running", "healthy"),
    )
    assert "overlays: kept what the stub saw" in ran.output


# ------------------------------------------------------------------ the ledger's preparation
PREPARE_STUB = r"""#!/bin/sh
S="$STUB_STATE"
echo "$*" >> "$S/calls"
case "$1" in
  ps) [ -s "$S/db" ] && cat "$S/db"; exit 0 ;;
  inspect) echo "u"; echo "u_default"; exit 0 ;;
  exec)
    case "$*" in
      *POSTGRES_USER*) echo brain; exit 0 ;;
      *POSTGRES_DB*) echo brain; exit 0 ;;
      *psql*) cat >> "$S/sql"; exit 0 ;;
    esac ;;
esac
exit 0
"""

SECRETS = {
    "LANGFUSE_POSTGRES_PASSWORD": 64,
    "LANGFUSE_CLICKHOUSE_PASSWORD": 64,
    "LANGFUSE_S3_ACCESS_KEY_ID": 32,
    "LANGFUSE_S3_SECRET_ACCESS_KEY": 64,
    "LANGFUSE_NEXTAUTH_SECRET": 64,
    "LANGFUSE_SALT": 64,
    # Langfuse refuses an encryption key that is not 64 hexadecimal characters.
    "LANGFUSE_ENCRYPTION_KEY": 64,
}

#: The ledger's project keys, in the shapes the ledger gives its own and `ledger_export` reads.
PROJECT_KEYS = {
    "LANGFUSE_INIT_PROJECT_PUBLIC_KEY": r"pk-lf-[0-9a-f]{32}",
    "LANGFUSE_INIT_PROJECT_SECRET_KEY": r"sk-lf-[0-9a-f]{64}",
}


@dataclass
class Prepared:
    code: int
    output: str
    env: dict[str, str]
    calls: list[str]
    sql: str
    settings: Path


def prepare(tmp_path: Path, *, db: bool = True) -> Prepared:
    """Run the real `langfuse.prepare.sh` from a copy of the step with the image's settings beside
    it, against a stub docker whose database records the SQL it was handed."""
    state = tmp_path / "state"
    bin_dir = tmp_path / "bin"
    step = tmp_path / "step"
    settings = tmp_path / "settings"
    for one in (state, bin_dir):
        one.mkdir(exist_ok=True)
    if not step.exists():
        shutil.copytree(SCRIPT.parent, step)
        for mounted in ("langfuse/clickhouse-memory.xml", "seaweedfs/provision.sh"):
            (step / "settings" / mounted).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / "ops" / mounted, step / "settings" / mounted)
    fake = bin_dir / "docker"
    fake.write_text(PREPARE_STUB, encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    (state / "db").write_text("db-u\n" if db else "", encoding="utf-8", newline="\n")
    (state / "calls").write_text("", encoding="utf-8", newline="\n")
    (state / "sql").write_text("", encoding="utf-8", newline="\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}",
        "STUB_STATE": state.as_posix(),
        "BRAIN_OVERLAYS_SETTINGS": settings.as_posix(),
        "BRAIN_OVERLAYS_ENV": (settings / "overlays.env").as_posix(),
        "BRAIN_APP_PROJECT": "u",
    }
    assert SH is not None
    done = subprocess.run(
        [SH, (step / "langfuse.prepare.sh").as_posix()],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    kept = settings / "overlays.env"
    return Prepared(
        code=done.returncode,
        output=done.stdout + done.stderr,
        env=dict(
            line.split("=", 1)
            for line in (kept.read_text(encoding="utf-8").splitlines() if kept.exists() else [])
        ),
        calls=(state / "calls").read_text(encoding="utf-8").splitlines(),
        sql=(state / "sql").read_text(encoding="utf-8"),
        settings=settings,
    )


@pytestmark_sh
def test_the_ledger_s_secrets_are_minted_on_the_server_once_and_kept_where_only_root_reads(
    tmp_path: Path,
) -> None:
    """Every secret the ledger's compose file interpolates is minted, at the length its consumer
    needs, into a file of mode 0600 in a directory of mode 0700, and a second deploy changes none
    of them. Delete this and a redeploy rotates the database password under a running ledger, or
    a secret lands somewhere another user on the server can read."""
    import json
    import stat

    first = prepare(tmp_path)
    assert first.code == 0, first.output
    for name, length in SECRETS.items():
        assert re.fullmatch(f"[0-9a-f]{{{length}}}", first.env[name]), name
    for name, shape in PROJECT_KEYS.items():
        assert re.fullmatch(shape, first.env[name]), name
    assert first.env["LANGFUSE_PUBLIC_URL"] == "http://langfuse-web:3000"
    assert first.env["BRAIN_APP_NETWORK"] == "u"
    assert stat.S_IMODE((first.settings / "overlays.env").stat().st_mode) == 0o600
    assert stat.S_IMODE(first.settings.stat().st_mode) == 0o700

    access = json.loads((first.settings / "seaweedfs" / "s3.json").read_text(encoding="utf-8"))
    [identity] = access["identities"]
    assert identity["credentials"] == [
        {
            "accessKey": first.env["LANGFUSE_S3_ACCESS_KEY_ID"],
            "secretKey": first.env["LANGFUSE_S3_SECRET_ACCESS_KEY"],
        }
    ]
    assert sorted(identity["actions"]) == [
        "List:langfuse-events",
        "Read:langfuse-events",
        "Write:langfuse-events",
    ]

    second = prepare(tmp_path)
    assert second.code == 0, second.output
    assert second.env == first.env
    kept = (first.settings / "overlays.env").read_text(encoding="utf-8")
    assert kept.count("BRAIN_APP_NETWORK=") == 1


@pytestmark_sh
def test_the_ledger_s_database_and_role_are_made_with_the_password_on_standard_input_only(
    tmp_path: Path,
) -> None:
    """The role is created or has its password set, and the database is created once, by SQL
    handed to psql on standard input, so the password is never an argument another process on the
    server can list. Delete this and the password appears in `ps`, or the role keeps a password the
    environment file no longer holds."""
    ran = prepare(tmp_path)

    assert ran.code == 0, ran.output
    password = ran.env["LANGFUSE_POSTGRES_PASSWORD"]
    assert f"PASSWORD '{password}'" in ran.sql
    assert "ALTER ROLE langfuse WITH LOGIN PASSWORD" in ran.sql
    assert "CREATE DATABASE langfuse OWNER langfuse" in ran.sql
    assert "\\gexec" in ran.sql
    assert not [one for one in ran.calls if password in one]
    assert not [
        one for one in ran.calls for value in ran.env.values() if len(value) == 64 and value in one
    ]


@pytestmark_sh
def test_the_settings_files_the_ledger_mounts_are_put_in_place_and_never_overwritten(
    tmp_path: Path,
) -> None:
    """Copied from the image when missing, left alone when an install has tuned them. Delete this
    and either the column store starts with no memory ceiling of its own, or a deploy undoes an
    administrator's tuning."""
    first = prepare(tmp_path)
    assert first.code == 0, first.output
    tuned = first.settings / "langfuse" / "clickhouse-memory.xml"
    assert tuned.read_bytes() == (REPO / "ops" / "langfuse" / "clickhouse-memory.xml").read_bytes()
    assert (first.settings / "seaweedfs" / "provision.sh").exists()

    tuned.write_text("<clickhouse><!-- tuned --></clickhouse>\n", encoding="utf-8")
    prepare(tmp_path)
    assert "tuned" in tuned.read_text(encoding="utf-8")


@pytestmark_sh
def test_a_server_with_no_database_for_the_ledger_refuses_to_prepare_it(tmp_path: Path) -> None:
    """No running `db` in the application's project is a ledger with nowhere to keep its records,
    and the preparation says so and exits non-zero, which leaves the ledger out of this deploy.
    Delete this and the ledger starts and fails its migrations in a loop."""
    ran = prepare(tmp_path, db=False)

    assert ran.code == 1
    assert "no running db service in u" in ran.output
    assert ran.sql == ""


@pytestmark_sh
def test_what_the_application_must_be_handed_is_handed_after_the_services_run(
    tmp_path: Path,
) -> None:
    """An overlay's AFTER script runs once its services are started, with the application's
    container and the environment file, and not for an overlay whose preparation failed. Delete
    this and the ledger runs with keys the application never receives, or keys from a preparation
    that never finished are handed over."""
    settings = (tmp_path / "ok" / "settings").as_posix()
    (tmp_path / "ok").mkdir()
    (tmp_path / "failed").mkdir()
    ran = apply(tmp_path / "ok", planned=_both(10_000), prepare_exit=0)
    left_out = apply(tmp_path / "failed", planned=_both(10_000), prepare_exit=1)

    assert ran.code == 0, ran.output
    assert ran.handed == f"app-u {settings}/overlays.env"
    assert left_out.handed == ""


KEYS_IN_A_FILE = (
    "LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-0a\nLANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-1b\n"
)

HAND_STUB = r"""#!/bin/sh
S="$STUB_STATE"
echo "$*" >> "$S/calls"
case "$*" in
  *ledger_export*)
    cat > "$S/stdin"
    echo "SAY the trace ledger's keys are kept in the vault"
    exit "$(cat "$S/keep_exit")" ;;
esac
exit 0
"""


def hand(tmp_path: Path, *, env: str, keep_exit: int = 0) -> tuple[int, str, str, list[str]]:
    """Run the real `langfuse.hand.sh` against a stub docker that keeps what it was handed."""
    state = tmp_path / "state"
    bin_dir = tmp_path / "bin"
    for one in (state, bin_dir):
        one.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(HAND_STUB, encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    (state / "keep_exit").write_text(f"{keep_exit}\n", encoding="utf-8", newline="\n")
    (state / "calls").write_text("", encoding="utf-8", newline="\n")
    envfile = tmp_path / "overlays.env"
    envfile.write_text(env, encoding="utf-8", newline="\n")
    assert SH is not None
    done = subprocess.run(
        [SH, (SCRIPT.parent / "langfuse.hand.sh").as_posix()],
        env={
            **os.environ,
            "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}",
            "STUB_STATE": state.as_posix(),
            "BRAIN_OVERLAYS_ENV": envfile.as_posix(),
            "BRAIN_APP_CONTAINER": "app-u",
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    stdin = state / "stdin"
    return (
        done.returncode,
        done.stdout + done.stderr,
        stdin.read_text(encoding="utf-8") if stdin.exists() else "",
        (state / "calls").read_text(encoding="utf-8").splitlines(),
    )


@pytestmark_sh
def test_the_ledger_s_keys_are_handed_to_the_application_on_standard_input_only(
    tmp_path: Path,
) -> None:
    """The public key then the secret, on standard input to `brain.ops.ledger_export keep` in the
    application, and in no argument docker or `ps` could show; the application's own sentence is
    what the journal says. Delete this and a key appears on a command line, or the two arrive in
    the order `keys_from` refuses."""
    env = "A=1\n" + KEYS_IN_A_FILE
    code, said, stdin, calls = hand(tmp_path, env=env)

    assert code == 0, said
    assert stdin == "pk-lf-0a\nsk-lf-1b\n"
    assert calls == ["exec -i app-u python -m brain.ops.ledger_export keep"]
    assert "overlays: langfuse: the trace ledger's keys are kept in the vault" in said
    assert "sk-lf-1b" not in said


@pytestmark_sh
@pytest.mark.parametrize(
    ("env", "keep_exit"),
    [
        ("A=1\n", 0),
        (
            "LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-0a\nLANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-1b\n",
            1,
        ),
    ],
    ids=["no keys minted", "the application did not keep them"],
)
def test_keys_that_cannot_be_handed_or_kept_are_said_and_exit_non_zero(
    tmp_path: Path, env: str, keep_exit: int
) -> None:
    """Delete this and a ledger with no keys in the application reads, in the deploy journal, as one
    that was handed them."""
    code, said, _, _ = hand(tmp_path, env=env, keep_exit=keep_exit)
    assert code == 1, said
