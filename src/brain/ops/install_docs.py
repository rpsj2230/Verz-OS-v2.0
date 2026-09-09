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

Task ids: M42.2.3, M42.2.4, M42.2.5, M42.2.6, M42.2.8
"""

from __future__ import annotations

import ast
import enum
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from brain.connectors.manifest import ConnectorManifest
from brain.deployment.installer import Step as InstallStep
from brain.ops.controls import CONTROLS, Control
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
