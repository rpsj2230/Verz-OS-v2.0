"""One command on a fresh server, and why it is a file list rather than a file.

M0.4.2 asks for `docker-compose.full.yml` and `brain.ops.compose` refuses to write it, with
four computed reasons. M42.5.1 asks for one command on a fresh server. Read together those
two look like a contradiction, and they are not, because **one command and one file are
different things and only one of them was ever asked for**. `docker compose -f a.yml -f b.yml
... up -d` is one command over eight files.

**The aggregate file would make the install worse, not better, and the reason is the third of
those four.** `A_RELATIVE_BIND_MOUNT_IS_EMPTY_IN_A_STORED_COMPOSE` is not a fact about an
aggregate file; it is a fact about a *deployment path* that stores its own copy of a compose
file with no repository beside it. Four services take something they need at startup from
`./ops/...`, and on that path docker creates an empty directory there and starts the container
anyway, so a memory ceiling, an egress allowlist and a set of object-store credentials all go
missing with nothing to read. An installer that unpacks the release archive into one directory
and runs compose *from that directory* has the repository beside the file, so those mounts
resolve. Writing the aggregate would reintroduce the trap at the exact moment the installer had
removed it, and would add the permanent obligation `brain.ops.compose` rejects: eight files
that must be copied into a ninth or a test goes red.

**Two of the four reasons are not about packaging at all.** `presidio-analyzer` is budgeted and
no compose file declares a service for it, and two services connect to a database nothing
creates. Both block `standard` or `full` coming up under any packaging, aggregate or not. The
remaining one, `seaweedfs` declared twice with bodies that disagree, is settled by the order of
the `-f` flags either way, and the flag list is the better home for it: an order declared in
`COMPOSE_FILES_FOR` is a decision a reviewer can read, where a merge fossilised into an
aggregate file is a decision nobody can see was made.

**So the honest answer is per profile, and it is computed rather than asserted.**
`one_command_blockers` asks the four questions of a profile's own file set. `lite` is one file,
four services and no blockers: one command works today. `standard` and `full` are blocked, and
by defects in the profiles rather than by the shape of the command.

**The other rule this module keeps is that a client's values move through the installer and
never into it.** A script that echoes what it set has put a password in a terminal scrollback
and, when the install is run under `tee` or from CI, in a file. `Step` refuses a fragment that
expands a credential-shaped variable into an output builtin, refuses `set -x`, and permits
exactly one exception: the setup code has to reach the person standing at the console or
nobody can become the first administrator. `brain.firstrun` already argues that case, and the
exception is a declared flag on one step rather than a value that slipped through because its
name happened not to match.

Rejected: making the installer a Python entry point rather than a rendered shell script. It is
the more testable shape and it cannot work: the machine has no Python at the moment the first
command runs, and an installer whose first act is to install its own runtime has moved the
bootstrap problem rather than solved it. What is testable is the plan, so the plan is the
object and the script is its printout, exactly as `.env.example` is the printout of
`brain.install.INSTALLATION`.

Rejected: `git clone` for the release. It is one line shorter and it is the shape
`brain.ops.independence.duplication_gaps` refuses in a build input, for the reason that ends
with a client running a copy nobody fixed. The installer fetches one archive of one tag.

Task ids: M42.1.3, M42.3.1, M42.3.4, M42.5.15
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from brain.deployment.requirements import (
    NOTHING_IN_THIS_DEPLOYMENT_PUBLISHES_A_PORT,
    files_for,
    published_ports,
)
from brain.deployment.variables import is_secret_name
from brain.ops.compose import (
    ComposeFiles,
    components_with_no_service,
    databases_nothing_creates,
    declared_services,
    services_declared_differently,
)
from brain.ops.wiring import assert_known_profile, components_for

#: The answer to "is a one-command install possible without the aggregate compose file".
#:
#: Kept as a sentence as well as a function because the next person to ask will read a
#: paragraph rather than run a check, and `one_command_blockers` is what stops the paragraph
#: going stale: it asks the same four questions of a profile's own file set.
THE_ONE_COMMAND_IS_A_FILE_LIST_AND_NOT_A_FILE: Final = (
    "One command and one file are different things and only the command was asked for. "
    "`docker compose -f a -f b ... up -d` is one command over eight files, so the aggregate "
    "buys the installer nothing, and it costs the one thing the installer fixes: four "
    "relative bind mounts are empty only when the compose file is deployed with no "
    "repository beside it, and an installer that unpacks the release into one directory and "
    "runs compose from there has the repository beside it. Two of the four reasons block "
    "standard and full under any packaging, and the third is settled by flag order either "
    "way, which the flag list declares and an aggregate file hides."
)

#: Why the installer runs compose from the release directory rather than from anywhere.
MOUNTS_RESOLVE_ONLY_FROM_THE_RELEASE_DIRECTORY: Final = (
    "A relative bind mount is resolved against the directory the compose file is read from, "
    "so `docker compose -f /opt/brain/docker-compose.objectstore.yml up` run from anywhere "
    "else creates an empty directory where `./ops/seaweedfs/s3.json` should be and starts the "
    "container with no error. The installer changes into the release directory first, and "
    "that single `cd` is what makes the bind mounts a non-issue for this deployment path."
)

#: Why a step that writes something has to say when it has nothing to do.
A_STEP_THAT_CANNOT_SAY_IT_IS_DONE_IS_A_STEP_THAT_RUNS_TWICE: Final = (
    "Safe to run twice is not a property of a script, it is a property of every step in it. "
    "The step that matters here is the one that mints the credentials: run a second time "
    "without a guard it writes a new database password into the environment file while the "
    "database volume still holds the old one, so the stack comes up and cannot authenticate "
    "to its own data, and the value that would have fixed it has been overwritten."
)

#: Where the release is unpacked and where every command in the script runs.
INSTALL_HOME: Final = "/opt/brain"

#: The environment file the install owns. One per server, gitignored everywhere, and a copy of
#: the template with values filled in. See `brain.deployment.variables`.
INSTALL_ENV_FILE: Final = ".env"

#: A name that could be a credential's, wherever it appears on the line.
#:
#: **Deliberately not an expansion.** The first version of this looked for `$NAME` and
#: `${NAME}`, and the step that presents the setup code reads it with
#: `grep BRAIN_SETUP_SECRET ... | cut` inside a command substitution, so the name is a bare
#: word and the rule saw nothing: the one step in the plan that certainly prints a credential
#: passed the check written to catch it. A value read out of a file and printed is exactly as
#: read as one expanded from a variable.
#:
#: Upper case with underscores, rather than any word, so `printf "set your password"` is
#: prose and not a finding. That is the line between a rule people keep and a rule people
#: switch off, and it is the same argument `is_secret_name` makes about a path to a credential.
CREDENTIAL_TOKEN = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")

#: A command that puts its argument somewhere a person or a log file can read it.
OUTPUT_BUILTIN = re.compile(r"(?:^|[\s;&|(])(echo|printf)\b")

#: Output redirected into this install's own environment file, which is the one destination a
#: credential belongs in. Anchored to the end of the line, because a redirect is the last thing
#: on a command and a path that merely mentions the file is not a destination.
TO_THE_ENVIRONMENT_FILE = re.compile(r">>?\s*\"?[^\"\s]*" + re.escape(INSTALL_ENV_FILE) + r"\"?$")

#: Tracing, and the two commands that print the whole environment. `set -x` is the one that
#: catches people out: it is added to debug a failing install and it prints every expansion
#: including the assignments, so the credentials appear in the output of the run that was
#: being watched most closely.
TRACES_EVERYTHING = re.compile(r"set\s+-[a-zA-Z]*x\b|\bprintenv\b|\benv\s*(?:\||$)")


class InstallerError(Exception):
    """Raised when a step would not be safe to run twice, or would print a value."""


def value_leaks_in(fragment: str) -> tuple[str, ...]:
    """Every way this shell fragment would put a credential somewhere it can be read.

    Line by line, because a step is a small script and the rule is about a command rather
    than about a file. The credential-shaped test is `brain.deployment.variables.is_secret_name`
    which delegates to `brain.firstrun`, so there is one answer in this repository to what a
    credential is called and this is not a second one.

    **A name counts wherever it appears on the line and not only where it is expanded.** See
    `CREDENTIAL_TOKEN`: the first version of this looked for `$NAME`, and the one step in the
    plan that certainly prints a credential reads it out of a file with `grep` and printed it
    past the check unnoticed.
    """
    found: list[str] = []
    for line in _reaching_somewhere_else(fragment):
        if TRACES_EVERYTHING.search(line):
            found.append(
                f"{line.strip()!r} traces or prints the whole environment, which is every "
                "credential this install minted"
            )
        if OUTPUT_BUILTIN.search(line):
            for name in CREDENTIAL_TOKEN.findall(line):
                if is_secret_name(name):
                    found.append(
                        f"{line.strip()!r} prints {name}, so the value reaches a terminal "
                        "scrollback and, under tee or CI, a file nothing sweeps"
                    )
    return tuple(found)


def _reaching_somewhere_else(fragment: str) -> tuple[str, ...]:
    """The lines of this fragment whose output does not go into the install's own file.

    **Without this the mint step is a leak and the rule is unusable.** Writing a generated
    password is `printf "POSTGRES_PASSWORD=%s" ... >> /opt/brain/.env`, which is a print of a
    credential and is also the one thing the installer exists to do. A line-by-line scan
    cannot see that the enclosing brace group is redirected, so it reads the printf and
    refuses the correct implementation, which is how a check comes to be deleted rather than
    obeyed.

    So the destination is the rule: into this install's environment file is where a credential
    belongs, and everything else is a leak. A closing brace carrying the redirect takes the
    whole group with it, because that is how several values are written in one open.
    """
    lines = fragment.splitlines()
    keep = [True] * len(lines)
    for index, line in enumerate(lines):
        if not TO_THE_ENVIRONMENT_FILE.search(line.rstrip()):
            continue
        keep[index] = False
        if not line.lstrip().startswith("}"):
            continue
        # Back to the `{` that opened the group, so the whole redirected block is permitted.
        for earlier in range(index - 1, -1, -1):
            keep[earlier] = False
            if lines[earlier].strip() == "{":
                break
    return tuple(line for line, wanted in zip(lines, keep, strict=True) if wanted)


@dataclass(frozen=True)
class Step:
    """One step of the install, with everything that makes it safe to run twice.

    `already_done` is the shell test that is true when this step has nothing left to do, and
    it is required of any step that writes something. See
    `A_STEP_THAT_CANNOT_SAY_IT_IS_DONE_IS_A_STEP_THAT_RUNS_TWICE`.

    `on_failure` is what the person reads when the step fails, and it says what to do rather
    than what went wrong. M42.5.15 asks for installer output legible to a person, and a step
    that fails with the shell's own message has told them a command exited non-zero.
    """

    #: What the step does, in a few words, printed as it runs.
    name: str
    #: The shell that does it.
    run: str
    #: What breaks or is skipped without it, for whoever is reading the plan rather than
    #: running it.
    why: str
    #: What to do when this step fails.
    on_failure: str
    #: True when the step writes something on the server.
    changes: bool
    #: The shell test that is true when there is nothing to do. Empty for a step that changes
    #: nothing, because running a check twice is the same as running it once.
    already_done: str = ""
    #: True for the one step that has to put a value in front of the person installing. See
    #: the module header.
    presents_once: bool = False

    def __post_init__(self) -> None:
        for field, value in (("name", self.name), ("why", self.why), ("run", self.run)):
            if not value.strip():
                msg = f"a step with no {field} cannot be printed, reviewed or run"
                raise InstallerError(msg)
        if not self.on_failure.strip():
            msg = (
                f"{self.name!r} does not say what to do when it fails, so the person "
                "installing reads the shell's exit code and nothing else"
            )
            raise InstallerError(msg)
        if self.changes and not self.already_done.strip():
            msg = (
                f"{self.name!r} writes something and cannot say when it is already done, so "
                "a second run repeats it. "
                f"{A_STEP_THAT_CANNOT_SAY_IT_IS_DONE_IS_A_STEP_THAT_RUNS_TWICE}"
            )
            raise InstallerError(msg)
        if not self.changes and self.already_done.strip():
            msg = (
                f"{self.name!r} changes nothing and carries a done test, which reads as a "
                "step that can be skipped; a check is idempotent because it writes nothing"
            )
            raise InstallerError(msg)
        leaks = value_leaks_in(self.run) + value_leaks_in(self.already_done)
        if leaks and not self.presents_once:
            msg = f"{self.name!r} would put a value where it can be read: {leaks[0]}"
            raise InstallerError(msg)


#: The install, in the order it runs. The count in the output is `len(PLAN)`, so a person
#: reading "step 4 of 12" knows how much is left.
#:
#: The number is deliberately not written in this sentence. It said ten while the plan held
#: twelve, which is what a hand-maintained count does, and the output was right the whole
#: time because `render` has always used `len`. A comment that disagrees with the code is
#: worse than no comment when the code is the thing being explained.
#:
#: `$BRAIN_RELEASE` is the release tag, which is the whole of what a client pins. Nothing here
#: reads it from anywhere but the argument the person ran the installer with, because a
#: default of `latest` is what makes an install unpinned.
PLAN: Final[tuple[Step, ...]] = (
    Step(
        name="check the machine",
        run=(
            'command -v docker >/dev/null || fail "docker is not installed"\n'
            'docker compose version >/dev/null 2>&1 || fail "docker compose v2 is not installed"'
        ),
        why=(
            "every memory ceiling in this deployment is written under deploy.resources.limits, "
            "which the v1 compose tool ignores without a warning"
        ),
        on_failure=(
            "install Docker Engine 24 or newer with the compose plugin, then run this again. "
            "Nothing has been written yet"
        ),
        changes=False,
    ),
    Step(
        name="check the machine is large enough",
        run=(
            "available=$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)\n"
            'test "$available" -ge "$BRAIN_MEMORY_MIB" || fail "this profile needs '
            '$BRAIN_MEMORY_MIB MiB and this machine has $available MiB"'
        ),
        why=(
            "an install that starts on a machine that cannot hold it fails later, one "
            "container at a time, as whichever service asks for memory last is killed"
        ),
        on_failure=(
            "use a larger machine, or install the lite profile, which is the whole stack "
            "without the worker and is what production runs today"
        ),
        changes=False,
    ),
    Step(
        name="create the install directory",
        run=f'mkdir -p "{INSTALL_HOME}"',
        why="everything below lives in one directory, so an uninstall is one removal",
        on_failure=f"run this as a user that can write {INSTALL_HOME}",
        changes=True,
        already_done=f'test -d "{INSTALL_HOME}"',
    ),
    Step(
        name="download and unpack the release",
        run=(
            f'curl -fsSL "$BRAIN_RELEASE_URL" -o "{INSTALL_HOME}/release.tar.gz"\n'
            f'tar -xzf "{INSTALL_HOME}/release.tar.gz" -C "{INSTALL_HOME}" --strip-components=1\n'
            f'printf "%s\\n" "$BRAIN_RELEASE" > "{INSTALL_HOME}/RELEASE"'
        ),
        why=(
            "one archive of one tag, never a clone: a build that fetches a second repository "
            "is the shape brain.ops.independence.duplication_gaps refuses, and the reason is "
            "a client left running a copy that a fix never reached"
        ),
        on_failure=(
            "check the release tag exists and that this server can reach the release host. "
            "Nothing has been started, so it is safe to run this again"
        ),
        changes=True,
        already_done=(
            f'test -f "{INSTALL_HOME}/RELEASE" && '
            f'test "$(cat "{INSTALL_HOME}/RELEASE")" = "$BRAIN_RELEASE"'
        ),
    ),
    Step(
        name="change into the release directory",
        run=f'cd "{INSTALL_HOME}" || fail "the release did not unpack into {INSTALL_HOME}"',
        why=(
            "compose resolves a relative bind mount against the project directory, which is "
            "the directory the first -f file was read from. Running from here is what makes "
            "the four `./ops/...` mounts resolve instead of silently becoming empty "
            "directories. See MOUNTS_RESOLVE_ONLY_FROM_THE_RELEASE_DIRECTORY"
        ),
        on_failure=(
            "the previous step reported success and left nothing behind, which means the "
            "archive unpacked somewhere else. Remove it and run this again"
        ),
        changes=False,
    ),
    Step(
        name="write the environment file from the template",
        run=(
            f'test -f "{INSTALL_HOME}/{INSTALL_ENV_FILE}" || '
            f'cp "{INSTALL_HOME}/.env.example" "{INSTALL_HOME}/{INSTALL_ENV_FILE}"'
        ),
        why=(
            "the template ships in the release and is copied, never edited in place, which is "
            "what docs/repository-map.md already says .env.example is for. This install's own "
            "values are then filled in from its file in the variables repository, and nothing "
            "in this repository is edited per client"
        ),
        on_failure=(
            f"copy the template yourself into {INSTALL_HOME}/{INSTALL_ENV_FILE} and run this "
            "again; the step writes nothing else"
        ),
        changes=True,
        already_done=f'test -f "{INSTALL_HOME}/{INSTALL_ENV_FILE}"',
    ),
    Step(
        name="mint this installation's secrets",
        run=(
            f'umask 077\n{{\n  printf "POSTGRES_PASSWORD=%s\\n" "$(openssl rand -hex 32)"\n'
            '  printf "APP_ROLE_PASSWORD=%s\\n" "$(openssl rand -hex 32)"\n'
            '  printf "BRAIN_SETUP_SECRET=%s\\n" "$(openssl rand -hex 32)"\n'
            f'}} >> "{INSTALL_HOME}/{INSTALL_ENV_FILE}"'
        ),
        why=(
            "every credential is generated here, on this server, so no two installs share "
            "one and none of them ships in the template. See M42.5.2 and "
            "brain.deployment.variables.A_VALUE_THAT_ARRIVED_WITH_THE_TEMPLATE_WAS_NEVER_MINTED"
        ),
        on_failure=(
            "install openssl and run this again. The environment file is written in one go, "
            "so a failure here leaves nothing half-minted"
        ),
        changes=True,
        # The sharpest guard in the plan, and it is keyed on a credential rather than on
        # the file. Minting again would write a new database password beside a volume that
        # still holds the old one, so the stack comes up and cannot authenticate to its own
        # data, and the value that would have fixed it is gone. Keying it on the file
        # existing would have been worse than no guard on the install where the variables
        # file arrived first: the file is there, nothing is minted, and every credential the
        # stack needs is missing with the step reporting that it had nothing to do.
        already_done=(f'grep -q "^POSTGRES_PASSWORD=." "{INSTALL_HOME}/{INSTALL_ENV_FILE}"'),
    ),
    Step(
        name="pull the images this profile runs",
        run="docker compose $BRAIN_COMPOSE_FILES pull --quiet",
        why=(
            "pulled before anything starts, so a registry that cannot be reached fails while "
            "the machine is still empty rather than half up"
        ),
        on_failure=(
            "check this server can reach the image registry, then run this again. Pulling an "
            "image that is already present does nothing"
        ),
        changes=True,
        already_done="docker compose $BRAIN_COMPOSE_FILES images --quiet | grep -q .",
    ),
    Step(
        name="start the database and wait for it",
        run=(
            "docker compose $BRAIN_COMPOSE_FILES up -d db\n"
            "docker compose $BRAIN_COMPOSE_FILES exec -T db "
            "sh -c 'until pg_isready -U brain -d brain; do sleep 2; done'"
        ),
        why=(
            "the application runs its own migrations at startup under an advisory lock, so "
            "it needs a database that is accepting connections rather than one that is starting"
        ),
        on_failure=(
            "read `docker compose $BRAIN_COMPOSE_FILES logs db`. A database that will not "
            "start is almost always a volume from a different major version"
        ),
        changes=True,
        already_done=(
            "docker compose $BRAIN_COMPOSE_FILES ps --status running --services | grep -qx db"
        ),
    ),
    Step(
        name="start everything else",
        run="docker compose $BRAIN_COMPOSE_FILES up -d",
        why="the one command this whole module is about, over the file list for this profile",
        on_failure=(
            "read `docker compose $BRAIN_COMPOSE_FILES ps` for the container that is not "
            "running, then its logs. Bringing the stack up again is safe"
        ),
        changes=True,
        already_done=(
            'test "$(docker compose $BRAIN_COMPOSE_FILES ps --status running '
            '--services | wc -l)" -ge "$BRAIN_SERVICES"'
        ),
    ),
    Step(
        name="wait for the application to report ready",
        run=(
            "for _ in $(seq 1 60); do\n"
            "  docker compose $BRAIN_COMPOSE_FILES exec -T app python -c "
            "'import urllib.request,sys; "
            'sys.exit(0 if urllib.request.urlopen("http://127.0.0.1:8000/health/ready",'
            "timeout=4).status==200 else 1)' && break\n"
            "  sleep 5\n"
            "done\n"
            "docker compose $BRAIN_COMPOSE_FILES exec -T app python -c "
            "'import urllib.request,sys; "
            'sys.exit(0 if urllib.request.urlopen("http://127.0.0.1:8000/health/ready",'
            'timeout=4).status==200 else 1)\' || fail "the application never reported ready"'
        ),
        why=(
            "readiness rather than liveness: a container that is up but cannot reach its "
            "database still answers questions, from whatever it can still reach"
        ),
        on_failure=(
            "read `docker compose $BRAIN_COMPOSE_FILES logs app`. Readiness fails while the "
            "migrations are still running, which on a first install takes a minute"
        ),
        changes=False,
    ),
    Step(
        # "once" is about the value and not about the step: `presents_once` is what exempts
        # this from the leak check, because the code has to reach the person standing here
        # exactly once and nowhere else. Re-running the installer runs this step again and
        # prints the same value, which is not a leak, because whoever can run the installer
        # already has a shell on that server and can read the environment file directly. It
        # is worth saying because the name reads as a guarantee the step does not make.
        name="present the setup code, once",
        run=(
            f'printf "setup code: %s\\n" "$(grep BRAIN_SETUP_SECRET '
            f'"{INSTALL_HOME}/{INSTALL_ENV_FILE}" | cut -d= -f2)"\n'
            'printf "%s\\n" "Open the console and enter it on the first screen. '
            'It is required before anybody can claim this system."'
        ),
        why=(
            "the one value that has to reach the person standing here, because without it "
            "whoever loads the page first becomes the administrator. See brain.firstrun"
        ),
        on_failure=(
            f"read the value out of {INSTALL_HOME}/{INSTALL_ENV_FILE} yourself; the install "
            "is complete either way"
        ),
        changes=False,
        presents_once=True,
    ),
)


def compose_argv(profile: str) -> tuple[str, ...]:
    """The one command, as the words it is made of.

    A tuple rather than a string so a test asserts on the argument list rather than on text
    that a docstring nearby could also supply, which is the substring trap CLAUDE.md records.
    """
    files: list[str] = []
    for name in files_for(profile):
        files.extend(("-f", name))
    return ("docker", "compose", *files, "up", "-d")


def compose_files_argument(profile: str, *, home: str = INSTALL_HOME) -> str:
    """The `-f` flags as one shell word list, for `$BRAIN_COMPOSE_FILES` in the script.

    **Absolute rather than relative, and that is the whole of the bind-mount answer.** Compose
    resolves a relative path inside a compose file against the project directory, and the
    project directory defaults to the directory the *first* `-f` file was read from. Naming
    them absolutely under the release directory therefore fixes `./ops/seaweedfs/s3.json` to
    `/opt/brain/ops/seaweedfs/s3.json` whatever the caller's working directory is, which is
    the failure `A_RELATIVE_BIND_MOUNT_IS_EMPTY_IN_A_STORED_COMPOSE` describes and the one
    thing a stored compose cannot do. The plan changes directory as well, which is belt and
    braces rather than the mechanism.
    """
    return " ".join(f"-f {home}/{name}" for name in files_for(profile))


def one_command_blockers(profile: str, files: ComposeFiles) -> tuple[str, ...]:
    """What stops `compose_argv(profile)` producing a working install, on these documents.

    The same four questions `brain.ops.compose` asks of an aggregate file, asked of a profile's
    own file set, plus the one an aggregate file never had to answer: nothing here publishes a
    port, so a complete install is reachable from other containers and from nowhere else.

    **Relative bind mounts are deliberately not a blocker here**, and that is the difference
    between this and the aggregate. They are empty only for a deployment that stores its own
    copy of a compose file with no repository beside it, and this installer unpacks the release
    into one directory and runs compose from inside it. See
    `MOUNTS_RESOLVE_ONLY_FROM_THE_RELEASE_DIRECTORY`.
    """
    assert_known_profile(profile)
    blockers = [
        *components_with_no_service(profile, files),
        *services_declared_differently(files),
        *databases_nothing_creates(files),
    ]
    if not published_ports(files):
        blockers.append(
            f"no service in this profile publishes a port to the host, so the install "
            "completes and the console is reachable from nowhere. "
            f"{NOTHING_IN_THIS_DEPLOYMENT_PUBLISHES_A_PORT}"
        )
    return tuple(blockers)


def render(profile: str, *, services: int, memory_mib: int) -> str:
    """The installer for one profile, as the shell it is.

    `services` and `memory_mib` are passed rather than computed, for the reason every function
    in `brain.ops.compose` takes documents somebody else parsed: rendering a script is not a
    good enough excuse to open a file, and a caller who has the parsed compose documents
    already has both figures from `brain.deployment.requirements.spec_for`.

    The output is numbered against `len(PLAN)`, so "step 4 of 10" is arithmetic rather than a
    number somebody typed and stopped updating.
    """
    assert_known_profile(profile)
    total = len(PLAN)
    lines = [
        "#!/bin/sh",
        "# Generated by brain.deployment.installer.render. Do not edit: edit PLAN and",
        "# regenerate, or the script and the plan disagree and the plan is the tested one.",
        "set -eu",
        "",
        f'BRAIN_PROFILE="{profile}"',
        f'BRAIN_HOME="{INSTALL_HOME}"',
        f'BRAIN_COMPOSE_FILES="{compose_files_argument(profile)}"',
        f'BRAIN_SERVICES="{services}"',
        f'BRAIN_MEMORY_MIB="{memory_mib}"',
        'BRAIN_RELEASE="${1:?usage: install.sh <release tag>}"',
        'BRAIN_RELEASE_URL="${BRAIN_RELEASE_URL:?set BRAIN_RELEASE_URL to the release archive}"',
        "",
        'say() { printf "%s\\n" "$1"; }',
        'fail() { printf "%s\\n" "$1" >&2; exit 1; }',
        "",
        f'say "Installing the $BRAIN_PROFILE profile into $BRAIN_HOME, {total} steps."',
        "",
    ]
    for number, step in enumerate(PLAN, 1):
        heading = f"step {number} of {total}: {step.name}"
        lines.append(f"# {heading}")
        if step.already_done:
            lines.append(f"if {step.already_done}; then")
            lines.append(f'  say "{heading} - already done, skipping"')
            lines.append("else")
            lines.append(f'  say "{heading}"')
            lines.extend(f"  {one}" for one in step.run.splitlines())
            lines.append("fi")
        else:
            lines.append(f'say "{heading}"')
            lines.extend(step.run.splitlines())
        lines.append("")
    lines.append(f'say "Done. The {profile} profile is running from $BRAIN_HOME."')
    return "\n".join(lines) + "\n"


def rebuild_gaps(files: ComposeFiles) -> tuple[str, ...]:
    """Every service this set would build on a client's server rather than pull by tag.

    M42.1.3 asks for one published image deployed by tag and never rebuilt per client. A
    `build:` key is the literal failure: the client's server compiles its own copy, which is
    then a different artefact from every other client's with the same version number on it,
    and nothing anywhere compares the two.

    An image with no tag at all is the quieter half of the same thing. Docker resolves a bare
    name to `:latest`, so two servers installing on two days run two different images and both
    report the same image name.
    """
    found: list[str] = []
    for name in sorted(files):
        for service, body in sorted(_services(files[name]).items()):
            if not isinstance(body, dict):
                continue
            if body.get("build"):
                found.append(
                    f"{name}: {service!r} declares a build, so this client compiles their own "
                    "copy of an image every other client pulls"
                )
            image = str(body.get("image", ""))
            if image and "${" not in image and ":" not in image.rsplit("/", 1)[-1]:
                found.append(
                    f"{name}: {service!r} names image {image!r} with no tag, which docker "
                    "resolves to :latest, so two installs on two days are two images"
                )
    return tuple(found)


#: `${VAR:-default}` or `${VAR:?message}` or `${VAR}`, as a whole image reference.
IMAGE_VARIABLE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[-?]([^}]*))?\}$")


def release_pinning_gaps(files: ComposeFiles) -> tuple[str, ...]:
    """Everything that stops a client holding one version back without forking (M42.1.4).

    Two shapes, and the first is the one nobody sees. A client pins by setting the variable
    that selects the image. When *one* image is selected by more than one variable, setting
    one of them pins some containers and leaves the rest on whatever the other variable
    resolves to, so an install can run two builds of one product at once and every version
    figure it reports is true of only part of it.

    The second is the default. `${VAR:-name:latest}` means an install that pins nothing is not
    pinned at all, and the release it runs changes under it on the next pull.

    Reported rather than raised, in the shape `test_compose.py` uses: this is true on arrival,
    and a check that is red the day it lands is a check somebody switches off. What pins it is
    a test asserting the exact set, so a fourth variable fails rather than joining a list
    nobody reads.
    """
    selected: dict[str, set[str]] = {}
    found: list[str] = []
    for name in sorted(files):
        for service, body in sorted(_services(files[name]).items()):
            if not isinstance(body, dict):
                continue
            match = IMAGE_VARIABLE.match(str(body.get("image", "")))
            if match is None:
                continue
            variable, default = match.group(1), match.group(2) or ""
            image = default.rsplit(":", 1)[0] if ":" in default else default
            if image:
                selected.setdefault(image, set()).add(variable)
            if default.endswith(":latest"):
                found.append(
                    f"{name}: {service!r} defaults to {default!r}, so an install that pins "
                    "nothing follows whatever latest points at on the day it pulls"
                )
    for image, variables in sorted(selected.items()):
        if len(variables) < 2:
            continue
        found.append(
            f"{image!r} is selected by {sorted(variables)}, so pinning one of them leaves "
            "the rest on their own default and one install runs two builds of one product"
        )
    return tuple(found)


def health_report(profile: str, files: ComposeFiles) -> str:
    """What to check after deploying, and what each check means, for a person to read.

    M42.3.4 asks for a health-check script somebody runs after deploying and can read the
    output of. The readable half is the harder one: a script that prints `ok` per container
    has told the reader that a process is up, which is liveness wearing readiness' clothes.
    Every component in `brain.ops.wiring` is required to carry a `ready_when` sentence for
    exactly this moment, and this is the first thing that has ever printed them.
    """
    assert_known_profile(profile)
    lines = [f"After deploying the {profile} profile, check each of these in order.", ""]
    for service, where in sorted(declared_services(files).items()):
        body = _services(files[where[0]]).get(service)
        declared = isinstance(body, dict) and bool(body.get("healthcheck"))
        state = "has a healthcheck" if declared else "has no healthcheck; check it by hand"
        lines.append(f"{service}: {state}")
    lines.append("")
    lines.append("Ready, for each component this profile adds, means:")
    for one in components_for(profile):
        lines.append(f"{one.name}: {one.ready_when}")
    return "\n".join(lines) + "\n"


def services_without_a_healthcheck(files: ComposeFiles) -> tuple[str, ...]:
    """Every service this set starts that nothing can tell the readiness of.

    A container with no healthcheck is `running` the instant its process starts, so
    `depends_on: service_healthy` cannot wait for it and a person reading `docker compose ps`
    is reading liveness. Reported rather than raised, for the reason `release_pinning_gaps` is.
    """
    found: list[str] = []
    for service, where in sorted(declared_services(files).items()):
        body = _services(files[where[0]]).get(service)
        if not isinstance(body, dict):
            continue
        # A one-shot is ready when it has exited, which compose spells
        # `service_completed_successfully`, and a healthcheck on one would never pass.
        # Both of this deployment's one-shots say so with `restart: "no"`.
        if str(body.get("restart", "")) == "no":
            continue
        if not body.get("healthcheck"):
            found.append(
                f"{where[0]}: {service!r} declares no healthcheck, so it counts as running "
                "the moment its process starts and nothing can wait for it to be ready"
            )
    return tuple(found)


def _services(document: Any) -> dict[str, Any]:
    """The services block of one document, or an empty one."""
    services = document.get("services") if hasattr(document, "get") else None
    return dict(services) if isinstance(services, dict) else {}


def step_named(name: str, plan: Sequence[Step] = PLAN) -> Step:
    """One step by name, refusing an unknown one rather than answering None.

    Refuses for the reason `brain.ops.wiring.component` refuses: a caller handed None writes
    `if step is None: return` and the step silently stops being part of the install.
    """
    for one in plan:
        if one.name == name:
            return one
    msg = f"no step named {name!r}; the plan is {[one.name for one in plan]}"
    raise InstallerError(msg)
