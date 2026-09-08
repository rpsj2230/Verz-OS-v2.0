"""Every extension point this platform has, and which of the three answers it takes.

CLAUDE.md's third rule is the one this module is written against, and it is worth quoting
because the whole register is a reading of it: "When something cannot be configured, that is
a defect in the extension points. The answer is never a branch for one company or a copy of
this repository. `M29` holds the plugin interfaces; a company-specific connector is a plugin,
and a genuinely new feature goes into this repository behind a flag and ships to everyone
switched off."

**That sentence names three answers, not one, and the register's job is to say which answer
each point takes.** A module elsewhere refusing a company-specific request points at M29, and
the reader assumes "plugin". For seven of the sixteen points that is right. For three of them
the honest answer is one of the other two, and for six there is no answer yet because there is
no contract to plug into. A register that recorded only the seven would be the promise being
kept on paper: every refusal elsewhere would still read as satisfied, and the six with nothing
behind them would be invisible.

**The interfaces are not written here and that is deliberate.** Ten of them already exist, in
the modules that own them, tested there: `ChannelAdapter` in `brain.channels.adapter`,
`StorageBackend` in `brain.ops.storage`, `ModelDriver` in `brain.models.driver`, and so on.
Rewriting them under `brain.plugins` would be sixteen second implementations of contracts the
repository already has, which is the failure `tests/invariants/test_single_implementation.py`
exists to catch and which every module docstring in this tree argues against. So a point names
its contract as `module:Symbol` and `contract_gaps` reads the source to check the symbol is
really there. A register that could name a protocol nobody wrote is a register that describes
an intention.

Rejected: writing the six missing protocols anyway, so that all sixteen leaves could be closed
together. `brain.ops.automation_piece` names the cost of that exactly once and it is the right
name for it: a file here would be "the seventh mechanism in this tree that nothing calls".
Six protocols with no implementation, no caller and no test would make the register complete
and make it a worse document, because `Answer.UNDECIDED` is information and a protocol nobody
implements is not.

**Two structural rules about isolation, and they are the ones that make the tier mean
something.** A point that takes code may not run in this process: a signature check stops a
plugin being *handed* something, never from importing the vault client and reading it, and
`brain.ops.automation` is already explicit that code from outside the company's review is
treated as hostile. A point that takes data may run nowhere else: a sidecar for a manifest is
a container whose only job is to parse, and the parser is the isolation.

**A point that is not a plugin has no tier, no direction and carries nothing.** There is no
third party to isolate, so a tier on it would be a number somebody would later read as a
promise that a plugin may run there. The three fields are set together or not at all.

**Three leaves are decided here and deliberately not claimed**, and the reason is that
closing them would make the tracker say the opposite of what the register found. M29.1.11,
M29.1.13 and M29.1.16 are the storage backend, the identity provider and the scope pack, and
all three are recorded below with a contract, an answer and an argument. Closing them under a
module named "Extension points" would tell a reader of the tracker that a plugin is possible
at each, when the whole content of those three entries is that it is not. The tracker
over-reporting is the failure worth avoiding, so the ids are absent from the lines below and
this paragraph is where the work is recorded instead. Six more leaves are `UNDECIDED` and are
not claimed for the ordinary reason: there is nothing behind them yet.

Task ids: M29.1.1, M29.1.2, M29.1.3, M29.1.4, M29.1.5, M29.1.7, M29.1.12
Task ids: M29.2.5
"""

from __future__ import annotations

import ast
import enum
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: A point's name, and the same shape a capability noun takes.
POINT_NAME_RE: Final = re.compile(r"^[a-z][a-z0-9_]*$")

#: The leaf a point serves. Every one of them is under M29's first task group.
POINT_LEAF_RE: Final = re.compile(r"^M29\.1\.\d+$")

#: `module.path:Symbol`, which is how an entry point is spelled everywhere else in Python.
CONTRACT_RE: Final = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*$")


class PointError(Exception):
    """An extension point was declared in a way that would mislead whoever reads the register.

    Outside the user-facing taxonomy in `brain.core.errors`, for the reason
    `brain.tools.skills.SkillError` gives about its own: nobody asking a question ever sees
    this. It is a contract violation by whoever edited the register, and it belongs in front
    of them.
    """


class Answer(enum.StrEnum):
    """Which of CLAUDE.md's three answers a point takes, plus the absence of one.

    `UNDECIDED` is not a fourth answer and must not read as one. It says the point has no
    contract in this repository and nobody has decided whether a third party may supply one.
    It exists so the gap is countable rather than invisible, which is the same move
    `brain.ops.export.export_gaps` and `brain.ops.halt.halt_gaps` make about their own.
    """

    #: A third party supplies it. CLAUDE.md's "a company-specific connector is a plugin".
    PLUGIN = "plugin"
    #: It goes into this repository behind a flag and ships to everyone switched off.
    FLAG = "flag"
    #: It is a value somebody sets during setup, read through `brain.install.value_of`.
    CONFIGURATION = "configuration"
    #: No contract, and no decision. See the class docstring.
    UNDECIDED = "undecided"


class Direction(enum.StrEnum):
    """Which way data crosses a point, which is what decides the contract test.

    The distinction is the whole of "cannot see an unredacted result it did not produce". A
    connector produces raw records and the redactor runs downstream of it, which
    `brain.connectors.__init__` already states as the reason a connector holds no permission
    logic. A notification sink is handed an answer the gate has already walked. The first may
    return an unredacted type and the second may not, and neither may accept one.
    """

    #: Raw records enter the system here. What it returns has not been redacted yet.
    PRODUCES = "produces"
    #: An answer leaves the system here. What it is handed has been redacted already.
    CONSUMES = "consumes"
    #: Neither. The plugin contributes a declaration and touches no record at all.
    DECLARES = "declares"


class Carries(enum.StrEnum):
    """Whether a plugin at this point is code or data, which is what decides the tier."""

    CODE = "code"
    DATA = "data"


class IsolationTier(enum.StrEnum):
    """Where a plugin at this point runs (M29.2.5).

    Ordered from most trusting to least, and named as the leaf names them. The tier belongs
    to the point rather than to the plugin, for the reason `brain.tools.skills` gives about a
    skill declaring its own capability: a plugin choosing its own isolation is a plugin
    granting itself something, and the review that was meant to catch it would be reviewing
    a manifest written by whoever it is meant to constrain.
    """

    #: The application process. Available only to a point that takes data.
    IN_PROCESS = "in_process"
    #: A container on the internal network, reachable over the tool API and nothing else.
    SIDECAR = "sidecar"
    #: A container with no network and no credential. `brain.tools.run_skill` describes one.
    SANDBOX = "sandbox"


#: Why a plugin may not choose where it runs.
A_TIER_BELONGS_TO_THE_POINT_AND_NEVER_TO_THE_PLUGIN: Final = (
    "A plugin that declares its own isolation tier has granted itself the difference between "
    "a sandbox and this process, and the review meant to catch that would be reading a file "
    "written by the party it is meant to constrain. The tier is a property of what the point "
    "hands over, which is known before any plugin exists, so it is declared here once."
)

#: Why code from outside never runs in this process.
CODE_IN_THIS_PROCESS_IS_INSIDE_EVERY_GUARD_AT_ONCE: Final = (
    "A signature check stops a plugin being handed the trace; it does nothing about a plugin "
    "that imports the vault client, opens a socket or reads the entitlement store, because "
    "in-process code is on the inside of every guard this repository has. brain.ops.automation "
    "already treats flows written by the client's own staff as hostile for the same reason. So "
    "a point that takes code runs in a sidecar or a sandbox, and IN_PROCESS is reserved for "
    "data, where the parser is the isolation."
)

#: Why the register does not write the six protocols that are missing.
A_PROTOCOL_NOTHING_IMPLEMENTS_MAKES_THE_REGISTER_COMPLETE_AND_WORSE: Final = (
    "Six of the sixteen points name an interface no module in this repository defines. "
    "Writing them here would close six leaves and produce six files nothing calls, nothing "
    "type-checks against and nothing tests, which is the state brain.ops.automation_piece "
    "refuses for the TypeScript piece in those words. UNDECIDED is information; a protocol "
    "with no implementation is a claim that the point is available when it is not."
)


@dataclass(frozen=True)
class ExtensionPoint:
    """One place a company's own behaviour can enter, and on what terms.

    `why` is required prose and is not decoration. It is the argument a reader needs when a
    module elsewhere refuses a company-specific request and sends them here, and a point
    nobody can explain is one somebody will reclassify as a plugin the first time a client
    asks. `brain.install.Setting` requires the same thing of an installation value and for
    the same reason.
    """

    #: What the point is called.
    name: str
    #: The M29.1.x leaf it serves.
    leaf: str
    #: Which of the three answers this point takes. See `Answer`.
    answer: Answer
    #: Why it takes that answer, for whoever was sent here by a refusal elsewhere.
    why: str
    #: `module:Symbol` naming the contract, checked by `contract_gaps`. Empty when there is none.
    contract: str = ""
    #: Which way data crosses. Set for a plugin point and None otherwise.
    direction: Direction | None = None
    #: Code or data. Set for a plugin point and None otherwise.
    carries: Carries | None = None
    #: Where a plugin runs. Set for a plugin point and None otherwise.
    tier: IsolationTier | None = None

    def __post_init__(self) -> None:
        if not POINT_NAME_RE.match(self.name):
            msg = f"{self.name!r} is not an extension point name"
            raise PointError(msg)
        if not POINT_LEAF_RE.match(self.leaf):
            msg = (
                f"{self.name} claims {self.leaf!r}, which is not one of M29's interface "
                "leaves; a point claiming a leaf that does not exist is a claim the "
                "traceability sweep credits to nothing"
            )
            raise PointError(msg)
        if not self.why.strip():
            msg = (
                f"{self.name} has no reason written down, and a point nobody can explain is "
                "one somebody reclassifies as a plugin the first time a client asks"
            )
            raise PointError(msg)
        if self.contract and not CONTRACT_RE.match(self.contract):
            msg = (
                f"{self.name} names {self.contract!r} as its contract, which is not "
                "module.path:Symbol, so contract_gaps cannot check that it exists"
            )
            raise PointError(msg)
        self._assert_the_terms_are_set_together()
        self._assert_isolation_matches_what_is_carried()

    def _assert_the_terms_are_set_together(self) -> None:
        """A plugin point states all four terms; every other point states none of them.

        Half a declaration is worse than none. A tier on a point nobody may supply reads as a
        promise that somebody may, and a plugin point with no tier is the case where the
        default gets chosen by whoever wires it up first.
        """
        terms = (self.direction, self.carries, self.tier)
        if self.answer is Answer.PLUGIN:
            if not self.contract:
                msg = (
                    f"{self.name} is declared a plugin point with no contract; there is "
                    "nothing to plug into, and the refusals elsewhere that send a reader "
                    "here would be pointing at an interface that does not exist"
                )
                raise PointError(msg)
            if any(one is None for one in terms):
                msg = (
                    f"{self.name} is a plugin point missing its direction, what it carries "
                    "or its tier; whichever is unset gets decided by whoever wires it up"
                )
                raise PointError(msg)
            return
        if any(one is not None for one in terms):
            msg = (
                f"{self.name} is not a plugin point but states a direction, a tier or what "
                "it carries; there is no third party to isolate and the terms read as a "
                "promise that one may supply it"
            )
            raise PointError(msg)
        if self.answer is Answer.UNDECIDED and self.contract:
            msg = (
                f"{self.name} is undecided and names {self.contract!r}; a contract exists, "
                "so the open question is which answer the point takes rather than whether "
                "there is anything to plug into"
            )
            raise PointError(msg)

    def _assert_isolation_matches_what_is_carried(self) -> None:
        """Code never runs in this process, and data runs nowhere else.

        See `CODE_IN_THIS_PROCESS_IS_INSIDE_EVERY_GUARD_AT_ONCE` for the first half. The
        second is the cheaper claim and still worth refusing: a sidecar whose whole job is to
        parse a manifest is a container to operate, a network to allow and a version to
        upgrade, in exchange for isolating a value that a parser in this process has already
        validated.
        """
        if self.carries is Carries.CODE and self.tier is IsolationTier.IN_PROCESS:
            msg = (
                f"{self.name} takes code and would run in this process, which is inside every "
                "guard at once; see CODE_IN_THIS_PROCESS_IS_INSIDE_EVERY_GUARD_AT_ONCE"
            )
            raise PointError(msg)
        if self.carries is Carries.DATA and self.tier is not IsolationTier.IN_PROCESS:
            msg = (
                f"{self.name} takes data and would run in a container; the parser is the "
                "isolation, and a sidecar for a manifest is one more thing to operate"
            )
            raise PointError(msg)


#: Every extension point M29 names, in leaf order.
#:
#: Seven take a plugin, two are configuration, one is a flag in this repository, and six have
#: no contract and no decision. That distribution is the finding rather than a shortfall: the
#: promise the rest of the repository makes on M29's behalf is kept for the seven, kept by a
#: different clause of the same sentence for the three, and not yet kept at all for the six.
POINTS: Final[tuple[ExtensionPoint, ...]] = (
    ExtensionPoint(
        name="channel_adapter",
        leaf="M29.1.1",
        answer=Answer.PLUGIN,
        contract="brain.channels.adapter:ChannelAdapter",
        direction=Direction.CONSUMES,
        carries=Carries.CODE,
        tier=IsolationTier.SIDECAR,
        why=(
            "A company reaches this system through the surfaces it already runs, and its own "
            "intranet or helpdesk is not a surface this repository will ever ship. The "
            "adapters that are shipped are not plugins: they are in this repository, tested "
            "here, and registered in process. A client's own is a sidecar, because it is code "
            "from outside the review."
        ),
    ),
    ExtensionPoint(
        name="connector",
        leaf="M29.1.2",
        answer=Answer.PLUGIN,
        contract="brain.connectors.contract:ConnectorFetch",
        direction=Direction.PRODUCES,
        carries=Carries.CODE,
        tier=IsolationTier.SIDECAR,
        why=(
            "CLAUDE.md's own example of a plugin. A connector returns everything it fetched "
            "and decides nothing about who may see it, which is what makes it safe to take "
            "from outside. What it may not decide is the projection's visibility predicate: "
            "see A_CONNECTOR_PLUGIN_STILL_CANNOT_BE_HANDED_THE_VISIBILITY_PREDICATE."
        ),
    ),
    ExtensionPoint(
        name="skill",
        leaf="M29.1.3",
        answer=Answer.PLUGIN,
        contract="brain.tools.skills:Skill",
        direction=Direction.DECLARES,
        carries=Carries.CODE,
        tier=IsolationTier.SANDBOX,
        why=(
            "Already the most worked-out extension point here, and the one whose rules the "
            "rest of this package copies. A skill names tools and can hold no capability, no "
            "grant, no scope and no rung, because brain.tools.skills has no field for one. "
            "Its scripts run in the sandbox brain.tools.run_skill describes."
        ),
    ),
    ExtensionPoint(
        name="template",
        leaf="M29.1.4",
        answer=Answer.PLUGIN,
        contract="brain.agents.template:TemplateManifest",
        direction=Direction.DECLARES,
        carries=Carries.DATA,
        tier=IsolationTier.IN_PROCESS,
        why=(
            "A template is a manifest and not a program, so the parser is the isolation and a "
            "container around it would isolate nothing. M13.6 is where a client's own "
            "templates get a real author; the catalogue in this repository is the house's."
        ),
    ),
    ExtensionPoint(
        name="model_provider",
        leaf="M29.1.5",
        answer=Answer.PLUGIN,
        contract="brain.models.driver:ModelDriver",
        direction=Direction.CONSUMES,
        carries=Carries.CODE,
        tier=IsolationTier.SIDECAR,
        why=(
            "A provider is already a network service, so a sidecar costs nothing that is not "
            "being paid anyway. INSTALL_MODEL_PROFILE decides whether an external provider "
            "may be reached at all, and it defaults to local: a client who has not chosen to "
            "send text off their own hardware has not chosen it."
        ),
    ),
    ExtensionPoint(
        name="retriever",
        leaf="M29.1.6",
        answer=Answer.UNDECIDED,
        why=(
            "No module defines a retriever contract. brain.knowledge.search holds the reach "
            "predicate and the SQL, brain.knowledge.fusion holds the ranking arithmetic, and "
            "neither is a seam a third party could sit in. The open question is whether a "
            "retriever may be replaced at all, given that the reach predicate is the thing "
            "deciding which rows exist for this caller."
        ),
    ),
    ExtensionPoint(
        name="field_classifier",
        leaf="M29.1.7",
        answer=Answer.PLUGIN,
        contract="brain.ops.pii:Recogniser",
        direction=Direction.PRODUCES,
        carries=Carries.CODE,
        tier=IsolationTier.SANDBOX,
        why=(
            "A recogniser proposes and brain.core.field_policy decides, and the split is the "
            "whole reason this one can be a plugin. A classifier that could decide would be a "
            "second source of policy able to call a confidential field public. It reads every "
            "value it classifies, which is why the tier is the sandbox rather than the "
            "sidecar: no network is the only thing standing between a regex and an exfiltration."
        ),
    ),
    ExtensionPoint(
        name="entity_resolver",
        leaf="M29.1.8",
        answer=Answer.UNDECIDED,
        why=(
            "brain.resolution has a cascade, a weight table and thresholds, and no seam. The "
            "open question is narrower than it looks: a resolver decides that two records are "
            "one company, and a wrong merge joins two clients' rows under one canonical id, "
            "which is a disclosure rather than a bad answer."
        ),
    ),
    ExtensionPoint(
        name="verifier",
        leaf="M29.1.9",
        answer=Answer.UNDECIDED,
        why=(
            "brain.knowledge.verification decides who may be told who verified an item and "
            "when a badge is disclosed. There is no contract for the act of verifying, and "
            "whether an outside party may perform it is a question about who the company "
            "stands behind rather than about an interface."
        ),
    ),
    ExtensionPoint(
        name="guard",
        leaf="M29.1.10",
        answer=Answer.UNDECIDED,
        why=(
            "The guards are spread across brain.gate.injection, brain.gate.abstain and the "
            "leash's own checks, and none of them is a named contract. A guard that could be "
            "supplied from outside could also be supplied as one that passes everything, so "
            "the decision needed first is whether a plugin guard may ever replace a shipped "
            "one or only run in addition to it."
        ),
    ),
    ExtensionPoint(
        name="storage_backend",
        leaf="M29.1.11",
        answer=Answer.FLAG,
        contract="brain.ops.storage:StorageBackend",
        why=(
            "The one point where the tracker asked for a plugin and the module refused in "
            "writing. brain.ops.storage argues that files are not optional to this platform "
            "and that brain.ext is where 'must work' stops being true, so the protocol lives "
            "in code that is tested here. A fourth backend is CLAUDE.md's other clause: it "
            "goes into this repository behind a flag and ships to everyone switched off."
        ),
    ),
    ExtensionPoint(
        name="notification_sink",
        leaf="M29.1.12",
        answer=Answer.PLUGIN,
        contract="brain.ops.digest_delivery:DigestSender",
        direction=Direction.CONSUMES,
        carries=Carries.CODE,
        tier=IsolationTier.SIDECAR,
        why=(
            "Where a company's messages go is a company's own decision and the list of places "
            "is open. A sink is handed what a channel is handed, which is why it is the "
            "cleanest plugin point of the seven: there is nothing in a ChannelPayload that "
            "the gate has not already walked."
        ),
    ),
    ExtensionPoint(
        name="identity_provider",
        leaf="M29.1.13",
        answer=Answer.CONFIGURATION,
        contract="brain.identity.staff_source:StaffSource",
        why=(
            "Refused as a plugin rather than unbuilt. An identity provider supplies "
            "principals, and a principal is where every grant in the system hangs from, so a "
            "provider from outside is a second source of grants wearing a directory's "
            "clothes. INSTALL_BROKERED_DIRECTORY already makes this a value somebody sets, "
            "and Keycloak brokers the rest."
        ),
    ),
    ExtensionPoint(
        name="approver_surface",
        leaf="M29.1.14",
        answer=Answer.UNDECIDED,
        why=(
            "brain.gate.leash suspends an action and brain.builder.publish counts approvers, "
            "and there is no contract for the surface a person approves on. The undecided "
            "part is not the interface: an approval is a person taking responsibility, and "
            "an outside surface would have to prove which person, which is the same question "
            "brain.ops.automation_piece leaves open about who a flow runs as."
        ),
    ),
    ExtensionPoint(
        name="export_format",
        leaf="M29.1.15",
        answer=Answer.UNDECIDED,
        why=(
            "The likeliest of the six to become a plugin and still not one today. "
            "brain.ops.export and brain.audit.export each render their own shape and neither "
            "declares a format seam. What a format plugin would need is the redacted answer "
            "and nothing else, which the contract test here already knows how to enforce."
        ),
    ),
    ExtensionPoint(
        name="scope_pack",
        leaf="M29.1.16",
        answer=Answer.CONFIGURATION,
        contract="brain.identity.packs:CapabilityPack",
        why=(
            "The sharpest refusal in this register. brain.identity.packs.expand turns a pack "
            "and an assignment into SubjectGrants, so a pack is a source of grants by "
            "definition, and entitlements here are additive with no deny list: nothing takes "
            "a grant back. A pack supplied from outside the company is the second source of "
            "grants the whole platform is built to not have."
        ),
    ),
)

#: The register, indexed. Built once because a point is looked up per request in a console view.
BY_NAME: Final[dict[str, ExtensionPoint]] = {one.name: one for one in POINTS}

#: What a connector plugin still may not be handed, recorded where the point is declared.
#:
#: `brain.connectors.manifest.ProjectedEntity` refuses an unrestricted visibility predicate and
#: refuses one enumerating principals, and both refusals are right. Neither refuses a predicate
#: that is restricted in shape and tautological in effect: a plugin that projects a field it
#: sets itself, and then names that field as the visibility predicate, has a projection every
#: guard passes and every row in it readable by anybody holding the entity's capability. That
#: is a widening that never touches an entitlement set, so nothing in this package sees it
#: either. The predicate is a client decision that belongs in front of a person.
A_CONNECTOR_PLUGIN_STILL_CANNOT_BE_HANDED_THE_VISIBILITY_PREDICATE: Final = (
    "ProjectedEntity refuses a visibility predicate that is unrestricted and one that "
    "enumerates principals, and a predicate can be neither of those and still admit every "
    "row: a field the plugin projects itself, compared against a value the plugin chooses. "
    "The connector point is a plugin for fetching. The predicate deciding who may read a "
    "projected row is not something a plugin supplies, because widening it needs no grant."
)


def point_named(name: str) -> ExtensionPoint | None:
    """The point with this name, or None.

    None rather than a raise, because the caller asking about a name is usually validating a
    manifest that arrived from outside and the absence is the answer rather than an error.
    """
    return BY_NAME.get(name)


def points_answering(answer: Answer) -> tuple[ExtensionPoint, ...]:
    """Every point taking one of the three answers, in leaf order."""
    return tuple(one for one in POINTS if one.answer is answer)


def _module_path(repo: Path, dotted: str) -> Path:
    """Where a dotted module lives, as either a module file or a package `__init__`."""
    parts = dotted.split(".")
    base = repo.joinpath("src", *parts)
    module = base.with_suffix(".py")
    return module if module.is_file() else base / "__init__.py"


def _defines(path: Path, symbol: str) -> bool:
    """True when the module defines this symbol at the top level, by any of the three means.

    Parsed rather than imported, and the difference matters twice. Importing runs module-level
    code, which a sweep must not do to sixteen modules to answer a question about names; and
    importing would count a symbol a module merely re-exports, which is not the same as owning
    the contract. A class, a function and an annotated assignment all count, because a protocol
    is usually a class and a contract is occasionally a callable alias.
    """
    if not path.is_file():
        return False
    tree = ast.parse(path.read_bytes().decode("utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name == symbol:
                return True
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == symbol:
                return True
        elif isinstance(node, ast.Assign) and any(
            isinstance(one, ast.Name) and one.id == symbol for one in node.targets
        ):
            return True
    return False


def contract_gaps(repo: Path, points: Sequence[ExtensionPoint] = POINTS) -> tuple[str, ...]:
    """Every point naming a contract that no module in this tree defines.

    **This is what stops the register describing an intention.** A point saying its contract
    is `brain.knowledge.search:Retriever` would read exactly like the ten that are real, and
    a reader sent here by a refusal elsewhere would go looking for a protocol nobody wrote.
    Checked against the source rather than against an import list, so renaming a protocol in
    the module that owns it fails here rather than at the first install.

    A point with no contract is not a gap of this kind. It is reported by `undecided_points`,
    which is a different question with a different answer.

    `points` is a parameter defaulting to the register, following `brain.ops.halt.halt_gaps`.
    A check that could only ever run over a module-level constant is a check whose refusing
    branch no test can reach until the constant happens to be wrong, which is the state that
    reads as covered and is not.
    """
    found: list[str] = []
    for one in points:
        if not one.contract:
            continue
        dotted, symbol = one.contract.split(":", 1)
        if not _defines(_module_path(repo, dotted), symbol):
            found.append(
                f"{one.name} ({one.leaf}) names {one.contract} and no module defines it, so "
                "the point describes an interface rather than naming one"
            )
    return tuple(found)


def undecided_points() -> tuple[str, ...]:
    """Every point with no contract and no decision, with the leaf it leaves open.

    Printed rather than raised, on the same grounds `brain.ops.sweeps.sweep_traceability`
    gives about its own notes: this is a backlog that predates the register, and a gate that
    is red the day it lands is a gate somebody switches off. It goes to zero by each point
    being decided, and until then the count is in front of whoever reads the register.
    """
    return tuple(
        f"{one.leaf} {one.name}: no contract in this repository and no decision about one"
        for one in POINTS
        if one.answer is Answer.UNDECIDED
    )
