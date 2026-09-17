"""The one command a person runs on a fresh server, as a file they can read before running it.

`brain.deployment.installer` already holds the plan and already renders it. What it could not
produce is a file a client fetches: `render` bakes one profile's memory and service figures in,
so it renders three scripts, and a person standing at a terminal has to know which one they
want before they have anything to run. This module renders **one** script for every profile,
in the shape `brain.deployment.release.render_update` already uses, and `ops/install/install.sh`
is the committed printout of it. `test_install_script.py` holds the two byte-identical, which
is the whole reason for rendering rather than writing: a generated file checked in without that
test is a copy that drifts, and the copy is the one that runs on a client's server.

**A second module rather than more of `installer.py`, and the reason is what it does not
touch.** `installer.PLAN` is read by `brain.deployment.release.update_plan` and
`rollback_plan`, by `release.paths_the_install_reads`, and by the table in
`docs/install/install.md` that `brain.ops.install_docs.step_gaps` holds against it. Inserting
the prerequisite steps into `PLAN` would move all four: the update script would start
installing Docker, and the manual sequence in the guide would go red for listing exactly the
steps it correctly lists. So the prerequisites are declared here and `install_plan`
concatenates. What `PLAN` describes is still exactly the manual sequence a person follows when
this script refuses them, which is what makes the guide's fallback a fallback rather than a
second product.

**This script is `bash` where the update and rollback scripts are `sh`, and it is the one
decision here with a cost.** `set -eu` alone does not see a pipeline whose *left*-hand side
failed, and the plan being rendered contains one that matters:
`sed -n "s/^LANGFUSE.../create role .../p" /opt/brain/.env | docker compose exec -T db psql`.
An environment file that cannot be read makes `sed` exit non-zero, `psql` read empty input and
exit zero, and the pipeline reports success having created no role: the step says done, and the
trace ledger fails to start an hour later with a message about a login rather than about this.
`set -o pipefail` is what turns that into the step's own `on_failure` sentence. See
`A_MASKED_PIPELINE_REPORTS_A_STEP_THAT_DID_NOTHING`. The cost is a machine with no bash, which
is a machine this script cannot even print a refusal on, and that is the case
`docs/install/install.md` keeps the manual sequence for. Every distribution whose Docker route
is documented ships bash; the ones that do not were never on the supported list.

**How the person supplies the profile and the address, decided rather than defaulted.** Three
values, three different answers, and what separates them is what happens when the value is
wrong.

- The **profile** is a flag and, with a terminal attached, a prompt when the flag is absent. It
  is a choice between three named answers that the script itself can list, and a wrong answer
  is caught by the next step rather than in a month: the memory check refuses a machine that
  cannot hold what was picked. There is deliberately no default, because a default profile is a
  machine size nobody chose. See `THE_PROFILE_IS_CHOSEN_HERE_AND_RECORDED_NOWHERE`.
- The **release tag** is a flag and is never prompted. It is the one value that has to be
  identical across this install, every update and any rollback, and a value typed at a prompt
  exists only in one terminal's scrollback. `latest` is refused here exactly as
  `brain.deployment.release` refuses it, and for the same reason: a tag that follows a moving
  pointer is an install that changes version with nobody deciding anything.
- The **console address** is a flag, a prompt with a terminal attached, and **blank is an
  accepted answer**. Nothing in this deployment publishes a port, so the address is a fact about
  a reverse proxy outside this stack entirely, which may not exist yet when the install runs.
  Given one, the last line says where to open the wizard. Given none, it says what the address
  depends on. What it never does is print `http://localhost:8000`, which would be a fabricated
  address that answers nothing. See `AN_ADDRESS_NOBODY_SUPPLIED_IS_NOT_LOCALHOST`.

Rejected: prompting for everything and taking no flags, which reads friendlier and cannot be
put in a runbook, re-run from a terminal that has scrolled, or driven over ssh without a tty.
Rejected: flags only, which is correct and hands a person on a fresh server a usage message
instead of an install. Both, with the prompt refusing when there is no terminal to ask at, is
the shape that survives both callers.

Rejected: fetching `https://get.docker.com` and piping it into a root shell. It is one line, it
is Docker's own script, and Docker's own documentation says not to use it in production. The
routes below are the per-distribution ones from that same documentation, and an unrecognised
distribution is told exactly what to run instead.

Task ids: M42.5.1, M42.6.2
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from brain.deployment import vault_setup
from brain.deployment.installer import (
    INSTALL_HOME,
    PLAN,
    PRODUCT_IMAGE,
    Step,
    compose_files_argument,
)
from brain.deployment.requirements import RUNTIME_REQUIREMENTS, Requirement
from brain.ops.wiring import PROFILES, assert_known_profile

#: Where the committed printout of this module lives, relative to the repository root.
#:
#: Beside `ops/update/` rather than at the root, because the two are the same kind of object.
#: The archive carries it for the reason `brain.deployment.release.INCLUDED` gives, which is
#: worth reading rather than assuming: the copy in the archive is never how anybody obtains the
#: script, because running the script is what fetches the archive. It is the record of what was
#: run, and the copy a person re-runs after an update has to belong to the release on that
#: server rather than being whichever one is newest.
SCRIPT_PATH: Final = "ops/install/install.sh"

#: Why this script is bash and its two siblings are POSIX sh.
A_MASKED_PIPELINE_REPORTS_A_STEP_THAT_DID_NOTHING: Final = (
    "Under `set -eu` a pipeline's status is its last command's, so a step spelled `sed ... | "
    "psql` succeeds when sed failed and psql read nothing: the install reports that it created "
    "the trace ledger's login and created no login. `set -o pipefail` is the only thing that "
    "turns that into a failure the step's own on_failure sentence answers, and it is a bash "
    "feature rather than a POSIX sh one."
)

#: Why a missing console address is printed as a missing console address.
AN_ADDRESS_NOBODY_SUPPLIED_IS_NOT_LOCALHOST: Final = (
    "No service in any profile publishes a port to the host, so there is no address this "
    "script could discover and none it could fall back to. A handover line reading "
    "http://localhost:8000 would be a fabricated address that answers nothing, and the person "
    "would spend the next twenty minutes deciding whether the install had failed. Given no "
    "address it says what the address depends on, which is the reverse proxy the requirements "
    "already name."
)

#: Why every requirement is answered by a check rather than by a sentence in a guide.
A_REQUIREMENT_WITH_NO_CHECK_IS_ONE_THE_SERVER_DISCOVERS_LATE: Final = (
    "Every entry in RUNTIME_REQUIREMENTS is something an install fails without, and the "
    "failures are not alike: a missing openssl stops the mint step with a clear message, and "
    "the older compose tool starts the whole stack with every memory ceiling silently ignored. "
    "A requirement nothing checks is therefore not a requirement, it is a paragraph, and "
    "requirements_without_a_check is what stops one being added to the list and to no script."
)

#: Why a check that cannot say no is not a check.
A_CHECK_THAT_CANNOT_REFUSE_IS_A_STEP_THAT_ALWAYS_PASSES: Final = (
    "A refusing check whose shell never calls `refuse` reads exactly like one that does and "
    "passes on every machine, including the machines it exists to turn away. Checked when the "
    "check is written rather than when the script is reviewed, which is the argument Step "
    "already makes about a step that cannot say when it is already done."
)

#: Why the profile is asked for and never remembered.
THE_PROFILE_IS_CHOSEN_HERE_AND_RECORDED_NOWHERE: Final = (
    "Nothing an install leaves on disk records which profile it is, so every script that has "
    "to compose the right files asks again, which is why the update script takes it as an "
    "argument. The installer is the one place where the person running it is choosing rather "
    "than recalling, so it is the one place a prompt is honest."
)

#: The environment variable holding the address of the release archive. The same name the
#: update and rollback scripts read, because the three are run on one server by one person and
#: a value spelled two ways is a value somebody sets twice.
RELEASE_URL_VARIABLE: Final = "BRAIN_RELEASE_URL"

#: The flags this script takes, as (flag, what it means). Read by the usage message and by the
#: test that holds the two equal, so a flag added to the parser and not to the usage is red.
FLAGS: Final[tuple[tuple[str, str], ...]] = (
    ("--profile", f"one of: {' '.join(PROFILES)}. Asked for if you leave it out"),
    ("--release", "the release tag to install. Required, and never latest"),
    ("--console-address", "the address your reverse proxy will serve the console on"),
    ("--no-install-docker", "do not install Docker, say what to run instead"),
    (
        vault_setup.DECLINE_FLAG,
        f"run no secrets vault, accepted only for: {' '.join(vault_setup.DECLINABLE_PROFILES)}",
    ),
    ("--help", "print this and stop"),
)

#: Docker's own per-distribution routes, by `ID` and `ID_LIKE` in `/etc/os-release`.
#:
#: The value is the name Docker publishes packages under, which is not always the distribution:
#: Rocky and Alma are served by the centos repository, and that mapping is the whole reason
#: this is a table rather than a string interpolation.
DOCKER_APT_ROUTES: Final[Mapping[str, str]] = {"debian": "debian", "ubuntu": "ubuntu"}
DOCKER_DNF_ROUTES: Final[Mapping[str, str]] = {
    "fedora": "fedora",
    "rhel": "rhel",
    "centos": "centos",
    "rocky": "centos",
    "almalinux": "centos",
}

#: What an unrecognised distribution is told, which is a page rather than a command, because a
#: command invented for a distribution nobody here has run is worse than an address.
#:
#: Declared here, at the top of the file, rather than written into the step that prints it, and
#: that is the rule `brain.ops.independence.DECLARING_AREAS` enforces rather than a convenience.
#: This is where Docker is for every client this system will ever have, which is exactly what a
#: connector's `BASE_URL` says about a vendor, and a URL buried in a function body is refused by
#: the client-independence sweep whether it is a vendor's or a client's.
DOCKER_DOCUMENTATION_URL: Final = "https://docs.docker.com/engine/install/"

#: Where Docker publishes its packages, keys and repository definitions. One constant for all
#: three routes, because the first draft wrote the address out three times inside the function
#: that renders the step, which is the shape the sweep refuses.
DOCKER_PACKAGES_URL: Final = "https://download.docker.com/linux"

#: The packages Docker's documentation installs, on both routes. The compose plugin is the one
#: that matters here: an engine installed without it satisfies one requirement and fails the
#: next, which is the shape of every install that comes up with no memory ceilings anywhere.
DOCKER_PACKAGES: Final = (
    "docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
)


class InstallScriptError(Exception):
    """Raised when a check or a rendering could not be produced in a form anybody can run."""


@dataclass(frozen=True)
class Check:
    """One entry of `RUNTIME_REQUIREMENTS`, as the shell that asks this machine for it.

    `requirement` is the `Requirement.what` it answers, spelled identically, because the pairing
    is what `requirements_without_a_check` reads. A string rather than the object, so that a
    check is declared beside its shell and the join is checked in both directions.

    `refuses` is false for the one requirement nothing running on the server can test. A reverse
    proxy is a machine in front of this one, so the check for it is a sentence, and a check that
    claimed to have verified it would be the worse of the two failures.
    """

    #: The requirement this answers, spelled as `Requirement.what` spells it.
    requirement: str
    #: The shell that asks, calling `refuse` for a machine that cannot run this.
    run: str
    #: True when this check can turn a machine away.
    refuses: bool = True

    def __post_init__(self) -> None:
        if not self.run.strip():
            msg = f"the check for {self.requirement!r} has no shell, so it asks nothing"
            raise InstallScriptError(msg)
        calls = "refuse " in self.run
        if self.refuses and not calls:
            msg = (
                f"the check for {self.requirement!r} refuses nothing, so it passes on every "
                f"machine including the ones it exists to turn away. "
                f"{A_CHECK_THAT_CANNOT_REFUSE_IS_A_STEP_THAT_ALWAYS_PASSES}"
            )
            raise InstallScriptError(msg)
        if not self.refuses and calls:
            msg = (
                f"the check for {self.requirement!r} says it cannot refuse and then refuses, "
                "so a machine is turned away by a check the plan describes as advisory"
            )
            raise InstallScriptError(msg)


def _requirement(
    what: str, requirements: Sequence[Requirement] = RUNTIME_REQUIREMENTS
) -> Requirement:
    """One requirement by name, refusing an unknown one rather than answering None.

    Refuses for the reason `brain.deployment.installer.step_named` refuses: a caller handed
    None writes a refusal with an empty reason in it, and an empty reason is the part of a
    refusal that somebody waives.
    """
    for one in requirements:
        if one.what == what:
            return one
    msg = f"no requirement named {what!r}; the list is {[one.what for one in requirements]}"
    raise InstallScriptError(msg)


def as_shell_text(text: str) -> str:
    """Prose, safe to put inside a double-quoted shell string.

    **A backtick inside double quotes is a command substitution**, and prose written by
    somebody thinking about Markdown is full of them: `Requirement.why` for Docker Engine says
    "the Compose specification's `deploy` block", which a shell reads as an instruction to run
    `deploy`. Escaped rather than stripped, because the backticks are what make the sentence
    readable at the terminal it is printed at, and stripping them would quietly edit a
    requirement's stated reason.

    A dollar is deliberately left alone. Every caller interpolates a value the script has to
    expand, `$BRAIN_ENGINE` and `$(uname -m)` among them, so escaping it would turn every
    refusal into a line naming a variable rather than a machine.
    """
    backslash = chr(92)
    return (
        text.replace(backslash, backslash * 2)
        .replace('"', backslash + '"')
        .replace("`", backslash + "`")
    )


#: The two variables this script expands unquoted, and why each one has to be.
#:
#: **Word splitting is the point for both of them.** `BRAIN_COMPOSE_FILES` holds
#: `-f /opt/brain/a.yml -f /opt/brain/b.yml`, which has to reach `docker compose` as up to
#: eighteen words: quoted it is one argument and compose refuses a file whose name is the whole
#: list. `BRAIN_OS_ID` holds `ID` and `ID_LIKE` together and is walked one word at a time to
#: find the first with a documented Docker route. Declared here rather than judged case by case,
#: so `unquoted_expansions` reports a third one the day somebody adds it.
SPLIT_ON_PURPOSE: Final[Mapping[str, str]] = {
    "BRAIN_COMPOSE_FILES": (
        "holds the -f flags for this profile and has to reach docker compose as separate "
        "words; quoted, compose reads the whole list as one file name"
    ),
    "BRAIN_OS_ID": (
        "holds ID and ID_LIKE from /etc/os-release together, and the loop walks it a word at "
        "a time looking for the first distribution with a documented Docker route"
    ),
}

#: Why an unquoted expansion anywhere else is a defect rather than a style question.
AN_UNQUOTED_EXPANSION_IS_A_PATH_WITH_A_SPACE_IN_IT: Final = (
    "Every value this script expands came from a flag, a prompt or a file on somebody else's "
    "server: a release tag, a console address, a version string, the contents of "
    "/etc/os-release. Unquoted, a value with a space in it becomes two arguments and a value "
    "with a * in it becomes whatever is in the current directory, and the install does "
    "something nobody wrote down rather than failing. The two exceptions are declared in "
    "SPLIT_ON_PURPOSE, because an exception nobody declared is indistinguishable from a "
    "mistake nobody caught."
)


def unquoted_expansions(
    script: str, allowed: Mapping[str, str] = SPLIT_ON_PURPOSE
) -> tuple[str, ...]:
    """Every variable this script expands outside quotes, other than the declared exceptions.

    A scanner rather than a regular expression, because the two constructs that matter are
    exactly the ones a regular expression cannot see. `awk '/MemTotal/ {print int($2 / 1024)}'`
    holds a dollar inside single quotes, where nothing expands at all, and a pattern counting
    quote characters across the line would read it as unquoted. And `$(...)` opens a context
    whose quoting is its own, so the quote state either side of it is not the state inside it.

    Arithmetic is skipped for the same reason single quotes are: `$((BRAIN_REFUSALS + 1))`
    names a variable and expands nothing that a word could split.
    """
    findings: list[str] = []
    quotes = [""]
    index = 0
    while index < len(script):
        character = script[index]
        if quotes[-1] == "'":
            if character == "'":
                quotes[-1] = ""
            index += 1
            continue
        if character == chr(92):
            index += 2
            continue
        if character == "#" and quotes[-1] == "" and (index == 0 or script[index - 1] in " \t\n;"):
            # A comment, which quotes nothing. The step headings are comments and carry prose, and
            # an apostrophe in one read as a quote put the rest of the script in single quotes
            # until the next apostrophe, which hid every expansion in between.
            end = script.find("\n", index)
            index = len(script) if end < 0 else end
            continue
        if character == "'" and quotes[-1] == "":
            quotes[-1] = "'"
            index += 1
            continue
        if character == '"':
            quotes[-1] = "" if quotes[-1] == '"' else '"'
            index += 1
            continue
        if character == ")" and len(quotes) > 1 and quotes[-1] == "":
            quotes.pop()
            index += 1
            continue
        if character != "$":
            index += 1
            continue
        if script.startswith("$((", index):
            index = _past_arithmetic(script, index)
            continue
        if script.startswith("$(", index):
            quotes.append("")
            index += 2
            continue
        name, index = _expansion_at(script, index)
        if not name or quotes[-1] == '"' or name in allowed:
            continue
        findings.append(
            f"${name} is expanded outside quotes, so a value with a space or a glob in it "
            f"becomes something else before the command sees it. "
            f"{AN_UNQUOTED_EXPANSION_IS_A_PATH_WITH_A_SPACE_IN_IT}"
        )
    return tuple(findings)


def _past_arithmetic(script: str, index: int) -> int:
    """The index after a `$((...))`, or after the `$` when it is never closed."""
    end = script.find("))", index)
    return len(script) if end < 0 else end + 2


def _expansion_at(script: str, index: int) -> tuple[str, int]:
    """The variable named by the `$` at `index`, and where to carry on reading.

    An empty name for a `$` that names nothing, which is a literal dollar in prose and is not
    an expansion anybody could have quoted.
    """
    rest = script[index + 1 :]
    if rest.startswith("{"):
        closing = rest.find("}")
        if closing < 0:
            return "", index + 1
        inside = rest[1:closing]
        name = ""
        for character in inside.lstrip("#!"):
            if character.isalnum() or character == "_":
                name += character
            else:
                break
        return name, index + closing + 2
    name = ""
    for character in rest:
        if character.isalnum() or character == "_":
            name += character
        else:
            break
    if name:
        return name, index + 1 + len(name)
    if rest[:1] in {"#", "@", "*", "?", "-", "$", "!"}:
        return "", index + 2
    return "", index + 1


def refusal(what: str, found: str) -> str:
    """One refusal line: what this machine has, then the reason the requirement is on the list.

    **The reason is read out of `RUNTIME_REQUIREMENTS` rather than retyped.** A refusal carrying
    its own copy of the sentence is a second answer to why the requirement exists, and the copy
    is the one that stops matching the module that owns it. It is also the half that matters:
    "Docker Compose v2 is not installed" is a refusal somebody works around in ten minutes, and
    the sentence after it is what stops them.
    """
    one = _requirement(what)
    wanted = f", and {one.minimum} or newer is needed" if one.minimum else ""
    return f'refuse "{found}{as_shell_text(wanted)}. {as_shell_text(one.why)}"'


_LINUX: Final = "a 64-bit Linux with cgroup v2"
_ENGINE: Final = "Docker Engine"
_COMPOSE: Final = "Docker Compose v2, as the `docker compose` subcommand"
_FETCHERS: Final = "curl and tar"
_OPENSSL: Final = "openssl"
_PROXY: Final = "a reverse proxy terminating TLS on 443"


def _linux_check() -> str:
    """Operating system, word size and the cgroup hierarchy, as three separate answers."""
    return "\n".join(
        (
            'test "$(uname -s)" = "Linux" || ' + refusal(_LINUX, "this machine runs $(uname -s)"),
            'case "$(uname -m)" in',
            "  x86_64|aarch64|arm64) ;;",
            "  *) " + refusal(_LINUX, "this machine is $(uname -m), which is not 64-bit") + " ;;",
            "esac",
            'test -e "/sys/fs/cgroup/cgroup.controllers" || '
            + refusal(_LINUX, "this kernel is not on the cgroup v2 unified hierarchy"),
        )
    )


def _engine_check() -> str:
    """The engine's version, out of the daemon rather than the client.

    The server's version and not the client's, because the client is a binary and the engine is
    what honours a `deploy` block. A daemon that is installed and not running answers nothing,
    which is a different refusal and reads as one.
    """
    minimum = _requirement(_ENGINE).minimum
    return "\n".join(
        (
            'BRAIN_ENGINE="$(docker version --format "{{.Server.Version}}" 2>/dev/null || true)"',
            'if test -z "$BRAIN_ENGINE"; then',
            "  " + refusal(_ENGINE, "the docker daemon on this machine is not answering"),
            f'elif ! at_least "$BRAIN_ENGINE" "{minimum}"; then',
            "  " + refusal(_ENGINE, "this machine runs Docker Engine $BRAIN_ENGINE"),
            "fi",
        )
    )


def _compose_check() -> str:
    """The compose plugin's version, and the refusal that names the old tool by name."""
    minimum = _requirement(_COMPOSE).minimum
    return "\n".join(
        (
            'BRAIN_COMPOSE_VERSION="$(docker compose version --short 2>/dev/null || true)"',
            'if test -z "$BRAIN_COMPOSE_VERSION"; then',
            "  "
            + refusal(
                _COMPOSE,
                "this machine has no docker compose subcommand, which usually means the older "
                "docker-compose is installed instead",
            ),
            f'elif ! at_least "$BRAIN_COMPOSE_VERSION" "{minimum}"; then',
            "  " + refusal(_COMPOSE, "this machine runs compose $BRAIN_COMPOSE_VERSION"),
            "fi",
        )
    )


#: Every requirement, as the shell that asks this machine for it, in the order a person wants
#: to be told.
#:
#: Ordered so the cheapest and most disqualifying questions come first: a machine that is not
#: Linux is told immediately, and the two version comparisons come after the step that may have
#: just installed Docker. `refuse` records rather than exits, so one run reports everything that
#: is wrong with the machine rather than one thing per run.
CHECKS: Final[tuple[Check, ...]] = (
    Check(requirement=_LINUX, run=_linux_check()),
    Check(
        requirement=_FETCHERS,
        run="\n".join(
            (
                "for one in curl tar; do",
                '  command -v "$one" >/dev/null 2>&1 || '
                + refusal(_FETCHERS, "$one is not installed"),
                "done",
            )
        ),
    ),
    Check(
        requirement=_OPENSSL,
        run="command -v openssl >/dev/null 2>&1 || "
        + refusal(_OPENSSL, "openssl is not installed"),
    ),
    Check(requirement=_ENGINE, run=_engine_check()),
    Check(requirement=_COMPOSE, run=_compose_check()),
    Check(
        requirement=_PROXY,
        refuses=False,
        run=(
            'say "  note: a reverse proxy terminating TLS on 443 is part of this install and '
            "nothing running on this machine can check for it. "
            f'{as_shell_text(_requirement(_PROXY).why)} See docs/install/network.md."'
        ),
    ),
)


def requirements_without_a_check(
    checks: Sequence[Check] = CHECKS,
    requirements: Sequence[Requirement] = RUNTIME_REQUIREMENTS,
) -> tuple[str, ...]:
    """Every requirement of a server that this script never asks the server about.

    The direction that matters, and it is the one nobody finds by running the installer: a
    requirement added to `RUNTIME_REQUIREMENTS` and to no check is documented, believed, and
    never tested on a single machine. See
    `A_REQUIREMENT_WITH_NO_CHECK_IS_ONE_THE_SERVER_DISCOVERS_LATE`.
    """
    asked = {one.requirement for one in checks}
    return tuple(
        f"{one.what!r} is a requirement of every server and no check asks for it, so an "
        "install without it fails somewhere else, later, as something that reads as a "
        "different fault"
        for one in requirements
        if one.what not in asked
    )


def checks_without_a_requirement(
    checks: Sequence[Check] = CHECKS,
    requirements: Sequence[Requirement] = RUNTIME_REQUIREMENTS,
) -> tuple[str, ...]:
    """Every check that turns a machine away over something nothing declares a requirement.

    The other half, and it is not symmetry for its own sake: a check with no requirement behind
    it is a refusal whose reason nobody wrote down, and `Requirement` exists precisely because
    that is the refusal somebody switches off on the day it is inconvenient.
    """
    declared = {one.what for one in requirements}
    return tuple(
        f"the check for {one.requirement!r} refuses a machine over something "
        "RUNTIME_REQUIREMENTS does not list, so its reason is in a script and nowhere else"
        for one in checks
        if one.requirement not in declared
    )


def _docker_route() -> str:
    """Docker's own per-distribution install, chosen from `/etc/os-release`.

    **Both package routes write the repository definition with a redirect rather than a pipe
    into `tee`**, which is the spelling Docker's documentation uses and is one of the two
    reasons this script sets `pipefail`: a `curl | tee` whose curl failed leaves an empty
    package source, `tee` exits zero, and the install fails three commands later with a message
    about a package that does not exist.
    """
    apt = " ".join(sorted(DOCKER_APT_ROUTES))
    dnf = " ".join(sorted(DOCKER_DNF_ROUTES))
    return "\n".join(
        (
            'test -r "/etc/os-release" || fail "there is no /etc/os-release on this machine, '
            f"so nothing here can tell which install route Docker documents for it. Install "
            f'Docker Engine and the compose plugin yourself: {DOCKER_DOCUMENTATION_URL}"',
            'BRAIN_OS_ID="$(. /etc/os-release && printf "%s" "${ID:-} ${ID_LIKE:-}")"',
            'test "$(id -u)" -eq 0 || fail "installing Docker needs root and this is not a '
            "root shell. Run this again with sudo, or install Docker Engine and the compose "
            f'plugin yourself: {DOCKER_DOCUMENTATION_URL}"',
            'BRAIN_DOCKER_ROUTE=""',
            "for one in $BRAIN_OS_ID; do",
            '  case "$one" in',
            f'    {apt.replace(" ", "|")}) BRAIN_DOCKER_ROUTE="apt $one" ;;',
            f'    {dnf.replace(" ", "|")}) BRAIN_DOCKER_ROUTE="dnf $one" ;;',
            "    *) continue ;;",
            "  esac",
            "  break",
            "done",
            'test -n "$BRAIN_DOCKER_ROUTE" || fail "this is $BRAIN_OS_ID, and the routes '
            f"Docker documents and this script knows are: {apt} {dnf}. Install Docker Engine "
            f"24 or newer with the compose plugin by the route your distribution documents, "
            f'then run this again: {DOCKER_DOCUMENTATION_URL}"',
            'say "  installing Docker by the $BRAIN_DOCKER_ROUTE route Docker documents"',
            'case "$BRAIN_DOCKER_ROUTE" in',
            "  apt*)",
            "    export DEBIAN_FRONTEND=noninteractive",
            "    apt-get update",
            "    apt-get install -y ca-certificates curl",
            '    install -m 0755 -d "/etc/apt/keyrings"',
            f'    curl -fsSL "{DOCKER_PACKAGES_URL}/${{BRAIN_DOCKER_ROUTE#apt }}/gpg" '
            '-o "/etc/apt/keyrings/docker.asc"',
            '    chmod a+r "/etc/apt/keyrings/docker.asc"',
            '    printf "deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] '
            f'{DOCKER_PACKAGES_URL}/%s %s stable\\n" "$(dpkg --print-architecture)" '
            '"${BRAIN_DOCKER_ROUTE#apt }" "$(. /etc/os-release && printf "%s" '
            '"${VERSION_CODENAME:-}")" > "/etc/apt/sources.list.d/docker.list"',
            "    apt-get update",
            f"    apt-get install -y {DOCKER_PACKAGES}",
            "    ;;",
            "  dnf*)",
            "    dnf -y install dnf-plugins-core",
            f'    dnf -y config-manager --add-repo "{DOCKER_PACKAGES_URL}/'
            '${BRAIN_DOCKER_ROUTE#dnf }/docker-ce.repo"',
            f"    dnf -y install {DOCKER_PACKAGES}",
            "    ;;",
            "esac",
            'systemctl enable --now docker || fail "Docker installed and its daemon would not '
            "start. Read the output of systemctl status docker, start it, then run this "
            "again. Nothing of "
            'this install has been written yet"',
        )
    )


#: The steps that run before `brain.deployment.installer.PLAN`, in the order they run.
#:
#: Every one of them is about the machine rather than about the install, which is the line
#: between this tuple and that one: nothing here writes anything under the install directory,
#: and `PLAN` assumes a machine that has already answered all of it.
PREPARE: Final[tuple[Step, ...]] = (
    Step(
        name="check this machine can run it",
        run="\n".join(
            (
                'say "  checking this machine against the requirements every install has"',
                *(one.run for one in CHECKS if one.requirement not in (_ENGINE, _COMPOSE)),
                'test "$BRAIN_REFUSALS" -eq 0 || fail "this machine cannot run it yet, for the '
                "reasons above. Nothing has been written. When a reason is one you cannot fix "
                'on this machine, docs/install/install.md has the sequence by hand"',
            )
        ),
        why=(
            "every requirement in brain.deployment.requirements.RUNTIME_REQUIREMENTS carries "
            "the sentence saying what breaks without it, and this is where each of them is "
            "asked of the machine rather than of the reader. All of them are asked before any "
            "of them refuses, so one run reports everything that is wrong"
        ),
        on_failure=(
            "read the reasons printed above this line. Nothing has been written, so a machine "
            "that can be fixed can run this again, and a machine that cannot has the sequence "
            "by hand in docs/install/install.md"
        ),
        changes=False,
    ),
    Step(
        name="install docker if it is missing",
        run=_docker_route(),
        why=(
            "the one requirement this script can satisfy rather than only report, by the route "
            "Docker documents for the distribution it finds in /etc/os-release. A distribution "
            "with no documented route here is told exactly what to install and where the "
            "instructions are, rather than handed a script piped from the internet into a root "
            "shell"
        ),
        on_failure=(
            "the package manager said what went wrong above this line. Install Docker Engine 24 "
            f"or newer with the compose plugin yourself ({DOCKER_DOCUMENTATION_URL}) and run this "
            "again with --no-install-docker. Nothing of the install has been written yet"
        ),
        changes=True,
        already_done=(
            'test "$BRAIN_INSTALL_DOCKER" = "no" || '
            "{ command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; }"
        ),
    ),
    Step(
        name="check the docker on this machine is new enough",
        run="\n".join(
            (
                *(one.run for one in CHECKS if one.requirement in (_ENGINE, _COMPOSE)),
                'test "$BRAIN_REFUSALS" -eq 0 || fail "the Docker on this machine is not one '
                'this deployment can run, for the reasons above. Nothing has been written"',
            )
        ),
        why=(
            "asked after the step that may have just installed Docker, and asked about the "
            "versions rather than about the presence that PLAN's own first step asks about. "
            "The compose version is the requirement that fails silently: the older tool starts "
            "every container with no memory ceiling at all and says nothing"
        ),
        on_failure=(
            "upgrade Docker Engine and the compose plugin by the route your distribution "
            "documents, then run this again. Nothing has been written"
        ),
        changes=False,
    ),
)

#: The last step, which is the handover: where to go, and what happens when you get there.
#:
#: After `PLAN`, because `PLAN`'s own last step is the one that prints the setup code and this
#: one says what to do with it. Two steps rather than one because the code is a value and this
#: is prose: `Step.presents_once` is the exemption from the leak check and it belongs on the
#: smallest possible step, not on one that also prints three paragraphs.
HANDOVER: Final[tuple[Step, ...]] = (
    Step(
        name="say where to go next",
        run="\n".join(
            (
                'say ""',
                'if test -n "$BRAIN_CONSOLE_ADDRESS"; then',
                '  printf "Open %s/first-run and enter the code above.\\n" '
                '"${BRAIN_CONSOLE_ADDRESS%/}"',
                "else",
                '  say "No service in this deployment publishes a port, so the console answers '
                "on whatever address your reverse proxy sends to the app service. Open "
                '/first-run on that address and enter the code above."',
                "fi",
                'say "Sign in there first, then enter the code: it is held in that one browser '
                'tab and a reload loses it."',
                'say "Until somebody does, this system has no administrator and whoever opens '
                'that address first becomes one."',
                'say "docs/install/install.md, under The setup code, is the rest of it."',
            )
        ),
        why=(
            "the install is finished and the person is not: the value printed by the step "
            "above is useless without the address it is entered at, and the address is the one "
            "fact this deployment cannot discover, because nothing in it publishes a port. See "
            "AN_ADDRESS_NOBODY_SUPPLIED_IS_NOT_LOCALHOST"
        ),
        on_failure=(
            "the install is complete either way; this step only prints. Open /first-run on the "
            "address your reverse proxy serves"
        ),
        changes=False,
    ),
)


def install_plan(plan: Sequence[Step] = PLAN) -> tuple[Step, ...]:
    """Everything this script runs, in the order it runs it.

    The machine's own requirements, then the install `brain.deployment.installer` owns
    unchanged, then the handover. Concatenated rather than merged, so that the middle of this
    list is the same object the update script derives from and the same object the guide's
    manual sequence is checked against.
    """
    return (*PREPARE, *plan, *HANDOVER)


def _usage(profiles: Sequence[str] = PROFILES) -> tuple[str, ...]:
    """The usage message, built from `FLAGS` so a flag cannot be added to only one of them."""
    widest = max(len(flag) for flag, _ in FLAGS)
    return (
        "usage() {",
        '  say "usage: install.sh --release <tag> [--profile <name>] [--console-address <url>]"',
        '  say ""',
        *(f'  say "  {flag.ljust(widest)}  {meaning}"' for flag, meaning in FLAGS),
        '  say ""',
        f'  say "  {RELEASE_URL_VARIABLE} must be set in the environment: it is the address '
        'of the release archive."',
        "}",
    )


def _helpers() -> tuple[str, ...]:
    """The shell functions the preamble and the steps use.

    `at_least` compares two versions with `sort -V` and reads the first line with `sed` rather
    than `head`. That is not a preference: `head` closes the pipe on the line it wanted, `sort`
    takes SIGPIPE, and under the `pipefail` this script sets that is a failed pipeline in the
    middle of a version comparison. `sed` reads its input to the end.
    """
    return (
        'say() { printf "%s\\n" "$1"; }',
        'fail() { printf "%s\\n" "$1" >&2; exit 1; }',
        'refuse() { printf "  %s\\n" "$1" >&2; BRAIN_REFUSALS=$((BRAIN_REFUSALS + 1)); }',
        "at_least() {",
        '  test "$(printf "%s\\n%s\\n" "$2" "$1" | sort -V | sed -n "1p")" = "$2"',
        "}",
        "ask() {",
        '  test -t 0 || fail "$2"',
        '  printf "%s " "$1" >&2',
        "  read -r BRAIN_ANSWER",
        '  printf "%s" "$BRAIN_ANSWER"',
        "}",
    )


def _arguments(profiles: Sequence[str] = PROFILES) -> tuple[str, ...]:
    """Reading the flags, then asking for what a person can be asked for.

    The order is the argument: every flag is read before any prompt, so a run that supplied
    everything never reaches a prompt and never needs a terminal. A prompt with no terminal
    fails by naming the flag it wanted, because the alternative is a script that blocks for
    ever in somebody's deployment pipeline.
    """
    names = " ".join(profiles)
    return (
        'while test "$#" -gt 0; do',
        '  case "$1" in',
        f'    --profile) BRAIN_PROFILE="${{2:?--profile needs one of: {names}}}"; shift 2 ;;',
        '    --release) BRAIN_RELEASE="${2:?--release needs a release tag}"; shift 2 ;;',
        '    --console-address) BRAIN_CONSOLE_ADDRESS="${2:?--console-address needs the '
        'address your reverse proxy will serve}"; shift 2 ;;',
        '    --no-install-docker) BRAIN_INSTALL_DOCKER="no"; shift ;;',
        f'    {vault_setup.DECLINE_FLAG}) BRAIN_VAULT="no"; shift ;;',
        "    --help|-h) usage; exit 0 ;;",
        '    *) usage >&2; fail "unknown option: $1" ;;',
        "  esac",
        "done",
        "",
        'test -n "$BRAIN_RELEASE" || { usage >&2; fail "--release is required and there is '
        'deliberately no default: a default of latest is what makes an install unpinned"; }',
        'test "$BRAIN_RELEASE" != "latest" || fail "latest is not a release tag: installing it '
        "leaves this install unpinned, so the next pull changes the version with nobody "
        'deciding anything. Name the release you mean to install"',
        "",
        'if test -z "$BRAIN_PROFILE"; then',
        f'  BRAIN_PROFILE="$(ask "Which profile? one of: {names}:" "--profile was not given '
        f'and there is no terminal to ask at. Pass --profile with one of: {names}")"',
        "fi",
        'if test -z "$BRAIN_CONSOLE_ADDRESS" && test -t 0; then',
        '  BRAIN_CONSOLE_ADDRESS="$(ask "What address will your reverse proxy serve the '
        'console on? (blank if you have not decided yet):" "pass --console-address, or leave '
        'it out: the install finishes either way")"',
        "fi",
    )


def _profile_case(
    *,
    services: Mapping[str, int],
    memory_mib: Mapping[str, int],
    profiles: Sequence[str] = PROFILES,
) -> tuple[str, ...]:
    """The three figures a profile decides, as the shell chooses between them.

    `brain.deployment.installer.render` bakes one profile's figures into one script, which is
    right for a caller that already knows the profile and wrong for a file a client fetches
    before they have chosen one. The arm carries all three because all three come from one
    `ServerSpec`, and splitting them would let a script pin one profile's memory against
    another's file list.
    """
    arms = []
    for profile in profiles:
        assert_known_profile(profile)
        if profile not in services or profile not in memory_mib:
            msg = (
                f"{profile!r} has no figures to render, and a profile arm with no memory figure "
                "would install onto a machine nothing measured"
            )
            raise InstallScriptError(msg)
        arms.append(
            f'  {profile}) BRAIN_COMPOSE_FILES="{compose_files_argument(profile)}"; '
            f'{vault_setup.WORKER_FILES_VARIABLE}="'
            f'{vault_setup.worker_files_argument(profile, home=INSTALL_HOME)}"; '
            f'BRAIN_SERVICES="{services[profile]}"; '
            f'BRAIN_MEMORY_MIB="{memory_mib[profile]}" ;;'
        )
    return (
        'case "$BRAIN_PROFILE" in',
        *arms,
        f'  *) fail "unknown profile: $BRAIN_PROFILE. One of: {" ".join(profiles)}" ;;',
        "esac",
    )


def render_install(
    *,
    services: Mapping[str, int],
    memory_mib: Mapping[str, int],
    repository: str = PRODUCT_IMAGE,
    plan: Sequence[Step] = PLAN,
    profiles: Sequence[str] = PROFILES,
) -> str:
    """The installer, as the shell it is, for every profile at once.

    `services` and `memory_mib` are passed rather than computed, for the reason
    `brain.deployment.installer.render` takes its two figures and every function in
    `brain.ops.compose` takes documents somebody else parsed: rendering a script is not a good
    enough excuse to open a file, and a caller who has the compose documents has both figures
    from `brain.deployment.requirements.spec_for`.

    The output is numbered against the length of the plan, so "step 4 of 18" is arithmetic
    rather than a number somebody typed and stopped updating.
    """
    steps = install_plan(plan)
    total = len(steps)
    lines = [
        "#!/bin/bash",
        "# Generated by brain.deployment.install_script.render_install. Do not edit: edit the",
        "# plan and regenerate, or the script and the plan disagree and the plan is the tested",
        "# one.",
        "set -euo pipefail",
        "",
        f'BRAIN_HOME="{INSTALL_HOME}"',
        f'BRAIN_REPOSITORY="{repository}"',
        'BRAIN_PROFILE=""',
        'BRAIN_RELEASE=""',
        'BRAIN_CONSOLE_ADDRESS=""',
        'BRAIN_INSTALL_DOCKER="yes"',
        'BRAIN_VAULT="yes"',
        "BRAIN_REFUSALS=0",
        "",
        *_helpers(),
        "",
        *_usage(profiles),
        "",
        *_arguments(profiles),
        "",
        *_profile_case(services=services, memory_mib=memory_mib, profiles=profiles),
        *vault_setup.decline_lines(),
        f'BRAIN_RELEASE_URL="${{{RELEASE_URL_VARIABLE}:?set {RELEASE_URL_VARIABLE} to the '
        'release archive for $BRAIN_RELEASE}"',
        "",
        f'say "Installing the $BRAIN_PROFILE profile of $BRAIN_RELEASE into $BRAIN_HOME, '
        f'{total} steps."',
        "",
    ]
    for number, step in enumerate(steps, 1):
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
    lines.append('say "Done. The $BRAIN_PROFILE profile is running from $BRAIN_HOME."')
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Print the script, which is how the committed file under `ops/install/` is produced.

    The compose documents are read here and nowhere else in this module, which is the split
    every check in `brain.ops.compose` keeps: the renderer takes figures and this reads them.
    Imported inside the function rather than at the top, because `brain.deployment.release` is
    the release machinery and nothing about rendering an install script should make a module
    that runs on a client's server depend on it.
    """
    from brain.deployment.release import REPO, compose_documents
    from brain.deployment.requirements import files_for, spec_for

    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print(f"usage: python -m {__name__}", file=sys.stderr)
        return 2
    files = compose_documents(REPO)
    specs = {
        profile: spec_for(profile, {name: files[name] for name in files_for(profile)})
        for profile in PROFILES
    }
    print(
        render_install(
            services={name: one.containers for name, one in specs.items()},
            memory_mib={name: one.memory_mib for name, one in specs.items()},
        ),
        end="",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - the command that writes the committed script
    raise SystemExit(main())
