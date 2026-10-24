"""The failure rehearsal: its table held to the matrix, the committed script held to the renderer,
and the script run against a stand-in for Docker to see how it reasons.

**The script is run, not read, and what running it against a stand-in does not show is written
here so nobody reads this file as the rehearsal.** Every behavioural test starts bash on the
committed file with a `docker` of the test's own first on `PATH`. What is proved is what the script
refuses, which containers it stops and starts, what it counts as a failure, and how it exits. What
is not proved, and cannot be here, is a real container stopping on a real server and the product
coming back: that is the first run of the script on a throwaway install, by a person.

Task ids: M30.4.3
"""

from __future__ import annotations

import os
import shutil
import signal
import stat
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import pytest

from brain.deployment.chaos import (
    DISPOSABLE_FLAG,
    FAULTS,
    REQUIRED_FAULTS,
    SCRIPT_PATH,
    ChaosError,
    Fault,
    fault_gaps,
    render_chaos,
)
from brain.deployment.release import REPO, archive_files, carried_paths, included_by, refused_by
from brain.ops.reliability import MATRIX

SCRIPT = REPO / SCRIPT_PATH
BASH = shutil.which("bash")

needs_bash = pytest.mark.skipif(BASH is None, reason="no bash on this machine")

#: A Docker that keeps its state in files under $STATE, and logs every call it is given.
DOCKER = """#!/bin/sh
echo "$*" >> "$STATE/log"
if test "$1" = compose; then
  case " $* " in
    *" ps -q app"*) test -e "$STATE/no_app" || echo app-id; exit 0 ;;
    *" exec "*)
      cat > /dev/null
      case " $* " in
        *" /health/live"*)
          if test -e "$STATE/live_down" && ls "$STATE" | grep -q '^down_'; then
            echo 0
          else
            echo 200
          fi
          exit 0 ;;
        *" /health/ready"*)
          if test -e "$STATE/unhealthy"; then echo 503; exit 0; fi
          if ls "$STATE" | grep -q '^down_'; then
            if test -e "$STATE/ready_stays"; then echo 200; else echo 503; fi
            if test -e "$STATE/block_while_down"; then touch "$STATE/blocked"; sleep 30; fi
            exit 0
          fi
          if test -e "$STATE/never"; then
            if ls "$STATE" | grep -q '^was_down'; then echo 503; exit 0; fi
          fi
          if test -e "$STATE/slow" && test -e "$STATE/was_down"; then
            left="$(cat "$STATE/slow")"
            if test "$left" -gt 0; then echo $((left - 1)) > "$STATE/slow"; echo 503; exit 0; fi
          fi
          echo 200; exit 0 ;;
      esac ;;
  esac
  exit 99
fi
case "$1" in
  inspect) test -e "$STATE/no_project" || echo thisproject; exit 0 ;;
  ps)
    case " $* " in
      *"label=brain.browser.run"*) test -e "$STATE/has_browser" && echo id-browser; exit 0 ;;
      *"project=thisproject"*)
        for svc in db brain-worker inference-server automation-egress; do
          case " $* " in
            *"service=$svc"*)
              if test -e "$STATE/has_$svc" && ! test -e "$STATE/down_$svc"; then
                echo "id-$svc"
              fi ;;
          esac
        done
        exit 0 ;;
    esac
    exit 0 ;;
  stop)
    for id in "$@"; do
      case "$id" in id-*) touch "$STATE/down_${id#id-}" "$STATE/was_down" ;; esac
    done
    exit 0 ;;
  start)
    for id in "$@"; do
      case "$id" in id-*) rm -f "$STATE/down_${id#id-}" ;; esac
    done
    exit 0 ;;
  kill) exit 0 ;;
esac
exit 99
"""

EVERYTHING = ("db", "brain-worker", "inference-server", "automation-egress", "browser")


def _stand_in(tmp_path: Path, present: tuple[str, ...], flags: tuple[str, ...]) -> Path:
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(DOCKER, encoding="utf-8", newline="\n")
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    for name in present:
        (state / f"has_{name}").touch()
    for name in flags:
        (state / name).write_text("3" if name == "slow" else "", encoding="utf-8")
    (tmp_path / "home").mkdir(exist_ok=True)
    return state


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        "PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin",
        "STATE": str(tmp_path / "state"),
        "BRAIN_HOME": str(tmp_path / "home"),
        "BRAIN_CHAOS_POLL_SECONDS": "0.1",
        "BRAIN_CHAOS_DOWN_WAIT": "1",
    }


def _run(
    tmp_path: Path,
    *args: str,
    present: tuple[str, ...] = EVERYTHING,
    flags: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    _stand_in(tmp_path, present, flags)
    assert BASH is not None
    return subprocess.run(
        [BASH, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=_env(tmp_path),
        cwd=tmp_path,
        check=False,
        timeout=120,
    )


def _log(tmp_path: Path) -> list[str]:
    path = tmp_path / "state" / "log"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _calls(tmp_path: Path, verb: str) -> list[str]:
    return [line for line in _log(tmp_path) if line.split(" ")[0] == verb]


OK = ("--profile", "standard", DISPOSABLE_FLAG, "--recover-within", "5")


# --------------------------------------------------------------------------- the table
def test_the_table_of_faults_has_no_gaps() -> None:
    """The five faults the owner named, each held to the matrix and to tests that exist. Delete
    this and a fault can name a component nothing deploys, or an in-process test that was
    renamed, and the rehearsal keeps printing a proof that is not there."""
    assert fault_gaps() == ()
    assert {one.name for one in FAULTS} == REQUIRED_FAULTS


def test_each_way_the_table_can_fall_short_is_a_finding_and_blocks_the_script() -> None:
    """One broken table per finding, each named, and the renderer refuses all of them. Delete this
    and a guard in `fault_gaps` that nothing exercises passes silently, which is the recurring
    defect in this repository: a validator written and correct and never run."""
    base = next(one for one in FAULTS if one.name == "worker")
    browser = next(one for one in FAULTS if one.name == "browser")
    cases: list[tuple[tuple[Fault, ...], str]] = [
        ((*FAULTS, base), "2 faults carry this name"),
        (tuple(one for one in FAULTS if one.name != "db"), "names no fault for it"),
        (
            tuple(replace(one, label="x") if one is base else one for one in FAULTS),
            "not both or neither",
        ),
        (
            tuple(replace(one, service=None) if one is base else one for one in FAULTS),
            "not both or neither",
        ),
        (
            tuple(
                replace(one, service="nothing-deploys-this") if one is base else one
                for one in FAULTS
            ),
            "which nothing deploys",
        ),
        (
            tuple(replace(one, component="no-such-row") if one is base else one for one in FAULTS),
            "has no failure mode in the matrix",
        ),
        (
            tuple(replace(one, presents_as_here=" ") if one is browser else one for one in FAULTS),
            "says nothing of what it looks like",
        ),
        (
            tuple(replace(one, while_down="maybe") if one is base else one for one in FAULTS),
            "neither",
        ),
        (
            tuple(replace(one, follow_up=" ") if one is base else one for one in FAULTS),
            "states no follow_up",
        ),
        (
            tuple(replace(one, skipped_because="") if one is base else one for one in FAULTS),
            "states no skipped_because",
        ),
        (
            tuple(replace(one, in_ci=()) if one is base else one for one in FAULTS),
            "names no in-process test",
        ),
        (
            tuple(
                replace(one, in_ci=("tests/unit/nope.py::test_x",)) if one is base else one
                for one in FAULTS
            ),
            "names a file that is not there",
        ),
        (
            tuple(
                replace(one, in_ci=("tests/unit/test_app.py::test_that_was_renamed",))
                if one is base
                else one
                for one in FAULTS
            ),
            "names a test that is not there",
        ),
    ]
    for table, said in cases:
        found = fault_gaps(table)
        assert any(said in finding for finding in found), (said, found)
        with pytest.raises(ChaosError):
            render_chaos(faults=table)


def test_a_fault_whose_matrix_row_is_withdrawn_is_a_finding() -> None:
    """The matrix is where what an outage looks like is written, and the script prints it. Delete
    this and a row removed from the matrix leaves a script printing nothing under its heading."""
    without_db = tuple(one for one in MATRIX if one.component != "db")

    assert any("no failure mode in the matrix" in one for one in fault_gaps(matrix=without_db))


def test_a_clean_table_has_no_findings_whatever_order_it_is_in() -> None:
    """The positive case: a guard tested only by its refusals is satisfied by a function that
    refuses everything. Delete this and `fault_gaps` can start returning a finding for every
    table, and every refusal test above still passes."""
    assert fault_gaps(tuple(reversed(FAULTS))) == ()


# ------------------------------------------------------------------------- the committed file
def test_the_committed_script_is_what_the_renderer_prints() -> None:
    """The file on the server is the one the tests describe. Delete this and the committed script
    can be edited by hand and drift from the table of faults and the matrix text it prints."""
    assert SCRIPT.read_text(encoding="utf-8") == render_chaos()


@needs_bash
def test_the_script_is_valid_bash_with_a_shebang() -> None:
    """Syntax-checked, and starts with a shebang, as the other generated scripts are. Delete this
    and a stray quote in a sentence taken from the matrix ships a script that fails on the one
    server it was written for."""
    assert BASH is not None
    done = subprocess.run([BASH, "-n", str(SCRIPT)], capture_output=True, text=True, check=False)

    assert done.returncode == 0, done.stderr
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/bin/bash\n")


def test_the_release_archive_carries_the_script() -> None:
    """A server installed from the archive has to have the rehearsal from the release it runs.
    Delete this and a rule that matches on paper selects nothing, and the script is on every
    developer's machine and no install's."""
    assert included_by(SCRIPT_PATH)
    assert not refused_by(SCRIPT_PATH)
    assert SCRIPT_PATH in set(carried_paths(REPO))
    assert SCRIPT_PATH in set(archive_files(REPO))


def test_the_script_names_no_company_and_no_address() -> None:
    """It is the product's, for a company nobody here has met. Delete this and a hostname or an
    install path from the machine it was tried on can be typed into it."""
    text = SCRIPT.read_text(encoding="utf-8")

    for word in ("verz", "staging", "coolify", "http://10.", "https://"):
        assert word not in text.lower(), word


# ------------------------------------------------------------------------------ the refusals
@needs_bash
def test_nothing_is_stopped_unless_the_install_is_called_disposable(tmp_path: Path) -> None:
    """Without the long flag the script does nothing and does not so much as ask Docker. Delete
    this and a person who runs it to see what it does stops their database."""
    done = _run(tmp_path, "--profile", "standard")

    assert done.returncode == 2
    assert DISPOSABLE_FLAG in done.stderr
    assert _log(tmp_path) == []


@needs_bash
@pytest.mark.parametrize(
    ("args", "said"),
    [
        (("--profile", "huge", DISPOSABLE_FLAG), "one of: lite standard full"),
        ((DISPOSABLE_FLAG,), "--profile is required"),
        ((*OK, "--fault", "network"), "unknown fault: network"),
        ((*OK, "--recover-within", "soon"), "whole number of seconds"),
        ((*OK, "--recover-within", "0"), "whole number of seconds"),
        ((*OK, "--turn-it-up"), "unknown option"),
    ],
)
def test_a_wrong_argument_is_refused_before_docker_is_asked(
    tmp_path: Path, args: tuple[str, ...], said: str
) -> None:
    """The profile and the fault are never guessed, and the wait is a number. Delete this and a
    typo stops a service of a stack the person did not mean."""
    done = _run(tmp_path, *args)

    assert done.returncode == 2
    assert said in done.stderr
    assert _log(tmp_path) == []


@needs_bash
def test_an_install_that_is_not_healthy_to_begin_with_is_left_alone(tmp_path: Path) -> None:
    """A stack already failing readiness teaches nothing about a fault and would hide one. Delete
    this and a fault is made on top of an outage, and the recovery it reports is the other one's."""
    done = _run(tmp_path, *OK, flags=("unhealthy",))

    assert done.returncode == 1
    assert "before any fault" in done.stderr
    assert _calls(tmp_path, "stop") == []


@needs_bash
@pytest.mark.parametrize("flag", ["no_app", "no_project"])
def test_when_the_compose_project_cannot_be_told_nothing_is_stopped(
    tmp_path: Path, flag: str
) -> None:
    """Containers are found by service name within the install's own compose project, so a host
    that runs another project's `db` is never touched. Delete this and an unknown project becomes
    a filter on the service name alone."""
    done = _run(tmp_path, *OK, flags=(flag,))

    assert done.returncode == 1
    assert "cannot be told" in done.stderr
    assert _calls(tmp_path, "stop") == []


# -------------------------------------------------------------------------------- a full run
@needs_bash
def test_every_fault_is_made_judged_and_undone_and_the_run_exits_zero(tmp_path: Path) -> None:
    """The positive case, over all five. Delete this and a script that calls everything a failure,
    or stops nothing, passes every refusal test."""
    done = _run(tmp_path, *OK)

    assert done.returncode == 0, done.stdout + done.stderr
    assert "ran 5: 5 passed, 0 failed; 0 skipped" in done.stdout
    assert done.stdout.count("recovered: ready again") == 5
    for heading in ("== browser", "== connector", "== provider", "== worker", "== db"):
        assert heading in done.stdout
    stopped = [line.split(" ", 1)[1] for line in _calls(tmp_path, "stop")]
    started = [line.split(" ", 1)[1] for line in _calls(tmp_path, "start")]
    assert stopped == ["id-automation-egress", "id-inference-server", "id-brain-worker", "id-db"]
    assert started == stopped
    assert _calls(tmp_path, "kill") == ["kill id-browser"]
    assert not list((tmp_path / "state").glob("down_*"))


@needs_bash
def test_the_outage_is_printed_beside_what_the_matrix_says_it_looks_like(tmp_path: Path) -> None:
    """Each fault prints the matrix's own sentences and a check to make by hand. Delete this and
    the script reports numbers with nothing to compare them to, and the matrix is never read."""
    done = _run(tmp_path, *OK, "--fault", "worker")
    row = next(one for one in MATRIX if one.component == "brain-worker")
    fault = next(one for one in FAULTS if one.name == "worker")

    assert f"A real outage presents as: {row.presents_as}" in done.stdout
    assert f"What to do about it: {row.response}" in done.stdout
    assert f"Check by hand: {fault.follow_up}" in done.stdout


@needs_bash
def test_only_the_fault_asked_for_is_made(tmp_path: Path) -> None:
    """`--fault` narrows the run. Delete this and asking for the worker also stops the database."""
    done = _run(tmp_path, *OK, "--fault", "worker")

    assert done.returncode == 0, done.stdout
    assert [line.split(" ", 1)[1] for line in _calls(tmp_path, "stop")] == ["id-brain-worker"]
    assert "ran 1: 1 passed" in done.stdout


@needs_bash
def test_containers_are_found_in_the_installs_own_compose_project(tmp_path: Path) -> None:
    """The ids come from a filter on the project the application runs in, and the service. Delete
    this and a shared host's other project, which also has a `db`, is stopped by a rehearsal of
    this one."""
    done = _run(tmp_path, *OK, "--fault", "db")
    asked = [line for line in _calls(tmp_path, "ps") if "service=db" in line]

    assert done.returncode == 0, done.stdout
    assert asked
    assert all("label=com.docker.compose.project=thisproject" in line for line in asked)


# --------------------------------------------------------------------- the judgements it makes
@needs_bash
def test_a_fault_the_install_cannot_make_is_skipped_and_said_so(tmp_path: Path) -> None:
    """Two present, three not. Delete this and a run over a lite install reads all faults passed
    over three it never made."""
    done = _run(tmp_path, *OK, present=("db", "brain-worker"))

    assert done.returncode == 0, done.stdout
    assert "ran 2: 2 passed, 0 failed; 3 skipped" in done.stdout
    assert done.stdout.count("SKIPPED:") == 3


@needs_bash
def test_a_run_in_which_nothing_could_be_made_exits_with_its_own_status(tmp_path: Path) -> None:
    """Nothing present. Delete this and an install with none of the five reports success."""
    done = _run(tmp_path, *OK, present=())

    assert done.returncode == 3
    assert "nothing was run" in done.stderr


@needs_bash
def test_readiness_that_stays_ready_with_the_database_stopped_is_a_failure(
    tmp_path: Path,
) -> None:
    """The database is the one fault readiness must reflect. Delete this and an application that
    answers from whatever it can still reach passes the rehearsal that exists to catch it."""
    done = _run(tmp_path, *OK, "--fault", "db", flags=("ready_stays",))

    assert done.returncode == 1
    assert "readiness still said ready" in done.stdout
    assert "0 passed, 1 failed" in done.stdout


@needs_bash
def test_readiness_that_stays_ready_with_the_worker_stopped_is_recorded_and_not_a_failure(
    tmp_path: Path,
) -> None:
    """The matrix says the worker's outage presents as nothing from outside, so requiring a
    failing readiness would contradict the row the script prints. Delete this and the script is
    changed to demand it, and fails on every healthy install."""
    done = _run(tmp_path, *OK, "--fault", "worker", flags=("ready_stays",))

    assert done.returncode == 0, done.stdout
    assert "while down: liveness 200, readiness 200" in done.stdout


@needs_bash
def test_an_application_that_stops_answering_liveness_while_a_component_is_down_fails(
    tmp_path: Path,
) -> None:
    """A process that dies with its dependency is a crash loop that hides the dependency's name.
    Delete this and the liveness half of the judgement is never exercised."""
    done = _run(tmp_path, *OK, "--fault", "worker", flags=("live_down",))

    assert done.returncode == 1
    assert "stopped answering liveness" in done.stdout


@needs_bash
def test_an_application_that_never_reports_ready_again_fails_the_run(tmp_path: Path) -> None:
    """Started again and still not ready after the wait the person chose. Delete this and a
    component that does not come back is reported as recovered."""
    done = _run(tmp_path, *OK, "--fault", "worker", "--recover-within", "1", flags=("never",))

    assert done.returncode == 1
    assert "FAILED: not ready 1s after it was started again" in done.stdout
    assert "recovered" not in done.stdout


@needs_bash
def test_an_application_that_takes_a_few_polls_to_come_back_is_polled_until_it_does(
    tmp_path: Path,
) -> None:
    """Three not-ready answers, then ready, inside the wait. Delete this and the script judges the
    first answer after the start, which is always not ready, and fails every real recovery."""
    done = _run(tmp_path, *OK, "--fault", "worker", flags=("slow",))

    assert done.returncode == 0, done.stdout
    assert "recovered: ready again after" in done.stdout


@needs_bash
def test_a_service_that_cannot_be_stopped_is_not_run_and_counts_against_the_run(
    tmp_path: Path,
) -> None:
    """Docker refusing the stop. Delete this and a fault that was never made is counted as one that
    passed."""
    _stand_in(tmp_path, ("brain-worker",), ())
    docker = tmp_path / "bin" / "docker"
    docker.write_text(
        DOCKER.replace("  stop)\n", "  stop) exit 1 ;;\n  stopped)\n"),
        encoding="utf-8",
        newline="\n",
    )
    assert BASH is not None
    done = subprocess.run(
        [BASH, str(SCRIPT), *OK, "--fault", "worker"],
        capture_output=True,
        text=True,
        env=_env(tmp_path),
        cwd=tmp_path,
        check=False,
        timeout=60,
    )

    assert done.returncode == 1
    assert "NOT RUN: it could not be stopped" in done.stdout
    assert "0 passed, 1 failed" in done.stdout


@needs_bash
def test_an_interrupted_run_starts_again_what_it_stopped(tmp_path: Path) -> None:
    """The script is killed while the database is down. Delete this and an interrupted rehearsal
    leaves a real install without its database."""
    _stand_in(tmp_path, ("db",), ("block_while_down",))
    assert BASH is not None
    process = subprocess.Popen(
        [BASH, str(SCRIPT), *OK, "--fault", "db"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env(tmp_path),
        cwd=tmp_path,
        start_new_session=True,
    )
    try:
        blocked = tmp_path / "state" / "blocked"
        for _ in range(100):
            if blocked.exists():
                break
            time.sleep(0.1)
        assert blocked.exists()
        os.killpg(process.pid, signal.SIGTERM)
        process.communicate(timeout=30)
        assert process.returncode == 130
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)

    assert _calls(tmp_path, "stop") == ["stop id-db"]
    assert "start id-db" in _calls(tmp_path, "start")
    assert not list((tmp_path / "state").glob("down_*"))
