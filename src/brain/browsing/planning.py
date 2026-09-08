"""The planner, and the reason it is unable to read a page rather than asked not to.

M19.2.1 asks for a planner that never reads page content, **asserted by test**. The word
doing the work is asserted. A planner that is handed a page and instructed to ignore the
instructions in it is a model taking instructions from an attacker with a login session
attached, and no amount of prompt text changes that, because the prompt and the attack
arrive through the same channel and the model has no way to tell them apart. So the refusal
here is structural, and it has three legs. Each one is checkable by a parser, and
`brain.browsing.shape` is the parser.

**One: the planner's inputs all exist before the run does.** `plan` takes a `PlanRequest`
and a `TargetRegistry`. A request is a goal somebody typed and the names of a target and a
surface; a registry is configuration a person wrote and a reviewer approved. Neither can
contain anything a page said, because both are complete before a browser starts. The
transitive field types of both are walked by `shape.plan_inputs_are_declared`, so smuggling
page text in as a new field on `Goal` fails a test rather than passing review.

**Two: this module cannot name the type page content arrives in.** Every page-derived value
in this package lives in `brain.browsing.observation`, and this module does not import it,
directly or through any module in the package. That is an import-graph question, which is
decided by parsing rather than by reading. `shape.forbidden_imports` decides it.

**Three, and this is the one that survives a future author.** No function anywhere in this
package takes a page-derived type and returns a plan, a step or a rubric. That is the shape
of the edit somebody makes in six months, in good faith, called `replan_from_snapshot`,
because the first attempt failed and the page had the answer on it. Legs one and two are
about this module as it stands; leg three is about the module nobody has written yet, and it
is checked over the whole package by `shape.nothing_turns_page_content_into_a_plan`.

**What this does not prove, said plainly.** There is no model call here. `plan` expands a
declared surface map into steps and is a pure function, so today the strongest possible
statement is true trivially. The seam where that changes is `render_brief`, which is the one
function that builds the text a planner model would be given, and it is written now, unused
by a model, precisely so that the structural checks have a single function to guard when one
arrives. A second seam added beside it is what the checks in `shape` are looking for.

Rejected: letting the planner see a redacted or summarised page. A summary of an attacker's
text is an attacker's text with fewer words, and the summariser is a model reading the page,
so the boundary moves rather than holds. There is no safe amount of page content in a
planner and the module structure says so by having no way to express any.

Rejected: replanning on failure. A run whose plan does not fit the page fails and reports
what it could not find. That is the staleness cost `brain.browsing.targets` names, paid
here.

Task ids: M19.2.1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from brain.browsing.targets import Target, TargetRegistry, Verb, is_write

#: Why the refusal is a shape rather than an instruction.
A_PLANNER_TOLD_TO_IGNORE_THE_PAGE_HAS_ALREADY_READ_IT: Final = (
    "Prompt text is not a boundary. An instruction to disregard what the page says arrives "
    "in the same context window as the page, from a channel the model cannot rank, and the "
    "page can say the same kind of thing back. The only version of this that holds is one "
    "where page content cannot be assembled into the planner's input at all, which is a "
    "property of the types and the import graph rather than of the wording."
)

#: Why a seam nothing uses is written anyway.
THE_SEAM_IS_WRITTEN_BEFORE_THE_MODEL_ARRIVES: Final = (
    "There is no model call in this package, so every structural claim about what a planner "
    "may read is currently true of a pure function and would be true of an empty file. "
    "`render_brief` exists so that the day a model is added there is one obvious place to "
    "add it, already covered by the checks, rather than a new function assembling a prompt "
    "from whatever was to hand."
)

#: The longest goal a person may write. Long enough for a sentence with conditions in it,
#: short enough that a goal is not a channel for pasting a document into the planner.
MAX_GOAL = 500


class PlanningError(Exception):
    """A plan was asked for in terms that cannot be turned into declared steps."""


@dataclass(frozen=True)
class Goal:
    """What somebody asked for, in their words, fixed before the run starts.

    Frozen and carried by value through the whole run. A goal that could be amended mid-run
    is a goal the run can amend, and the run is the party whose judgement is in question.
    """

    text: str
    asked_by: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            msg = "a goal with no text cannot be planned against or graded against"
            raise PlanningError(msg)
        if len(self.text) > MAX_GOAL:
            msg = (
                f"a goal of {len(self.text)} characters is a document rather than a goal; "
                f"the limit is {MAX_GOAL} and it is there because the goal is the only "
                "free text that reaches the planner"
            )
            raise PlanningError(msg)
        if not self.asked_by.strip():
            msg = "a goal nobody asked for has no reach to be compiled against"
            raise PlanningError(msg)


@dataclass(frozen=True)
class PlanRequest:
    """The whole of a planner's input: a goal, and which declared surfaces to use.

    Surfaces are named rather than described, so the description comes from the registry
    where a person wrote it. A request carrying its own surface definition would be a caller
    declaring a target at call time, which is the same widening the registry exists to stop.
    """

    goal: Goal
    target: str
    surfaces: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.target.strip():
            msg = "a plan request names no target, so there is no allowlist to plan inside"
            raise PlanningError(msg)
        if not self.surfaces:
            msg = (
                "a plan request names no surfaces; a planner free to choose from every "
                "declared surface is a planner choosing where to go, which is the decision "
                "the declaration was supposed to have made already"
            )
            raise PlanningError(msg)
        if len(self.surfaces) != len(set(self.surfaces)):
            msg = f"plan request for {self.target!r} names one surface twice"
            raise PlanningError(msg)


@dataclass(frozen=True)
class Step:
    """One declared thing to do, on one declared surface.

    There is no element reference here and that absence is deliberate. A reference is minted
    by the runner from a tree it has seen, so a plan that named one would be a plan written
    after looking. The enforcer matches an action to a step by surface and verb, and
    validates the reference against the snapshot instead.
    """

    surface: str
    verb: Verb
    #: The credential this step needs, named and never valued. See `brain.browsing.credentials`.
    placeholder: str = ""

    def is_write(self) -> bool:
        return is_write(self.verb)


@dataclass(frozen=True)
class Plan:
    """Everything a run intends to do, before it may do any of it."""

    request: PlanRequest
    steps: tuple[Step, ...]

    def writes(self) -> tuple[Step, ...]:
        return tuple(step for step in self.steps if step.is_write())

    def surfaces(self) -> frozenset[str]:
        return frozenset(step.surface for step in self.steps)


def plan(request: PlanRequest, registry: TargetRegistry) -> Plan:
    """Expand a request into steps, using only what a person declared.

    Deterministic, and the determinism is not the point: what matters is that every argument
    was complete before a browser existed. Each named surface contributes an `OPEN` and then
    whichever of its declared verbs it admits, in a fixed order, so that two plans for the
    same request are the same plan and an envelope digest means something.

    A surface the target does not declare is refused rather than skipped. Skipping produces a
    shorter plan that looks like a successful one, and the run then reports that it could not
    achieve the goal for a reason nobody can find.
    """
    target = registry.get(request.target)
    if target is None:
        msg = (
            f"no target named {request.target!r} is declared; a run cannot be planned "
            "against a system nobody has described and reviewed"
        )
        raise PlanningError(msg)
    steps: list[Step] = []
    for name in request.surfaces:
        surface = target.surface(name)
        if surface is None:
            msg = (
                f"target {target.name!r} declares no surface {name!r}; refused rather than "
                "skipped, because a quietly shorter plan fails later and blames the goal"
            )
            raise PlanningError(msg)
        for verb in (Verb.OPEN, Verb.READ, Verb.TYPE, Verb.CLICK, Verb.SUBMIT, Verb.UPLOAD):
            if surface.admits(verb):
                steps.append(Step(surface=name, verb=verb))
    return Plan(request=request, steps=tuple(steps))


def render_brief(request: PlanRequest, target: Target) -> str:
    """The text a planner model would be given, and the only place such text is assembled.

    Written before there is a model to give it to, for the reason
    `THE_SEAM_IS_WRITTEN_BEFORE_THE_MODEL_ARRIVES` states. Its signature is the assertion:
    a goal and a declaration, and nothing that a page could have reached.

    Every declared value it prints came from configuration. That includes the surface paths,
    which look like the sort of thing scraped from a site and are not: they are in the
    registry because somebody wrote them there.
    """
    lines = [
        f"Goal: {request.goal.text}",
        f"Asked by: {request.goal.asked_by}",
        f"Target: {target.name}",
        "Declared surfaces:",
    ]
    for name in request.surfaces:
        surface = target.surface(name)
        if surface is None:
            lines.append(f"  {name}: not declared")
            continue
        verbs = ", ".join(sorted(verb.value for verb in surface.verbs))
        lines.append(f"  {name}: {surface.origin}{surface.path} [{verbs}]")
    return "\n".join(lines)
