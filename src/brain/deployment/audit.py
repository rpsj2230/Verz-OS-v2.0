"""The half of the client-independence audit that reads what nothing else reads.

M42.4.1 asks for an audit of source, configuration, compose, environment files and git history.
`brain.ops.independence` already covers source and compose, and is a hard gate over `src`,
`migrations`, `console/src` and `docs`. **The other three are not covered anywhere, and the
first run of this module found the first client's server in eight files.**

**What is outside `SEARCHED` is not a smaller area, it is the area with the values in it.**
`.env.example` is the one file `docs/repository-map.md` says an install copies, and it carried
this deployment's host name, its address and its deployment identifier under `DEPLOY_HOST`,
`DEPLOY_UUID` and `DEPLOY_URL`. `ops/keycloak/realm-export.json` is the realm every client's
Keycloak is built from, and it names this deployment's callback URL as a redirect URI, its
origin as a web origin and its address in two logout attributes. `brain.install` declares
`INSTALL_OIDC_REDIRECT_URIS` as required with no default precisely so that a guessed redirect
cannot happen, and a realm file with the value written into it walks straight past that
declaration: the sweep reads `src`, the realm is JSON in `ops`, and the two never meet.

**Those two areas are now the sweep's, and this module gave them up rather than keeping a
second opinion about them.** On 2026-09-09 `brain.ops.independence.SEARCHED` grew `ops` and
`SEARCHED_FILES` grew `.env.example`, and the twenty-six findings this module was reporting
were fixed. Keeping them here as well would leave two modules answering "is this host a
client's" with nothing to say which one is right, which is the failure
`tests/invariants/test_single_implementation.py` exists for. So `UNSWEPT` is what is still
genuinely unswept: the build inputs and the workflows. Shrinking it is the module working, not
the module retreating, and the day `docs/*.md` or `.github` joins the gate this list gets
shorter again.

**The half that could not move is git history**, and it is now the larger half. Every value
removed from `ops` and `.env.example` on 2026-09-09 is still in the log, so this module went
from reporting a working tree that agreed with its history to reporting the gap between them,
which is the state the check was written for and had never yet seen.

**Git history is the half that cannot be fixed by an edit**, and saying so is most of the value
of checking it. A value removed from the working tree is still in every clone, so the finding
is not "fix this file" but "this value is disclosed, rotate it". Reading it is cheap and the
answer is worth having either way: measured over the environment and compose files in this
repository on 2026-09-08, history holds exactly what the working tree holds and nothing that
was removed, which means the exposure is the current files and not a year of forgotten ones.

**The shapes are imported and not written again.** `ADDRESS`, `IPV4`, `URL_HOST`, the allowlist
and `is_reserved` all come from `brain.ops.independence`, which argues at length for why they
are shapes rather than one client's names. A second copy here would be a second answer to what
a client value looks like, and the wrong copy is the one that says a host is fine. What differs
is only where the text comes from: a file on disk there, a blob out of git history here.

Rejected: making this a gate. Every check in this module is red on arrival, and
`brain.ops.sweeps` records at length that a check which is red the day it lands is a check
somebody switches off. What pins these instead is a test asserting the exact set of files, in
the shape `tests/unit/test_compose.py` uses: a file dropping off the list is a fix and fails
the test, which is the notification.

Task ids: M42.4.1
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Final

from brain.ops.independence import (
    ADDRESS,
    ALLOWED_HOSTS,
    ALLOWED_IPS,
    COMMENT,
    IPV4,
    URL_HOST,
    compose_services,
    is_reserved,
    vendor_hosts,
)

#: Why the areas this module reads are the ones a client value actually lands in.
THE_UNSWEPT_AREAS_ARE_THE_ONES_WITH_THE_VALUES_IN_THEM: Final = (
    "brain.ops.independence searches src, migrations, the console and the served docs, which "
    "is where the product is written. A deployment's own address is not written in the "
    "product: it is written in the environment file an install copies, in the identity realm "
    "an install imports, in the deploy script and in the workflow that runs it. Every one of "
    "those is outside the sweep, all four carried this deployment's host, and each of them "
    "reaches a client's server."
)

#: Why a value found in history is a rotation rather than an edit.
A_VALUE_IN_HISTORY_IS_DISCLOSED_AND_CANNOT_BE_UNCOMMITTED: Final = (
    "Removing a value from the working tree removes it from the next checkout and from "
    "nowhere else. Every clone that already exists still holds it, and so does every fork, "
    "every CI cache and every backup of the repository. So a finding here is not a file to "
    "edit: it is a credential to rotate or a host to accept as public, and treating it as an "
    "edit is how a repository comes to be full of values everybody believes were removed."
)

#: What `brain.ops.independence.SEARCHED` does not cover, and every entry is a place a client
#: value has actually been found. Globs rather than names so a second workflow is covered on
#: the day it is written.
#:
#: `.env.example` and `ops/**/*` were here until 2026-09-09 and are the sweep's now. This list
#: shrinking is the intended direction: an entry here is an area nothing gates, and the fix
#: for one is to gate it rather than to keep reporting it.
UNSWEPT: Final[tuple[str, ...]] = (
    "Dockerfile",
    "Makefile",
    "alembic.ini",
    ".github/workflows/*.yml",
)

#: Suffixes that are text. A realm export is JSON, a firewall script is shell, a runbook is
#: Markdown, and all three carry a host. Anything else is skipped rather than decoded, because
#: a binary read as text produces findings that point at nothing.
TEXT_SUFFIXES: Final[frozenset[str]] = frozenset(
    {"", ".env", ".example", ".json", ".md", ".sh", ".yml", ".yaml", ".conf", ".ini", ".service"}
)

#: The paths whose whole history is read by default. The environment file because an install
#: copies it, the compose files because they are the deployment, and the realm because it is
#: the one file that configures somebody else's identity provider.
HISTORY_PATHS: Final[tuple[str, ...]] = (
    ".env.example",
    "docker-compose.yml",
    "docker-compose.lite.yml",
    "docker-compose.keycloak.yml",
    "docker-compose.staging.yml",
    "ops/keycloak/realm-export.json",
    "ops/deploy.sh",
)


class AuditError(Exception):
    """Raised when the audit cannot read what it was asked to read."""


def allowed_hosts_for(repo: Path) -> frozenset[str]:
    """Every host this deployment declares, so a finding is a client value and not a service.

    Assembled from `brain.ops.independence` rather than listed: the vendor endpoints come from
    the connectors that declare them and the service names from the compose files, so adding a
    connector or a service does not mean editing this module.
    """
    return frozenset(ALLOWED_HOSTS | vendor_hosts(repo) | compose_services(repo))


def client_values_in(text: str, *, where: str, allowed: Iterable[str]) -> tuple[str, ...]:
    """Every literal in this text that looks like one client's value.

    Read line by line with comments stripped, which is the coarseness
    `brain.ops.independence._literals` settles on for everything that is not Python: YAML,
    JSON and shell all put the real value on the left of a comment and never on the right.
    """
    permitted = {one.lower() for one in allowed}
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = COMMENT.sub("", line)
        for match in ADDRESS.finditer(stripped):
            if not is_reserved(match.group(1)):
                found.append(f"{where}:{number}: a work address, {match.group(0)!r}")
        for match in URL_HOST.finditer(stripped):
            host = match.group(1).split(":")[0].lower()
            if host not in permitted and not is_reserved(host):
                found.append(f"{where}:{number}: a client host, {match.group(1)!r}")
        for match in IPV4.finditer(stripped):
            if match.group(0) not in ALLOWED_IPS:
                found.append(f"{where}:{number}: an address, {match.group(0)!r}")
    return tuple(found)


def unswept_files(repo: Path, patterns: Sequence[str] = UNSWEPT) -> tuple[Path, ...]:
    """Every readable file in the areas the independence sweep does not cover."""
    found: list[Path] = []
    for pattern in patterns:
        for path in sorted(repo.glob(pattern)):
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                found.append(path)
    return tuple(found)


def configuration_gaps(repo: Path, patterns: Sequence[str] = UNSWEPT) -> tuple[str, ...]:
    """Every client value in the configuration, the environment file and the workflows.

    See `THE_UNSWEPT_AREAS_ARE_THE_ONES_WITH_THE_VALUES_IN_THEM`. Reported rather than raised:
    this is true on arrival and the fix is somebody else's decision about which of these hosts
    is a client's and which is the product's own infrastructure.
    """
    allowed = allowed_hosts_for(repo)
    found: list[str] = []
    for path in unswept_files(repo, patterns):
        where = path.relative_to(repo).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        found.extend(client_values_in(text, where=where, allowed=allowed))
    return tuple(found)


def files_with_client_values(repo: Path, patterns: Sequence[str] = UNSWEPT) -> tuple[str, ...]:
    """The distinct files `configuration_gaps` reports, without the line numbers.

    Separate from the findings because that is what a test can hold steady. A line number moves
    every time somebody adds a comment above it, so a test pinned to the findings fails for an
    edit that changed nothing, and a test that fails for nothing is one that gets loosened.
    """
    return tuple(sorted({one.split(":", 1)[0] for one in configuration_gaps(repo, patterns)}))


def history_gaps(repo: Path, paths: Sequence[str] = HISTORY_PATHS) -> tuple[str, ...]:
    """Every client value that any revision of these paths has ever held.

    One finding per value per path rather than per revision, because a host that survived
    forty commits is one disclosure and forty lines of it is a report nobody reads to the end.
    The revision it was first seen in is kept, so the finding still says where to look.

    See `A_VALUE_IN_HISTORY_IS_DISCLOSED_AND_CANNOT_BE_UNCOMMITTED` for why a finding here is
    not a file to edit.
    """
    allowed = allowed_hosts_for(repo)
    seen: set[str] = set()
    found: list[str] = []
    for path in paths:
        for revision in _revisions(repo, path):
            blob = _show(repo, revision, path)
            if blob is None:
                continue
            for one in client_values_in(blob, where=f"{revision[:8]}:{path}", allowed=allowed):
                # Keyed on the path and the value rather than on the whole finding, which
                # carries a revision and a line number and would therefore never repeat.
                key = f"{path}|{one.split(': ', 1)[-1]}"
                if key in seen:
                    continue
                seen.add(key)
                found.append(one)
    return tuple(found)


def _revisions(repo: Path, path: str) -> tuple[str, ...]:
    """Every commit on any branch that touched this path, newest first."""
    result = _git(repo, "log", "--all", "--format=%H", "--", path)
    return tuple(result.split())


#: What git says when a path is simply not in that revision, which is ordinary: `git log`
#: reports the commit that deleted a file, and the file is not there to read at that commit.
#: Anything else git says is a failure, and the difference matters because both come back as a
#: non-zero exit with empty output, which is indistinguishable from a clean file.
NOT_AT_THAT_REVISION = re.compile(
    r"does not exist|exists on disk|invalid object name|unknown revision", re.I
)


def _show(repo: Path, revision: str, path: str) -> str | None:
    """One path as it was at one revision, or None when it did not exist there.

    **A failure and an absence are told apart**, and the first version did not tell them apart.
    Both come back as a non-zero exit with nothing on stdout, so returning None for either
    means a git that could not run at all reports a clean history, which is the shape
    `brain.ops.sweeps` keeps finding: a check that is green because it never looked.

    Decoded from bytes rather than read as text, because `subprocess` with `text=True` decodes
    with the locale's encoding, and on this machine that is not UTF-8: an accented character in
    a comment would come back mangled and a host beside it would be missed.
    """
    result = subprocess.run(  # noqa: S603  arguments are literals and a revision from git
        ["git", "show", f"{revision}:{path}"],  # noqa: S607  git on PATH, as elsewhere here
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.decode("utf-8", errors="replace")
    detail = result.stderr.decode("utf-8", errors="replace").strip()
    if NOT_AT_THAT_REVISION.search(detail):
        return None
    msg = f"git show {revision[:8]}:{path} in {repo}: {detail}"
    raise AuditError(msg)


def _git(repo: Path, *args: str) -> str:
    """git, refusing rather than returning an empty string when it fails.

    An empty string would read as "this path has no history", which is the answer that makes
    the whole audit report nothing and pass.
    """
    result = subprocess.run(  # noqa: S603  arguments are literals from this module
        ["git", *args],  # noqa: S607  git on PATH, as elsewhere in this repository
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        msg = f"git {' '.join(args)} in {repo}: {detail}"
        raise AuditError(msg)
    return result.stdout.decode("utf-8", errors="replace")
