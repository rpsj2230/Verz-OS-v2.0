"""The health check a person runs after deploying, as a file they can read and run on the server.

`brain.deployment.installer.health_report` has said for a long time what a person should check
after deploying and what ready means for each component, and nothing ever ran it: the install
script's last numbered step polls `/health/ready` once and goes quiet, so a service that is up and
unhealthy, or finished with a non-zero exit, was found by the person who ran `docker compose ps`
because something else broke. M42.3.4 asks for a script somebody runs and can read the output of.
This renders that script, `ops/install/health.sh`, and the install script runs it as its last act.

**One printed file with the report baked in, not a command that imports the product.** The
server that runs the installer has Docker and bash and nothing else, and the product image does
not carry the compose files, which are what `health_report` reads. So the report is rendered for
each profile here, from the same function, and written into the script; the script adds what only
the server can know, which is the state of each container now. `test_deployment_health.py` holds the
committed file byte-identical to this render and each embedded report equal to `health_report`, so
the sentences a person reads are the ones the module that declares readiness produces, and not a
copy that drifts. Rejected: running `python -m brain.deployment.installer` inside the image, which
needs the compose files copied into it for no purpose but this.

**Liveness is not reported as health.** A container is ok when it is running and its own
healthcheck says healthy (or it declares none and the report already said so), or when it is a
one-shot that exited with 0. Anything else, including `running` with `starting` or `unhealthy`,
is printed as NOT READY with the state it is in, and the script exits 1. The application's
readiness is asked the same way the installer's wait step asks it, because a running container
whose dependencies are unreachable is the case this exists for.

**It prints, and it changes nothing.** No container is started, restarted or removed, and no file
is written. A person can run it as often as they like.

Task ids: M42.3.4
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from typing import Final

from brain.deployment.installer import INSTALL_HOME, compose_files_argument, health_report
from brain.ops.compose import ComposeFiles
from brain.ops.wiring import PROFILES, assert_known_profile

#: Where the committed printout of this module lives, relative to the repository root. Beside the
#: install script, which runs it, so the archive carries both by the rule that carries one.
SCRIPT_PATH: Final = "ops/install/health.sh"

#: The line that ends an embedded report. A report containing it would end early.
REPORT_END: Final = "BRAIN_HEALTH_REPORT_END"

#: Why the script reads the state of every container and not only whether the app answers.
A_RUNNING_CONTAINER_IS_NOT_A_READY_ONE: Final = (
    "A container is `running` the instant its process starts, whether or not it has finished "
    "starting, and the application answers `/health/ready` from whatever it can still reach. So "
    "the one probe the install script made could pass while the trace ledger, the object store "
    "or the model server was still starting or had stopped. The script reads each container's own "
    "healthcheck state and exit code, and calls only a healthy container, or a one-shot that "
    "exited 0, ok."
)


class HealthScriptError(Exception):
    """The script could not be rendered as asked."""


def _live_lines() -> tuple[str, ...]:
    """The part of the script that asks Docker what each container is doing now."""
    return (
        'echo "Now, on this server:"',
        'echo ""',
        'cd "$BRAIN_HOME" || { echo "cannot enter $BRAIN_HOME" >&2; exit 2; }',
        'states="$(docker compose $BRAIN_COMPOSE_FILES ps --all --format '
        "'{{.Service}}|{{.State}}|{{.Health}}|{{.ExitCode}}')\" \\",
        '  || { echo "docker compose could not list the containers, so nothing can be '
        'said about them" >&2; exit 2; }',
        "problems=0",
        "total=0",
        "while IFS='|' read -r service state health exitcode; do",
        '  test -n "$service" || continue',
        "  total=$((total + 1))",
        '  if test "$state" = running && { test -z "$health" || test "$health" = healthy; }; then',
        '    echo "$service: ok (running${health:+, $health})"',
        '  elif test "$state" = exited && test "$exitcode" = 0; then',
        '    echo "$service: ok (finished, exit 0)"',
        "  else",
        '    detail="${state:-unknown}${health:+, $health}"',
        '    if test -n "$exitcode" && test "$exitcode" != 0; then',
        '      detail="$detail, exit $exitcode"',
        "    fi",
        '    echo "$service: NOT READY ($detail)"',
        "    problems=$((problems + 1))",
        "  fi",
        'done <<< "$states"',
        'if test "$total" -eq 0; then',
        '  echo "No container of this profile exists on this server. Has it been started?"',
        "  problems=$((problems + 1))",
        "fi",
        'echo ""',
        "if docker compose $BRAIN_COMPOSE_FILES exec -T app python -c "
        "'import urllib.request,sys; "
        'sys.exit(0 if urllib.request.urlopen("http://127.0.0.1:8000/health/ready",'
        "timeout=4).status==200 else 1)' >/dev/null 2>&1; then",
        '  echo "application readiness: ok"',
        "else",
        '  echo "application readiness: NOT READY (the application does not report ready, or '
        'cannot be asked)"',
        "  problems=$((problems + 1))",
        "fi",
        'echo ""',
        'if test "$problems" -eq 0; then',
        '  echo "Everything this profile starts is ready."',
        "  exit 0",
        "fi",
        'echo "$problems thing(s) are not ready. Read the lines above marked NOT READY, then '
        '\\`docker compose $BRAIN_COMPOSE_FILES logs <service>\\` for that service."',
        "exit 1",
    )


def render_health(
    reports: Mapping[str, str], *, home: str = INSTALL_HOME, profiles: Sequence[str] = PROFILES
) -> str:
    """The health script for every profile, with each profile's report written in.

    `reports` maps a profile to `health_report`'s text for it, passed rather than computed for
    the reason `brain.deployment.install_script.render_install` takes figures: rendering is not a
    good enough excuse to read a compose file.
    """
    arms: list[str] = []
    bodies: list[str] = []
    for profile in profiles:
        assert_known_profile(profile)
        report = reports.get(profile)
        if report is None:
            msg = f"{profile!r} has no report to write into the script"
            raise HealthScriptError(msg)
        if any(line == REPORT_END for line in report.splitlines()):
            msg = f"the report for {profile!r} contains the line that ends a report"
            raise HealthScriptError(msg)
        arms.append(
            f'  {profile}) BRAIN_COMPOSE_FILES="{compose_files_argument(profile, home=home)}" ;;'
        )
        bodies.extend(
            (
                f"  {profile})",
                f"    cat <<'{REPORT_END}'",
                report.rstrip("\n"),
                REPORT_END,
                "    ;;",
            )
        )
    names = " ".join(profiles)
    lines = [
        "#!/bin/bash",
        "# Generated by brain.deployment.health.render_health. Do not edit: edit the plan or the",
        "# report and regenerate, or this script and the plan disagree and the plan is the tested",
        "# one.",
        "# Prints what to check after deploying and what each check means, then the state of every",
        "# container now. Changes nothing, and exits 1 if anything is not ready.",
        "set -uo pipefail",
        "",
        f'BRAIN_HOME="${{BRAIN_HOME:-{home}}}"',
        'BRAIN_PROFILE=""',
        "",
        "usage() {",
        f'  echo "usage: health.sh --profile <{names.replace(" ", "|")}>" >&2',
        "}",
        "",
        'while test "$#" -gt 0; do',
        '  case "$1" in',
        '    --profile) BRAIN_PROFILE="${2:-}"; shift 2 ;;',
        '    *) usage; echo "unknown option: $1" >&2; exit 2 ;;',
        "  esac",
        "done",
        "",
        'case "$BRAIN_PROFILE" in',
        *arms,
        f'  *) usage; echo "--profile is required, and one of: {names}" >&2; exit 2 ;;',
        "esac",
        "",
        'case "$BRAIN_PROFILE" in',
        *bodies,
        "esac",
        'echo ""',
        "",
        *_live_lines(),
    ]
    return "\n".join(lines) + "\n"


def reports_for(files: ComposeFiles, profiles: Sequence[str] = PROFILES) -> dict[str, str]:
    """`health_report` for every profile, each over the compose files that profile composes."""
    from brain.deployment.requirements import files_for

    return {
        profile: health_report(profile, {name: files[name] for name in files_for(profile)})
        for profile in profiles
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Print the script, which is how the committed file under `ops/install/` is produced."""
    from brain.deployment.release import REPO, compose_documents

    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print(f"usage: python -m {__name__}", file=sys.stderr)
        return 2
    print(render_health(reports_for(compose_documents(REPO))), end="")
    return 0


if __name__ == "__main__":  # pragma: no cover - the command that writes the committed script
    raise SystemExit(main())
