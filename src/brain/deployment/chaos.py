"""The failure rehearsal a person runs on a throwaway install: stop one thing at a time and read
what the product does, as a file they can read and run on the server.

`brain.ops.reliability.MATRIX` says what each component's failure looks like and what to do, and
`brain.ops.crash` and `brain.ops.recovery_run` decide what is resumed, and nothing ever stopped a
component on a running install to see whether the sentences are true. M30.4.3 asks for that: kill
the database, a model provider, a connector, the browser and the worker, one at a time, and record
what the product did. This renders the script, `ops/chaos/chaos.sh`, from a table of the five
faults, and holds the table to the matrix.

**What CI proves and what only a person can.** CI proves the table (every fault names a component
the matrix covers or a container the browser launcher labels, and every fault names the in-process
tests that prove the product's side of it, which must exist), proves the committed script is what
the renderer prints, and *runs* the script against a stand-in for Docker to prove how it reasons:
what it refuses, what it stops, what it starts again, what it counts as a failure and what it
exits with. **What nothing here shows is a real container stopping on a real server and the
product coming back**: that is the first run of the script on a throwaway install, and the
progress note for M30.4.3 says it is a person's step. A rehearsal that reports itself proved
because its stand-in passed would be the failure this file exists to catch.

**It measures three things per fault and judges two.** While a component is down the application
must still answer liveness, because a process that dies with its dependency is a crash loop that
hides the dependency's name; and, after the component starts, the application must report ready
again within a wait the person chooses. Both are judged. The third, what readiness said while the
component was down, is judged for the database only (readiness that stays ready with the database
stopped is the failure `/health/ready` exists to prevent) and is otherwise recorded beside what the
matrix says the outage presents as, because the matrix itself says several of them present as
nothing, and a script that required a failing readiness for the worker would be contradicting
the row it prints.

**Nothing is stopped unless the person says the install is disposable.** The flag is long on
purpose. The script also starts again whatever it stopped, on any exit, so a person who interrupts
it does not leave a database down. Rejected: running the faults from inside the application, which
cannot stop its own database and would need the container socket; and a fault injected by the
product's own test doubles on the install, which proves the double.

**A fault the profile cannot make is skipped and said so.** The model server runs in no profile of
its own and the egress proxy only in the full one, and a run that read "all faults passed" over two
skipped would be rounding up. The summary counts ran, passed, failed and skipped, and a run in which
nothing ran exits with its own status.

Task ids: M30.4.3
"""

from __future__ import annotations

import ast
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from brain.browsing.sandbox import RUN_LABEL
from brain.deployment.installer import INSTALL_HOME, compose_files_argument
from brain.ops.reliability import MATRIX, FailureMode, all_components
from brain.ops.wiring import PROFILES, assert_known_profile

#: Where the committed printout of this module lives, relative to the repository root.
SCRIPT_PATH: Final = "ops/chaos/chaos.sh"

#: How the application reads while the database is down: not ready.
DOWN_NOT_READY: Final = "not-ready"

#: How the application reads while any other component is down: whatever it reads, recorded.
DOWN_RECORDED: Final = "recorded"

#: The seconds after a start that the application is given to report ready again, unless the
#: person names another. A starting position and not a requirement, like every figure in
#: `brain.ops.reliability`: an install with a large database takes longer to open it.
RECOVERY_WAIT_SECONDS: Final = 180

#: The seconds after a stop that the script waits for readiness to fail, for the database.
DOWN_WAIT_SECONDS: Final = 30

#: The flag that says the install may be broken on purpose.
DISPOSABLE_FLAG: Final = "--this-install-is-disposable"

#: Why the flag is as long as it is.
A_RUN_STOPS_REAL_SERVICES_SO_THE_PERSON_SAYS_THE_INSTALL_MAY_BE_BROKEN: Final = (
    "The script stops the database, the worker and the rest of a running install. On the wrong "
    "server that is an outage with a person's name on it, so it does nothing until it is told in "
    "words that the install is disposable, and it starts again whatever it stopped on any exit."
)


class ChaosError(Exception):
    """The script could not be rendered as asked."""


@dataclass(frozen=True)
class Fault:
    """One component stopped on purpose, and everything the script and its readers need.

    Exactly one of `service` and `label` is set: a compose service is stopped by name, and the
    browser's containers are made per run by the launcher and found by the label it puts on them.
    """

    name: str
    #: The compose service stopped, or None for a fault found by label.
    service: str | None
    #: The label a container carries, killed where found, or None for a compose service.
    label: str | None
    #: The `MATRIX` row whose `presents_as` and `response` are printed, or None when the row is not
    #: a compose component (the browser's containers are made on demand).
    component: str | None
    #: `DOWN_NOT_READY` or `DOWN_RECORDED`.
    while_down: str
    #: What a real outage looks like, for a fault whose component has no matrix row.
    presents_as_here: str
    #: What the person checks by hand afterwards, which the script cannot.
    follow_up: str
    #: Why the fault is skipped where its target is not running.
    skipped_because: str
    #: Tests in this repository that prove the product's side of the fault in-process, as
    #: `path::function`. Each must exist: a name here is a claim.
    in_ci: tuple[str, ...]


#: The five faults M30.4.3 names. Order is the order they are run in: the least disruptive first,
#: and the database last, because everything else reads through it.
FAULTS: Final[tuple[Fault, ...]] = (
    Fault(
        name="browser",
        service=None,
        label=RUN_LABEL,
        component=None,
        while_down=DOWN_RECORDED,
        presents_as_here=(
            "a browsing run ends without its result, and its sandbox containers are left behind "
            "carrying the run label until the launcher sweeps them at its next start"
        ),
        follow_up=(
            "start a browsing task, kill its containers again, then start another and confirm the "
            "first is shown as ended and its leftovers are gone"
        ),
        skipped_because="no browsing run was in flight, so there is nothing to kill",
        in_ci=(
            "tests/unit/test_browsing_launcher.py::"
            "test_the_docker_adapter_finds_leftovers_by_the_run_label",
        ),
    ),
    Fault(
        name="connector",
        service="automation-egress",
        label=None,
        component="automation-egress",
        while_down=DOWN_RECORDED,
        presents_as_here="",
        follow_up=(
            "run a flow that calls a connector while the proxy is stopped, then confirm the step "
            "failed closed and that the operation record, not the canvas, says whether it reached "
            "its source"
        ),
        skipped_because="the egress proxy runs only in the full profile",
        in_ci=(
            "tests/unit/test_connectors.py::"
            "test_a_degraded_connector_is_still_usable_and_a_down_one_is_not",
        ),
    ),
    Fault(
        name="provider",
        service="inference-server",
        label=None,
        component="inference-server",
        while_down=DOWN_RECORDED,
        presents_as_here="",
        follow_up=(
            "ask a question while the model server is stopped and confirm the answer falls to the "
            "next step of the ladder or says plainly that it could not be composed, and that the "
            "Models screen shows the step as unhealthy afterwards"
        ),
        skipped_because="the model server is started by its own compose file, which an install may not have added",
        in_ci=(
            "tests/unit/test_model_calls.py::test_every_rung_failing_raises_the_last_failure",
            "tests/unit/test_health.py::test_a_provider_outage_is_degraded_rather_than_failed",
        ),
    ),
    Fault(
        name="worker",
        service="brain-worker",
        label=None,
        component="brain-worker",
        while_down=DOWN_RECORDED,
        presents_as_here="",
        follow_up=(
            "queue a job, stop the worker before it finishes, start it again, and confirm the "
            "job was put back only if its task is declared safe, and set aside for a person if not"
        ),
        skipped_because="the worker runs in the standard and full profiles",
        in_ci=(
            "tests/unit/test_recovery_run.py::"
            "test_an_orphaned_job_its_task_declares_safe_is_put_back_on_its_queue",
            "tests/unit/test_recovery_run.py::"
            "test_an_orphaned_job_nobody_declared_safe_is_set_aside_and_never_run_again",
        ),
    ),
    Fault(
        name="db",
        service="db",
        label=None,
        component="db",
        while_down=DOWN_NOT_READY,
        presents_as_here="",
        follow_up=(
            "confirm no request was answered from the cache while the database was down, and that "
            "nothing written during the outage is missing or doubled afterwards"
        ),
        skipped_because="the database is in every profile, so this is an install that is not up",
        in_ci=(
            "tests/unit/test_app.py::test_readiness_fails_when_any_dependency_is_unreachable",
            "tests/unit/test_app.py::test_liveness_stays_ok_while_readiness_fails",
        ),
    ),
)


def _functions_in(path: Path) -> frozenset[str]:
    """Every function and method defined in a Python file, by name."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return frozenset(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def fault_gaps(
    faults: Sequence[Fault] | None = None,
    matrix: Sequence[FailureMode] | None = None,
    components: Sequence[str] | None = None,
    root: Path | None = None,
) -> tuple[str, ...]:
    """Every way the table of faults stops being the five M30.4.3 names, held to the matrix.

    Findings: a name that is missing or repeated, a fault with both or neither of a service and a
    label, a component the matrix has no row for, a service nothing deploys, a fault without a
    sentence for a reader, and an in-process test it names that is not there.
    """
    declared = FAULTS if faults is None else tuple(faults)
    rows = {one.component for one in (MATRIX if matrix is None else tuple(matrix))}
    known = set(all_components() if components is None else components)
    repo = root if root is not None else Path(__file__).resolve().parents[3]
    findings: list[str] = []

    seen: dict[str, int] = {}
    for one in declared:
        seen[one.name] = seen.get(one.name, 0) + 1
    findings.extend(
        f"{name}: {count} faults carry this name"
        for name, count in sorted(seen.items())
        if count > 1
    )
    findings.extend(
        f"{name}: the chaos suite names no fault for it"
        for name in sorted(REQUIRED_FAULTS - set(seen))
    )

    for one in declared:
        if (one.service is None) == (one.label is None):
            findings.append(
                f"{one.name}: must name a compose service or a label, and not both or neither"
            )
        if one.service is not None and one.service not in known:
            findings.append(f"{one.name}: stops {one.service!r}, which nothing deploys")
        if one.component is not None and one.component not in rows:
            findings.append(f"{one.name}: {one.component!r} has no failure mode in the matrix")
        if one.component is None and not one.presents_as_here.strip():
            findings.append(f"{one.name}: has no matrix row and says nothing of what it looks like")
        if one.while_down not in (DOWN_NOT_READY, DOWN_RECORDED):
            findings.append(f"{one.name}: reads {one.while_down!r} while down, which is neither")
        for field in ("follow_up", "skipped_because"):
            if not getattr(one, field).strip():
                findings.append(f"{one.name}: states no {field}")
        if not one.in_ci:
            findings.append(f"{one.name}: names no in-process test, so CI proves nothing of it")
        for ident in one.in_ci:
            file, _, function = ident.partition("::")
            path = repo / file
            if not path.is_file():
                findings.append(f"{one.name}: {ident} names a file that is not there")
            elif function not in _functions_in(path):
                findings.append(f"{one.name}: {ident} names a test that is not there")
    return tuple(findings)


#: The five components the owner's brief names, and so the five the table must hold.
REQUIRED_FAULTS: Final[frozenset[str]] = frozenset(
    {"db", "provider", "connector", "browser", "worker"}
)


def _reading(one: Fault, matrix: Sequence[FailureMode]) -> tuple[str, str]:
    """What a real outage presents as and what to do about it, from the matrix where there is a row."""
    if one.component is None:
        return (
            one.presents_as_here,
            "see ops/browser/REHEARSAL.md; the launcher removes everything carrying the run label at its next start",
        )
    for row in matrix:
        if row.component == one.component:
            return row.presents_as, row.response
    msg = f"{one.name!r} names {one.component!r}, which the matrix has no row for"
    raise ChaosError(msg)


def _q(text: str) -> str:
    return shlex.quote(text)


def _fault_arm(one: Fault, matrix: Sequence[FailureMode]) -> tuple[str, ...]:
    presents, response = _reading(one, matrix)
    return (
        f"    {one.name})",
        f"      F_SERVICE={_q(one.service or '')}; F_LABEL={_q(one.label or '')}",
        f"      F_DOWN={_q(one.while_down)}",
        f"      F_PRESENTS={_q(presents)}",
        f"      F_RESPONSE={_q(response)}",
        f"      F_FOLLOW={_q(one.follow_up)}",
        f"      F_WHY_SKIPPED={_q(one.skipped_because)}",
        "      ;;",
    )


def _run_lines() -> tuple[str, ...]:
    """The part of the script that makes a fault and judges it. Hand-written, then tested by being run."""
    return (
        "probe() {",
        "  docker compose $BRAIN_COMPOSE_FILES exec -T app python - \"$1\" 2>/dev/null <<'PY' || echo 0",
        "import sys, urllib.error, urllib.request",
        "try:",
        '    print(urllib.request.urlopen("http://127.0.0.1:8000" + sys.argv[1], timeout=4).status)',
        "except urllib.error.HTTPError as error:",
        "    print(error.code)",
        "except Exception:",
        "    print(0)",
        "PY",
        "}",
        "",
        "start_again() {",
        '  if test -n "$CURRENT_IDS"; then',
        "    docker start $CURRENT_IDS >/dev/null 2>&1",
        '    CURRENT_IDS=""',
        "  fi",
        "}",
        "trap start_again EXIT",
        "trap 'exit 130' INT TERM HUP",
        "",
        "run_fault() {",
        '  load_fault "$1"',
        '  echo "== $1"',
        '  echo "   A real outage presents as: $F_PRESENTS"',
        '  echo "   What to do about it: $F_RESPONSE"',
        '  if test -n "$F_SERVICE"; then',
        '    ids="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" '
        '--filter "label=com.docker.compose.service=$F_SERVICE")"',
        "  else",
        '    ids="$(docker ps -q --filter "label=$F_LABEL")"',
        "  fi",
        '  if test -z "$ids"; then',
        '    echo "   SKIPPED: no running container to stop ($F_WHY_SKIPPED)"',
        "    skipped=$((skipped + 1))",
        "    return",
        "  fi",
        '  if test -n "$F_SERVICE"; then',
        '    CURRENT_IDS="$ids"',
        "    docker stop $ids >/dev/null 2>&1 \\",
        '      || { echo "   NOT RUN: it could not be stopped"; failed=$((failed + 1)); return; }',
        "  else",
        "    docker kill $ids >/dev/null 2>&1 \\",
        '      || { echo "   NOT RUN: the containers could not be killed"; failed=$((failed + 1)); return; }',
        "  fi",
        "  ran=$((ran + 1))",
        "  verdict=ok",
        '  live="$(probe /health/live)"',
        '  ready="$(probe /health/ready)"',
        '  if test "$F_DOWN" = not-ready; then',
        "    started=$SECONDS",
        '    while test "$ready" = 200 && test $((SECONDS - started)) -lt "$DOWN_WAIT"; do',
        '      sleep "$POLL_SECONDS"',
        '      ready="$(probe /health/ready)"',
        "    done",
        '    if test "$ready" = 200; then',
        '      echo "   FAILED: readiness still said ready after ${DOWN_WAIT}s with it stopped"',
        "      verdict=failed",
        "    fi",
        "  fi",
        '  echo "   while down: liveness $live, readiness $ready"',
        '  if test "$live" != 200; then',
        '    echo "   FAILED: the application stopped answering liveness while it was down"',
        "    verdict=failed",
        "  fi",
        '  if test -n "$F_SERVICE"; then',
        "    docker start $ids >/dev/null 2>&1 \\",
        '      || echo "   could not start it again; start it by hand"',
        '    CURRENT_IDS=""',
        "  fi",
        "  started=$SECONDS",
        '  ready="$(probe /health/ready)"',
        '  while test "$ready" != 200 && test $((SECONDS - started)) -lt "$RECOVER_WITHIN"; do',
        '    sleep "$POLL_SECONDS"',
        '    ready="$(probe /health/ready)"',
        "  done",
        '  if test "$ready" = 200; then',
        '    echo "   recovered: ready again after $((SECONDS - started))s (limit ${RECOVER_WITHIN}s)"',
        "  else",
        '    echo "   FAILED: not ready ${RECOVER_WITHIN}s after it was started again"',
        "    verdict=failed",
        "  fi",
        '  echo "   Check by hand: $F_FOLLOW"',
        '  if test "$verdict" = ok; then',
        "    passed=$((passed + 1))",
        "  else",
        "    failed=$((failed + 1))",
        "  fi",
        "}",
    )


def render_chaos(
    *,
    faults: Sequence[Fault] | None = None,
    matrix: Sequence[FailureMode] | None = None,
    home: str = INSTALL_HOME,
    profiles: Sequence[str] = PROFILES,
) -> str:
    """The rehearsal script, for every profile, with each fault's reading written in."""
    declared = FAULTS if faults is None else tuple(faults)
    rows = MATRIX if matrix is None else tuple(matrix)
    gaps = fault_gaps(declared, rows)
    if gaps:
        msg = "the table of faults has gaps, so no script is rendered: " + "; ".join(gaps)
        raise ChaosError(msg)
    names = " ".join(one.name for one in declared)
    arms = []
    for profile in profiles:
        assert_known_profile(profile)
        arms.append(
            f'  {profile}) BRAIN_COMPOSE_FILES="{compose_files_argument(profile, home=home)}" ;;'
        )
    lines = [
        "#!/bin/bash",
        "# Generated by brain.deployment.chaos.render_chaos. Do not edit: edit the table of faults",
        "# and regenerate, or this script and the table disagree and the table is the tested one.",
        "# Stops one component of a running install at a time, reads what the application does",
        "# while it is down and whether it recovers, and starts it again. Run it only on an",
        "# install that may be broken on purpose.",
        "set -uo pipefail",
        "",
        f'BRAIN_HOME="${{BRAIN_HOME:-{home}}}"',
        'POLL_SECONDS="${BRAIN_CHAOS_POLL_SECONDS:-5}"',
        'BRAIN_PROFILE=""',
        f"RECOVER_WITHIN={RECOVERY_WAIT_SECONDS}",
        f'DOWN_WAIT="${{BRAIN_CHAOS_DOWN_WAIT:-{DOWN_WAIT_SECONDS}}}"',
        "DISPOSABLE=no",
        'WANTED=""',
        'CURRENT_IDS=""',
        "ran=0; passed=0; failed=0; skipped=0",
        "",
        "usage() {",
        f'  echo "usage: chaos.sh --profile <{"|".join(profiles)}> {DISPOSABLE_FLAG} '
        f'[--fault <{"|".join(one.name for one in declared)}>]... [--recover-within SECONDS]" >&2',
        "}",
        "",
        'while test "$#" -gt 0; do',
        '  case "$1" in',
        '    --profile) BRAIN_PROFILE="${2:-}"; shift 2 ;;',
        '    --fault) WANTED="$WANTED ${2:-}"; shift 2 ;;',
        '    --recover-within) RECOVER_WITHIN="${2:-}"; shift 2 ;;',
        f"    {DISPOSABLE_FLAG}) DISPOSABLE=yes; shift ;;",
        '    *) usage; echo "unknown option: $1" >&2; exit 2 ;;',
        "  esac",
        "done",
        "",
        'if test "$DISPOSABLE" != yes; then',
        "  usage",
        '  echo "this stops real services of a running install, so it does nothing until it is told '
        f'the install may be broken on purpose with {DISPOSABLE_FLAG}" >&2',
        "  exit 2",
        "fi",
        "",
        'case "$BRAIN_PROFILE" in',
        *arms,
        f'  *) usage; echo "--profile is required, and one of: {" ".join(profiles)}" >&2; exit 2 ;;',
        "esac",
        "",
        'case "$RECOVER_WITHIN" in',
        '  ""|*[!0-9]*|0) usage; echo "--recover-within is a whole number of seconds, at least 1" >&2; exit 2 ;;',
        "esac",
        "",
        'test -n "$WANTED" || WANTED=" ' + names + '"',
        "for one in $WANTED; do",
        '  case "$one" in',
        f"    {'|'.join(one.name for one in declared)}) ;;",
        f'    *) usage; echo "unknown fault: $one; the faults are: {names}" >&2; exit 2 ;;',
        "  esac",
        "done",
        "",
        "load_fault() {",
        '  case "$1" in',
        *(line for one in declared for line in _fault_arm(one, rows)),
        "  esac",
        "}",
        "",
        'cd "$BRAIN_HOME" || { echo "cannot enter $BRAIN_HOME" >&2; exit 2; }',
        "",
        *_run_lines(),
        "",
        'app_id="$(docker compose $BRAIN_COMPOSE_FILES ps -q app 2>/dev/null)"',
        'PROJECT="$(docker inspect -f \'{{index .Config.Labels "com.docker.compose.project"}}\' "$app_id" 2>/dev/null)"',
        'if test -z "$app_id" || test -z "$PROJECT"; then',
        '  echo "the application container of this profile is not found, so which compose project '
        'this install is cannot be told, and nothing is stopped" >&2',
        "  exit 1",
        "fi",
        'live="$(probe /health/live)"; ready="$(probe /health/ready)"',
        'if test "$live" != 200 || test "$ready" != 200; then',
        '  echo "the application is not live and ready before any fault (liveness $live, readiness $ready), so a fault would teach nothing" >&2',
        "  exit 1",
        "fi",
        "",
        "for one in $WANTED; do",
        '  run_fault "$one"',
        "done",
        "",
        'echo ""',
        'echo "ran $ran: $passed passed, $failed failed; $skipped skipped"',
        'if test "$failed" -gt 0; then',
        "  exit 1",
        "fi",
        'if test "$ran" -eq 0; then',
        '  echo "nothing was run, so nothing is shown" >&2',
        "  exit 3",
        "fi",
        "exit 0",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Print the script, which is how the committed file under `ops/chaos/` is produced."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print(f"usage: python -m {__name__}", file=sys.stderr)
        return 2
    print(render_chaos(), end="")
    return 0


if __name__ == "__main__":  # pragma: no cover - the command that writes the committed script
    raise SystemExit(main())
