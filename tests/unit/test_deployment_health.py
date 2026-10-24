"""The health script a person runs after deploying: rendered from the report, run against a
stand-in for Docker, and run last by the install script.

**The script is run, not read.** Every behavioural test starts bash on the committed file with a
`docker` of the test's own first on `PATH`, which answers `compose ... ps` with whatever lines the
test gives it and `compose ... exec` with a chosen exit status. What is proved is what the script
says about each state and how it exits. What is not proved, and cannot be here, is what a real
Docker prints for `--format`: the first run on a server reads that.

Task ids: M42.3.4
"""

from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from brain.deployment import health
from brain.deployment.health import (
    SCRIPT_PATH,
    HealthScriptError,
    render_health,
    reports_for,
)
from brain.deployment.install_script import HEALTH_SCRIPT
from brain.deployment.install_script import SCRIPT_PATH as INSTALL_PATH
from brain.deployment.release import REPO, compose_documents, included_by
from brain.ops.wiring import PROFILES

SCRIPT = REPO / SCRIPT_PATH
BASH = shutil.which("bash")

needs_bash = pytest.mark.skipif(BASH is None, reason="no bash on this machine")

DOCKER = """#!/bin/sh
case " $* " in
  *" ps "*) cat "$PS_FILE"; exit "${PS_STATUS:-0}" ;;
  *" exec "*) exit "${READY_STATUS:-0}" ;;
esac
exit 99
"""


def _run(
    tmp_path: Path, states: str, *, profile: str = "lite", ready: int = 0, ps_status: int = 0
) -> subprocess.CompletedProcess[str]:
    """The committed script, run in a folder of its own with a Docker that says `states`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(DOCKER, encoding="utf-8", newline="\n")
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    listed = tmp_path / "ps.txt"
    listed.write_text(states, encoding="utf-8", newline="\n")
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "PS_FILE": str(listed),
        "PS_STATUS": str(ps_status),
        "READY_STATUS": str(ready),
        "BRAIN_HOME": str(home),
    }
    assert BASH is not None
    return subprocess.run(
        [BASH, str(SCRIPT), "--profile", profile],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        check=False,
        timeout=60,
    )


def test_the_committed_script_is_what_the_renderer_prints() -> None:
    """The file on the server is the one the tests describe. Delete this and the committed script
    can be edited by hand and drift from the report it is meant to print, which is the copy
    that runs on a client's server."""
    rendered = render_health(reports_for(compose_documents(REPO)))

    assert SCRIPT.read_text(encoding="utf-8") == rendered


@needs_bash
def test_the_script_is_valid_bash_with_a_shebang_and_is_run_through_bash() -> None:
    """The file is syntax-checked, starts with a shebang, and is invoked as `bash <path>` by the
    install script and the guide, exactly as install.sh is, so no executable bit is needed or
    promised. Delete this and a stray quote in an embedded report ships a script that fails on
    the one server it was written for, or the invocation drifts to one that needs a mode."""
    assert BASH is not None
    done = subprocess.run([BASH, "-n", str(SCRIPT)], capture_output=True, text=True, check=False)

    assert done.returncode == 0, done.stderr
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/bin/bash\n")
    install = (REPO / INSTALL_PATH).read_text(encoding="utf-8")
    assert f'bash "$BRAIN_HOME/{HEALTH_SCRIPT}"' in install


@needs_bash
@pytest.mark.parametrize("profile", PROFILES)
def test_each_profile_prints_the_installers_own_report(tmp_path: Path, profile: str) -> None:
    """What a person reads first is `health_report`'s text for the profile they named. Delete this
    and the sentences about what ready means can be rewritten here and no longer be the ones
    `brain.ops.wiring` requires every component to carry."""
    files = compose_documents(REPO)
    expected = reports_for(files)[profile]
    done = _run(tmp_path, "app|running|healthy|0\n", profile=profile)

    assert done.stdout.startswith(expected.rstrip("\n"))


@needs_bash
def test_a_healthy_profile_is_ok_everywhere_and_exits_zero(tmp_path: Path) -> None:
    """The positive case. Delete this and a script that calls everything NOT READY, and so is
    never read, passes every refusal test below."""
    states = "app|running|healthy|0\ndb|running|healthy|0\nmigrate|exited||0\ncache|running||0\n"
    done = _run(tmp_path, states)

    assert done.returncode == 0, done.stdout
    for line in (
        "app: ok (running, healthy)",
        "db: ok (running, healthy)",
        "migrate: ok (finished, exit 0)",
        "cache: ok (running)",
        "application readiness: ok",
        "Everything this profile starts is ready.",
    ):
        assert line in done.stdout


@needs_bash
@pytest.mark.parametrize(
    ("row", "said"),
    [
        ("db|running|starting|0", "db: NOT READY (running, starting)"),
        ("db|running|unhealthy|0", "db: NOT READY (running, unhealthy)"),
        ("db|exited||1", "db: NOT READY (exited, exit 1)"),
        ("db|restarting||0", "db: NOT READY (restarting)"),
    ],
)
def test_a_container_that_is_not_ready_is_named_and_the_script_exits_one(
    tmp_path: Path, row: str, said: str
) -> None:
    """Running is not ready. Delete this and `running, unhealthy` is reported as ok, which is the
    liveness-for-readiness mistake the whole script exists to stop making."""
    done = _run(tmp_path, f"app|running|healthy|0\n{row}\n")

    assert done.returncode == 1
    assert said in done.stdout
    assert "app: ok (running, healthy)" in done.stdout
    assert "1 thing(s) are not ready" in done.stdout


@needs_bash
def test_an_application_that_does_not_report_ready_is_not_ok(tmp_path: Path) -> None:
    """Every container healthy and the application refusing readiness. Delete this and a stack
    whose dependencies are unreachable is called ready because each container is."""
    done = _run(tmp_path, "app|running|healthy|0\n", ready=1)

    assert done.returncode == 1
    assert "application readiness: NOT READY" in done.stdout


@needs_bash
def test_no_containers_is_a_problem_and_a_failed_listing_is_not_a_pass(tmp_path: Path) -> None:
    """Nothing listed, and Docker failing. Delete this and an install that was never started, or a
    server where Docker cannot be asked, prints an empty list and exits 0."""
    none = _run(tmp_path, "")
    broken = _run(tmp_path, "", ps_status=1)

    assert none.returncode == 1
    assert "No container of this profile exists" in none.stdout
    assert broken.returncode == 2
    assert "could not list the containers" in broken.stderr


@needs_bash
def test_a_missing_or_unknown_profile_is_refused_before_docker_is_asked(tmp_path: Path) -> None:
    """The profile is never guessed. Delete this and a typo reads a stack the person did not
    mean, with a compose file list that is not theirs."""
    unknown = _run(tmp_path, "", profile="huge")

    assert unknown.returncode == 2
    assert "one of: lite standard full" in unknown.stderr
    assert "ok (" not in unknown.stdout


@needs_bash
def test_the_script_writes_nothing(tmp_path: Path) -> None:
    """It reads and prints. Delete this and a health check that quietly writes a file becomes a
    thing a person hesitates to run twice."""
    _run(tmp_path, "app|running|healthy|0\n")
    found = {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}

    assert found == {"bin", "bin/docker", "ps.txt", "home"}


def test_a_report_that_contains_the_end_marker_is_refused() -> None:
    """A report cannot end the heredoc early. Delete this and a sentence added to a component's
    ready_when that happens to equal the marker truncates the report silently."""
    reports = dict.fromkeys(PROFILES, "a\n")
    reports["lite"] = f"a\n{health.REPORT_END}\nb\n"

    with pytest.raises(HealthScriptError):
        render_health(reports)


def test_a_profile_without_a_report_is_refused() -> None:
    """Every profile arm has text. Delete this and a profile added to the installer prints nothing
    but live state, with no sentence on what ready means."""
    with pytest.raises(HealthScriptError):
        render_health({"lite": "a\n"})


def test_the_install_script_runs_the_health_script_last_and_does_not_fail_for_it() -> None:
    """The install script's last act is to read the health back, and a server still starting does
    not fail the install. Delete this and the one thing M42.3.4 asked for, a script run after
    deploying whose output a person reads, is a file nothing runs."""
    lines = (REPO / INSTALL_PATH).read_text(encoding="utf-8").splitlines()
    ran = [i for i, one in enumerate(lines) if one.startswith("bash ") and HEALTH_SCRIPT in one]
    done = [i for i, one in enumerate(lines) if one.startswith('say "Done.')]

    assert len(ran) == 1 and len(done) == 1 and ran[0] < done[0]
    assert lines[ran[0]].endswith("\\")
    assert lines[ran[0] + 1].lstrip().startswith("|| say ")
    assert HEALTH_SCRIPT == SCRIPT_PATH


def test_the_release_archive_carries_the_health_script() -> None:
    """The archive's `ops/install` rule covers it. Delete this and the script is in the repository
    and on no server, so the install script's last line runs a file that is not there."""
    assert included_by(SCRIPT_PATH)
