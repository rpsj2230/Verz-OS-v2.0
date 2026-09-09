"""What reaches a client's server, and the three things a release has to say in plain English.

**No release archive has ever been published, and the consequence is not a missing
convenience.** `brain.deployment.installer.PLAN` fetches one archive of one tag and unpacks it
into `/opt/brain`, and until this module nothing in this repository produced one, so a copy of
this git repository was the only way the compose files and `ops/` could reach a server. That
copy carries `.github/` and the whole history, and three commits in this history hold the
first deployment's host and address in files that have since been cleaned. A commit cannot be
un-made. So the fix is not to clean the history, it is that a client never receives the
repository at all, which is exactly what an archive of one tag is for. See
`A_CLIENT_MUST_NEVER_RECEIVE_A_COPY_OF_THIS_REPOSITORY`.

**What exists now is the declaration and the workflow, and nothing has been tagged**, so the
honest state is that an archive can be built and none has been published.
`docs/install/install.md` says so in those words under "What you cannot do today", because a
page claiming an install can be followed end to end is worth less than one that says which
step still has nothing to fetch.

**The file list is an allowlist and never a set of `tar --exclude` flags.** An exclusion list
is written against the tree that exists on the day somebody writes it, and every file added
afterwards ships by default: a script added under `ops/` for this deployment's own VPS would
reach a client's server with nobody having decided it should. The include list names what a
client needs, everything else is out by construction, and the exclusions are the net under a
widened include rather than the mechanism. `docker-compose.staging.yml` is the worked example:
it is out of the archive because no profile composes it, not because a rule names it.

**The include list is derived from the install, not chosen.** The environment template is
there because the plan copies it; each compose file is there because `files_for` names it for
some profile; the four `ops/...` paths are there because a service in one of those files
bind-mounts them, and a bind mount that resolves to nothing starts the container anyway with
no error at all. `archive_gaps` computes that set from the plan and the compose documents and
reports anything the archive would not carry, because **a mismatch between the archive and the
install plan is a failure a client meets on their own server and nobody here ever sees**.

**Whether a release changes the database is read out of the release, never typed into it.**
A person typing "no schema change" on a release that has one is the exact failure the field
exists to prevent, so there is no field to type: `ReleaseNotes.database` folds
`brain.deployment.compatibility.changes_in` over the migrations the release carries, and the
same reader with its two arguments swapped answers whether going back is safe. See
`WHETHER_IT_CHANGES_THE_DATABASE_IS_READ_AND_NEVER_TYPED`.

Rejected: building the archive here, in Python, and having the workflow call one function. It
reads well and it puts a tar writer in a module whose whole job is a declaration, for no gain:
the workflow already has GNU tar, and what it cannot be trusted with is the list. So the module
prints the list and the workflow pipes it into `tar -T`, which is the same split
`brain.ops.limits` keeps from `brain.ops.limit_store`.

Rejected: `tar --exclude '.git' --exclude '.github' ...` in the workflow, which is how this is
usually written. It puts the decision in a file no test reads, so the exclusions and the tests
would be two lists that agree until somebody edits one. Everything here is asked of the module,
including where the migrations live, so there is no path spelled in the workflow at all and
`tests/unit/test_deployment_release.py` can assert that.

Rejected: deriving urgency the way the database answer is derived. Nothing in a diff says
whether a fix is one an attacker can reach, and a rule guessing from the files touched would be
wrong in the direction that costs a client a week of exposure. Urgency is a person's judgement,
so it is stated, and what is enforced is that it is stated at all and that a release breaking
the schema cannot be called routine.

Task ids: M42.3.8
"""

from __future__ import annotations

import enum
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Final

from brain.deployment.compatibility import VERSIONS, Verdict, changes_in
from brain.deployment.installer import INSTALL_HOME, PLAN, Step
from brain.deployment.requirements import files_for
from brain.ops.compose import ComposeDoc, ComposeFiles
from brain.ops.wiring import PROFILES

REPO: Final = Path(__file__).resolve().parents[3]

#: An empty migration set, named so a frozen dataclass can default to it without a call.
NO_MIGRATIONS: Final[Mapping[str, str]] = MappingProxyType({})


class ReleaseError(Exception):
    """Raised when a release would say something untrue, or would carry something it must not."""


# ------------------------------------------------------------------ written-down reasons
#: Why the archive exists at all, which is not packaging convenience.
A_CLIENT_MUST_NEVER_RECEIVE_A_COPY_OF_THIS_REPOSITORY: Final = (
    "The installer fetches one archive of one tag and never clones, so a client's server "
    "holds the files and not the repository they came from. Three commits in this history "
    "carry the first deployment's host and address in files that have since been cleaned, a "
    "commit cannot be un-made, and a copy of the repository carries them however tidy the "
    "working tree is. The archive is the structural answer rather than a tidier history: it "
    "carries no .git, no .github and no history, so there is nothing left to clean."
)

#: Why the list is an allowlist rather than a set of exclusions.
AN_EXCLUSION_LIST_SHIPS_EVERY_FILE_ADDED_AFTER_IT_WAS_WRITTEN: Final = (
    "A `tar --exclude` list is written against the tree that exists on the day somebody "
    "writes it, and everything added afterwards ships by default. A script added under `ops/` "
    "for this deployment's own machine would reach a client's server with nobody having "
    "decided it should, and the first sign would be a client reading a runbook about a server "
    "they do not own. So the include list names what a client needs, everything else is out "
    "by construction, and the refusals below are the net under a widened include."
)

#: Why a missing path is the failure this check exists for.
A_PATH_THE_INSTALL_READS_AND_THE_ARCHIVE_LACKS_FAILS_ON_SOMEBODY_ELSES_SERVER: Final = (
    "The install unpacks the archive into /opt/brain and then reads files from there: the "
    "environment template it copies, the compose files it names with -f, and the paths those "
    "files bind-mount. A missing compose file fails loudly. A missing bind-mount source does "
    "not: docker creates an empty directory where the file should be and starts the container "
    "anyway, so a memory ceiling, an egress allowlist and a set of object-store credentials go "
    "missing with nothing to read and every health check green. Nobody here would ever see it."
)

#: Why nobody types the answer to "does this change the database".
WHETHER_IT_CHANGES_THE_DATABASE_IS_READ_AND_NEVER_TYPED: Final = (
    "A person typing 'no schema change' on a release that has one is the exact failure this "
    "field exists to prevent: the client reads it, decides they do not need the backup, and "
    "finds out from the console. So there is no field to type. The answer is folded out of the "
    "migrations the release carries by brain.deployment.compatibility.changes_in, which is the "
    "reader this repository already has, and the same reader with its two arguments swapped "
    "answers whether going back is safe."
)

#: Why urgency and the database answer are not independent.
A_BREAKING_SCHEMA_CHANGE_IS_NEVER_ROUTINE: Final = (
    "Routine means install it whenever you next install anything, which is a client "
    "scheduling no window and taking no backup. A release the previous version cannot run "
    "against needs both. The two fields are written by different halves of the same person "
    "and this is the pair that has to agree, so it is refused rather than reviewed."
)

#: Why a note naming a module is not a note.
A_NOTE_A_CLIENT_CANNOT_ACT_ON_IS_A_COMMIT_SUBJECT: Final = (
    "A client's IT team has no source tree, no module names and no task ids. A note reading "
    "'fix leash.py resume path, closes M12.2.4' is a commit subject that has been pasted into "
    "the one field written for somebody outside this repository, and it reads as coverage: "
    "the release has notes, and nobody can act on them. Plain English is the requirement and "
    "this is the part of it a machine can hold."
)


# ------------------------------------------------------------------ the declaration
@dataclass(frozen=True)
class Rule:
    """One line of the archive declaration, and the sentence saying why it is there.

    `why` is required for the same reason `brain.ops.starter.Default.meaning` is: this is what
    the next person reads when they wonder whether a path still belongs, and a line nobody can
    explain is one that gets deleted by whoever is tidying, or copied by whoever is adding.
    """

    #: A repository-relative path for an include, or a glob for a refusal.
    pattern: str
    why: str

    def __post_init__(self) -> None:
        if not self.pattern.strip():
            msg = "a rule with no pattern matches nothing and reads as a decision"
            raise ReleaseError(msg)
        if not self.why.strip():
            msg = f"{self.pattern!r} is in the declaration with no reason written down"
            raise ReleaseError(msg)


def _compose_rules(profiles: Sequence[str] = PROFILES) -> tuple[Rule, ...]:
    """One include per compose file some profile composes, read off `files_for`.

    Derived rather than listed, and the derivation is the check: a ninth compose file added to
    a profile is in the archive the same day, and a file no profile composes is out of it
    without anybody writing a refusal. `docker-compose.staging.yml` is the second case, and it
    is this repository's own staging stack rather than anything a client runs.
    """
    names = sorted({name for profile in profiles for name in files_for(profile)})
    return tuple(
        Rule(
            name,
            "the install runs `docker compose -f /opt/brain/" + name + "`, so a profile that "
            "names this file and an archive that does not carry it is a command that cannot run",
        )
        for name in names
    )


#: What the archive carries, and nothing else is in it.
#:
#: Every entry is a path rather than a glob, and a directory carries everything under it. See
#: `AN_EXCLUSION_LIST_SHIPS_EVERY_FILE_ADDED_AFTER_IT_WAS_WRITTEN` for why this is the shape,
#: and `install_needs` for the half of it that is computed: the compose files and the four
#: `ops/...` paths a service bind-mounts are derived, and `archive_gaps` reports any the list
#: below would miss.
INCLUDED: Final[tuple[Rule, ...]] = (
    *_compose_rules(),
    Rule(
        ".env.example",
        "the plan copies it to /opt/brain/.env and fills the values in there, so the template "
        "is the one file the whole of brain.install exists to keep neutral",
    ),
    Rule(
        "ops/automation",
        "the automation profile bind-mounts the egress allowlist from here, and a container "
        "that comes up without it is one whose outbound traffic nothing restricts",
    ),
    Rule(
        "ops/keycloak",
        "the identity realm every install imports, and the script that loads it. The realm "
        "reaches the container inside the image rather than through a mount, and it is here "
        "because an administrator reads and edits it on their own server",
    ),
    Rule(
        "ops/langfuse",
        "the trace ledger's memory configuration, bind-mounted by the full profile. Without "
        "it the container starts with its own default and the profile's memory arithmetic is "
        "describing a ceiling nothing set",
    ),
    Rule(
        "ops/openbao",
        "the vault policies, the credential slots and the unseal runbook. A client running the "
        "vault has to hold these on their own server, because a policy nobody can read is a "
        "permission nobody can review",
    ),
    Rule(
        "ops/seaweedfs",
        "the object store's credentials file and its provisioning script, both bind-mounted. "
        "The second is named as an entrypoint, so its absence at least fails loudly",
    ),
    Rule(
        "migrations",
        "the evidence for the release notes' database answer. The notes state whether a "
        "release changes the database and these files are what that claim was read from, so a "
        "client can check it rather than take it. docs/install/update-and-rollback.md already "
        "tells them to compare this directory between two tags",
    ),
    Rule(
        "alembic.ini",
        "a migration directory with no configuration beside it is not runnable, so the two "
        "travel together or neither is worth carrying",
    ),
    Rule(
        "docs/install",
        "the nine pages somebody reads standing in front of the server. Everything else under "
        "docs/ is this project's own record: the work breakdown, the build pages the console "
        "serves, and the owner's decision list",
    ),
)

#: What must never be in the archive, whatever the include list says.
#:
#: **None of these is reachable from the includes above today, and that is the design rather
#: than an argument that the list is decoration.** `refused_by` is consulted for every path
#: before it goes into the tar and `archive_gaps` reports any that got that far, so widening an
#: include cannot ship one of these quietly; it fails the release build instead. The test that
#: proves it widens an include and watches the refusal hold.
#:
#: `__pycache__` is deliberately not here. It is not a file of this repository at all, so it is
#: skipped while walking rather than refused afterwards, which is the same distinction
#: `brain.ops.independence._searched_files` makes when it reads an area.
EXCLUDED: Final[tuple[Rule, ...]] = (
    Rule(
        ".git",
        "the history, which is the whole reason this archive exists. Three commits in it carry "
        "the first deployment's host and address in files that have since been cleaned, and a "
        "commit cannot be un-made",
    ),
    Rule(
        ".github",
        "this repository's own pipeline, which names the machine this deployment runs on, the "
        "registry it pushes to and the identity it signs with. None of it is a client's",
    ),
    Rule(
        ".scratch",
        "agent scratch, gitignored and never committed, which means nothing has ever looked at "
        "what is in it and no sweep reads it",
    ),
    Rule(
        "tests",
        "the suite is not the product, and the invariant tests plant deliberate canary values "
        "for the sweeps to find, so shipping the suite ships the canaries",
    ),
    Rule(
        "src",
        "the application is deployed by tag as one published image. Source beside it on a "
        "client's server is a second copy of the product that a fix never reaches, which is "
        "the shape brain.ops.independence.duplication_gaps refuses",
    ),
    Rule(
        "console",
        "the administrative front end, built into the image for the same reason. A client "
        "server that could rebuild it could run a console the release never contained",
    ),
    Rule(
        "docs/needs-rupash.md",
        "the owner's own decision list. It is written about this project rather than about the "
        "product, and it held fourteen client values on the day the sweep was widened to read "
        "Markdown",
    ),
    Rule(
        ".env",
        "one install's own environment file, with the credentials that install minted in it. "
        "The template is a separate file and is carried; this one is nobody else's",
    ),
    Rule(
        ".venv",
        "a virtual environment built on somebody's laptop, with that machine's absolute paths "
        "compiled into its scripts",
    ),
    Rule(
        "*.pem",
        "a certificate or a private key. Neither belongs in a build artefact and one of them "
        "is a credential",
    ),
    Rule(
        "*.key",
        "a private key, wherever it turns up and whatever the include list says about the "
        "directory it is in",
    ),
)


def included_by(path: str, included: Sequence[Rule] = INCLUDED) -> str:
    """Which include rule puts this path in the archive, or an empty string.

    A path is carried when a rule names it or names a directory above it. Deliberately not a
    glob: an include is a decision about a file or a directory, and a glob in an allowlist is
    the same open-endedness the exclusion list was rejected for.
    """
    for rule in included:
        if path == rule.pattern or path.startswith(f"{rule.pattern}/"):
            return f"{rule.pattern}: {rule.why}"
    return ""


def refused_by(path: str, excluded: Sequence[Rule] = EXCLUDED) -> str:
    """Why the archive must never carry this path, or an empty string.

    Matched against the whole path and against every segment of it, so `.git` refuses
    `.git/config` and `*.key` refuses one anywhere. `fnmatchcase` rather than `fnmatch`, which
    normalises case through the host operating system: the same path would be refused on
    Windows and carried on Linux, and the release is built on Linux.
    """
    parts = PurePosixPath(path).parts
    for rule in excluded:
        if fnmatchcase(path, rule.pattern) or any(fnmatchcase(one, rule.pattern) for one in parts):
            return f"{rule.pattern}: {rule.why}"
    return ""


#: A directory of compiled bytecode, which is not a file of this repository. See `EXCLUDED`.
NOT_OF_THIS_REPOSITORY: Final = "__pycache__"


def carried_paths(tree: Path, included: Sequence[Rule] = INCLUDED) -> tuple[str, ...]:
    """Every path in this tree an include rule reaches, refusals not yet applied.

    Unfiltered on purpose. `archive_files` is what goes into the tar and it applies the
    refusals; this is what `archive_gaps` is asked about, so a path that an include reaches and
    a refusal rejects is **reported** rather than quietly dropped. A build that silently
    dropped it would go green on the day somebody widened an include, which is the one day
    anybody wants to be told.
    """
    found: set[str] = set()
    for rule in included:
        target = tree / rule.pattern
        if target.is_file():
            found.add(rule.pattern)
            continue
        if not target.is_dir():
            continue
        found.update(
            one.relative_to(tree).as_posix()
            for one in target.rglob("*")
            if one.is_file() and NOT_OF_THIS_REPOSITORY not in one.parts
        )
    return tuple(sorted(found))


def archive_files(
    tree: Path, included: Sequence[Rule] = INCLUDED, excluded: Sequence[Rule] = EXCLUDED
) -> tuple[str, ...]:
    """The file list the release workflow hands to `tar -T`, in a stable order."""
    return tuple(one for one in carried_paths(tree, included) if not refused_by(one, excluded))


# ------------------------------------------------------------------ what the install reads
#: A path under the install directory, wherever it appears on a line of the plan.
UNDER_THE_INSTALL_HOME: Final = re.compile(re.escape(INSTALL_HOME) + r"/([\w./-]+)")

#: The three ways a step of the plan creates a file rather than reading one: a redirect, curl's
#: output flag, and the destination half of a copy. A file the install writes is not a file the
#: archive owes it, and the four the plan writes today are the tarball, the RELEASE marker and
#: the environment file, twice.
WRITTEN_BY_THE_INSTALL: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r">>?\s*\"?" + re.escape(INSTALL_HOME) + r"/([\w./-]+)"),
    re.compile(r"-o\s+\"?" + re.escape(INSTALL_HOME) + r"/([\w./-]+)"),
    re.compile(r"\bcp\s+\"?[^\"\s]+\"?\s+\"?" + re.escape(INSTALL_HOME) + r"/([\w./-]+)"),
)


def paths_the_install_reads(plan: Sequence[Step] = PLAN) -> tuple[str, ...]:
    """Every path under the install directory the plan reads and does not write itself.

    Read out of the plan rather than listed, because the plan is where the answer changes: a
    step that starts reading a second file is a second file the archive owes it, and a list
    here would go on naming one. The written set is computed the same way and from the same
    text, so the tarball the install downloads and the environment file it creates are not
    mistaken for things the archive should have carried.
    """
    read: set[str] = set()
    written: set[str] = set()
    for step in plan:
        for fragment in (step.run, step.already_done):
            read.update(UNDER_THE_INSTALL_HOME.findall(fragment))
            for pattern in WRITTEN_BY_THE_INSTALL:
                written.update(pattern.findall(fragment))
    return tuple(sorted(read - written))


def mounts_in(files: ComposeFiles) -> tuple[str, ...]:
    """Every path beside the compose file that a service in this set bind-mounts.

    `brain.ops.compose.relative_bind_mounts` finds the same mounts and answers a different
    question: it reports, per service, that a container will come up without its configuration,
    which is what an operator acts on, and it hands back sentences rather than paths. This
    hands back the paths, because the question here is what the archive owes the install.
    `test_deployment_release.py` asserts the two agree on the set, so a mount one of them
    stops seeing is a failure rather than a divergence.

    Absolute and home-relative sources are skipped. They name a path on the host that the
    archive could not carry wherever it put the file, so reporting them here would be asking
    for a fix nobody can make in this repository.
    """
    found: set[str] = set()
    for name in sorted(files):
        for body in _services_in(files[name]).values():
            for source in _mount_sources(body):
                if source.startswith("./"):
                    found.add(source[2:])
    return tuple(sorted(found))


def _services_in(document: ComposeDoc) -> dict[str, Any]:
    services = document.get("services")
    return dict(services) if isinstance(services, dict) else {}


def _mount_sources(body: Any) -> tuple[str, ...]:
    """The source half of every volume entry, in both the short and the long spelling."""
    if not isinstance(body, Mapping):
        return ()
    sources: list[str] = []
    for entry in body.get("volumes") or ():
        if isinstance(entry, Mapping):
            sources.append(str(entry.get("source", "")))
        else:
            sources.append(str(entry).split(":", 1)[0])
    return tuple(sources)


def install_needs(
    plan: Sequence[Step] = PLAN,
    files: ComposeFiles | None = None,
    profiles: Sequence[str] = PROFILES,
) -> tuple[str, ...]:
    """Every path that has to be at /opt/brain after the archive is unpacked.

    Three sources and none of them is a list somebody keeps: what the plan reads, what
    `files_for` names for each profile, and what those documents bind-mount. `files` defaults
    to the compose documents of this repository, which is what makes calling this with no
    arguments the deployment check.
    """
    documents = compose_documents() if files is None else files
    needed = {
        *paths_the_install_reads(plan),
        *(name for profile in profiles for name in files_for(profile)),
        *mounts_in(documents),
    }
    return tuple(sorted(needed))


def compose_documents(tree: Path = REPO, profiles: Sequence[str] = PROFILES) -> ComposeFiles:
    """The compose files every profile composes, parsed, keyed by file name.

    The one read in this module, and it is here for the reason `brain.ops.compose` has none:
    every function above takes documents somebody else parsed, and this is the somebody for the
    no-argument case. The import is local, following `brain.ops.independence.compose_services`,
    because YAML is a development dependency and nothing on the request path may come to need
    it through this module.
    """
    import yaml

    documents: dict[str, ComposeDoc] = {}
    for profile in profiles:
        for name in files_for(profile):
            if name in documents:
                continue
            parsed = yaml.safe_load((tree / name).read_text(encoding="utf-8"))
            documents[name] = parsed if isinstance(parsed, dict) else {}
    return documents


def _client_values(tree: Path = REPO) -> tuple[str, ...]:
    """What the client-independence sweep found, as `path:line: what it is` strings.

    Imported inside the function because the sweep reads the whole tree and this module is
    otherwise a declaration. It is the same matchers rather than a second set: what is added
    here is the question the sweep does not ask, which is whether the file it found something
    in is one that gets handed to a client.
    """
    from brain.ops.independence import value_shaped_literals

    return value_shaped_literals(tree)


def archive_gaps(
    carried: Sequence[str] | None = None,
    needed: Sequence[str] | None = None,
    client_values: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Everything about the archive that would make it the wrong delivery.

    Three refusals, and they fail for three different people. A path the install reads that the
    archive would not carry is a client whose install stops, or worse comes up without it. A
    path the archive would carry that a refusal names is this repository reaching a client's
    server. A client value in a carried file is one client's details on another client's
    server, which is the first rule in CLAUDE.md arriving through the one route the sweep does
    not check, because the sweep asks whether a value is in the repository and never whether
    the file it is in gets handed over.

    **Takes its inputs, for the reason `brain.ops.starter.starter_gaps` argues at length.** Its
    first version read the constants directly, had nothing to report on today's data, and both
    of its refusals survived a mutation run: not because the checks were wrong but because no
    test could hand them a bad case. The defaults here are the real values, so calling this
    with no arguments is the deployment check and calling it with a constructed set is the test.
    """
    held = set(carried_paths(REPO) if carried is None else carried)
    wanted = install_needs() if needed is None else tuple(needed)
    values = _client_values() if client_values is None else tuple(client_values)

    findings = [
        f"{one}: the install reads {INSTALL_HOME}/{one} and the archive would not carry it. "
        f"{A_PATH_THE_INSTALL_READS_AND_THE_ARCHIVE_LACKS_FAILS_ON_SOMEBODY_ELSES_SERVER}"
        for one in sorted(set(wanted) - held)
    ]
    findings.extend(
        f"{one}: the archive would carry it and it is refused by {refused_by(one)}"
        for one in sorted(held)
        if refused_by(one)
    )
    findings.extend(
        f"{one.split(':', 1)[0]}: a client value reaches a file the archive carries, so it "
        f"reaches every other client's server. {one}"
        for one in values
        if one.split(":", 1)[0] in held
    )
    return tuple(findings)


# ------------------------------------------------------------------ what a release says
class DatabaseChange(enum.StrEnum):
    """What this release does to a client's database, read out of what it carries."""

    #: It carries no migration at all.
    NONE = "none"
    #: It carries migrations and the reading proved the previous release can still use the
    #: schema they leave behind.
    COMPATIBLE = "compatible"
    #: It carries migrations and part of the change could not be read from the source.
    UNREADABLE = "unreadable"
    #: It carries a migration the previous release provably cannot run against.
    BREAKING = "breaking"


#: The sentence a client reads for each answer. Written for somebody with a server and no
#: source tree, which is why none of them names a migration, a revision or a table.
WHAT_A_CLIENT_READS: Final[Mapping[DatabaseChange, str]] = MappingProxyType(
    {
        DatabaseChange.NONE: (
            "This release does not change your database. Installing it swaps the containers "
            "and nothing else."
        ),
        DatabaseChange.COMPATIBLE: (
            "This release changes your database, and the release you are running now keeps "
            "working against the changed database while the swap happens. Take a backup "
            "first anyway: that is what makes the sentence before this one worth trusting."
        ),
        DatabaseChange.UNREADABLE: (
            "This release changes your database and part of the change could not be read "
            "from the source, so treat it as one the release you are running now cannot use. "
            "Take a backup, and expect the console to be unavailable while it installs."
        ),
        DatabaseChange.BREAKING: (
            "This release changes your database in a way the release you are running now "
            "cannot use. Take a backup, expect the console to be unavailable while it "
            "installs, and read the line below about going back before you start."
        ),
    }
)

#: The sentence a client reads about the other direction, which is the one they need at the
#: moment they are least able to work it out for themselves.
GOING_BACK: Final[Mapping[DatabaseChange, str]] = MappingProxyType(
    {
        DatabaseChange.NONE: (
            "Going back is re-pinning the previous tag. There is no database decision to make."
        ),
        DatabaseChange.COMPATIBLE: (
            "Going back is re-pinning the previous tag: the release before this one can read "
            "the database this one leaves behind."
        ),
        DatabaseChange.UNREADABLE: (
            "Going back could not be proven safe from the source. Re-pinning the previous tag "
            "leaves the older release in front of this release's database, and whether that "
            "works is a question somebody has to answer by reading the change."
        ),
        DatabaseChange.BREAKING: (
            "Going back is not only a tag change. The older release cannot use the database "
            "this one leaves behind, so a rollback means restoring the backup you took before "
            "installing, and that is why the line above asks for one."
        ),
    }
)


class Urgency(enum.StrEnum):
    """How soon a client should install this, in the three answers a client can act on."""

    SECURITY = "security"
    IMPORTANT = "important"
    ROUTINE = "routine"


@dataclass(frozen=True)
class Level:
    """One urgency, the argument for it, and the rule about what a client does.

    Both sentences are required, and they are different things. `why` is what makes the level
    the right one for this release; `what_a_client_does` is the instruction, and without it a
    label is a word three people read three ways.
    """

    urgency: Urgency
    why: str
    what_a_client_does: str

    def __post_init__(self) -> None:
        for field, value in (("why", self.why), ("what_a_client_does", self.what_a_client_does)):
            if not value.strip():
                msg = f"{self.urgency.value} has no {field}, so the level is a word and no rule"
                raise ReleaseError(msg)


#: The three levels. Every member of `Urgency` has an entry, and a test holds that: a fourth
#: level added without an argument and a rule is a label a client cannot act on.
URGENCY: Final[Mapping[Urgency, Level]] = MappingProxyType(
    {
        Urgency.SECURITY: Level(
            urgency=Urgency.SECURITY,
            why=(
                "Somebody outside your organisation could reach something they should not, or "
                "somebody inside could reach something their role does not carry. Your "
                "exposure is the time between this being published and your server running "
                "it, and nothing about your install shortens that on its own."
            ),
            what_a_client_does=(
                "Install it today, outside working hours if you have to. Do not wait for the "
                "next maintenance window."
            ),
        ),
        Urgency.IMPORTANT: Level(
            urgency=Urgency.IMPORTANT,
            why=(
                "Something is wrong for everybody running the previous release and nobody "
                "outside can make use of it: a job that stops, a figure that is wrong, a "
                "screen that will not load. It costs you time rather than exposure."
            ),
            what_a_client_does=(
                "Install it at your next maintenance window, and within a week. If you have "
                "no window, make one."
            ),
        ),
        Urgency.ROUTINE: Level(
            urgency=Urgency.ROUTINE,
            why=(
                "An improvement, or a fix to something rare enough that most installs will "
                "never meet it. Nothing about the previous release is unsafe or broken for "
                "everybody."
            ),
            what_a_client_does=(
                "Install it whenever you next install anything. Nothing is waiting on it."
            ),
        ),
    }
)


def _fold(migrations: Mapping[str, str], *, applying: str, reversing: str) -> DatabaseChange:
    """The worst verdict across every migration this release carries, in one direction.

    The worst rather than a count, because a client acts on the hardest thing in the release
    and a release that is nine safe migrations and one narrowing needs the window either way.
    A migration whose body this reader finds nothing in still counts as a change: the release
    carries it, alembic will apply it, and reporting nothing found as no change is the failure
    `brain.ops.sweeps` records for a check that looked at nothing.
    """
    if not migrations:
        return DatabaseChange.NONE
    verdicts = {
        change.verdict
        for text in migrations.values()
        for change in changes_in(text, applying=applying, reversing=reversing)
    }
    if Verdict.BREAKING in verdicts:
        return DatabaseChange.BREAKING
    if Verdict.UNREADABLE in verdicts:
        return DatabaseChange.UNREADABLE
    return DatabaseChange.COMPATIBLE


def database_change(migrations: Mapping[str, str]) -> DatabaseChange:
    """Whether this release changes the database, read from the migrations it carries.

    See `WHETHER_IT_CHANGES_THE_DATABASE_IS_READ_AND_NEVER_TYPED`. The mapping is file name
    against source, which is what a release build has after asking git which migration files
    the tag added.
    """
    return _fold(migrations, applying="upgrade", reversing="downgrade")


def rollback_change(migrations: Mapping[str, str]) -> DatabaseChange:
    """Whether the release before this one can still use the database this one leaves behind.

    The same reader with its two arguments swapped, which is the whole of how the other
    direction is asked; `brain.deployment.compatibility.changes_in` says so in its own
    docstring and `0022` and `0023` are the worked example. A second implementation of it here
    would be a second answer about the direction nobody tests until they need it.
    """
    return _fold(migrations, applying="downgrade", reversing="upgrade")


#: A note that names something only somebody with this repository could act on: a Python file,
#: a source path, or a WBS task id. See `A_NOTE_A_CLIENT_CANNOT_ACT_ON_IS_A_COMMIT_SUBJECT`.
NOT_PLAIN_ENGLISH: Final = re.compile(r"[\w/]+\.py\b|\bsrc/|\btests?/|\bM\d+(?:\.\d+)+\b")


@dataclass(frozen=True)
class ReleaseNotes:
    """What a release says, in the three parts M42.3.8 asks for.

    **There is no field for whether the database changes, and that is the point.** It is a
    property computed from `migrations`, so the only way to publish "no schema change" beside a
    schema change is to publish a release that does not contain the migration it contains.
    """

    tag: str
    #: What changed, one line per thing, for somebody with a server and no source tree.
    what_changed: tuple[str, ...]
    urgency: Urgency
    #: File name against source, for every migration this release adds. Empty is a real
    #: answer and is the common one.
    migrations: Mapping[str, str] = NO_MIGRATIONS

    def __post_init__(self) -> None:
        if not self.tag.strip():
            msg = "a release with no tag names nothing a client could pin"
            raise ReleaseError(msg)
        if not self.what_changed:
            msg = (
                f"{self.tag} states nothing that changed, so a client reading it has a version "
                "number and no way to decide whether to install it"
            )
            raise ReleaseError(msg)
        for line in self.what_changed:
            if not line.strip():
                msg = f"{self.tag} carries an empty note line, which reads as a note"
                raise ReleaseError(msg)
            found = NOT_PLAIN_ENGLISH.search(line)
            if found is not None:
                msg = (
                    f"{self.tag}: {line!r} names {found.group(0)!r}. "
                    f"{A_NOTE_A_CLIENT_CANNOT_ACT_ON_IS_A_COMMIT_SUBJECT}"
                )
                raise ReleaseError(msg)
        if self.database is DatabaseChange.BREAKING and self.urgency is Urgency.ROUTINE:
            msg = (
                f"{self.tag} changes the database in a way the previous release cannot use and "
                f"is called routine. {A_BREAKING_SCHEMA_CHANGE_IS_NEVER_ROUTINE}"
            )
            raise ReleaseError(msg)

    @property
    def database(self) -> DatabaseChange:
        """Whether this release changes the database. Derived, never typed."""
        return database_change(self.migrations)

    @property
    def going_back(self) -> DatabaseChange:
        """Whether the release before this one can still use the database this one leaves."""
        return rollback_change(self.migrations)

    def render(self) -> str:
        """The published notes, as the three questions a client is actually asking.

        Headings rather than a paragraph, because this is read on the day somebody is deciding
        whether to install now or on Friday, and the database line is the one they scroll for.
        """
        level = URGENCY[self.urgency]
        lines = [
            f"# {self.tag}",
            "",
            "## What changed",
            "",
            *(f"- {one}" for one in self.what_changed),
            "",
            "## Does this change your database",
            "",
            WHAT_A_CLIENT_READS[self.database],
            "",
            GOING_BACK[self.going_back],
            "",
            "## How urgent this is",
            "",
            f"**{self.urgency.value.capitalize()}.** {level.why}",
            "",
            f"What to do: {level.what_a_client_does}",
        ]
        return "\n".join(lines) + "\n"


#: `Urgency: security` on a line of its own, which is how a tag message states it.
URGENCY_LINE: Final = re.compile(r"^\s*Urgency:\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)


def notes_from_tag_message(
    tag: str, message: str, migrations: Mapping[str, str] = NO_MIGRATIONS
) -> ReleaseNotes:
    """The notes for one tag, from what the person tagging wrote and what the tag carries.

    **The urgency has to be in the message and there is no default**, for the reason
    `brain.deployment.installer` refuses a default release tag: a default is what makes every
    release routine, including the one that was not. A tag message with no urgency fails the
    release build, which is the only moment anybody is still in a position to fix it.

    Everything else in the message is what changed, one line each, with a leading list marker
    removed so a person can write the message either way.
    """
    found = URGENCY_LINE.search(message)
    if found is None:
        msg = (
            f"the tag message for {tag} carries no `Urgency:` line, so nothing in this release "
            f"says whether a client installs it today or next month. One of "
            f"{[one.value for one in Urgency]}"
        )
        raise ReleaseError(msg)
    word = found.group(1).strip().lower()
    if word not in {one.value for one in Urgency}:
        msg = f"{word!r} is not an urgency; one of {[one.value for one in Urgency]}"
        raise ReleaseError(msg)
    changed = tuple(
        one.strip().lstrip("-*").strip()
        for one in message.splitlines()
        if one.strip() and URGENCY_LINE.match(one) is None
    )
    return ReleaseNotes(tag=tag, what_changed=changed, urgency=Urgency(word), migrations=migrations)


# ------------------------------------------------------------------ what the workflow asks
USAGE: Final = (
    "usage: python -m brain.deployment.release "
    "files | gaps | migrations-path | notes <tag> <message file> [migration file ...]"
)


def main(argv: Sequence[str] | None = None) -> int:
    """The four questions the release workflow asks, so the workflow spells no path itself.

    `migrations-path` looks like an odd thing to expose and it is the point: the workflow asks
    git which migration files a tag added, which needs the directory, and a directory typed
    into a workflow is a second declaration of where migrations live. It is
    `brain.deployment.compatibility.VERSIONS` here and nowhere else.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    command, rest = (args[0], args[1:]) if args else ("", [])
    if command == "files":
        for one in archive_files(REPO):
            print(one)
        return 0
    if command == "gaps":
        findings = archive_gaps()
        for one in findings:
            print(f"  {one}", file=sys.stderr)
        if findings:
            print(f"\n{A_CLIENT_MUST_NEVER_RECEIVE_A_COPY_OF_THIS_REPOSITORY}", file=sys.stderr)
            return 1
        carried = archive_files(REPO)
        print(f"ok: {len(carried)} file(s), {len(INCLUDED)} include(s), {len(EXCLUDED)} refusal(s)")
        return 0
    if command == "migrations-path":
        print(VERSIONS.relative_to(REPO).as_posix())
        return 0
    if command == "notes" and len(rest) >= 2:
        tag, message = rest[0], Path(rest[1]).read_text(encoding="utf-8")
        carried = tuple(one for one in rest[2:] if one.strip())
        migrations = {Path(one).name: Path(one).read_text(encoding="utf-8") for one in carried}
        print(notes_from_tag_message(tag, message, migrations).render(), end="")
        return 0
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
