"""The step that asks docker about the running canvas, run for real against a stub `docker`.

`ops/deploy/overlays/automation.observe.sh` is shell and decides nothing, but what it prints is what
the install's checks believe, so it is run here the way `tests/unit/test_overlays.py` runs the step
that starts the services: a stub `docker` answers from files, keeps every call, and keeps what the
step hands the application on standard input. What is asserted is what leaves the host: names and
counts and never a value, a fact it cannot read said as unknown and never as the good answer, and a
canvas that is not running reported as nothing at all.

Task ids: M32.6.1.2
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from brain.ops.automation import EGRESS_ALLOWLIST
from brain.ops.automation_report import facts_from, gaps

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "deploy" / "overlays" / "automation.observe.sh"
EGRESS_CONF = REPO / "ops" / "automation" / "egress.conf"
SH = shutil.which("sh")

#: Values that must never leave the stub's files: a secret under an ordinary name, and a connection
#: string under an innocent one. Asserted absent from everything the step prints and hands over.
SECRET = "hunter2-the-canvas-secret"
CONNECTION = "postgresql://brain:application-password@db:5432/brain"

STUB = r"""#!/bin/sh
S="$STUB_STATE"
printf '%s\n' "$*" >> "$S/calls"
case "$1" in
  inspect)
    shift; fmt=""; name=""
    while [ $# -gt 0 ]; do
      case "$1" in --format) shift; fmt="$1" ;; *) name="$1" ;; esac
      shift
    done
    case "$fmt" in
      *compose.project*) echo "u"; exit 0 ;;
    esac
    case "$name" in
      u-activepieces)
        case "$fmt" in
          *Networks*) cat "$S/canvas_networks" ;;
          *Config.Env*) cat "$S/canvas_env" ;;
        esac ;;
      u-automation-egress)
        case "$fmt" in *Networks*) cat "$S/proxy_networks" ;; esac ;;
    esac
    exit 0 ;;
  ps)
    svc=""
    for a in "$@"; do
      case "$a" in
        label=com.docker.compose.service=*) svc="${a#label=com.docker.compose.service=}" ;;
      esac
    done
    [ -f "$S/running_$svc" ] && echo "u-$svc"
    exit 0 ;;
  exec)
    shift
    if [ "$1" = -i ]; then
      cat > "$S/handed"
      echo "SAY the canvas's facts are kept for this release"
      exit "$(cat "$S/hand_exit")"
    fi
    case "$*" in
      "u-activepieces cat /proc/net/route") [ -f "$S/route" ] && cat "$S/route"; exit 0 ;;
      "u-automation-egress cat /etc/squid/squid.conf") cat "$S/squid.conf"; exit 0 ;;
      "u-automation-egress timeout 10 bash -c"*) cat "$S/probe_answer"; exit 0 ;;
    esac
    exit 0 ;;
esac
exit 0
"""

ROUTE_WITHOUT_DEFAULT = (
    "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
    "eth0\t0002A8C0\t00000000\t0001\t0\t0\t0\t00FFFFFF\n"
)
ROUTE_WITH_DEFAULT = (
    "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
    "eth0\t00000000\t0102A8C0\t0003\t0\t0\t0\t00000000\n"
)


@dataclass
class Observed:
    code: int
    output: str
    handed: str
    calls: str


def observe(
    tmp_path: Path,
    *,
    running: tuple[str, ...] = ("activepieces", "automation-egress"),
    canvas_env: str | None = None,
    route: str | None = ROUTE_WITHOUT_DEFAULT,
    probe: str = "HTTP/1.1 403 Forbidden\r\n",
    hand_exit: int = 0,
) -> Observed:
    """Run the real step once against the stub, with the facts docker would give."""
    state = tmp_path / "state"
    bin_dir = tmp_path / "bin"
    state.mkdir(parents=True)
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(STUB, encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    env_text = canvas_env or (
        f"PATH=/usr/bin\nAP_JWT_SECRET={SECRET}\nAP_POSTGRES_PASSWORD={SECRET}\nNODE_VERSION=22\n"
    )
    for name, text in (
        ("canvas_networks", "u-overlays_automation\nbrain-tool-api\n"),
        ("proxy_networks", "u-overlays_automation\nu-overlays_egress\n"),
        ("canvas_env", env_text),
        ("squid.conf", EGRESS_CONF.read_text(encoding="utf-8")),
        ("probe_answer", probe),
        ("hand_exit", f"{hand_exit}\n"),
        ("calls", ""),
    ):
        (state / name).write_text(text, encoding="utf-8", newline="\n")
    if route is not None:
        (state / "route").write_text(route, encoding="utf-8", newline="\n")
    for service in running:
        (state / f"running_{service}").write_text("", encoding="utf-8")
    environment = {
        **os.environ,
        "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}",
        "STUB_STATE": state.as_posix(),
        "BRAIN_APP_CONTAINER": "app-u",
    }
    assert SH is not None
    done = subprocess.run(
        [SH, SCRIPT.as_posix()],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    handed = state / "handed"
    return Observed(
        code=done.returncode,
        output=done.stdout + done.stderr,
        handed=handed.read_text(encoding="utf-8") if handed.exists() else "",
        calls=(state / "calls").read_text(encoding="utf-8"),
    )


pytestmark = pytest.mark.skipif(SH is None, reason="the step is a POSIX shell script")


def test_the_canvas_overlay_runs_this_step_after_it_starts_and_the_image_carries_it() -> None:
    """The overlay names the script as one that runs once its services are up, the script is where
    the step looks for it, and the image's ignore file lets it through. Delete this and the step is
    written, tested and never run, which is this repository's recurring shape."""
    from brain.ops.overlays import BY_NAME, plan, render

    assert BY_NAME["automation"].after == ("automation.observe.sh",)
    assert (SCRIPT.parent / "automation.observe.sh").exists()
    ignored = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "!ops/deploy/overlays/automation.observe.sh" in ignored
    from brain.ops.overlays import Host

    host = Host(total_mib=16384, reserved_mib=0, unlimited_used_mib=0)
    lines = render(plan((BY_NAME["automation"],), host), host).splitlines()
    assert "AFTER automation.observe.sh" in lines


def test_a_running_canvas_is_reported_as_facts_that_say_it_keeps_the_boundary(
    tmp_path: Path,
) -> None:
    """The positive case, end to end: the stub's networks, names, routes, allowlist and refusal,
    handed to the application and read back by the parser into a canvas with no gap. Delete this and
    the script and the parser can disagree on a line and every canvas reads as failing, or as
    passing, on a fact nobody sent."""
    seen = observe(tmp_path)
    assert seen.code == 0, seen.output
    facts = facts_from(seen.handed.splitlines())
    assert facts.networks == ("brain-tool-api", "u-overlays_automation")
    assert facts.proxy_networks == ("u-overlays_automation", "u-overlays_egress")
    assert facts.env_names == ("AP_JWT_SECRET", "AP_POSTGRES_PASSWORD", "NODE_VERSION", "PATH")
    assert (facts.connection_strings, facts.default_routes) == (0, 0)
    assert facts.allowlist == tuple(sorted(EGRESS_ALLOWLIST))
    assert facts.probe == "HTTP/1.1 403 Forbidden"
    assert gaps(facts) == ()
    assert "kept for this release" in seen.output


def test_no_value_leaves_the_host_by_any_road(tmp_path: Path) -> None:
    """A secret under an ordinary name and a connection string under an innocent one, in the
    canvas's variables. Delete this and the step prints, hands over or logs a value, which is the
    one thing a step that reads a container's environment must never do."""
    env = f"AP_JWT_SECRET={SECRET}\nDATABASE_URL={CONNECTION}\nHARMLESS=1\n"
    seen = observe(tmp_path, canvas_env=env)
    for text in (seen.output, seen.handed, seen.calls):
        assert SECRET not in text
        assert "application-password" not in text
        assert CONNECTION not in text
    facts = facts_from(seen.handed.splitlines())
    assert facts.env_names == ("AP_JWT_SECRET", "DATABASE_URL", "HARMLESS")
    assert facts.connection_strings == 1


@pytest.mark.parametrize(
    "scheme", ["postgres", "postgresql", "postgresql+psycopg", "redis", "rediss", "amqp", "mongodb"]
)
def test_every_connection_scheme_the_policy_names_is_counted_under_any_name(
    tmp_path: Path, scheme: str
) -> None:
    """Each scheme as a value under a name that says nothing. Delete this and a scheme in the
    script's pattern can be mistyped, so a canvas holding that kind of URL reports none."""
    seen = observe(tmp_path, canvas_env=f"SOMETHING_ELSE={scheme}://user:pw@host/db\nPATH=/bin\n")
    assert facts_from(seen.handed.splitlines()).connection_strings == 1


def test_a_value_that_only_mentions_a_scheme_is_not_a_connection_string(tmp_path: Path) -> None:
    """A URL for a web page, and a value that contains the word. Delete this and the pattern counts
    every variable with `redis` in it, and a sound canvas reports a credential."""
    env = "AP_FRONTEND_URL=https://editor.example/redis://x\nNOTE=see postgres://later\n"
    seen = observe(tmp_path, canvas_env=env)
    assert facts_from(seen.handed.splitlines()).connection_strings == 0


def test_a_default_route_is_counted(tmp_path: Path) -> None:
    """Delete this and the count is read as zero whatever the table holds."""
    seen = observe(tmp_path, route=ROUTE_WITH_DEFAULT)
    assert facts_from(seen.handed.splitlines()).default_routes == 1


def test_a_routing_table_that_could_not_be_read_is_reported_unknown_and_never_zero(
    tmp_path: Path,
) -> None:
    """The container will not give its routing table. Delete this and nothing read is zero routes,
    which is the answer the check hopes for."""
    seen = observe(tmp_path, route=None)
    assert "routes|unknown" in seen.handed.splitlines()
    assert facts_from(seen.handed.splitlines()).default_routes is None


def test_a_proxy_that_answers_nothing_is_reported_as_an_empty_probe(tmp_path: Path) -> None:
    """Delete this and a probe that got no answer is reported as a refusal."""
    seen = observe(tmp_path, probe="")
    assert "probe|" in seen.handed.splitlines()
    assert facts_from(seen.handed.splitlines()).probe == ""


def test_a_proxy_that_lets_the_tunnel_through_is_reported_as_it_answered(tmp_path: Path) -> None:
    """The carriage return a proxy's reply ends with is gone and the line is its own. Delete this
    and the status carries a stray character, or a 200 is read as a 403."""
    seen = observe(tmp_path, probe="HTTP/1.1 200 Connection established\r\n")
    assert facts_from(seen.handed.splitlines()).probe == "HTTP/1.1 200 Connection established"


def test_a_canvas_or_proxy_that_is_not_running_reports_nothing_and_exits_non_zero(
    tmp_path: Path,
) -> None:
    """Delete this and a stopped canvas is reported as a canvas with empty facts, which the check
    reads as a canvas that was inspected."""
    for running in ((), ("activepieces",), ("automation-egress",)):
        seen = observe(tmp_path / "_".join(running or ("none",)), running=running)
        assert seen.code == 1
        assert seen.handed == ""
        assert "nothing to report" in seen.output


def test_a_report_the_application_could_not_keep_is_said_and_exits_non_zero(
    tmp_path: Path,
) -> None:
    """Delete this and a failed hand-over is a deploy that believes the checks have facts."""
    seen = observe(tmp_path, hand_exit=1)
    assert seen.code == 1
    assert "kept for this release" in seen.output


def test_the_step_reads_the_proxy_s_file_and_the_canvas_s_table_and_changes_nothing(
    tmp_path: Path,
) -> None:
    """Every docker call the step makes, by verb. Delete this and a step that stops, restarts,
    connects or removes something to see it better passes."""
    seen = observe(tmp_path)
    verbs = {line.split()[0] for line in seen.calls.splitlines() if line.strip()}
    assert verbs <= {"inspect", "ps", "exec"}
    assert "exec u-activepieces cat /proc/net/route" in seen.calls
    assert "exec u-automation-egress cat /etc/squid/squid.conf" in seen.calls
    assert not [line for line in seen.calls.splitlines() if " rm" in line or " stop" in line]
