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

**A release is two artefacts and this module only ever described one of them.** The archive
pins an image by tag, and until 2026-09-16 no workflow here published an image at a release
tag: the deploy pipeline is triggered by CI completing on `main` and a tag push runs neither
CI nor the deploy. So the declaration below could be perfect and the install would still stop
at the pull. `THE_IMAGE_A_RELEASE_PINS_IS_PROMOTED_AND_NEVER_REBUILT` and
`A_TAG_WITH_NO_IMAGE_BEHIND_IT_IS_A_COMMIT_THAT_NEVER_PASSED` are the two rules the release
workflow's image job holds, and `image-repository` is what it asks this module so that the
name is not written into a fifth file. `ops/RELEASE.md` is the procedure for the tag itself.

**The file list is an allowlist and never a set of `tar --exclude` flags.** An exclusion list
is written against the tree that exists on the day somebody writes it, and every file added
afterwards ships by default: a script added under `ops/` for this deployment's own VPS would
reach a client's server with nobody having decided it should. The include list names what a
client needs, everything else is out by construction, and the exclusions are the net under a
widened include rather than the mechanism. `docker-compose.staging.yml` is the worked example:
it is out of the archive because no profile composes it, not because a rule names it.

**The include list is derived from the install, not chosen.** The environment template is
there because the plan copies it; each compose file is there because `files_for` names it for
some profile; the four `ops/...` settings are there because the plan copies them into the
install's settings directory, which four services then mount by absolute path.

Until 2026-09-10 those four were derived the other way, from the compose files bind-mounting
`./ops/...`, and item 43 of `docs/needs-rupash.md` closed that shape: a relative source is
resolved against the directory the compose file was read from, and a deployment that stores
its own copy resolves it to nothing and starts the container anyway with no error at all. The
paths are the same four and the reason the archive owes them has moved from the compose files
to the plan, which is where `paths_the_install_reads` already looks. `mounts_in` is kept
because the shape it refuses is one edit away from coming back.

`archive_gaps` computes that set from the plan and the compose documents and reports anything
the archive would not carry, because **a mismatch between the archive and the install plan is a
failure a client meets on their own server and nobody here ever sees**.

**Whether a release changes the database is read out of the release, never typed into it.**
A person typing "no schema change" on a release that has one is the exact failure the field
exists to prevent, so there is no field to type: `ReleaseNotes.database` folds
`brain.deployment.compatibility.changes_in` over the migrations the release carries, and the
same reader with its two arguments swapped answers whether going back is safe. See
`WHETHER_IT_CHANGES_THE_DATABASE_IS_READ_AND_NEVER_TYPED`.

**Moving an install between releases is the other half, and the half nothing recorded.**
`brain.deployment.installer.PLAN` wrote the tag it unpacked into `/opt/brain/RELEASE` and,
until 2026-09-15, nothing that selected an image, so a fresh install pinned to a tag ran
containers that resolved `${APP_IMAGE:-...:latest}` and the two facts disagreed from the first
day. The compose files now require the variable and the install writes it with the step these
scripts take by name. The second is worse for a rollback: `RELEASE` is the only version fact an
install holds, an update overwrites it, and nothing anywhere records what it overwrote. So
`update_plan` **copies the marker before it writes over it**, which is the whole of what makes
`rollback_plan` possible, and `rollback_plan` refuses when that copy is missing rather than
guessing. See `RECORDING_THE_PREVIOUS_RELEASE_AFTER_THE_NEW_ONE_RECORDS_THE_NEW_ONE` and
`A_ROLLBACK_THAT_GUESSES_IS_WORSE_THAN_ONE_THAT_REFUSES`.

**A rollback re-pins code and leaves the schema.** Migrations run forward at startup under an
advisory lock and nothing runs a downgrade against a client's data, so going back is safe
exactly when the newer migrations were compatible for the older code, which
`ReleaseNotes.going_back` already answers at release time. On the server the answerable
question is narrower and worth more: whether the database sits at a revision the release being
gone back to does not carry. `rollback_plan` asks the database for its applied revision and
looks for it in the target archive, and refuses loudly when it is not there rather than
recreating old code in front of a newer schema.

Rejected: a second reader of the rollback direction. `ReleaseNotes.going_back` is
`changes_in` with its two arguments swapped and it is the answer at release time; the plan's
check is a different question asked of a running database, not a second opinion on the same
one.

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

**The two tunnel overlays are carried although no profile composes them**, which is the one
exception to deriving the includes from `files_for`, and it is derived too: from
`brain.ops.tunnel.overlays_for`. The update and rollback scripts compose them onto an install
whose environment file holds the tunnel token, so a release without them would be an update
that stops on exactly the installs that chose the tunnel. See `_tunnel_rules`.

**The vault overlay is carried and composed the same way, for the same reason.**
`docker-compose.vault.yml` hands the application the vault's address and token and joins it to
the vault's network, and no profile composes it. The scripts compose it onto an install whose
environment file names a vault address, so an update does not recreate the application without
the vault and quietly stop loading every provider key the console put there. See
`brain.deployment.app_environment.AN_ADDRESS_IN_THE_ENVIRONMENT_FILE_RECORDS_THE_VAULT`.

Task ids: M42.3.6, M42.3.8, M30.2.7, M30.1.3
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

from brain.deployment.app_environment import (
    AN_ADDRESS_IN_THE_ENVIRONMENT_FILE_RECORDS_THE_VAULT,
    VAULT_OVERLAY,
    WORKER_VAULT_OVERLAY,
)
from brain.deployment.compatibility import VERSIONS, Verdict, changes_in
from brain.deployment.installer import (
    IMAGE_VARIABLE,
    INSTALL_ENV_FILE,
    INSTALL_HOME,
    PLAN,
    PRODUCT_IMAGE,
    THE_IMAGE_VARIABLE,
    Step,
    compose_files_argument,
    step_named,
)
from brain.deployment.requirements import files_for
from brain.deployment.vault_setup import (
    WORKER_FILES_VARIABLE,
    vault_choice_lines,
    worker_files_argument,
)
from brain.ops.compose import ComposeDoc, ComposeFiles
from brain.ops.independence import NOT_OF_THIS_REPOSITORY
from brain.ops.tunnel import (
    OVERLAY,
    THE_ENVIRONMENT_FILE_RECORDS_THE_CHOICE,
    overlays_for,
    token_variable,
)
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

#: Why an update writes down what it is replacing before it replaces it.
RECORDING_THE_PREVIOUS_RELEASE_AFTER_THE_NEW_ONE_RECORDS_THE_NEW_ONE: Final = (
    "An install holds one version fact, the tag in its marker file, and an update overwrites "
    "it. So a rollback has nothing to go back to unless the old value was copied first, and "
    "copied before the overwrite rather than after. The other order fails silently and in the "
    "worst way: the copy exists, it holds a real tag, and it holds the tag that was just "
    "installed, so the rollback re-pins the release it was meant to be leaving and everything "
    "about it reports success."
)

#: Why the rollback refuses rather than working the previous release out for itself.
A_ROLLBACK_THAT_GUESSES_IS_WORSE_THAN_ONE_THAT_REFUSES: Final = (
    "What a rollback could guess from is the tag it is already on, whatever the release host "
    "offers today, or whatever else is in the local image store, and every one of those is a "
    "guess about a server nobody here can see. It is run at the worst moment of somebody's "
    "week, so it either goes back to the release this install was actually on or it stops and "
    "names the file that is missing. There is no third answer worth having."
)

#: Why `latest` is refused as the target of an update.
LATEST_IS_AN_UNPIN_WEARING_AN_UPDATES_CLOTHES: Final = (
    "A client who updates to latest has not moved to a release, they have stopped being "
    "pinned: the next pull changes the running version with nobody having decided anything, "
    "and the marker beside it goes on naming a tag that is no longer a fact. It is the same "
    "refusal brain.deployment.installer makes of a default release tag, at the other end of "
    "the same install."
)

#: Why a rollback is a code change, and what is checkable about that on a server.
A_ROLLBACK_RE_PINS_THE_CODE_AND_LEAVES_THE_SCHEMA: Final = (
    "Migrations run forward at startup under an advisory lock and nothing in this product "
    "runs a downgrade against a client's data, so going back re-pins the code and leaves the "
    "schema where the newer release left it. That is safe exactly when the newer migrations "
    "were compatible for the older code, which ReleaseNotes.going_back answers at release "
    "time and nothing on a server can re-derive. What a server can answer is narrower and is "
    "worth more at that moment: if the database is at a revision the target release does not "
    "carry, the rollback is old code in front of a newer schema and it says so rather than "
    "recreating the containers and finding out from the logs."
)

#: Why the release names an image it did not build, and what a rebuild would cost.
THE_IMAGE_A_RELEASE_PINS_IS_PROMOTED_AND_NEVER_REBUILT: Final = (
    "The install writes APP_IMAGE as the product repository at the release tag, so a tag with "
    "no image at it is an install that stops at the pull with the machine already half "
    "prepared. The image that carries that tag is the one the deploy pipeline already built "
    "for the commit the tag names, retagged in the registry, and it is never a second build "
    "of the same source. A second build produces a second digest from the same commit, and "
    "then the artefact a client runs is one no test ever ran against and no signature covers: "
    "cosign signs a digest, so an image rebuilt after signing is an unsigned image wearing a "
    "release tag. Retagging moves a name onto a digest and leaves the digest alone, which is "
    "why the signature made at build time still verifies against the release."
)

#: Why a release refuses when the commit it names has no published image.
A_TAG_WITH_NO_IMAGE_BEHIND_IT_IS_A_COMMIT_THAT_NEVER_PASSED: Final = (
    "Only the deploy pipeline publishes an image, and only a commit whose CI went green "
    "reaches it, so the absence of an image at a commit is the statement that the commit was "
    "never shipped. A release built anyway would hand a client an archive pinning an image "
    "that does not exist, and the failure would land on their server rather than in this "
    "repository. Refusing here also means the gate CI holds over production is the same gate "
    "a client's install is behind, with nothing restating it."
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


def _tunnel_rules(profiles: Sequence[str] = PROFILES) -> tuple[Rule, ...]:
    """One include per tunnel overlay a profile would compose, read off `overlays_for`.

    No profile composes these by default, so `_compose_rules` leaves them out, and until
    2026-09-15 that was the whole of it: an install from a release had no tunnel file, and the
    network guide told a person to copy it across by hand and to start it again after every
    update. Derived rather than listed for the reason the compose rules are: a third overlay
    that `overlays_for` starts naming is in the archive the same day.
    """
    names = sorted({name for profile in profiles for name in overlays_for(files_for(profile))})
    return tuple(
        Rule(
            name,
            "a tunnel overlay the update and rollback scripts compose onto a profile whose "
            "environment file holds the tunnel token, so a release that did not carry it is "
            "an update that stops on the one install that chose the tunnel",
        )
        for name in names
    )


def _vault_rules() -> tuple[Rule, ...]:
    """The vault overlays, which no profile names and the install, update and rollback compose."""
    return (
        Rule(
            VAULT_OVERLAY,
            "the overlay the installer, the update and the rollback compose onto an install whose "
            "environment file names a vault address, so a release that did not carry it is an "
            "update that stops on every install that runs the vault. "
            + AN_ADDRESS_IN_THE_ENVIRONMENT_FILE_RECORDS_THE_VAULT,
        ),
        Rule(
            WORKER_VAULT_OVERLAY,
            "the overlay handing the general worker its own vault token, composed where the "
            "environment file holds one, so a release that did not carry it is an update that "
            "stops on every standard and full install that runs the vault",
        ),
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
    *_tunnel_rules(),
    *_vault_rules(),
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
        "ops/install",
        "the installer this release was installed by, carried for the reason ops/update is: an "
        "install is safe to run twice and re-running it after an update is a repair somebody "
        "reaches for at a bad moment, and the script that does it has to be the one belonging "
        "to the release on the server rather than whichever one is newest. It is also published "
        "beside the archive, because running it is what fetches the archive, so this copy is "
        "the record of what was run and never the way anybody gets it",
    ),
    Rule(
        "ops/update",
        "the update and rollback scripts, which are the only two things on a client's server "
        "that write the image variable, so an install that does not carry them is one whose "
        "marker and running image can only ever drift further apart. They are carried by the "
        "release you are on rather than fetched at the moment you need them, because the "
        "moment you need the rollback is the moment you are least able to fetch anything",
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
        "the eleven pages somebody reads standing in front of the server. Everything else under "
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
#: `__pycache__`, `node_modules` and `dist` are deliberately not here. They are not files of
#: this repository at all, so they are skipped while walking rather than refused afterwards,
#: from the one set `brain.ops.independence.NOT_OF_THIS_REPOSITORY` holds for every walker.
#: Refusing them instead would make the deployment check red on every tree that has built the
#: automation piece, and `ops/automation` is carried.
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
            if one.is_file() and not NOT_OF_THIS_REPOSITORY.intersection(one.parts)
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

#: The fourth way, and the one that cannot be a destination pattern: `mkdir` creates every
#: operand it is given, however many there are. See `paths_the_install_reads`.
MAKES_A_DIRECTORY: Final = re.compile(r"mkdir\b")


def paths_the_install_reads(plan: Sequence[Step] = PLAN) -> tuple[str, ...]:
    """Every path under the install directory the plan reads and does not write itself.

    Read out of the plan rather than listed, because the plan is where the answer changes: a
    step that starts reading a second file is a second file the archive owes it, and a list
    here would go on naming one. The written set is computed the same way and from the same
    text, so the tarball the install downloads and the environment file it creates are not
    mistaken for things the archive should have carried.

    **A `mkdir` is read line by line rather than by a pattern, and it has to be.** Every other
    way the plan writes has one destination in a fixed position, so a regular expression can
    name it: after the redirect, after `-o`, second argument of `cp`. `mkdir` takes any number
    of operands and creates all of them, and the settings step passes it three, so a pattern
    capturing "the path after the command" would have counted two of the three as files the
    archive owes the install. That is the affordable direction again: a release refusing to
    build over a directory it was never supposed to carry.
    """
    read: set[str] = set()
    written: set[str] = set()
    for step in plan:
        for fragment in (step.run, step.already_done):
            read.update(UNDER_THE_INSTALL_HOME.findall(fragment))
            for pattern in WRITTEN_BY_THE_INSTALL:
                written.update(pattern.findall(fragment))
            for line in fragment.splitlines():
                if MAKES_A_DIRECTORY.match(line.strip()):
                    written.update(UNDER_THE_INSTALL_HOME.findall(line))
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


def tunnel_token_variable(tree: Path = REPO) -> str:
    """The variable the tunnel overlay requires, read off the overlay the release carries.

    Read rather than spelled here, because the update script greps the environment file for
    this name and the overlay refuses to start without it: two spellings would agree until the
    day somebody renamed one, and the script would then decide every install had no tunnel.
    Refuses rather than defaulting, for the reason `release_marker` does.
    """
    import yaml

    parsed = yaml.safe_load((tree / OVERLAY).read_text(encoding="utf-8"))
    variable = token_variable(parsed if isinstance(parsed, dict) else {})
    if variable is None:
        msg = (
            f"{OVERLAY} requires no token variable, so nothing in an install's environment file "
            f"records the tunnel. {THE_ENVIRONMENT_FILE_RECORDS_THE_CHOICE}"
        )
        raise ReleaseError(msg)
    return variable


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
        # A directory the install walks, the vault's policies, is carried when a file under it is.
        if not (one.endswith("/") and any(path.startswith(one) for path in held))
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


# --------------------------------------------------- moving an install between two releases
#: The file an update copies the marker into before it writes the new tag over it. Beside the
#: marker rather than inside the environment file, because it is one install's own history and
#: nothing reads it but the rollback.
PREVIOUS_MARKER: Final = "PREVIOUS_RELEASE"

#: The tag that is not one. See `LATEST_IS_AN_UNPIN_WEARING_AN_UPDATES_CLOTHES`.
NOT_A_RELEASE_TAG: Final = "latest"

#: The one question the rollback asks of a running database.
#:
#: Written whole rather than composed from a table name, because there is one form of it and
#: assembling it would be a second thing to get wrong. The table is unqualified in alembic's own
#: configuration, which puts it in the connection's default schema, and `migrations/env.py`
#: names no other one; the test asserts that second half against the file rather than against
#: this line.
APPLIED_REVISION_QUERY: Final = "select version_num from public.alembic_version"

#: How the install records the tag it unpacked: a printf of the release variable straight into
#: a file under the install directory. Read out of the plan rather than spelled a second time,
#: because that marker is the whole of what an update has to go on, and a second spelling would
#: be right until the day somebody renamed the file in one place.
RECORDS_THE_TAG: Final = re.compile(
    r'printf\s+"%s\\n"\s+"\$(\w+)"\s*>\s*"' + re.escape(INSTALL_HOME) + r'/(\w+)"'
)


def release_marker(plan: Sequence[Step] = PLAN) -> tuple[str, str]:
    """The variable the install pins and the file it writes it into, as the one pair they are.

    Both halves come off one line of the plan and are returned together because they are one
    fact: the marker is only meaningful as the value of that variable, and a caller that had
    to fetch them separately could pair a renamed file with the old variable and render a
    script that pins nothing.

    Refuses rather than defaulting, for the reason `brain.deployment.installer.step_named`
    refuses: a caller handed a default writes a script that reads a file no install has, which
    fails on somebody else's server with a message about a missing file.
    """
    for step in plan:
        found = RECORDS_THE_TAG.search(step.run)
        if found is not None:
            return found.group(1), found.group(2)
    msg = (
        f"no step of the install writes a release tag into a file under {INSTALL_HOME}, so "
        "nothing on a server says which release it is on and an update has nothing to record. "
        f"{A_ROLLBACK_THAT_GUESSES_IS_WORSE_THAN_ONE_THAT_REFUSES}"
    )
    raise ReleaseError(msg)


def image_repository(files: ComposeFiles) -> str:
    """The published image an install pins a tag of, once the compose files are shown to read it.

    **The name is `brain.deployment.installer.PRODUCT_IMAGE`, and it was read off a default
    until 2026-09-15.** Needs Rupash item 51 made the variable required, and `${APP_IMAGE:?...}`
    names no image, so a reader of defaults would have had nothing to read. What the compose
    files can still answer is whether anything reads the variable these scripts write, and
    whether a default left behind names a different image from the one they pin.

    Two refusals, and they fail for different people. No reference at all means these scripts
    would write a variable nothing reads, which is a pin that pins nothing and reports success.
    A default naming another repository means a script that pins one image while an install
    that loses the variable starts another, so it runs two builds of one product, which is the
    failure `release_pinning_gaps` describes arriving through the update.
    """
    readers = 0
    for name in sorted(files):
        for body in _services_in(files[name]).values():
            if not isinstance(body, Mapping):
                continue
            match = IMAGE_VARIABLE.match(str(body.get("image", "")))
            if match is None or match.group(1) != THE_IMAGE_VARIABLE:
                continue
            readers += 1
            default = (match.group(3) or "") if match.group(2) == "-" else ""
            named = default.rsplit(":", 1)[0] if ":" in default else default
            if named and named != PRODUCT_IMAGE:
                msg = (
                    f"{name} gives {THE_IMAGE_VARIABLE} a default naming {named!r} while these "
                    f"scripts pin {PRODUCT_IMAGE!r}, so an install that loses the variable starts "
                    "a different image from the one it was pinned to and runs two builds of one "
                    "product"
                )
                raise ReleaseError(msg)
    if not readers:
        msg = (
            f"no service in these compose files chooses an image through {THE_IMAGE_VARIABLE}, "
            "so there is no image reference for an update to pin and writing "
            f"{THE_IMAGE_VARIABLE} would put a variable nothing reads into the environment file"
        )
        raise ReleaseError(msg)
    return PRODUCT_IMAGE


def refusal(condition: str, message: str) -> str:
    """One guard of these plans, as the shell it is: run the test, or fail with the reason.

    **The message is checked for the three characters a double-quoted shell string acts on
    rather than prints.** This is the one place in this repository where prose is compiled into
    shell, and a `$` in a refusal expands to nothing at the exact moment somebody most needs to
    read it: the operator sees a sentence with a hole in it and no indication there was ever a
    word there. A backtick is worse than a hole, because it runs.
    """
    for char in ('"', "$", "`"):
        if char in message:
            msg = (
                f"{message!r} carries {char!r}, which the shell acts on rather than prints, so "
                "the refusal reaches the person reading it with a word missing or a command run"
            )
            raise ReleaseError(msg)
    return f'{condition} || fail "{message}"'


def _an_install_is_here(marker: str) -> Step:
    """The step both plans open with: this directory holds an install, and it holds its file.

    Two tests rather than one, and the second is not decoration. The step that pins the image
    rewrites the environment file, and an absent one would be created holding the pin and
    nothing else: every credential the install minted gone, replaced by one line, with the
    script reporting that it had pinned the release.
    """
    return Step(
        name="check this directory holds an install",
        run=(
            refusal(
                f'test -s "{INSTALL_HOME}/{marker}"',
                "there is no release marker here, so this directory is not an install this "
                "script can move. Install first",
            )
            + "\n"
            + refusal(
                f'test -s "{INSTALL_HOME}/{INSTALL_ENV_FILE}"',
                "there is no environment file here, and the pin is written into it. Install "
                "first, or put the file back from your own copy of it",
            )
        ),
        why=(
            "everything below reads or rewrites one of these two files, and both failures are "
            "quiet without this: a missing marker is a rollback with nothing to record, and a "
            "missing environment file is one the pin step would create holding the pin alone"
        ),
        on_failure=(
            f"nothing has been changed. Check {INSTALL_HOME} is the directory the install was "
            "made in, and that you are running this as a user that can read it"
        ),
        changes=False,
    )


def _onto_this_release(variable: str, plan: Sequence[Step] = PLAN) -> tuple[Step, ...]:
    """The five steps that put an install on the release it has just unpacked.

    One tuple rather than two copies, because an update and a rollback do exactly the same
    thing from here and differ only in how they decided which tag.

    **Three of the five are the installer's own, taken by name.** Pinning the image is one of
    them since 2026-09-15, because the install has to write the variable too now that the
    compose files refuse without it, and two copies of a pin are two ways to pin. The settings
    step is first because a release that adds a fifth file four containers might mount would
    otherwise reach a server with nobody creating it, and a bind mount whose source does not
    exist is the one failure that starts the container anyway: its own guard is per file, so
    an allowlist a client has edited is not touched. The readiness step is last because
    readiness is what tells a person the swap worked, and a second copy of that check here
    would be a second answer to the only question either script is run to have answered.
    """
    pinned = f'"$BRAIN_REPOSITORY:${variable}"'
    return (
        step_named("create the settings the containers mount", plan),
        step_named("pin the image this install runs", plan),
        Step(
            name="pull the image this release publishes",
            run="docker compose $BRAIN_COMPOSE_FILES pull --quiet",
            why=(
                "pulled before anything is recreated, so a registry that cannot be reached "
                "fails while the containers of the release you are on are still serving"
            ),
            on_failure=(
                "check this server can reach the image registry, then run this again. The pin "
                "is already written, so repeating this costs nothing"
            ),
            changes=True,
            # Keyed on the pinned image rather than on any image being present, which is the
            # guard the install uses and is exactly wrong here: an update runs against a server
            # that already has images, so that test is true before the pull and the one step
            # the script exists for would be skipped.
            already_done=f"docker image inspect {pinned} >/dev/null 2>&1",
        ),
        Step(
            name="recreate the containers on the pinned image",
            run="docker compose $BRAIN_COMPOSE_FILES up -d",
            why=(
                "compose recreates the containers whose image changed and leaves the rest, and "
                "the application runs its own migrations at startup under an advisory lock "
                "before readiness passes"
            ),
            on_failure=(
                "read `docker compose $BRAIN_COMPOSE_FILES ps` for the container that is not "
                "running, then its logs. Bringing the stack up again is safe"
            ),
            changes=True,
            # Named no service, because more than one service of a profile runs this image and
            # naming one would report success while another stayed behind. Both halves are
            # required: something is running the pin, and nothing is running a different tag of
            # it, so a stack that is entirely down does not count as already done.
            already_done=(f'running_images | grep -qxF {pinned} && test -z "$(off_the_pin)"'),
        ),
        step_named("wait for the application to report ready", plan),
    )


def update_plan(plan: Sequence[Step] = PLAN) -> tuple[Step, ...]:
    """Moving an install forward to a named release, in the order it has to happen.

    **The third step is the one this plan is shaped around.** It copies the marker before the
    fourth step writes over it, so an update that fails anywhere after it still leaves a
    rollback something to go back to, and an update that fails before it has changed nothing.
    See `RECORDING_THE_PREVIOUS_RELEASE_AFTER_THE_NEW_ONE_RECORDS_THE_NEW_ONE`.

    Its guard is the comparison that makes a second run safe rather than destructive. Run
    twice, an unguarded copy would record the release that was just installed as the one to go
    back to; guarded on the marker already naming the target, the second run skips it and the
    real previous release survives.

    Five of the steps are the installer's own, taken by name. Fetching and unpacking one archive
    of one tag is the same act whether the directory is empty or holds the release before it,
    and the failure of a second copy of it is that only one of the two would be corrected.
    """
    variable, marker = release_marker(plan)
    return (
        Step(
            name="refuse a tag that pins nothing",
            run=refusal(
                f'test "${variable}" != "{NOT_A_RELEASE_TAG}"',
                "latest is not a release tag: updating to it stops this install being pinned, "
                "so the next pull changes the version with nobody deciding anything. Name the "
                "release you mean to install",
            ),
            why=LATEST_IS_AN_UNPIN_WEARING_AN_UPDATES_CLOTHES,
            on_failure=(
                "run this again with the tag of the release you mean to install. Nothing has "
                "been read or written yet"
            ),
            changes=False,
        ),
        _an_install_is_here(marker),
        Step(
            name="record the release this update replaces",
            run=f'cp "{INSTALL_HOME}/{marker}" "{INSTALL_HOME}/{PREVIOUS_MARKER}"',
            why=RECORDING_THE_PREVIOUS_RELEASE_AFTER_THE_NEW_ONE_RECORDS_THE_NEW_ONE,
            on_failure=(
                "do not continue: this copy is the only thing a rollback reads, and every step "
                f"after it changes what is running. Check {INSTALL_HOME} is writable and run "
                "this again"
            ),
            changes=True,
            already_done=f'test "$(cat "{INSTALL_HOME}/{marker}")" = "${variable}"',
        ),
        step_named("download and unpack the release", plan),
        step_named("change into the release directory", plan),
        *_onto_this_release(variable, plan),
    )


def rollback_plan(plan: Sequence[Step] = PLAN) -> tuple[Step, ...]:
    """Moving an install back to the release the last update recorded, or refusing to.

    **It takes no tag, and that is the design rather than a convenience.** The release to go
    back to is read out of the file the update wrote, so the script cannot be pointed at a
    release this install was never on, and when that file is missing it stops. See
    `A_ROLLBACK_THAT_GUESSES_IS_WORSE_THAN_ONE_THAT_REFUSES`.

    **The archive is fetched, read, and only then unpacked**, which is why this does not reuse
    the installer's download step the way `update_plan` does. The check that matters runs
    against the migrations the target release carries, and it has to run while the install is
    still whole: unpacked first, a refusal would leave the older release's files on disk and
    its marker claiming a tag the containers are not running, which is a worse state than the
    one being refused. See `A_ROLLBACK_RE_PINS_THE_CODE_AND_LEAVES_THE_SCHEMA`.

    The last step removes the record it acted on. A rollback goes back one release: leaving the
    record would make a second run re-pin the release this one just left, so two scripts would
    oscillate between two tags, each reporting success. Removed, the second run refuses and
    asks for a decision, which is what going back two releases actually needs.
    """
    variable, marker = release_marker(plan)
    archive = f"{INSTALL_HOME}/going-back-${variable}.tar.gz"
    return (
        _an_install_is_here(marker),
        Step(
            name="refuse without a record of the release being left",
            run=refusal(
                f'test -s "{INSTALL_HOME}/{PREVIOUS_MARKER}"',
                "nothing here records the release this install was on before its last update, "
                "so there is no release to go back to. Update once with the update script, "
                "which writes it, or install the tag you want by name",
            ),
            why=A_ROLLBACK_THAT_GUESSES_IS_WORSE_THAN_ONE_THAT_REFUSES,
            on_failure=(
                "nothing has been changed. An install that has never been updated by the "
                "update script has no record, and the release you want has to be named"
            ),
            changes=False,
        ),
        Step(
            name="read the release this rollback goes back to",
            run=(
                f'{variable}="$(cat "{INSTALL_HOME}/{PREVIOUS_MARKER}")"\n'
                f'say "going back to ${variable}"\n'
                + refusal(
                    f'test "${variable}" != "{NOT_A_RELEASE_TAG}"',
                    "the release recorded here is latest, which is not a release: going back "
                    "to it would leave this install unpinned. Name the tag you want instead",
                )
                + "\n"
                + refusal(
                    'test -n "${BRAIN_RELEASE_URL:-}"',
                    "set BRAIN_RELEASE_URL to the archive of the release printed above and "
                    "run this again",
                )
            ),
            why=(
                "the tag is printed before it is needed, because the archive for it is what "
                "the operator has to supply and they cannot supply it until they know which "
                "release this is going back to"
            ),
            on_failure=(
                "nothing has been changed. The tag is in the file this step read, and the "
                "archive for it is the one the release was published with"
            ),
            changes=False,
        ),
        Step(
            name="fetch the archive of that release",
            run=(
                f'curl -fsSL "$BRAIN_RELEASE_URL" -o "{archive}.part"\n'
                f'mv "{archive}.part" "{archive}"'
            ),
            why=(
                "downloaded beside itself and moved into place, so the guard on this step "
                "cannot be satisfied by a transfer that stopped halfway. Named for the tag, so "
                "a download for one release is never mistaken for another's"
            ),
            on_failure=(
                "check this server can reach the release host and that the archive for that "
                "tag exists. Nothing about the running install has changed"
            ),
            changes=True,
            already_done=f'test -s "{archive}"',
        ),
        Step(
            name="check the database is not past that release",
            run=(
                'applied="$(docker compose $BRAIN_COMPOSE_FILES exec -T db '
                f'psql -qtAX -U brain -d brain -c "{APPLIED_REVISION_QUERY}")"\n'
                + refusal(
                    'test -n "$applied"',
                    "the database did not answer with the migration revision it is on, so "
                    "nothing here can say whether it is past the release you are going back "
                    "to. Check the database container is running",
                )
                + "\n"
                + refusal(
                    f'tar -xzOf "{archive}" --wildcards "*/migrations/versions/*.py" '
                    '| grep -qxF "revision = \\"$applied\\""',
                    "this database has been migrated past what the release you are going back "
                    "to carries, so re-pinning it would put older code in front of a newer "
                    "schema. Nothing has been changed. Going back from here means the backup "
                    "taken before the update that moved it",
                )
            ),
            why=A_ROLLBACK_RE_PINS_THE_CODE_AND_LEAVES_THE_SCHEMA,
            on_failure=(
                "nothing has been changed and nothing has been recreated. Read the sentence "
                "the step printed: it is either a database that cannot be reached or a schema "
                "the older release does not know about, and they need different answers"
            ),
            changes=False,
        ),
        Step(
            name="unpack it and record which release this install is on",
            run=(
                f'tar -xzf "{archive}" -C "{INSTALL_HOME}" --strip-components=1\n'
                f'printf "%s\\n" "${variable}" > "{INSTALL_HOME}/{marker}"'
            ),
            why=(
                "the marker is written in the same step as the unpack, so the tag a server "
                "reports is the tag whose files are in the directory it reports it from"
            ),
            on_failure=(
                f"the archive is still at {archive}. Unpack it by hand into {INSTALL_HOME} "
                "with one directory stripped, then run this again"
            ),
            changes=True,
            already_done=f'test "$(cat "{INSTALL_HOME}/{marker}")" = "${variable}"',
        ),
        step_named("change into the release directory", plan),
        *_onto_this_release(variable, plan),
        Step(
            name="forget the release this rollback left",
            run=f'rm -f "{INSTALL_HOME}/{PREVIOUS_MARKER}"',
            why=(
                "a rollback goes back one release. Left in place, the record would send a "
                "second run back to the release this one just left, so the two scripts "
                "oscillate between two tags with each run reporting success"
            ),
            on_failure=(
                "the install is already back on the release it was asked for; only the record "
                f"is left. Remove {INSTALL_HOME}/{PREVIOUS_MARKER} by hand"
            ),
            changes=True,
            already_done=f'test ! -f "{INSTALL_HOME}/{PREVIOUS_MARKER}"',
        ),
    )


def _profile_case(profiles: Sequence[str] = PROFILES) -> tuple[str, ...]:
    """The compose file list per profile, as the shell chooses between them.

    **These scripts take the profile and the installer bakes it in**, because the two are run
    by people who know different things. Whoever runs the installer is choosing the profile at
    that moment; whoever runs an update is standing in front of an install whose profile was
    chosen months ago, and nothing the install leaves on disk records which one it was. So the
    choice is an argument with the three answers spelled out, and a fourth profile appears here
    the day it is declared rather than the day somebody remembers.
    """
    arms = [
        f'  {profile}) BRAIN_COMPOSE_FILES="{compose_files_argument(profile)}"; '
        f'BRAIN_TUNNEL_FILES="{_overlays_argument(profile)}"; '
        f'{WORKER_FILES_VARIABLE}="{worker_files_argument(profile, home=INSTALL_HOME)}" ;;'
        for profile in profiles
    ]
    names = " ".join(profiles)
    return (
        'case "$BRAIN_PROFILE" in',
        *arms,
        f'  *) fail "unknown profile; one of: {names}" ;;',
        "esac",
    )


def _overlays_argument(profile: str) -> str:
    """The tunnel's `-f` flags for this profile, absolute for the reason the profile's are."""
    return " ".join(f"-f {INSTALL_HOME}/{name}" for name in overlays_for(files_for(profile)))


def _tunnel_choice(variable: str) -> str:
    """The one line that composes the tunnel in, when this install's environment file chose it.

    See `THE_ENVIRONMENT_FILE_RECORDS_THE_CHOICE`. A value is required
    after the `=`, so a line left empty from a template is not a choice; the overlay would
    refuse that token anyway, and composing it in would stop an update over a tunnel nobody
    set up. Read before the step that checks the file exists, so a missing file reads as no
    tunnel here and is refused by name there.
    """
    return (
        f'if grep -q "^{variable}=." "{INSTALL_HOME}/{INSTALL_ENV_FILE}" 2>/dev/null; then '
        'BRAIN_COMPOSE_FILES="$BRAIN_COMPOSE_FILES $BRAIN_TUNNEL_FILES"; '
        'say "The environment file holds the tunnel token, so the tunnel is composed in."; fi'
    )


def _vault_choice() -> tuple[str, ...]:
    """The lines that compose the vault overlays in, when the environment file names them.

    See `AN_ADDRESS_IN_THE_ENVIRONMENT_FILE_RECORDS_THE_VAULT`. The lines are
    `brain.deployment.vault_setup.vault_choice_lines`, the installer's own, so an install, an
    update and a rollback compose a vault in one way. After the tunnel's line, so the overlays
    come after the profile's own files in both scripts in one order.
    """
    return vault_choice_lines(INSTALL_HOME, INSTALL_ENV_FILE)


def _helpers() -> tuple[str, ...]:
    """The shell functions both scripts use, including the two that read what is running."""
    return (
        'say() { printf "%s\\n" "$1"; }',
        'fail() { printf "%s\\n" "$1" >&2; exit 1; }',
        "running_images() {",
        "  docker compose $BRAIN_COMPOSE_FILES ps --quiet | while read -r one; do",
        '    docker inspect --format "{{.Config.Image}}" "$one"',
        "  done",
        "}",
        "off_the_pin() {",
        '  running_images | grep -F "$BRAIN_REPOSITORY:" '
        '| grep -vxF "$BRAIN_REPOSITORY:$BRAIN_RELEASE"',
        "}",
    )


def _render(generator: str, preamble: Sequence[str], steps: Sequence[Step], done: str) -> str:
    """One plan as the shell it is, numbered against its own length.

    The same shape as `brain.deployment.installer.render` and deliberately not shared with it.
    The loop is nine lines; what differs is everything around it, because that renderer bakes
    one profile's memory and service figures into a script for a machine that has nothing on it
    yet, and these two are run against an install that already exists. Sharing it would mean a
    parameterised preamble, which is more machinery than the nine lines it saves.
    """
    total = len(steps)
    lines = [
        "#!/bin/sh",
        f"# Generated by brain.deployment.release.{generator}. Do not edit: edit the plan and",
        "# regenerate, or the script and the plan disagree and the plan is the tested one.",
        "set -eu",
        "",
        *preamble,
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
    lines.append(f'say "{done}"')
    return "\n".join(lines) + "\n"


def render_update(
    *,
    repository: str,
    tunnel_token: str,
    plan: Sequence[Step] = PLAN,
    profiles: Sequence[str] = PROFILES,
) -> str:
    """The update script, as the shell it is.

    `repository` is passed rather than read, for the reason `installer.render` takes its
    figures: rendering a script is not a good enough excuse to open a file, and a caller who
    has the compose documents has it from `image_repository`. `tunnel_token` is passed for the
    same reason, from `tunnel_token_variable`.
    """
    variable, _ = release_marker(plan)
    usage = "usage: update.sh <profile> <release tag>"
    preamble = [
        f'BRAIN_PROFILE="${{1:?{usage}}}"',
        f'{variable}="${{2:?{usage}}}"',
        f'BRAIN_HOME="{INSTALL_HOME}"',
        f'BRAIN_REPOSITORY="{repository}"',
        'BRAIN_RELEASE_URL="${BRAIN_RELEASE_URL:?set BRAIN_RELEASE_URL to the release archive}"',
        "",
        *_helpers(),
        "",
        *_profile_case(profiles),
        _tunnel_choice(tunnel_token),
        *_vault_choice(),
        "",
        f'say "Updating the $BRAIN_PROFILE profile in $BRAIN_HOME to ${variable}."',
    ]
    return _render(
        "render_update",
        preamble,
        update_plan(plan),
        f"Done. This install is on ${variable} and pinned to it.",
    )


def render_rollback(
    *,
    repository: str,
    tunnel_token: str,
    plan: Sequence[Step] = PLAN,
    profiles: Sequence[str] = PROFILES,
) -> str:
    """The rollback script, as the shell it is.

    It takes no tag. `BRAIN_RELEASE_URL` is checked inside a step rather than demanded in the
    preamble, which is the one thing here that reads as an inconsistency and is not: the tag
    whose archive the operator has to supply is read out of the install, so demanding the URL
    before the script has printed the tag would be refusing to run over a value nobody could
    have known to set.
    """
    variable, _ = release_marker(plan)
    usage = "usage: rollback.sh <profile>"
    preamble = [
        f'BRAIN_PROFILE="${{1:?{usage}}}"',
        f'BRAIN_HOME="{INSTALL_HOME}"',
        f'BRAIN_REPOSITORY="{repository}"',
        f'{variable}=""',
        "",
        *_helpers(),
        "",
        *_profile_case(profiles),
        _tunnel_choice(tunnel_token),
        *_vault_choice(),
        "",
        'say "Going back one release on the $BRAIN_PROFILE profile in $BRAIN_HOME."',
    ]
    return _render(
        "render_rollback",
        preamble,
        rollback_plan(plan),
        f"Done. This install is back on ${variable} and pinned to it.",
    )


# ------------------------------------------------------------------ what the workflow asks
USAGE: Final = (
    "usage: python -m brain.deployment.release "
    "files | gaps | image-repository | migrations-path | update-script | rollback-script | "
    "notes <tag> <message file> [migration file ...]"
)


def main(argv: Sequence[str] | None = None) -> int:
    """What the release workflow asks, so the workflow spells no path itself, and two more.

    `migrations-path` looks like an odd thing to expose and it is the point: the workflow asks
    git which migration files a tag added, which needs the directory, and a directory typed
    into a workflow is a second declaration of where migrations live. It is
    `brain.deployment.compatibility.VERSIONS` here and nowhere else.

    `image-repository` is the same argument about the other artefact a release publishes. The
    image name is declared once, in `brain.deployment.installer.PRODUCT_IMAGE`, and the release
    workflow has to name it to move a tag onto it; written into the workflow it would be a
    fifth copy of a string that has already broken this deployment once by being renamed in
    four places and not in a fifth. Going through `image_repository` rather than printing the
    constant is deliberate: the answer is refused outright when no compose file reads the
    variable the install writes, so a release cannot publish an image tag that nothing an
    install brings up would ever pull.

    The two script commands are not asked by the workflow at all. They are how the checked-in
    files under `ops/update/` are produced, and the test that compares those files against
    these renderings is what keeps a generated artefact from drifting away from its generator.
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
    if command == "image-repository":
        print(image_repository(compose_documents()))
        return 0
    if command == "migrations-path":
        print(VERSIONS.relative_to(REPO).as_posix())
        return 0
    if command in {"update-script", "rollback-script"}:
        render = render_update if command == "update-script" else render_rollback
        print(
            render(
                repository=image_repository(compose_documents()),
                tunnel_token=tunnel_token_variable(),
            ),
            end="",
        )
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
