"""A workflow is stored, versioned step data, and it is checked before it can be saved.

An administrator defines a multi-step workflow in the console and an agent assigned it runs it with
nobody performing each step (M17.6.1). This module is the shape of that data and the one reader of
it. `brain.orchestration.workflow_run` runs what this reads, and `brain.workflow_routes` stores it.

**The definition is data and never code, and its vocabulary has no member for judgement.** A step
is a tool, a connector read or a skill. There is nothing that asks a model what to do next, so a
workflow cannot be an ungoverned agent loop with an editor, for the reason
`brain.ops.automation.DETERMINISTIC_ONLY` gives about the canvas. What judgement a workflow needs
is an agent's, reached through a step that is a tool call.

**What a step returns is named, and a later step can read only what an earlier one declared**
(M17.6.3). A step lists its outputs (a name, one of the six kinds `brain.orchestration.contract`
has, and where in the first record the value is). A reference to an output is `{"$ref":
"step.name"}` and `read_definition` refuses one that names a step this one does not follow, an
output nobody declared, or a step that is later in the list. The cheaper design lets a step read the
whole of what an earlier one returned, which makes every step's result an input to every later one
and a record's fields a place to carry data round a column mask. An output has no prose kind for the
reason a subtask has none: see `brain.orchestration.contract.PROSE_IS_NOT_A_CONTRACT`.

**A step runs when a condition over earlier outputs holds, and a skipped step says which**
(M17.6.4). A condition is one comparison from a short named list over one declared output, the shape
needs-rupash 177 decided for an automation's trigger. Free expressions were rejected: a condition
that can compute is a second language to review, and it is the thing that reads a model's output.

**Steps declared parallel start together, and a step that follows them waits for each** (M17.6.5).
Steps are listed in the order they were meant to be read and each lists what it follows (`after`),
which has to be earlier in the list, so the graph has no cycle by construction and no cycle check
to get wrong. A step that is `parallel` starts with the other parallel steps that follow the same
things; the rest of its wave runs one after another.

**Each step carries its own retry and its own failure path** (M17.6.6). Retries are at most
`MOST_RETRIES` with a bounded back-off. A failed step stops the run, or is recorded as a gap and the
run goes on, or hands over to a handler step (a step whose `handles` names it), which runs only
then. A step that changes something (`writes`) is retried only through the idempotency key the
engine hands it, which is the same on every attempt.

**Nothing here decides reach.** A step names a tool, and which tools a run may call and what they
return is decided by the gate at the run's reach when the step runs, as for any call. A definition
that names a tool nobody may call is a definition whose step is refused, and the refusal is stated
as a gap.

Task ids: M17.6.1, M17.6.3, M17.6.4, M17.6.5, M17.6.6
"""

from __future__ import annotations

import enum
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from brain.core.envelope import TOOL_NAME_PATTERN
from brain.ops.automation_piece import RESERVED_ARGUMENT_NAMES
from brain.orchestration.contract import FIELD_NAME_RE, FieldKind

# ------------------------------------------------------------------ written-down reasons
#: Why a step's reads are named and bounded.
A_STEP_READS_ONLY_WHAT_AN_EARLIER_STEP_DECLARED: Final = (
    "A reference names a step this one follows and an output that step declared. Letting a step "
    "read all of an earlier step's result would make every result an input to every later step, "
    "and a record's fields a way to carry data round the mask that governs every other way "
    "to the same information."
)

#: Why a definition has no member for a decision.
A_WORKFLOW_IS_PLUMBING_AND_NOT_JUDGEMENT: Final = (
    "A step is a tool, a connector read or a skill. There is no step that asks a model what to do "
    "next, so a workflow cannot be a second agent runtime with no leash: what needs judgement is "
    "an agent's, reached by a step that calls a tool."
)

#: Limits, stated once.
MOST_STEPS: Final = 24
MOST_RETRIES: Final = 3
MOST_BACKOFF_SECONDS: Final = 60.0
MOST_OUTPUTS: Final = 8
MOST_ARGUMENTS: Final = 16
MOST_DEPTH: Final = 4
NAME_CHARS: Final = 120
LITERAL_CHARS: Final = 200

STEP_ID_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
PATH_RE: Final = re.compile(r"^(?:[0-9]{1,2}\.)?[a-z][a-z0-9_]*$")
TOOL_RE: Final = re.compile(TOOL_NAME_PATTERN)

#: The keys a definition and a step may carry. Closed: a key nobody declared is refused rather than
#: dropped, because an author who sent one believes it did something.
DEFINITION_KEYS: Final = frozenset({"name", "steps"})
STEP_KEYS: Final = frozenset(
    {
        "id",
        "kind",
        "target",
        "arguments",
        "outputs",
        "after",
        "when",
        "parallel",
        "retry",
        "on_failure",
        "handles",
        "writes",
    }
)
OUTPUT_KEYS: Final = frozenset({"name", "kind", "path"})
RETRY_KEYS: Final = frozenset({"limit", "backoff_seconds"})
WHEN_KEYS: Final = frozenset({"ref", "op", "value"})


class WorkflowError(Exception):
    """A definition that cannot be saved, with every reason it cannot."""

    def __init__(self, reasons: Sequence[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons: tuple[str, ...] = tuple(reasons)


class StepKind(enum.StrEnum):
    """Every kind of step. There is no member for a model call, an agent or a decision."""

    TOOL = "tool"
    CONNECTOR_READ = "connector_read"
    SKILL = "skill"


class Op(enum.StrEnum):
    """The comparisons a condition may make. A short named list and no expression language."""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"


class OnFailure(enum.StrEnum):
    """What a step does when it has used its retries."""

    #: The run stops here and is a failure naming this step.
    STOP = "stop"
    #: The step is recorded as a gap and the run goes on.
    CONTINUE = "continue"
    #: The step that `handles` this one runs, and the run goes on.
    HANDLER = "handler"


@dataclass(frozen=True)
class Ref:
    """A named output of an earlier step."""

    step_id: str
    name: str

    def __str__(self) -> str:
        return f"{self.step_id}.{self.name}"


@dataclass(frozen=True)
class Condition:
    """One comparison over one earlier output."""

    ref: Ref
    op: Op
    value: object = None

    def words(self) -> str:
        """The condition as a short line a trace can carry: only the definition's own words."""
        if self.op in (Op.IS_TRUE, Op.IS_FALSE):
            return f"{self.ref} {self.op.value}"
        return f"{self.ref} {self.op.value} {json.dumps(self.value, default=str)}"[:LITERAL_CHARS]


@dataclass(frozen=True)
class Output:
    """A value a step promises, and where in its first record it is."""

    name: str
    kind: FieldKind
    path: str


@dataclass(frozen=True)
class Retry:
    limit: int = 0
    backoff_seconds: float = 0.0


@dataclass(frozen=True)
class Step:
    """One step of a workflow, as `read_definition` admits it."""

    id: str
    kind: StepKind
    target: str
    arguments: Mapping[str, object] = field(default_factory=dict)
    outputs: tuple[Output, ...] = ()
    after: tuple[str, ...] = ()
    when: Condition | None = None
    parallel: bool = False
    retry: Retry = field(default_factory=Retry)
    on_failure: OnFailure = OnFailure.STOP
    handles: str | None = None
    writes: bool = False


@dataclass(frozen=True)
class Definition:
    """A workflow: a name and its steps in the order they were meant to be read."""

    name: str
    steps: tuple[Step, ...]

    def step(self, step_id: str) -> Step:
        for one in self.steps:
            if one.id == step_id:
                return one
        msg = f"this workflow has no step {step_id!r}"
        raise WorkflowError((msg,))

    def waves(self) -> tuple[tuple[str, ...], ...]:
        """The steps in the order they become ready, each wave in the order they were listed."""
        placed: set[str] = set()
        remaining = list(self.steps)
        waves: list[tuple[str, ...]] = []
        while remaining:
            ready = [one for one in remaining if set(one.after) <= placed]
            if not ready:
                msg = "this workflow has a step that follows one that never runs"
                raise WorkflowError((msg,))
            waves.append(tuple(one.id for one in ready))
            placed.update(one.id for one in ready)
            remaining = [one for one in remaining if one.id not in placed]
        return tuple(waves)


def _ancestors(step_id: str, after: Mapping[str, tuple[str, ...]]) -> frozenset[str]:
    found: set[str] = set()
    stack = list(after.get(step_id, ()))
    while stack:
        one = stack.pop()
        if one not in found:
            found.add(one)
            stack.extend(after.get(one, ()))
    return frozenset(found)


def _literal(value: object, depth: int = 0) -> bool:
    """Whether a value is plain data: a string, a number, a boolean, null, or a list or object of
    those, nested at most `MOST_DEPTH` deep. An object's keys are plain words, so a `$ref` is never
    one: a reference is only an argument's whole value."""
    if isinstance(value, bool) or value is None:
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, str):
        return len(value) <= LITERAL_CHARS
    if isinstance(value, list):
        return (
            depth < MOST_DEPTH
            and len(value) <= MOST_ARGUMENTS
            and all(_literal(one, depth + 1) for one in value)
        )
    if isinstance(value, dict):
        return (
            depth < MOST_DEPTH
            and len(value) <= MOST_ARGUMENTS
            and all(
                isinstance(k, str) and re.match(FIELD_NAME_RE, k) and _literal(v, depth + 1)
                for k, v in value.items()
            )
        )
    return False


def _ref_of(raw: object) -> tuple[Ref | None, str]:
    """A reference out of `{"$ref": "step.name"}`, or why it is not one."""
    if not isinstance(raw, str) or raw.count(".") != 1:
        return None, 'a reference is written {"$ref": "step.output"}'
    step_id, name = raw.split(".")
    if not STEP_ID_RE.match(step_id) or not re.match(FIELD_NAME_RE, name):
        return None, "a reference names a step and one of its outputs"
    return Ref(step_id, name), ""


def read_definition(raw: object) -> Definition:
    """Read a stored definition into steps, or refuse it whole with every reason (M17.6.1).

    Takes `object` because it arrives as JSON from a console and is untrusted until read. The
    checks are in the order a reader needs them: the shape, then each step alone, then what the
    steps say about each other (what follows what, who reads which output, who handles whom).
    """
    problems: list[str] = []
    if not isinstance(raw, dict) or set(raw) - DEFINITION_KEYS or "steps" not in raw:
        raise WorkflowError(('a workflow is an object with a "name" and a list of "steps"',))
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > NAME_CHARS:
        problems.append(f"a workflow has a name of at most {NAME_CHARS} characters")
    items = raw["steps"]
    if not isinstance(items, list) or not items or len(items) > MOST_STEPS:
        raise WorkflowError((f"a workflow has between one and {MOST_STEPS} steps", *problems))
    steps: list[Step] = []
    for index, item in enumerate(items):
        one, wrong = _read_step(index, item)
        problems.extend(wrong)
        if one is not None:
            steps.append(one)
    if problems:
        raise WorkflowError(problems)
    problems.extend(_read_together(steps))
    if problems:
        raise WorkflowError(problems)
    return Definition(name=str(name).strip(), steps=tuple(steps))


def _read_step(index: int, item: object) -> tuple[Step | None, list[str]]:
    where = f"step {index + 1}"
    if not isinstance(item, dict):
        return None, [f"{where} is not an object"]
    unknown = sorted(set(item) - STEP_KEYS)
    if unknown:
        return None, [f"{where} carries {unknown}, which no step may hold"]
    problems: list[str] = []
    step_id = item.get("id")
    if not isinstance(step_id, str) or not STEP_ID_RE.match(step_id):
        return None, [f"{where} has an id that is not a short lowercase word"]
    where = f"step {step_id!r}"
    try:
        kind = StepKind(str(item.get("kind")))
    except ValueError:
        return None, [f"{where} has a kind that is not one of {[k.value for k in StepKind]}"]
    target = item.get("target")
    if not isinstance(target, str) or not TOOL_RE.match(target):
        problems.append(f"{where} names a target that is not a tool name")
    elif kind is StepKind.SKILL and not target.startswith("skill."):
        problems.append(f"{where} is a skill step and its target is not a skill tool")
    arguments, wrong = _read_arguments(where, item.get("arguments", {}))
    problems.extend(wrong)
    outputs, wrong = _read_outputs(where, item.get("outputs", []))
    problems.extend(wrong)
    after = item.get("after", [])
    if not isinstance(after, list) or not all(isinstance(one, str) for one in after):
        problems.append(f"{where} follows a list of step ids")
        after = []
    retry, wrong = _read_retry(where, item.get("retry", {}))
    problems.extend(wrong)
    try:
        on_failure = OnFailure(str(item.get("on_failure", OnFailure.STOP.value)))
    except ValueError:
        problems.append(
            f"{where} has a failure path that is not one of {[o.value for o in OnFailure]}"
        )
        on_failure = OnFailure.STOP
    when, wrong = _read_when(where, item.get("when"))
    problems.extend(wrong)
    handles = item.get("handles")
    if handles is not None and not (isinstance(handles, str) and STEP_ID_RE.match(handles)):
        problems.append(f"{where} handles a step by its id")
        handles = None
    flags = {key: item.get(key, False) for key in ("parallel", "writes")}
    if not all(isinstance(value, bool) for value in flags.values()):
        problems.append(f"{where} says parallel and writes with true or false")
    if problems:
        return None, problems
    return (
        Step(
            id=step_id,
            kind=kind,
            target=str(target),
            arguments=arguments,
            outputs=outputs,
            after=tuple(after),
            when=when,
            parallel=bool(flags["parallel"]),
            retry=retry,
            on_failure=on_failure,
            handles=handles,
            writes=bool(flags["writes"]),
        ),
        [],
    )


def _read_arguments(where: str, raw: object) -> tuple[dict[str, object], list[str]]:
    if not isinstance(raw, dict) or len(raw) > MOST_ARGUMENTS:
        return {}, [f"{where} gives its arguments as an object of at most {MOST_ARGUMENTS}"]
    problems: list[str] = []
    read: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not re.match(FIELD_NAME_RE, key):
            problems.append(f"{where} has an argument whose name is not a plain word")
        elif key in RESERVED_ARGUMENT_NAMES:
            problems.append(f"{where} names an argument a tool takes as wiring")
        elif isinstance(value, dict) and set(value) == {"$ref"}:
            ref, why = _ref_of(value["$ref"])
            if ref is None:
                problems.append(f"{where} argument {key!r}: {why}")
            else:
                read[key] = ref
        elif _literal(value):
            read[key] = value
        else:
            problems.append(f"{where} argument {key!r} is not plain data")
    return read, problems


def _read_outputs(where: str, raw: object) -> tuple[tuple[Output, ...], list[str]]:
    if not isinstance(raw, list) or len(raw) > MOST_OUTPUTS:
        return (), [f"{where} lists at most {MOST_OUTPUTS} outputs"]
    problems: list[str] = []
    found: list[Output] = []
    for one in raw:
        if not isinstance(one, dict) or set(one) != OUTPUT_KEYS:
            problems.append(f"{where} has an output that is not a name, a kind and a path")
            continue
        name, path = one["name"], one["path"]
        try:
            kind = FieldKind(str(one["kind"]))
        except ValueError:
            problems.append(
                f"{where} output {name!r} is of a kind that does not exist; prose is not a kind"
            )
            continue
        if not isinstance(name, str) or not re.match(FIELD_NAME_RE, name):
            problems.append(f"{where} has an output whose name is not a plain word")
        elif not isinstance(path, str) or not PATH_RE.match(path):
            problems.append(
                f"{where} output {name!r} says where it is in a way that is not a field"
            )
        else:
            found.append(Output(name=name, kind=kind, path=path))
    names = [one.name for one in found]
    problems.extend(
        f"{where} declares the output {one!r} more than once"
        for one in sorted({n for n in names if names.count(n) > 1})
    )
    return tuple(found), problems


def _read_retry(where: str, raw: object) -> tuple[Retry, list[str]]:
    if not isinstance(raw, dict) or set(raw) - RETRY_KEYS:
        return Retry(), [f"{where} gives its retry as a limit and a back-off"]
    limit, backoff = raw.get("limit", 0), raw.get("backoff_seconds", 0.0)
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 0 <= limit <= MOST_RETRIES
        or isinstance(backoff, bool)
        or not isinstance(backoff, (int, float))
        or not 0 <= backoff <= MOST_BACKOFF_SECONDS
    ):
        return Retry(), [
            f"{where} retries between 0 and {MOST_RETRIES} times, waiting at most "
            f"{MOST_BACKOFF_SECONDS:g} seconds"
        ]
    return Retry(limit=limit, backoff_seconds=float(backoff)), []


def _read_when(where: str, raw: object) -> tuple[Condition | None, list[str]]:
    if raw is None:
        return None, []
    if not isinstance(raw, dict) or not {"ref", "op"} <= set(raw) <= WHEN_KEYS:
        return None, [f"{where} gives its condition as a reference, a comparison and a value"]
    ref, why = _ref_of(raw["ref"])
    if ref is None:
        return None, [f"{where} condition: {why}"]
    try:
        op = Op(str(raw["op"]))
    except ValueError:
        return None, [f"{where} compares with something that is not one of {[o.value for o in Op]}"]
    value = raw.get("value")
    needs_value = op not in (Op.IS_TRUE, Op.IS_FALSE)
    if needs_value and (isinstance(value, (list, dict)) or not _literal(value)):
        return None, [f"{where} compares with a value that is not a plain number, word or flag"]
    return Condition(ref=ref, op=op, value=value if needs_value else None), []


def _read_together(steps: Sequence[Step]) -> list[str]:
    """What the steps say about each other: order, reads, handlers."""
    problems: list[str] = []
    ids = [one.id for one in steps]
    problems.extend(
        f"the step {one!r} is listed more than once"
        for one in sorted({i for i in ids if ids.count(i) > 1})
    )
    if problems:
        return problems
    position = {one: index for index, one in enumerate(ids)}
    after = {one.id: one.after for one in steps}
    declared = {one.id: {out.name: out for out in one.outputs} for one in steps}
    handlers = [one for one in steps if one.handles is not None]
    for one in steps:
        for before in one.after:
            if before not in position:
                problems.append(f"step {one.id!r} follows {before!r}, which is not a step here")
            elif position[before] >= position[one.id]:
                problems.append(
                    f"step {one.id!r} follows {before!r}, which is not listed before it"
                )
        reads = [(f"argument {k!r}", v) for k, v in one.arguments.items() if isinstance(v, Ref)]
        if one.when is not None:
            reads.append(("condition", one.when.ref))
        if problems:
            continue
        visible = _ancestors(one.id, after)
        for label, ref in reads:
            if ref.step_id not in visible:
                problems.append(
                    f"step {one.id!r} {label} reads {ref}, and it does not follow {ref.step_id!r}. "
                    f"{A_STEP_READS_ONLY_WHAT_AN_EARLIER_STEP_DECLARED}"
                )
            elif ref.name not in declared[ref.step_id]:
                problems.append(f"step {one.id!r} {label} reads {ref}, which was never declared")
        if one.handles is not None:
            if one.handles not in one.after:
                problems.append(
                    f"handler {one.id!r} handles {one.handles!r} and does not follow it"
                )
            elif position.get(one.handles, -1) < 0:
                problems.append(f"handler {one.id!r} handles a step that is not here")
    if problems:
        return problems
    for one in steps:
        named = [h for h in handlers if h.handles == one.id]
        if one.on_failure is OnFailure.HANDLER and len(named) != 1:
            problems.append(
                f"step {one.id!r} hands over to a handler and exactly one step must handle it"
            )
        if one.on_failure is not OnFailure.HANDLER and named:
            problems.append(
                f"step {one.id!r} has a handler and its failure path does not hand over"
            )
        if one.handles is not None and one.handles == one.id:
            problems.append(f"step {one.id!r} handles itself")
    return problems
