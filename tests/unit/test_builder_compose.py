"""The composer held to the two rules that stop an authoring surface becoming a grant path.

A form and a canvas both take typing from a person and turn it into something that will later
run against real rows, and each has one way of going wrong that nothing else in the system
catches. A form's capability list is a thing somebody typed, and the moment it is stored as
the agent's authority the composer is where grants are made, reviewed by whoever was designing
an agent. A canvas's node kinds are a vocabulary, and the moment one of them can carry a
script the drawing surface is a second runtime with no leash, no entitlement intersection and
no audit row in front of it.

The four leaves claimed here are the ones with a rule in them rather than a control. The seven
sections cover every manifest path exactly once (M20.1.1); the authority is derived from the
tools that were chosen rather than from the list that was typed (M20.1.5); a branch is the
only node that may carry a condition and the condition is a scope predicate (M20.2.3); and a
node kind outside the five, or a node carrying a body, is refused at the door (M20.2.4).

Real `ToolDefinition`s, real `Capability`s and the real `MANIFEST_PATHS` throughout. A fixture
standing in for any of them would be this module agreeing with itself.

Task ids: M20.1.1, M20.1.5, M20.2.3, M20.2.4
"""

from __future__ import annotations

import pytest

from brain.agents.template import MANIFEST_PATHS
from brain.builder.compose import (
    AN_AUTHORED_LIST_IS_INTENT_AND_THE_TOOLS_ARE_THE_AUTHORITY,
    COMPOSE_SURFACE,
    CONDITIONAL_KIND,
    NAMES_THAT_WOULD_BE_A_CODE_NODE,
    NAMES_THAT_WOULD_BE_AN_AUTHORISATION,
    NODE_KIND_COUNT,
    SECTION_COUNT,
    SECTION_OF_PATH,
    BuilderError,
    DerivedAuthority,
    Draft,
    Node,
    NodeKind,
    Section,
    assert_drawable,
    authorisation_shaped_fields,
    code_node_fields,
    compose_gaps,
    derive,
    derived_capabilities,
    paths_in,
)
from brain.core.entitlement import Capability
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.scope import Clause, Op, Scope

AGENT = "support_triage"
AUTHOR = "p_author"

#: The seven the work breakdown names, written out here so the enum is compared against the
#: leaf's own list rather than against itself.
SEVEN_SECTIONS = ("identity", "persona", "knowledge", "skills", "tools", "leash", "tests")


def a_tool(name: str, capability: str) -> ToolDefinition:
    """One real tool definition, so a capability is derived from the type it lives on."""
    return ToolDefinition(
        name=name,
        description="Reads one thing.",
        entity="ticket",
        required_capability=capability,
        side_effect=SideEffect.NONE,
    )


def a_draft(*requested: str) -> Draft:
    """A draft asking for these capabilities, with a tool list the caller sets separately."""
    return Draft(
        agent_id=AGENT,
        author_id=AUTHOR,
        tools=("helpdesk.read_ticket",),
        requested=tuple(Capability(value=one) for one in requested),
    )


def a_department_scope(name: str) -> Scope:
    return Scope(clauses=(Clause(field="department", op=Op.EQ, value=name),))


# --- the seven sections cover the manifest (M20.1.1) ------------------------------------------


def test_the_form_has_exactly_the_seven_sections_the_work_breakdown_names() -> None:
    """**M20.1.1.** The seven are the list the composer is arranged by. A section that
    disappeared in a refactor takes its manifest paths off the form with it, and every
    remaining check would still pass because each one asks about the sections that are there.
    Deleting this leaves the count free to be anything.
    """
    assert tuple(one.value for one in Section) == SEVEN_SECTIONS
    assert len(Section) == SECTION_COUNT


def test_every_manifest_path_is_edited_in_exactly_one_section() -> None:
    """**M20.1.1.** A path in no section is a field the form never shows, so it keeps whatever
    the template set and nobody is asked about it. A path in two is a field whose value depends
    on which section was saved last. Deleting this lets a manifest path be added with no
    section, which fails silently in the direction of nobody noticing.
    """
    assert set(SECTION_OF_PATH) == set(MANIFEST_PATHS)
    assert len(SECTION_OF_PATH) == len(MANIFEST_PATHS)
    covered = [path for section in Section for path in paths_in(section)]
    assert sorted(covered) == sorted(MANIFEST_PATHS)


def test_no_section_is_a_heading_with_nothing_under_it() -> None:
    """**M20.1.1.** An empty section is a heading a person opens to find nothing, and the
    fields they expected are somewhere else. Deleting this lets a section survive a
    re-sectioning that emptied it, which reads to a user as a missing feature.
    """
    for section in Section:
        assert paths_in(section), f"{section.value} edits no manifest path"


def test_a_sectioning_that_empties_a_section_is_reported() -> None:
    """**M20.1.1.** The check above asks `paths_in` whether the sections this module declares
    are full, which says nothing about whether `compose_gaps` would notice one that was not:
    a mutation switching that refusal off survived until this test existed, because the only
    input the diagnostic ever saw was the healthy one. Deleting this returns it to that state.
    """
    identity_only = {
        path: section for path, section in SECTION_OF_PATH.items() if section is Section.IDENTITY
    }
    found = compose_gaps(sections=identity_only, paths=tuple(identity_only))
    assert any("the tests section edits no path" in one for one in found)
    assert any("the leash section edits no path" in one for one in found)


def test_a_manifest_path_left_out_of_the_sections_is_reported() -> None:
    """**M20.1.1.** The exhaustiveness check is the whole of the leaf, so it has to be
    exercised against a broken sectioning rather than only against the healthy one: a check
    that can only run against a tree with nothing wrong with it survives being switched off.
    Deleting this leaves that check unexercised.
    """
    incomplete = {
        path: section for path, section in SECTION_OF_PATH.items() if path != "authority.scope"
    }
    found = compose_gaps(sections=incomplete)
    assert any("authority.scope" in one for one in found)


def test_a_sectioned_path_the_manifest_does_not_have_is_reported() -> None:
    """**M20.1.1.** The other direction: a path renamed in the manifest leaves its old name
    sectioned and its new name unsectioned, and only the second is obvious. Deleting this lets
    a rename ship with a form field that edits nothing.
    """
    stale = dict(SECTION_OF_PATH)
    stale["authority.scope_predicate"] = Section.KNOWLEDGE
    found = compose_gaps(sections=stale)
    assert any("authority.scope_predicate" in one for one in found)


def test_a_healthy_sectioning_reports_nothing() -> None:
    """**M20.1.1.** The positive case. A diagnostic tested only by what it catches is
    satisfied by one that reports everything, and this module's own sectioning is the input it
    has to be quiet about. Deleting this lets the checks above pass with a gap function that
    always finds something.
    """
    assert compose_gaps() == ()


# --- authority is derived and never authored (M20.1.5) ----------------------------------------


def test_the_authority_is_derived_from_the_tools_that_were_chosen() -> None:
    """**M20.1.5.** The positive half: a capability the chosen tools require is carried, and it
    is read off the tool definitions rather than off the author's list. Deleting this leaves
    the refusal below satisfied by a function that derives nothing at all.
    """
    derived = derive(
        a_draft("read:ticket.subject"),
        [a_tool("helpdesk.read_ticket", "read:ticket.subject")],
    )
    assert derived.capabilities == (Capability(value="read:ticket.subject"),)
    assert derived.unearned == ()


def test_a_capability_no_chosen_tool_requires_is_not_carried_into_the_authority() -> None:
    """**M20.1.5.** This is the leaf. An authored list is intent, so a capability nobody's tool
    asks for is reported back rather than granted; storing it would make the form the grant
    path. Deleting this lets the composer honour whatever a browser posted.
    """
    derived = derive(
        a_draft("read:ticket.subject", "read:invoice.total"),
        [a_tool("helpdesk.read_ticket", "read:ticket.subject")],
    )
    assert derived.capabilities == (Capability(value="read:ticket.subject"),)
    assert derived.unearned == ("read:invoice.total",)


def test_a_tool_requiring_a_whole_entity_earns_a_request_for_one_of_its_fields() -> None:
    """**M20.1.5.** Coverage runs one way only. A tool requiring `read:client.*` earns a
    request for `read:client.name`, and the reverse must not hold, because an entity-level
    request would otherwise confer every field under it. Deleting this lets `derive` compare
    capability strings for equality, which reports a correct request as unearned.
    """
    earns = derive(a_draft("read:client.name"), [a_tool("crm.read_client", "read:client.*")])
    assert earns.unearned == ()
    not_earned = derive(a_draft("read:client.*"), [a_tool("crm.read_client", "read:client.name")])
    assert not_earned.unearned == ("read:client.*",)


def test_capabilities_are_derived_from_the_definition_and_not_from_a_string() -> None:
    """**M20.1.5.** `derived_capabilities` reads its answer through the tool registry's own
    `capability_for`, which refuses an unparseable requirement rather than treating it as no
    requirement at all. Deleting this lets a typo in a tool definition become a tool with no
    capability in front of it.
    """
    assert derived_capabilities([a_tool("helpdesk.read_ticket", "read:ticket.subject")]) == (
        Capability(value="read:ticket.subject"),
    )
    with pytest.raises(Exception, match="not a capability"):
        derived_capabilities([a_tool("helpdesk.read_ticket", "Ticket Subject")])


def test_no_type_on_the_composer_carries_a_field_that_would_read_as_a_grant() -> None:
    """**M20.1.5.** The rule has to survive the next edit, and the shape it dies in is a field
    called `granted` added beside `requested` to save a lookup. Deleting this lets that field
    appear with every other test still green, because every other test asks about behaviour
    and this one asks about the type.
    """
    assert authorisation_shaped_fields(COMPOSE_SURFACE) == ()
    assert "granted" in NAMES_THAT_WOULD_BE_AN_AUTHORISATION
    assert AN_AUTHORED_LIST_IS_INTENT_AND_THE_TOOLS_ARE_THE_AUTHORITY


def test_a_type_carrying_a_granted_field_is_reported() -> None:
    """**M20.1.5.** The check above is silent on a healthy tree, so it has to be run against a
    type that breaks it or nothing exercises it. Deleting this leaves the field check
    satisfied by a function that always returns nothing.
    """
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class WouldBeAGrant:
        granted: tuple[str, ...] = ()

    found = compose_gaps(surface=[WouldBeAGrant])
    assert any("WouldBeAGrant.granted" in one for one in found)


# --- the canvas grammar (M20.2.3) ------------------------------------------------------------


def test_a_procedure_has_exactly_five_node_kinds() -> None:
    """**M20.2.3.** Five is the figure the leaf gives, and a sixth kind is how a code node
    arrives: not as a node called `code` but as one that seemed reasonable and carries a
    payload nothing governs. Deleting this lets the vocabulary grow without a diff anybody
    argues about.
    """
    assert len(NodeKind) == NODE_KIND_COUNT
    assert tuple(one.value for one in NodeKind) == (
        "start",
        "tool_call",
        "branch",
        "ask",
        "finish",
    )


def test_a_branch_splits_on_a_scope_predicate() -> None:
    """**M20.2.3.** The positive case. A branch is the one conditional there is, and it has to
    work, or the refusals below are satisfied by a grammar that admits no conditional at all.
    Deleting this lets the canvas refuse the thing it exists to allow.
    """
    node = Node(node_id="n1", kind=NodeKind.BRANCH, predicate=a_department_scope("web"))
    assert node.predicate == a_department_scope("web")
    assert CONDITIONAL_KIND is NodeKind.BRANCH


def test_a_node_that_is_not_a_branch_may_not_carry_a_condition() -> None:
    """**M20.2.3.** A second place to put a condition is a second conditional grammar, and the
    one that gets used is whichever the drawing surface writes to. Deleting this lets a
    predicate ride on a tool call, where nothing checks that it is a scope.
    """
    with pytest.raises(BuilderError, match="carrying a predicate"):
        Node(
            node_id="n1",
            kind=NodeKind.TOOL_CALL,
            tool="helpdesk.read_ticket",
            predicate=a_department_scope("web"),
        )


def test_a_branch_without_a_predicate_is_refused() -> None:
    """**M20.2.3.** A branch with nothing to split on is a branch whose condition is decided by
    whatever reads it, which is the evaluation-order failure the scope grammar exists to avoid.
    Deleting this lets a drawing ship a conditional nobody wrote.
    """
    with pytest.raises(BuilderError, match="carries no predicate"):
        Node(node_id="n1", kind=NodeKind.BRANCH)


def test_a_node_with_no_id_is_refused() -> None:
    """**Written because a mutation of this guard survived the whole file.** Every node built
    anywhere here was given an id, so the refusal could be deleted with nothing red.

    An id is how a node is connected to, and it is how it is talked about afterwards. Every
    other refusal on this class names the node by its id in the sentence it raises, so a
    drawing full of unnamed nodes produces a series of refusals reading `node ''`, and the
    author is told that something on the canvas is wrong and not which thing. A reviewer
    reading the same drawing has nothing to point at either.

    Blank as well as empty, because a drawing surface that hands back a trimmed field for a
    box somebody clicked into and left gives a space rather than nothing.

    Delete this and a canvas can hold two nodes nothing tells apart."""
    for missing in ("", "   "):
        with pytest.raises(BuilderError, match="a node with no id"):
            Node(node_id=missing, kind=NodeKind.ASK, prompt="Which client is this about?")

    assert Node(node_id="n1", kind=NodeKind.ASK, prompt="Which client?").node_id == "n1"


def test_only_a_tool_call_may_name_a_tool() -> None:
    """**M20.2.3.** A tool named on any other kind is a call made from a node kind nothing
    projects a catalogue for, so the gate is not in front of it. Deleting this lets a finish
    node invoke something on the way out.
    """
    assert Node(node_id="n1", kind=NodeKind.TOOL_CALL, tool="helpdesk.read_ticket").tool
    with pytest.raises(BuilderError, match="naming a tool"):
        Node(node_id="n1", kind=NodeKind.ASK, tool="helpdesk.read_ticket")
    with pytest.raises(BuilderError, match="does not name"):
        Node(node_id="n1", kind=NodeKind.TOOL_CALL)


# --- no code node, enforced (M20.2.4) ---------------------------------------------------------


def test_a_drawing_of_the_five_known_kinds_is_accepted() -> None:
    """**M20.2.4.** The positive case for the door. A refusal tested only by what it refuses is
    satisfied by one that refuses everything, and a canvas that could draw nothing would pass
    every other test here. Deleting this lets the door close on the permitted kinds.
    """
    drawing: list[dict[str, object]] = [
        {"kind": "start"},
        {"kind": "tool_call", "tool": "helpdesk.read_ticket"},
        {"kind": "branch"},
        {"kind": "ask", "prompt": "which ticket?"},
        {"kind": "finish"},
    ]
    # The assertion is that this raises nothing: `assert_drawable` is a door and returns None.
    assert_drawable(drawing)
    with pytest.raises(BuilderError):
        assert_drawable([*drawing, {"kind": "code"}])


def test_a_node_kind_the_vocabulary_does_not_have_is_refused() -> None:
    """**M20.2.4.** Nodes arrive as JSON from a canvas outside this repository on its own
    release schedule, so an unrecognised kind that ran anyway would be the boundary not
    existing. Deleting this lets a `code` node through the moment somebody adds one upstream.
    """
    with pytest.raises(BuilderError, match="not one of"):
        assert_drawable([{"kind": "code", "script": "os.system('id')"}])
    with pytest.raises(BuilderError, match="not one of"):
        assert_drawable([{"tool": "helpdesk.read_ticket"}])


def test_a_permitted_node_carrying_a_body_is_refused() -> None:
    """**M20.2.4.** The second door, and the one the kind check misses entirely: a `tool_call`
    with a `script` on it is a code node wearing a permitted name. Deleting this leaves the
    boundary passable by anybody who reads the enum and names their node after one of it.
    """
    with pytest.raises(BuilderError, match="under a permitted name"):
        assert_drawable([{"kind": "tool_call", "script": "os.system('id')"}])
    assert "script" in NAMES_THAT_WOULD_BE_A_CODE_NODE


def test_the_node_type_carries_no_field_a_body_could_arrive_in() -> None:
    """**M20.2.4.** The payload check asks about what a canvas sends; this asks about what this
    module declares, and the two failures arrive by different routes. Deleting this lets a
    `script` field be added to `Node`, where every drawing would carry it legitimately.
    """
    assert code_node_fields(Node) == ()


def test_a_node_type_with_a_script_field_is_reported() -> None:
    """**M20.2.4.** The type check is silent on a healthy tree, so it has to be run against a
    type that breaks it. Deleting this leaves it satisfied by a function that finds nothing.
    """
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class WouldRunCode:
        script: str = ""

    found = compose_gaps(node_type=WouldRunCode)
    assert any("WouldRunCode.script" in one for one in found)


# --- the module holds no copy of the invariant -------------------------------------------------


def test_the_composer_computes_no_reach_of_its_own() -> None:
    """**M20.1.5.** `EntitlementSet.intersect` is the one implementation of the platform's
    central rule, and a composer that worked out its own reach would be a second copy owned by
    the layer with the least reason to be trusted with it. Deleting this lets one be added,
    and the copy that is subtly wrong is the one in production.
    """
    assert compose_gaps() == ()
    planted = "def f(caller, ceiling):\n    return caller.intersect(ceiling)\n"
    found = compose_gaps(source=planted)
    assert any("intersects two entitlement sets" in one for one in found)


def test_a_draft_names_an_agent_and_an_author() -> None:
    """**M20.1.5.** A draft with no author is a change nobody can be asked about, which matters
    at the publish gate rather than here: the second approver has to be somebody other than
    the author, and that is unanswerable when there is no author. Deleting this lets one be
    built.
    """
    assert Draft(agent_id=AGENT, author_id=AUTHOR).requested == ()
    with pytest.raises(BuilderError, match="no agent"):
        Draft(agent_id=" ", author_id=AUTHOR)
    with pytest.raises(BuilderError, match="no author"):
        Draft(agent_id=AGENT, author_id="")


def test_a_derived_authority_reports_what_it_declined_without_naming_anything_else() -> None:
    """**M20.1.5.** `unearned` is the author's own two lists compared with each other, so it
    says nothing about the installation: no capability the author did not type can appear in
    it. Deleting this lets a future version fill it from a registry, which would turn the
    composer into a way of enumerating capabilities by asking for them.
    """
    derived = derive(a_draft("read:invoice.total"), [])
    assert isinstance(derived, DerivedAuthority)
    assert set(derived.unearned) <= {"read:invoice.total"}
    assert derived.capabilities == ()
