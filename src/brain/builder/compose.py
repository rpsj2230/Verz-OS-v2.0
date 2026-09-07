"""What an author fills in, and the grammar a procedure may be drawn in.

Two surfaces with one rule between them. The form is where somebody says what an agent
should be; the canvas is where somebody draws what it should do. Both take typing from a
person and turn it into something that will later run against real rows, and both are
therefore places where a thing said can be mistaken for a thing decided.

**An authored list is intent, and the manifest is the authority** (M20.1.5). A form posts
whatever the browser sent, so a capability list arriving from one is a statement about what
somebody wanted, and storing it as the agent's authority makes the form the grant path. The
server therefore derives the authority from the tools that were chosen, through
`brain.tools.registry.capability_for`, and reports the difference rather than honouring it.
`Draft.requested` is named for what it is, and `authorisation_shaped_fields` refuses a field
on any of these types that would let the two be confused. See
`AN_AUTHORED_LIST_IS_INTENT_AND_THE_TOOLS_ARE_THE_AUTHORITY`.

**Seven sections, and every manifest path lands in exactly one** (M20.1.1). The sectioning is
the part of a form that is a decision rather than a rendering: which question a person is
answering when they meet a field. A path in no section is a field nobody can edit and nobody
reviews, and it goes missing without anything failing, which is why `SECTION_OF_PATH` is held
against `brain.agents.template.MANIFEST_PATHS` by `compose_gaps` rather than by a reader.

**The work breakdown's seven sections name no model section**, and `tier` is the path that
exposes it. It is filed under the persona with the argument stated at `SECTION_OF_PATH`,
because a tier is a statement about how an agent thinks rather than about what it may reach.
That is a decision recorded rather than a path quietly left out.

**Five node kinds, and a scope predicate is the only conditional** (M20.2.3). A procedure
canvas that could branch on anything else is a small programming language, and a small
programming language on a drawing surface is a second runtime with no gate in front of it,
which is the argument `brain.ops.automation` makes at length about the same shape. A `Scope`
is conjunction-only with no NOT and no OR, so the conditional grammar cannot express anything
that widens; `Node` refuses a predicate on any kind but `BRANCH`, so there is nowhere else for
a condition to live.

**There is no code node and the vocabulary is the enforcement** (M20.2.4). Two doors, because
either alone is open. `assert_drawable` refuses a node whose kind is not one of the five,
which is what a canvas outside this repository sends; and it refuses a node carrying a field
from `NAMES_THAT_WOULD_BE_A_CODE_NODE`, because a script attached to a node called `tool_call`
is a code node wearing a permitted name. `code_node_fields` asks the same of the type, so an
edit adding the field is caught rather than an edit adding the kind.

**Rejected: a validator that read a deny list of dangerous node kinds.** It is the obvious
design and it is the wrong way round. A deny list has to anticipate what somebody will draw,
and the canvas ships on its own release schedule; a closed vocabulary refuses everything it
was not told about, which includes the thing nobody thought of.

**Rejected: emitting the SKILL.md here.** M20.2.2 asks for a bounded canvas that outputs one,
and the output is the half that would be easy to write. It is not claimed, because a document
emitted from a graph nobody can draw is a serialiser for an absent surface, and the leaf asks
for both. Edges are absent for the same reason: a node set with no edges is a vocabulary, and
the connecting is the canvas.

Scope: domain logic. Nothing here opens a connection, renders anything or reads a clock.

**This declares the sections and builds no form.** M20.1.2 is the form generated from the
manifest JSON Schema through a JavaScript library, M20.1.3 is a co-author that needs a model
lane nothing in this repository assembles, and M20.1.4 is a draft store. None is claimed and
none is here.

Task ids: M20.1.1, M20.1.5, M20.2.3, M20.2.4
"""

from __future__ import annotations

import enum
import inspect
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.agents.template import MANIFEST_PATHS
from brain.core.entitlement import Capability
from brain.core.envelope import ToolDefinition
from brain.core.scope import Scope
from brain.tools.registry import capability_for

# ------------------------------------------------------------------ written-down reasons
#: Why the capability list a form posts is not the capability list an agent gets.
AN_AUTHORED_LIST_IS_INTENT_AND_THE_TOOLS_ARE_THE_AUTHORITY: Final = (
    "A form posts what the browser sent, so a capability list arriving from one says what "
    "somebody wanted rather than what anybody decided. Stored as the agent's authority it "
    "makes the composer the grant path, reviewed by whoever was designing an agent rather "
    "than by whoever reviews grants. The authority is therefore derived from the tools that "
    "were chosen, by the same capability_for the tool registry uses, and a capability no "
    "chosen tool requires is reported to the author rather than carried into the manifest."
)

#: Why the sectioning is checked against the manifest rather than read.
A_PATH_IN_NO_SECTION_IS_A_FIELD_NOBODY_EDITS_AND_NOBODY_REVIEWS: Final = (
    "A section is where a person meets a field, so a manifest path in no section is a field "
    "the form never shows: it keeps whatever the template set, nobody is asked about it, and "
    "nobody reviewing the agent sees it. That failure is silent, which is why the sections "
    "are held against MANIFEST_PATHS by a check rather than by whoever adds the next path."
)

#: Why a branch may only test a scope predicate.
A_CONDITIONAL_THAT_IS_NOT_A_SCOPE_IS_A_SMALL_PROGRAMMING_LANGUAGE: Final = (
    "Every conditional grammar starts as one comparison and grows, because the second thing "
    "somebody wants to branch on is always reasonable. A Scope is conjunction-only with no "
    "NOT and no OR, so composing predicates can only narrow, and the reachable set of any "
    "drawing stays computable by inspection. Any other condition makes what a procedure does "
    "an evaluation-order question, which is the reason brain.core.scope has no disjunction."
)

#: Why the node vocabulary is closed rather than filtered.
A_CODE_NODE_IS_A_SECOND_RUNTIME_WITH_NO_GATE_IN_FRONT_OF_IT: Final = (
    "A node that runs a script is an execution path that no leash rung, no autonomy tier, no "
    "entitlement intersection and no audit row governs, reached from a drawing surface whose "
    "author is by definition outside this repository's review. The refusal is a vocabulary "
    "with nowhere to say it rather than a list of dangerous kinds, because a deny list has to "
    "anticipate what somebody will draw and a closed set refuses what nobody thought of."
)


class BuilderError(Exception):
    """Something was authored in a shape that would run wider than anybody decided.

    One error type for the package, outside `brain.core.errors` for the reason
    `brain.agents.model.AgentError` gives about itself: those five outcomes describe an
    answer given to a person who asked a question, and this is a refusal to accept a thing
    somebody was building. Nobody asking a question ever sees one.
    """


# --------------------------------------------------------------- the seven sections (M20.1.1)
class Section(enum.StrEnum):
    """The seven parts of the form, in the order M20.1.1 lists them.

    An enum rather than seven headings in a template, for the reason
    `brain.console.workspace.Part` is one: a section nothing enumerates has no exhaustiveness
    check behind it, and the manifest path that should have been in it goes missing quietly.
    """

    IDENTITY = "identity"
    PERSONA = "persona"
    KNOWLEDGE = "knowledge"
    SKILLS = "skills"
    TOOLS = "tools"
    LEASH = "leash"
    TESTS = "tests"


#: How many sections there are, pinned so a test can hold it against the leaf's own list.
#:
#: Pinned rather than computed at the call site, for the reason `brain.console.screens.
#: SCREEN_COUNT` is: the interesting failure is a section disappearing in a refactor, and a
#: test asserting `len(Section) == len(Section)` would not notice.
SECTION_COUNT: Final = 7

#: Which section each manifest path is edited in. Exhaustive over `MANIFEST_PATHS`, checked.
#:
#: Written as data rather than derived from the path's own prefix, because two of the
#: assignments are arguments rather than facts about a name.
#:
#: `authority.scope` sits under knowledge rather than under tools. A person in the tools
#: section is answering what this agent may do, which is a list of verbs; a person in the
#: knowledge section is answering what it may know, and a row predicate is half of that
#: answer. Filing the predicate with the tool names asks somebody for a row filter while they
#: are ticking capabilities, which is the point at which a scope gets left unrestricted.
#:
#: `tier` sits under persona, and it is the path that shows the seven sections do not cover
#: the manifest. The work breakdown names no model section. A tier is a statement about how
#: much thinking an agent does rather than about what it may reach, so it goes with the prose
#: that says how the agent behaves. Recorded here rather than left out, because a path in no
#: section is `A_PATH_IN_NO_SECTION_IS_A_FIELD_NOBODY_EDITS_AND_NOBODY_REVIEWS`.
SECTION_OF_PATH: Mapping[str, Section] = MappingProxyType(
    {
        "identity.display_name": Section.IDENTITY,
        "identity.published_by": Section.IDENTITY,
        "identity.summary": Section.IDENTITY,
        "identity.template_id": Section.IDENTITY,
        "identity.version": Section.IDENTITY,
        "persona": Section.PERSONA,
        "placeholders": Section.PERSONA,
        "tier": Section.PERSONA,
        "authority.scope": Section.KNOWLEDGE,
        "connectors": Section.KNOWLEDGE,
        "skills": Section.SKILLS,
        "authority.allowed_tools": Section.TOOLS,
        "authority.capabilities": Section.TOOLS,
        "authority.required_tools": Section.TOOLS,
        "guardrails.leash": Section.LEASH,
        "guardrails.max_side_effect": Section.LEASH,
        "golden_set": Section.TESTS,
    }
)


def paths_in(section: Section) -> tuple[str, ...]:
    """The manifest paths one section edits, in manifest order.

    Manifest order rather than the mapping's, so two readings of an unchanged manifest give
    the same list and a form's field order does not depend on how the mapping was typed.
    """
    return tuple(path for path in MANIFEST_PATHS if SECTION_OF_PATH.get(path) is section)


# ------------------------------------------------- authority is derived, not authored (M20.1.5)
#: Field names that would let something an author typed be read as something granted.
#:
#: Names rather than a rule about values, because the failure arrives as a field somebody adds
#: to save a lookup: a `granted` beside a `requested` is one assignment away from being the
#: thing the projector reads. The same construction as
#: `brain.console.workspace.NAMES_THAT_WOULD_BE_AN_INLINE_COPY`.
NAMES_THAT_WOULD_BE_AN_AUTHORISATION: Final[frozenset[str]] = frozenset(
    {
        "allowed",
        "authorised",
        "effective_reach",
        "entitlement",
        "entitlements",
        "granted",
        "grants",
        "permissions",
        "reach",
    }
)


@dataclass(frozen=True)
class Draft:
    """What an author has typed: which tools they ticked and which capabilities they asked for.

    **Both fields are intent and neither is authority.** `requested` is named for what it is
    rather than for what a reader might hope it is, and there is no second field beside it
    holding what was granted, which is
    `AN_AUTHORED_LIST_IS_INTENT_AND_THE_TOOLS_ARE_THE_AUTHORITY` expressed as a shape.
    `authorisation_shaped_fields` reports one if a later edit adds it.
    """

    agent_id: str
    author_id: str
    #: The tool names ticked in the tools section.
    tools: tuple[str, ...] = ()
    #: The capabilities typed alongside them. Read as a request and never as a grant.
    requested: tuple[Capability, ...] = ()

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            msg = "a draft of no agent names nothing anybody can publish or review"
            raise BuilderError(msg)
        if not self.author_id.strip():
            msg = "a draft with no author is a change nobody can be asked about"
            raise BuilderError(msg)


@dataclass(frozen=True)
class DerivedAuthority:
    """What the server worked out from the tools, and what it declined to carry across.

    `unearned` is the author's own two lists compared with each other, so it discloses
    nothing they did not type: it says which of their requests no tool they chose requires,
    which is a fact about their draft rather than about the installation.
    """

    capabilities: tuple[Capability, ...]
    unearned: tuple[str, ...]


def derived_capabilities(tools: Iterable[ToolDefinition]) -> tuple[Capability, ...]:
    """The capabilities these tools require, deduplicated and sorted.

    Through `brain.tools.registry.capability_for` rather than by reading
    `ToolDefinition.required_capability` as a string, because that function is where an
    unparseable requirement is refused, and treating one as "no requirement" here would turn
    a typo in a tool definition into an open door in the composer.
    """
    found = {capability_for(one).value for one in tools}
    return tuple(Capability(value=one) for one in sorted(found))


def derive(draft: Draft, definitions: Iterable[ToolDefinition]) -> DerivedAuthority:
    """The authority for this draft, worked out from its tools rather than from its list.

    `definitions` are the tools the author ticked, resolved by whoever holds the registry.
    They are handed in rather than looked up, for the reason `brain.ops.limits` gives about
    policy that owns a client: the case worth testing is the one where the author asked for
    something no tool requires, and that case cannot be reached through a module that opens
    a socket to find out what the tools are.

    A requested capability is earned when a chosen tool's own requirement covers it, so a
    tool requiring `read:client.*` earns a request for `read:client.name`. It is not earned
    the other way round, because `Capability.covers` only expands a trailing star and an
    entity-level request must not confer every field under it.
    """
    earned = derived_capabilities(definitions)
    unearned = tuple(
        sorted(one.value for one in draft.requested if not any(each.covers(one) for each in earned))
    )
    return DerivedAuthority(capabilities=earned, unearned=unearned)


def authorisation_shaped_fields(surface: Sequence[type]) -> tuple[str, ...]:
    """Fields on these types that would let an authored value be read as a granted one.

    Reported as `Type.field` so the finding names the edit, following
    `brain.ops.jobs.hidden_count_fields`.
    """
    findings: list[str] = []
    for one in surface:
        declared: Mapping[str, object] = getattr(one, "__dataclass_fields__", {})
        findings.extend(
            f"{one.__name__}.{name}"
            for name in declared
            if name in NAMES_THAT_WOULD_BE_AN_AUTHORISATION
        )
    return tuple(findings)


# ------------------------------------------------------------ the canvas grammar (M20.2.3, M20.2.4)
class NodeKind(enum.StrEnum):
    """Every kind of node a procedure may contain.

    Five: an entry, an action, a conditional, a question to a person, and an exit. There is
    no member for a script, an expression, a model call or a decision, and there is nowhere
    to put one without changing this enum in a diff somebody reviews. That is the whole of
    `A_CODE_NODE_IS_A_SECOND_RUNTIME_WITH_NO_GATE_IN_FRONT_OF_IT`: not a rule a drawing is
    asked to follow, a vocabulary in which the forbidden thing cannot be said. The same
    construction as `brain.ops.automation.StepKind` and for the same reason.
    """

    #: Where the procedure begins. Exactly one per drawing.
    START = "start"
    #: Invoke one registered tool, which runs the gate like any other call.
    TOOL_CALL = "tool_call"
    #: Split on a scope predicate. The only conditional there is.
    BRANCH = "branch"
    #: Put a question to the person the procedure is being run for.
    ASK = "ask"
    #: Where it ends.
    FINISH = "finish"


#: How many kinds there are, pinned so a test can hold it against the leaf's own figure.
NODE_KIND_COUNT: Final = 5

#: The one kind that may carry a condition. Named rather than written into the check twice.
CONDITIONAL_KIND: Final = NodeKind.BRANCH

#: Field names that would make a node a code node whatever its kind says.
#:
#: The second door. A `TOOL_CALL` carrying a `script` is a code node wearing a permitted
#: name, so the kind check alone is open, and a check of these names alone would miss a kind
#: called `code`. Both are needed and neither is a copy of the other.
NAMES_THAT_WOULD_BE_A_CODE_NODE: Final[frozenset[str]] = frozenset(
    {
        "body",
        "code",
        "command",
        "eval",
        "exec",
        "expression",
        "javascript",
        "python",
        "script",
        "shell",
        "source",
        "template",
    }
)


@dataclass(frozen=True)
class Node:
    """One node on a procedure canvas: what kind it is, and the one payload that kind takes.

    **A predicate may only be on a branch.** Not because a predicate elsewhere would be
    dangerous by itself, but because a second place to put a condition is a second
    conditional grammar, and the one that gets used is whichever the drawing surface writes
    to. See `A_CONDITIONAL_THAT_IS_NOT_A_SCOPE_IS_A_SMALL_PROGRAMMING_LANGUAGE`.

    There is no check that `prompt` is empty on the kinds that do not use it, and that is
    deliberate rather than an omission. Prose on a node that ignores it is meaningless rather
    than dangerous, and a refusal nobody needs is a branch no test can exercise. It is the
    same removal `brain.console.reads.ConsoleRead` records having made.
    """

    node_id: str
    kind: NodeKind
    #: The registered tool a `TOOL_CALL` invokes. Empty on every other kind.
    tool: str = ""
    #: The predicate a `BRANCH` splits on. None on every other kind.
    predicate: Scope | None = None
    #: What an `ASK` puts to the person.
    prompt: str = ""

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            msg = "a node with no id cannot be connected to, refused or pointed at in review"
            raise BuilderError(msg)
        if self.predicate is not None and self.kind is not CONDITIONAL_KIND:
            msg = (
                f"node {self.node_id!r} is a {self.kind.value} carrying a predicate, so a "
                f"condition lives somewhere the drawing does not call a branch. "
                f"{A_CONDITIONAL_THAT_IS_NOT_A_SCOPE_IS_A_SMALL_PROGRAMMING_LANGUAGE}"
            )
            raise BuilderError(msg)
        if self.kind is CONDITIONAL_KIND and self.predicate is None:
            msg = (
                f"branch {self.node_id!r} carries no predicate, so what it splits on is "
                "decided by whatever reads it rather than by what was drawn"
            )
            raise BuilderError(msg)
        if self.tool.strip() and self.kind is not NodeKind.TOOL_CALL:
            msg = (
                f"node {self.node_id!r} is a {self.kind.value} naming a tool, so a call "
                "happens from a node kind nothing projects a catalogue for"
            )
            raise BuilderError(msg)
        if self.kind is NodeKind.TOOL_CALL and not self.tool.strip():
            msg = f"node {self.node_id!r} calls a tool it does not name"
            raise BuilderError(msg)


def assert_drawable(nodes: Iterable[Mapping[str, object]]) -> None:
    """Refuse a drawing containing a node this system will not run.

    Nodes arrive as JSON from a canvas outside this repository, so they are validated as
    untrusted input rather than typed. Two refusals, and both are needed: a kind that is not
    one of the five, which is the vocabulary door, and a field from
    `NAMES_THAT_WOULD_BE_A_CODE_NODE`, which is the payload door. A node with no `kind` is
    refused rather than skipped, because an unrecognised node that runs anyway is the
    definition of the boundary not existing, and a canvas ships on its own release schedule.
    """
    known = {one.value for one in NodeKind}
    for index, node in enumerate(nodes):
        kind = node.get("kind")
        if not isinstance(kind, str) or kind not in known:
            msg = (
                f"node {index} has kind {kind!r}, which is not one of {sorted(known)}. "
                f"{A_CODE_NODE_IS_A_SECOND_RUNTIME_WITH_NO_GATE_IN_FRONT_OF_IT}"
            )
            raise BuilderError(msg)
        carried = sorted(set(node) & NAMES_THAT_WOULD_BE_A_CODE_NODE)
        if carried:
            msg = (
                f"node {index} is a {kind} carrying {carried}, which is a code node under a "
                f"permitted name. {A_CODE_NODE_IS_A_SECOND_RUNTIME_WITH_NO_GATE_IN_FRONT_OF_IT}"
            )
            raise BuilderError(msg)


def code_node_fields(node_type: type) -> tuple[str, ...]:
    """Fields on the node type that would carry a body rather than a reference.

    Asked of the type as well as of the payload, because the two failures arrive by
    different routes: a canvas sends an extra key, and an author of this module adds a field.
    """
    declared: Mapping[str, object] = getattr(node_type, "__dataclass_fields__", {})
    return tuple(
        f"{node_type.__name__}.{name}"
        for name in declared
        if name in NAMES_THAT_WOULD_BE_A_CODE_NODE
    )


# ------------------------------------------------------------------------- the diagnostic
#: The types an author of this surface is handed. Listed rather than discovered, following
#: `brain.console.workspace.WORKSPACE_SURFACE`: a type added here and not to this tuple is a
#: type the checks below never see.
COMPOSE_SURFACE: Final[tuple[type, ...]] = (Draft, DerivedAuthority, Node)


def compose_gaps(
    *,
    sections: Mapping[str, Section] = SECTION_OF_PATH,
    paths: Sequence[str] = MANIFEST_PATHS,
    surface: Sequence[type] = COMPOSE_SURFACE,
    node_type: type = Node,
    source: str | None = None,
) -> tuple[str, ...]:
    """Everything about this composer that would let an authored value become an authority.

    Takes its inputs rather than reading this module's own constants, and a mutation is the
    reason: a diagnostic that can only run against the healthy tree has nothing to report on
    today's data, so switching off any of its refusals changes nothing observable and every
    one of them survives. Calling it with no arguments is the deployment check and calling it
    with a constructed set is the test. `brain.console.workspace.workspace_gaps` and
    `brain.ops.starter.starter_gaps` both make the same argument about their own parameters.
    """
    # Imported here rather than at module scope so that this module's own dependency on the
    # console is the check and not the surface: nothing in the composer's public shape needs
    # a console type, and a top-level import would suggest otherwise to a reader.
    from brain.console.workspace import intersections_in

    gaps: list[str] = []

    for path in paths:
        if path not in sections:
            gaps.append(
                f"{path!r} is in no section, so the form never shows it, nobody is asked "
                f"about it and nobody reviewing the agent sees it. "
                f"{A_PATH_IN_NO_SECTION_IS_A_FIELD_NOBODY_EDITS_AND_NOBODY_REVIEWS}"
            )
    known = set(paths)
    for path in sections:
        if path not in known:
            gaps.append(
                f"{path!r} is sectioned and is not a manifest path, so the form has a field "
                "that edits nothing and the path it was renamed from is now unsectioned"
            )
    filled = set(sections.values())
    for section in Section:
        if section not in filled:
            gaps.append(
                f"the {section.value} section edits no path, so it is a heading with nothing "
                "under it and the fields somebody expects there are in another section"
            )

    gaps.extend(
        f"{found} would let something an author typed be read as something granted. "
        f"{AN_AUTHORED_LIST_IS_INTENT_AND_THE_TOOLS_ARE_THE_AUTHORITY}"
        for found in authorisation_shaped_fields(surface)
    )
    gaps.extend(
        f"{found} would let a node carry a body. "
        f"{A_CODE_NODE_IS_A_SECOND_RUNTIME_WITH_NO_GATE_IN_FRONT_OF_IT}"
        for found in code_node_fields(node_type)
    )

    text = inspect.getsource(sys.modules[__name__]) if source is None else source
    gaps.extend(
        f"line {line} intersects two entitlement sets, so the composer works out a reach "
        "rather than being handed one, which is a second copy of the central rule owned by "
        "the layer with the least reason to be trusted with it"
        for line in intersections_in(text)
    )

    return tuple(gaps)
