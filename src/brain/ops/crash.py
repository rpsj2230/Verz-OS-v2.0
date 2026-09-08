"""What survives a process dying, what must not happen twice, and what is re-checked on the
way back.

Three modules already answer a third of this each and none of them can answer the question a
person asks after a worker is killed. `brain.ops.queue.verdict_for` decides what becomes of an
in-flight row and knows nothing about side effects. `brain.ops.idempotency.resume` decides what
becomes of a side-effecting record and knows nothing about workers. And `brain.ops.checkpoints`
argues that a resume re-resolves entitlements and holds no resume. This module is the join.

**The boundary set is derived from the source, twice, because a typed one goes stale on the
day somebody adds a state.** That is not hypothetical: `tests/unit/test_idempotency.py` carries
eleven crash points as a literal list, written by hand, and a seventh member of `OperationState`
would leave it green and short. So `durable_machines` finds the state machines by reading them,
two independent ways that have to agree: a syntactic scan of `src/brain` that imports nothing,
and a runtime scan of the imported package. **Both walk the whole tree**, which is the half the
first draft of this module got wrong: it scanned every file for the syntax and only
`brain.ops` for the objects, so a machine written anywhere else would have been reported as a
disagreement between the scans rather than as a machine. See
`A_TYPED_BOUNDARY_LIST_IS_A_LIST_THAT_GOES_STALE`.

**A boundary is a durable write, and there is one before the first edge.** For each machine
every edge of its transition table is a point at which a process can die with that write
committed, and so is the write that created the record, which no edge describes: `CRASH_POINTS`
in that test file opens with exactly that case and an edge set alone would silently drop it.
`Crossing.CREATE` is that write, and the state it lands in is read off the record type's own
default rather than named here. An `EFFECT` boundary is the call itself, derived as an edge
from a state the plan will `ISSUE` from into one it will only `VERIFY`, which is the
definition of the instant the world may change: nothing issued on one side of it, nobody
knowing on the other. There is one today and a machine with no plan of its own has none.

**What a crash left behind is a question the machine answers about itself, or cannot.**
`idempotency.RESUME_PLAN` maps every state to what a recovering worker does with it, and the
four dispositions partition the states into "the world is unchanged" and "the world may have
changed": `ISSUE` and `STOP` mean nothing happened, `VERIFY` means nobody knows, `DONE` means it
happened once. `world_may_have_changed` reads that partition rather than restating it, **and is
`None` for a machine with no plan of its own**. The first draft made it `False` there, which put
`brain.ops.jobs` on record as saying a job killed mid-flight cannot have changed anything, in
flat contradiction of that module's own `_side_effect_state`, and in the exact direction
`unplanned_dispositions` is written to refuse: nobody-thought-about-it must never read as
nothing-happened. A borrowed plan is a delegated answer, not an answer. See
`A_BORROWED_PLAN_ANSWERS_FOR_A_RECORD_AND_NOT_FOR_THIS_MACHINE`.

**The dangerous edge is one whose origin may have changed the world and whose landing resumes
by issuing, and getting that comparison the wrong way round makes the check unfireable.** The
first draft asked whether a boundary both `world_may_have_changed` and resumed by `ISSUE`, and
both halves read the *landing* state: `ISSUE` is in `NOTHING_HAPPENED`, so the two conditions
are disjoint by construction and the finding could not be produced for any table whatsoever. It
is the *before* state that says whether anything may have been issued yet. Asked that way,
the edge `NO_PATH_FROM_UNKNOWN_TO_A_SECOND_ISSUE` exists to forbid, `VERIFYING` back to
`PENDING`, is reported the moment somebody adds it.

**The driver's one new rule is that a quarantine with a record on it may become a
verification, and nothing else.** `verdict_for` returns `QUARANTINE` for every orphaned job
whose task is not declared re-drive safe, which is correct and, on its own, sends every one of
them to a person. An orphaned job with an operation record nobody knows the fate of is the case
`idempotency` was built for: the way out of nobody knowing is asking the source. So
`recovery_for` keeps the queue's verdict and lets the record replace a quarantine with a
read-back. See `THE_RECORD_NARROWS_THE_VERDICT_AND_NEVER_WIDENS_IT`.

Rejected: ordering the four recovery actions by how much work they are and taking the smaller
of the queue's answer and the record's. That was the first draft's construction and it is
wrong in one direction that matters: an orphaned, quarantined job whose operation record says
`DONE` ordered below `NEEDS_A_PERSON`, so the join answered `LEAVE_IT`, and nothing then
reclaims a row whose worker is gone. `brain.ops.queue.Verdict` names that failure in its own
docstring, which is rows that sit in running for ever. The record settles what happened to the
side effect; it says nothing about the job, and only one of its four answers has anywhere to go
that a person would not have to.

Rejected: a scheduler. `brain.ops.controls` found on 2026-09-08 that twelve of the thirteen
scheduled safety mechanisms here have no caller at all, and `queue_redrive` and
`side_effect_resume` are two of them. Adding a fourteenth wire would answer the wrong half:
what was missing is not a timer, it is the decision the timer would call. `redrive` and
`verify_once` are now named on those two rows, so the registry records that each control has a
second half and that nothing calls it either.

Rejected: restating what a killed process is not. `idempotency.WHAT_THE_CRASH_MODEL_DOES_NOT_COVER`
says it once, about the durable write, the source honouring the key and a source that refuses
after acting, and every word of it is true here. The first draft wrote a second copy under a
different name, which is how one of them comes to be edited.

Rejected: a hardened `classify` that refuses an impossible HTTP status.
`brain.connectors.throttle.classify` reads any status below 400 as `OK`, so a client reporting
`0` for a failed connection records a side effect as `SUCCEEDED`, which is the worst direction
for this module's subject. It is a real defect and it is reported rather than guarded here,
because nothing in this repository makes a connector call: a guard on a path that does not
exist is the mechanism with no caller that `brain.ops.controls` counted thirteen of.

Scope: domain logic and derivation. Nothing here opens a connection, reads a clock or stores a
row; `now` is a parameter, and the only files touched are read as source.

Task ids: M17.2.2, M17.2.3, M17.2.4, M17.2.5, M30.4.4
"""

from __future__ import annotations

import ast
import enum
import importlib
import pkgutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import MISSING, dataclass
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Final

from brain.connectors.throttle import CallOutcome
from brain.ops.idempotency import (
    Disposition,
    IdempotencyError,
    Operation,
    OperationState,
    Verification,
    resume,
    state_after_call,
)
from brain.ops.idempotency import verify as verify_operation
from brain.ops.jobs import reach_carrying_fields
from brain.ops.queue import InFlight, Redrive, Verdict, verdict_for

#: The repository this module was installed from, used only by the derived scans below.
#:
#: Four levels up from `src/brain/ops/crash.py`, derived the way `brain.ops.controls.REPO` and
#: `brain.ops.sweeps.REPO` are and for the same reason: a written path is right on one machine.
REPO: Final[Path] = Path(__file__).resolve().parents[3]

#: Everything this repository ships as code. Where the syntactic scan looks.
SRC: Final[Path] = REPO / "src" / "brain"

#: The package the runtime scan walks. The whole of it, so the two scans ask one question over
#: one tree; see the module docstring for what a mismatch between their scopes would report.
PACKAGE: Final = "brain"

# ------------------------------------------------------------------ written-down reasons
#: The reason the boundary set is computed rather than listed.
A_TYPED_BOUNDARY_LIST_IS_A_LIST_THAT_GOES_STALE: Final = (
    "A crash point written down by hand is right on the day it is written and silently short "
    "afterwards. tests/unit/test_idempotency.py carries eleven of them as a literal, and a "
    "seventh member of OperationState would leave that list green, complete-looking and "
    "missing the state nobody had thought about, which is the only kind that matters. So the "
    "boundaries are read out of the transition tables themselves: a new state or a new edge "
    "arrives as a new boundary the property has to hold at, without anybody remembering to "
    "add it. Derived twice, because one derivation has one blind spot: a syntactic scan "
    "cannot see a table built in a shape it does not recognise, and a runtime scan cannot see "
    "a table in a module that will not import. Both walk the same tree, or the disagreement "
    "between them reports the difference in their scopes instead of a difference in the code."
)

#: Why the queue's verdict is the ceiling and the operation record may only narrow it.
THE_RECORD_NARROWS_THE_VERDICT_AND_NEVER_WIDENS_IT: Final = (
    "brain.ops.queue.verdict_for decides freshness, the re-drive cap and re-drive safety, in "
    "that order, and every one of those is a reason to do less. An operation record can turn "
    "a quarantine into a verification, because asking the source is exactly what resolves "
    "nobody knowing and is what the record exists for. It must never turn a dead letter into "
    "a run, or a live job into anything at all: a record says what happened to one side "
    "effect and knows nothing about the worker that was killing containers or the heartbeat "
    "that is fresh. And it must not turn a quarantine into leaving the row alone either, "
    "however settled the side effect is, because the job is still orphaned and nothing else "
    "is going to come back for it."
)

#: Why a job declaring itself safe while carrying an unsettled record goes to a person.
TWO_DECLARATIONS_THAT_CANNOT_BOTH_BE_TRUE: Final = (
    "Redrive.SAFE is a task author's claim that running the job twice changes nothing the "
    "world can see. An operation record past PENDING is the machine's record that a request "
    "left this process. Both cannot be true. Believing the author re-runs a side effect "
    "nobody can withdraw; believing the record parks work that was genuinely safe and costs a "
    "person's afternoon. The cheap resolution is to pick one, and the cheap resolution is how "
    "a duplicate payment gets made by a rule that read sensibly. So it is reported with both "
    "halves named, which is the one outcome that cannot be wrong."
)

#: Why a resume does not carry a reach, and what that buys.
A_RESUME_HAS_NOTHING_TO_BELIEVE: Final = (
    "The re-check at a resume point is not a step somebody performs, it is the absence of an "
    "alternative. A resumable record carries identifiers and no entitlement set, so the work "
    "cannot be reconstituted without going back through the gate, and going back through the "
    "gate is what resolves the reach at that instant. A record that carried the reach would "
    "make the re-check optional, and an optional re-check is a stored permission decision "
    "that outlives the decision: a grant revoked while a job sat in a queue would not take "
    "effect, which is the one place in this system revocation could fail to mean anything."
)

#: Why a machine that imports its recovery plan is not thereby able to answer for its own
#: boundaries.
A_BORROWED_PLAN_ANSWERS_FOR_A_RECORD_AND_NOT_FOR_THIS_MACHINE: Final = (
    "brain.ops.jobs declares a state machine, declares no recovery plan, and looks what a "
    "crash left behind up in brain.ops.idempotency.RESUME_PLAN. That import is what keeps it "
    "from being a state graph nobody can recover from, and it is not an answer about a job "
    "boundary: the plan it borrows is keyed on an operation's states, and the question "
    "'may this write have left the world different' is being asked about a job's. The honest "
    "value is that this machine does not say, which is None rather than False. False is the "
    "reading a sweep would act on, and acting on it means re-driving a job that had already "
    "sent something."
)


class CrashError(Exception):
    """A recovery was asked for in a shape that cannot be answered.

    Outside `brain.core.errors` for the reason `brain.ops.idempotency.IdempotencyError` gives
    about itself: nobody asking a question ever sees this. It is a mistake by whoever wired
    the recovery sweep up, and it should stop that sweep rather than degrade an answer.
    """


# ------------------------------------------------------- the machines, read out of the source
@dataclass(frozen=True)
class Machine:
    """One durable state machine, as it was found rather than as anybody described it.

    `states`, `edges` and `terminal` are names rather than enum members, because two machines
    in two modules have two unrelated enums and the point of this type is to hold them in one
    list.
    """

    #: The dotted module the table was found in.
    module: str
    #: The name the table is bound to at module scope.
    symbol: str
    #: The enum the table is keyed on, qualified by its module.
    kind: str
    states: tuple[str, ...]
    #: The state a newly created record of this machine is in, read off the record type's own
    #: default. Empty when no record type declares one, which `machine_gaps` reports: without
    #: it the write that created the record is a boundary nothing enumerates.
    start: str
    edges: tuple[tuple[str, str], ...]
    terminal: frozenset[str]
    #: state -> (state a recovering worker moves it to, what it then does). Empty where the
    #: module declares none of its own.
    plan: Mapping[str, tuple[str, str]]
    #: Where the plan came from, as `module.symbol`, or empty when this machine has none it
    #: can reach. Declared and borrowed are different answers and this says which; see
    #: `A_BORROWED_PLAN_ANSWERS_FOR_A_RECORD_AND_NOT_FOR_THIS_MACHINE`.
    plan_from: str

    @property
    def name(self) -> str:
        """How a boundary names the machine it belongs to."""
        return f"{self.module}.{self.symbol}"

    @property
    def declares_its_own_plan(self) -> bool:
        """Whether the plan is this module's, rather than one it imports or does not have."""
        return bool(self.plan)


def _is_transition_table(node: ast.stmt) -> str:
    """The name a module-level transition table is bound to, or empty for anything else.

    The shape recognised is `NAME = MappingProxyType({State.X: frozenset({...}), ...})`, with
    or without an annotation, where every key is an attribute of one name. That is what both
    tables in this repository are, and recognising a shape rather than a name is what makes a
    third one arrive on its own.

    Deliberately narrow. A wider matcher would start reporting ordinary lookup tables as state
    machines, and a boundary set with an invented machine in it is worse than one that is
    short, because the runtime scan next to this exists to catch short.
    """
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        name, value = node.target.id, node.value
    elif isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            return ""
        name, value = target.id, node.value
    else:
        return ""
    if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
        return ""
    if value.func.id != "MappingProxyType" or len(value.args) != 1:
        return ""
    table = value.args[0]
    if not isinstance(table, ast.Dict) or not table.keys:
        return ""
    owners: set[str] = set()
    for key, entry in zip(table.keys, table.values, strict=True):
        if not isinstance(key, ast.Attribute) or not isinstance(key.value, ast.Name):
            return ""
        owners.add(key.value.id)
        if not isinstance(entry, ast.Call) or not isinstance(entry.func, ast.Name):
            return ""
        if entry.func.id != "frozenset":
            return ""
    return name if len(owners) == 1 else ""


@cache
def _sources(src: Path | None = None) -> tuple[Path, ...]:
    """Every Python file this repository ships, excluding this one.

    Excluded because this module holds no state machine and would only ever be parsed to
    prove that. Cached for the reason `brain.ops.controls._sources` is: the tree does not move
    underneath a running process, and a tuple rather than a list so a cached answer is not one
    a caller can edit for everybody else.
    """
    root = SRC if src is None else src
    here = Path(__file__).resolve()
    return tuple(
        sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts and p != here)
    )


@cache
def declared_tables(src: Path | None = None) -> tuple[tuple[str, str], ...]:
    """Every transition table this repository declares, as (module, symbol), in name order.

    Syntactic and importing nothing, which is the half a runtime scan cannot do: a machine in
    a module that will not import is still reported, and reported as a machine rather than as
    silence.

    A file that does not parse raises rather than being skipped, following
    `brain.ops.controls._parsed`: the tree is broken, every other gate is about to say so more
    clearly than this one would, and swallowing it turns a broken repository into a scan that
    quietly stopped seeing a module.
    """
    root = SRC if src is None else src
    found: list[tuple[str, str]] = []
    for path in _sources(src):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = "brain." + ".".join(path.relative_to(root).with_suffix("").parts)
        found.extend((module, name) for name in map(_is_transition_table, tree.body) if name)
    return tuple(sorted(found))


@cache
def imported_tables(package: str = PACKAGE) -> tuple[tuple[str, str], ...]:
    """Every transition table reachable by importing `package`, as (module, symbol).

    The runtime half, and it sees what the syntactic half cannot: a table assembled by a
    comprehension, a loop or a helper still answers the shape question here, because the
    question is asked of the object rather than of the text that built it.

    `walk_packages` rather than `iter_modules`, so this covers the same tree the syntactic
    scan reads. The first draft walked `brain.ops` alone against a syntactic scan of
    everything, which makes `machine_gaps` report the difference between two scopes and call
    it a difference between two scans.

    An import failure is not caught. A module in this package that will not import is a broken
    repository and every other gate is about to say so; catching it here would turn that into
    a machine silently leaving the boundary set. Cached because the walk imports the whole
    tree, which costs seconds rather than milliseconds.
    """
    root = importlib.import_module(package)
    found: list[tuple[str, str]] = []
    for info in pkgutil.walk_packages(root.__path__, prefix=f"{package}."):
        module = importlib.import_module(info.name)
        found.extend(
            (module.__name__, name)
            for name, value in vars(module).items()
            if not name.startswith("_") and _keyed_by_one_enum(value) is not None
        )
    return tuple(sorted(set(found)))


def _keyed_by_one_enum(value: object) -> type[enum.Enum] | None:
    """The enum a mapping is a transition table over, or None if it is not one.

    Exhaustive over the enum, and every value a set of members of that same enum. Exhaustive
    rather than "keys are members", because a partial mapping is a lookup table with a default
    somewhere, and a state machine with a default is one where the state nobody thought about
    picks a behaviour by accident.
    """
    if not isinstance(value, Mapping) or not value:
        return None
    kind = type(next(iter(value)))
    if not (isinstance(kind, type) and issubclass(kind, enum.Enum)):
        return None
    if set(value) != set(kind):
        return None
    for onward in value.values():
        if not isinstance(onward, frozenset | set):
            return None
        if any(not isinstance(one, kind) for one in onward):
            return None
    return kind


def _is_recovery_plan(value: object, kind: type[enum.Enum]) -> Mapping[str, tuple[str, str]] | None:
    """A mapping read as a recovery plan over `kind`, or None if it is not one.

    Found by shape rather than by name: exhaustive over the same enum, values a pair of that
    state and a member of some other enum. That is `brain.ops.idempotency.RESUME_PLAN` and
    nothing else in this repository, and a second one written in the same shape would be found
    without being named here.
    """
    if not isinstance(value, Mapping) or set(value) != set(kind):
        return None
    pairs: dict[str, tuple[str, str]] = {}
    for state, entry in value.items():
        if not isinstance(entry, tuple) or len(entry) != 2:
            return None
        landed, action = entry
        if not isinstance(landed, kind) or not isinstance(action, enum.Enum):
            return None
        if isinstance(action, kind):
            return None
        pairs[str(state.name)] = (str(landed.name), str(action.name))
    return pairs


def _declared_plan(
    module: object, kind: type[enum.Enum]
) -> tuple[str, Mapping[str, tuple[str, str]]]:
    """The name this module binds a recovery plan over `kind` to, and the plan, or ("", {}).

    Keyed on the machine's own enum, which is what keeps a borrower from counting as a
    source: `brain.ops.jobs` binds `RESUME_PLAN` because it imports it, and that mapping is
    exhaustive over `OperationState` rather than over the machine `jobs` declares, so it does
    not answer here.

    Private names are considered rather than skipped. There was a `startswith("_")` filter
    here and it was an equivalent mutant: `_is_recovery_plan` is what decides, and it already
    refuses every private mapping in this repository. It was also arguably wrong, because a
    module that declares its plan privately has still declared one.
    """
    for name, value in vars(module).items():
        plan = _is_recovery_plan(value, kind)
        if plan is not None:
            return name, plan
    return "", {}


def _resolved(src: Path | None = None) -> tuple[tuple[str, str, object, type[enum.Enum]], ...]:
    """Every declared table with the module it lives in and the enum it turned out to key on.

    One pass over the source scan's answer, and it raises before anything downstream sees a
    table that is only one on paper. That ordering is what removes a `kind is None` branch
    from every caller: the alternative had `_plan_symbols` skipping such a table and
    `durable_machines` raising for it, so which behaviour a reader got depended on which
    function reached it first.
    """
    out: list[tuple[str, str, object, type[enum.Enum]]] = []
    for module, symbol in declared_tables(src):
        imported = importlib.import_module(module)
        kind = _keyed_by_one_enum(getattr(imported, symbol))
        if kind is None:
            msg = (
                f"{module}.{symbol} reads as a transition table in the source and is not one "
                "at runtime, so the boundary set would depend on which scan was asked"
            )
            raise CrashError(msg)
        out.append((module, symbol, imported, kind))
    return tuple(out)


@cache
def _plan_symbols(src: Path | None = None) -> tuple[tuple[str, str], ...]:
    """Every recovery plan declared beside a machine, as (module, symbol), in name order.

    Derived by asking each machine's module for one, so the set a borrower can borrow from is
    the set that exists rather than a name written here. `_declared_plan` is what keeps a
    borrower from counting as a source, by asking for a plan over the machine's own enum.
    """
    found: list[tuple[str, str]] = []
    for module, _, imported, kind in _resolved(src):
        name, plan = _declared_plan(imported, kind)
        if plan:
            found.append((module, name))
    return tuple(sorted(found))


def _imported_plan(module: str, src: Path | None = None) -> str:
    """Where this module imports a recovery plan from, as `module.symbol`, or empty.

    Asked of the source rather than of the imported module, because an imported name that has
    been shadowed since is still an import and this question is about where the answer comes
    from. `brain.ops.jobs` is the case: it declares a machine, declares no plan, and looks
    what a crash left behind up in `brain.ops.idempotency.RESUME_PLAN` rather than spelling
    the most expensive state in the system a second time.

    The file is read without checking that it is there. It is: this is only ever asked about a
    module `declared_tables` produced by parsing that same file, under that same root. There
    was a `path.exists()` guard and it could not be made to fire, which is the shape
    `brain.ops.queue.verdict_for` records deleting for the same reason.
    """
    root = SRC if src is None else src
    path = root.joinpath(*module.removeprefix("brain.").split(".")).with_suffix(".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {symbol: owner for owner, symbol in _plan_symbols(src)}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for one in node.names:
            if one.name in wanted:
                return f"{wanted[one.name]}.{one.name}"
    return ""


def _start_state(module: object, enum_name: str) -> str:
    """The state a newly created record of this machine is in, from the record's own default.

    Read off `__dataclass_fields__` rather than named here, so the write that creates a record
    is a boundary derived like every other one. A record type with no default contributes
    nothing: it is a record whose creator chooses the state, and there is no single landing
    state for the write that made it.

    The annotation is not consulted, only the default. There was a check on the annotation
    text as well and it was an equivalent mutant: a default that is a member of this enum
    answers the question by itself, and the annotation is the weaker of the two readings
    because `from __future__ import annotations` leaves it a string that a type alias can
    spell any way it likes.

    Classes are not separated from instances here, unlike in `resume_points`, and the
    difference is that this returns a state name rather than the object: an instance's
    `__dataclass_fields__` is its class's, so both answer identically and a guard between them
    was an equivalent mutant.
    """
    for value in vars(module).values():
        declared: Mapping[str, object] = getattr(value, "__dataclass_fields__", {})
        for spec in declared.values():
            default = getattr(spec, "default", MISSING)
            if isinstance(default, enum.Enum) and type(default).__name__ == enum_name:
                return str(default.name)
    return ""


def durable_machines(src: Path | None = None) -> tuple[Machine, ...]:
    """Every durable state machine in this repository, in module order.

    Discovered syntactically and then read at runtime, which is the order that matters: the
    syntactic scan decides *which* modules hold a machine without importing anything, and the
    import happens only for those. A module that fails to import therefore fails loudly here
    and only here, rather than removing a machine from the boundary set everywhere.
    """
    machines: list[Machine] = []
    for module, symbol, imported, kind in _resolved(src):
        table = getattr(imported, symbol)
        plan_name, plan = _declared_plan(imported, kind)
        machines.append(
            Machine(
                module=module,
                symbol=symbol,
                kind=f"{kind.__module__}.{kind.__name__}",
                states=tuple(str(one.name) for one in kind),
                start=_start_state(imported, kind.__name__),
                edges=tuple(
                    (str(state.name), str(onward.name))
                    for state in kind
                    for onward in sorted(table[state], key=lambda one: str(one.name))
                ),
                terminal=frozenset(str(state.name) for state in kind if not table[state]),
                plan=plan,
                plan_from=f"{module}.{plan_name}" if plan else _imported_plan(module, src),
            )
        )
    return tuple(machines)


def machine_gaps(machines: Sequence[Machine] | None = None) -> tuple[str, ...]:
    """Every way the two derivations disagree, or a machine cannot be recovered from.

    Four findings, and the first two are what make the enumeration trustworthy at all. A table
    the source scan found and the runtime scan did not is a machine in a module nothing
    imports, or a symbol rebound since. A table the runtime scan found and the source scan did
    not is a machine built in a shape the syntactic matcher does not recognise, which is the
    blind spot that would otherwise make a derived list quietly as short as a typed one.

    Then a machine whose records declare no starting state, which is the write that created
    the record having no boundary to be enumerated as. And a machine that neither declares a
    recovery plan nor imports one, which separates `brain.ops.jobs` from a third machine
    written by somebody who had not thought about a crash at all.

    There is deliberately no check that every terminal state has a plan entry. A plan is
    accepted only when it is exhaustive over the machine's enum, so that condition cannot be
    false for any table this module will read, and the first draft carried it as a guard that
    could never fire. `brain.ops.queue.verdict_for` records removing the same shape of clause
    for the same reason: one that reads as a guard and guards nothing is worse than its
    absence, because the next person to touch this trusts it.

    The machines are a parameter defaulting to the discovered ones, for the reason
    `brain.ops.queue.concurrency_gaps` takes its allocation: a check that can only ever be run
    against the two machines this repository happens to have cannot be shown to fail, and a
    check nobody has seen fail is a check nobody knows works.

    **There is no `src` parameter, unlike every other derived function here, and the asymmetry
    is the point.** The two scans are a question about this tree and only this tree: pointed at
    a fabricated root, the syntactic half would read the fabricated modules and the runtime
    half would still read the installed package, and every finding would be the difference
    between two roots rather than between two scans. A caller who wants to drive the checks
    over a machine of their own passes the machine, which is what `machines` is for.
    """
    rows = durable_machines() if machines is None else tuple(machines)
    declared = set(declared_tables())
    imported = set(imported_tables())
    findings: list[str] = []
    findings.extend(
        f"{module}.{symbol} is declared in the source and not found at runtime, so the "
        "boundary set depends on which scan a caller asked"
        for module, symbol in sorted(declared - imported)
    )
    findings.extend(
        f"{module}.{symbol} is a transition table at runtime and is not written in a shape "
        "the source scan recognises, so it would be missing from a scan that cannot import"
        for module, symbol in sorted(imported - declared)
    )
    for machine in rows:
        if not machine.start:
            findings.append(
                f"{machine.name} has no record type declaring a starting state, so the write "
                "that creates a record lands nowhere this can name and a kill straight after "
                "it is a boundary nothing enumerates"
            )
        if not machine.plan_from:
            findings.append(
                f"{machine.name} declares no recovery plan and imports none, so what a crash "
                "left behind is not answerable from the machine itself"
            )
    return tuple(findings)


# --------------------------------------------------------------- the boundaries themselves
class Crossing(enum.StrEnum):
    """What kind of boundary this is. Three, and they fail differently.

    A `CREATE` and a `RECORD` crossing are ours: the write happened or it did not, and the
    next process reads whichever. An `EFFECT` crossing is the source's: it happened or it did
    not and nothing here can tell, which is the entire reason
    `brain.ops.idempotency.OperationState.UNKNOWN` exists.
    """

    #: The durable write that created the record. No state before it.
    CREATE = "create"
    #: A durable write moving a record from one state to the next.
    RECORD = "record"
    #: The call itself. The instant the world may change, bracketed by two record writes.
    EFFECT = "effect"


@dataclass(frozen=True)
class Boundary:
    """One point at which a process can die with something already committed.

    `after` is the state the next process finds, which is what makes a boundary testable at
    all: a kill is not simulated, it is a resume from `after`.
    """

    #: The machine this belongs to, as `module.symbol`. Not the enum's name: two machines
    #: could be keyed on one enum and a boundary has to say which table it came out of.
    machine: str
    crossing: Crossing
    #: The state the record was in before this write, empty for the write that created it.
    before: str
    after: str
    #: Whether a process that died immediately after this may have left the world changed.
    #: Read from the machine's own recovery plan, and `None` where the machine has no plan of
    #: its own to read; see `A_BORROWED_PLAN_ANSWERS_FOR_A_RECORD_AND_NOT_FOR_THIS_MACHINE`.
    world_may_have_changed: bool | None


#: Recovery dispositions that mean nothing outside this process has happened yet.
#:
#: Named rather than derived as the complement, for the reason
#: `brain.ops.reliability.FAILURE_STATUSES` is: a complement classifies a fifth disposition
#: the moment somebody adds one, silently, and in the flattering direction.
#: `unplanned_dispositions` reports one nobody has classified.
NOTHING_HAPPENED: Final[frozenset[str]] = frozenset({"ISSUE", "STOP"})

#: Recovery dispositions that mean the world may already be different.
SOMETHING_MAY_HAVE_HAPPENED: Final[frozenset[str]] = frozenset({"VERIFY", "DONE"})

#: The disposition a state has when a recovering worker would make the call from it.
_ISSUES: Final = "ISSUE"

#: The disposition a state has when nobody knows whether the call landed.
_ASKS: Final = "VERIFY"


def unplanned_dispositions(
    machines: Sequence[Machine] | None = None, src: Path | None = None
) -> tuple[str, ...]:
    """Dispositions a recovery plan uses that neither set above classifies.

    The partition check, and it is the reason `world_may_have_changed` can be two-valued
    wherever it is answered at all. A disposition in neither set would silently take the
    safe-looking branch of an `in NOTHING_HAPPENED` test, which is the wrong one: unclassified
    means nobody thought about it, and nobody-thought-about-it must never read as
    nothing-happened.
    """
    rows = durable_machines(src) if machines is None else tuple(machines)
    used = {action for machine in rows for _, action in machine.plan.values()}
    return tuple(sorted(used - NOTHING_HAPPENED - SOMETHING_MAY_HAVE_HAPPENED))


def _changed(machine: Machine, state: str) -> bool | None:
    """Whether a record of this machine sitting in `state` may correspond to a changed world."""
    if not machine.declares_its_own_plan:
        return None
    return machine.plan[state][1] in SOMETHING_MAY_HAVE_HAPPENED


def side_effect_boundaries(
    machines: Sequence[Machine] | None = None, src: Path | None = None
) -> tuple[Boundary, ...]:
    """Every point a kill has to be survivable at, derived from the machines.

    One `CREATE` boundary per machine, which is the write that made the record and which no
    edge describes. One `RECORD` boundary per edge, because every edge is a write and a
    process can die after any of them. And one `EFFECT` boundary per issuing edge, which is
    the call: derived as an edge from a state the machine's own plan will `ISSUE` from into
    one it will only `VERIFY`. That pair of dispositions is the definition of the instant the
    world may change, with nothing issued on one side of it and nobody knowing on the other,
    and it is why the edge from `PENDING` to `FAILED` is not one: a refusal before anything
    left the process is a claim, not a doubt.

    A machine with no plan of its own contributes only record boundaries and answers `None`
    to whether the world may have changed at them. That is correct rather than a gap:
    `brain.ops.jobs` holds no side effect, it holds a job whose side effect is an operation
    record with boundaries of its own.

    The machines are a parameter defaulting to the discovered ones, so the derivation can be
    driven over a machine this repository does not have. That is what makes the claims in this
    docstring checkable rather than asserted: `tests/invariants/test_crash_exactly_once.py`
    hands it a table with an edge back to the issuing state and watches a second boundary
    arrive without anybody adding a line here.
    """
    rows = durable_machines(src) if machines is None else tuple(machines)
    boundaries: list[Boundary] = []
    for machine in rows:
        if machine.start:
            boundaries.append(
                Boundary(
                    machine=machine.name,
                    crossing=Crossing.CREATE,
                    before="",
                    after=machine.start,
                    world_may_have_changed=_changed(machine, machine.start),
                )
            )
        for before, after in machine.edges:
            boundaries.append(
                Boundary(
                    machine=machine.name,
                    crossing=Crossing.RECORD,
                    before=before,
                    after=after,
                    world_may_have_changed=_changed(machine, after),
                )
            )
            if not machine.declares_its_own_plan:
                continue
            if machine.plan[before][1] == _ISSUES and machine.plan[after][1] == _ASKS:
                boundaries.append(
                    Boundary(
                        machine=machine.name,
                        crossing=Crossing.EFFECT,
                        before=before,
                        after=after,
                        world_may_have_changed=True,
                    )
                )
    return tuple(boundaries)


def boundary_gaps(
    machines: Sequence[Machine] | None = None, src: Path | None = None
) -> tuple[str, ...]:
    """Every boundary a crash could not be recovered from (M17.2.3).

    Two findings. A machine using a disposition nobody has classified, which is
    `unplanned_dispositions`. And **an edge out of a state that may already have changed the
    world into one a recovering worker will issue from**, which is the duplicate-side-effect
    bug written as a graph property rather than as a row of a table.

    The direction of that second comparison is the whole of it and the first draft had it the
    wrong way round. It asked whether the *landing* state both may have changed the world and
    resumes by issuing, and `ISSUE` is in `NOTHING_HAPPENED`, so the two halves are disjoint
    by construction and no table could ever have produced the finding. What says whether
    anything may have been issued yet is the state the record was in *before* the write. Asked
    that way, the edge `brain.ops.idempotency.NO_PATH_FROM_UNKNOWN_TO_A_SECOND_ISSUE` exists
    to forbid, `VERIFYING` back to `PENDING`, is reported the day somebody adds it.

    Empty today. It stays empty only while every state a write can land in is one somebody has
    said what to do with. The machines are a parameter for the reason `machine_gaps` takes
    one, and here it is load-bearing: the forbidden edge does not exist in this repository, so
    a check that could only be run against the tables it ships with could never be shown to
    produce its own finding.

    A machine with no plan of its own is carried by `_changed` answering `None` rather than by
    a clause skipping it, which is the same construction `brain.ops.queue.verdict_for` records
    choosing for a future heartbeat: a signed answer rather than a branch. The `and` after it
    is what keeps the plan lookup from being reached for a machine that has no plan.
    """
    rows = durable_machines(src) if machines is None else tuple(machines)
    findings: list[str] = list(unplanned_dispositions(rows))
    boundaries = side_effect_boundaries(rows)
    for machine in rows:
        findings.extend(
            f"{machine.name}: a crash after {boundary.before} to {boundary.after} may have "
            "left the world changed and resumes by issuing, which is the second side effect "
            "wearing the first attempt's name"
            for boundary in boundaries
            if boundary.machine == machine.name
            and boundary.crossing is Crossing.RECORD
            and _changed(machine, boundary.before)
            and machine.plan[boundary.after][1] == _ISSUES
        )
    return tuple(findings)


# --------------------------------------------------------------- resume points (M17.2.5)
def resume_points(
    machines: Sequence[Machine] | None = None, src: Path | None = None
) -> tuple[type, ...]:
    """Every record type a resume reads back, in name order.

    Derived from the machines: a record type is one whose dataclass carries a field annotated
    with a state of a discovered machine. That is `brain.ops.jobs.JobRecord` and
    `brain.ops.idempotency.Operation` today, and a third record with a state on it arrives
    here rather than being remembered.
    """
    found: dict[str, type] = {}
    for machine in durable_machines(src) if machines is None else tuple(machines):
        module = importlib.import_module(machine.module)
        _, _, enum_name = machine.kind.rpartition(".")
        for value in vars(module).values():
            if not isinstance(value, type):
                continue
            declared: Mapping[str, object] = getattr(value, "__dataclass_fields__", {})
            if any(enum_name in str(getattr(spec, "type", "")) for spec in declared.values()):
                found[f"{value.__module__}.{value.__name__}"] = value
    return tuple(found[name] for name in sorted(found))


def stored_reach_gaps(records: Sequence[type] | None = None) -> tuple[str, ...]:
    """Every resumable record that carries a permission decision (M17.2.5).

    The whole of the resume-time entitlement guarantee, stated as an absence. See
    `A_RESUME_HAS_NOTHING_TO_BELIEVE` and, at greater length,
    `brain.ops.checkpoints.ENTITLEMENT_IS_RESOLVED_AT_THE_ATTEMPT`.

    `brain.ops.jobs.reach_carrying_fields` is what decides what a reach looks like, rather
    than a second reading of the same question here: that function already answers it for
    `JobRecord` and answering it differently for the next record type is how two resume points
    come to disagree about whether a `Scope` is a permission decision.

    The record types are a parameter defaulting to the derived ones, and it is the only way
    this check can be watched refusing anything: no record in this repository carries a reach,
    which is the point, so a check that could only be run against them is one nobody has seen
    work.
    """
    return tuple(
        f"{record.__module__}.{record.__name__} carries {list(carried)}, so a resume could "
        "believe a permission decision taken before the crash instead of asking now"
        for record in (resume_points() if records is None else tuple(records))
        for carried in (reach_carrying_fields(record),)
        if carried
    )


# ------------------------------------------------------------- the re-drive driver (M17.2.2)
class Recovery(enum.StrEnum):
    """What happens to one orphaned job once both records have been read. Four, and no fifth.

    There is deliberately no "probably safe" and no "unknown". `brain.ops.queue.Verdict` gives
    the reasons for both: a middle rung is chosen by whoever is in a hurry, and a sweep that
    can answer "not sure" answers it for the rows nobody has thought about, which are the rows
    that then sit in running for ever.
    """

    #: Its heartbeat is fresh. Nothing to do, because somebody is still doing it.
    LEAVE_IT = "leave_it"
    #: Nothing was issued and the world is unchanged, so the work is simply done.
    RUN_AGAIN = "run_again"
    #: Ask the source what happened. The only way out of nobody knowing.
    VERIFY = "verify"
    #: A person decides, because the two records disagree or there is nothing to ask.
    NEEDS_A_PERSON = "needs_a_person"


@dataclass(frozen=True)
class JobRecovery:
    """What one in-flight row gets, and both halves of why.

    Carries the queue's verdict as well as the action, for the reason
    `brain.ops.idempotency.Resumption` carries its reason: a row put in front of a person has
    to say which of the two records sent it there, and an action name on its own does not.
    """

    job_id: str
    verdict: Verdict
    recovery: Recovery
    reason: str

    @property
    def may_run_again(self) -> bool:
        return self.recovery is Recovery.RUN_AGAIN


#: What each verdict means before an operation record is consulted. Written as data for the
#: reason `brain.ops.idempotency.RESUME_PLAN` is: the property a reviewer has to be able to
#: check in ten seconds is how many verdicts can reach `RUN_AGAIN`, and a chain of branches
#: does not answer that.
#:
#: Exhaustive over `Verdict` and tested to be. A missing entry would pick a behaviour by
#: accident, and the accident nobody notices is the one that runs a job twice.
VERDICT_FLOOR: Final[Mapping[Verdict, Recovery]] = {
    Verdict.RUNNING: Recovery.LEAVE_IT,
    Verdict.REDRIVE: Recovery.RUN_AGAIN,
    Verdict.QUARANTINE: Recovery.NEEDS_A_PERSON,
    Verdict.DEAD_LETTER: Recovery.NEEDS_A_PERSON,
}

#: What an operation record does to a quarantine, which is the one verdict a record can
#: change. Exhaustive over `Disposition` and tested to be.
#:
#: Only `VERIFY` moves it, and that is the argument in
#: `THE_RECORD_NARROWS_THE_VERDICT_AND_NEVER_WIDENS_IT` written as data. The other three all
#: settle what happened to the *side effect* and say nothing about the *job*, which is still
#: orphaned, still not declared safe to repeat, and still going to sit in running for ever if
#: this answers `LEAVE_IT`.
QUARANTINE_WITH_A_RECORD: Final[Mapping[Disposition, Recovery]] = {
    Disposition.ISSUE: Recovery.NEEDS_A_PERSON,
    Disposition.VERIFY: Recovery.VERIFY,
    Disposition.DONE: Recovery.NEEDS_A_PERSON,
    Disposition.STOP: Recovery.NEEDS_A_PERSON,
}


def recovery_for(entry: InFlight, operation: Operation | None, now: datetime) -> JobRecovery:
    """What becomes of one in-flight job, reading the queue and the record together.

    The queue answers first and its answer stands unless one rule replaces it, for the reason
    `THE_RECORD_NARROWS_THE_VERDICT_AND_NEVER_WIDENS_IT` gives. Then three cases.

    **A live job is left alone whatever its record says.** A fresh heartbeat means the job is
    still running and its record is mid-flight by design, not by accident, and a sweep that
    verified it would be racing the worker that is about to write the next state.

    **A job declaring itself re-drive safe while carrying an unsettled record goes to a
    person.** See `TWO_DECLARATIONS_THAT_CANNOT_BOTH_BE_TRUE`. Checked before the verdict is
    used, because the two declarations contradict each other whether the queue wants to
    re-drive the job or has already given up on it.

    **A quarantine whose record nobody knows the fate of becomes a verification.** This is the
    one new answer in the module and the reason it exists. `verdict_for` sends every orphaned
    unsafe job to a person, which is right when nothing is known and wasteful when the record
    already says what to ask. A read-back is how nobody-knowing is resolved, and a machine can
    do it.
    """
    verdict = verdict_for(entry, now)
    floor = VERDICT_FLOOR[verdict]
    if operation is None:
        return JobRecovery(
            job_id=entry.job_id,
            verdict=verdict,
            recovery=floor,
            reason=_no_record_reason(verdict, entry),
        )
    if verdict is Verdict.RUNNING:
        return JobRecovery(
            job_id=entry.job_id,
            verdict=verdict,
            recovery=Recovery.LEAVE_IT,
            reason=(
                "its heartbeat is fresh, so the worker holding it is still writing states "
                "into that record and a sweep reading them would be racing it"
            ),
        )
    if entry.redrive is Redrive.SAFE and operation.state is not OperationState.PENDING:
        return JobRecovery(
            job_id=entry.job_id,
            verdict=verdict,
            recovery=Recovery.NEEDS_A_PERSON,
            reason=(
                f"the task is declared re-drive safe and its operation record is "
                f"{operation.state}. {TWO_DECLARATIONS_THAT_CANNOT_BOTH_BE_TRUE}"
            ),
        )
    plan = resume(operation)
    chosen = QUARANTINE_WITH_A_RECORD[plan.disposition] if verdict is Verdict.QUARANTINE else floor
    return JobRecovery(
        job_id=entry.job_id,
        verdict=verdict,
        recovery=chosen,
        reason=f"the queue says {verdict} and the record says {plan.disposition}: {plan.reason}",
    )


def _no_record_reason(verdict: Verdict, entry: InFlight) -> str:
    """Why an in-flight row with no operation record gets the verdict's own answer.

    A separate function because there are four verdicts and one of them means something quite
    different without a record: a quarantine with nothing to ask is the case that genuinely
    needs a person, and saying so is the difference between a queue somebody triages and a
    queue somebody stops reading.
    """
    if verdict is Verdict.QUARANTINE:
        return (
            f"{entry.task!r} is not declared re-drive safe and no operation record was found "
            "for it, so there is nothing to read back and nobody can say what it had done"
        )
    if verdict is Verdict.DEAD_LETTER:
        return (
            f"it has been re-driven {entry.redrives} time(s) and is doing this to workers "
            "rather than having it done to it"
        )
    if verdict is Verdict.REDRIVE:
        return (
            f"{entry.task!r} is declared re-drive safe and issued nothing that has a record, "
            "so running it again changes nothing the first run had not already changed"
        )
    return "its heartbeat is fresh"


def redrive(
    entries: Sequence[InFlight],
    operations: Mapping[str, Operation],
    now: datetime,
) -> tuple[JobRecovery, ...]:
    """Every in-flight job, decided, in the order they were given (M17.2.2).

    A row for every entry including the live ones, following
    `brain.ops.queue.redrive_plan`'s argument about its empty verdicts: a sweep whose output
    omits the rows it decided to leave alone is a sweep a reader cannot tell apart from one
    that never saw them.

    `operations` is keyed on job id, and a job with no entry is a job that issued nothing this
    layer can see, which is not the same as a job that issued nothing. That difference is the
    reason `Redrive.UNSAFE` is the default: an absent record and a safe task are the only
    combination that runs anything again.
    """
    return tuple(recovery_for(one, operations.get(one.job_id), now) for one in entries)


def runnable_again(plan: Iterable[JobRecovery]) -> tuple[str, ...]:
    """The job ids a recovery plan would run again, in the order decided.

    A function rather than a comprehension at each call site, so the exactly-once property has
    one place to be asserted against and a sweep cannot quietly filter on something else.
    """
    return tuple(one.job_id for one in plan if one.may_run_again)


# ------------------------------------------------- what a connector answered (M30.4.4)
#: What a read-back may answer with, as text. Derived from the vocabulary rather than typed,
#: so a fourth verification arrives here without anybody adding it.
ANSWERS: Final[frozenset[str]] = frozenset(one.value for one in Verification)


def answer_of(raw: object) -> Verification:
    """A connector's raw read-back answer as a verification, or a refusal naming what it said.

    **A read-back is the only exit from `UNKNOWN`, so the one thing it may never do is be
    generous.** `brain.ops.idempotency.state_after_verification` is a mapping lookup, which is
    correct and unforgiving: it raises on anything outside the vocabulary. That is safe and it
    is safe by accident of `KeyError`, and the accident is worth replacing with a sentence,
    because the edit somebody makes to a lookup that keeps raising in production is a
    `.get(answer, Verification.FOUND)`.

    Refuses a `bool` explicitly, before anything else. `True` is the answer a hurried adapter
    returns for "yes it is there" and `isinstance(True, int)` is `True`, so any check that
    admitted a number would admit it, and admitting it settles an operation as `SUCCEEDED` on
    a value that carries no evidence at all.

    Accepts the plain string spellings, because `Verification` is a `StrEnum` and an adapter
    reading a source's own field into `"found"` has said exactly what the enum says. What it
    does not accept is a spelling nobody declared, which is where a malformed response
    arrives.

    A member of `Verification` needs no branch of its own and had one. `Verification` is a
    `StrEnum`, so a member is a `str`, compares equal to its own value and is therefore in
    `ANSWERS`, and `Verification(member)` is the member: an early return for it was an
    equivalent mutant and is gone.
    """
    if isinstance(raw, bool) or not isinstance(raw, str):
        msg = (
            f"a read-back answered with {type(raw).__name__} {raw!r}, which is not one of "
            f"{sorted(ANSWERS)}. A verification is the only way out of an operation nobody "
            "knows the fate of, so an answer nobody declared settles nothing"
        )
        raise CrashError(msg)
    if raw not in ANSWERS:
        msg = (
            f"a read-back answered {raw!r}, which is not one of {sorted(ANSWERS)}; an "
            "operation is not settled on a word the vocabulary does not contain"
        )
        raise CrashError(msg)
    return Verification(raw)


def verify_once(operation: Operation, read_back: Callable[[Operation], object]) -> Operation:
    """Ask the source what happened, refusing an answer nobody declared.

    Delegated whole to `brain.ops.idempotency.verify`, which owns the write-ahead and the
    transition, exactly as `brain.ops.outbox.signature_for` delegates to
    `brain.channels.webhook.sign`: two copies of when a record moves to `VERIFYING` is how one
    of them stops moving it. What this adds is the one thing that module cannot check, which
    is what the connector on the other side of `ReadBackFn` actually returned, and the type
    here is deliberately weaker than `ReadBackFn` for that reason: a connector that answers
    rubbish cannot be represented by a callable that is typed as answering a `Verification`.

    A refused answer leaves the record where the caller had it. That is recoverable by
    construction rather than by care: `RESUME_PLAN` sends both `UNKNOWN` and `VERIFYING` to
    `VERIFY`, so a read-back that answered rubbish is asked again, which is the whole reason
    verification rather than retry is the way out.
    """

    def checked(one: Operation) -> Verification:
        return answer_of(read_back(one))

    return verify_operation(operation, checked)


def definite_refusals() -> tuple[CallOutcome, ...]:
    """Outcomes that settle an operation as `FAILED` without asking the source (M30.4.4).

    Computed by driving `brain.ops.idempotency.state_after_call` over the vocabulary rather
    than by listing the two that do it today, so an outcome added to
    `brain.connectors.throttle.CallOutcome` and mapped to `FAILED` shows up here instead of
    quietly joining a list.

    `QUOTA` is the member worth reading: a 429 is the one status this system takes as a
    definite answer without a read-back, on the grounds that a rate limiter refuses at the
    door. A source that applied a change and then answered 429 has lied about whether it
    acted, and `brain.ops.idempotency.WHAT_THE_CRASH_MODEL_DOES_NOT_COVER` says so.
    """
    settled: list[CallOutcome] = []
    for outcome in CallOutcome:
        try:
            state = state_after_call(outcome)
        except IdempotencyError:
            continue
        if state is OperationState.FAILED:
            settled.append(outcome)
    return tuple(settled)


__all__ = [
    "ANSWERS",
    "A_BORROWED_PLAN_ANSWERS_FOR_A_RECORD_AND_NOT_FOR_THIS_MACHINE",
    "A_RESUME_HAS_NOTHING_TO_BELIEVE",
    "A_TYPED_BOUNDARY_LIST_IS_A_LIST_THAT_GOES_STALE",
    "NOTHING_HAPPENED",
    "QUARANTINE_WITH_A_RECORD",
    "SOMETHING_MAY_HAVE_HAPPENED",
    "THE_RECORD_NARROWS_THE_VERDICT_AND_NEVER_WIDENS_IT",
    "TWO_DECLARATIONS_THAT_CANNOT_BOTH_BE_TRUE",
    "VERDICT_FLOOR",
    "Boundary",
    "CrashError",
    "Crossing",
    "JobRecovery",
    "Machine",
    "Recovery",
    "answer_of",
    "boundary_gaps",
    "declared_tables",
    "definite_refusals",
    "durable_machines",
    "imported_tables",
    "machine_gaps",
    "recovery_for",
    "redrive",
    "resume_points",
    "runnable_again",
    "side_effect_boundaries",
    "stored_reach_gaps",
    "unplanned_dispositions",
    "verify_once",
]
