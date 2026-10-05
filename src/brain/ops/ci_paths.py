"""Which of CI's path-scoped jobs a pull request's diff can affect, as the `changes` job's outputs.

Measured on 2026-09-30 over the last 50 pull-request runs: 3,172 runner minutes, on the free plan's
20 concurrent jobs, so every pull request queued behind the one before it. Four jobs read a narrow,
nameable set of files and ran on every pull request regardless: the dependency audit (lock files 1
of 30 diffs), the vulnerability scan (1 of 30), the personal data analyser (0 of 30) and, less
narrowly, the console's own suite. Each is given a filter here, and `changes` prints one output per
filter that the job's `if` reads.

**A filter is the files the job reads, and every pattern must name a file that exists.** A job
switched off by a pattern pointing where a file used to be passes as skipped, and a skipped job
passes a required check, so a moved lock file would quietly stop the audit. `tests/unit/
test_ci_paths.py` holds every pattern to at least one tracked file, and holds each job's `if` to
its filter's output. See `A_FILTER_NAMES_WHAT_ITS_JOB_READS_AND_EVERY_NAME_EXISTS`.

**Anything uncertain runs everything.** A diff that cannot be computed, or an empty one, makes every
output true, as `changes` already does for `tasks_only`; and this file and the workflow are in every
filter, so a change to the filters runs the jobs they gate.

**Main is not filtered.** Every job here is already pull-request-only; the jobs a deploy depends on
are untouched. The vulnerability scan also runs nightly on main (`.github/workflows/nightly.yml`),
because a new advisory arrives with no change to any file.

**Standard library only**, because the `changes` job runs it with the runner's own Python before
any environment is built, which is what keeps that job a few seconds long.

Rejected: skipping the unit shards when no Python changed. The Python tests read the console's
source, the documents, the realm, the compose files and this workflow, so a diff with no Python in
it is not a diff the suite cannot see. Selecting the suite is being measured in shadow instead.
No leaf names CI's cost.

Task ids: none
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

#: Why the patterns are held to the tree.
A_FILTER_NAMES_WHAT_ITS_JOB_READS_AND_EVERY_NAME_EXISTS: Final = (
    "A filter decides whether a required job runs, and a skipped job passes a required check. So "
    "each filter lists the files its job reads, every pattern matches at least one tracked file, "
    "and a pattern whose file moved fails the build rather than switching the job off in silence."
)

#: In every filter: a change to the filters or to the workflow runs every job they gate.
ALWAYS: Final[tuple[str, ...]] = (".github/workflows/ci.yml", "src/brain/ops/ci_paths.py")

_LOCKS: Final[tuple[str, ...]] = (
    "uv.lock",
    "pyproject.toml",
    "matcher/uv.lock",
    "matcher/pyproject.toml",
    "console/package.json",
    "console/package-lock.json",
    "ops/automation/piece/package.json",
    "ops/automation/piece/package-lock.json",
)

#: The files each path-scoped job reads, as `fnmatch` patterns over repository paths. `*` crosses
#: directories, so `console/*` is everything under the console.
FILTERS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        # `brain.ops.sweeps dependencies` and `brain.ops.dependency_policy`: every lock, and every
        # image a compose file names, whose terms the policy reads.
        "dependencies": (
            *_LOCKS,
            "docker-compose*.yml",
            "Dockerfile",
            "src/brain/ops/dependency_policy.py",
            "src/brain/ops/sweeps.py",
        ),
        # Trivy over every lock in the tree and over the image the Dockerfile builds, judged by
        # `brain.ops.vulnerabilities` against its recorded exceptions.
        "image": (
            *_LOCKS,
            "Dockerfile",
            ".dockerignore",
            "ops/security/vulnerability-exceptions.json",
            "src/brain/ops/vulnerabilities.py",
        ),
        # The analyser's job validates the one-file full profile and starts the analyser from
        # its compose file; it runs no product code.
        "presidio": ("docker-compose*.yml",),
        # The console's typecheck, tests and build: its own tree, the document generated from the
        # live application, and the repository files its tests read (the audit, the WBS, the
        # realm, the design notes).
        "console": (
            "console/*",
            "src/*",
            "migrations/*",
            "docs/*",
            "ops/keycloak/*",
            "pyproject.toml",
            "uv.lock",
        ),
    }
)


def affected(changed: Sequence[str] | None) -> dict[str, bool]:
    """For each filter, whether this diff can affect its job. Everything, when the diff is unknown.

    None or an empty list is a diff nobody could compute, and runs every job.
    """
    if not changed:
        return dict.fromkeys(FILTERS, True)
    return {
        name: any(
            fnmatch.fnmatchcase(path, pattern)
            for path in changed
            for pattern in (*patterns, *ALWAYS)
        )
        for name, patterns in FILTERS.items()
    }


def changed_files(base: str, head: str) -> list[str] | None:
    """The paths `git diff --name-only base head` names, or None when git cannot say."""
    # A push that opens a branch names forty zeros, which git refuses below like any other
    # revision it does not hold.
    if not base:
        return None
    done = subprocess.run(  # noqa: S603  two commit ids from the workflow's own context, no shell
        ["git", "diff", "--name-only", base, head],  # noqa: S607  git on PATH, as elsewhere here
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        return None
    return [line for line in done.stdout.splitlines() if line.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    """Print `name=true|false` per filter, the lines `changes` appends to `$GITHUB_OUTPUT`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args(argv)
    for name, runs in affected(changed_files(args.base, args.head)).items():
        print(f"{name}={'true' if runs else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
