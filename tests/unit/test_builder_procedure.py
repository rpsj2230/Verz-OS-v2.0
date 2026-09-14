"""A drawn procedure is bounded, and its SKILL.md is the drawing and nothing else.

M20.2.2 is "a bounded procedure canvas outputting a SKILL.md", and both halves of that carry a
claim this file holds the server's side of. *Bounded*: one start, no loop, no step a run
cannot reach, every way out a kind requires, and no more steps than the gate lets a plan name.
*Outputting*: the document is written from the drawing and reads back as an equal drawing, so
nothing drawn is missing from it and nothing in it was not drawn.

Most refusals share one positive sibling. `a_drawing()` uses all five kinds, a branch whose
two ways meet again at one finish, a question with quotes and a newline in it and a predicate
with a list in it, and it is accepted. A refusal test here asserts that sibling as well,
because a reader that refused everything would satisfy every refusal on its own.

The console's half is `console/tests/procedure-canvas.test.tsx`, and the two meet at
`console/tests/fixtures/procedure-drawing.json`: that suite asserts the canvas produces it, and
the last test here asserts this module accepts it and writes a document that reads back as the
same drawing. Without that file the two halves would each be tested against their own idea of
the other.

Task ids: M20.2.2
"""

from __future__ import annotations

import copy
import inspect
import itertools
import json
import re
from pathlib import Path
from typing import Any

import pytest

from brain.agents.template import PROMPT_CHARS
from brain.builder.compose import BuilderError, NodeKind
from brain.builder.procedure import (
    PREAMBLE,
    Procedure,
    procedure_from_skill_markdown,
    read_drawing,
    skill_markdown,
    tools_called,
)
from brain.gate.caches import MAX_PLAN_TOOLS, CachedPlan
from brain.tools.skills import skill_from_markdown

REPO = Path(__file__).resolve().parents[2]
CANVAS_FIXTURE = REPO / "console" / "tests" / "fixtures" / "procedure-drawing.json"

READ = "crm.read_client"
RAISE = "billing.create_invoice"
TOOLS = frozenset({READ, RAISE})
NAME = "invoice_on_request"
DESCRIPTION = "Reads a client, checks the tier and asks before raising an invoice."

#: Two clauses, one of them a list, so a tuple value has to survive the document too.
PREDICATE = {
    "clauses": [
        {"field": "tier", "op": "eq", "value": "gold"},
        {"field": "region", "op": "in", "value": ["north", "south"]},
    ]
}

#: Quotes and a newline, which are the two things a line-based document could mangle.
QUESTION = 'Shall I raise the invoice marked "urgent"?\nAnswer yes or no.'


def a_drawing() -> dict[str, Any]:
    """Every kind once or more, and a branch whose two ways meet again at one finish."""
    return copy.deepcopy(
        {
            "nodes": [
                {"id": "start", "kind": "start"},
                {"id": "read_client", "kind": "tool_call", "tool": READ},
                {"id": "check_tier", "kind": "branch", "predicate": PREDICATE},
                {"id": "ask_first", "kind": "ask", "prompt": QUESTION},
                {"id": "raise_invoice", "kind": "tool_call", "tool": RAISE},
                {"id": "done", "kind": "finish"},
            ],
            "edges": [
                {"from": "start", "to": "read_client", "way": "next"},
                {"from": "read_client", "to": "check_tier", "way": "next"},
                {"from": "check_tier", "to": "ask_first", "way": "holds"},
                {"from": "check_tier", "to": "done", "way": "otherwise"},
                {"from": "ask_first", "to": "raise_invoice", "way": "next"},
                {"from": "raise_invoice", "to": "done", "way": "next"},
            ],
        }
    )


def drawn(payload: dict[str, Any] | None = None) -> Procedure:
    return read_drawing(a_drawing() if payload is None else payload, drawable_tools=TOOLS)


def arrow(payload: dict[str, Any], source: str, way: str) -> dict[str, Any]:
    return next(one for one in payload["edges"] if one["from"] == source and one["way"] == way)


def step(payload: dict[str, Any], step_id: str) -> dict[str, Any]:
    return next(one for one in payload["nodes"] if one["id"] == step_id)


def a_chain(length: int) -> tuple[dict[str, Any], frozenset[str]]:
    """A start, then tool calls in a row, then a finish: the longest path `length` steps allow.

    Each call names a different tool, because a plan the gate caches may not name one twice.
    """
    calls = [f"call_{index}" for index in range(length - 2)]
    tools = [f"crm.read_item_{index}" for index in range(length - 2)]
    nodes = [
        {"id": "start", "kind": "start"},
        *(
            {"id": call, "kind": "tool_call", "tool": tool}
            for call, tool in zip(calls, tools, strict=True)
        ),
        {"id": "done", "kind": "finish"},
    ]
    edges = [
        {"from": before, "to": after, "way": "next"}
        for before, after in itertools.pairwise(["start", *calls, "done"])
    ]
    return {"nodes": nodes, "edges": edges}, frozenset(tools)


def a_document() -> str:
    return skill_markdown(drawn(), name=NAME, description=DESCRIPTION)


# --- bounded: how many steps ---------------------------------------------------------------


def test_a_procedure_as_long_as_the_gate_lets_a_plan_be_is_accepted() -> None:
    """**M20.2.2.** The positive side of the size bound, measured against the gate rather
    than against this module's own constant: the longest single path a drawing at the bound
    can hold is a plan `brain.gate.caches.CachedPlan` accepts. Raise the bound past the gate's
    and this fails, because the chain grows more calls than a plan may name.

    Deleting this lets the bound drift from the gate's, so the canvas draws procedures whose
    every run the gate would treat as a model looping.
    """
    payload, tools = a_chain(MAX_PLAN_TOOLS)
    procedure = read_drawing(payload, drawable_tools=tools)

    assert len(procedure.nodes) == MAX_PLAN_TOOLS
    calls = tuple(node.tool for node in procedure.nodes if node.kind is NodeKind.TOOL_CALL)
    assert CachedPlan(key="a procedure at the bound", tool_ids=calls).tool_ids == calls


def test_a_procedure_one_step_longer_than_that_is_refused() -> None:
    """**M20.2.2.** The refusal the word "bounded" asks for. The figure comes from the gate,
    so a bound quietly raised here is caught rather than compared with itself.

    Deleting this lets a canvas hold as many steps as somebody has patience to draw, and the
    reviewer who approves the skill by digest approves a document nobody read to the end.
    """
    payload, tools = a_chain(MAX_PLAN_TOOLS + 1)
    with pytest.raises(BuilderError, match="holds at most"):
        read_drawing(payload, drawable_tools=tools)


# --- bounded: that every run ends ------------------------------------------------------------


def test_a_step_that_leads_back_to_an_earlier_one_is_refused() -> None:
    """**M20.2.2.** A back edge is a `while` whose exit is a predicate, and without one no run
    takes a step twice, which is what makes the size bound a bound on runs.

    Deleting this lets a drawing loop, and a procedure that loops has no length at all.
    """
    payload = a_drawing()
    arrow(payload, "raise_invoice", "next")["to"] = "read_client"
    with pytest.raises(BuilderError, match="lead back to"):
        drawn(payload)

    assert drawn().nodes[0].kind is NodeKind.START


def test_a_step_no_path_from_the_start_reaches_is_refused() -> None:
    """**M20.2.2.** A walk from the start never meets it, so it would be on the canvas and not
    in the document, which is the drawing and the skill disagreeing.

    Deleting this lets an author approve a document missing a step they can see drawn.
    """
    payload = a_drawing()
    payload["nodes"].append({"id": "orphan", "kind": "finish"})
    with pytest.raises(BuilderError, match="no path from the start reaches"):
        drawn(payload)

    arrow(payload, "check_tier", "otherwise")["to"] = "orphan"
    assert "orphan" in {node.node_id for node in drawn(payload).nodes}


def test_a_step_missing_one_of_its_ways_out_is_refused() -> None:
    """**M20.2.2.** A step with nowhere to go ends a run somewhere that is not a finish, and a
    branch with one way out is a branch that only knows what to do when it holds.

    Deleting this lets a procedure stop in the middle, silently, for some of the people who
    run it.
    """
    for source, way in (("raise_invoice", "next"), ("check_tier", "otherwise")):
        payload = a_drawing()
        payload["edges"].remove(arrow(payload, source, way))
        with pytest.raises(BuilderError, match=f"never leaves by {way}"):
            drawn(payload)


def test_a_way_out_the_kind_does_not_have_is_refused() -> None:
    """**M20.2.2.** A tool call that "holds" is a condition living on a node the drawing does not
    call a branch, which is the second conditional grammar `compose` refuses on the node itself.

    Deleting this lets a condition ride out of a step by its arrow instead of its predicate.
    """
    payload = a_drawing()
    arrow(payload, "read_client", "next")["way"] = "holds"
    with pytest.raises(BuilderError, match="does not leave by holds"):
        drawn(payload)


def test_a_step_that_leaves_the_same_way_twice_is_refused() -> None:
    """**M20.2.2.** Two arrows out by one way is a step whose next step is a guess, and the
    document can only write one of them.

    Deleting this lets the document silently keep whichever arrow was sorted last.
    """
    payload = a_drawing()
    payload["edges"].append({"from": "read_client", "to": "done", "way": "next"})
    with pytest.raises(BuilderError, match="twice"):
        drawn(payload)


def test_an_arrow_to_a_step_that_is_not_drawn_is_refused() -> None:
    """**M20.2.2.** On a trace an arrow to a missing step is dropped, because the step is one the
    reader may not see. On an authoring canvas every step is the author's own, so an arrow
    ending nowhere is a broken drawing and not a filtered one.

    Deleting this lets a document say "go to" a step it never describes.
    """
    payload = a_drawing()
    arrow(payload, "raise_invoice", "next")["to"] = "somewhere_else"
    with pytest.raises(BuilderError, match="not drawn"):
        drawn(payload)


def test_a_procedure_has_exactly_one_start() -> None:
    """**M20.2.2.** Two starts are two procedures on one canvas and none is no procedure, and
    the document can only begin in one place.

    Deleting this lets a skill's first step depend on which start was listed first.
    """
    two = a_drawing()
    two["nodes"].append({"id": "again", "kind": "start"})
    two["edges"].append({"from": "again", "to": "done", "way": "next"})
    none = a_drawing()
    none["nodes"].remove(step(none, "start"))
    none["edges"].remove(arrow(none, "start", "next"))

    for payload in (two, none):
        with pytest.raises(BuilderError, match="exactly one start"):
            drawn(payload)


def test_a_branch_that_cannot_fail_is_refused() -> None:
    """**M20.2.2.** A predicate admitting every row sends every run the same way, so the other
    way out leads to steps no run reaches, written into a reviewed document as though they
    did something.

    Deleting this lets a reviewer approve a path that cannot happen.
    """
    admits_everything: list[dict[str, Any]] = [
        {"clauses": []},
        {"clauses": [{"field": "tier", "op": "any"}]},
    ]
    for predicate in admits_everything:
        payload = a_drawing()
        step(payload, "check_tier")["predicate"] = predicate
        with pytest.raises(BuilderError, match="cannot fail"):
            drawn(payload)


def test_a_question_with_no_words_or_too_many_is_refused() -> None:
    """**M20.2.2.** A question with no words is a pause nobody can answer, and a question longer
    than a template may ask a person is a paragraph of instructions wearing an ask's name.

    Deleting this lets an `ask` step carry nothing, or carry the procedure.
    """
    for prompt in ("", "   ", "x" * (PROMPT_CHARS + 1)):
        payload = a_drawing()
        step(payload, "ask_first")["prompt"] = prompt
        with pytest.raises(BuilderError, match="asks"):
            drawn(payload)

    payload = a_drawing()
    step(payload, "ask_first")["prompt"] = "x" * PROMPT_CHARS
    assert drawn(payload)


def test_a_step_id_that_cannot_be_written_into_a_line_is_refused() -> None:
    """**M20.2.2.** Every line of the document points at a step by its id inside backquotes, so
    an id with a space or a backquote in it is a line that reads back as a different line.

    Deleting this lets a drawing produce a document its own reader cannot read.
    """
    for bad in ("Ask First", "ask`first"):
        payload = a_drawing()
        step(payload, "ask_first")["id"] = bad
        arrow(payload, "check_tier", "holds")["to"] = bad
        arrow(payload, "ask_first", "next")["from"] = bad
        with pytest.raises(BuilderError, match="not a lowercase name"):
            drawn(payload)


def test_two_steps_with_one_id_are_refused() -> None:
    """**M20.2.2.** An arrow to a shared id points at both steps, so what follows it depends on
    which the reader met last.

    Deleting this lets one step silently replace another between the canvas and the document.
    """
    payload = a_drawing()
    step(payload, "raise_invoice")["id"] = "read_client"
    with pytest.raises(BuilderError, match="two steps are called"):
        drawn(payload)


def test_a_key_the_document_cannot_say_is_refused_rather_than_dropped() -> None:
    """**M20.2.2.** The SKILL.md has no way to say where a step sat, what colour an arrow was or
    anything else a canvas might send, so each would be dropped between the drawing and the
    skill. A position is the one that matters: an arrangement meant as an order would vanish.

    Deleting this lets the document and the drawing differ with no refusal anywhere.
    """
    positioned = a_drawing()
    step(positioned, "read_client")["position"] = {"x": 0, "y": 0}
    labelled = a_drawing()
    arrow(labelled, "check_tier", "holds")["label"] = "yes"
    annotated = a_drawing()
    annotated["zoom"] = 1

    for payload in (positioned, labelled, annotated):
        with pytest.raises(BuilderError, match="no way to say"):
            drawn(payload)
    assert drawn()


def test_a_kind_outside_the_five_or_a_body_is_refused_before_a_field_is_read() -> None:
    """**M20.2.2, M20.2.4.** The reader goes through `compose`'s two doors first, so the drawing
    a canvas sends is held to the vocabulary before it is held to anything else, and a script
    on a permitted kind is refused as a code node rather than as an unknown key.

    Deleting this lets the procedure reader become the way round the no-code-node rule.
    """
    coded = a_drawing()
    step(coded, "read_client")["kind"] = "code"
    scripted = a_drawing()
    step(scripted, "read_client")["script"] = "os.system('id')"

    with pytest.raises(BuilderError, match="not one of"):
        drawn(coded)
    with pytest.raises(BuilderError, match="under a permitted name"):
        drawn(scripted)


def test_a_tool_the_canvas_did_not_offer_is_refused_in_words_that_do_not_say_if_it_exists() -> None:
    """**M20.2.2.** DENIED and ABSENT on an authoring surface. A tool that exists and is not this
    author's, and a tool that does not exist at all, must be refused in the same words, or the
    refusal is a way of learning which tool names are real in an installation the author may
    not see all of. The reader is handed the author's tools and has no parameter for the
    registry, so it cannot tell the two apart, and both halves of that are asserted.

    Deleting this lets a friendlier message ("that tool is restricted") map the catalogue.
    """
    assert list(inspect.signature(read_drawing).parameters) == ["payload", "drawable_tools"]

    def refusal(tool: str) -> str:
        payload = a_drawing()
        step(payload, "raise_invoice")["tool"] = tool
        with pytest.raises(BuilderError) as refused:
            read_drawing(payload, drawable_tools=TOOLS - {RAISE})
        return str(refused.value).replace(tool, "<tool>")

    assert refusal(RAISE) == refusal("billing.create_refund")
    assert "not a tool this canvas offers" in refusal(RAISE)
    assert tools_called(drawn()) == (RAISE, READ)


def test_a_drawing_that_is_not_an_object_of_two_lists_is_refused() -> None:
    """**M20.2.2.** A drawing arrives from outside this repository, so every shape it could
    have is refused rather than coerced: a list for the whole, a string for the nodes, a
    node that is not an object, a way out nobody named, text that is not text, and a
    predicate that is not a scope.

    Deleting this lets a malformed body reach `Node` and fail with an attribute error that
    tells the author nothing.
    """
    not_a_way = a_drawing()
    arrow(not_a_way, "check_tier", "holds")["way"] = "maybe"
    not_text = a_drawing()
    step(not_text, "raise_invoice")["tool"] = 7
    not_a_scope = a_drawing()
    step(not_a_scope, "check_tier")["predicate"] = {"clauses": [{"field": "Tier", "op": "or"}]}

    cases: list[tuple[object, str]] = [
        ([], "is an object"),
        ({"nodes": "start", "edges": []}, "a list of nodes"),
        ({"nodes": ["start"], "edges": []}, "every node and every edge"),
        (not_a_way, "which is not one of"),
        (not_text, "is text"),
        (not_a_scope, "not a scope predicate"),
    ]
    for payload, match in cases:
        with pytest.raises(BuilderError, match=match):
            read_drawing(payload, drawable_tools=TOOLS)


# --- outputting a SKILL.md -------------------------------------------------------------------


def test_the_skill_md_reads_back_as_exactly_the_drawing_it_was_written_from() -> None:
    """**M20.2.2.** The claim "outputting a SKILL.md" has to carry: the document is the drawing
    written down. Read back, it is a procedure equal to the one drawn, every step, every
    way out, the question with its quotes and newline, and the predicate with its list, so
    nothing was lost and nothing was assembled from anywhere but the canvas.

    Deleting this leaves the serialiser free to write a plausible document that is not what
    the author drew, and a reviewer approves the document.
    """
    procedure = drawn()
    read_back = procedure_from_skill_markdown(a_document())

    assert read_back == procedure
    asked = next(node for node in read_back.nodes if node.node_id == "ask_first")
    assert asked.prompt == QUESTION


def test_redrawing_one_arrow_rewrites_the_document() -> None:
    """**M20.2.2.** The round trip above would also pass for a serialiser that ignored the
    arrows and a reader that invented the same ones. Swapping which way a branch goes has to
    change the document and read back swapped.

    Deleting this lets a document describe the right steps in the wrong order.
    """
    swapped = a_drawing()
    arrow(swapped, "check_tier", "holds")["to"] = "done"
    arrow(swapped, "check_tier", "otherwise")["to"] = "ask_first"
    rewritten = skill_markdown(drawn(swapped), name=NAME, description=DESCRIPTION)

    assert rewritten != a_document()
    assert procedure_from_skill_markdown(rewritten) == drawn(swapped)


def test_the_document_is_a_skill_the_importer_accepts_with_the_calls_that_were_drawn() -> None:
    """**M20.2.2.** The output is judged by `brain.tools.skills.skill_from_markdown`, the parser
    that decides what a skill is, and its tools line is the tools the drawn steps call.

    Deleting this lets the builder write a document the skill importer refuses, or one whose
    card lists different tools from the ones it calls.
    """
    skill = skill_from_markdown(a_document())

    assert (skill.name, skill.description) == (NAME, DESCRIPTION)
    assert skill.tools == (RAISE, READ)
    assert skill.body.split("\n")[0] == PREAMBLE


def test_a_tools_line_that_leaves_out_a_drawn_call_is_refused_on_the_way_back_in() -> None:
    """**M20.2.2.** The tools line is what a skill's card shows and what a reviewer checks, so a
    document edited to leave a call off it hides that call from review.

    Deleting this lets a hand edit to one line of a drawn skill hide a write from its card.
    """
    text = a_document()
    edited = text.replace(f"tools: [{RAISE}, {READ}]", f"tools: [{READ}]")

    assert edited != text
    with pytest.raises(BuilderError, match="the steps call"):
        procedure_from_skill_markdown(edited)


@pytest.mark.parametrize(
    ("name", "description", "match"),
    [
        ("Invoice On Request", DESCRIPTION, "importer accepts"),
        (NAME, "[draft] Reads a client.", "importer accepts"),
        (NAME, "Reads a client.\nThen asks.", "importer accepts"),
        (NAME, "Reads a client. ", "does not survive"),
    ],
    ids=[
        "name that is not a slug",
        "description read as a list",
        "description on two lines",
        "description the importer trims",
    ],
)
def test_a_name_or_description_the_format_would_change_is_refused(
    name: str, description: str, match: str
) -> None:
    """**M20.2.2.** Two different failures. A value opening with a bracket is a list to the
    importer and a newline ends its line, so the importer refuses the document outright; and a
    value with space around it is accepted and trimmed, so the skill that arrives says something
    slightly different from what was typed, and only comparing the two catches it.

    Deleting this lets the builder publish a skill whose card says something the author never
    typed.
    """
    with pytest.raises(BuilderError, match=match):
        skill_markdown(drawn(), name=name, description=description)


def test_every_arrow_in_the_document_points_at_a_later_step() -> None:
    """**M20.2.2.** The document lists steps so that each is written after every step that leads
    to it, starting from the start, and it lists them in the order the procedure holds them.
    Where nothing but a branch decides the order, the side that holds comes first, whatever the
    ids happen to sort as: every topological order points every arrow forward, so without that
    case the tie-break is a decision nothing watches.

    Deleting this lets the steps come out in any order the round trip tolerates, which is a
    document that reads as a puzzle rather than a procedure.
    """
    procedure = drawn()
    position = {node.node_id: index for index, node in enumerate(procedure.nodes)}
    listed = re.findall(r"^\d+\. `([^`]+)`", a_document(), flags=re.MULTILINE)

    assert procedure.nodes[0].kind is NodeKind.START
    assert all(position[edge.source] < position[edge.target] for edge in procedure.edges)
    assert listed == [node.node_id for node in procedure.nodes]

    split = {
        "nodes": [
            {"id": "start", "kind": "start"},
            {"id": "check_tier", "kind": "branch", "predicate": PREDICATE},
            {"id": "zulu", "kind": "finish"},
            {"id": "alpha", "kind": "finish"},
        ],
        "edges": [
            {"from": "start", "to": "check_tier", "way": "next"},
            {"from": "check_tier", "to": "zulu", "way": "holds"},
            {"from": "check_tier", "to": "alpha", "way": "otherwise"},
        ],
    }
    assert [node.node_id for node in drawn(split).nodes] == ["start", "check_tier", "zulu", "alpha"]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (PREAMBLE, "Do these things."),
        ("\n2. `read_client`", "\n3. `read_client`"),
        (f"call `{READ}`", f"invoke `{READ}`"),
        ("if the record matches {", "if the record matches {oops "),
        ("(finish): stop.", "(finish): stop here."),
        ("(ask)", "(script)"),
    ],
    ids=["preamble", "numbering", "wording", "predicate", "finish", "kind"],
)
def test_a_document_edited_into_something_no_drawing_produces_is_refused(
    before: str, after: str
) -> None:
    """**M20.2.2.** The reader exists to prove the writer loses nothing, and a reader that
    guessed at a hand-edited line would prove nothing about the writer. Each edit here is a
    shape the writer never produces.

    Deleting this lets an edited document read back as a drawing somebody would then trust.
    """
    text = a_document()
    edited = text.replace(before, after)

    assert edited != text
    with pytest.raises(BuilderError):
        procedure_from_skill_markdown(edited)


def test_the_drawing_the_console_canvas_sends_is_one_this_module_reads_and_writes() -> None:
    """**M20.2.2.** Where the two halves meet. `console/tests/procedure-canvas.test.tsx` asserts
    that drawing on the canvas produces this file, and this asserts the file is a drawing within
    the bound that writes a document reading back as itself, with every kind on it.

    Deleting this lets the console and the server each pass against their own idea of the
    wire, which is how a canvas ships that the server refuses every drawing from.
    """
    payload = json.loads(CANVAS_FIXTURE.read_text(encoding="utf-8"))
    offered = {node["tool"] for node in payload["nodes"] if node["kind"] == "tool_call"}
    procedure = read_drawing(payload, drawable_tools=offered)
    text = skill_markdown(procedure, name=NAME, description=DESCRIPTION)

    assert procedure_from_skill_markdown(text) == procedure
    assert {node.kind for node in procedure.nodes} == set(NodeKind)
