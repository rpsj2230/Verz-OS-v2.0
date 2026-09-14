"""A procedure somebody drew, what bounds it, and the SKILL.md that is the same thing written down.

`brain.builder.compose` declares the vocabulary a procedure is drawn in and declined to emit a
SKILL.md, for a reason worth keeping: a document emitted from a graph nobody can draw is a
serialiser for an absent surface. The surface is `console/src/components/ProcedureCanvas.tsx`
now, and this is the half of M20.2.2 that has to live on the server: the edges, the bound,
and the document.

**A drawing is bounded three ways, and each bound is a refusal rather than a warning.**

*Which nodes exist.* The five kinds and nothing else, refused by `compose.assert_drawable`
before this module reads a single field, and exactly one `start`. The vocabulary is not
restated here.

*That every run ends.* A drawing is acyclic, every step is reachable from the start, and every
step has each exit its kind requires, so every path ends at a `finish` and no run visits a
step twice. **A loop on a canvas is a `while` with no bound on it.** The only conditional is a
scope predicate so that a drawing is not a small programming language
(`A_CONDITIONAL_THAT_IS_NOT_A_SCOPE_IS_A_SMALL_PROGRAMMING_LANGUAGE`), and a back edge would
hand that language the half it is missing. With no cycle, a run takes at most as many steps as
were drawn, which is what makes the third bound a bound on runs and not only on drawings.
Depth is therefore not a figure of its own: no path is longer than the drawing it is in.

*How many steps.* `MAX_STEPS`, which is `brain.gate.caches.MAX_PLAN_TOOLS` imported rather than
restated. The architecture asks for "a small node set" and names no number, and the gate
already has one for the same question: a cached plan naming more tools than that "is not a
plan, it is a model looping". A procedure is a plan an author drew instead of one a model
wrote, so **two figures for "too long to be a plan" that disagree are one figure that is
wrong**, and the wrong one would be whichever the next person tuned. It counts every node,
start and finish included, because the bound is on what an author draws and a reviewer reads,
and a person counting the boxes on a canvas counts those too.

**The SKILL.md is the drawing written down, and it reads back as the same drawing.**
`skill_markdown` writes one numbered line per step, each naming the step it goes to, and
`procedure_from_skill_markdown` reads the text back into a `Procedure` that compares equal to
the one drawn. The round trip is the point rather than a convenience: it is the only way to
state "nothing drawn is missing from the document and nothing in the document was not drawn"
as a test rather than as a hope. Two refusals follow from it.

*What the document cannot say, the drawing may not hold.* A key outside `NODE_KEYS`,
`EDGE_KEYS` or `DRAWING_KEYS` is refused rather than ignored, and a position is the case that
matters: a canvas where steps could be dragged would carry an arrangement the document drops,
and an author who arranged steps to mean an order would find the order gone. Order comes from
edges and from nothing else, which is why the console lays a procedure out rather than letting
anybody place a step. An unreachable step is refused for the same reason: a walk from the start
never meets it, so it would be drawn and not written.

*The tools line is the calls that were drawn.* `tools:` is derived from the `tool_call` steps,
and a document whose line disagrees with its steps is refused on the way back in. The line is
what a skill's card and `brain.tools.skills.unknown_tools` read, so a hand-edited line leaving
a call out is a call that nobody reviewing the card sees.

**The document is checked by the parser that decides what a skill is.** `skill_markdown` hands
its own output to `brain.tools.skills.skill_from_markdown` and refuses when the name, the
description or the tools do not survive. A frontmatter value opening with a bracket is a list
to that parser, and a serialiser with its own opinion about the format would write skills the
importer then refuses.

**A tool the canvas did not offer is one refusal whatever the reason.** `read_drawing` is
handed the tools this author may draw, resolved by whoever holds the catalogue, and it has no
parameter for the registry. A tool that exists and is not theirs and a tool that does not
exist at all are refused in the same words because nothing here can tell them apart, which is
DENIED and ABSENT kept indistinguishable by construction rather than by careful wording.

**A branch that cannot fail is refused.** A predicate admitting every row sends every run the
same way, so its other exit leads to steps no run reaches, written into a reviewed document as
though they did something.

**Rejected: the serialiser in the console.** It is where the drawing is, and it is on the wrong
side of the trust boundary. A SKILL.md assembled in a browser and posted is intent in exactly
the sense `A_AUTHORED_LIST_IS_INTENT_AND_THE_TOOLS_ARE_THE_AUTHORITY` means, so the server would
re-derive it from the drawing anyway, and two serialisers are two answers to what a drawing
says. The console sends the drawing and shows the document it is given back.

**Rejected: referring to steps by number.** A number reads well and changes on every insertion,
so one added step would rewrite every line of a reviewed document and the diff a reviewer reads
would be noise. A line points at a step by its id; the number is presentation, and the reader
checks only that the numbers run in order.

Scope: domain logic. Nothing here opens a connection, renders anything or reads a clock. No
route hands a drawing to this module yet.

Task ids: M20.2.2
"""

from __future__ import annotations

import enum
import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from pydantic import ValidationError

from brain.agents.template import PROMPT_CHARS
from brain.builder.compose import CONDITIONAL_KIND, BuilderError, Node, NodeKind, assert_drawable
from brain.core.envelope import OBJECT_NAME_PATTERN
from brain.core.scope import Scope
from brain.gate.caches import MAX_PLAN_TOOLS
from brain.tools.skills import Skill, SkillError, skill_from_markdown

# ------------------------------------------------------------------ written-down reasons
#: Why the bound is the gate's bound on a plan rather than a number chosen here.
A_PROCEDURE_IS_NO_LONGER_THAN_A_PLAN: Final = (
    "A procedure is a plan somebody drew rather than one a model wrote, and the gate already "
    "says how long a plan may be: past MAX_PLAN_TOOLS it is not a plan but a model looping. "
    "A drawing holds no more steps than that, counted over every node, because two figures "
    "for too long to be a plan that disagree are one figure that is wrong."
)

#: Why a drawing may not loop.
A_LOOP_ON_A_CANVAS_IS_A_WHILE_WITH_NO_BOUND: Final = (
    "A step leading back to an earlier one makes the procedure a loop whose exit is a "
    "predicate, which is the small programming language the scope grammar exists to keep off "
    "a drawing surface. Without a cycle no run takes a step twice, so the number of steps "
    "drawn bounds every run and not only the drawing."
)

#: Why an unknown key, a position or an unreachable step is refused rather than dropped.
WHAT_THE_DOCUMENT_CANNOT_SAY_THE_DRAWING_MAY_NOT_HOLD: Final = (
    "The SKILL.md is the drawing written down, so anything drawn that the document has no way "
    "to say would be lost between the canvas and the skill, and the author would approve a "
    "document that is not what they drew. A position is the case that matters, because an "
    "arrangement meant as an order would vanish. An unknown key and a step no walk from the "
    "start reaches are therefore refused where they arrive."
)

#: Why a tool outside the author's catalogue gets one sentence whatever the reason.
A_TOOL_THE_CANVAS_DID_NOT_OFFER_IS_ONE_REFUSAL: Final = (
    "The tools an author may draw are handed in and the registry is not, so a tool that exists "
    "and is not theirs and a tool that does not exist are refused in the same words, because "
    "nothing here can tell them apart. A refusal that said which would tell an author which "
    "tool names are real in an installation they may not see all of."
)

#: Why a branch whose predicate admits everything is refused.
A_BRANCH_THAT_CANNOT_FAIL_DECIDES_NOTHING: Final = (
    "A predicate that admits every row sends every run the same way, so the other exit leads "
    "to steps no run reaches, written into the document as though they did something. A "
    "reviewer reading it would be reviewing a path that cannot happen."
)

# ------------------------------------------------------------------------------ the bound
#: The most steps a procedure may hold, start and finish included.
#:
#: Imported rather than written as a number. See `A_PROCEDURE_IS_NO_LONGER_THAN_A_PLAN`.
MAX_STEPS: Final = MAX_PLAN_TOOLS

#: What a step id may be: the object-name grammar, imported rather than restated, because an id
#: is written into every line that points at its step and must survive being backquoted there.
STEP_ID_RE: Final = re.compile(OBJECT_NAME_PATTERN)

#: The keys a node may carry. See `WHAT_THE_DOCUMENT_CANNOT_SAY_THE_DRAWING_MAY_NOT_HOLD`.
NODE_KEYS: Final[frozenset[str]] = frozenset({"id", "kind", "tool", "predicate", "prompt"})

#: The keys an edge may carry.
EDGE_KEYS: Final[frozenset[str]] = frozenset({"from", "to", "way"})

#: The keys a drawing may carry.
DRAWING_KEYS: Final[frozenset[str]] = frozenset({"nodes", "edges"})


class Way(enum.StrEnum):
    """Which way out of a step an edge leaves by.

    Three, and two of them belong to a branch. An edge carries its way rather than a label,
    because "which of a branch's two arrows is which" is part of what was drawn: a canvas that
    told them apart by position, the first arrow meaning "holds", would carry the most
    important fact on the drawing in a place the document cannot see.
    """

    #: The one way out of a start, a tool call and a question.
    NEXT = "next"
    #: A branch whose predicate matched.
    HOLDS = "holds"
    #: A branch whose predicate did not.
    OTHERWISE = "otherwise"


#: The ways out of each kind, every one of them required. A finish has none.
WAYS: Final[Mapping[NodeKind, tuple[Way, ...]]] = MappingProxyType(
    {
        NodeKind.START: (Way.NEXT,),
        NodeKind.TOOL_CALL: (Way.NEXT,),
        NodeKind.BRANCH: (Way.HOLDS, Way.OTHERWISE),
        NodeKind.ASK: (Way.NEXT,),
        NodeKind.FINISH: (),
    }
)

#: The first line of a drawn skill's body, and how the reader knows a document was drawn.
PREAMBLE: Final = "Follow these steps from the first. Each one names the step that comes after it."


@dataclass(frozen=True, order=True)
class Edge:
    """One arrow: from a step, by one of its ways, to another step."""

    source: str
    way: Way
    target: str


@dataclass(frozen=True)
class Procedure:
    """A drawing that is within the bound, in the order its document lists it.

    **A `Procedure` that exists is one that was checked.** The bound is enforced in
    `__post_init__` rather than in the reader, so a procedure read from a canvas, read back out
    of a SKILL.md and built by hand in a test are held to one rule, and there is no second
    constructor that skips it.

    The nodes are stored in step order and the edges sorted, so two procedures drawing the same
    graph compare equal however their steps arrived. That equality is what the round trip
    through the document is asserted with.
    """

    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]

    def __post_init__(self) -> None:
        nodes, edges = _checked(self.nodes, self.edges)
        # The dataclass idiom for normalising a frozen instance in `__post_init__`, and not a
        # way round the freeze: nothing outside this method can reach the attribute.
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "edges", edges)


# ------------------------------------------------------------------------ checking a graph
def _check_step(node: Node) -> None:
    """The refusals that are about one step on its own, beyond what `Node` already makes."""
    if not STEP_ID_RE.match(node.node_id):
        msg = (
            f"step id {node.node_id!r} is not a lowercase name, and every line of the SKILL.md "
            "points at a step by its id"
        )
        raise BuilderError(msg)
    if node.kind is NodeKind.ASK and not node.prompt.strip():
        msg = f"step {node.node_id!r} asks the person nothing, which is a pause nobody can answer"
        raise BuilderError(msg)
    if node.kind is NodeKind.ASK and len(node.prompt) > PROMPT_CHARS:
        msg = (
            f"step {node.node_id!r} asks a question longer than the {PROMPT_CHARS} characters a "
            "template may ask a person"
        )
        raise BuilderError(msg)
    if node.predicate is not None and node.predicate.is_unrestricted():
        msg = f"branch {node.node_id!r} cannot fail. {A_BRANCH_THAT_CANNOT_FAIL_DECIDES_NOTHING}"
        raise BuilderError(msg)


def _a_loop(following: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """One cycle in the graph as the steps along it, or nothing.

    Recursive, which is safe only because the size bound is checked first: no path through a
    drawing that got this far is longer than `MAX_STEPS`.
    """
    state: dict[str, bool] = {}
    path: list[str] = []

    def visit(step: str) -> tuple[str, ...]:
        state[step] = True
        path.append(step)
        for target in following[step]:
            if state.get(target) is True:
                return tuple(path[path.index(target) :])
            if target not in state:
                found = visit(target)
                if found:
                    return found
        path.pop()
        state[step] = False
        return ()

    for step in following:
        if step not in state:
            found = visit(step)
            if found:
                return found
    return ()


def _step_order(start: str, following: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """Every step reachable from the start, each after every step that leads to it.

    A topological order, with ties broken by the order a walk from the start first meets each
    step, so the document reads from the top and a branch's `holds` side is listed before its
    `otherwise` side. Steps not reachable from the start are not in it, which is how the caller
    finds them.
    """
    met: dict[str, int] = {}
    stack = [start]
    while stack:
        step = stack.pop()
        if step in met:
            continue
        met[step] = len(met)
        stack.extend(reversed(following[step]))

    waiting = dict.fromkeys(met, 0)
    for step in met:
        for target in following[step]:
            waiting[target] += 1

    ready = [start]
    order: list[str] = []
    while ready:
        ready.sort(key=met.__getitem__)
        step = ready.pop(0)
        order.append(step)
        for target in following[step]:
            waiting[target] -= 1
            if waiting[target] == 0:
                ready.append(target)
    return tuple(order)


def _checked(
    nodes: Sequence[Node], edges: Sequence[Edge]
) -> tuple[tuple[Node, ...], tuple[Edge, ...]]:
    """The nodes in step order and the edges sorted, or the first refusal the graph earns.

    The size bound is checked first and that order is load-bearing: everything after it walks
    the graph, and the walk is bounded because the graph is.
    """
    if len(nodes) > MAX_STEPS:
        msg = (
            f"this procedure has {len(nodes)} steps and a procedure holds at most {MAX_STEPS}. "
            f"{A_PROCEDURE_IS_NO_LONGER_THAN_A_PLAN}"
        )
        raise BuilderError(msg)

    by_id: dict[str, Node] = {}
    for node in nodes:
        _check_step(node)
        if node.node_id in by_id:
            msg = f"two steps are called {node.node_id!r}, so an arrow to it points at both"
            raise BuilderError(msg)
        by_id[node.node_id] = node

    starts = [node.node_id for node in nodes if node.kind is NodeKind.START]
    if len(starts) != 1:
        msg = (
            "a procedure has exactly one start, because a run begins in one place and a second "
            "start is a second procedure drawn on the same canvas"
        )
        raise BuilderError(msg)

    following: dict[str, list[str]] = {step: [] for step in by_id}
    taken: set[tuple[str, Way]] = set()
    for edge in sorted(edges):
        if edge.source not in by_id or edge.target not in by_id:
            msg = (
                f"an arrow from {edge.source!r} to {edge.target!r} names a step that is not "
                "drawn, and an arrow ending nowhere on an authoring canvas is a broken drawing"
            )
            raise BuilderError(msg)
        source = by_id[edge.source]
        if edge.way not in WAYS[source.kind]:
            msg = (
                f"step {edge.source!r} is a {source.kind.value}, which does not leave by "
                f"{edge.way.value}"
            )
            raise BuilderError(msg)
        if (edge.source, edge.way) in taken:
            msg = (
                f"step {edge.source!r} leaves by {edge.way.value} twice, so which way a run goes "
                "from it would be a guess"
            )
            raise BuilderError(msg)
        taken.add((edge.source, edge.way))
        following[edge.source].append(edge.target)

    for node in nodes:
        for way in WAYS[node.kind]:
            if (node.node_id, way) not in taken:
                msg = (
                    f"step {node.node_id!r} never leaves by {way.value}, so a run that reaches "
                    "it stops somewhere that is not a finish"
                )
                raise BuilderError(msg)

    loop = _a_loop(following)
    if loop:
        msg = (
            f"steps {' then '.join(loop)} lead back to {loop[0]!r}. "
            f"{A_LOOP_ON_A_CANVAS_IS_A_WHILE_WITH_NO_BOUND}"
        )
        raise BuilderError(msg)

    order = _step_order(starts[0], following)
    unreachable = sorted(set(by_id) - set(order))
    if unreachable:
        msg = (
            f"no path from the start reaches {unreachable}. "
            f"{WHAT_THE_DOCUMENT_CANNOT_SAY_THE_DRAWING_MAY_NOT_HOLD}"
        )
        raise BuilderError(msg)

    return tuple(by_id[step] for step in order), tuple(sorted(edges))


# ------------------------------------------------------------------ reading a drawing
def _closed(entry: Mapping[Any, Any], allowed: frozenset[str], what: str) -> None:
    """Refuse a key the document has no way to say."""
    unknown = sorted(str(key) for key in entry if key not in allowed)
    if unknown:
        msg = (
            f"{what} carries {unknown}, which the SKILL.md has no way to say. "
            f"{WHAT_THE_DOCUMENT_CANNOT_SAY_THE_DRAWING_MAY_NOT_HOLD}"
        )
        raise BuilderError(msg)


def _text(entry: Mapping[str, Any], key: str) -> str:
    """A string field off an untrusted object, or the empty string when it is absent."""
    value = entry.get(key, "")
    if not isinstance(value, str):
        msg = f"{key!r} in a drawing is text, and this one is {type(value).__name__}"
        raise BuilderError(msg)
    return value


def _predicate(value: object, step: str) -> Scope | None:
    """A branch's predicate as the scope grammar reads it, or None when there is none."""
    if value is None:
        return None
    try:
        return Scope.model_validate(value)
    except ValidationError as exc:
        msg = f"the predicate on step {step!r} is not a scope predicate: {exc}"
        raise BuilderError(msg) from exc


def _node_from(raw: Mapping[str, Any], drawable_tools: Collection[str]) -> Node:
    """One node off the wire, after `assert_drawable` has refused any kind outside the five."""
    _closed(raw, NODE_KEYS, f"step {raw.get('id')!r}")
    step = _text(raw, "id")
    node = Node(
        node_id=step,
        kind=NodeKind(raw["kind"]),
        tool=_text(raw, "tool"),
        predicate=_predicate(raw.get("predicate"), step),
        prompt=_text(raw, "prompt"),
    )
    if node.kind is NodeKind.TOOL_CALL and node.tool not in drawable_tools:
        msg = (
            f"step {step!r} calls {node.tool!r}, which is not a tool this canvas offers. "
            f"{A_TOOL_THE_CANVAS_DID_NOT_OFFER_IS_ONE_REFUSAL}"
        )
        raise BuilderError(msg)
    return node


def _edge_from(raw: Mapping[str, Any]) -> Edge:
    """One edge off the wire."""
    _closed(raw, EDGE_KEYS, "an arrow")
    way = raw.get("way")
    if not isinstance(way, str) or way not in {one.value for one in Way}:
        msg = f"an arrow leaves by {way!r}, which is not one of {[one.value for one in Way]}"
        raise BuilderError(msg)
    return Edge(source=_text(raw, "from"), way=Way(way), target=_text(raw, "to"))


def read_drawing(payload: object, *, drawable_tools: Collection[str]) -> Procedure:
    """The procedure a canvas sent, checked against every bound, or a refusal (M20.2.2).

    `payload` is untrusted JSON from a surface outside this repository. `drawable_tools` is the
    set of tool names this author may put on a canvas, resolved by whoever holds the catalogue
    and handed in, for the reason `compose.derive` takes its definitions: the case worth
    testing is a tool that is not offered, and it cannot be reached through a module that opens
    the registry to find out. See `A_TOOL_THE_CANVAS_DID_NOT_OFFER_IS_ONE_REFUSAL`.
    """
    if not isinstance(payload, Mapping):
        msg = "a drawing is an object carrying nodes and edges"
        raise BuilderError(msg)
    _closed(payload, DRAWING_KEYS, "the drawing")
    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        msg = "a drawing carries a list of nodes and a list of edges"
        raise BuilderError(msg)
    if not all(isinstance(one, Mapping) for one in [*raw_nodes, *raw_edges]):
        msg = "every node and every edge in a drawing is an object"
        raise BuilderError(msg)
    # The two doors `compose` keeps, before a single field is read off a node: a kind outside
    # the five, and a permitted kind carrying a body.
    assert_drawable(raw_nodes)
    return Procedure(
        nodes=tuple(_node_from(raw, drawable_tools) for raw in raw_nodes),
        edges=tuple(_edge_from(raw) for raw in raw_edges),
    )


# ------------------------------------------------------------------ writing the document
def tools_called(procedure: Procedure) -> tuple[str, ...]:
    """The tools the steps call, sorted and each once, as a skill's tools line holds them."""
    return tuple(sorted({node.tool for node in procedure.nodes if node.kind is NodeKind.TOOL_CALL}))


def _predicate_text(predicate: Scope) -> str:
    """A predicate in the one spelling that reads back into an equal scope."""
    return json.dumps(predicate.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _line(node: Node, ways: Mapping[tuple[str, Way], str]) -> str:
    """One step as a line of the document, less its number."""
    head = f"`{node.node_id}` ({node.kind.value}): "
    if node.kind is NodeKind.START:
        return f"{head}go to `{ways[(node.node_id, Way.NEXT)]}`."
    if node.kind is NodeKind.TOOL_CALL:
        return f"{head}call `{node.tool}`, then go to `{ways[(node.node_id, Way.NEXT)]}`."
    if node.kind is NodeKind.ASK:
        question = json.dumps(node.prompt, ensure_ascii=False)
        return f"{head}ask the person {question}, then go to `{ways[(node.node_id, Way.NEXT)]}`."
    if node.kind is CONDITIONAL_KIND and node.predicate is not None:
        return (
            f"{head}if the record matches {_predicate_text(node.predicate)}, "
            f"go to `{ways[(node.node_id, Way.HOLDS)]}`; "
            f"otherwise go to `{ways[(node.node_id, Way.OTHERWISE)]}`."
        )
    return f"{head}stop."


def _skill(text: str) -> Skill:
    """The skill the importer would build from this text, or a builder refusal saying why not."""
    try:
        return skill_from_markdown(text)
    except SkillError as exc:
        msg = f"this is not a SKILL.md the skill importer accepts: {exc}"
        raise BuilderError(msg) from exc


def skill_markdown(procedure: Procedure, *, name: str, description: str) -> str:
    """The SKILL.md a drawing is, written from the drawing and from nothing else (M20.2.2).

    The name and description are the only inputs that did not come off the canvas, and they
    are checked by the importer's own parser on the way out, so a value the format would
    change is refused here rather than imported as something else.
    """
    tools = tools_called(procedure)
    ways = {(edge.source, edge.way): edge.target for edge in procedure.edges}
    lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
        f"tools: [{', '.join(tools)}]",
        "---",
        PREAMBLE,
        "",
        *(f"{number}. {_line(node, ways)}" for number, node in enumerate(procedure.nodes, 1)),
    ]
    text = "\n".join(lines) + "\n"
    skill = _skill(text)
    if (skill.name, skill.description, skill.tools) != (name, description, tools):
        msg = (
            "the name or the description does not survive the SKILL.md format unchanged, so the "
            "skill an importer would build is not the one described here; a value opening with "
            "a bracket is read as a list, and surrounding space is trimmed"
        )
        raise BuilderError(msg)
    return text


# ------------------------------------------------------------------ reading it back
_STEP_LINE: Final = re.compile(
    r"^(?P<number>[1-9][0-9]*)\. `(?P<id>[^`]+)` \((?P<kind>[a-z_]+)\): (?P<rest>.*)$"
)
_START_REST: Final = re.compile(r"^go to `(?P<next>[^`]+)`\.$")
_CALL_REST: Final = re.compile(r"^call `(?P<tool>[^`]+)`, then go to `(?P<next>[^`]+)`\.$")
_ASK_REST: Final = re.compile(r'^ask the person (?P<prompt>".*"), then go to `(?P<next>[^`]+)`\.$')
_BRANCH_REST: Final = re.compile(
    r"^if the record matches (?P<predicate>\{.*\}), go to `(?P<holds>[^`]+)`; "
    r"otherwise go to `(?P<otherwise>[^`]+)`\.$"
)
_FINISH_REST: Final = "stop."


def _match(pattern: re.Pattern[str], rest: str, step: str) -> re.Match[str]:
    found = pattern.match(rest)
    if found is None:
        msg = f"step {step!r} is not written the way a drawn step is written: {rest!r}"
        raise BuilderError(msg)
    return found


def _json(text: str, step: str) -> object:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"step {step!r} carries {text!r}, which is not JSON"
        raise BuilderError(msg) from exc
    return value


def _read_step(step: str, kind: NodeKind, rest: str) -> tuple[Node, tuple[Edge, ...]]:
    """One line of the document as the node it describes and the arrows leaving it."""
    if kind is NodeKind.START:
        found = _match(_START_REST, rest, step)
        return Node(node_id=step, kind=kind), (Edge(step, Way.NEXT, found["next"]),)
    if kind is NodeKind.TOOL_CALL:
        found = _match(_CALL_REST, rest, step)
        node = Node(node_id=step, kind=kind, tool=found["tool"])
        return node, (Edge(step, Way.NEXT, found["next"]),)
    if kind is NodeKind.ASK:
        found = _match(_ASK_REST, rest, step)
        # The pattern only admits text that opens and closes with a quote, so what `json.loads`
        # returns is a string or it raised; `str` names the type rather than converting.
        prompt = str(_json(found["prompt"], step))
        node = Node(node_id=step, kind=kind, prompt=prompt)
        return node, (Edge(step, Way.NEXT, found["next"]),)
    if kind is NodeKind.BRANCH:
        found = _match(_BRANCH_REST, rest, step)
        predicate = _predicate(_json(found["predicate"], step), step)
        node = Node(node_id=step, kind=kind, predicate=predicate)
        return node, (
            Edge(step, Way.HOLDS, found["holds"]),
            Edge(step, Way.OTHERWISE, found["otherwise"]),
        )
    if rest != _FINISH_REST:
        msg = f"step {step!r} is a finish and says {rest!r} rather than stopping"
        raise BuilderError(msg)
    return Node(node_id=step, kind=kind), ()


def procedure_from_skill_markdown(text: str) -> Procedure:
    """The drawing a SKILL.md was written from, read back out of it, or a refusal (M20.2.2).

    It exists to prove `skill_markdown` loses nothing and adds nothing, and it refuses a
    document that was edited into something no drawing produces rather than guessing what the
    edit meant.
    """
    skill = _skill(text)
    lines = skill.body.split("\n")
    if lines[0] != PREAMBLE:
        msg = "this SKILL.md was not written from a drawing, so there is no drawing to read back"
        raise BuilderError(msg)

    nodes: list[Node] = []
    edges: list[Edge] = []
    for number, line in enumerate((one for one in lines[1:] if one), 1):
        step = _STEP_LINE.match(line)
        if step is None or int(step["number"]) != number:
            msg = f"{line!r} is not step {number} of a drawn procedure"
            raise BuilderError(msg)
        # The vocabulary door again, because a document is edited on its own schedule too.
        assert_drawable([{"kind": step["kind"]}])
        node, leaving = _read_step(step["id"], NodeKind(step["kind"]), step["rest"])
        nodes.append(node)
        edges.extend(leaving)

    procedure = Procedure(nodes=tuple(nodes), edges=tuple(edges))
    if tools_called(procedure) != skill.tools:
        msg = (
            f"the tools line says {list(skill.tools)} and the steps call "
            f"{list(tools_called(procedure))}; the line is what a skill's card shows, so a call "
            "it leaves out is a call nobody reviewing the card sees"
        )
        raise BuilderError(msg)
    return procedure
