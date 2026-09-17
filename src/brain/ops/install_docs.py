"""Which claims in the install documentation are checked against the code, and how.

`docs/install/` is what somebody who has never met anybody here reads while standing in front
of a bare server. Two of those documents are lists, and **a hand-typed list goes stale the
week after it is written, silently, while continuing to look complete**. That is the whole
reason this module exists: not to render the documents, which are prose somebody has to write,
but to refuse the two lists when they stop agreeing with what the product declares.

**The configuration guide's register is four files and not one, and three of them are ones
nobody would look in.** `.env.example` is the obvious register and it is not the whole answer.
`POSTGRES_PASSWORD` is set on every install, is read by four compose files, and does not appear
in `.env.example` at all, because `brain.deployment.installer.PLAN` mints it on the client's own
server. `KEYCLOAK_ADMIN_PASSWORD` appears in no template either and is read straight out of a
compose file. `BRAIN_RELEASE` is not an environment-file value at all: it is the argument the
installer refuses to run without, and it is the whole of what a client pins. A guide checked
against the template alone would be complete by its own test and missing all three. See
`THE_REGISTER_IS_MORE_THAN_THE_TEMPLATE`.

**Where a value comes from is derived, never read off the guide.** A row saying a value is
minted by the installer is checked against the plan that mints it, and a row saying it is
collected by the wizard is checked against the questions that collect it. Both directions: a
variable the installer starts minting with no row, and a row claiming an installer mints
something it does not. The alternative is a provenance column that is prose, and a provenance
column that is prose is the one thing in the table nobody can act on when it is wrong, because
it reads exactly the same either way.

**The integration guide is checked against the manifests, in both directions, and the second
direction is the one that matters.** A connector with no section is a client who was handed a
source and no instructions, which is visible the first time somebody looks for it. A section
for a connector that no longer exists is invisible: it reads as coverage. See
`A_GUIDE_SECTION_FOR_A_CONNECTOR_THAT_IS_GONE_READS_AS_COVERAGE`. The set of connectors is read
out of the package rather than taken from the caller, so a connector added tomorrow is a
finding rather than a gap nobody noticed.

**What is checked is what a manifest declares and what does not vary between two installs.**
Transport, the kind of resource the scope pins to, the access mode, the permission-sync posture
and the rate ceiling are properties of the connector. Tool names are deliberately not among
them: `lark_base` names its tools after the entity it was configured with, so a guide listing
them would be right for one install and wrong for the next, and a check comparing them would
have to be handed a fixture's entity to agree with. See
`TOOL_NAMES_ARE_NOT_A_PROPERTY_OF_EVERY_CONNECTOR`.

Rejected: reading the documents, the template and the compose files here. Every function takes
text or documents somebody else parsed, which is the split `brain.ops.compose` and
`brain.deployment.requirements` both keep, and it is what lets each refusal be exercised against
a guide built to fail. A check that could only ever run against the real document has no test
for the case it exists to find, and `brain.ops.wiring.trace_stack_gaps` records what that costs.
The one exception is `connector_modules`, which reads a directory because the question it answers
is what the package contains, and `brain.ops.controls` reads the tree for the same reason.

Rejected: rendering the tables from the registers instead of checking them. It is the shape that
cannot go stale and it produces a document nobody wrote: the useful half of an install guide is
the sentence beside each value saying what it is for, and a generator has nothing to put there.
`brain.install.runbook` already exists for the generated half and has never been what a client
reads. So the guide is written, and this refuses it when it drifts.

**Nothing here is a gate and none of it runs in a sweep.** It is asserted by
`tests/unit/test_install_docs.py`, which is where `brain.launch.screen_runbook_gaps` and
`brain.ops.controls.registry_gaps` are asserted too, and for the same reason: the finding is
about a document in this repository rather than about a running system, so the unit suite is
the thing that has the document in front of it.

**Three pages were prose and nothing else until 2026-09-14, and each is held now by the part of
it that can be held.** The troubleshooting guide by its shape: every entry states what is seen
and what it is before it says what to do, because the reader arrives knowing the symptom and not
the name. The deployment checklist by its ten sections, the four links a copied install carries,
and the scheduled jobs this repository installs, read off the timer units in both directions.
The update page by its script table, read off the scripts the release carries. What each line
of those pages advises stays prose, and each page says so at its foot. See
`AN_ENTRY_THAT_OPENS_WITH_THE_REMEDY_IS_ONE_NOBODY_CAN_FIND`.

**The restore drill page is held by what a person following it writes, because nobody has
followed it.** The procedure is shell on a client's server and nothing here can run it. What can
be held is its output: the questions a drill record must answer, the fields it must carry, the
figures its schedule depends on, and the verdict the product reaches from the page's own worked
examples. That verdict is obtained through `brain.ops.backup_manifest.read_drills`, the reader
a real record goes through, and never by calling `verification_of` here:
`tests/unit/test_installation.py` pins that one module decides what a drill proved, and a
documentation check is not a second place for it. The page also states, as checked facts, which
pieces of a drill have no machine yet. See
`A_PROCEDURE_NOBODY_HAS_RUN_IS_HELD_BY_WHAT_IT_PRODUCES`.

Task ids: M42.2.3, M42.2.4, M42.2.5, M42.2.6, M42.2.8, M42.2.9, M42.3.7, M34.3.3.1, M34.3.3.2
**The administrative console decision is held by what can be read off a file, and no further.**
M37.6.1.3 asks for a decision to be written down: the consoles that control the server stay on
public addresses, each behind a second factor and an IP allowlist. The network page records it,
and what is checked is the part a document can get wrong on its own: the four consoles in both
directions, neither protection left blank on any of them, the two rejected options with their
reasons, the allowlist middleware the panel's proxy template defines and passes every router
through first, and whether the vault's interface is served at all. Whether a second factor is
switched on is a setting on an account inside a running console, and no check here pretends to
read it. See `A_PUBLIC_CONSOLE_NEEDS_A_SECOND_FACTOR_AND_AN_ALLOWLIST`.

Task ids: M34.3.3.3, M30.2.8, M42.3.3, M34.3.3.4, M37.6.1.3
"""

from __future__ import annotations

import ast
import enum
import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from brain.connectors.manifest import ConnectorManifest
from brain.deployment.installer import INSTALL_HOME
from brain.deployment.installer import Step as InstallStep
from brain.ops.backup_manifest import (
    CHECK_REQUIRED_FIELDS,
    DRILL_REQUIRED_FIELDS,
    DRILL_SUFFIX,
    MANIFEST_SUFFIX,
    ManifestError,
    backup_from,
    read_drills,
)
from brain.ops.controls import CONTROLS, Control
from brain.ops.queue import DeployStep
from brain.ops.recovery import DRILL_INTERVAL_DAYS, REQUIRED_CHECKS, Backup
from brain.ops.retention import BACKUP_RETENTION_DAYS
from brain.ops.wiring import PROFILES, assert_known_profile
from brain.setup_wizard import Step as WizardStep

# ------------------------------------------------------------------ written-down reasons
#: Why the configuration guide is not checked against `.env.example` alone.
THE_REGISTER_IS_MORE_THAN_THE_TEMPLATE: Final = (
    "A guide checked against .env.example alone is complete by its own test and missing the "
    "database password. POSTGRES_PASSWORD is set on every install and appears in no template, "
    "because the installer mints it on the client's own server; the Keycloak and trace-ledger "
    "credentials appear in no template either, because they are read straight out of the "
    "compose files; and BRAIN_RELEASE is not an environment-file value at all, it is the "
    "argument the installer refuses to run without. So the register is the template, the "
    "installer's mint steps, the interpolations in the compose files a profile composes, and "
    "what the rendered script demands, and a value in any of the four is a value somebody has "
    "to set."
)

#: Why the completeness check runs in both directions.
A_GUIDE_SECTION_FOR_A_CONNECTOR_THAT_IS_GONE_READS_AS_COVERAGE: Final = (
    "A connector with no section is a client handed a source and no instructions, and it is "
    "found the first time anybody looks for it. A section for a connector that no longer "
    "exists is not found at all: it reads as coverage, so the reader stops looking, and the "
    "guide is longer than the product. Both directions are checked for that asymmetry, which "
    "is the same argument brain.launch.screen_runbook_gaps makes about a runbook naming a "
    "screen somebody renamed."
)

#: Why the integration table names no tools.
TOOL_NAMES_ARE_NOT_A_PROPERTY_OF_EVERY_CONNECTOR: Final = (
    "lark_base declares lark_base.read_<entity> and lark_base.list_<entity>, where the entity "
    "is chosen when the connector is installed, so its tool names differ between two installs "
    "of one connector. A guide listing them would be right for whichever install it was "
    "written beside, and a check comparing them would have to be handed a fixture's entity to "
    "agree with, which is a check that agrees with the test rather than with the product. What "
    "is checked instead is every field of the manifest that two installs would both declare."
)

#: Why a value that has no default is worth saying so about, rather than left blank.
A_BLANK_DEFAULT_AND_AN_EMPTY_ONE_ARE_THE_SAME_LINE_ON_A_SERVER: Final = (
    "docker-compose.yml writes ${POSTGRES_PASSWORD} and docker-compose.lite.yml writes "
    "${APP_ROLE_PASSWORD:-}, and both resolve to an empty string when nobody sets them. The "
    "container starts, the connection is refused, and the message is about authentication "
    "rather than about a variable nobody set. So the guide states for every value whether "
    "anything anywhere supplies one, and this is where that column is held to the files."
)


class InstallDocsError(Exception):
    """Raised when a document cannot be read as the thing the check is about."""


# ------------------------------------------------------------------- where a value comes from
class Provenance(enum.StrEnum):
    """Who supplies one value, of the three answers this system can prove.

    Three rather than a longer vocabulary, because each of these is derivable from a
    declaration and anything finer would be a judgement typed into a table. `YOU` is the
    residue and is deliberately the widest: a value nothing in this repository mints and no
    wizard screen asks for is a value somebody has to know about and type, whether that is an
    image tag, an identity provider's issuer or a Keycloak password.
    """

    #: Minted on the client's own server by `brain.deployment.installer.PLAN`.
    INSTALLER = "installer"
    #: Collected by a screen of `brain.setup_wizard.WIZARD`.
    WIZARD = "wizard"
    #: Set by whoever installs, before the stack is started.
    YOU = "you"


@dataclass(frozen=True)
class Variable:
    """One value a new client must set, as the registers declare it.

    Obtainable from `variables` rather than constructed by a caller. Every field on it is read
    off a register, so a hand-built one would be a fourth opinion about what a client sets.
    """

    name: str
    comes_from: Provenance
    #: True when the template or a compose interpolation supplies a usable value. See
    #: `A_BLANK_DEFAULT_AND_AN_EMPTY_ONE_ARE_THE_SAME_LINE_ON_A_SERVER`.
    has_default: bool
    #: The profiles that read it, in declaration order.
    profiles: tuple[str, ...]


#: `${NAME}`, `${NAME:-default}` and `${NAME:?message}`, which are the three forms the compose
#: files use. The operator and the default are captured separately because only one pair of
#: them supplies a value: `:-` with something after it.
INTERPOLATION: Final = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?::([-?])([^}]*))?\}")

#: `printf "NAME=` inside an install step, which is how every credential the installer mints is
#: written. Anchored on the output builtin rather than on the assignment alone, so a shell test
#: comparing against `NAME=` is not read as minting one.
MINTS: Final = re.compile(r'printf\s+"([A-Z][A-Z0-9_]*)=')

#: `NAME="${...:?message}"` at the top of the rendered installer, which is the shell's way of
#: demanding a value and refusing to run without one. It is the fourth register and the one that
#: is not an environment file at all: `BRAIN_RELEASE` arrives as the script's first argument and
#: `BRAIN_RELEASE_URL` out of the environment, and both are values a client supplies.
#:
#: Matched on `:?` rather than on the assignment, because the same block also writes the profile,
#: the install directory, the compose file list, the service count and the memory figure, and all
#: five of those are computed by the generator. A register that counted them would send a client
#: to set five values nobody can set.
DEMANDED: Final = re.compile(r'^([A-Z][A-Z0-9_]*)="\$\{[^}]*:\?[^}]*\}"', re.M)


def minted_variables(plan: Sequence[InstallStep]) -> frozenset[str]:
    """Every variable the installer writes on the client's server, read out of the plan.

    Read rather than listed, because the plan is where the answer changes: a fifth credential
    added to the mint step is a fifth value a client has, and a list here would go on naming
    four. This is the half of the register `.env.example` cannot hold, for the reason
    `THE_REGISTER_IS_MORE_THAN_THE_TEMPLATE` gives.

    A step that changes nothing cannot mint anything, so the last step of the plan, which
    prints the setup code and writes nothing, is not read as a source of one.
    """
    found: set[str] = set()
    for step in plan:
        if not step.changes:
            continue
        found.update(MINTS.findall(step.run))
    return frozenset(found)


def script_variables(script: str) -> frozenset[str]:
    """Every value whoever runs the installer has to supply, read out of the rendered script.

    The fourth register, and the one nobody would think to look in, because it is not an
    environment file: these are an argument and an environment variable that the script itself
    refuses to run without. `BRAIN_RELEASE` is the release tag, which is the whole of what a
    client pins, and it has deliberately no default anywhere, because a default of `latest` is
    what makes an install unpinned.

    See `DEMANDED` for why this reads the shell's own refusal rather than the assignments: the
    same block writes five figures the generator computed, and a client cannot set any of them.
    """
    return frozenset(DEMANDED.findall(script))


def wizard_settings(steps: Sequence[WizardStep]) -> frozenset[str]:
    """Every installation setting a wizard screen collects an answer for.

    `Question.setting` is empty for an answer that is used rather than stored, so the residue
    here is exactly the settings a person will not be asked for and has to write into the
    environment file themselves. That is the distinction the guide's provenance column makes,
    and reading it off the wizard is what stops the column being a guess.
    """
    return frozenset(
        question.setting for step in steps for question in step.questions if question.setting
    )


def interpolations(document: Any) -> dict[str, bool]:
    """Every `${VAR}` in one compose document, against whether it supplies a usable default.

    Recursive over the parsed document rather than a scan of the file's text, so a variable
    inside a command list or a nested environment mapping is found and one inside a comment is
    not: a commented-out service is not a value anybody has to set.

    `${VAR:-}` counts as no default, which is not a technicality. See
    `A_BLANK_DEFAULT_AND_AN_EMPTY_ONE_ARE_THE_SAME_LINE_ON_A_SERVER`.
    """
    found: dict[str, bool] = {}
    _walk(document, found)
    return found


def _walk(node: Any, found: dict[str, bool]) -> None:
    """One node of a parsed compose document, and everything under it."""
    if isinstance(node, str):
        for name, operator, default in INTERPOLATION.findall(node):
            supplied = operator == "-" and bool(default.strip())
            found[name] = found.get(name, False) or supplied
        return
    if isinstance(node, Mapping):
        for key, value in node.items():
            _walk(key, found)
            _walk(value, found)
        return
    if isinstance(node, list | tuple):
        for item in node:
            _walk(item, found)


def variables(
    *,
    template: Mapping[str, str],
    minted: Collection[str],
    wizard: Collection[str],
    compose: Mapping[str, Mapping[str, Any]],
    script: Collection[str] = (),
) -> tuple[Variable, ...]:
    """Every value a new client must set, from every register that declares one.

    `template` is `.env.example` parsed, `compose` is the parsed compose documents per profile,
    and the other three are the sets `minted_variables`, `wizard_settings` and `script_variables`
    produce. Arguments rather than reads, so the check can be asked about a register with a
    variable in it that the guide has never heard of.

    A variable in the template belongs to every profile, because the application reads it
    whatever is deployed beside it. A variable that appears only in a compose file belongs to
    the profiles whose file list contains that file, which is what stops a client running the
    smallest profile reading twenty rows about a trace ledger they do not have.

    Sorted by name, because the guide is a table somebody reads down and a register in
    declaration order would put the compose variables in whatever order the files happen to be
    composed in.
    """
    defaults: dict[str, bool] = {}
    profiles: dict[str, set[str]] = {}
    for name, value in template.items():
        defaults[name] = bool(value.strip())
        profiles[name] = set(PROFILES)
    for profile in compose:
        assert_known_profile(profile)
        for document in compose[profile].values():
            for name, supplied in interpolations(document).items():
                defaults[name] = defaults.get(name, False) or supplied
                profiles.setdefault(name, set()).add(profile)
    for name in script:
        # The shell refuses to run without it, so it has no default whatever else says, and it
        # belongs to every profile because the installer demands it before it knows which one.
        defaults[name] = False
        profiles.setdefault(name, set()).update(PROFILES)
    return tuple(
        Variable(
            name=name,
            comes_from=_provenance(name, minted=minted, wizard=wizard),
            has_default=defaults[name],
            profiles=tuple(one for one in PROFILES if one in profiles[name]),
        )
        for name in sorted(defaults)
    )


def _provenance(name: str, *, minted: Collection[str], wizard: Collection[str]) -> Provenance:
    """Who supplies this value. The installer first, because a minted value is nobody's to type."""
    if name in minted:
        return Provenance.INSTALLER
    if name in wizard:
        return Provenance.WIZARD
    return Provenance.YOU


# ------------------------------------------------------------------- reading the documents
#: What marks the table this module checks, in the configuration guide.
#:
#: A comment rather than a heading, because a heading is prose somebody rewrites and the marker
#: has to survive that. A guide whose marker was renamed refuses rather than reporting no
#: findings, which is the direction that matters: a completeness check that quietly stops
#: finding the thing it checks is worse than one that is absent.
VALUES_MARKER: Final = "<!-- checked: every value a new client must set -->"

#: What marks the table this module checks, in the integration guide.
CONNECTORS_MARKER: Final = "<!-- checked: what each connector is trusted to read -->"

#: What marks the table this module checks, in the network guide.
PORTS_MARKER: Final = "<!-- checked: every port this deployment opens -->"

#: What marks the table this module checks, in the step-by-step install.
STEPS_MARKER: Final = "<!-- checked: the steps the installer runs -->"
#: Where the operations chapter lists what runs on a schedule and what starts each one.
MECHANISMS_MARKER: Final = (
    "<!-- checked: every scheduled mechanism and whether anything starts it -->"
)
#: Where the operations chapter lists the steps that install the job queue.
#:
#: A second marker rather than a second table under `STEPS_MARKER`, because these are a second
#: plan rather than more of the first one. `brain.deployment.installer.PLAN` runs on the
#: client's server once; `brain.ops.queue.DEPLOY_PLAN` is applied against the database by an
#: operator, some of it optional depending on what the database has already seen. Merging them
#: would make every row need a column saying which install it belongs to, which is the same
#: information in a worse place.
QUEUE_STEPS_MARKER: Final = "<!-- checked: the steps that install the job queue -->"

#: The cell that marks a queue step an install may already have satisfied.
#:
#: Spelled in the table rather than left to an empty cell, for the reason `NO_CEILING` is
#: spelled: an empty cell reads as one somebody did not fill in, and the difference between
#: "you may skip this" and "nobody said" is exactly what an operator is reading the column for.
REQUIRED_STEP: Final = "required"
OPTIONAL_STEP: Final = "optional"

#: One connector's section heading, which is its manifest name in a code span. Matched rather
#: than searched for by name, so a heading for a connector nobody has is a finding.
SECTION: Final = re.compile(r"^##\s+`([a-z][a-z0-9_]*)`\s*$", re.M)

#: The cell that stands for a connector with no verified rate ceiling. `ConnectorManifest`
#: spells that as an empty string, and an empty cell in a table reads as a cell somebody did
#: not fill in rather than as a statement that no ceiling was ever measured.
NO_CEILING: Final = "none measured"

#: The cell that stands for a value every profile reads, rather than the three profile names.
EVERY_PROFILE: Final = "every profile"


def table_after(text: str, marker: str) -> tuple[tuple[str, ...], ...]:
    """The body rows of the first markdown table after `marker`, as tuples of cells.

    Raises when the marker is missing and when nothing after it is a table, rather than
    returning nothing. **An empty result would be indistinguishable from a table with no rows
    in it**, and every check below reports a missing row, so a guide that had lost its table
    entirely would come back with one finding per variable and read as a formatting mistake
    rather than as a document that no longer contains the thing being checked.

    The header row and the `---` rule are dropped, and a table with neither is refused: two
    rows of a three-row table are its header, and a check reading them as data would compare
    the word "Variable" against a register.
    """
    at = text.find(marker)
    if at < 0:
        msg = f"the guide carries no {marker!r}, so there is no table to check against"
        raise InstallDocsError(msg)
    rows: list[tuple[str, ...]] = []
    for line in text[at + len(marker) :].splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        rows.append(tuple(cell.strip() for cell in stripped.strip("|").split("|")))
    if len(rows) < 3:
        msg = (
            f"the table after {marker!r} has {len(rows)} row(s); a header, a rule and at "
            "least one row is the smallest table that states anything"
        )
        raise InstallDocsError(msg)
    return tuple(rows[2:])


def bare(cell: str) -> str:
    """One cell with its code span removed, so a table can be readable and still comparable."""
    return cell.strip().strip("`").strip()


# --------------------------------------------------------- the configuration guide (M42.2.5)
def profiles_cell(one: Variable) -> str:
    """How the guide names the profiles that read this value."""
    return EVERY_PROFILE if len(one.profiles) == len(PROFILES) else ", ".join(one.profiles)


def default_cell(one: Variable) -> str:
    """How the guide says whether anything supplies a value when nobody sets one."""
    return "yes" if one.has_default else "none"


def configuration_gaps(guide: str, *, register: Sequence[Variable]) -> tuple[str, ...]:
    """Every way the configuration guide and the registers disagree (M42.2.5).

    Five findings and they are not five spellings of one. A variable with no row is a value
    somebody sets by reading a compose file. A row for a variable no register declares is a
    value somebody sets that nothing reads, which is worse, because it looks like work that was
    done. Two rows for one variable is one of them being the one people read. And the three
    checked cells each carry a different mistake: the wrong profile sends a client hunting for
    a container they do not run, the wrong provenance has them typing a value the installer
    already minted, and the wrong default has them leaving blank a value nothing supplies.

    The fifth cell of each row is what the value is for, and it is deliberately not checked.
    That sentence is the reason the table is worth reading and there is nothing in this
    repository to check it against; `brain.install.Setting.meaning` covers eighteen of the
    fifty-odd and says nothing about the rest.
    """
    declared = {one.name: one for one in register}
    findings: list[str] = []
    stated: dict[str, tuple[str, ...]] = {}
    for cells in table_after(guide, VALUES_MARKER):
        if len(cells) < 5:
            findings.append(
                f"a row with {len(cells)} cell(s) reads {cells}; every row states the "
                "variable, the profiles, where it comes from, whether it has a default and "
                "what it is for"
            )
            continue
        name = bare(cells[0])
        if name in stated:
            findings.append(
                f"{name}: two rows, and whichever a reader finds first is the one they act on"
            )
            continue
        stated[name] = cells
    findings.extend(
        f"{name}: no row, so a client sets it by reading a compose file or does not set it"
        for name in sorted(set(declared) - set(stated))
    )
    findings.extend(
        f"{name}: a row for a variable no register declares, which reads as a value that "
        "matters and is a value nothing reads"
        for name in sorted(set(stated) - set(declared))
    )
    for name in sorted(set(stated) & set(declared)):
        one, cells = declared[name], stated[name]
        findings.extend(_cell_gaps(one, cells))
    return tuple(findings)


def _cell_gaps(one: Variable, cells: Sequence[str]) -> tuple[str, ...]:
    """The three checked cells of one row against what the registers say.

    Collected rather than returned at the first mismatch, matching every other check here: a
    row that is wrong about two things is two edits, and finding out about the second one after
    fixing the first is a second run of the suite.
    """
    expected = (profiles_cell(one), one.comes_from.value, default_cell(one))
    columns = ("the profiles that read it", "where it comes from", "whether it has a default")
    return tuple(
        f"{one.name}: {column} reads {bare(cells[index + 1])!r} and the registers say {want!r}"
        for index, (column, want) in enumerate(zip(columns, expected, strict=True))
        if bare(cells[index + 1]) != want
    )


# ------------------------------------------------- the step-by-step install (M42.2.3)
def step_gaps(guide: str, *, plan: Sequence[InstallStep]) -> tuple[str, ...]:
    """Every way the written install and the install plan disagree (M42.2.3).

    A guide that lists the steps by hand is a second plan, and the second one is the one that
    goes stale, because nothing imports it. `brain.launch` makes the same argument about a
    handover document that restates a register. What is different here is that the drift is
    invisible in the worst direction: a step appended to the plan and not to the guide leaves a
    person following the guide with an install that stopped one step short of working, and the
    guide reads as complete.

    **Order is checked and it is checked separately.** A guide naming every step in the wrong
    order is a guide that mints credentials before the environment file exists, and a
    membership check alone would pass it. It is reported only when nothing is missing or extra,
    because a list with a step missing is out of order by arithmetic and saying so twice buries
    the finding somebody can act on.
    """
    findings: list[str] = []
    stated: list[str] = []
    for cells in table_after(guide, STEPS_MARKER):
        if len(cells) < 3:
            findings.append(
                f"a row with {len(cells)} cell(s) reads {cells}; every row states the step, "
                "what it does and what to do when it fails"
            )
            continue
        stated.append(bare(cells[0]))
    named = [one.name for one in plan]
    findings.extend(
        f"{name!r}: the installer runs this step and the guide does not list it, so somebody "
        "following the guide stops one step short of a working install"
        for name in named
        if name not in stated
    )
    findings.extend(
        f"{name!r}: the guide lists a step the installer does not run"
        for name in stated
        if name not in named
    )
    if not findings and stated != named:
        findings.append(
            f"the guide names every step and not in the order they run: it reads {stated} "
            f"and the installer runs {named}"
        )
    return tuple(findings)


# ------------------------------------------------------------- the network guide (M42.2.4)
def port_gaps(guide: str, *, exposed: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Ports this deployment opens that the network guide does not account for.

    The one checkable claim in a document that is otherwise about a machine nobody here has.
    A person putting a reverse proxy in front of this stack has to decide, per service, whether
    anything outside the compose network may reach it, and **the decision that goes wrong is
    the one nobody made**: a service added to a compose file with a port on it and no row here
    is a port that was never argued about, which is how a database ends up answering on an
    interface somebody assumed was internal.

    Both directions, as everywhere else. A row for a service that no longer opens a port reads
    as a decision that is still being kept.

    The application itself is deliberately absent from what this is asked about, and that is a
    fact about the deployment rather than an exemption: it declares neither `ports` nor
    `expose`, so the port the proxy has to send traffic to is written down only inside its own
    healthcheck command. The guide says so in words above the table, because there is nothing
    here to check it against.
    """
    findings: list[str] = []
    stated: dict[str, str] = {}
    for cells in table_after(guide, PORTS_MARKER):
        if len(cells) < 3:
            findings.append(
                f"a row with {len(cells)} cell(s) reads {cells}; every row states the "
                "service, the port and who may reach it"
            )
            continue
        stated[bare(cells[0])] = bare(cells[1])
    findings.extend(
        f"{name}: opens {', '.join(exposed[name])} and the guide does not say who may reach "
        "it, so nobody decided whether the proxy or the firewall should"
        for name in sorted(set(exposed) - set(stated))
    )
    findings.extend(
        f"{name}: a row for a service that opens no port, which reads as a decision somebody "
        "is still keeping"
        for name in sorted(set(stated) - set(exposed))
    )
    findings.extend(
        f"{name}: the guide says port {stated[name]!r} and the compose files open "
        f"{', '.join(exposed[name])!r}"
        for name in sorted(set(stated) & set(exposed))
        if stated[name] != ", ".join(exposed[name])
    )
    return tuple(findings)


# ----------------------------------------------------------- the integration guide (M42.2.6)
def ceiling_cell(manifest: ConnectorManifest) -> str:
    """How the guide names the rate ceiling a connector runs against, measured or not."""
    return manifest.ceiling or NO_CEILING


def integration_gaps(guide: str, *, manifests: Sequence[ConnectorManifest]) -> tuple[str, ...]:
    """Every way the integration guide and the connector manifests disagree (M42.2.6).

    Both directions for both halves, the table and the sections, for the reason in
    `A_GUIDE_SECTION_FOR_A_CONNECTOR_THAT_IS_GONE_READS_AS_COVERAGE`.

    The five checked cells are the manifest's own fields, and each is a claim a client acts on.
    What the connector is pinned to at connect is the answer to "what is it trusted to read".
    The access mode is whether it can change anything at the source. The permission-sync
    posture is whether the source is applying its own rules to the person asking, and a guide
    overstating that is the failure
    `brain.connectors.manifest.A_PERMISSION_SYNC_CLAIM_IS_CHECKED_AGAINST_THE_DECLARATIONS`
    describes, arriving through a document rather than through a console.
    """
    declared = {one.name: one for one in manifests}
    findings: list[str] = []
    rows: dict[str, tuple[str, ...]] = {}
    for cells in table_after(guide, CONNECTORS_MARKER):
        if len(cells) < 6:
            findings.append(
                f"a row with {len(cells)} cell(s) reads {cells}; every row states the "
                "connector, the transport, what it is pinned to, the access, what the source "
                "enforces and the rate ceiling"
            )
            continue
        rows[bare(cells[0])] = cells
    findings.extend(
        f"{name}: no row in the table, so a client installing it has nothing saying what it "
        "is trusted to read"
        for name in sorted(set(declared) - set(rows))
    )
    findings.extend(
        f"{name}: a row for a connector this install does not have. "
        f"{A_GUIDE_SECTION_FOR_A_CONNECTOR_THAT_IS_GONE_READS_AS_COVERAGE}"
        for name in sorted(set(rows) - set(declared))
    )
    for name in sorted(set(rows) & set(declared)):
        findings.extend(_connector_cell_gaps(declared[name], rows[name]))
    sections = set(SECTION.findall(guide))
    findings.extend(
        f"{name}: no section of its own, so the table names a connector the guide never says "
        "how to install"
        for name in sorted(set(declared) - sections)
    )
    findings.extend(
        f"{name}: a section for a connector this install does not have. "
        f"{A_GUIDE_SECTION_FOR_A_CONNECTOR_THAT_IS_GONE_READS_AS_COVERAGE}"
        for name in sorted(sections - set(declared))
    )
    return tuple(findings)


def _connector_cell_gaps(manifest: ConnectorManifest, cells: Sequence[str]) -> tuple[str, ...]:
    """The five checked cells of one connector's row against its manifest."""
    expected = (
        manifest.transport.value,
        manifest.scope.resource_kind,
        manifest.credential.mode.value,
        manifest.permission_sync.value,
        ceiling_cell(manifest),
    )
    columns = (
        "the transport",
        "what it is pinned to at connect",
        "the access it is bound with",
        "what the source enforces",
        "the rate ceiling",
    )
    return tuple(
        f"{manifest.name}: {column} reads {bare(cells[index + 1])!r} and the manifest "
        f"declares {want!r}"
        for index, (column, want) in enumerate(zip(columns, expected, strict=True))
        if bare(cells[index + 1]) != want
    )


#: The return annotation that makes a function a connector's manifest builder. Every one of the
#: seven is spelled differently on the left of it, `manifest` in four modules and
#: `<name>_manifest` in three, so a scan by function name would have found four connectors and
#: reported the other three as absent. The annotation is the one thing all seven share.
# --------------------------------------------------- the operations guide (M42.2.8)
def started_by_cell(one: Control) -> str:
    """How the guide names what starts a control, in the registry's own vocabulary.

    The enum value rather than a sentence, because the sentence is `handover_lines`' job and a
    second prose rendering here would be a second thing to keep in step. What a client reads
    beside it in the chapter is prose; what this compares is the word.
    """
    return one.invoked_by.value


def mechanism_gaps(guide: str, *, controls: Sequence[Control] | None = None) -> tuple[str, ...]:
    """Every way the operations chapter and the control registry disagree (M42.2.8).

    **The chapter said "the twelve mechanisms nothing runs" and eleven of them did not.** One
    control acquired a caller on 2026-09-09 and the heading, the table and the count were three
    hand-maintained copies of a fact the registry already holds. That is the drift this check
    exists for, and it is the one a client feels: an operations chapter that names twelve
    mechanisms as unwired is a chapter somebody reads once, believes, and does not re-read on
    the day the twelfth is switched on.

    Both directions and the value as well as the membership. A control with no row is a
    mechanism the client was never told about. A row naming no control is a mechanism that was
    removed from the product and is still being planned around. And a row whose "started by"
    disagrees with the registry is the worst of the three, because it is the column the reader
    acts on: a mechanism recorded as running that nothing calls is exactly the sentence
    `brain.ops.controls.handover_lines` refuses to let a handover pack print.

    `controls` is a parameter defaulting to the registry, for the reason
    `brain.ops.recovery.backup_policy_gaps` takes the same shape: a check that can only be run
    against the healthy declaration cannot be shown to fail.
    """
    rows = CONTROLS if controls is None else tuple(controls)
    findings: list[str] = []
    stated: dict[str, str] = {}
    for cells in table_after(guide, MECHANISMS_MARKER):
        if len(cells) < 3:
            findings.append(
                f"a row with {len(cells)} cell(s) reads {cells}; every row states the "
                "mechanism, what it guards and what starts it"
            )
            continue
        stated[bare(cells[0])] = bare(cells[2])
    declared = {one.name: started_by_cell(one) for one in rows}
    findings.extend(
        f"{name}: a mechanism this install carries and the operations chapter does not name, "
        "so the client was never told it exists"
        for name in sorted(set(declared) - set(stated))
    )
    findings.extend(
        f"{name}: a row for a mechanism this install does not carry, so the client is "
        "planning around something that is not here"
        for name in sorted(set(stated) - set(declared))
    )
    findings.extend(
        f"{name}: the chapter says it is started by {stated[name]!r} and the registry says "
        f"{declared[name]!r}, which is the column somebody acts on"
        for name in sorted(set(stated) & set(declared))
        if stated[name] != declared[name]
    )
    return tuple(findings)


def queue_step_gaps(guide: str, *, plan: Sequence[DeployStep] | None = None) -> tuple[str, ...]:
    """Every way the operations chapter and the queue's deploy plan disagree.

    **The gap this closes was found by the session that built the plan, not by any check.**
    `brain.ops.queue.DEPLOY_PLAN` is the four steps that turn a database with a driver
    installed into one with a queue on it, and `python -m brain.ops.worker --deploy-plan`
    prints them. Nothing pointed an operator at that command, and the chapter they would
    actually open said nothing about the queue at all. A plan printed by a command nobody is
    told to run is the documentation equivalent of this repository's recurring defect.

    `step_gaps` makes the whole argument for holding a guide against a plan rather than
    letting it list the steps by hand, and this is that argument applied to the second plan.
    What is different is which cell matters most. There, a missing step leaves an install one
    step short; here, the step most worth getting right is the one an operator may skip. The
    driver's schema DDL is not idempotent, so a step described as optional that is not is an
    install that stops, and a step described as required that is not is an operator running
    something that raises `DuplicateObject` on a database that was already correct. So the
    optional column is checked as a value and not merely as a presence.

    **Matched on `kind` rather than on the sentence.** `DeployStep.what` is prose meant to be
    read, and holding a table against prose means the table has to restate a sentence that can
    be improved, so improving it breaks the check and the fix is to paste the new wording
    across. `kind` is the field the plan's own tests treat as the stable identifier for exactly
    this reason.

    Order is reported only when nothing is missing or extra, for the reason `step_gaps` gives:
    a list with a step missing is out of order by arithmetic, and saying so twice buries the
    finding somebody can act on.

    `plan` is a parameter defaulting to the real one, the shape `mechanism_gaps` and
    `backup_policy_gaps` both take: a check that can only be run against today's plan is a
    check whose failure mode cannot be tested.
    """
    from brain.ops.queue import DEPLOY_PLAN

    steps = DEPLOY_PLAN if plan is None else plan
    findings: list[str] = []
    stated: list[str] = []
    optionality: dict[str, str] = {}
    for cells in table_after(guide, QUEUE_STEPS_MARKER):
        if len(cells) < 3:
            findings.append(
                f"a row with {len(cells)} cell(s) reads {cells}; every row states the step, "
                "what it does and whether an install may skip it"
            )
            continue
        kind = bare(cells[0])
        stated.append(kind)
        optionality[kind] = bare(cells[2])
    # `.value` rather than the member, and it is not cosmetic. `StepKind` is a `StrEnum`, so
    # a member compares equal to its own string at runtime: every check below passed while
    # mypy refused the dictionary lookups, because the table yields `str` and the plan yields
    # members and only the type checker could see the difference. One vocabulary throughout
    # is what keeps a finding here about the document rather than about a conversion.
    named = [one.kind.value for one in steps]
    skippable = {one.kind.value: OPTIONAL_STEP if one.optional else REQUIRED_STEP for one in steps}
    findings.extend(
        f"{kind!r}: the queue install runs this step and the chapter does not list it, so an "
        "operator following the chapter leaves the queue half installed"
        for kind in named
        if kind not in stated
    )
    findings.extend(
        f"{kind!r}: the chapter lists a queue step the install does not run"
        for kind in stated
        if kind not in named
    )
    findings.extend(
        f"{kind!r}: the chapter calls it {optionality[kind]!r} and the plan says "
        f"{skippable[kind]!r}, which is the column that decides whether somebody runs it"
        for kind in sorted(set(stated) & set(named))
        if optionality[kind] != skippable[kind]
    )
    if not findings and stated != named:
        findings.append(
            f"the chapter names every queue step and not in the order they run: it reads "
            f"{stated} and the install runs {named}"
        )
    return tuple(findings)


MANIFEST_BUILDER: Final = "ConnectorManifest"


def connector_modules(package: Path) -> tuple[str, ...]:
    """Every module in the connectors package that declares a manifest builder.

    Read out of the package rather than taken as an argument, which is the one read in this
    module and is the same read `brain.ops.controls` makes of the tree: the question is what
    this repository contains, and a caller who had to pass the answer would pass the answer they
    already believed. A connector added tomorrow is then a finding rather than a gap nobody
    noticed, which is the whole point of checking a document against a package.

    Module level only. A builder defined inside a function is not a connector anybody installs,
    and walking the whole tree would find the fixtures a test defines inside its own body.
    """
    found: list[str] = []
    for path in sorted(package.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.FunctionDef)
            and isinstance(node.returns, ast.Name)
            and node.returns.id == MANIFEST_BUILDER
            for node in tree.body
        ):
            found.append(path.stem)
    return tuple(found)


def connector_gaps(
    modules: Collection[str], manifests: Sequence[ConnectorManifest]
) -> tuple[str, ...]:
    """Connectors the package declares that no manifest was built for, and the reverse.

    The stage before `integration_gaps`, and it is a separate check rather than a branch inside
    it because the two fail for different people. A module with no manifest here is a caller who
    has not been shown the whole package, so every claim `integration_gaps` makes is about a
    subset it was never told was a subset. A manifest naming a module that does not exist is a
    connector that was deleted with its fixture left behind.
    """
    named = {one.name for one in manifests}
    findings = [
        f"{name}: the package declares a manifest builder for it and none was handed to the "
        "check, so the guide is being held to a subset of the connectors"
        for name in sorted(set(modules) - named)
    ]
    findings.extend(
        f"{name}: a manifest for a connector this package has no module for"
        for name in sorted(named - set(modules))
    )
    return tuple(findings)


# ------------------------------------------------------------- pages read as sections
#: One level-two heading. `###` does not match, because the third character is not a space.
HEADING: Final = re.compile(r"^##\s+(.+?)\s*$", re.M)


def sections(text: str) -> tuple[tuple[str, str], ...]:
    """Every level-two heading in a page and the text under it, in the order they appear."""
    found = list(HEADING.finditer(text))
    return tuple(
        (
            one.group(1),
            text[one.end() : found[index + 1].start() if index + 1 < len(found) else len(text)],
        )
        for index, one in enumerate(found)
    )


# --------------------------------------------------------- the troubleshooting guide (M42.2.9)
#: Why an entry has to state the symptom and the cause before the remedy.
AN_ENTRY_THAT_OPENS_WITH_THE_REMEDY_IS_ONE_NOBODY_CAN_FIND: Final = (
    "Somebody troubleshooting knows what they are seeing and not what it is called, so an entry "
    "is found by its symptom and believed by its cause. An entry that opens with what to do "
    "asks the reader to already know which failure they have, and an entry with no remedy at "
    "all is a story. So every entry says what to do, and says something before it."
)

#: The line every troubleshooting entry carries once it has said what is happening.
WHAT_TO_DO: Final = "**What to do.**"

#: The sections of the troubleshooting guide that are not entries, and that come last.
TROUBLESHOOTING_CLOSING: Final = (
    "Failures from this build that you will not meet",
    "What is checked and what is not",
    "Task ids",
)


def troubleshooting_gaps(guide: str) -> tuple[str, ...]:
    """Every entry in the troubleshooting guide that cannot be used the way it is meant to be.

    Structure only, and deliberately. Whether a heading reads as a symptom is a judgement, and
    a check pretending to make it would be a word list somebody satisfies. What is checked is
    what makes a symptom-first entry usable at all: it says what to do, it says something
    before that, and it sits above the closing sections rather than after them, where a reader
    who has stopped at "failures you will not meet" would never reach it.
    """
    found = sections(guide)
    entries = [(heading, body) for heading, body in found if heading not in TROUBLESHOOTING_CLOSING]
    if not entries:
        return (
            "the guide carries no entries, so there is nothing a reader can look a symptom up in",
        )
    findings: list[str] = []
    for heading, body in entries:
        at = body.find(WHAT_TO_DO)
        if at < 0:
            findings.append(f"{heading!r}: says what is happening and never what to do about it")
        elif not body[:at].strip(" \n-"):
            findings.append(
                f"{heading!r}: opens with what to do, so a reader who knows only the symptom "
                "has nothing to recognise it by"
            )
    headings = [heading for heading, _ in found]
    closing_at = [
        index for index, heading in enumerate(headings) if heading in TROUBLESHOOTING_CLOSING
    ]
    if closing_at:
        findings.extend(
            f"{heading!r}: an entry after the closing sections, where nobody reading for a "
            "symptom still is"
            for heading in headings[closing_at[0] :]
            if heading not in TROUBLESHOOTING_CLOSING
        )
    return tuple(findings)


# ----------------------------------------------------------- the deployment checklist (M42.3.7)
#: The ten sections the checklist is written in, in the order the work happens.
CHECKLIST_SECTIONS: Final = (
    "Pre-deployment",
    "Server",
    "Application",
    "Database",
    "Environment",
    "Integrations",
    "Security",
    "Testing",
    "Go-live",
    "Post-deployment",
)

#: The sections of the checklist that are about the page rather than about the install.
CHECKLIST_CLOSING: Final = ("What is checked and what is not", "Task ids")

#: One item somebody ticks.
CHECKLIST_ITEM: Final = re.compile(r"^\s*- \[ \] \S", re.M)

#: The four links a copy of an install carries to the install it was copied from (M34.3.3.1,
#: M30.2.8). Named by where they hide rather than by one platform's file names, because the
#: platform differs between two installs and the hiding place does not.
HIDDEN_LINKS: Final = (
    "platform project files",
    "temporary CLI state",
    "git remotes",
    "scheduled jobs",
)

#: Why a copied install is checked for links and not only for credentials.
A_COPY_ACTS_ON_WHAT_THE_ORIGINAL_POINTED_AT: Final = (
    "A server image, a home directory or a deployment project copied from one install to "
    "another carries more than its credentials. It carries where a deploy tool stored its own "
    "copy of the project, a registry login and an ssh destination, a remote naming somebody "
    "else's repository, and timers that keep running against whatever they were pointed at. "
    "Three of the four are invisible from the directory a person is looking at, and every one "
    "of them acts on the original install the moment the copy starts."
)

#: Where the checklist names the four links.
LINKS_MARKER: Final = "<!-- checked: the four links a copied install carries -->"

#: Where the checklist names every scheduled job this repository installs.
TIMERS_MARKER: Final = "<!-- checked: every scheduled job this repository installs -->"


def checklist_gaps(guide: str) -> tuple[str, ...]:
    """Every way the deployment checklist has stopped being the checklist the leaf asks for.

    The ten sections by name and in order, none of them empty, and the four links a copied
    install carries by name in both directions. A section with no item is a heading somebody
    reads as done, and a link table that has lost a row is the one hiding place nobody checks.
    """
    findings: list[str] = []
    found = [
        (heading, body) for heading, body in sections(guide) if heading not in CHECKLIST_CLOSING
    ]
    stated = [heading for heading, _ in found]
    findings.extend(
        f"{name!r}: the checklist has no section for it"
        for name in CHECKLIST_SECTIONS
        if name not in stated
    )
    findings.extend(
        f"{name!r}: a section the checklist does not declare, which reads as coverage"
        for name in stated
        if name not in CHECKLIST_SECTIONS
    )
    if not findings and stated != list(CHECKLIST_SECTIONS):
        findings.append(
            f"the sections are not in the order the work happens: the page reads {stated}"
        )
    findings.extend(
        f"{heading!r}: a section with nothing to tick, which reads as done"
        for heading, body in found
        if heading in CHECKLIST_SECTIONS and not CHECKLIST_ITEM.search(body)
    )
    named: list[str] = []
    for cells in table_after(guide, LINKS_MARKER):
        if len(cells) < 3:
            findings.append(
                f"a row with {len(cells)} cell(s) reads {cells}; every row states the link, "
                "where it hides and what to do"
            )
            continue
        named.append(bare(cells[0]))
    findings.extend(
        f"{link!r}: a copied install carries this link and the checklist does not name it"
        for link in HIDDEN_LINKS
        if link not in named
    )
    findings.extend(
        f"{link!r}: a link the checklist names that is not one of the four"
        for link in named
        if link not in HIDDEN_LINKS
    )
    return tuple(findings)


def scheduled_job_gaps(guide: str, *, timers: Collection[str]) -> tuple[str, ...]:
    """Timer units this repository installs that the checklist does not name, and the reverse.

    `timers` is the file names of the units, read out of `ops/` by the caller. A timer the page
    does not name is a job that survives a copied disk with nobody told to look for it; a row
    for a timer that is gone sends somebody looking for a unit that is not there, and reads as
    coverage while they do.
    """
    findings: list[str] = []
    named: list[str] = []
    for cells in table_after(guide, TIMERS_MARKER):
        if len(cells) < 3:
            findings.append(
                f"a row with {len(cells)} cell(s) reads {cells}; every row states the timer, "
                "what installs it and what it does"
            )
            continue
        named.append(bare(cells[0]))
    findings.extend(
        f"{timer}: this repository installs the timer and the checklist does not name it"
        for timer in sorted(timers)
        if timer not in named
    )
    findings.extend(
        f"{timer}: the checklist names a timer this repository does not install"
        for timer in named
        if timer not in timers
    )
    return tuple(findings)


# ------------------------------------------------------- the update page (M34.3.3.3)
#: Where the update page lists the scripts a person runs.
UPDATE_SCRIPTS_MARKER: Final = "<!-- checked: the update and rollback scripts -->"

#: Where the release unpacks the scripts, which is the directory the page tells somebody to run.
UPDATE_SCRIPTS_HOME: Final = f"{INSTALL_HOME}/ops/update"


def update_script_gaps(guide: str, *, scripts: Collection[str]) -> tuple[str, ...]:
    """Every way the update page's script table disagrees with the scripts the release carries.

    Both directions, and the command column as a value. A script renamed in `ops/update` with
    the page left alone is a command that fails with a missing file at the worst moment of
    somebody's week, which is the moment the rollback exists for.
    """
    findings: list[str] = []
    named: list[str] = []
    for cells in table_after(guide, UPDATE_SCRIPTS_MARKER):
        if len(cells) < 3:
            findings.append(
                f"a row with {len(cells)} cell(s) reads {cells}; every row states the script, "
                "the command and what it needs"
            )
            continue
        name = bare(cells[0])
        named.append(name)
        command = f"sh {UPDATE_SCRIPTS_HOME}/{name}"
        if bare(cells[1]) != command and not bare(cells[1]).startswith(f"{command} "):
            findings.append(
                f"{name}: the page says to run {bare(cells[1])!r}, and the release unpacks the "
                f"script at {UPDATE_SCRIPTS_HOME}/{name}"
            )
    findings.extend(
        f"{name}: the release carries this script and the page does not say how to run it"
        for name in sorted(scripts)
        if name not in named
    )
    findings.extend(
        f"{name}: the page names a script the release does not carry"
        for name in named
        if name not in scripts
    )
    return tuple(findings)


# ------------------------------------------------ the database commands (M42.3.3)
#: The table in the operations page naming every database command and how to run it.
DATABASE_COMMANDS_MARKER: Final = "<!-- checked: the database commands -->"


def database_command_gaps(guide: str, *, commands: Sequence[str], module: str) -> tuple[str, ...]:
    """Every way the page's database command table disagrees with the commands that exist.

    Handed the commands and the module rather than importing them, for the split this module
    keeps throughout. Both directions and the command column as a value: a command renamed in
    `brain.deployment.database` with the page left alone is a runbook line that prints a usage
    message to somebody in the middle of an install.
    """
    findings: list[str] = []
    named: list[str] = []
    for cells in table_after(guide, DATABASE_COMMANDS_MARKER):
        if len(cells) < 3:
            findings.append(
                f"a row with {len(cells)} cell(s) reads {cells}; every row states the command, "
                "how to run it and what it does"
            )
            continue
        name = bare(cells[0])
        named.append(name)
        expected = f"python -m {module} {name}"
        if bare(cells[1]) != expected:
            findings.append(
                f"{name}: the page says to run {bare(cells[1])!r}, and the command is {expected!r}"
            )
    findings.extend(
        f"{name}: this command exists and the page does not say how to run it"
        for name in commands
        if name not in named
    )
    findings.extend(
        f"{name}: the page names a database command that does not exist"
        for name in named
        if name not in commands
    )
    return tuple(findings)


# ------------------------------------------------------- the restore drill page (M34.3.3.4)
#: Why the drill page is checked by what following it produces.
A_PROCEDURE_NOBODY_HAS_RUN_IS_HELD_BY_WHAT_IT_PRODUCES: Final = (
    "A restore drill procedure is prose until somebody follows it on a server, and nobody has. "
    "What can be held is what a person following it writes and what the product makes of that: "
    "the checks a record must answer, the fields it must carry, and the verdict "
    "verification_of reaches from the page's own example. A page whose example the product "
    "refuses teaches everybody who copies it to write a record nothing can read, and the "
    "recovery panel then says never verified about an install that rehearsed every week."
)

#: Why the page states, as checked facts, what has no machine.
A_PROCEDURE_THAT_DOES_NOT_SAY_WHAT_IS_MISSING_READS_AS_AUTOMATION: Final = (
    "A page describing a weekly drill beside a console screen with a control to run one reads as "
    "a drill that runs. Nothing performs, schedules or starts one today, so each of those is a "
    "row stating whether it exists, compared against the repository, and the row goes red on the "
    "day one is built, which is the day the page's procedure should be read again."
)

#: Where the drill page lists the checks a drill asks, what each asks, and how.
DRILL_CHECKS_MARKER: Final = "<!-- checked: the questions a drill asks the copy -->"

#: Where the drill page lists the fields a drill record carries and where each sits.
DRILL_FIELDS_MARKER: Final = "<!-- checked: the fields a drill record carries -->"

#: Where the drill page states the figures its schedule and its file names depend on.
DRILL_FIGURES_MARKER: Final = "<!-- checked: the figures this procedure depends on -->"

#: Where the drill page states which pieces of a drill exist today.
DRILL_PIECES_MARKER: Final = "<!-- checked: what this procedure has no machine for -->"

#: The worked examples, each a fenced JSON block directly after its marker.
DRILL_COPY_EXAMPLE_MARKER: Final = "<!-- checked: the manifest of the copy the drill read -->"
DRILL_PASSING_EXAMPLE_MARKER: Final = "<!-- checked: a drill record that verifies -->"
DRILL_FAILING_EXAMPLE_MARKER: Final = "<!-- checked: a drill record that does not verify -->"

#: Where a field sits, as the fields table says it.
ON_THE_RECORD: Final = "the record"
ON_EACH_CHECK: Final = "each check"

#: A command a page tells somebody to run as a module.
RUNS_A_MODULE: Final = re.compile(r"python -m ([a-z_][a-z0-9_.]*[a-z0-9_])")

#: The object name a worked drill example is read under, ending as a real record's must.
EXAMPLE_RECORD: Final = f"example{DRILL_SUFFIX}"

_JSON_FENCE: Final = "```json"
_FENCE: Final = "```"


def drill_figures() -> tuple[tuple[str, str], ...]:
    """What the drill page's figures table has to say, read off the modules that decide each."""
    return (
        ("Days between rehearsals", str(DRILL_INTERVAL_DAYS)),
        ("Days a copy is kept", str(BACKUP_RETENTION_DAYS)),
        ("A copy's manifest name ends", MANIFEST_SUFFIX),
        ("A drill record's name ends", DRILL_SUFFIX),
    )


def json_after(text: str, marker: str) -> dict[str, Any]:
    """The JSON object in the fenced block directly after `marker`.

    Directly after, with nothing but blank lines between, because the first block anywhere after
    the marker would be the next example's when one is deleted, and a check reading the wrong
    example agrees with the page for the wrong reason. Raises rather than returning nothing, for
    `table_after`'s reason.
    """
    at = text.find(marker)
    if at < 0:
        msg = f"the page carries no {marker!r}, so there is no example to read"
        raise InstallDocsError(msg)
    after = at + len(marker)
    fence = text.find(_JSON_FENCE, after)
    if fence < 0 or text[after:fence].strip():
        msg = f"the example after {marker!r} is not a json block directly beneath it"
        raise InstallDocsError(msg)
    start = fence + len(_JSON_FENCE)
    end = text.find(_FENCE, start)
    if end < 0:
        msg = f"the example after {marker!r} opens a json block and never closes it"
        raise InstallDocsError(msg)
    try:
        document = json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        msg = f"the example after {marker!r} is not JSON: {exc}"
        raise InstallDocsError(msg) from exc
    if not isinstance(document, dict):
        msg = (
            f"the example after {marker!r} is a {type(document).__name__} and a record is an object"
        )
        raise InstallDocsError(msg)
    return document


def drill_procedure_gaps(
    page: str,
    *,
    pieces: Mapping[str, bool],
    runnable: Collection[str],
    figures: Sequence[tuple[str, str]] | None = None,
) -> tuple[str, ...]:
    """Every way the restore drill page disagrees with what a drill record must be (M34.3.3.4).

    `pieces` is whether each piece of a drill exists, observed by the caller from the repository,
    and `runnable` is every module that runs as a command, for the split this module keeps: the
    reading happens in the test. See `A_PROCEDURE_NOBODY_HAS_RUN_IS_HELD_BY_WHAT_IT_PRODUCES` and
    `A_PROCEDURE_THAT_DOES_NOT_SAY_WHAT_IS_MISSING_READS_AS_AUTOMATION`.
    """
    return (
        *_drill_check_gaps(page, runnable),
        *_drill_field_gaps(page),
        *_stated_gaps(
            page,
            DRILL_FIGURES_MARKER,
            dict(drill_figures() if figures is None else figures),
            noun="figure",
        ),
        *_stated_gaps(
            page,
            DRILL_PIECES_MARKER,
            {name: "yes" if built else "no" for name, built in pieces.items()},
            noun="piece",
        ),
        *_drill_example_gaps(page),
    )


def _drill_check_gaps(page: str, runnable: Collection[str]) -> tuple[str, ...]:
    """The checks, exactly `REQUIRED_CHECKS` in order, and every module a row says to run."""
    findings: list[str] = []
    stated: list[str] = []
    for cells in table_after(page, DRILL_CHECKS_MARKER):
        if len(cells) < 3:
            findings.append(
                f"a check row with {len(cells)} cell(s) reads {cells}; every row states the "
                "check, what it asks and how"
            )
            continue
        name = bare(cells[0])
        stated.append(name)
        findings.extend(
            f"{name}: the page says to run python -m {module}, and no module of that name runs "
            "as a command"
            for module in RUNS_A_MODULE.findall(cells[2])
            if module not in runnable
        )
    required = [one.value for one in REQUIRED_CHECKS]
    if stated != required:
        findings.append(
            f"the page lists the checks {stated} and a drill verifies only on {required}, in "
            "that order, so a runner following the page writes a record that cannot verify"
        )
    return tuple(findings)


def _drill_field_gaps(page: str) -> tuple[str, ...]:
    """Every field a drill record and each of its checks must carry, in both directions."""
    declared = [(name, ON_THE_RECORD) for name in DRILL_REQUIRED_FIELDS] + [
        (name, ON_EACH_CHECK) for name in CHECK_REQUIRED_FIELDS
    ]
    findings: list[str] = []
    stated: list[tuple[str, str]] = []
    for cells in table_after(page, DRILL_FIELDS_MARKER):
        if len(cells) < 2:
            findings.append(
                f"a field row with {len(cells)} cell(s) reads {cells}; every row states the "
                "field and where it sits"
            )
            continue
        stated.append((bare(cells[0]), bare(cells[1])))
    findings.extend(
        f"{name} on {where}: a drill record is refused without it and the page does not ask for it"
        for name, where in declared
        if (name, where) not in stated
    )
    findings.extend(
        f"{name} on {where}: the page asks for a field no reader reads, so a runner writes it "
        "and nothing believes it"
        for name, where in stated
        if (name, where) not in declared
    )
    return tuple(findings)


def _stated_gaps(
    page: str, marker: str, declared: Mapping[str, str], *, noun: str
) -> tuple[str, ...]:
    """A two-column table of names and values against the declared ones, in both directions."""
    findings: list[str] = []
    stated: dict[str, str] = {}
    for cells in table_after(page, marker):
        if len(cells) < 2:
            findings.append(f"a {noun} row with {len(cells)} cell(s) reads {cells}")
            continue
        stated[bare(cells[0])] = bare(cells[1])
    findings.extend(
        f"{name}: the page does not state this {noun}" for name in declared if name not in stated
    )
    findings.extend(
        f"{name}: a {noun} nothing here declares, which reads as one it does"
        for name in stated
        if name not in declared
    )
    findings.extend(
        f"{name}: the page says {stated[name]!r} and the repository says {declared[name]!r}"
        for name in declared
        if name in stated and stated[name] != declared[name]
    )
    return tuple(findings)


def _drill_example_gaps(page: str) -> tuple[str, ...]:
    """The three worked examples, read by the product's own readers and judged by its verdict."""
    findings: list[str] = []
    copy: Backup | None = None
    try:
        copy = backup_from(
            json_after(page, DRILL_COPY_EXAMPLE_MARKER), where="the example manifest"
        )
    except (InstallDocsError, ManifestError) as exc:
        findings.append(str(exc))
    for marker, label, verifies in (
        (DRILL_PASSING_EXAMPLE_MARKER, "the drill record that verifies", True),
        (DRILL_FAILING_EXAMPLE_MARKER, "the drill record that does not verify", False),
    ):
        try:
            document = json_after(page, marker)
        except InstallDocsError as exc:
            findings.append(str(exc))
            continue
        # Through the bucket reader, named as a record in a bucket would be, so the example is
        # judged by exactly the path a record uploaded in step 9 takes.
        verifications, unreadable = read_drills([(EXAMPLE_RECORD, json.dumps(document))])
        if unreadable:
            findings.extend(f"{label}: {one.why}" for one in unreadable)
            continue
        (verdict,) = verifications
        if verdict.verified is not verifies:
            findings.append(
                f"{label}: the product reads it as "
                f"{'verified' if verdict.verified else 'not verified'}"
                f"{''.join(f'; {one}' for one in verdict.shortfalls)}"
            )
        if copy is None:
            continue
        if verdict.backup_id != copy.backup_id:
            findings.append(
                f"{label}: reads {verdict.backup_id!r} and the example manifest describes "
                f"{copy.backup_id!r}"
            )
        if verdict.attempted_at < copy.recoverable_to:
            findings.append(
                f"{label}: starts before the copy it reads was consistent, which is a drill of a "
                "copy that did not exist yet"
            )
    return tuple(findings)


# ------------------------------------------------ the administrative consoles (M37.6.1.3)
#: The decision the network page records, and why it is two protections and not one.
A_PUBLIC_CONSOLE_NEEDS_A_SECOND_FACTOR_AND_AN_ALLOWLIST: Final = (
    "The administrative consoles stay on public addresses rather than behind an SSH tunnel, so "
    "that an administrator with no SSH habit can reach them. That leaves the most powerful "
    "sign-in pages on the server answering from the internet, and the decision holds only while "
    "every one of them carries both protections: a second factor, so a guessed or leaked "
    "password is not enough on its own, and an IP allowlist, so the sign-in page is not offered "
    "to the whole internet to be guessed at. A console with one of the two fails on the day that "
    "one does, which is the exposure the tunnel would have removed and this decision accepted."
)

#: The consoles the decision covers, named for what they control rather than by product, in the
#: order the network page lists them. The console staff use and the identity provider's sign-in
#: page are not among them: those have to answer the people who use them.
ADMINISTRATIVE_CONSOLES: Final = (
    "deployment panel",
    "identity provider admin console",
    "secrets vault interface",
    "trace ledger dashboard",
)

#: The options considered and not taken. A decision written down without them is one the next
#: reader reopens, because the argument against the alternative is the half that gets lost.
REJECTED_CONSOLE_OPTIONS: Final = (
    "an SSH tunnel on every install",
    "a choice made per client",
)

#: Where the network page lists the consoles.
CONSOLES_MARKER: Final = "<!-- checked: the administrative consoles -->"

#: Where the network page lists the options that were rejected.
REJECTED_CONSOLES_MARKER: Final = "<!-- checked: the options rejected for the consoles -->"

#: The proxy middleware carrying the allowlist, by the name `ops/vps/traefik-coolify-panel.yaml`
#: gives it. The page names it and the template defines it, and the checks hold the two equal.
ALLOWLIST_MIDDLEWARE: Final = "admin-allowlist"

#: How a console row's last cell opens when this product does not serve that console at all.
NOT_SERVED: Final = "Not served"

#: Cells that say a protection is absent rather than how it is provided.
ABSENT: Final = frozenset({"", "none", "no", "nothing", "n/a"})

#: One `ui` setting in an OpenBao configuration.
VAULT_UI_SETTING: Final = re.compile(r"^\s*ui\s*=\s*(true|false)\s*$", re.M)


def console_gaps(guide: str, *, vault_served: bool) -> tuple[str, ...]:
    """Every way the network page has stopped recording the console decision M37.6.1.3 asks for.

    The four consoles by name in both directions; a second factor and an allowlist stated for
    every one; the panel's allowlist named as the middleware its proxy template defines; the
    vault's row saying it is not served exactly when its interface is off; and the two rejected
    options in both directions, each with its reason.

    `vault_served` is read out of the vault's compose file by the caller, for the split this
    module keeps: the page is text, and the compose file is somebody else's parse.
    """
    findings: list[str] = []
    named: list[str] = []
    for cells in table_after(guide, CONSOLES_MARKER):
        if len(cells) < 5:
            findings.append(
                f"a row with {len(cells)} cell(s) reads {cells}; every row states the console, "
                "what it hands over, its second factor, its allowlist and what this repository "
                "configures"
            )
            continue
        name = bare(cells[0])
        named.append(name)
        if bare(cells[2]).lower() in ABSENT:
            findings.append(f"{name}: no second factor, and the decision requires one")
        if bare(cells[3]).lower() in ABSENT:
            findings.append(f"{name}: no IP allowlist, and the decision requires one")
        if name == ADMINISTRATIVE_CONSOLES[0] and f"`{ALLOWLIST_MIDDLEWARE}`" not in cells[3]:
            findings.append(
                f"{name}: the allowlist cell does not name `{ALLOWLIST_MIDDLEWARE}`, the "
                "middleware its proxy template defines"
            )
        if name == ADMINISTRATIVE_CONSOLES[2] and cells[4].startswith(NOT_SERVED) == vault_served:
            state = "on" if vault_served else "off"
            findings.append(
                f"{name}: the vault's compose file switches its interface {state} and the "
                "page says otherwise"
            )
    findings.extend(
        f"{name!r}: a console the decision covers and the page does not list"
        for name in ADMINISTRATIVE_CONSOLES
        if name not in named
    )
    findings.extend(
        f"{name!r}: a console the page lists and the decision does not cover, which reads as "
        "coverage"
        for name in named
        if name not in ADMINISTRATIVE_CONSOLES
    )
    rejected: list[str] = []
    for cells in table_after(guide, REJECTED_CONSOLES_MARKER):
        if len(cells) < 2 or not bare(cells[1]):
            findings.append(
                f"a rejected option reads {cells}; every row states the option and why it was "
                "not taken"
            )
            continue
        rejected.append(bare(cells[0]))
    findings.extend(
        f"{option!r}: an option that was rejected and the page does not record"
        for option in REJECTED_CONSOLE_OPTIONS
        if option not in rejected
    )
    findings.extend(
        f"{option!r}: a rejected option the decision never considered"
        for option in rejected
        if option not in REJECTED_CONSOLE_OPTIONS
    )
    return tuple(findings)


def panel_allowlist_gaps(route: Mapping[str, Any]) -> tuple[str, ...]:
    """Every way the deployment panel's proxy template lets a request past without the allowlist.

    `route` is `ops/vps/traefik-coolify-panel.yaml`, parsed by the caller. The middleware has to
    exist, be an allowlist, and name at least one range; and every router has to pass it first,
    so nothing on the route, not even the redirect to HTTPS, answers an address it refuses.
    """
    http = route.get("http")
    if not isinstance(http, Mapping):
        msg = "the panel template has no http section, so there is no route to check"
        raise InstallDocsError(msg)
    findings: list[str] = []
    middleware = (http.get("middlewares") or {}).get(ALLOWLIST_MIDDLEWARE)
    allow = middleware.get("ipAllowList") if isinstance(middleware, Mapping) else None
    if not isinstance(allow, Mapping) or not allow.get("sourceRange"):
        findings.append(
            f"{ALLOWLIST_MIDDLEWARE}: not defined as an ipAllowList with a sourceRange, so a "
            "router naming it restricts nothing"
        )
    routers = http.get("routers") or {}
    if not routers:
        findings.append("the panel template defines no router, so the allowlist guards nothing")
    for name, router in sorted(routers.items()):
        chain = list(router.get("middlewares") or ()) if isinstance(router, Mapping) else []
        if chain[:1] != [ALLOWLIST_MIDDLEWARE]:
            findings.append(
                f"{name}: answers before {ALLOWLIST_MIDDLEWARE} is consulted, so the panel is "
                "reachable from any address on this route"
            )
    return tuple(findings)


def vault_interface_served(compose: Mapping[str, Any]) -> bool:
    """Whether the vault's compose file switches its web interface on.

    Read from the configuration the container starts with. A configuration that sets no `ui`
    leaves the interface off, which is the server's own default. A compose file with no vault
    configuration in it is refused rather than answered: "off" for a file whose configuration
    has moved would be the check agreeing with the page about a setting it never read.
    """
    try:
        config = compose["services"]["vault"]["environment"]["BAO_LOCAL_CONFIG"]
    except (KeyError, TypeError) as exc:
        msg = "the vault compose file carries no BAO_LOCAL_CONFIG, so its interface is unread"
        raise InstallDocsError(msg) from exc
    if not isinstance(config, str):
        msg = f"the vault's BAO_LOCAL_CONFIG is a {type(config).__name__}, not a configuration"
        raise InstallDocsError(msg)
    found = VAULT_UI_SETTING.findall(config)
    return bool(found) and found[-1] == "true"


# ------------------------------------------------------------- the threat model (M38.5.2)
SURFACES_MARKER: Final = "<!-- checked: every exposed surface -->"

#: A code span in a table cell, which is how a surface is named in the threat model.
_CODE_SPAN: Final = re.compile(r"`([^`]+)`")


def first_segment(path: str) -> str:
    """`/api/status.json` is `/api`, and the root is `/`: the unit the threat model has rows for."""
    head = path.lstrip("/").split("/", 1)[0]
    return f"/{head}"


def threat_model_gaps(
    guide: str, *, served: Collection[str], reachable: Collection[str]
) -> tuple[str, ...]:
    """Surfaces an install exposes that the threat model has no row for, and paths it invents.

    `served` is every path the application routes and `reachable` every service a compose file
    publishes a port for or the network guide sends a browser to. A surface with no row is one
    nobody argued about. Only paths are checked the other way: rows like `ssh` or `outbound
    calls` name surfaces no register in this repository declares, and are prose.
    """
    rows: set[str] = set()
    for cells in table_after(guide, SURFACES_MARKER):
        rows.update(one.strip() for one in _CODE_SPAN.findall(cells[0]))
    segments = {first_segment(one) for one in served}
    stated_paths = {one for one in rows if one.startswith("/")}
    findings = [
        f"{one}: the application serves it and the threat model has no row for it"
        for one in sorted(segments - stated_paths)
    ]
    findings.extend(
        f"{one}: a row for a path the application does not serve, which reads as a surface "
        "somebody is still defending"
        for one in sorted(stated_paths - segments)
    )
    findings.extend(
        f"{one}: reachable from outside the compose network and the threat model has no row for it"
        for one in sorted(set(reachable) - rows)
    )
    return tuple(findings)
